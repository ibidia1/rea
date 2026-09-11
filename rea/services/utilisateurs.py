"""Les comptes du service : qui existe, avec quel rôle, et qui peut entrer
(SPEC §1.2 et §2.5).

Deux choses distinctes, qu'il ne faut pas confondre :

* **le rôle** dit ce que l'écran propose — un infirmier ne voit pas de bouton
  qui modifie le prescrit ;
* **le code d'accès** dit qui peut prendre ce rôle.

Sans le second, le premier n'est pas une protection : la liste d'ouverture
montre tous les noms, et rien n'empêche de choisir celui du chef de service.
Le code d'accès est donc facultatif compte par compte — un service qui
démarre n'en met nulle part, et se protège le jour où il en a besoin — mais
**tant qu'un compte n'en a pas, son rôle est une commodité, pas une serrure**.
Le logiciel le dit à l'écran plutôt que de laisser croire le contraire.

Le code n'est jamais gardé en clair : on stocke une empreinte salée
(PBKDF2-HMAC-SHA256), comme n'importe quel mot de passe. Ce n'est pas de la
sur-ingénierie — une base volée sur une clé USB rendrait autrement tous les
codes du service, et les gens réutilisent leurs codes ailleurs.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime

from .. import config
from ..db import Base
from ..domaine import droits as dom_droits

#: Les essais ratés, par compte, en mémoire du processus : nom -> (nombre,
#: heure du dernier essai). En mémoire et non en base, délibérément — un
#: redémarrage du logiciel remet les compteurs à zéro, ce qui est acceptable
#: (il faut un accès au serveur pour le provoquer) et évite d'écrire dans le
#: dossier à chaque code mal tapé à six heures du matin.
_ESSAIS: dict[str, tuple[int, datetime]] = {}


def blocage_restant(nom: str) -> int:
    """Minutes restantes avant de pouvoir réessayer. 0 si le compte est libre.

    Sans ce verrou, un code à quatre chiffres tombe en huit minutes d'essais
    automatiques — mesuré sur ce poste, pas supposé. Le jour où l'application
    écoute sur le Wi-Fi du service, c'est n'importe quel téléphone du couloir
    qui peut les enchaîner.
    """
    essais = _ESSAIS.get(_cle(nom))
    if not essais:
        return 0
    nombre, dernier = essais
    if nombre < config.ESSAIS_AVANT_BLOCAGE:
        return 0
    ecoule = (datetime.now() - dernier).total_seconds() / 60
    reste = config.BLOCAGE_MINUTES - ecoule
    if reste <= 0:
        _ESSAIS.pop(_cle(nom), None)
        return 0
    return max(1, int(reste + 0.999))


def noter_echec(nom: str) -> None:
    nombre, _dernier = _ESSAIS.get(_cle(nom), (0, datetime.now()))
    _ESSAIS[_cle(nom)] = (nombre + 1, datetime.now())


def oublier_echecs(nom: str) -> None:
    """Une entrée réussie efface l'ardoise."""
    _ESSAIS.pop(_cle(nom), None)


def _cle(nom: str) -> str:
    return (nom or "").strip().lower()


#: Coût du calcul d'empreinte. Assez haut pour qu'essayer les dix mille codes
#: à quatre chiffres coûte cher, assez bas pour que l'ouverture reste
#: instantanée sur le poste du service.
_ITERATIONS = 200_000


def _empreinte(code: str, sel: bytes) -> str:
    brut = hashlib.pbkdf2_hmac("sha256", code.encode("utf-8"), sel, _ITERATIONS)
    return f"pbkdf2${_ITERATIONS}${sel.hex()}${brut.hex()}"


def chiffrer_code(code: str) -> str:
    return _empreinte(code, os.urandom(16))


