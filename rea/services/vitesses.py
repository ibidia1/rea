"""Les réglages de vitesse d'une seringue ou d'une perfusion.

Une vitesse n'est pas une donnée figée : on part à 25 cc/h et on descend à 15
à 16 h. La ligne de prescription porte la vitesse de départ ; ce module porte
la suite des réglages, horodatés — et c'est elle que la feuille imprime, heure
par heure (demande du service, 8 septembre).

Deux choses peuvent couler : une ligne de prescription (noradrénaline en
P.S.E.) et un dispositif (la sédation, posée dans l'écran des actes puis
reportée dans le bloc P.S.E.). Les deux se règlent pareil, elles se lisent
donc pareil — `cible` dit seulement d'où vient ce qui coule.
"""

from __future__ import annotations

from ..db import Base
from ..domaine import prescription as dom

LIGNE = "prescription_ligne"
DISPOSITIF = "dispositif"


def regler(
    base: Base,
    *,
    cible: str,
    cible_id: str,
    date_heure: str,
    vitesse: float,
    utilisateur_id: str | None = None,
) -> str:
    """Note une vitesse à une heure donnée. Jamais un remplacement : une
    vitesse réglée reste dans l'historique, c'est ce qui permet de relire la
    conduite d'une sédation ou d'une noradrénaline sur plusieurs jours.

    Pour un dispositif, passer plutôt par `services.dispositifs.regler_vitesse`
    — c'est lui qui tient à jour, en plus, la vitesse courante affichée sur sa
    carte et dans la pastille du bandeau. Ce module ne connaît pas les
    dispositifs, et c'est voulu : la dépendance ne va que dans un sens.
    """
    return base.inserer(
        "vitesse_reglage",
        {
            "cible": cible,
            "cible_id": cible_id,
            "date_heure": date_heure,
            "vitesse": vitesse,
        },
        utilisateur_id=utilisateur_id,
    )



def annuler(base: Base, reglage_id: str, *, utilisateur_id: str | None = None) -> None:
    """Retire un réglage saisi par erreur — logiquement, jamais physiquement
    (règle de conception 2)."""
    base.supprimer_logiquement("vitesse_reglage", reglage_id, utilisateur_id=utilisateur_id)


def reglages(base: Base, cible: str, cible_id: str) -> list[dict]:
    return base.requete(
        "SELECT * FROM vitesse_reglage WHERE cible = ? AND cible_id = ? "
        "AND supprime = 0 ORDER BY date_heure",
        (cible, cible_id),
    )


def reglages_du_sejour(base: Base, sejour_id: str) -> dict[str, list[dict]]:
    """Tous les réglages du séjour, rangés par cible.

    Une seule requête plutôt qu'une par ligne : la feuille en demande autant
    qu'il y a de seringues, et c'est le genre de lecture qu'on ne veut pas
    voir se multiplier au moment d'imprimer.
    """
    lignes = base.requete(
        "SELECT v.* FROM vitesse_reglage v "
        "LEFT JOIN prescription_ligne p ON p.id = v.cible_id AND v.cible = ? "
        "LEFT JOIN dispositif d ON d.id = v.cible_id AND v.cible = ? "
        "WHERE v.supprime = 0 AND (p.sejour_id = ? OR d.sejour_id = ?) "
        "ORDER BY v.date_heure",
        (LIGNE, DISPOSITIF, sejour_id, sejour_id),
    )
    par_cible: dict[str, list[dict]] = {}
    for ligne in lignes:
        par_cible.setdefault(ligne["cible_id"], []).append(ligne)
    return par_cible


def par_heure(
    base: Base, cible: str, cible_id: str, vitesse_initiale: float | None, date_jour: str
) -> dict[int, float]:
    """La vitesse à écrire dans chaque case horaire d'une journée."""
    return dom.vitesses_par_heure(vitesse_initiale, reglages(base, cible, cible_id), date_jour)
