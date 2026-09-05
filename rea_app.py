"""Point d'entrée Streamlit.

    streamlit run rea_app.py

Ce fichier ne contient que le montage de l'application : la configuration de
la page, la barre latérale, et l'aiguillage vers l'écran demandé. Chaque écran
vit dans son propre module sous `rea/ui/` — voir SPEC.md pour leur détail.

Il n'y a volontairement aucune logique ici. C'est ce qui permet aux écrans
d'être des modules ordinaires, importables et vérifiables sans lancer
Streamlit — ce qu'un fichier de deux mille lignes ne permettait pas.
"""

from __future__ import annotations

import streamlit as st

from rea import config
from rea.ui import administration as administration_ui
from rea.ui import contexte
from rea.ui import fiche as fiche_ui
from rea.ui import lits as lits_ui
from rea.ui import recherche as recherche_ui
from rea.ui import theme
from rea.ui import utilisateur as utilisateur_ui

st.set_page_config(page_title="Réanimation polyvalente", page_icon="🏥", layout="wide")
theme.appliquer()

base = contexte.base()

utilisateur_id = utilisateur_ui.selecteur(base)
if not utilisateur_id:
    st.stop()

# --------------------------------------------------------------------------
# Barre latérale — utilisateur courant, retour à l'accueil
# --------------------------------------------------------------------------
with st.sidebar:
    st.write(f"**{utilisateur_ui.nom_utilisateur_courant()}**")
    if st.button("↩ Changer d'utilisateur"):
        utilisateur_ui.changer_utilisateur()
    st.divider()
    if st.button("🛏 Tableau des lits", use_container_width=True):
        st.session_state.pop("sejour_id", None)
        st.session_state.pop("ecran", None)
        st.rerun()
    if st.button("📈 Recherche", use_container_width=True):
        st.session_state.pop("sejour_id", None)
        st.session_state["ecran"] = "recherche"
        st.rerun()
    if st.button("⚙ Administration", use_container_width=True):
        st.session_state.pop("sejour_id", None)
        st.session_state["ecran"] = "administration"
        st.rerun()
    st.caption(f"Réanimation polyvalente · {config.NB_LITS} lits")
    st.caption("SPEC.md — voir le dépôt pour l'état d'avancement")


# --------------------------------------------------------------------------
# Aiguillage
# --------------------------------------------------------------------------
if st.session_state.get("ecran") == "administration":
    administration_ui.ecran(base, utilisateur_id)
elif st.session_state.get("ecran") == "recherche":
    recherche_ui.ecran(base, utilisateur_id)
elif st.session_state.get("sejour_id"):
    fiche_ui.ecran_fiche(st.session_state["sejour_id"])
else:
    lits_ui.ecran_lits()
