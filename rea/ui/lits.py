"""Écran 1 — tableau des lits (accueil) et vue d'ensemble du service.
"""

from __future__ import annotations

import streamlit as st

from .. import config, listes
from ..domaine import prescription as dom
from ..domaine.dates import lendemain
from ..services import bilans as bilans_service
from ..services import dispositifs as dispositifs_service
from ..services import lits as lits_service
from ..services import prescriptions as prescriptions_service
from ..services import sejours as sejours_service
from . import contexte, theme

from . import champs
from .admission import ecran_nouvelle_admission


def _motif_court(sejour_id: str, traumatique: bool | None) -> str:
    """Une ligne de contexte sur la tuile du lit : ce qu'un médecin veut
    voir avant même d'ouvrir le dossier."""
    if traumatique:
        regions = sejours_service.regions_traumatiques(contexte.base(), sejour_id)
        if sejours_service.est_polytraumatise(contexte.base(), sejour_id):
            return "Polytraumatisé"
        if regions:
            return listes.libelle(listes.REGIONS_TRAUMATIQUES, regions[0])
        return "Traumatique"
    motifs = sejours_service.motifs_du_sejour(contexte.base(), sejour_id)
    principal = next((m for m in motifs if m["principal"]), None)
    return listes.libelle_motif(principal["code"]) if principal else "Motif non précisé"


def ecran_lits() -> None:
    etat = lits_service.etat_des_lits(contexte.base())
    occupes = [l for l in etat if l["occupe"]]

    resumes = {
        l["sejour_id"]: dispositifs_service.etats(contexte.base(), l["sejour_id"]) for l in occupes
    }
    intubes = sum(
        1 for e in resumes.values()
        if any(d.en_place and d.type == "intubation" for d in e)
    )
    sedates = sum(
        1 for e in resumes.values()
        if any(d.en_place and d.type == "sedation" for d in e)
    )

    aujourdhui = contexte.aujourdhui()
    admissions_jour = contexte.base().une_ligne(
        "SELECT COUNT(*) AS n FROM sejour WHERE date_admission LIKE ? AND supprime = 0",
        (f"{aujourdhui}%",),
    )["n"]
    sorties_jour = contexte.base().une_ligne(
        "SELECT COUNT(*) AS n FROM sejour WHERE date_sortie LIKE ? AND supprime = 0",
        (f"{aujourdhui}%",),
    )["n"]

    st.markdown("### Tableau des lits")
    c1, c2, c3, c4, c5, c6, c7, _vide = st.columns([1, 1, 1, 1, 1, 1, 1, 1.6])
    c1.metric("Occupés", f"{len(occupes)}/{config.NB_LITS}")
    c2.metric("Libres", config.NB_LITS - len(occupes))
    c3.metric("Occupation", f"{round(100 * len(occupes) / config.NB_LITS)} %")
    c4.metric("Intubés", intubes)
    c5.metric("Sédatés", sedates)
    c6.metric("Admissions du jour", admissions_jour)
    c7.metric("Sorties du jour", sorties_jour)

    # Six colonnes : les douze lits tiennent en deux rangées, sans défilement.
    for rangee in (range(1, 7), range(7, config.NB_LITS + 1)):
        colonnes = st.columns(6)
        for i, numero in enumerate(rangee):
            lit_info = next(l for l in etat if l["lit"] == numero)
            with colonnes[i]:
                with st.container(border=True):
                    _carte_lit(lit_info, resumes)

    if st.session_state.get("mode") == "nouvelle_admission":
        ecran_nouvelle_admission(st.session_state.get("lit_admission_choisi"))
        return

    _tableau_de_bord(occupes, resumes)


