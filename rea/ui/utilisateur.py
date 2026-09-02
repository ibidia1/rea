"""Sélecteur d'utilisateur obligatoire à l'ouverture (SPEC §1.2).

Enregistré une fois par session Streamlit ; l'id est réutilisé sur chaque
ligne créée ou modifiée durant la session.
"""

from __future__ import annotations

import streamlit as st

from .. import listes
from ..db import Base


def utilisateurs_actifs(base: Base) -> list[dict]:
    return base.requete(
        "SELECT * FROM utilisateur WHERE actif = 1 AND supprime = 0 ORDER BY nom"
    )


def creer_utilisateur(base: Base, nom: str, role: str) -> str:
    return base.inserer("utilisateur", {"nom": nom.strip(), "role": role})


def selecteur(base: Base) -> str | None:
    """Affiche le sélecteur. Retourne l'id de l'utilisateur courant, ou None
    tant qu'aucun n'est choisi — l'appelant doit alors bloquer la suite."""
    if "utilisateur_id" in st.session_state:
        return st.session_state["utilisateur_id"]

    st.title("Réanimation polyvalente")
    st.caption("Sélection obligatoire avant toute saisie (SPEC §1.2)")

    utilisateurs = utilisateurs_actifs(base)
    noms = [u["nom"] for u in utilisateurs]

    with st.form("selecteur_utilisateur"):
        choix = st.selectbox("Qui êtes-vous ?", ["— Nouveau —"] + noms)
        nouveau_nom = ""
        nouveau_role = "interne"
        if choix == "— Nouveau —":
            nouveau_nom = st.text_input("Nom")
            nouveau_role = st.selectbox("Rôle", listes.codes(listes.ROLES), format_func=lambda c: listes.libelle(listes.ROLES, c))
        valide = st.form_submit_button("Entrer")

    if valide:
        if choix == "— Nouveau —":
            nom_saisi = nouveau_nom.strip()
            if not nom_saisi:
                st.error("Le nom est obligatoire.")
                return None
            # Un nom déjà pris n'est pas une erreur : on se reconnecte comme
            # cet utilisateur plutôt que de planter sur la contrainte UNIQUE.
            existant = next(
                (u for u in utilisateurs if u["nom"].strip().lower() == nom_saisi.lower()), None
            )
            if existant:
                uid = existant["id"]
                nom_retenu = existant["nom"]
            else:
                uid = creer_utilisateur(base, nom_saisi, nouveau_role)
                nom_retenu = nom_saisi
        else:
            uid = next(u["id"] for u in utilisateurs if u["nom"] == choix)
            nom_retenu = choix
        st.session_state["utilisateur_id"] = uid
        st.session_state["utilisateur_nom"] = nom_retenu
        st.rerun()

    return None


def nom_utilisateur_courant() -> str:
    return st.session_state.get("utilisateur_nom", "")


def changer_utilisateur() -> None:
    for cle in ("utilisateur_id", "utilisateur_nom"):
        st.session_state.pop(cle, None)
    st.rerun()
