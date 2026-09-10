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

from ..db import Base

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

#: Ce qui **sort** du malade, relevé heure par heure comme le reste.
#:
#: Séparé des constantes vitales pour deux raisons, et la seconde compte plus
#: que la première. À l'écran, ces cases se remplissent d'un autre geste : on
#: vide un bocal, on ne lit pas un moniteur. Et surtout ces valeurs-là
#: **s'additionnent sur la journée** — une FC ne se somme pas, une diurèse
#: si. C'est cette somme qui devient le total des pertes du bilan hydrique ;
#: sommer par erreur une température donnerait 900 °C.
#:
#: Les « jetés » sont ce qu'on recueille et qu'on jette au lieu de le
#: réinjecter — le liquide gastrique aspiré, avant tout (demande du service,
#: 10 septembre). Sans cette ligne, un patient qui perd 800 mL par la sonde
#: gastrique apparaît en bilan positif alors qu'il se déshydrate.
SORTIES = (
    ("diurese", "Diurèse", "mL"),
    ("jetes", "Jetés", "mL"),
)

#: Tout ce qui se relève, dans l'ordre du papier. Les sorties ferment la
#: liste, comme au verso de la feuille.
CLES = VITALES + SORTIES

#: Les clés dont la somme de la journée a un sens (voir `SORTIES`).
CLES_SOMMABLES = tuple(cle for cle, _l, _u in SORTIES)


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
    utilisateur_id: str | None = None,
) -> None:
    """Écrit les mesures d'une heure. Une valeur à None efface la mesure.

    Effacer plutôt que d'écrire zéro : une FC à 0 est un arrêt cardiaque, pas
    une case qu'on a vidée.
    """
    existantes = {
        ligne["cle"]: ligne
        for ligne in base.requete(
            "SELECT * FROM constante_horaire WHERE sejour_id = ? AND date_jour = ? "
            "AND heure = ? AND supprime = 0",
            (sejour_id, date_jour, heure),
        )
    }
    for cle, valeur in valeurs.items():
        ancienne = existantes.get(cle)
        if valeur is None:
            if ancienne:
                base.supprimer_logiquement("constante_horaire", ancienne["id"],
                                           utilisateur_id=utilisateur_id)
            continue
        if ancienne:
            base.mettre_a_jour("constante_horaire", ancienne["id"],
                               {"valeur_num": float(valeur)},
                               utilisateur_id=utilisateur_id)
        else:
            base.inserer(
                "constante_horaire",
                {"sejour_id": sejour_id, "date_jour": date_jour, "heure": heure,
                 "cle": cle, "valeur_num": float(valeur)},
                utilisateur_id=utilisateur_id,
            )


def du_jour(base: Base, sejour_id: str, date_jour: str) -> dict[int, dict[str, float]]:
    """heure -> {clé: valeur} pour toute la journée de service."""
    grille: dict[int, dict[str, float]] = {}
    for ligne in base.requete(
        "SELECT heure, cle, valeur_num FROM constante_horaire "
        "WHERE sejour_id = ? AND date_jour = ? AND supprime = 0 "
        "ORDER BY heure",
        (sejour_id, date_jour),
    ):
        grille.setdefault(ligne["heure"], {})[ligne["cle"]] = ligne["valeur_num"]
    return grille


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


def total_du_jour(base: Base, sejour_id: str, date_jour: str, cle: str) -> float | None:
    """La somme d'une sortie sur la journée de service, ou None si rien n'a
    été relevé.

    None et 0 ne disent pas la même chose et l'écart se paie dans le bilan
    hydrique : « rien de relevé » n'est pas « rien de perdu ». Ce total est
    proposé au médecin dans l'évolution, jamais écrit à sa place — c'est lui
    qui arrête le chiffre des 24 h, et une journée peut avoir été relevée à
    trous.

    Refuse une clé qui ne s'additionne pas : la somme des températures de la
    journée n'est pas une température.
    """
    if cle not in CLES_SOMMABLES:
        raise ValueError(f"{cle} ne s'additionne pas sur la journée")
    ligne = base.une_ligne(
        "SELECT COUNT(*) AS n, SUM(valeur_num) AS total FROM constante_horaire "
        "WHERE sejour_id = ? AND date_jour = ? AND cle = ? AND supprime = 0 "
        "AND valeur_num IS NOT NULL",
        (sejour_id, date_jour, cle),
    )
    if not ligne or not ligne["n"]:
        return None
    return float(ligne["total"])


def heures_relevees(base: Base, sejour_id: str, date_jour: str, cle: str) -> int:
    """Combien d'heures portent une valeur — ce qui dit si le total vaut
    quelque chose. Un « total » sur trois heures n'est pas un total /24 h."""
    ligne = base.une_ligne(
        "SELECT COUNT(*) AS n FROM constante_horaire WHERE sejour_id = ? "
        "AND date_jour = ? AND cle = ? AND supprime = 0 AND valeur_num IS NOT NULL",
        (sejour_id, date_jour, cle),
    )
    return int((ligne or {}).get("n") or 0)
