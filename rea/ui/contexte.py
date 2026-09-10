"""Ce que tout écran a besoin de savoir : la base ouverte, qui est devant, et
le garde-fou de cohérence partagé.

Ces trois choses vivaient en variables globales de `rea_app.py`, ce qui obligeait
tous les écrans à tenir dans ce fichier. Les passer par ici permet à chaque écran
d'être un module ordinaire — donc testable sans lancer Streamlit.

La couche reste mince à dessein : elle ne calcule rien et ne décide rien, elle
donne accès. Toute règle métier reste dans `rea/domaine/`, toute écriture dans
`rea/services/` (règle R1 de la feuille de route).
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from ..db import Base, obtenir_base


def base() -> Base:
    """La base du service. `obtenir_base()` garde une connexion unique."""
    return obtenir_base()


def utilisateur_id() -> str | None:
    """Qui est devant l'écran — posé par `utilisateur.selecteur()` à l'ouverture.

    Toute écriture le reçoit : c'est ce qui rend le journal exploitable
    (SPEC §1.2, règle de conception 8).
    """
    return st.session_state.get("utilisateur_id")


def aller_a(ecran: str) -> None:
    """Change d'écran et repart de l'accueil de cet écran.

    Le séjour ouvert est oublié au passage : garder « lit 3 » en mémoire en
    allant sur la recherche fait revenir sur la fiche du lit 3 au clic
    suivant, sans que personne comprenne pourquoi.
    """
    st.session_state.pop("sejour_id", None)
    st.session_state["ecran"] = ecran
    st.rerun()


def aujourdhui() -> str:
    return date.today().isoformat()


def controle(
    cle: str,
    avertissements: list,
    *,
    cible: str = "ecran",
    ligne_id: str | None = None,
) -> bool:
    """Affiche les avertissements de cohérence et dit si l'on peut enregistrer.

    Un avertissement n'est jamais un blocage définitif (bloc 4) : un
    « improbable » s'affiche et laisse passer, un « impossible » — sortie
    avant l'admission, extubation avant l'intubation — demande un second
    clic. Le médecin garde le dernier mot, mais pas par inadvertance.

    Ce second clic est journalisé. `bilan_resultat` a une colonne
    `saisie_forcee`, mais les cinq autres écrans qui laissent forcer n'en ont
    aucune : sans cette trace, rien dans le dossier ne dirait qu'un garde-fou
    a été franchi. `cible` nomme ce qui est concerné (la table, ou l'écran
    quand aucune ligne n'existe encore).
    """
    if not avertissements:
        st.session_state.pop(f"forcer_{cle}", None)
        return True
    for a in avertissements:
        (st.error if a.gravite == "impossible" else st.warning)(a.message, icon="⚠️")
    if not any(a.gravite == "impossible" for a in avertissements):
        return True
    if st.session_state.pop(f"forcer_{cle}", False):
        base().journaliser_forcage(
            cible=cible,
            avertissements=avertissements,
            utilisateur_id=utilisateur_id(),
            ligne_id=ligne_id,
        )
        return True
    st.session_state[f"forcer_{cle}"] = True
    st.info("Cliquer à nouveau sur le bouton pour enregistrer malgré tout.")
    return False
