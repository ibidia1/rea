"""La surveillance clinique heure par heure — le verso de la feuille
(SPEC §5.8).

C'est ce que l'infirmière écrit toutes les heures sur le papier : FC, pression,
température, SpO₂, Glasgow, diurèse. Jusqu'ici le logiciel n'en gardait qu'une
valeur par jour, dans l'évolution — la courbe des vingt-quatre heures restait
sur une feuille qu'on jette à la sortie du patient.

Deux tables voisines, et il faut savoir laquelle sert à quoi :
`evolution_element` porte **la valeur du jour** retenue par le médecin dans
son observation ; celle-ci porte **le relevé de l'heure**. La première se
raconte, la seconde se trace.

Le jour est celui du service (8 h → 8 h), comme la feuille imprimée : un
relevé de 2 h du matin appartient à la feuille ouverte la veille.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from ..db import Base
from ..domaine import recueil
from ..domaine import vacations as dom_vacations

#: Ce qui se relève toutes les heures, dans l'ordre du verso de la feuille.
#:
#: L'ordre n'est pas décoratif : l'écran affiche ces champs **deux par
#: rangée**, et les deux pressions doivent tomber côte à côte. Saisir une
#: systolique en haut d'une rangée et la diastolique en bas de la suivante,
#: c'est une inversion par garde.
VITALES = (
    ("temperature", "T°", "°C"),
    ("fc", "FC", "/min"),
    ("pas", "PA syst.", "mmHg"),
    ("pad", "PA diast.", "mmHg"),
    ("fr", "FR", "/min"),
    ("spo2", "SpO₂", "%"),
    ("glasgow", "Glasgow", "/15"),
    ("dextro", "Dextro", "g/L"),
)

#: Ce qui se recueille dans un sac, relevé heure par heure comme le reste —
#: mais ce n'est **pas la même chose qu'on écrit**.
#:
#: Dans ces cases, l'infirmier note le **niveau lu sur le sac** : 120, puis
#: 210, puis 300. Pas ce qui est sorti pendant l'heure. C'est ce qu'il voit,
#: et lui demander la soustraction au lit du malade, de nuit, avec des gants,
#: serait lui demander de se tromper (pratique du service, 10 septembre).
#:
#: Le logiciel fait la soustraction, dans `domaine/recueil.py`. Additionner
#: ces cases recompterait la même urine à chaque heure : douze relevés d'un
#: patient qui fait 100 mL/h annonceraient 7 800 mL pour 1 200 produits.
SORTIES = (
    ("diurese", "Diurèse", "mL"),
)

#: Tout ce qui se relève, dans l'ordre du papier. Les sorties ferment la
#: liste, comme au verso de la feuille.
CLES = VITALES + SORTIES

#: Les clés dont la case porte un **niveau** et non une quantité. Elles ne
#: s'additionnent jamais telles quelles : elles passent par `recueil`.
CLES_NIVEAU = tuple(cle for cle, _l, _u in SORTIES)

#: Préfixe des clés de recueil d'un drain : `drain:<id du dispositif>`.
#:
#: Un drain n'a pas de clé fixe comme la diurèse : il n'existe que si on l'a
#: posé, et un patient peut en porter quatre. Sa clé porte donc l'identifiant
#: du dispositif — la colonne `cle` étant du texte libre, un redon de plus se
#: relève comme les autres sans rien changer au schéma (demande du service,
#: 10 septembre).
PREFIXE_DRAIN = "drain:"


#: Préfixe des clés d'état d'un drain thoracique : `etat_drain:<id>`.
#:
#: Séparé du volume, parce que ce n'est pas la même nature de chose. Le
#: volume se totalise sur la journée ; l'état, lui, se lit heure par heure et
#: ne se totalise jamais — la moyenne de « clampé » et de « siphonnage »
#: n'existe pas (demande du service, 11 septembre).
PREFIXE_ETAT_DRAIN = "etat_drain:"

#: Ce qui s'ajoute au mode quand il est constaté : le bullage. Il n'est pas
#: dans la liste des modes et c'est voulu — un drain peut buller en
#: siphonnage comme en aspiration, et une liste unique obligerait à choisir
#: entre les deux.
MARQUE_BULLAGE = "bullage"


def cle_drain(dispositif_id: str) -> str:
    return f"{PREFIXE_DRAIN}{dispositif_id}"


def cle_etat_drain(dispositif_id: str) -> str:
    return f"{PREFIXE_ETAT_DRAIN}{dispositif_id}"


def etat_drain(mode: str | None, bullage: bool) -> str | None:
    """Le mode et le bullage réunis en une ligne, telle qu'elle se relit.

    « aspiration+bullage » plutôt que deux colonnes : le tableau du médecin
    a déjà vingt-quatre heures de large, et ces deux-là se lisent toujours
    ensemble.
    """
    if not mode:
        return MARQUE_BULLAGE if bullage else None
    return f"{mode}+{MARQUE_BULLAGE}" if bullage else mode


def lire_etat_drain(texte: str | None) -> tuple[str | None, bool]:
    """L'inverse : de « aspiration+bullage » au mode et au bullage."""
    if not texte:
        return None, False
    morceaux = texte.split("+")
    bullage = MARQUE_BULLAGE in morceaux
    mode = next((m for m in morceaux if m != MARQUE_BULLAGE), None)
    return mode, bullage


