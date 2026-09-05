"""Écran 2 — admission d'un patient dans un lit libre (SPEC §4.1).
"""

from __future__ import annotations

from datetime import date, datetime

import streamlit as st

from .. import listes, referentiels
from ..domaine import coherence
from ..services import sejours as sejours_service
from . import contexte

from . import champs


def ecran_nouvelle_admission(lit: int | None) -> None:
    st.divider()
    st.header(f"Nouvelle admission — Lit {lit}")
    with st.form("nouvelle_admission"):
        col1, col2 = st.columns(2)
        with col1:
            non_identifie = st.checkbox("Patient non identifié")
            matricule = (
                sejours_service.prochain_matricule_non_identifie(contexte.base())
                if non_identifie
                else st.text_input("Matricule")
            )
            nom_affichage = (
                "Non identifié" if non_identifie else st.text_input("Nom affiché (ex. « K. Abdelaziz »)")
            )
            date_naissance = None if non_identifie else st.date_input(
                "Date de naissance", value=None, min_value=date(1900, 1, 1), max_value=date.today()
            )
            c_sexe, c_groupe = st.columns(2)
            sexe = c_sexe.selectbox(
                "Sexe", listes.codes(listes.SEXES),
                format_func=lambda c: listes.libelle(listes.SEXES, c),
            )
            # Le groupe sanguin est demandé dès l'admission : il figure en tête
            # de la feuille imprimée, et le chercher à quatre heures du matin
            # n'est pas un moment pour le chercher.
            groupes = referentiels.charger("groupes_sanguins")
            groupe_sanguin = c_groupe.selectbox(
                "Groupe sanguin", listes.codes(groupes),
                format_func=lambda c: listes.libelle(groupes, c),
            )
            c_poids, c_taille = st.columns(2)
            # Le poids conditionne la clairance de la créatinine : sans lui,
            # aucune formule pondérale n'est calculable ensuite.
            poids_kg = champs.nombre_saisi(
                c_poids.text_input("Poids (kg)", value="", placeholder="ex. 70")
            )
            taille_cm = champs.nombre_saisi(
                c_taille.text_input("Taille (cm)", value="", placeholder="ex. 175")
            )
            creatinine_base = champs.nombre_saisi(
                st.text_input(
                    "Créatinine antérieure connue (µmol/L)", value="",
                    placeholder="si connue — sert au diagnostic d'insuffisance rénale aiguë",
                )
            )
        with col2:
            date_admission = st.date_input("Date d'admission", value=date.today())
            provenance_type = st.selectbox(
                "Provenance", listes.codes(listes.PROVENANCES), format_func=lambda c: listes.libelle(listes.PROVENANCES, c)
            )
            provenance_detail = ""
            if provenance_type in listes.PROVENANCES_AVEC_DETAIL:
                provenance_detail = st.text_input("Préciser le service / l'établissement")
            est_readmission = st.checkbox("Réadmission")
            motif_readmission = st.text_input("Motif de réadmission") if est_readmission else ""
            # Deux variables de l'IGS II qu'aucune autre donnée du dossier ne
            # permet de retrouver après coup.
            types_admission = referentiels.charger("types_admission")
            type_admission = st.selectbox(
                "Type d'admission", listes.codes(types_admission),
                format_func=lambda c: listes.libelle(types_admission, c),
            )
            maladies = referentiels.charger("maladies_chroniques_igs2")
            maladie_chronique_igs2 = st.selectbox(
                "Maladie chronique (IGS II)", listes.codes(maladies),
                format_func=lambda c: listes.libelle(maladies, c),
            )

        st.markdown("**Motif d'admission**")
        traumatique = st.radio("Type", ["Traumatique", "Non traumatique"], horizontal=True) == "Traumatique"

        regions_choisies: list[str] = []
        mecanisme = None
        mecanisme_detail = ""
        motif_principal = None
        motifs_associes: list[str] = []

        if traumatique:
            regions_choisies = st.multiselect(
                "Régions atteintes",
                listes.codes(listes.REGIONS_TRAUMATIQUES),
                format_func=lambda c: listes.libelle(listes.REGIONS_TRAUMATIQUES, c),
            )
            if len(regions_choisies) >= 2:
                st.info("Statut polytraumatisé — calculé automatiquement")
            mecanisme = st.selectbox(
                "Mécanisme", listes.codes(listes.MECANISMES), format_func=lambda c: listes.libelle(listes.MECANISMES, c)
            )
            if mecanisme in listes.MECANISMES_AVEC_DETAIL:
                mecanisme_detail = st.text_input("Préciser le mécanisme")
        else:
            tous_motifs = listes.motifs_a_plat()
            motif_principal = st.selectbox(
                "Motif principal", [c for c, _l, _g in tous_motifs],
                format_func=lambda c: f"{listes.libelle_motif(c)} ({next(g for cc,_l,g in tous_motifs if cc==c)})",
            )
            motifs_associes = st.multiselect(
                "Motifs associés",
                [c for c, _l, _g in tous_motifs if c != motif_principal],
                format_func=listes.libelle_motif,
            )

        valide = st.form_submit_button("Créer l'admission")

    if valide:
        if not non_identifie and not matricule:
            st.error("Le matricule est obligatoire.")
            return
        if not contexte.controle(
            "admission",
            coherence.verifier_sejour(
                date_admission=date_admission, date_naissance=date_naissance
            ),
            cible="sejour",
        ):
            return
        pid = sejours_service.creer_patient(
            contexte.base(),
            matricule=matricule,
            nom_affichage=nom_affichage or "Non identifié",
            date_naissance=str(date_naissance) if date_naissance else None,
            sexe=sexe,
            groupe_sanguin=groupe_sanguin,
            non_identifie=non_identifie,
            utilisateur_id=contexte.utilisateur_id(),
        )
        sid = sejours_service.creer_sejour(
            contexte.base(),
            patient_id=pid,
            date_admission=datetime.combine(date_admission, datetime.min.time()).isoformat(),
            lit_admission=lit,
            provenance_type=provenance_type,
            provenance_detail=provenance_detail or None,
            est_readmission=est_readmission,
            motif_readmission=motif_readmission or None,
            traumatique=traumatique,
            mecanisme=mecanisme,
            mecanisme_detail=mecanisme_detail or None,
            poids_kg=poids_kg,
            taille_cm=taille_cm,
            creatinine_base=creatinine_base,
            type_admission=type_admission,
            maladie_chronique_igs2=maladie_chronique_igs2,
            utilisateur_id=contexte.utilisateur_id(),
        )
        if traumatique and regions_choisies:
            sejours_service.definir_regions_traumatiques(contexte.base(), sid, regions_choisies, utilisateur_id=contexte.utilisateur_id())
        if not traumatique and motif_principal:
            sejours_service.definir_motifs(
                contexte.base(), sid, motif_principal=motif_principal, motifs_associes=motifs_associes,
                utilisateur_id=contexte.utilisateur_id(),
            )
        st.session_state.pop("mode", None)
        st.session_state.pop("lit_admission_choisi", None)
        st.session_state["sejour_id"] = sid
        st.session_state.pop("ecran", None)
        st.success("Séjour créé.")
        st.rerun()
