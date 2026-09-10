"""La bande du haut — l'accès administrateur, et l'essai de rôle (SPEC §2.5).

La barre latérale se replie sur un téléphone et se referme d'un clic par
erreur ; l'administration, elle, doit rester à portée depuis n'importe quel
écran (demande du service, 10 septembre). D'où cette bande, en haut à droite,
rendue avant tout le reste.

Elle porte aussi le bandeau d'essai de rôle, et c'est là qu'il doit être :
**permanent**, en tête de chaque écran. Un message qui passe se serait oublié
— on prescrit, et l'écriture porte le nom de l'administrateur sur une ligne
qu'un infirmier semblait avoir faite.
"""

from __future__ import annotations

import streamlit as st

from ..domaine import droits as dom_droits
from . import contexte
from . import utilisateur as utilisateur_ui


def haut_de_page() -> None:
    """L'accès Admin à droite, et le rappel d'essai s'il y en a un."""
    if not (utilisateur_ui.peut("comptes") or utilisateur_ui.role_essaye()):
        return

    _, bouton = st.columns([5, 1])
    with bouton:
        if st.button("Admin", use_container_width=True, key="acces_admin"):
            # Quitter l'essai d'abord, et **seulement s'il y en a un** :
            # l'écran d'administration appartient à l'administrateur, l'y
            # amener « en tant qu'infirmier » afficherait une page vide.
            if utilisateur_ui.role_essaye():
                utilisateur_ui.essayer_role(None)
            contexte.aller_a("administration")

    essai = utilisateur_ui.role_essaye()
    if not essai:
        return
    gauche, retour = st.columns([4, 1])
    gauche.warning(
        f"**Essai en cours : vous voyez l'application comme "
        f"« {dom_droits.libelle(essai)} ».** Tout ce qui s'écrit reste signé "
        f"« {utilisateur_ui.nom_utilisateur_courant()} » — l'essai change ce "
        "qu'on voit, jamais qui signe.",
        icon="🧪",
    )
    if retour.button("Quitter l'essai", use_container_width=True,
                     type="primary", key="quitter_essai"):
        utilisateur_ui.essayer_role(None)
        st.rerun()
