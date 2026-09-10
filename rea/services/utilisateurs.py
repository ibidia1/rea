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

def actifs(base: Base) -> list[dict]:
    return base.requete(
        "SELECT * FROM utilisateur WHERE actif = 1 AND supprime = 0 ORDER BY nom"
    )


def tous(base: Base) -> list[dict]:
    """Actifs et désactivés — l'écran des comptes montre les deux."""
    return base.requete(
        "SELECT * FROM utilisateur WHERE supprime = 0 ORDER BY actif DESC, nom"
    )


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
    telephone: str | None = None,
    utilisateur_id: str | None = None,
) -> str:
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
    base: Base, cible_id: str, code: str | None, *, utilisateur_id: str | None = None
) -> None:
    """Pose ou retire le code d'accès d'un compte."""
    base.mettre_a_jour(
        "utilisateur", cible_id,
        {"pin": chiffrer_code(code) if code else None},
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


def comptes_sans_code(base: Base) -> list[dict]:
    """Les comptes actifs qu'aucun code ne protège.

    Sur un poste isolé, c'est un choix de confort. Dès que l'application
    écoute sur le réseau, c'est une porte ouverte : l'écran d'ouverture les
    refuse et l'administrateur est renvoyé vers l'écran des comptes.
    """
    return [u for u in actifs(base) if not u["pin"]]


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