def code_correct(code: str, empreinte: str | None) -> bool:
    """Compare sans fuiter le temps de calcul.

    Un `==` ordinaire s'arrête au premier caractère différent : le temps de
    réponse dit alors combien de caractères sont bons. C'est théorique sur un
    poste de réanimation, mais `compare_digest` ne coûte rien.
    """
    if not empreinte:
        return False
    try:
        _algo, iterations, sel, _attendu = empreinte.split("$")
        candidat = hashlib.pbkdf2_hmac(
            "sha256", code.encode("utf-8"), bytes.fromhex(sel), int(iterations)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(f"pbkdf2${iterations}${sel}${candidat.hex()}", empreinte)


# --------------------------------------------------------------------------
# Lire
# --------------------------------------------------------------------------

def _sans_secours(lignes: list[dict]) -> list[dict]:
    """Retire le compte de secours de toute liste montrée ou comptée.

    Il ne doit apparaître nulle part — ni dans l'ouverture, ni dans l'écran
    des comptes, ni dans le décompte des administrateurs. C'est le seul filtre
    qui le tient caché : `actifs` et `tous` sont les deux seules portes par
    lesquelles les lignes d'utilisateurs sortent vers le reste du logiciel.
    `par_id`, lui, le rend — c'est ainsi que sa session fonctionne une fois
    entré, sans qu'il figure jamais dans une liste.
    """
    return [u for u in lignes if u["id"] != config.SECOURS_UTILISATEUR_ID]


def actifs(base: Base) -> list[dict]:
    return _sans_secours(base.requete(
        "SELECT * FROM utilisateur WHERE actif = 1 AND supprime = 0 ORDER BY nom"
    ))


def tous(base: Base) -> list[dict]:
    """Actifs et désactivés — l'écran des comptes montre les deux."""
    return _sans_secours(base.requete(
        "SELECT * FROM utilisateur WHERE supprime = 0 ORDER BY actif DESC, nom"
    ))


def par_id(base: Base, utilisateur_id: str | None) -> dict | None:
    if not utilisateur_id:
        return None
    return base.une_ligne(
        "SELECT * FROM utilisateur WHERE id = ? AND supprime = 0", (utilisateur_id,)
    )


def par_nom(base: Base, nom: str) -> dict | None:
    """Retrouve un utilisateur sur son nom, sans tenir compte de la casse."""
    cible = nom.strip().lower()
    return next(
        (u for u in actifs(base) if u["nom"].strip().lower() == cible), None
    )


def par_role(base: Base, role: str) -> list[dict]:
    return [u for u in actifs(base) if u["role"] == role]


def peut(base: Base, utilisateur_id: str | None, droit: str) -> bool:
    """Le droit d'un compte, relu en base à chaque fois.

    Pas de cache : un rôle retiré doit prendre effet au prochain écran, pas à
    la prochaine ouverture de l'application. Le coût est d'une requête.
    """
    utilisateur = par_id(base, utilisateur_id)
    return dom_droits.peut((utilisateur or {}).get("role"), droit)


def role_de(base: Base, utilisateur_id: str | None) -> str | None:
    return (par_id(base, utilisateur_id) or {}).get("role")


# --------------------------------------------------------------------------
# Écrire
# --------------------------------------------------------------------------

def creer(
    base: Base,
    nom: str,
    role: str,
    *,
    code: str | None = None,
    code_provisoire: bool = False,
    telephone: str | None = None,
    utilisateur_id: str | None = None,
) -> str:
    """Crée un compte.

    `code_provisoire` marque un code que l'administrateur a choisi pour
    quelqu'un d'autre et lui dit de vive voix. C'est le seul moyen de donner
    la main à un infirmier quand l'application est sur le réseau : un compte
    sans code y est refusé à l'entrée, il ne pourrait donc jamais entrer pour
    poser le sien. Le compte réclame un vrai code à sa première ouverture, et
    ce code-là n'est plus connu que de son propriétaire.
    """
    nom = (nom or "").strip()
    if not nom:
        raise ValueError("Le nom du compte est obligatoire.")
    if role not in dom_droits.roles():
        raise ValueError(f"Rôle inconnu : {role}")
    if par_nom(base, nom):
        raise ValueError(f"Un compte « {nom} » existe déjà.")
    return base.inserer(
        "utilisateur",
        {"nom": nom, "role": role,
         "pin": chiffrer_code(code) if code else None,
         "code_provisoire": 1 if (code and code_provisoire) else 0,
         "telephone": (telephone or "").strip() or None},
        utilisateur_id=utilisateur_id,
    )


def modifier_role(
    base: Base, cible_id: str, role: str, *, utilisateur_id: str | None = None
) -> None:
    if role not in dom_droits.roles():
        raise ValueError(f"Rôle inconnu : {role}")
    _refuser_dernier_administrateur(base, cible_id, nouveau_role=role)
    base.mettre_a_jour("utilisateur", cible_id, {"role": role},
                       utilisateur_id=utilisateur_id)


def definir_code(
    base: Base, cible_id: str, code: str | None, *,
    provisoire: bool = False, utilisateur_id: str | None = None,
) -> None:
    """Pose ou retire le code d'accès d'un compte.

    `provisoire` distingue les deux gestes qui se ressemblent : un code que
    l'on choisit pour soi n'est connu que de soi ; un code qu'un
    administrateur pose pour quelqu'un d'autre — un code oublié qu'on
    réinitialise, un compte qu'on ouvre — est connu de deux personnes, et
    le compte le sait : il en réclamera un vrai à la prochaine entrée.
    """
    base.mettre_a_jour(
        "utilisateur", cible_id,
        {"pin": chiffrer_code(code) if code else None,
         "code_provisoire": 1 if (code and provisoire) else 0},
        utilisateur_id=utilisateur_id,
    )


def definir_telephone(
    base: Base, cible_id: str, telephone: str | None, *,
    utilisateur_id: str | None = None,
) -> None:
    base.mettre_a_jour(
        "utilisateur", cible_id,
        {"telephone": (telephone or "").strip() or None},
        utilisateur_id=utilisateur_id,
    )


def desactiver(base: Base, cible_id: str, *, utilisateur_id: str | None = None) -> None:
    """Un compte qui part du service : il ne peut plus entrer, mais tout ce
    qu'il a écrit garde son nom.

    C'est pour cela qu'on désactive au lieu de supprimer — effacer le compte
    rendrait anonymes des années de prescriptions, et le journal d'audit
    n'aurait plus de sens (règle de conception 2).
    """
    _refuser_dernier_administrateur(base, cible_id)
    base.mettre_a_jour("utilisateur", cible_id, {"actif": 0},
                       utilisateur_id=utilisateur_id)


def reactiver(base: Base, cible_id: str, *, utilisateur_id: str | None = None) -> None:
    base.mettre_a_jour("utilisateur", cible_id, {"actif": 1},
                       utilisateur_id=utilisateur_id)


def _refuser_dernier_administrateur(
    base: Base, cible_id: str, nouveau_role: str | None = None
) -> None:
    """On ne se ferme pas la porte de l'extérieur.

    Retirer le dernier compte capable de gérer les comptes laisse un service
    sans aucun moyen d'en créer un autre — il faudrait ouvrir la base à la
    main. C'est le seul geste que ce module refuse.
    """
    cible = par_id(base, cible_id)
    if not cible or not dom_droits.peut(cible["role"], "comptes"):
        return
    if nouveau_role and dom_droits.peut(nouveau_role, "comptes"):
        return
    autres = [
        u for u in actifs(base)
        if u["id"] != cible_id and dom_droits.peut(u["role"], "comptes")
    ]
    if not autres:
        raise ValueError(
            "C'est le dernier compte capable de gérer les comptes : en créer "
            "un autre d'abord, sinon plus personne ne pourra en créer."
        )


def administrateurs(base: Base) -> list[dict]:
    """Les comptes actifs capables de gérer les comptes."""
    return [u for u in actifs(base) if dom_droits.peut(u["role"], "comptes")]


def sans_administrateur(base: Base) -> bool:
    """Une base qui a des comptes, mais aucun pour les administrer.

    C'est l'état d'un service qui tournait avant que les rôles n'existent :
    des médecins et des infirmiers, personne d'administrateur, donc aucun
    moyen d'en désigner un — le bouton qui le permettrait est justement
    réservé à l'administrateur qui n'existe pas.
    """
    return bool(actifs(base)) and not administrateurs(base)


def rien_n_est_protege(base: Base) -> bool:
    """Aucun compte actif n'a de code : la base est ouverte à qui l'ouvre.

    C'est la seule situation où créer un administrateur au code public ne
    retire rien à personne — il n'y avait pas de serrure à forcer.
    """
    comptes = actifs(base)
    return not any(u["pin"] for u in comptes)


def comptes_a_code_provisoire(base: Base) -> list[dict]:
    """Les comptes qui portent encore le code écrit dans `config.py`."""
    return [u for u in actifs(base) if u["code_provisoire"]]


def creer_compte_initial(base: Base) -> str:
    """Le compte administrateur du premier démarrage (`config.CODE_INITIAL`).

    Il ouvre la porte d'un service qui installe le logiciel un matin : sans
    administrateur, personne ne peut créer de compte. Son code est écrit dans
    le code source, donc public : il est marqué provisoire, et l'application
    n'ouvre aucun écran tant qu'un vrai code n'a pas été posé.

    Deux refus, pour que cette commodité ne devienne pas une porte dérobée :
    une base qui a déjà un administrateur n'en a pas besoin, et une base dont
    un seul compte porte un code est **protégée** — y ajouter un compte au
    code public rendrait cette protection illusoire, et quiconque lit le
    dépôt entrerait administrateur. Là, la porte reste `designer_administrateur`,
    qui exige un code déjà connu.
    """
    if administrateurs(base):
        raise ValueError(
            "Cette base a déjà un administrateur : c'est à lui de créer les "
            "comptes, dans Administration → Comptes."
        )
    if not rien_n_est_protege(base):
        raise ValueError(
            "Des comptes de cette base ont un code d'accès : ajouter un "
            "administrateur au code public les laisserait sans protection. "
            "Désigner plutôt un compte existant, avec son code."
        )
    with base.transaction():
        cible = par_nom(base, config.COMPTE_INITIAL_NOM)
        if cible:
            identifiant = cible["id"]
            base.mettre_a_jour(
                "utilisateur", identifiant,
                {"role": "admin", "actif": 1,
                 "pin": chiffrer_code(config.CODE_INITIAL),
                 "code_provisoire": 1},
                utilisateur_id=identifiant,
            )
        else:
            identifiant = base.inserer(
                "utilisateur",
                {"nom": config.COMPTE_INITIAL_NOM, "role": "admin",
                 "pin": chiffrer_code(config.CODE_INITIAL),
                 "code_provisoire": 1},
            )
    return identifiant


# --------------------------------------------------------------------------
# Codes oubliés (demande du service, 11 septembre 2026)
# --------------------------------------------------------------------------
# Une personne qui a perdu son code ne peut pas le remettre elle-même : ce
# serait une porte ouverte à qui saurait un nom. Elle dépose une demande, et
# l'administrateur y répond.

EN_ATTENTE = "en_attente"
TRAITEE = "traitee"
REFUSEE = "refusee"


def demander_un_code(base: Base, cible_id: str) -> str:
    """Dépose une demande de code oublié, ou rend celle qui attend déjà.

    Rend l'existante plutôt que d'en empiler : appuyer trois fois sur le
    bouton ne doit pas donner trois lignes à traiter à l'administrateur.
    """
    cible = par_id(base, cible_id)
    if not cible or not cible["actif"]:
        raise ValueError("Compte introuvable.")
    with base.transaction():
        deja = base.une_ligne(
            "SELECT * FROM demande_code WHERE utilisateur_id = ? AND etat = ? "
            "AND supprime = 0",
            (cible_id, EN_ATTENTE),
        )
        if deja:
            return deja["id"]
        return base.inserer(
            "demande_code",
            {"utilisateur_id": cible_id,
             "demande_le": datetime.now().isoformat(timespec="minutes"),
             "etat": EN_ATTENTE},
            utilisateur_id=cible_id,
        )


def demandes_de_code(base: Base) -> list[dict]:
    """Les demandes qui attendent une réponse, la plus ancienne d'abord."""
    lignes = base.requete(
        "SELECT * FROM demande_code WHERE etat = ? AND supprime = 0 "
        "ORDER BY demande_le",
        (EN_ATTENTE,),
    )
    demandes = []
    for ligne in lignes:
        compte = par_id(base, ligne["utilisateur_id"])
        if compte and compte["actif"]:
            demandes.append({**ligne, "nom": compte["nom"], "role": compte["role"]})
    return demandes


def reinitialiser_le_code(
    base: Base, demande_id: str, *, utilisateur_id: str | None = None
) -> str:
    """Remet le code du compte à celui de départ, et lève son blocage.

    Trois choses ensemble, et c'est le tout qui rend le compte utilisable :

    * le code redevient `config.CODE_INITIAL`, marqué **provisoire** — il est
      écrit dans le logiciel, donc public : la personne en choisira un vrai
      dès son entrée, et rien ne s'ouvrira avant ;
    * le compteur d'essais ratés est remis à zéro. Sans cela, quelqu'un qui
      s'est bloqué en cherchant son code recevrait un nouveau code et se
      verrait quand même refuser l'entrée pendant dix minutes — le temps de
      rappeler l'administrateur pour lui dire que ça ne marche pas ;
    * la demande est marquée traitée, pour qu'elle cesse de figurer dans la
      liste de l'administrateur.
    """
    demande = base.une_ligne(
        "SELECT * FROM demande_code WHERE id = ? AND supprime = 0", (demande_id,)
    )
    if not demande or demande["etat"] != EN_ATTENTE:
        raise ValueError("Cette demande a déjà été traitée.")
    cible = par_id(base, demande["utilisateur_id"])
    if not cible or not cible["actif"]:
        raise ValueError("Compte introuvable.")

    with base.transaction():
        definir_code(base, cible["id"], config.CODE_INITIAL, provisoire=True,
                     utilisateur_id=utilisateur_id)
        base.mettre_a_jour(
            "demande_code", demande_id,
            {"etat": TRAITEE,
             "traitee_le": datetime.now().isoformat(timespec="minutes"),
             "traitee_par": utilisateur_id},
            utilisateur_id=utilisateur_id,
        )
    oublier_echecs(cible["nom"])
    return cible["nom"]


def refuser_la_demande(
    base: Base, demande_id: str, *, utilisateur_id: str | None = None
) -> None:
    """L'administrateur a vu et a dit non. La demande reste, marquée refusée :
    trois demandes refusées sur le même compte en une semaine ne se lisent pas
    comme un code oublié trois fois."""
    base.mettre_a_jour(
        "demande_code", demande_id,
        {"etat": REFUSEE,
         "traitee_le": datetime.now().isoformat(timespec="minutes"),
         "traitee_par": utilisateur_id},
        utilisateur_id=utilisateur_id,
    )


def designer_administrateur(
    base: Base, cible_id: str, *, code: str, nouveau_code: str | None = None
) -> None:
    """Sortie de secours : donner le rôle d'administrateur à un compte
    existant, quand la base n'en a aucun.

    Deux verrous, parce qu'un écran d'ouverture est vu par tout le service :

    * la porte ne s'ouvre que si **aucun** administrateur actif n'existe.
      Dès qu'il y en a un, c'est à lui de distribuer les rôles, dans
      Administration → Comptes ;
    * il faut le code du compte que l'on promeut. On ne promeut donc que le
      compte dans lequel on sait déjà entrer, et promouvoir ne donne rien de
      plus que ce qu'on avait. Un compte sans code doit en recevoir un ici :
      donner les pleins pouvoirs à un nom que n'importe qui peut choisir dans
      une liste reviendrait à ne rien protéger du tout.
    """
    if not sans_administrateur(base):
        raise ValueError(
            "Cette base a déjà un administrateur : c'est à lui de changer "
            "les rôles, dans Administration → Comptes."
        )
    cible = par_id(base, cible_id)
    if not cible or not cible["actif"]:
        raise ValueError("Compte introuvable.")
    if cible["pin"]:
        if not code_correct(code, cible["pin"]):
            raise ValueError("Code d'accès incorrect.")
        a_poser = nouveau_code or None
    else:
        refus = code_acceptable(nouveau_code or "")
        if refus:
            raise ValueError(
                f"Ce compte n'a pas de code : en poser un pour le promouvoir. {refus}"
            )
        a_poser = nouveau_code
    with base.transaction():
        base.mettre_a_jour("utilisateur", cible_id, {"role": "admin"},
                           utilisateur_id=cible_id)
        if a_poser:
            definir_code(base, cible_id, a_poser, utilisateur_id=cible_id)


def comptes_sans_code(base: Base) -> list[dict]:
    """Les comptes actifs qu'aucun code ne protège.

    Sur un poste isolé, c'est un choix de confort. Dès que l'application
    écoute sur le réseau, c'est une porte ouverte : l'écran d'ouverture les
    refuse et l'administrateur est renvoyé vers l'écran des comptes.
    """
    return [u for u in actifs(base) if not u["pin"]]


def est_compte_de_secours(nom: str, code: str) -> bool:
    """Le nom et le code frappés ouvrent-ils le compte de secours ?

    On ne compare pas à une empreinte stockée en base — délibérément : le code
    de secours vit dans un secret local au poste (`config.SECOURS_CODE`), pas
    dans la base, pour qu'il n'y ait rien à voler dans une sauvegarde et rien
    à changer par un écran. `compare_digest` des deux côtés, pour ne pas
    laisser le temps de réponse trahir ce qui est bon.
    """
    if not config.SECOURS_ACTIF:
        return False
    nom_ok = hmac.compare_digest(_cle(nom), _cle(config.SECOURS_ID))
    code_ok = hmac.compare_digest((code or "").strip(), config.SECOURS_CODE)
    return nom_ok and code_ok


def compte_de_secours(base: Base) -> dict:
    """Matérialise, une fois, la ligne du compte de secours, et la rend.

    Une vraie ligne en base, et non une session fantôme : tout ce qui s'écrit
    porte un `cree_par` qui référence un utilisateur par clé étrangère (les
    clés étrangères sont actives). Sans ligne, la première écriture du compte
    de secours serait refusée par la base. Elle reste hors de toutes les
    listes — `actifs` et `tous` l'excluent — donc invisible partout.

    Son `pin` reste vide : il ne sert jamais à l'entrée, qui passe par
    `est_compte_de_secours` et le secret local, jamais par la base.
    """
    with base.transaction():
        existant = base.une_ligne(
            "SELECT * FROM utilisateur WHERE id = ?", (config.SECOURS_UTILISATEUR_ID,)
        )
        if not existant:
            base.inserer(
                "utilisateur",
                {"id": config.SECOURS_UTILISATEUR_ID, "nom": config.SECOURS_ID,
                 "role": "admin", "pin": None, "code_provisoire": 0},
            )
            existant = base.une_ligne(
                "SELECT * FROM utilisateur WHERE id = ?",
                (config.SECOURS_UTILISATEUR_ID,),
            )
    return existant


def code_acceptable(code: str) -> str | None:
    """Le motif de refus d'un code, ou None s'il convient.

    Six chiffres et non quatre : à 47 ms l'essai, quatre chiffres tombent en
    huit minutes, six en treize heures. Le verrou après cinq essais ratés est
    la vraie protection, mais les deux se complètent — le verrou se contourne
    en changeant de compte, la longueur non.
    """
    code = (code or "").strip()
    if not code:
        return "Le code est obligatoire."
    if len(code) < config.LONGUEUR_CODE_MINIMALE:
        return (
            f"Le code doit faire au moins {config.LONGUEUR_CODE_MINIMALE} "
            "caractères."
        )
    if code in ("000000", "123456", "111111", "654321"):
        return "Ce code est trop courant — en choisir un autre."
    return None
