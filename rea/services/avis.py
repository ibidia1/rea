"""Les avis demandés aux autres spécialités (SPEC §7).

Un avis de neurochirurgie ne se résume pas : « refaire la TDM à 48 h » est une
consigne datée et signée, et c'est sur elle qu'on décide trois jours plus tard.
Écrits dans le texte libre du plan infectieux, ces avis disparaissaient à la
première réécriture du plan — et personne ne savait plus qui avait dit quoi, ni
quand (demande du service, 8 septembre).
"""

from __future__ import annotations

from ..db import Base
from ..domaine import avis as dom


def demander(
    base: Base,
    *,
    sejour_id: str,
    specialite: str,
    texte: str,
    date_avis: str,
    nom: str | None = None,
    grade: str | None = None,
    utilisateur_id: str | None = None,
) -> str:
    """Enregistre un avis. N'annule jamais le précédent, même de la même
    spécialité : c'est la suite des avis qui raconte l'évolution d'une décision
    chirurgicale, et le second ne se comprend souvent qu'à la lumière du
    premier."""
    return base.inserer(
        "avis_specialise",
        {
            "sejour_id": sejour_id,
            "date_avis": date_avis,
            "specialite": specialite,
            "nom": nom,
            "grade": grade,
            "texte": texte,
        },
        utilisateur_id=utilisateur_id,
    )


def du_sejour(base: Base, sejour_id: str) -> list[dict]:
    """Du plus ancien au plus récent : on lit une suite de décisions, et une
    suite se lit dans le sens où elle s'est produite."""
    return base.requete(
        "SELECT * FROM avis_specialise WHERE sejour_id = ? AND supprime = 0 "
        "ORDER BY date_avis, cree_le",
        (sejour_id,),
    )


def supprimer(base: Base, avis_id: str, *, utilisateur_id: str | None = None) -> None:
    """Un avis saisi sur le mauvais patient. Logiquement, jamais
    physiquement : ce qui a été écrit sur un dossier y reste traçable."""
    base.supprimer_logiquement("avis_specialise", avis_id, utilisateur_id=utilisateur_id)


def lignes_imprimees(base: Base, sejour_id: str) -> list[str]:
    """Les avis tels qu'ils s'écrivent sur la feuille, un par ligne."""
    return [dom.ligne_avis(a) for a in du_sejour(base, sejour_id)]
