"""Onglet Sortie — clôture du séjour (SPEC §4.7).
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from .. import listes
from ..domaine import coherence
from ..domaine.dates import format_date_fr
from ..services import sejours as sejours_service
from . import contexte


def onglet_sortie(sejour: dict) -> None:
    if sejour.get("date_sortie"):
        st.success(f"Séjour clôturé le {format_date_fr(sejour['date_sortie'])}")
        st.text_area("Compte rendu de sortie", value=sejours_service.compte_rendu_sortie(contexte.base(), sejour["id"]), height=250)
        return

    with st.form("sortie_form"):
        mode_sortie = st.selectbox("Mode de sortie", listes.codes(listes.MODES_SORTIE), format_func=lambda c: listes.libelle(listes.MODES_SORTIE, c))
        destination = st.text_input("Destination (service, établissement)")
        meme_etablissement = st.checkbox("Même établissement")
        date_heure_sortie = st.text_input("Date / heure de sortie (AAAA-MM-JJTHH:MM)", value=datetime.now().isoformat(timespec="minutes"))
        complication_statut = st.selectbox(
            "Complications du séjour", listes.codes(listes.TROIS_ETATS),
            index=0,
            format_func=lambda c: listes.libelle(listes.TROIS_ETATS, c),
        )
        complication_texte = st.text_input("Préciser") if complication_statut == "presente" else ""
        ordonnance = st.text_area("Ordonnance de sortie")
        consultation = st.text_input("Consultation externe")
        if st.form_submit_button("Clôturer le séjour") and contexte.controle(
            "sortie",
            coherence.verifier_sejour(
                date_admission=sejour["date_admission"],
                date_sortie=date_heure_sortie,
                date_naissance=sejour.get("date_naissance"),
            ),
            cible="sejour",
            ligne_id=sejour["id"],
        ):
            sejours_service.cloturer_sejour(
                contexte.base(), sejour["id"], date_heure_sortie=date_heure_sortie, mode_sortie=mode_sortie,
                destination=destination or None, meme_etablissement=meme_etablissement,
                complication_statut=complication_statut, complication_texte=complication_texte or None,
                ordonnance_sortie=ordonnance or None, consultation_externe=consultation or None,
                utilisateur_id=contexte.utilisateur_id(),
            )
            st.rerun()