def _tableau_de_bord(occupes: list[dict], resumes: dict) -> None:
    """La vue de la visite : une ligne par patient avec l'essentiel, et à
    côté ce qui demande une décision aujourd'hui. Tout est calculé depuis ce
    qui est déjà saisi — rien à ressaisir, rien à cocher."""
    if not occupes:
        st.info("Aucun patient hospitalisé. Cliquez sur « Admettre » pour ouvrir un séjour.")
        return

    aujourdhui = contexte.aujourdhui()
    demain = str(lendemain(aujourdhui))

    synoptique: list[dict] = []
    echeances: list[str] = []
    dispositifs_anciens: list[str] = []
    a_preparer: list[str] = []

    for lit in sorted(occupes, key=lambda l: l["lit"]):
        nom = lit["nom_affichage"]
        sejour_id = lit["sejour_id"]
        pancarte = prescriptions_service.pancarte_du_jour(contexte.base(), sejour_id, aujourdhui)

        durees: list[str] = []
        for ligne in pancarte["lignes"]:
            if ligne["statut"] != "active":
                continue
            etiquette = dom.etiquette_jour(ligne, aujourdhui)
            if not ligne["duree_prevue_jours"]:
                continue
            durees.append(f"{ligne['produit']} {etiquette.texte}")
            if etiquette.dernier_jour:
                echeances.append(
                    f"<b>Lit {lit['lit']} · {nom}</b> — {ligne['produit']} "
                    f'<span class="rea-fin">dernier jour ({etiquette.texte})</span>'
                )
            elif etiquette.echue:
                echeances.append(
                    f"<b>Lit {lit['lit']} · {nom}</b> — {ligne['produit']} "
                    f"au-delà de la durée prévue ({etiquette.texte})"
                )

        etats_disp = resumes.get(sejour_id, [])
        for e in etats_disp:
            if e.en_place and e.jour >= 7 and e.type in (
                "kt_central", "kta", "sonde_urinaire", "picc", "ktsp", "intubation"
            ):
                dispositifs_anciens.append(f"<b>Lit {lit['lit']} · {nom}</b> — {e.texte}")

        journee = contexte.base().une_ligne(
            "SELECT preparee_le FROM journee WHERE sejour_id = ? AND date_jour = ? "
            "AND supprime = 0",
            (sejour_id, demain),
        )
        prete = bool(journee and journee["preparee_le"])
        if not prete:
            a_preparer.append(f"Lit {lit['lit']} · {nom}")

        derniers = bilans_service.dernieres_variations(
            contexte.base(), sejour_id, ["crp", "creat", "hb"]
        )
        valeurs = {v.analyte: v for v in derniers}

        def _valeur(code: str) -> str:
            v = valeurs.get(code)
            if not v or v.valeur is None:
                return "—"
            fleche = ""
            if v.delta:
                fleche = " ↑" if v.delta > 0 else " ↓"
            marque = " !" if v.alerte else ""
            return f"{champs.format_valeur(v.valeur)}{fleche}{marque}"

        synoptique.append({
            "Lit": lit["lit"],
            "Patient": nom,
            "J": lit["jour_hospitalisation"],
            "Motif": _motif_court(sejour_id, lit["traumatique"]),
            "Dispositifs": " · ".join(
                e.texte.split(" (")[0] for e in etats_disp if e.en_place
            ) or "—",
            "Durées prévues": " · ".join(durees) or "—",
            "Entrées 24 h": f"{pancarte['bilan_entrees'].total_ml:.0f} mL",
            "CRP": _valeur("crp"),
            "Créat.": _valeur("creat"),
            "Hb": _valeur("hb"),
            "Bilans demain": len(pancarte["bilans_demandes"]) or "—",
            "Pancarte demain": "prête" if prete else "à préparer",
        })

    import pandas as pd

    # Le synoptique prend toute la largeur : c'est un tableau de visite, il
    # ne doit jamais avoir de colonne tronquée.
    st.markdown("##### Synoptique du service")
    st.dataframe(
        pd.DataFrame(synoptique).set_index("Lit"),
        use_container_width=True,
        height=min(36 * len(synoptique) + 40, 430),
    )
    st.caption(
        "Flèche = variation depuis le prélèvement précédent · "
        "« ! » = hors des bornes usuelles, à valider par un senior"
    )

    g, m, d = st.columns(3)
    with g:
        theme.bloc(
            "Traitements à revoir",
            echeances or ["Aucune échéance aujourd'hui"],
            theme.ROUGE if echeances else theme.VERT,
        )
    with m:
        theme.bloc(
            "Dispositifs de 7 jours ou plus",
            dispositifs_anciens or ["Aucun"],
            theme.ORANGE if dispositifs_anciens else theme.VERT,
        )
    with d:
        theme.bloc(
            f"Pancartes de demain ({len(a_preparer)} à préparer)",
            a_preparer or ["Toutes préparées"],
            theme.BLEU if a_preparer else theme.VERT,
        )


def _carte_lit(lit_info: dict, resumes: dict) -> None:
    numero = lit_info["lit"]
    st.markdown(
        f'<div class="rea-lit"><span class="rea-lit-num">Lit {numero} · '
        f'Ch. {lit_info["chambre"]}</span>',
        unsafe_allow_html=True,
    )
    if not lit_info["occupe"]:
        # « Libre » suffit : ajouter une pastille « Disponible » disait deux
        # fois la même chose dans une carte déjà étroite.
        st.markdown('<div class="rea-lit-libre">Libre</div></div>', unsafe_allow_html=True)
        if st.button("Admettre", key=f"lit_{numero}", use_container_width=True):
            st.session_state["lit_admission_choisi"] = numero
            st.session_state["mode"] = "nouvelle_admission"
            st.rerun()
        return

    sejour_id = lit_info["sejour_id"]
    st.markdown(
        f'<div class="rea-lit-nom">{lit_info["nom_affichage"]}</div>'
        f'<div class="rea-lit-motif">{_motif_court(sejour_id, lit_info["traumatique"])}</div></div>',
        unsafe_allow_html=True,
    )

    pastilles: list[tuple[str, str]] = [(f"J{lit_info['jour_hospitalisation']}", "info")]
    if sejours_service.allergies_du_patient(contexte.base(), lit_info["patient_id"]):
        pastilles.append(("Allergie", "alerte"))
    # Sur une tuile étroite, seuls les dispositifs qui changent la conduite
    # tiennent : le détail complet est dans le bandeau de la fiche patient.
    for e in resumes.get(sejour_id, []):
        if not e.en_place or e.type not in ("intubation", "sedation", "eer", "kt_central"):
            continue
        court = e.texte.split(" (")[0]
        style = "attention" if e.type in ("intubation", "sedation", "eer") else "neutre"
        pastilles.append((court, style))
    theme.chips(pastilles[:4])

    if st.button("Ouvrir", key=f"lit_{numero}", use_container_width=True):
        st.session_state["sejour_id"] = sejour_id
        st.session_state.pop("ecran", None)
        st.rerun()
