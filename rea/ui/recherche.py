"""Écran Recherche — cohortes, indicateurs, export (blocs 13 à 18).

Le service saisit déjà tout ce qu'il faut ; ce qui manquait, c'est de pouvoir
le relire en bloc. Cet écran ne calcule rien lui-même : il assemble une
cohorte, la donne aux services d'analyse, et affiche ce qu'ils rendent — y
compris quand ils rendent « incalculable ».
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from .. import listes, referentiels
from ..db import Base
from ..services import export as export_service
from ..services import statistiques as stats
from . import theme


def ecran(base: Base, utilisateur_id: str | None = None) -> None:
    st.title("Recherche et indicateurs")
    filtres = _filtres()
    selection = stats.cohorte(base, filtres)
    pluriel = "s" if len(selection) > 1 else ""
    st.caption(f"**{len(selection)} séjour{pluriel}** — {filtres.resume()}")
    if not selection:
        st.info("Aucun séjour ne correspond à ces filtres.")
        return

    onglets = st.tabs(
        ["Tableau descriptif", "Indicateurs de service", "Antibiotiques", "Export"]
    )
    with onglets[0]:
        _table_1(base, selection)
    with onglets[1]:
        _indicateurs(base, selection)
    with onglets[2]:
        _antibiotiques(base, selection)
    with onglets[3]:
        _export(base, selection, filtres, utilisateur_id)


def _filtres() -> stats.Filtres:
    with st.expander("🔎 Définir la cohorte", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        debut = c1.date_input("Admissions depuis", value=None, key="coh_debut")
        fin = c2.date_input("Jusqu'au", value=None, key="coh_fin")
        type_admission = c3.selectbox(
            "Type de motif", ["Tous", "Traumatique", "Non traumatique"]
        )
        statut = c4.selectbox("Séjours", ["Tous", "Clos seulement", "Décédés", "Survivants"])

        c5, c6, c7 = st.columns(3)
        age_min = c5.number_input("Âge minimum", 0, 120, 0)
        age_max = c6.number_input("Âge maximum", 0, 120, 120)
        provenances = c7.multiselect(
            "Provenance", listes.codes(listes.PROVENANCES),
            format_func=lambda c: listes.libelle(listes.PROVENANCES, c),
        )
        dispositifs = st.multiselect(
            "Ayant eu au moins un de ces dispositifs",
            listes.ORDRE_DISPOSITIFS, format_func=listes.libelle_dispositif,
        )
    return stats.Filtres(
        date_debut=str(debut) if debut else None,
        date_fin=str(fin) if fin else None,
        traumatique={"Tous": None, "Traumatique": True, "Non traumatique": False}[type_admission],
        age_min=age_min or None,
        age_max=age_max if age_max < 120 else None,
        provenances=tuple(provenances),
        dispositifs=tuple(dispositifs),
        decedes={"Tous": None, "Clos seulement": None, "Décédés": True, "Survivants": False}[statut],
        sejours_clos_seulement=statut != "Tous",
    )


def _table_1(base: Base, selection: list[dict]) -> None:
    st.caption(
        "Tableau descriptif au format attendu par STROBE. Chaque ligne indique "
        "sur combien de dossiers elle est calculée : une donnée manquante est "
        "déclarée, jamais diluée dans un pourcentage."
    )
    lignes = stats.table_1(base, selection)
    corps = "".join(
        f"<tr><td>{l.libelle}</td>"
        f"<td style='text-align:right;font-weight:600'>{l.valeur}</td>"
        f"<td style='text-align:right;color:{'#94a3b8' if not l.manquants else theme.ORANGE}'>"
        f"{l.renseignes}/{l.total}</td>"
        f"<td style='color:#94a3b8;font-size:0.8rem'>{l.note}</td></tr>"
        for l in lignes
    )
    st.markdown(
        "<table style='width:100%;border-collapse:collapse;font-size:0.9rem'>"
        "<thead><tr style='text-align:left;color:#64748b'><th>Caractéristique</th>"
        "<th style='text-align:right'>Valeur</th><th style='text-align:right'>Renseignés</th>"
        "<th>Note</th></tr></thead><tbody>" + corps + "</tbody></table>",
        unsafe_allow_html=True,
    )


def _indicateurs(base: Base, selection: list[dict]) -> None:
    journees = stats.journees_hospitalisation(base, selection)
    c1, c2, c3 = st.columns(3)
    c1.metric("Séjours", len(selection))
    c2.metric("Journées d'hospitalisation", journees)
    morts = stats.mortalite(base, selection)
    c3.metric(
        "Mortalité observée",
        f"{morts['mortalite_observee'] * 100:.0f} %" if morts["mortalite_observee"] is not None else "—",
        help=f"sur {morts['sejours_clos']} séjours clos",
    )

    st.subheader("Infections liées aux dispositifs")
    st.caption(
        "Dénominateur en jours-dispositif (protocole ECDC) : rapporter les "
        "infections au nombre de patients ferait paraître bon un service qui "
        "ventile peu, et mauvais un service qui ventile longtemps."
    )
    for taux in stats.taux_infections_dispositifs(base, selection):
        couleur = theme.GRIS if taux.valeur is None else theme.BLEU
        valeur = "—" if taux.valeur is None else f"{taux.valeur}"
        detail = (
            "Incalculable : aucun jour-dispositif enregistré."
            if taux.valeur is None
            else f"{taux.numerateur} infections / {taux.denominateur} jours-dispositif"
        )
        theme.bloc_html(
            taux.libelle,
            f"<span style='font-size:1.5rem;font-weight:600'>{valeur}</span> "
            f"<span style='color:#94a3b8'>{taux.unite}</span><br>"
            f"<span style='color:#94a3b8;font-size:0.82rem'>{detail} · {taux.note}</span>",
            couleur,
        )

    st.subheader("Mortalité")
    if morts["rapport_observe_attendu"] is not None:
        theme.bloc(
            "Rapport observé / attendu (IGS II)",
            [
                f"{morts['rapport_observe_attendu']}",
                f"{morts['deces']} décès observés pour {morts['deces_attendus']} attendus",
                "Un rapport < 1 ne prouve pas une meilleure prise en charge : "
                "l'étalonnage de l'IGS II vieillit et dépend du recrutement.",
            ],
            theme.BLEU,
        )
    else:
        st.info(morts["note"] or "Rapport observé/attendu non calculable.")


def _antibiotiques(base: Base, selection: list[dict]) -> None:
    resultat = stats.consommation_antibiotiques(base, selection)
    c1, c2 = st.columns(2)
    c1.metric("Jours de traitement antibiotique", resultat["jours_de_traitement"])
    c2.metric(
        "Pour 1000 journées d'hospitalisation",
        resultat["dot_pour_1000_journees"] if resultat["dot_pour_1000_journees"] is not None else "—",
    )
    if resultat["note"]:
        st.caption(resultat["note"])
    if resultat["par_molecule"]:
        st.caption("Jours de traitement par molécule reconnue dans le prescrit :")
        st.dataframe(
            {"molécule": list(resultat["par_molecule"].keys()),
             "jours": list(resultat["par_molecule"].values())},
            use_container_width=True, hide_index=True,
        )
    else:
        st.info(
            "Aucun antibiotique reconnu dans le prescrit de cette cohorte. La "
            "reconnaissance se fait par nom : compléter la liste dans "
            "`referentiels/antibiotiques_ddd.json` si une molécule manque."
        )


def _export(base: Base, selection: list[dict], filtres: stats.Filtres,
            utilisateur_id: str | None) -> None:
    st.caption(
        "L'export ne contient ni matricule, ni nom, ni date de naissance : le "
        "patient y est désigné par son identifiant d'étude, et l'âge remplace "
        "la date de naissance. Il emporte son dictionnaire des données et la "
        "version de chaque référentiel."
    )
    motif = st.text_input("Motif de l'export (noté dans le journal)", value="")
    texte_libre = st.checkbox(
        "Inclure les zones de texte libre (déconseillé)",
        help="Un commentaire d'évolution peut contenir un nom, un lieu, un "
             "numéro de chambre. Cochée, cette case rend l'export non "
             "pseudonymisé de façon fiable.",
    )
    if texte_libre:
        st.warning(
            "L'export contiendra du texte libre : il n'est alors plus "
            "pseudonymisé de façon fiable et se traite comme un dossier "
            "nominatif.", icon="⚠️",
        )
    c1, c2 = st.columns(2)
    if c1.button("📤 Exporter la cohorte", type="primary", use_container_width=True):
        dossier = export_service.exporter(
            base, sejour_ids=[s["id"] for s in selection],
            avec_texte_libre=texte_libre, motif=motif or filtres.resume(),
            utilisateur_id=utilisateur_id,
        )
        st.success(f"Export écrit dans `{dossier}`")
        st.caption(
            "Un export reste une donnée de santé : il se conserve et se "
            "transmet comme telle."
        )
    if c2.button("🧊 Geler la base pour analyse", use_container_width=True):
        gel = export_service.geler(
            base, motif=motif or "analyse", utilisateur_id=utilisateur_id
        )
        st.success(f"Base gelée : `{gel['fichier']}` ({gel['nb_sejours']} séjours)")
        st.caption(
            "Une étude qui tourne pendant que les données bougent n'est pas "
            "reproductible : ce gel garde l'état exact ayant servi à l'analyse."
        )
