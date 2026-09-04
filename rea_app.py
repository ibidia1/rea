"""Point d'entrée Streamlit.

    streamlit run rea_app.py

Voir SPEC.md pour le détail des écrans. v1 minimale : Lits, Admission,
Prescrit, Sortie — le sous-ensemble qui, selon la feuille de route,
« résout déjà le problème principal du service ».
"""

from __future__ import annotations

from datetime import date, datetime

import streamlit as st

from rea import analytes as cat, config, listes, referentiels
from rea.db import obtenir_base
from rea.domaine import calculs
from rea.domaine import coherence
from rea.domaine import prescription as dom
from rea.domaine.dates import age_ans, format_date_fr, jour_hospitalisation, lendemain, parse_date
from rea.services import aides as aides_service
from rea.services import bilans as bilans_service
from rea.services import dispositifs as dispositifs_service
from rea.services import evolution as evolution_service
from rea.services import explorations as explorations_service
from rea.services import lits as lits_service
from rea.services import microbiologie as micro_service
from rea.services import pancarte as pancarte_service
from rea.services import prescriptions as prescriptions_service
from rea.services import scores as scores_service
from rea.services import sejours as sejours_service
from rea.ui import administration as administration_ui
from rea.ui import recherche as recherche_ui
from rea.ui import theme
from rea.ui import utilisateur as utilisateur_ui

st.set_page_config(page_title="Réanimation polyvalente", page_icon="🏥", layout="wide")
theme.appliquer()

base = obtenir_base()

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


def _aujourdhui() -> str:
    return date.today().isoformat()


def _controle(cle: str, avertissements: list) -> bool:
    """Affiche les avertissements de cohérence et dit si l'on peut enregistrer.

    Un avertissement n'est jamais un blocage définitif (bloc 4) : un
    « improbable » s'affiche et laisse passer, un « impossible » — sortie
    avant l'admission, extubation avant l'intubation — demande un second
    clic. Le médecin garde le dernier mot, mais pas par inadvertance.
    """
    if not avertissements:
        st.session_state.pop(f"forcer_{cle}", None)
        return True
    for a in avertissements:
        (st.error if a.gravite == "impossible" else st.warning)(a.message, icon="⚠️")
    if not any(a.gravite == "impossible" for a in avertissements):
        return True
    if st.session_state.pop(f"forcer_{cle}", False):
        return True
    st.session_state[f"forcer_{cle}"] = True
    st.info("Cliquer à nouveau sur le bouton pour enregistrer malgré tout.")
    return False


# --------------------------------------------------------------------------
# Écran 1 — Tableau des lits (accueil)
# --------------------------------------------------------------------------

def _motif_court(sejour_id: str, traumatique: bool | None) -> str:
    """Une ligne de contexte sur la tuile du lit : ce qu'un médecin veut
    voir avant même d'ouvrir le dossier."""
    if traumatique:
        regions = sejours_service.regions_traumatiques(base, sejour_id)
        if sejours_service.est_polytraumatise(base, sejour_id):
            return "Polytraumatisé"
        if regions:
            return listes.libelle(listes.REGIONS_TRAUMATIQUES, regions[0])
        return "Traumatique"
    motifs = sejours_service.motifs_du_sejour(base, sejour_id)
    principal = next((m for m in motifs if m["principal"]), None)
    return listes.libelle_motif(principal["code"]) if principal else "Motif non précisé"


