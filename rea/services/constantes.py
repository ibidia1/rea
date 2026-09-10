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
#: Les libellés viennent du même référentiel que la feuille imprimée : deux
#: listes à tenir à jour finiraient par diverger.
CLES = (
    ("fc", "FC", "/min"),
    ("pas", "PA syst.", "mmHg"),
    ("pad", "PA diast.", "mmHg"),
    ("temperature", "T°", "°C"),
    ("fr", "FR", "/min"),
    ("spo2", "SpO₂", "%"),
    ("glasgow", "Glasgow", "/15"),
    ("diurese", "Diurèse", "mL"),
    ("dextro", "Dextro", "g/L"),
)


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
