"""Écran « Explorations et actes » — partie actes et dispositifs.

Pose, retrait, et lecture de l'état d'un séjour. Aucune durée n'est
stockée : les compteurs (« Intubé J3 », « Extubé J2 ») sont calculés par
`rea.domaine.dispositifs`.
"""

from __future__ import annotations

import json

from ..db import Base
from ..domaine import dispositifs as dom


def poser(
    base: Base,
    *,
    sejour_id: str,
    type_: str,
    date_pose: str,
    site: str | None = None,
    details: dict | None = None,
    commentaire: str | None = None,
    utilisateur_id: str | None = None,
) -> str:
    return base.inserer(
        "dispositif",
        {
            "sejour_id": sejour_id,
            "type": type_,
            "date_pose": date_pose,
            "site": site,
            "details": json.dumps(details or {}, ensure_ascii=False),
            "commentaire": commentaire,
        },
        utilisateur_id=utilisateur_id,
    )


def retirer(
    base: Base,
    dispositif_id: str,
    *,
    date_retrait: str,
    motif_retrait: str | None = None,
    utilisateur_id: str | None = None,
) -> None:
    """Le dispositif reste visible après retrait — c'est ce qui permet de
    lire « Extubé J2 » les jours suivants."""
    base.mettre_a_jour(
        "dispositif",
        dispositif_id,
        {"date_retrait": date_retrait, "motif_retrait": motif_retrait},
        utilisateur_id=utilisateur_id,
        action="retrait",
    )


def modifier(
    base: Base, dispositif_id: str, valeurs: dict, *, utilisateur_id: str | None = None
) -> None:
    valeurs = dict(valeurs)
    if "details" in valeurs and isinstance(valeurs["details"], dict):
        valeurs["details"] = json.dumps(valeurs["details"], ensure_ascii=False)
    base.mettre_a_jour("dispositif", dispositif_id, valeurs, utilisateur_id=utilisateur_id)


def du_sejour(base: Base, sejour_id: str) -> list[dict]:
    return base.requete(
        "SELECT * FROM dispositif WHERE sejour_id = ? AND supprime = 0 "
        "ORDER BY date_pose DESC, cree_le DESC",
        (sejour_id,),
    )


def en_place(base: Base, sejour_id: str) -> list[dict]:
    return [l for l in du_sejour(base, sejour_id) if not l["date_retrait"]]


def etats(base: Base, sejour_id: str, a_la_date: str | None = None) -> list[dom.EtatDispositif]:
    return [dom.etat(l, a_la_date) for l in du_sejour(base, sejour_id)]


def resume(base: Base, sejour_id: str, a_la_date: str | None = None) -> str:
    """Ligne compacte des dispositifs en place — reprise dans la pancarte,
    l'évolution et le tableau des lits."""
    return dom.resume(du_sejour(base, sejour_id), a_la_date)


def dernier_du_type(base: Base, sejour_id: str, type_: str) -> dict | None:
    lignes = [l for l in du_sejour(base, sejour_id) if l["type"] == type_]
    return lignes[0] if lignes else None


def duree_ventilation_jours(base: Base, sejour_id: str, a_la_date: str | None = None) -> int:
    """Durée totale de ventilation invasive — variable du socle de recherche
    (SPEC §9.2), calculée depuis les épisodes d'intubation."""
    return dom.duree_totale_jours(du_sejour(base, sejour_id), "intubation", a_la_date)


def duree_epuration_jours(base: Base, sejour_id: str, a_la_date: str | None = None) -> int:
    return dom.duree_totale_jours(du_sejour(base, sejour_id), "eer", a_la_date)


def jours_dispositif_total(base: Base, sejour_id: str, type_: str, a_la_date: str | None = None) -> int:
    """Jours-dispositif : dénominateur des taux d'infection nosocomiale
    (PAVM pour 1 000 jours de ventilation, ILC pour 1 000 jours de
    cathéter — SPEC §9.4)."""
    return dom.duree_totale_jours(du_sejour(base, sejour_id), type_, a_la_date)
