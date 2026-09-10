"""Point d'entrée Streamlit.

    streamlit run rea_app.py

Ce fichier ne contient que le montage de l'application : la configuration de
la page, la barre latérale, et l'aiguillage vers l'écran demandé. Chaque écran
vit dans son propre module sous `rea/ui/` — voir SPEC.md pour leur détail.

Il n'y a volontairement aucune logique ici. C'est ce qui permet aux écrans
d'être des modules ordinaires, importables et vérifiables sans lancer
Streamlit — ce qu'un fichier de deux mille lignes ne permettait pas.

L'aiguillage tient compte du rôle : un infirmier ouvre son poste, un
surveillant sa supervision, un médecin le tableau des lits. Ce n'est pas une
barrière de sécurité — c'est écrit dans `domaine/droits.py` — mais un écran
qui ne propose que ce qu'on a le droit de faire évite la moitié des erreurs.
"""

from __future__ import annotations

import streamlit as st

from rea import config
from rea.ui import administration as administration_ui
from rea.ui import bandeau as bandeau_ui
from rea.ui import contexte
from rea.ui import fiche as fiche_ui
from rea.ui import infirmier as infirmier_ui
from rea.ui import lits as lits_ui
from rea.ui import recherche as recherche_ui
from rea.ui import surveillant as surveillant_ui
from rea.ui import theme
from rea.ui import utilisateur as utilisateur_ui

st.set_page_config(page_title="Réanimation polyvalente", page_icon="🏥", layout="wide")
theme.appliquer()

base = contexte.base()

utilisateur_id = utilisateur_ui.selecteur(base)
if not utilisateur_id:
    st.stop()

# Une seule fois par session, et pas « chaque fois que l'écran est absent ».
# La nuance décide de tout : ouvrir un dossier retire `ecran` pour laisser
# passer la fiche, et un test « si absent, remets l'accueil du rôle » la
# reposait aussitôt — le surveillant et l'infirmier étaient renvoyés chez eux
# à chaque tentative d'ouvrir un patient, sans jamais pouvoir en lire un.
if "accueil_pose" not in st.session_state:
    contexte.poser_accueil(utilisateur_ui.role_courant())


bandeau_ui.haut_de_page()


# --------------------------------------------------------------------------
# Barre latérale — utilisateur courant, navigation selon le rôle
# --------------------------------------------------------------------------

with st.sidebar:
    from rea.domaine import droits as dom_droits

    st.write(f"**{utilisateur_ui.nom_utilisateur_courant()}**")
    st.caption(dom_droits.libelle(utilisateur_ui.role_courant()))
    if st.button("Changer d'utilisateur"):
        utilisateur_ui.changer_utilisateur()
    st.divider()

    if utilisateur_ui.peut("administrations"):
        if st.button("Mon poste", use_container_width=True):
            contexte.aller_a("poste")
    if utilisateur_ui.peut("dossier_lire"):
        if st.button("Tableau des lits", use_container_width=True):
            contexte.aller_a("")
    if utilisateur_ui.peut("supervision"):
        if st.button("Surveillance", use_container_width=True):
            contexte.aller_a("supervision")
    if utilisateur_ui.peut("recherche"):
        if st.button("Recherche", use_container_width=True):
            contexte.aller_a("recherche")
    if utilisateur_ui.peut("protocoles") or utilisateur_ui.peut("comptes"):
        if st.button("Administration", use_container_width=True):
            contexte.aller_a("administration")

    st.caption(f"Réanimation polyvalente · {config.NB_LITS} lits")
    st.caption("SPEC.md — voir le dépôt pour l'état d'avancement")


# --------------------------------------------------------------------------
# Aiguillage
# --------------------------------------------------------------------------
ecran = st.session_state.get("ecran")

if ecran == "poste" and utilisateur_ui.peut("administrations"):
    infirmier_ui.ecran(base, utilisateur_id)
elif ecran == "supervision" and utilisateur_ui.peut("supervision"):
    surveillant_ui.ecran(base, utilisateur_id)
elif ecran == "administration" and (
    utilisateur_ui.peut("protocoles") or utilisateur_ui.peut("comptes")
):
    administration_ui.ecran(base, utilisateur_id)
elif ecran == "recherche" and utilisateur_ui.peut("recherche"):
    recherche_ui.ecran(base, utilisateur_id)
elif st.session_state.get("sejour_id"):
    fiche_ui.ecran_fiche(st.session_state["sejour_id"])
elif utilisateur_ui.peut("dossier_lire"):
    lits_ui.ecran_lits()
else:
    st.error(
        "Ce compte n'a accès à aucun écran. Demander à un administrateur de "
        "vérifier son rôle."
    )