def etats_du_jour(base: Base, sejour_id: str, date_jour: str) -> dict[int, dict[str, str]]:
    """heure -> {clé d'état: texte relevé}, pour toute la journée."""
    grille: dict[int, dict[str, str]] = {}
    for ligne in base.requete(
        "SELECT heure, cle, valeur_texte FROM constante_horaire "
        "WHERE sejour_id = ? AND date_jour = ? AND supprime = 0 "
        "AND valeur_texte IS NOT NULL ORDER BY heure",
        (sejour_id, date_jour),
    ):
        grille.setdefault(ligne["heure"], {})[ligne["cle"]] = ligne["valeur_texte"]
    return grille


def est_recueil(cle: str) -> bool:
    """Cette case porte-t-elle un **niveau lu** plutôt qu'une quantité ?

    Diurèse et drains : ce que l'infirmier voit, c'est le contenu du sac ou
    du bocal, pas ce qui est sorti pendant l'heure. Le logiciel fait la
    soustraction ; la lui demander au lit du malade, de nuit, avec des gants,
    serait lui demander de se tromper.
    """
    return cle in CLES_NIVEAU or cle.startswith(PREFIXE_DRAIN)


def libelle(cle: str) -> str:
    return next((l for c, l, _u in CLES if c == cle), cle)


def unite(cle: str) -> str:
    return next((u for c, _l, u in CLES if c == cle), "")


def enregistrer(
    base: Base,
    sejour_id: str,
    date_jour: str,
    heure: int,
    valeurs: dict[str, float | None],
    *,
    textes: dict[str, str | None] | None = None,
    sacs_jetes: set[str] | None = None,
    utilisateur_id: str | None = None,
) -> None:
    """Écrit les mesures d'une heure. Une valeur à None efface la mesure.

    Effacer plutôt que d'écrire zéro : une FC à 0 est un arrêt cardiaque, pas
    une case qu'on a vidée.

    `textes` porte ce qui se relève sans se chiffrer — l'état d'un drain
    thoracique : clampé, en siphonnage, en aspiration. Une case à part de
    `valeurs` parce qu'un état ne se moyenne pas, ne s'additionne pas, et
    n'a pas d'extrêmes : le confondre avec un nombre ferait calculer la
    moyenne de « clampé » et de « siphonnage ».

    `sacs_jetes` nomme les recueils vidés **juste après** ce relevé : le
    niveau qu'on vient d'écrire est le dernier de ce sac-là, et le suivant
    repartira de zéro. Sans ce drapeau, un sac changé se lirait comme une
    diurèse qui s'effondre.
    """
    jetes = sacs_jetes or set()
    # Lire puis écrire n'est atomique que dans une transaction. Sans elle, deux
    # fils — deux téléphones, ou un seul doigt qui appuie deux fois sur un
    # réseau lent — lisent tous les deux « rien de noté » et insèrent tous les
    # deux : le second heurte l'index unique et l'écriture est perdue. Mesuré
    # sur seize écrivains simultanés (10 septembre) : onze échecs sur trente-six
    # mille écritures, tous de cette forme.
    with base.transaction():
        _ecrire_les_mesures(base, sejour_id, date_jour, heure, valeurs, jetes,
                            utilisateur_id, textes or {})