def ecran_lits() -> None:
    etat = lits_service.etat_des_lits(base)
    occupes = [l for l in etat if l["occupe"]]

    resumes = {
        l["sejour_id"]: dispositifs_service.etats(base, l["sejour_id"]) for l in occupes
    }
    intubes = sum(
        1 for e in resumes.values()
        if any(d.en_place and d.type == "intubation" for d in e)
    )
    sedates = sum(
        1 for e in resumes.values()
        if any(d.en_place and d.type == "sedation" for d in e)
    )

    aujourdhui = _aujourdhui()
    admissions_jour = base.une_ligne(
        "SELECT COUNT(*) AS n FROM sejour WHERE date_admission LIKE ? AND supprime = 0",
        (f"{aujourdhui}%",),
    )["n"]
    sorties_jour = base.une_ligne(
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

    aujourdhui = _aujourdhui()
    demain = str(lendemain(aujourdhui))

    synoptique: list[dict] = []
    echeances: list[str] = []
    dispositifs_anciens: list[str] = []
    a_preparer: list[str] = []

    for lit in sorted(occupes, key=lambda l: l["lit"]):
        nom = lit["nom_affichage"]
        sejour_id = lit["sejour_id"]
        pancarte = prescriptions_service.pancarte_du_jour(base, sejour_id, aujourdhui)

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

        journee = base.une_ligne(
            "SELECT preparee_le FROM journee WHERE sejour_id = ? AND date_jour = ? "
            "AND supprime = 0",
            (sejour_id, demain),
        )
        prete = bool(journee and journee["preparee_le"])
        if not prete:
            a_preparer.append(f"Lit {lit['lit']} · {nom}")

        derniers = bilans_service.dernieres_variations(
            base, sejour_id, ["crp", "creat", "hb"]
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
            return f"{_format_valeur(v.valeur)}{fleche}{marque}"

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
    if sejours_service.allergies_du_patient(base, lit_info["patient_id"]):
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


# --------------------------------------------------------------------------
# Écran 2 — Admission
# --------------------------------------------------------------------------

def ecran_nouvelle_admission(lit: int | None) -> None:
    st.divider()
    st.header(f"Nouvelle admission — Lit {lit}")
    with st.form("nouvelle_admission"):
        col1, col2 = st.columns(2)
        with col1:
            non_identifie = st.checkbox("Patient non identifié")
            matricule = (
                sejours_service.prochain_matricule_non_identifie(base)
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
            poids_kg = _nombre_saisi(
                c_poids.text_input("Poids (kg)", value="", placeholder="ex. 70")
            )
            taille_cm = _nombre_saisi(
                c_taille.text_input("Taille (cm)", value="", placeholder="ex. 175")
            )
            creatinine_base = _nombre_saisi(
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
        if not _controle(
            "admission",
            coherence.verifier_sejour(
                date_admission=date_admission, date_naissance=date_naissance
            ),
        ):
            return
        pid = sejours_service.creer_patient(
            base,
            matricule=matricule,
            nom_affichage=nom_affichage or "Non identifié",
            date_naissance=str(date_naissance) if date_naissance else None,
            sexe=sexe,
            groupe_sanguin=groupe_sanguin,
            non_identifie=non_identifie,
            utilisateur_id=utilisateur_id,
        )
        sid = sejours_service.creer_sejour(
            base,
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
            utilisateur_id=utilisateur_id,
        )
        if traumatique and regions_choisies:
            sejours_service.definir_regions_traumatiques(base, sid, regions_choisies, utilisateur_id=utilisateur_id)
        if not traumatique and motif_principal:
            sejours_service.definir_motifs(
                base, sid, motif_principal=motif_principal, motifs_associes=motifs_associes,
                utilisateur_id=utilisateur_id,
            )
        st.session_state.pop("mode", None)
        st.session_state.pop("lit_admission_choisi", None)
        st.session_state["sejour_id"] = sid
        st.session_state.pop("ecran", None)
        st.success("Séjour créé.")
        st.rerun()


# --------------------------------------------------------------------------
# Fiche patient — Identité, Prescrit, Évolution, Sortie
# --------------------------------------------------------------------------

def _ligne_poids(sejour: dict) -> str:
    """Poids réel et poids idéal côte à côte : le réel entre dans la
    clairance, l'idéal sert de référence."""
    if not sejour.get("poids_kg"):
        return (
            "<span style='color:#B4442E'>Poids non renseigné — "
            "clairance incalculable</span>"
        )
    texte = f"Poids {_format_valeur(sejour['poids_kg'])} kg"
    if sejour.get("taille_cm"):
        texte += f" · {_format_valeur(sejour['taille_cm'])} cm"
    ideal = calculs.poids_ideal_devine(
        taille_cm=sejour.get("taille_cm"), sexe=sejour.get("sexe")
    )
    if ideal.disponible:
        texte += (
            f" · <span style='color:#5B6470'>poids idéal "
            f"{_format_valeur(ideal.valeur)} kg</span>"
        )
    return texte


def onglet_identite(sejour: dict) -> None:
    age = age_ans(sejour.get("date_naissance"))
    c_identite, c_motif, c_antecedents = st.columns(3)

    with c_identite:
        theme.bloc(
            "Identité",
            [
                f"<b>{sejour['nom_affichage']}</b>",
                f"Matricule {sejour['matricule']}",
                f"{age if age is not None else '?'} ans · {listes.libelle(listes.SEXES, sejour.get('sexe'))}"
                + (f" · groupe {sejour['groupe_sanguin']}"
                   if sejour.get("groupe_sanguin") else ""),
                f"Lit {sejour['lit_admission']} · admis le {format_date_fr(sejour['date_admission'][:10])}",
                f"Provenance : {listes.libelle(listes.PROVENANCES, sejour['provenance_type'], 'non renseignée')}",
                _ligne_poids(sejour),
            ],
            theme.BLEU,
        )

    with c_motif:
        if sejour["traumatique"]:
            regions = sejours_service.regions_traumatiques(base, sejour["id"])
            elements = [listes.libelle(listes.REGIONS_TRAUMATIQUES, r) for r in regions] or [
                "Régions non précisées"
            ]
            if sejours_service.est_polytraumatise(base, sejour["id"]):
                elements.insert(0, "<b>Polytraumatisé</b> (calculé)")
            if sejour["mecanisme"]:
                elements.append(
                    f"Mécanisme : {listes.libelle(listes.MECANISMES, sejour['mecanisme'])}"
                )
            theme.bloc("Motif traumatique", elements, theme.ORANGE)
        else:
            motifs = sejours_service.motifs_du_sejour(base, sejour["id"])
            principal = next((m for m in motifs if m["principal"]), None)
            associes = [m for m in motifs if not m["principal"]]
            elements = []
            if principal:
                elements.append(f"<b>{listes.libelle_motif(principal['code'])}</b>")
            elements += [listes.libelle_motif(m["code"]) for m in associes]
            theme.bloc("Motif d'admission", elements or ["Non renseigné"], theme.ORANGE)

    antecedents = sejours_service.antecedents_du_patient(base, sejour["patient_id"])
    allergies = [a for a in antecedents if a["categorie"] == "allergie"]
    with c_antecedents:
        if allergies:
            theme.bloc(
                "Allergies",
                [f"<b>{a['libelle']}</b>" for a in allergies],
                theme.ROUGE,
            )
        theme.bloc(
            "Antécédents",
            [
                f"{a['libelle']}"
                + (f" — {a['precision']}" if a["precision"] else "")
                for a in antecedents if a["categorie"] != "allergie"
            ] or ["Aucun antécédent enregistré"],
            theme.GRIS,
        )

    _codage_cim10(sejour)
    _corriger_admission(sejour)

    with st.form("ajout_antecedent"):
        col1, col2 = st.columns(2)
        with col1:
            code_court = st.selectbox(
                "Antécédent",
                ["— Autre / recherche libre —"] + [c for c, _l, _cat in listes.ANTECEDENTS_COURTS],
                format_func=lambda c: c if c == "— Autre / recherche libre —" else listes.libelle(
                    [(cc, ll) for cc, ll, _ in listes.ANTECEDENTS_COURTS], c
                ),
            )
            libelle_libre = st.text_input("Libellé (si recherche libre)") if code_court == "— Autre / recherche libre —" else ""
        with col2:
            categorie = st.selectbox(
                "Catégorie", listes.codes(listes.CATEGORIES_ANTECEDENT),
                format_func=lambda c: listes.libelle(listes.CATEGORIES_ANTECEDENT, c),
            )
            precision = st.text_input("Précision (facultatif)")
        if st.form_submit_button("Ajouter l'antécédent"):
            if code_court != "— Autre / recherche libre —":
                libelle_txt = listes.libelle([(c, l) for c, l, _ in listes.ANTECEDENTS_COURTS], code_court)
                categorie_auto = next(cat for c, _l, cat in listes.ANTECEDENTS_COURTS if c == code_court)
                sejours_service.ajouter_antecedent(
                    base, patient_id=sejour["patient_id"], categorie=categorie_auto,
                    libelle=libelle_txt, code=code_court, precision=precision or None,
                    utilisateur_id=utilisateur_id,
                )
            elif libelle_libre:
                sejours_service.ajouter_antecedent(
                    base, patient_id=sejour["patient_id"], categorie=categorie,
                    libelle=libelle_libre, precision=precision or None, utilisateur_id=utilisateur_id,
                )
            st.rerun()


def _corriger_admission(sejour: dict) -> None:
    """Corrige une erreur de saisie faite à l'admission.

    Ce n'est pas un nouveau séjour : les mêmes lignes sont mises à jour, avec
    trace dans le journal de qui a corrigé et quand (règle de conception 2 —
    jamais de suppression physique). Le lit n'est pas modifiable ici : changer
    de lit est un transfert, une autre opération, avec d'autres contrôles.

    Fermé par défaut et sans enregistrement automatique : une correction est
    un geste délibéré, pas quelque chose qui doit pouvoir arriver par mégarde
    en survolant le formulaire.
    """
    with st.expander("✏️ Corriger l'admission"):
        st.caption(
            "Pour une erreur de saisie — matricule, nom, date, poids, motif "
            "coché du mauvais côté. Le lit ne se change pas ici."
        )
        with st.form(f"correction_{sejour['id']}"):
            col1, col2 = st.columns(2)
            with col1:
                matricule = st.text_input("Matricule", value=sejour.get("matricule") or "")
                nom_affichage = st.text_input(
                    "Nom affiché", value=sejour.get("nom_affichage") or ""
                )
                date_naissance = st.date_input(
                    "Date de naissance",
                    value=parse_date(sejour.get("date_naissance")),
                    min_value=date(1900, 1, 1), max_value=date.today(),
                )
                c_sexe, c_groupe = st.columns(2)
                sexe = c_sexe.selectbox(
                    "Sexe", listes.codes(listes.SEXES),
                    index=listes.codes(listes.SEXES).index(sejour.get("sexe") or "non_renseigne"),
                    format_func=lambda c: listes.libelle(listes.SEXES, c),
                )
                groupes = referentiels.charger("groupes_sanguins")
                codes_groupes = listes.codes(groupes)
                groupe_sanguin = c_groupe.selectbox(
                    "Groupe sanguin", codes_groupes,
                    index=codes_groupes.index(sejour.get("groupe_sanguin") or "non_renseigne"),
                    format_func=lambda c: listes.libelle(groupes, c),
                )
                c_poids, c_taille = st.columns(2)
                poids_kg = _nombre_saisi(c_poids.text_input(
                    "Poids (kg)", value=_valeur_texte(sejour.get("poids_kg"))
                ))
                taille_cm = _nombre_saisi(c_taille.text_input(
                    "Taille (cm)", value=_valeur_texte(sejour.get("taille_cm"))
                ))
                creatinine_base = _nombre_saisi(st.text_input(
                    "Créatinine antérieure (µmol/L)",
                    value=_valeur_texte(sejour.get("creatinine_base")),
                ))
            with col2:
                date_admission = st.date_input(
                    "Date d'admission",
                    value=parse_date(sejour["date_admission"]) or date.today(),
                )
                provenance_type = st.selectbox(
                    "Provenance", listes.codes(listes.PROVENANCES),
                    index=listes.codes(listes.PROVENANCES).index(sejour.get("provenance_type"))
                          if sejour.get("provenance_type") in listes.codes(listes.PROVENANCES) else 0,
                    format_func=lambda c: listes.libelle(listes.PROVENANCES, c),
                )
                provenance_detail = st.text_input(
                    "Préciser la provenance", value=sejour.get("provenance_detail") or ""
                )
                types_admission = referentiels.charger("types_admission")
                codes_types = listes.codes(types_admission)
                type_admission = st.selectbox(
                    "Type d'admission (IGS II)", codes_types,
                    index=codes_types.index(sejour.get("type_admission"))
                          if sejour.get("type_admission") in codes_types else 0,
                    format_func=lambda c: listes.libelle(types_admission, c),
                )
                maladies = referentiels.charger("maladies_chroniques_igs2")
                codes_maladies = listes.codes(maladies)
                maladie_chronique_igs2 = st.selectbox(
                    "Maladie chronique (IGS II)", codes_maladies,
                    index=codes_maladies.index(sejour.get("maladie_chronique_igs2"))
                          if sejour.get("maladie_chronique_igs2") in codes_maladies else 0,
                    format_func=lambda c: listes.libelle(maladies, c),
                )

            st.markdown("**Motif d'admission**")
            traumatique = st.radio(
                "Type", ["Traumatique", "Non traumatique"], horizontal=True,
                index=0 if sejour.get("traumatique") else 1,
                key=f"corr_type_{sejour['id']}",
            ) == "Traumatique"

            regions_choisies: list[str] = []
            mecanisme = None
            motif_principal = None
            motifs_associes: list[str] = []
            if traumatique:
                regions_actuelles = sejours_service.regions_traumatiques(base, sejour["id"])
                regions_choisies = st.multiselect(
                    "Régions atteintes", listes.codes(listes.REGIONS_TRAUMATIQUES),
                    default=[r for r in regions_actuelles if r in listes.codes(listes.REGIONS_TRAUMATIQUES)],
                    format_func=lambda c: listes.libelle(listes.REGIONS_TRAUMATIQUES, c),
                )
                codes_mecanismes = listes.codes(listes.MECANISMES)
                mecanisme = st.selectbox(
                    "Mécanisme", codes_mecanismes,
                    index=codes_mecanismes.index(sejour.get("mecanisme"))
                          if sejour.get("mecanisme") in codes_mecanismes else 0,
                    format_func=lambda c: listes.libelle(listes.MECANISMES, c),
                )
            else:
                motifs_actuels = sejours_service.motifs_du_sejour(base, sejour["id"])
                principal_actuel = next((m["code"] for m in motifs_actuels if m["principal"]), None)
                tous_motifs = listes.motifs_a_plat()
                codes_motifs = [c for c, _l, _g in tous_motifs]
                motif_principal = st.selectbox(
                    "Motif principal", codes_motifs,
                    index=codes_motifs.index(principal_actuel) if principal_actuel in codes_motifs else 0,
                    format_func=lambda c: f"{listes.libelle_motif(c)} "
                                          f"({next(g for cc,_l,g in tous_motifs if cc==c)})",
                )
                motifs_associes = st.multiselect(
                    "Motifs associés",
                    [c for c in codes_motifs if c != motif_principal],
                    default=[m["code"] for m in motifs_actuels
                            if not m["principal"] and m["code"] in codes_motifs and m["code"] != motif_principal],
                    format_func=listes.libelle_motif,
                )

            if st.form_submit_button("Enregistrer les corrections", type="primary"):
                if not _controle(
                    f"correction_{sejour['id']}",
                    coherence.verifier_sejour(
                        date_admission=date_admission, date_naissance=date_naissance
                    ),
                ):
                    return
                sejours_service.modifier_identite(
                    base, sejour["patient_id"], matricule=matricule,
                    nom_affichage=nom_affichage or "Non identifié",
                    date_naissance=str(date_naissance) if date_naissance else None,
                    sexe=sexe, groupe_sanguin=groupe_sanguin,
                    utilisateur_id=utilisateur_id,
                )
                sejours_service.modifier_admission(
                    base, sejour["id"],
                    date_admission=datetime.combine(date_admission, datetime.min.time()).isoformat(),
                    provenance_type=provenance_type, provenance_detail=provenance_detail or None,
                    poids_kg=poids_kg, taille_cm=taille_cm, creatinine_base=creatinine_base,
                    type_admission=type_admission, maladie_chronique_igs2=maladie_chronique_igs2,
                    traumatique=traumatique,
                    regions_traumatiques_choisies=regions_choisies, mecanisme=mecanisme,
                    motif_principal=motif_principal, motifs_associes=motifs_associes,
                    utilisateur_id=utilisateur_id,
                )
                st.success("Admission corrigée.")
                st.rerun()


def _valeur_texte(valeur) -> str:
    if valeur is None:
        return ""
    return str(valeur).replace(".", ",") if isinstance(valeur, float) else str(valeur)


def _codage_cim10(sejour: dict) -> None:
    """Codage CIM-10 du diagnostic principal (bloc 12).

    Le code est saisi une fois, à froid, et sert ensuite à toutes les
    extractions : sans lui, chaque étude recommence le codage à la main sur
    des libellés libres, et deux études du même service ne comptent pas les
    mêmes patients.
    """
    actuel = sejour.get("code_icd10")
    with st.expander(
        f"🔖 Codage CIM-10 — {actuel or 'non codé'}", expanded=not actuel
    ):
        if actuel:
            libelle_actuel = listes.libelle(referentiels.charger("cim10"), actuel)
            st.markdown(f"**{actuel}** — {libelle_actuel}")
        requete = st.text_input(
            "Rechercher un code ou un libellé",
            placeholder="ex. « pneumo », « J18 », « traumatique »",
            key=f"cim_{sejour['id']}",
        )
        resultats = referentiels.rechercher("cim10", requete) if requete else ()
        if requete and not resultats:
            st.caption(
                "Aucun code trouvé. La liste livrée est un sous-ensemble de "
                "démarrage : compléter `referentiels/cim10.json` avec le code "
                "manquant, relevé sur le volume officiel."
            )
        for code, libelle_code in resultats:
            colonne_texte, colonne_bouton = st.columns([5, 1])
            colonne_texte.markdown(
                f"<span style='color:{theme.BLEU};font-weight:600'>{code}</span> "
                f"{libelle_code}", unsafe_allow_html=True,
            )
            if colonne_bouton.button("Choisir", key=f"cim_{sejour['id']}_{code}",
                                     use_container_width=True):
                sejours_service.definir_code_icd10(
                    base, sejour["id"], code, utilisateur_id=utilisateur_id
                )
                st.rerun()
        st.caption(
            f"Référentiel CIM-10 version {referentiels.version('cim10')} — "
            "sous-ensemble partiel, chaque code est à vérifier sur le volume "
            "officiel avant usage statistique."
        )


def onglet_prescrit(sejour: dict) -> None:
    date_jour = st.date_input("Jour affiché", value=date.today(), key="date_prescrit")
    date_jour_str = str(date_jour)

    pancarte = prescriptions_service.pancarte_du_jour(base, sejour["id"], date_jour_str)

    voies_remplies = [
        v for v in listes.ORDRE_VOIES if pancarte["lignes_par_voie"].get(v)
    ]
    zone_pancarte, zone_actions = st.columns([2.3, 1])

    with zone_actions:
        st.metric("Entrées calculées / 24 h", f"{pancarte['bilan_entrees'].total_ml:.0f} mL")
        if st.button("📅 Préparer la pancarte de demain", use_container_width=True):
            prescriptions_service.preparer_pancarte_de_demain(
                base, sejour["id"], aujourdhui=date_jour_str, utilisateur_id=utilisateur_id
            )
            st.success("Journée de demain préparée.")
        if st.button("🖨 Imprimer la pancarte de ce jour", use_container_width=True):
            snap = pancarte_service.imprimer(
                base, sejour["id"], date_jour_str, utilisateur_id=utilisateur_id
            )
            st.session_state["derniere_impression"] = snap["html"]
            st.session_state["nom_impression"] = (
                f"feuille-lit{sejour['lit_admission']}-{date_jour_str}.html"
            )
            st.success(f"Feuille enregistrée — version {snap['version']}.")
        demandes = pancarte["bilans_demandes"]
        theme.bloc(
            "Bilans demandés",
            [
                f"{listes.libelle(listes.EXAMENS_A_DEMANDER, b['examen_code'])} "
                f"<span style='color:{theme.GRIS}'>{b['heure_prelevement']}</span>"
                for b in demandes
            ] or ["Aucun bilan demandé"],
            theme.VIOLET if demandes else theme.GRIS,
        )

    with zone_pancarte:
        gauche, droite = st.columns(2)
        _afficher_pancarte(voies_remplies, pancarte, date_jour_str, gauche, droite)

    _actions_prescrit(sejour, pancarte, date_jour_str)


def _historique_fiches(sejour: dict) -> None:
    """Retrouver une fiche imprimée un autre jour.

    Chaque impression est un instantané figé (`pancarte_snapshot`) : le
    revoir montre la fiche telle qu'elle est sortie ce jour-là, même si le
    dossier a changé depuis — c'est la seule lecture fidèle d'un historique
    médico-légal.
    """
    snapshots = pancarte_service.snapshots_du_sejour(base, sejour["id"])
    if not snapshots:
        return
    with st.expander(f"📜 Anciennes fiches imprimées ({len(snapshots)})"):
        options = [s["id"] for s in snapshots]
        choix = st.selectbox(
            "Jour", options,
            format_func=lambda sid: next(
                f"{format_date_fr(s['date_jour'])} — v{s['version']}"
                + (f", imprimée {s['imprime_le'][11:16]}" if s.get("imprime_le") else "")
                for s in snapshots if s["id"] == sid
            ),
            key=f"hist_fiche_{sejour['id']}",
        )
        ancienne = pancarte_service.snapshot(base, choix)
        if not ancienne:
            st.caption("Fiche introuvable — a-t-elle été purgée ?")
            return
        st.caption(
            f"Imprimée le {format_date_fr(ancienne['date_jour'])}"
            + (f" par {ancienne['imprime_par_nom']}" if ancienne.get("imprime_par_nom") else "")
        )
        st.download_button(
            "⬇ Télécharger cette version",
            data=ancienne["html"],
            file_name=f"feuille-lit{sejour['lit_admission']}-{ancienne['date_jour']}"
                      f"-v{ancienne['version']}.html",
            mime="text/html",
            key=f"dl_hist_{choix}",
        )
        st.components.v1.html(ancienne["html"], height=700, scrolling=True)

def _afficher_pancarte(voies_remplies, pancarte, date_jour_str, gauche, droite) -> None:
    for i, code_voie in enumerate(voies_remplies):
        lignes = pancarte["lignes_par_voie"][code_voie]
        colonne = gauche if i % 2 == 0 else droite
        with colonne:
            elements = []
            for ligne in lignes:
                texte = dom.libelle_ligne(ligne, date_jour_str)
                etiquette = dom.etiquette_jour(ligne, date_jour_str)
                # Le compteur de jours en bleu, le dernier jour en rouge :
                # ce sont les deux choses qu'on cherche du regard.
                if etiquette.dernier_jour:
                    texte = texte.replace(
                        "  ← dernier jour", ' <span class="rea-fin">← dernier jour</span>'
                    )
                texte = texte.replace(
                    etiquette.texte, f'<span class="rea-j">{etiquette.texte}</span>', 1
                )
                classe = ' class="arretee"' if ligne["statut"] == "arretee" else ""
                elements.append(f"<span{classe}>{texte}</span>")
            theme.bloc(
                listes.VOIES[code_voie]["titre"], elements,
                theme.COULEUR_VOIE.get(code_voie, theme.GRIS),
            )

def _actions_prescrit(sejour: dict, pancarte: dict, date_jour_str: str) -> None:
    with st.expander("⏹ Arrêter une ligne"):
        actives = [l for l in pancarte["lignes"] if l["statut"] == "active"]
        if not actives:
            st.caption("Aucune ligne active.")
        for ligne in actives:
            col1, col2 = st.columns([6, 1])
            col1.write(dom.libelle_ligne(ligne, date_jour_str))
            if col2.button("Arrêter", key=f"arret_{ligne['id']}", use_container_width=True):
                prescriptions_service.arreter_ligne(
                    base, ligne["id"], date_arret=date_jour_str, utilisateur_id=utilisateur_id
                )
                st.rerun()

    with st.expander("➕ Ajouter une ligne"):
        voie = st.selectbox("Voie", listes.ORDRE_VOIES, format_func=lambda c: listes.VOIES[c]["titre"])
        champs = listes.VOIES[voie]["champs"]
        with st.form(f"ajout_ligne_{voie}"):
            produit = st.text_input("Produit / libellé")
            dose = unite = rythme = condition = None
            dilution = None
            nb_ampoules = vitesse = volume_dilution = volume_24h = None
            additifs = None
            sous_type = None
            duree_prevue = None

            if "dose" in champs:
                c1, c2 = st.columns(2)
                dose = c1.number_input("Dose", min_value=0.0, step=1.0, value=0.0)
                unite = c2.selectbox("Unité", listes.UNITES)
            if "rythme" in champs:
                rythme = st.selectbox("Rythme", listes.codes(listes.RYTHMES), format_func=lambda c: listes.libelle(listes.RYTHMES, c))
            if "condition" in champs:
                condition = st.text_input("Condition (si conditionnel)")
            if "dilution" in champs:
                dilution = st.text_input("Dilution (ex. 0,5 mg/cc)")
            if "nb_ampoules" in champs:
                # PO se compte en comprimés, les autres voies en ampoules — le
                # mot change, la valeur reste un nombre saisi par le médecin,
                # jamais déduit du dosage (SPEC §3.1).
                etiquette_unites = "Nombre de comprimés" if voie == "PO" else "Nombre d'ampoules"
                nb_ampoules = st.number_input(etiquette_unites, min_value=0.0, step=1.0, value=0.0)
            if "vitesse" in champs:
                vitesse = st.number_input("Vitesse (cc/h)", min_value=0.0, step=1.0, value=0.0)
            if "volume_dilution" in champs:
                volume_dilution = st.number_input("Volume de dilution (mL/prise)", min_value=0.0, step=10.0, value=0.0)
            if "additifs" in champs:
                additifs = st.text_input("Additifs (ex. + 3 KCl + 2 NaCl)")
            if "sous_type" in champs:
                sous_type = st.selectbox("Type", listes.codes(listes.SOUS_TYPES_ENTREES), format_func=lambda c: listes.libelle(listes.SOUS_TYPES_ENTREES, c))
            if "volume_24h" in champs:
                volume_24h = st.number_input("Volume /24 h (mL)", min_value=0.0, step=50.0, value=0.0)
            if voie in ("IV", "PSE"):
                duree_prevue = st.number_input("Durée prévue (jours, si antibiotique)", min_value=0, step=1, value=0)

            date_debut = st.date_input(
                "Date de début", value=date.fromisoformat(date_jour_str), key=f"debut_{voie}"
            )

            if st.form_submit_button("Ajouter à la pancarte"):
                if not produit:
                    st.error("Le produit est obligatoire.")
                elif _controle(
                    f"ligne_{voie}",
                    coherence.verifier_prescription(
                        date_debut=date_debut,
                        duree_prevue_jours=int(duree_prevue) if duree_prevue else None,
                        dose=dose or None, vitesse=vitesse or None,
                        volume_24h=volume_24h or None,
                        date_admission=sejour["date_admission"],
                    ),
                ):
                    prescriptions_service.ajouter_ligne(
                        base, sejour_id=sejour["id"], voie=voie, produit=produit,
                        date_debut=str(date_debut),
                        dose=dose or None, unite=unite, rythme=rythme,
                        condition_texte=condition or None, dilution=dilution or None,
                        nb_ampoules=nb_ampoules or None, vitesse=vitesse or None,
                        volume_dilution=volume_dilution or None, volume_24h=volume_24h or None,
                        additifs=additifs or None, sous_type=sous_type,
                        duree_prevue_jours=int(duree_prevue) if duree_prevue else None,
                        utilisateur_id=utilisateur_id,
                    )
                    st.rerun()

    with st.expander("🧪 Bilans à demander pour le lendemain"):
        demain = date_jour_str
        journee_bilans = prescriptions_service.pancarte_du_jour(base, sejour["id"], demain)["bilans_demandes"]
        deja_coches = {b["examen_code"] for b in journee_bilans}
        with st.form("bilans_demandes"):
            choisis = st.multiselect(
                "Examens", listes.codes(listes.EXAMENS_A_DEMANDER),
                default=list(deja_coches),
                format_func=lambda c: listes.libelle(listes.EXAMENS_A_DEMANDER, c),
            )
            heure = st.text_input("Heure de prélèvement", value=config.HEURE_PRELEVEMENT_DEFAUT)
            if st.form_submit_button("Enregistrer les bilans"):
                prescriptions_service.definir_bilans_demandes(
                    base, sejour["id"], demain, [(c, heure) for c in choisis],
                    utilisateur_id=utilisateur_id,
                )
                st.rerun()

    if st.session_state.get("derniere_impression"):
        # La feuille est en A3 paysage : l'aperçu dans un cadre étroit ne
        # remplace pas une impression. Le téléchargement ouvre la feuille dans
        # un vrai onglet, où Ctrl+P sort la bonne page.
        st.download_button(
            "⬇ Ouvrir la feuille pour l'imprimer (A3 paysage)",
            data=st.session_state["derniere_impression"],
            file_name=st.session_state.get("nom_impression", "feuille.html"),
            mime="text/html",
            use_container_width=True,
        )
        st.caption(
            "Ouvrir le fichier téléchargé, puis imprimer : A3, paysage, "
            "marges nulles, sans mise à l'échelle."
        )
        with st.expander("Aperçu de la dernière impression"):
            st.components.v1.html(
                st.session_state["derniere_impression"], height=900, scrolling=True
            )

    _historique_fiches(sejour)


def _champ_element(cle: str, libelle: str, unite: str, type_: str, plage: str,
                   valeur_actuelle, prefixe: str):
    """Un élément fixe d'un plan. Même principe que les bilans : champ vide,
    plage normale en gris, et l'unité dans le libellé."""
    etiquette = f"{libelle} ({unite})" if unite else libelle
    cle_widget = f"{prefixe}_{cle}"
    if type_ == "nombre":
        return _nombre_saisi(
            st.text_input(
                etiquette,
                value="" if valeur_actuelle is None else str(valeur_actuelle).replace(".", ","),
                placeholder=plage,
                key=cle_widget,
            )
        )
    if type_ == "liste_pupilles":
        options = ["", *listes.codes(listes.PUPILLES)]
        index = options.index(valeur_actuelle) if valeur_actuelle in options else 0
        return st.selectbox(
            etiquette, options, index=index, key=cle_widget,
            format_func=lambda c: "—" if not c else listes.libelle(listes.PUPILLES, c),
        ) or None
    if type_ == "oui_non":
        options = listes.codes(listes.OUI_NON)
        index = options.index(valeur_actuelle) if valeur_actuelle in options else 0
        return st.selectbox(
            etiquette, options, index=index, key=cle_widget,
            format_func=lambda c: listes.libelle(listes.OUI_NON, c),
        )
    options = listes.codes(listes.TROIS_ETATS_PRESENCE)
    index = options.index(valeur_actuelle) if valeur_actuelle in options else 0
    return st.selectbox(
        etiquette, options, index=index, key=cle_widget,
        format_func=lambda c: listes.libelle(listes.TROIS_ETATS_PRESENCE, c),
    )


_STYLE_ETAT = {
    "ok": ("✅", theme.VERT),
    "a_verifier": ("⬜", theme.ORANGE),
    "non_renseigne": ("·", theme.GRIS),
}
_STYLE_GRAVITE = {
    "alerte": theme.ROUGE,
    "attention": theme.ORANGE,
    "info": theme.BLEU,
}


def panneau_aides(sejour: dict, date_jour_str: str) -> None:
    """Check-list du jour et rappels — des questions, jamais des consignes.

    Le logiciel coche ce qu'il sait lire de ce qui est déjà saisi, laisse
    « non renseigné » ce qu'il ne sait pas, et ne prescrit rien.
    """
    items = aides_service.checklist(base, sejour["id"], date_jour_str)
    rappels = aides_service.rappels(base, sejour["id"], date_jour_str)
    if not items and not rappels:
        return

    gauche, droite = st.columns([1.1, 1], gap="large")
    with gauche:
        if items:
            lignes = []
            for i in items:
                marque, couleur = _STYLE_ETAT.get(i.etat, ("·", theme.GRIS))
                titre = f"<b>{i.lettre}</b> · {i.libelle}"
                question = (
                    f"<br><span style='color:#94a3b8'>{i.question}</span>"
                    if i.etat != "ok" and i.question else ""
                )
                lignes.append(
                    f"<span style='color:{couleur}'>{marque}</span> {titre}{question}"
                )
            reste = sum(1 for i in items if i.etat != "ok")
            theme.bloc_html(
                f"Check-list du jour — {len(items) - reste}/{len(items)}",
                "<br>".join(lignes),
                theme.VERT if reste == 0 else theme.ORANGE,
            )
    with droite:
        if rappels:
            for r in rappels:
                note = "" if r["valide"] else (
                    "<br><span style='color:#94a3b8;font-size:0.78rem'>"
                    "Règle de service non encore signée par un senior.</span>"
                )
                theme.bloc_html(
                    r["libelle"], r["message"] + note,
                    _STYLE_GRAVITE.get(r["gravite"], theme.GRIS),
                )
        else:
            theme.bloc_html(
                "Rappels", "Aucun rappel déclenché aujourd'hui.", theme.VERT
            )
    st.caption(
        "Ces rappels sont déclaratifs : leurs seuils se modifient dans "
        "`regles/*.json`, sans reprogrammer le logiciel. Aucun ne propose de "
        "posologie (SPEC §3.1)."
    )
    panneau_scores(sejour, date_jour_str)


def _bloc_score(score, complement: str = "") -> None:
    if score.complet:
        manque = ""
    else:
        # La liste complète noierait le chiffre : on annonce combien il manque
        # et on donne les premières, le détail restant lisible au survol.
        debut = ", ".join(score.manquantes[:3])
        reste = len(score.manquantes) - 3
        manque = (
            "<br><span style='color:#94a3b8;font-size:0.78rem' title='"
            + "; ".join(score.manquantes)
            + f"'>Incomplet — {len(score.manquantes)} variables manquantes : {debut}"
            + (f" et {reste} autres" if reste > 0 else "")
            + "</span>"
        )
    non_valide = (
        "" if score.valide
        else "<br><span style='color:#94a3b8;font-size:0.78rem'>Barème non encore "
             "relu par un senior contre la publication.</span>"
    )
    theme.bloc_html(
        score.libelle,
        f"<span style='font-size:1.6rem;font-weight:600'>{score.total}</span>"
        f"{complement}{manque}{non_valide}",
        theme.BLEU if score.complet else theme.GRIS,
    )


def panneau_scores(sejour: dict, date_jour_str: str) -> None:
    """SOFA du jour, IGS II d'admission, jours sans ventilation.

    Un score décrit, il ne décide pas — et un score incomplet le dit.
    """
    with st.expander("📊 Scores de gravité"):
        c1, c2, c3 = st.columns(3)
        with c1:
            _bloc_score(scores_service.sofa(base, sejour["id"], date_jour_str))
            st.caption(
                "Composante circulatoire limitée à la PAM : les paliers "
                "supérieurs dépendent de la dose de vasopresseur, que le "
                "logiciel ne saisit pas."
            )
        with c2:
            score = scores_service.igs2(base, sejour["id"])
            mortalite = scores_service.mortalite_predite(base, sejour["id"])
            complement = (
                f"<br>Mortalité prédite : {mortalite * 100:.0f} %"
                if mortalite is not None else ""
            )
            _bloc_score(score, complement)
            st.caption(
                "Calculé sur les valeurs du jour d'admission ; la règle du "
                "score demande les plus défavorables des 24 premières heures."
            )
        with c3:
            jsv = scores_service.jours_sans_ventilation(base, sejour["id"])
            theme.bloc_html(
                "Jours sans ventilation (J28)",
                f"<span style='font-size:1.6rem;font-weight:600'>{jsv}</span>"
                if jsv is not None else
                "<span style='color:#94a3b8'>Pas encore calculable — "
                "période de 28 jours non écoulée.</span>",
                theme.BLEU if jsv is not None else theme.GRIS,
            )
            st.caption("Un patient décédé compte 0, quelle qu'ait été sa durée de ventilation.")

        serie = scores_service.evolution_sofa(base, sejour["id"])
        if len(serie) >= 2:
            import pandas as pd

            st.caption("SOFA jour par jour — c'est sa variation qui informe.")
            st.line_chart(
                pd.DataFrame({"SOFA": [v for _d, v in serie]},
                             index=[d for d, _v in serie]),
                height=180,
            )


def onglet_evolution(sejour: dict) -> None:
    date_jour = st.date_input("Jour", value=date.today(), key="date_evolution")
    date_jour_str = str(date_jour)
    panneau_aides(sejour, date_jour_str)
    entree = evolution_service.obtenir_ou_creer(
        base, sejour["id"], date_jour_str, utilisateur_id=utilisateur_id
    )
    elements_existants = evolution_service.elements_du_jour(
        base, sejour["id"], date_jour_str
    )

    saisie, rendu = st.columns([1.25, 1])

    with saisie:
        elements: dict = {}
        plans = list(evolution_service.PLANS)
        for rangee in (plans[:2], plans[2:]):
            colonnes = st.columns(2)
            for colonne, cle_plan in zip(colonnes, rangee):
                plan = cle_plan.replace("plan_", "")
                with colonne:
                    with st.container(border=True):
                        st.markdown(
                            f'<div class="rea-bloc-titre" style="color:{theme.BLEU}">'
                            f"{evolution_service.LIBELLES_PLANS[cle_plan]}</div>",
                            unsafe_allow_html=True,
                        )
                        # Ce que le logiciel sait déjà : affiché, jamais retapé.
                        auto = evolution_service._elements_automatiques(
                            base, sejour["id"], plan, date_jour_str
                        )
                        if auto:
                            st.caption(auto)
                        for champ in listes.ELEMENTS_PLAN.get(plan, ()):
                            cle, libelle, unite, type_, plage = champ
                            elements[cle] = _champ_element(
                                cle, libelle, unite, type_, plage,
                                elements_existants.get(cle), f"evo_{date_jour_str}",
                            )
                        texte_libre = st.text_area(
                            "Commentaire", value=entree.get(cle_plan) or "", height=80,
                            key=f"evo_libre_{date_jour_str}_{cle_plan}",
                            label_visibility="collapsed", placeholder="Commentaire libre…",
                        )
                        elements[f"__libre__{cle_plan}"] = texte_libre

        conduite = st.text_area(
            "Conduite", value=entree.get("conduite") or "", height=90,
            key=f"evo_conduite_{date_jour_str}",
        )

        if st.button("Enregistrer l'évolution", type="primary", use_container_width=True):
            mesures = {k: v for k, v in elements.items() if not k.startswith("__libre__")}
            evolution_service.enregistrer_elements(
                base, sejour["id"], date_jour_str, mesures, utilisateur_id=utilisateur_id
            )
            evolution_service.enregistrer(
                base, sejour["id"], date_jour_str,
                {
                    **{p: elements.get(f"__libre__{p}", "") for p in plans},
                    "conduite": conduite,
                },
                utilisateur_id=utilisateur_id,
            )
            st.success("Évolution enregistrée.")
            st.rerun()

        with st.expander("🩹 Escarres"):
            existantes = evolution_service.escarres(base, sejour["id"])
            for e in existantes:
                col1, col2 = st.columns([4, 1])
                etat = "guérie le " + format_date_fr(e["date_guerison"]) if e["date_guerison"] else "en cours"
                col1.markdown(
                    f"**{e['localisation']}** — grade {e['grade'] or '?'} · "
                    f"constatée le {format_date_fr(e['date_constat'])} · {etat}"
                )
                if not e["date_guerison"] and col2.button(
                    "Guérie", key=f"escarre_guerie_{e['id']}", use_container_width=True
                ):
                    evolution_service.modifier_escarre(
                        base, e["id"], {"date_guerison": date_jour_str},
                        utilisateur_id=utilisateur_id,
                    )
                    st.rerun()
            with st.form(f"ajout_escarre_{date_jour_str}"):
                c1, c2 = st.columns(2)
                localisation = c1.selectbox("Localisation", listes.LOCALISATIONS_ESCARRE)
                grade = c2.selectbox(
                    "Grade", [g for g, _l in listes.GRADES_ESCARRE],
                    format_func=lambda g: listes.libelle(listes.GRADES_ESCARRE, g),
                )
                if st.form_submit_button("Ajouter l'escarre"):
                    evolution_service.ajouter_escarre(
                        base, sejour_id=sejour["id"], localisation=localisation,
                        grade=grade, date_constat=date_jour_str,
                        utilisateur_id=utilisateur_id,
                    )
                    st.rerun()

    with rendu:
        texte = evolution_service.texte_genere(base, sejour["id"], date_jour_str)
        st.text_area("Prêt à copier dans le DMI", value=texte, height=640)


def onglet_sortie(sejour: dict) -> None:
    if sejour.get("date_sortie"):
        st.success(f"Séjour clôturé le {format_date_fr(sejour['date_sortie'])}")
        st.text_area("Compte rendu de sortie", value=sejours_service.compte_rendu_sortie(base, sejour["id"]), height=250)
        return

    with st.form("sortie_form"):
        mode_sortie = st.selectbox("Mode de sortie", listes.codes(listes.MODES_SORTIE), format_func=lambda c: listes.libelle(listes.MODES_SORTIE, c))
        destination = st.text_input("Destination (service, établissement)")
        meme_etablissement = st.checkbox("Même établissement")
        date_heure_sortie = st.text_input("Date / heure de sortie (AAAA-MM-JJTHH:MM)", value=datetime.now().isoformat(timespec="minutes"))
        complication_statut = st.selectbox(
            "Complications du séjour", listes.codes(listes.TROIS_ETATS),
            index=0,
            format_func=lambda c: listes.libelle(listes.TROIS_ETATS, c),
        )
        complication_texte = st.text_input("Préciser") if complication_statut == "presente" else ""
        ordonnance = st.text_area("Ordonnance de sortie")
        consultation = st.text_input("Consultation externe")
        if st.form_submit_button("Clôturer le séjour") and _controle(
            "sortie",
            coherence.verifier_sejour(
                date_admission=sejour["date_admission"],
                date_sortie=date_heure_sortie,
                date_naissance=sejour.get("date_naissance"),
            ),
        ):
            sejours_service.cloturer_sejour(
                base, sejour["id"], date_heure_sortie=date_heure_sortie, mode_sortie=mode_sortie,
                destination=destination or None, meme_etablissement=meme_etablissement,
                complication_statut=complication_statut, complication_texte=complication_texte or None,
                ordonnance_sortie=ordonnance or None, consultation_externe=consultation or None,
                utilisateur_id=utilisateur_id,
            )
            st.rerun()


def _nombre_saisi(texte: str | None) -> float | None:
    """Lit un nombre tapé à la main. La virgule décimale est acceptée : au lit
    du malade on tape « 9,2 », pas « 9.2 »."""
    if not texte or not texte.strip():
        return None
    try:
        return float(texte.strip().replace(",", ".").replace(" ", ""))
    except ValueError:
        return None


def _plage_normale(a) -> str:
    """Texte gris affiché dans le champ vide : la plage attendue."""
    if a.borne_basse is not None and a.borne_haute is not None:
        return f"{_format_valeur(a.borne_basse)} – {_format_valeur(a.borne_haute)}"
    if a.borne_haute is not None:
        return f"< {_format_valeur(a.borne_haute)}"
    if a.borne_basse is not None:
        return f"> {_format_valeur(a.borne_basse)}"
    return ""


def _champ_analyte(a, cle_widget: str) -> float | None:
    """Un champ de saisie : vide au départ, la plage normale en gris dedans,
    un signalement rouge sous le champ si la valeur en sort."""
    texte = st.text_input(
        f"{a.libelle} ({a.unite})" if a.unite else a.libelle,
        value="",
        placeholder=_plage_normale(a),
        key=cle_widget,
    )
    if not texte.strip():
        return None
    valeur = _nombre_saisi(texte)
    if valeur is None:
        st.markdown(
            f"<span style='color:{theme.ROUGE};font-size:.74rem'>valeur non numérique</span>",
            unsafe_allow_html=True,
        )
        return None

    # Deux niveaux, comme le veut le bloc 4 : « anormal » n'est pas
    # « impossible ». Le premier informe, le second alerte.
    impossible = coherence.verifier_bilan({a.id: valeur})
    if impossible:
        st.markdown(
            f"<span style='color:{theme.ROUGE};font-size:.74rem;font-weight:700'>"
            f"⚠ hors bornes physiologiques</span>",
            unsafe_allow_html=True,
        )
    else:
        alerte = a.hors_bornes(valeur)
        if alerte:
            fleche = "↑" if alerte == "haut" else "↓"
            st.markdown(
                f"<span style='color:{theme.ROUGE};font-size:.74rem;font-weight:600'>"
                f"{fleche} hors plage usuelle</span>",
                unsafe_allow_html=True,
            )
    return valeur


def onglet_bilans(sejour: dict) -> None:
    """Deux usages, deux ordres de lecture. Par défaut on vient saisir un
    bilan, souvent avec le DMI ouvert à côté et la fenêtre en demi-écran :
    la saisie est donc en premier, sur deux colonnes qui tiennent dans cette
    largeur. La cinétique suit."""
    saisie_bilan(sejour)

    st.divider()
    panneau_microbiologie(sejour)

    st.divider()
    vue_cinetique(sejour)

    st.subheader("Texte généré")
    date_affichee = st.date_input("Jour", value=date.today(), key="date_bilan_texte")
    texte = bilans_service.texte_genere(base, sejour["id"], str(date_affichee))
    st.text_area(
        "Prêt à coller dans l'évolution",
        value=texte or "(aucun bilan ce jour-là)",
        height=200,
    )


def panneau_microbiologie(sejour: dict) -> None:
    """Prélèvements et infections acquises (bloc 14).

    Un prélèvement dont le résultat n'est jamais revenu est ce qu'on oublie le
    plus sûrement : les prélèvements en attente sont donc affichés en premier
    et en orange, tant qu'ils ne sont pas complétés.
    """
    st.markdown("##### 🦠 Microbiologie")
    lignes = micro_service.du_sejour(base, sejour["id"])
    attente = [l for l in lignes if l["resultat"] == "en_cours"]

    gauche, droite = st.columns([1, 1.2], gap="large")
    with gauche:
        with st.form(f"micro_{sejour['id']}"):
            c1, c2 = st.columns(2)
            date_prelevement = c1.date_input("Date", value=date.today(),
                                             key="micro_date")
            type_prelevement = c2.selectbox(
                "Prélèvement", listes.codes(listes.PRELEVEMENTS),
                format_func=lambda c: listes.libelle(listes.PRELEVEMENTS, c),
            )
            if st.form_submit_button("Enregistrer le prélèvement"):
                micro_service.enregistrer(
                    base, sejour_id=sejour["id"], date_prelevement=str(date_prelevement),
                    type_prelevement=type_prelevement, utilisateur_id=utilisateur_id,
                )
                st.rerun()

        with st.expander("Déclarer une infection acquise"):
            with st.form(f"nosoco_{sejour['id']}"):
                type_infection = st.selectbox(
                    "Type", listes.codes(listes.INFECTIONS_NOSOCOMIALES),
                    format_func=lambda c: listes.libelle(listes.INFECTIONS_NOSOCOMIALES, c),
                )
                date_diagnostic = st.date_input("Date du diagnostic", value=date.today())
                germe_nosoco = st.text_input("Germe (si connu)")
                if st.form_submit_button("Déclarer"):
                    micro_service.declarer_infection_nosocomiale(
                        base, sejour_id=sejour["id"], type_=type_infection,
                        date_diagnostic=str(date_diagnostic),
                        germe=germe_nosoco or None, utilisateur_id=utilisateur_id,
                    )
                    st.rerun()
            st.caption(
                "Seules les infections diagnostiquées au moins 48 h après "
                "l'admission comptent dans les taux du service : avant, "
                "l'infection est réputée importée."
            )

    with droite:
        if attente:
            for ligne in attente:
                with st.form(f"resultat_{ligne['id']}"):
                    st.markdown(
                        f"**{listes.libelle(listes.PRELEVEMENTS, ligne['type_prelevement'])}** "
                        f"du {format_date_fr(ligne['date_prelevement'])} — en attente"
                    )
                    c1, c2 = st.columns([1, 1.4])
                    resultat = c1.selectbox(
                        "Résultat", listes.codes(listes.RESULTATS_MICROBIO),
                        format_func=lambda c: listes.libelle(listes.RESULTATS_MICROBIO, c),
                        key=f"res_{ligne['id']}",
                    )
                    germe = c2.text_input("Germe", key=f"germe_{ligne['id']}")
                    antibiogramme = st.text_area(
                        "Antibiogramme", key=f"atb_{ligne['id']}", height=70
                    )
                    if st.form_submit_button("Enregistrer le résultat"):
                        micro_service.completer(
                            base, ligne["id"],
                            {"resultat": resultat, "germe": germe or None,
                             "antibiogramme": antibiogramme or None},
                            utilisateur_id=utilisateur_id,
                        )
                        st.rerun()
        rendus = [l for l in lignes if l["resultat"] != "en_cours"]
        if rendus:
            theme.bloc(
                "Résultats rendus",
                [
                    f"{format_date_fr(l['date_prelevement'])} · "
                    f"{listes.libelle(listes.PRELEVEMENTS, l['type_prelevement'])} — "
                    f"{listes.libelle(listes.RESULTATS_MICROBIO, l['resultat'])}"
                    + (f" : {l['germe']}" if l["germe"] else "")
                    for l in rendus
                ],
                theme.VIOLET,
            )
        infections = micro_service.infections_du_sejour(base, sejour["id"])
        if infections:
            theme.bloc(
                "Infections déclarées",
                [
                    f"{format_date_fr(i['date_diagnostic'])} · "
                    f"{listes.libelle(listes.INFECTIONS_NOSOCOMIALES, i['type'])}"
                    + (f" ({i['germe']})" if i["germe"] else "")
                    + ("" if micro_service.acquise_en_reanimation(sejour, i)
                       else " — présente à l'admission, non comptée comme acquise")
                    for i in infections
                ],
                theme.ROUGE,
            )
        if not lignes and not micro_service.infections_du_sejour(base, sejour["id"]):
            st.caption("Aucun prélèvement enregistré pour ce séjour.")


def saisie_bilan(sejour: dict) -> None:
    st.markdown("##### Saisir un bilan")
    haut1, haut2 = st.columns(2)
    date_heure = haut1.text_input(
        "Date / heure du prélèvement",
        value=datetime.now().isoformat(timespec="minutes"),
        key="bilan_date_heure",
    )
    unite_lipides = haut2.radio(
        "Lipides en", ["mmol/L", "g/L"], horizontal=True, key="unite_lipides"
    )

    valeurs: dict[str, float | None] = {}

    # Deux colonnes : c'est ce qui tient dans une fenêtre en demi-écran, à
    # côté du DMI.
    for groupe in cat.GROUPES:
        st.markdown(f"**{groupe.titre}**")
        colonnes = st.columns(2)
        saisissables = [a for a in groupe.analytes if not a.calcule]
        for i, a in enumerate(saisissables):
            with colonnes[i % 2]:
                valeur = _champ_analyte(a, f"bilan_{a.id}")
                if groupe.code == "lipidique" and valeur is not None and unite_lipides == "g/L":
                    valeur = bilans_service.gl_vers_mmol(a.id, valeur)
                valeurs[a.id] = valeur

    st.markdown("**Gaz du sang & ventilation**")
    g1, g2 = st.columns(2)
    mode_vent = g1.selectbox("Mode ventilatoire", ["—", *cat.MODES_VENTILATOIRES], key="gds_mode")
    debit_o2 = _nombre_saisi(
        g2.text_input("Débit O₂ (L/min)", value="", placeholder="si masque ou lunette",
                      key="gds_debit")
    )
    gaz: dict[str, float | None] = {}
    champs_gaz = [
        ("fio2", "FiO₂ (%)", "21 – 100"), ("pep", "PEP (cmH₂O)", "0 – 20"),
        ("fr", "FR (/min)", "12 – 25"), ("spo2", "SpO₂ (%)", "≥ 94"),
        ("ph", "pH", "7,35 – 7,45"), ("pao2", "PaO₂ (mmHg)", "80 – 100"),
        ("paco2", "PaCO₂ (mmHg)", "35 – 45"), ("hco3", "HCO₃⁻ (mmol/L)", "22 – 26"),
        ("lactate", "Lactates (mmol/L)", "< 2"),
    ]
    colonnes_gaz = st.columns(2)
    for i, (cle, libelle, plage) in enumerate(champs_gaz):
        with colonnes_gaz[i % 2]:
            texte = st.text_input(libelle, value="", placeholder=plage, key=f"gds_{cle}")
            valeur = _nombre_saisi(texte)
            if texte.strip() and valeur is None:
                st.markdown(
                    f"<span style='color:{theme.ROUGE};font-size:.74rem'>valeur non numérique</span>",
                    unsafe_allow_html=True,
                )
            elif valeur is not None and coherence.verifier_gaz_du_sang({cle: valeur}):
                st.markdown(
                    f"<span style='color:{theme.ROUGE};font-size:.74rem;font-weight:700'>"
                    f"⚠ hors bornes physiologiques</span>",
                    unsafe_allow_html=True,
                )
            gaz[cle] = valeur

    # Valeurs dérivées, affichées dès que leurs ingrédients sont là.
    age = age_ans(sejour.get("date_naissance"))
    derivees = [
        v for v in calculs.toutes_les_valeurs(
            resultats=valeurs, gaz=gaz, poids_kg=sejour.get("poids_kg"),
            taille_cm=sejour.get("taille_cm"), age_ans=age, sexe=sejour.get("sexe"),
        )
        if v.disponible
    ]
    if derivees:
        theme.bloc(
            "Calculé automatiquement",
            [
                f"<b>{v.libelle}</b> : {_format_valeur(v.valeur)} {v.unite}"
                f" <span style='color:{theme.GRIS};font-size:.78rem'>— {v.formule}</span>"
                for v in derivees
            ],
            theme.BLEU,
        )
    if not sejour.get("poids_kg"):
        st.caption(
            "Poids non renseigné à l'admission : la clairance de la créatinine "
            "ne peut pas être calculée."
        )

    avertissements = (
        coherence.verifier_bilan(valeurs) + coherence.verifier_gaz_du_sang(gaz)
    )
    forcer = False
    if avertissements:
        for a in avertissements:
            st.warning(a.message)
        forcer = st.checkbox(
            "Forcer l'enregistrement malgré les avertissements",
            key="bilan_forcer",
            help="La valeur est enregistrée et marquée comme forcée, pour qu'un "
                 "relecteur puisse la retrouver.",
        )

    saisi = any(v is not None for v in valeurs.values()) or any(
        v is not None for v in gaz.values()
    ) or mode_vent != "—"

    if st.button("Enregistrer le bilan", type="primary", use_container_width=True,
                 disabled=not saisi):
        if avertissements and not forcer:
            st.error(
                "Corrigez les valeurs signalées, ou cochez « Forcer "
                "l'enregistrement » puis validez à nouveau."
            )
            return
        bilans_service.enregistrer_resultats(
            base, sejour["id"], date_heure, valeurs,
            utilisateur_id=utilisateur_id, saisie_forcee=forcer,
        )
        if mode_vent != "—" or any(v is not None for v in gaz.values()):
            bilans_service.enregistrer_gaz_du_sang(
                base, sejour["id"], date_heure,
                mode_ventilatoire=None if mode_vent == "—" else mode_vent,
                debit_o2=debit_o2, utilisateur_id=utilisateur_id, **gaz,
            )
        for cle in list(st.session_state):
            if cle.startswith(("bilan_", "gds_")) and cle != "bilan_date_heure":
                del st.session_state[cle]
        st.success("Bilan enregistré.")
        st.rerun()


def _format_valeur(valeur: float | None) -> str:
    if valeur is None:
        return "—"
    return str(int(valeur)) if float(valeur) == int(valeur) else f"{valeur:g}"


def vue_cinetique(sejour: dict) -> None:
    """Ce qu'un clinicien regarde vraiment : la dernière valeur et sa
    variation depuis la veille, puis la ligne complète à travers les jours,
    puis la courbe. Dans cet ordre."""
    presents = bilans_service.analytes_renseignes(base, sejour["id"])
    if not presents:
        st.caption("Aucun bilan enregistré pour ce séjour.")
        return

    st.subheader("Cinétique")

    panels = [(c, t, [a for a in ids if a in presents])
              for c, t, ids in bilans_service.PANELS]
    panels = [p for p in panels if p[2]]
    noms_panels = [t for _c, t, _ids in panels] + ["Tout"]
    choix_panel = st.radio(
        "Panneau", noms_panels, horizontal=True, key="panel_cinetique",
        label_visibility="collapsed",
    )
    if choix_panel == "Tout":
        ids_affiches = presents
    else:
        ids_affiches = next(ids for _c, t, ids in panels if t == choix_panel)

    # 1. Dernière valeur et variation depuis le prélèvement précédent
    variations = bilans_service.dernieres_variations(base, sejour["id"], ids_affiches)
    variations = [v for v in variations if v.valeur is not None]
    if variations:
        colonnes = st.columns(min(len(variations), 5))
        for i, v in enumerate(variations):
            with colonnes[i % len(colonnes)]:
                st.metric(
                    f"{v.libelle} ({v.unite})" if v.unite else v.libelle,
                    _format_valeur(v.valeur),
                    delta=None if v.delta in (None, 0) else _format_valeur(v.delta),
                    delta_color="off",
                )
                if v.alerte:
                    couleur = theme.ROUGE if v.alerte == "haut" else theme.BLEU
                    mot = "au-dessus" if v.alerte == "haut" else "en dessous"
                    a = cat.analyte(v.analyte)
                    borne = a.borne_haute if v.alerte == "haut" else a.borne_basse
                    st.markdown(
                        f"<span style='color:{couleur};font-size:.75rem;font-weight:600'>"
                        f"{mot} de {_format_valeur(borne)}</span>",
                        unsafe_allow_html=True,
                    )

    # 2. Le tableau analytes × dates — la lecture de fond
    dates, matrice = bilans_service.tableau_par_date(base, sejour["id"], ids_affiches)
    if dates:
        import pandas as pd

        colonnes_dates = dates[-8:]  # les huit derniers prélèvements tiennent à l'écran
        tableau = {}
        for id_analyte in ids_affiches:
            if id_analyte not in matrice:
                continue
            a = cat.analyte(id_analyte)
            etiquette = f"{a.libelle} ({a.unite})" if a.unite else a.libelle
            tableau[etiquette] = [
                _format_valeur(matrice[id_analyte].get(d)) for d in colonnes_dates
            ]
        if tableau:
            entetes = [format_date_fr(d[:10]) + (f" {d[11:16]}" if len(d) >= 16 else "")
                       for d in colonnes_dates]
            st.dataframe(
                pd.DataFrame(tableau, index=entetes).T,
                use_container_width=True,
            )
            st.caption(
                "Valeurs telles que saisies. Les bornes usuelles servant à signaler "
                "une anomalie restent à valider par un senior (question ouverte 8)."
            )

    # 3. Les courbes, une par analyte du panneau
    traçables = [i for i in ids_affiches
                 if len(bilans_service.historique_analyte(base, sejour["id"], i)) >= 2]
    if traçables:
        with st.expander("📈 Courbes", expanded=len(traçables) <= 4):
            import pandas as pd

            colonnes = st.columns(2)
            for i, id_analyte in enumerate(traçables):
                a = cat.analyte(id_analyte)
                historique = bilans_service.historique_analyte(base, sejour["id"], id_analyte)
                with colonnes[i % 2]:
                    st.caption(f"{a.libelle} ({a.unite})" if a.unite else a.libelle)
                    df = pd.DataFrame(historique)
                    df["date_heure"] = pd.to_datetime(df["date_heure"])
                    st.line_chart(df.set_index("date_heure")["valeur_num"], height=180)


# --------------------------------------------------------------------------
# Écran — Explorations et actes (SPEC §6, étendu aux dispositifs invasifs)
# --------------------------------------------------------------------------

def bandeau_etat(sejour: dict) -> None:
    """Ce qu'on doit voir avant de lire quoi que ce soit d'autre : allergie,
    jour d'hospitalisation, dispositifs en place avec leur compteur."""
    pastilles: list[tuple[str, str]] = []
    allergies = sejours_service.allergies_du_patient(base, sejour["patient_id"])
    for a in allergies:
        pastilles.append((f"Allergie : {a['libelle']}", "alerte"))
    pastilles.append(
        (f"J{jour_hospitalisation(sejour['date_admission'])} d'hospitalisation", "info")
    )
    if sejour["traumatique"] and sejours_service.est_polytraumatise(base, sejour["id"]):
        pastilles.append(("Polytraumatisé", "attention"))
    for e in dispositifs_service.etats(base, sejour["id"]):
        if e.en_place:
            style = "attention" if e.type in ("intubation", "sedation", "eer") else "neutre"
            pastilles.append((e.texte, style))
    theme.chips(pastilles)


def onglet_actes(sejour: dict) -> None:
    lignes = dispositifs_service.du_sejour(base, sejour["id"])
    etats = dispositifs_service.etats(base, sejour["id"])

    en_place = [e for e in etats if e.en_place]
    retires = [e for e in etats if not e.en_place]

    lignes_en_place = [l for l in lignes if not l["date_retrait"]]
    if not en_place:
        st.caption("Aucun dispositif en place.")
    else:
        colonnes = st.columns(3)
        for i, (etat_disp, ligne) in enumerate(zip(en_place, lignes_en_place)):
            couleur = theme.COULEUR_DISPOSITIF.get(etat_disp.type, theme.GRIS)
            with colonnes[i % 3]:
                with st.container(border=True):
                    st.markdown(
                        f'<div class="rea-bloc-titre" style="color:{couleur}">'
                        f"{etat_disp.libelle_type}</div>"
                        f'<div style="font-weight:700;font-size:.95rem">{etat_disp.texte}</div>'
                        f'<div style="color:{theme.GRIS};font-size:.78rem;margin-bottom:4px">'
                        f"posé le {format_date_fr(etat_disp.date_pose)}</div>",
                        unsafe_allow_html=True,
                    )
                    c1, c2 = st.columns([1.3, 1])
                    date_retrait = c1.date_input(
                        "Date", value=date.today(), key=f"retrait_date_{ligne['id']}",
                        label_visibility="collapsed",
                    )
                    config_type = listes.TYPES_DISPOSITIF.get(ligne["type"], {})
                    if c2.button(
                        config_type.get("verbe_retrait", "Retirer"),
                        key=f"retrait_{ligne['id']}", use_container_width=True,
                    ) and _controle(
                        f"retrait_{ligne['id']}",
                        coherence.verifier_dispositif(
                            date_pose=etat_disp.date_pose,
                            date_retrait=date_retrait,
                            date_admission=sejour["date_admission"],
                        ),
                    ):
                        dispositifs_service.retirer(
                            base, ligne["id"], date_retrait=str(date_retrait),
                            utilisateur_id=utilisateur_id,
                        )
                        st.rerun()

    if retires:
        with st.expander(f"Retirés ({len(retires)})"):
            theme.bloc(
                "Historique",
                [
                    f"{e.texte} — posé le {format_date_fr(e.date_pose)}, "
                    f"retiré le {format_date_fr(e.date_retrait)}"
                    for e in retires
                ],
                theme.GRIS,
            )

    with st.expander("➕ Poser un dispositif / noter un acte"):
        type_ = st.selectbox(
            "Type", listes.ORDRE_DISPOSITIFS, format_func=listes.libelle_dispositif,
            key="type_dispositif",
        )
        config_type = listes.TYPES_DISPOSITIF[type_]
        with st.form(f"pose_{type_}"):
            date_pose = st.date_input("Date de pose", value=date.today())
            site = None
            if config_type["sites"]:
                site = st.selectbox("Site", config_type["sites"])
            details: dict = {}
            for champ in config_type["champs"]:
                libelle_champ, _prefixe, unite = listes.CHAMPS_DISPOSITIF[champ]
                etiquette = f"{libelle_champ} ({unite})" if unite else libelle_champ
                if champ in ("molecules", "technique"):
                    details[champ] = st.text_input(etiquette)
                else:
                    details[champ] = st.number_input(etiquette, min_value=0.0, step=1.0, value=0.0)
            commentaire = st.text_input("Commentaire (facultatif)")
            if st.form_submit_button("Enregistrer") and _controle(
                f"pose_{type_}",
                coherence.verifier_dispositif(
                    date_pose=date_pose, date_admission=sejour["date_admission"]
                ),
            ):
                dispositifs_service.poser(
                    base, sejour_id=sejour["id"], type_=type_, date_pose=str(date_pose),
                    site=site, details={k: v for k, v in details.items() if v},
                    commentaire=commentaire or None, utilisateur_id=utilisateur_id,
                )
                st.rerun()

    st.divider()
    explos = explorations_service.du_sejour(base, sejour["id"])
    if not explos:
        st.caption("Aucune exploration enregistrée.")
    else:
        theme.bloc(
            "Explorations du séjour",
            [
                f"<span style='color:{theme.GRIS}'>{format_date_fr(e['date_heure'][:10])}</span> "
                f"{explorations_service.texte_exploration(base, e)[2:]}"
                for e in explos[:15]
            ],
            theme.VIOLET,
        )

    with st.expander("➕ Ajouter une exploration"):
        type_expl = st.selectbox(
            "Type d'exploration", list(listes.TYPES_EXPLORATION.keys()),
            format_func=lambda c: listes.TYPES_EXPLORATION[c]["libelle"],
            key="type_exploration",
        )
        definition = listes.TYPES_EXPLORATION[type_expl]
        with st.form(f"exploration_{type_expl}"):
            date_heure = st.text_input(
                "Date / heure", value=datetime.now().isoformat(timespec="minutes")
            )
            valeurs: dict = {}
            champs = definition["valeurs"]
            if champs:
                cols = st.columns(min(len(champs), 4))
                for i, (cle, libelle_v, unite, type_v) in enumerate(champs):
                    etiquette = f"{libelle_v} ({unite})" if unite else libelle_v
                    with cols[i % len(cols)]:
                        if type_v == "nombre":
                            valeurs[cle] = st.number_input(
                                etiquette, min_value=0.0, step=0.01, value=0.0,
                                key=f"expl_{type_expl}_{cle}",
                            )
                        elif type_v == "trois_etats":
                            valeurs[cle] = st.selectbox(
                                etiquette, ["", "Présent", "Absent", "Non renseigné"],
                                key=f"expl_{type_expl}_{cle}",
                            )
                        else:
                            valeurs[cle] = st.text_input(etiquette, key=f"expl_{type_expl}_{cle}")
            conclusion = st.text_input("Conclusion")
            operateur = st.text_input("Opérateur (facultatif)")
            if st.form_submit_button("Enregistrer l'exploration"):
                explorations_service.enregistrer(
                    base, sejour_id=sejour["id"], date_heure=date_heure, type_=type_expl,
                    valeurs={k: v for k, v in valeurs.items() if v not in (None, "", 0, 0.0)},
                    conclusion=conclusion or None, operateur=operateur or None,
                    utilisateur_id=utilisateur_id,
                )
                st.rerun()

    historisables = [
        (t, cle, lib)
        for t, d in listes.TYPES_EXPLORATION.items()
        for cle, lib, _u, tv in d["valeurs"] if tv == "nombre"
    ]
    types_presents = {e["type"] for e in explos}
    candidats = [(t, c, l) for t, c, l in historisables if t in types_presents]
    if candidats:
        with st.expander("📈 Cinétique d'une valeur d'exploration"):
            choix = st.selectbox(
                "Valeur", candidats,
                format_func=lambda x: f"{listes.TYPES_EXPLORATION[x[0]]['libelle']} — {x[2]}",
            )
            historique = explorations_service.historique_valeur(base, sejour["id"], choix[0], choix[1])
            if len(historique) >= 2:
                import pandas as pd

                df = pd.DataFrame(historique).set_index("date_heure")
                st.line_chart(df["valeur_num"])
            else:
                st.caption("Au moins deux mesures sont nécessaires pour tracer une courbe.")


def ecran_fiche(sejour_id: str) -> None:
    sejour = sejours_service.sejour_avec_patient(base, sejour_id)
    if sejour is None:
        st.session_state.pop("sejour_id", None)
        st.rerun()
        return

    st.title(f"Lit {sejour['lit_admission']} — {sejour['nom_affichage']}")
    bandeau_etat(sejour)
    onglets = st.tabs(
        ["Identité", "Prescrit", "Explorations et actes", "Bilans", "Évolution", "Sortie"]
    )
    with onglets[0]:
        onglet_identite(sejour)
    with onglets[1]:
        onglet_prescrit(sejour)
    with onglets[2]:
        onglet_actes(sejour)
    with onglets[3]:
        onglet_bilans(sejour)
    with onglets[4]:
        onglet_evolution(sejour)
    with onglets[5]:
        onglet_sortie(sejour)


# --------------------------------------------------------------------------
# Routage
# --------------------------------------------------------------------------
if st.session_state.get("ecran") == "administration":
    administration_ui.ecran(base, utilisateur_id)
elif st.session_state.get("ecran") == "recherche":
    recherche_ui.ecran(base, utilisateur_id)
elif st.session_state.get("sejour_id"):
    ecran_fiche(st.session_state["sejour_id"])
else:
    ecran_lits()
