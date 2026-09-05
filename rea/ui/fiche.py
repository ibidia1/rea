"""Fiche patient — le bandeau d'état et l'assemblage des onglets.
"""

from __future__ import annotations

import streamlit as st

from ..domaine.dates import jour_hospitalisation
from ..services import dispositifs as dispositifs_service, sejours as sejours_service
from . import contexte, theme

from .actes import onglet_actes
from .bilans import onglet_bilans
from .evolution import onglet_evolution
from .identite import onglet_identite
from .prescrit import onglet_prescrit
from .sortie import onglet_sortie


def bandeau_etat(sejour: dict) -> None:
    """Ce qu'on doit voir avant de lire quoi que ce soit d'autre : allergie,
    jour d'hospitalisation, dispositifs en place avec leur compteur."""
    pastilles: list[tuple[str, str]] = []
    allergies = sejours_service.allergies_du_patient(contexte.base(), sejour["patient_id"])
    for a in allergies:
        pastilles.append((f"Allergie : {a['libelle']}", "alerte"))
    pastilles.append(
        (f"J{jour_hospitalisation(sejour['date_admission'])} d'hospitalisation", "info")
    )
    if sejour["traumatique"] and sejours_service.est_polytraumatise(contexte.base(), sejour["id"]):
        pastilles.append(("Polytraumatisé", "attention"))
    for e in dispositifs_service.etats(contexte.base(), sejour["id"]):
        if e.en_place:
            style = "attention" if e.type in ("intubation", "sedation", "eer") else "neutre"
            pastilles.append((e.texte, style))
    theme.chips(pastilles)


def ecran_fiche(sejour_id: str) -> None:
    sejour = sejours_service.sejour_avec_patient(contexte.base(), sejour_id)
    if sejour is None:
        st.session_state.pop("sejour_id", None)
        st.rerun()
        return

    st.title(f"Lit {sejour['lit_admission']} — {sejour['nom_affichage']}")
    bandeau_etat(sejour)
    onglets = st.tabs(
        ["Identité", "Prescrit", "Explorations et actes", "Bilans", "Évolution", "Sortie"]
    )
    with onglets[0]:
        onglet_identite(sejour)
    with onglets[1]:
        onglet_prescrit(sejour)
    with onglets[2]:
        onglet_actes(sejour)
    with onglets[3]:
        onglet_bilans(sejour)
    with onglets[4]:
        onglet_evolution(sejour)
    with onglets[5]:
        onglet_sortie(sejour)