def _ecrire_les_mesures(base, sejour_id, date_jour, heure, valeurs, jetes,
                        utilisateur_id, textes=None) -> None:
    existantes = {
        ligne["cle"]: ligne
        for ligne in base.requete(
            "SELECT * FROM constante_horaire WHERE sejour_id = ? AND date_jour = ? "
            "AND heure = ? AND supprime = 0",
            (sejour_id, date_jour, heure),
        )
    }
    a_ecrire = [(cle, valeur, None) for cle, valeur in valeurs.items()]
    a_ecrire += [(cle, None, texte) for cle, texte in (textes or {}).items()]

    for cle, valeur, texte in a_ecrire:
        ancienne = existantes.get(cle)
        if valeur is None and not texte:
            if ancienne:
                base.supprimer_logiquement("constante_horaire", ancienne["id"],
                                           utilisateur_id=utilisateur_id)
            continue
        champs = {
            "valeur_num": float(valeur) if valeur is not None else None,
            "valeur_texte": texte,
            "sac_jete": 1 if cle in jetes else 0,
        }
        if ancienne:
            base.mettre_a_jour("constante_horaire", ancienne["id"], champs,
                               utilisateur_id=utilisateur_id)
        else:
            base.inserer(
                "constante_horaire",
                {"sejour_id": sejour_id, "date_jour": date_jour, "heure": heure,
                 "cle": cle, **champs},
                utilisateur_id=utilisateur_id,
            )


def du_jour(base: Base, sejour_id: str, date_jour: str) -> dict[int, dict[str, float]]:
    """heure -> {clé: valeur} pour toute la journée de service.

    Pour les recueils, la valeur est le **niveau lu**, pas ce qui est sorti :
    c'est la case telle qu'elle a été remplie. Les volumes se demandent à
    `sorties_du_jour`.
    """
    grille: dict[int, dict[str, float]] = {}
    for ligne in base.requete(
        "SELECT heure, cle, valeur_num FROM constante_horaire "
        "WHERE sejour_id = ? AND date_jour = ? AND supprime = 0 "
        "ORDER BY heure",
        (sejour_id, date_jour),
    ):
        grille.setdefault(ligne["heure"], {})[ligne["cle"]] = ligne["valeur_num"]
    return grille


def sacs_jetes_du_jour(base: Base, sejour_id: str, date_jour: str) -> set[tuple[int, str]]:
    """Les (heure, clé) après lesquels le sac a été jeté — pour le marquer à
    l'écran. Un niveau qui retombe à 40 après 900 doit s'expliquer de
    lui-même, sinon c'est le relevé qu'on soupçonne."""
    return {
        (l["heure"], l["cle"])
        for l in base.requete(
            "SELECT heure, cle FROM constante_horaire WHERE sejour_id = ? "
            "AND date_jour = ? AND supprime = 0 AND sac_jete = 1",
            (sejour_id, date_jour),
        )
    }


def serie(base: Base, sejour_id: str, date_jour: str, cle: str) -> list[tuple[int, float]]:
    """La courbe d'une constante sur la journée, pour la tracer."""
    return [
        (ligne["heure"], ligne["valeur_num"])
        for ligne in base.requete(
            "SELECT heure, valeur_num FROM constante_horaire WHERE sejour_id = ? "
            "AND date_jour = ? AND cle = ? AND supprime = 0 AND valeur_num IS NOT NULL "
            "ORDER BY heure",
            (sejour_id, date_jour, cle),
        )
    ]


