"""Rassemble ce que la base sait déjà pour appliquer les définitions du
bloc 15 (`rea/domaine/definitions.py`).

Ce module ne calcule rien : il lit, `domaine/definitions.py` décide (règle
R3). Quand une donnée nécessaire n'est tracée nulle part — la PEP n'est pas
saisie, l'imagerie n'est pas structurée —, elle part à `None` et la
définition répond honnêtement « non applicable », plutôt qu'un calcul
approché à partir de ce qu'on a sous la main.
"""

from __future__ import annotations

from ..domaine import definitions as dom
from . import bilans as bilans_service
from . import dispositifs as dispositifs_service
from . import evolution as evolution_service
from . import scores as scores_service
from . import sejours as sejours_service


def _dispositif_en_place(base, sejour_id: str, date_jour: str, type_: str) -> bool:
    return any(
        e.type == type_ and e.en_place for e in dispositifs_service.etats(base, sejour_id, date_jour)
    )


def sdra(base, sejour_id: str, date_jour: str) -> dom.Verdict:
    gaz = bilans_service.dernier_gaz_du_sang(base, sejour_id, date_jour)
    pao2_fio2 = (
        bilans_service.rapport_pao2_fio2(gaz.get("pao2"), gaz.get("fio2")) if gaz else None
    )
    return dom.sdra_berlin(
        pao2_fio2=pao2_fio2,
        peep=(gaz or {}).get("pep"),
        ventile=_dispositif_en_place(base, sejour_id, date_jour, "intubation"),
    )


def ira(base, sejour_id: str, date_jour: str) -> dom.Verdict:
    sejour = sejours_service.sejour_avec_patient(base, sejour_id)
    creat = bilans_service.resultats_du_jour(base, sejour_id, date_jour).get("creat")
    return dom.ira_kdigo(
        creatinine=(creat or {}).get("valeur_num"),
        creatinine_base=(sejour or {}).get("creatinine_base"),
        epuration_en_cours=_dispositif_en_place(base, sejour_id, date_jour, "eer"),
    )


def qsofa(base, sejour_id: str, date_jour: str) -> dom.Verdict:
    elements = evolution_service.elements_du_jour(base, sejour_id, date_jour)
    return dom.qsofa(
        frequence_respiratoire=elements.get("fr_clinique"),
        pas=elements.get("pas"),
        glasgow=elements.get("glasgow"),
    )


def sepsis(
    base, sejour_id: str, date_jour: str, *,
    infection_suspectee: bool | None = None,
    vasopresseurs: bool | None = None,
    hypotension_persistante: bool | None = None,
    lactate: float | None = None,
) -> dom.Verdict:
    """L'infection suspectée est un jugement clinique, jamais déduit d'une
    ligne de prescription (un antibiotique peut être prophylactique) : les
    trois indicateurs viennent de l'écran, pas de la base."""
    sofa_jour = scores_service.sofa(base, sejour_id, date_jour)
    if lactate is None:
        gaz = bilans_service.dernier_gaz_du_sang(base, sejour_id, date_jour)
        lactate = (gaz or {}).get("lactate")
    return dom.sepsis3(
        infection_suspectee=infection_suspectee,
        sofa_actuel=sofa_jour.total if sofa_jour.complet else None,
        vasopresseurs=vasopresseurs,
        hypotension_persistante=hypotension_persistante,
        lactate=lactate,
    )
