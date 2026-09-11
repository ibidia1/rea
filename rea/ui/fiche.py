"""Fiche patient — le bandeau d'état et l'assemblage des onglets.
"""

from __future__ import annotations

import streamlit as st

from ..domaine import dispositifs as dom_dispositifs
from ..domaine.dates import jour_hospitalisation
from ..services import dispositifs as dispositifs_service, sejours as sejours_service
from . import contexte, theme

from .actes import onglet_actes
from .bilans import onglet_bilans
from .evolution import onglet_evolution
from .identite import onglet_identite
from .prescrit import onglet_prescrit
from .sortie import onglet_sortie
from .visite import onglet_visite


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
    en_place = [e for e in dispositifs_service.etats(contexte.base(), sejour["id"])
                if e.en_place]
    # Deux redons dans le même abdomen faisaient deux pastilles identiques,
    # dans la première ligne qu'on lit de la fiche.
    numeros = dom_dispositifs.numeros_distincts(en_place)
    for e in en_place:
        style = "attention" if e.type in ("intubation", "sedation", "eer") else "neutre"
        numero = numeros.get(e.id)
        pastilles.append((e.texte if numero is None else f"{e.texte} {numero}", style))
    theme.chips(pastilles)


def ecran_fiche(sejour_id: str) -> None:
    sejour = sejours_service.sejour_avec_patient(contexte.base(), sejour_id)
    if sejour is None:
        st.session_state.pop("sejour_id", None)
        st.rerun()
        return

    st.title(f"Lit {sejour['lit_admission']} — {sejour['nom_affichage']}")
    bandeau_etat(sejour)
    _ecran_choisi(sejour)


#: Les écrans de la fiche, dans l'ordre du travail de la journée. « Visite » en
#: tête : c'est celui qu'on ouvre au pied du lit, et le seul qui n'écrit rien.
ECRANS = (
    ("Visite", onglet_visite),
    ("Identité", onglet_identite),
    ("Prescrit", onglet_prescrit),
    ("Explorations et actes", onglet_actes),
    ("Bilans", onglet_bilans),
    ("Évolution", onglet_evolution),
    ("Sortie", onglet_sortie),
)


def _ecran_choisi(sejour: dict) -> None:
    """N'affiche que l'écran regardé — et c'est une question de vitesse.

    Avec `st.tabs`, Streamlit construit le contenu des sept onglets à chaque
    exécution, qu'on les regarde ou non : 2 785 widgets et 5 400 éléments de
    page pour un patient chargé. Le moindre clic dans le prescrit — changer de
    voie, choisir une date — refaisait tout, et coûtait de 0,7 à 1,1 seconde ;
    ouvrir un patient en demandait neuf. Ce n'est pas la base de données : les
    110 requêtes d'une exécution complète prennent 20 ms.

    Avec un sélecteur, un seul écran est construit. Changer d'écran coûte
    désormais un aller-retour au serveur au lieu d'être instantané — c'est
    l'échange, et il est largement favorable : on change d'écran quelques fois
    par patient, on clique dedans des dizaines de fois.
    """
    cle = f"ecran_{sejour['id']}"
    noms = [nom for nom, _ in ECRANS]
    choix = st.segmented_control(
        "Écran", noms, default=st.session_state.get(cle, noms[0]),
        key=f"segments_{cle}", label_visibility="collapsed",
    ) or st.session_state.get(cle, noms[0])
    st.session_state[cle] = choix
    dict(ECRANS)[choix](sejour)