def _releves(base: Base, sejour_id: str, cle: str) -> list[recueil.Releve]:
    """Tous les niveaux lus pour ce recueil, depuis l'admission.

    Toute la série et pas seulement la journée demandée : le premier relevé
    d'un jour se compare à **celui de la veille au soir**. Coupé à minuit ou
    à 7 h, le calcul perdrait la première heure de chaque journée, soit une
    heure sur vingt-quatre, tous les jours.
    """
    return [
        recueil.Releve(
            instant=dom_vacations.instant_du_releve(l["date_jour"], l["heure"]),
            niveau_ml=float(l["valeur_num"]),
            sac_jete=bool(l["sac_jete"]),
        )
        for l in base.requete(
            "SELECT date_jour, heure, valeur_num, sac_jete FROM constante_horaire "
            "WHERE sejour_id = ? AND cle = ? AND supprime = 0 "
            "AND valeur_num IS NOT NULL",
            (sejour_id, cle),
        )
    ]


def sorties_du_jour(
    base: Base, sejour_id: str, date_jour: str, cle: str
) -> dict[int, recueil.Sortie]:
    """heure -> ce qui est sorti pendant cette heure-là, calculé.

    C'est la ligne que le médecin lit et que l'infirmier vérifie : pas les
    niveaux qu'on a écrits, mais les volumes qu'ils impliquent.
    """
    _verifier_niveau(cle)
    debut, fin = _fenetre(date_jour)
    return {
        s.instant.hour: s
        for s in recueil.sorties(_releves(base, sejour_id, cle))
        if debut <= s.instant < fin
    }


def total_du_jour(
    base: Base, sejour_id: str, date_jour: str, cle: str
) -> recueil.Total:
    """Ce qui est sorti sur les 24 h de la journée d'infirmerie.

    Pas la somme des cases : la somme des **différences** entre niveaux
    successifs, sac jeté compris (`domaine/recueil.py`). Additionner les cases
    recompterait la même urine à chaque heure.

    Le total sait aussi ce qui lui manque — heures sans relevé de référence,
    niveaux en baisse sans sac déclaré jeté. Un total amputé qui se présente
    comme complet est pire qu'un total absent : le médecin le recopie.
    """
    _verifier_niveau(cle)
    debut, fin = _fenetre(date_jour)
    return recueil.total(recueil.sorties(_releves(base, sejour_id, cle)), debut, fin)


def _verifier_niveau(cle: str) -> None:
    """La somme des températures d'une journée n'est pas une température."""
    if not est_recueil(cle):
        raise ValueError(f"{cle} n'est pas un recueil : rien à cumuler")


def drains_du_jour(
    base: Base, sejour_id: str, date_jour: str, dispositifs_ids: list[str]
) -> dict[str, recueil.Total]:
    """Ce que chaque drain a donné sur les 24 h — id du drain -> total.

    Un drain par ligne et non un total unique : deux redons qui donnent 90 et
    410 ne se lisent pas comme deux qui donnent 250 chacun, et c'est le genre
    de chiffre qui fait rappeler le chirurgien.
    """
    return {
        identifiant: total_du_jour(base, sejour_id, date_jour, cle_drain(identifiant))
        for identifiant in dispositifs_ids
    }


def _fenetre(date_jour: str) -> tuple[datetime, datetime]:
    """Les bornes de la journée d'infirmerie, en horodatages.

    De 7 h ce jour-là à 7 h le lendemain — pas de minuit à minuit : une
    équipe de nuit a pris son poste la veille, et son relevé de 3 h appartient
    à sa journée.
    """
    heures = dom_vacations.heures_du_jour()
    debut = dom_vacations.instant_du_releve(date_jour, heures[0])
    return debut, debut + timedelta(hours=len(heures))
