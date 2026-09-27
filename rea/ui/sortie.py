"""Onglet Sortie — clôture du séjour (SPEC §4.7).
"""

from __future__ import annotations

from datetime import date, datetime

import streamlit as st

from .. import listes
from ..models import coherence
from ..models import devenir as dom_devenir
from ..models.dates import format_date_fr
from ..services import sejours as sejours_service
from . import contexte

#: Libellés du devenir à J28, dans l'ordre où on les propose.
LIBELLES_J28 = {"vivant": "Vivant à J28", "decede": "Décédé avant J28",
                "perdu_de_vue": "Perdu de vue"}


def suivi_j28(sejour: dict, *, cle: str) -> None:
    """Le devenir à J28 : affiché quand il est connu (saisi ou déduit),
    demandé quand il ne l'est pas — un patient sorti vivant avant J28."""
    statut = dom_devenir.statut_j28(sejour)
    if sejour.get("statut_j28"):
        st.caption(
            f"Devenir à J28 : **{LIBELLES_J28[sejour['statut_j28']]}** "
            f"(noté le {format_date_fr(sejour.get('date_statut_j28') or '')})."
        )
    elif statut:
        st.caption(f"Devenir à J28 : **{LIBELLES_J28[statut]}** — déduit du séjour.")
    if not dom_devenir.a_relancer(sejour) and not sejour.get("statut_j28"):
        return
    c1, c2, c3 = st.columns([2, 1.3, 1])
    choix = c1.selectbox(
        "Devenir à J28", list(LIBELLES_J28), format_func=LIBELLES_J28.get,
        index=None, placeholder="Vivant, décédé ou perdu de vue",
        key=f"j28_statut_{cle}",
    )
    quand = c2.date_input("Vérifié le", value=date.today(), key=f"j28_date_{cle}",
                          format="DD/MM/YYYY")
    c3.markdown("<div style='height:1.7rem'></div>", unsafe_allow_html=True)
    if c3.button("Enregistrer", key=f"j28_ok_{cle}", disabled=choix is None):
        sejours_service.noter_statut_j28(
            contexte.base(), sejour["id"], statut=choix, date_statut=str(quand),
            utilisateur_id=contexte.utilisateur_id(),
        )
        st.rerun()


def onglet_sortie(sejour: dict) -> None:
    if sejour.get("date_sortie"):
        st.success(f"Séjour clôturé le {format_date_fr(sejour['date_sortie'])}")
        if dom_devenir.a_relancer(sejour):
            st.info(
                "Sorti vivant avant J28 : son **devenir à J28** reste à vérifier "
                "(appel, dossier du service d'aval). C'est ce qui rend la "
                "mortalité à J28 calculable."
            )
        suivi_j28(sejour, cle=sejour["id"])
        st.text_area("Compte rendu de sortie", value=sejours_service.compte_rendu_sortie(contexte.base(), sejour["id"]), height=250)
        return

    with st.form("sortie_form"):
        mode_sortie = st.selectbox("Mode de sortie", listes.codes(listes.MODES_SORTIE), format_func=lambda c: listes.libelle(listes.MODES_SORTIE, c))
        destination = st.text_input("Destination (service, établissement)")
        meme_etablissement = st.checkbox("Même établissement")
        # Un jour et une heure choisis, plus une chaîne à taper au format
        # « AAAA-MM-JJTHH:MM » : une faute de frappe faisait planter l'écran
        # au lieu d'enregistrer la sortie (audit du 27 septembre).
        c_jour, c_heure = st.columns(2)
        jour_sortie = c_jour.date_input("Date de sortie", value=date.today(),
                                        format="DD/MM/YYYY")
        heure_sortie = c_heure.time_input(
            "Heure de sortie",
            value=datetime.now().time().replace(second=0, microsecond=0), step=300,
        )
        date_heure_sortie = f"{jour_sortie.isoformat()}T{heure_sortie:%H:%M}"
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
