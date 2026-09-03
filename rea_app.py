"""Point d'entrée Streamlit.

    streamlit run rea_app.py

Voir SPEC.md pour le détail des écrans. v1 minimale : Lits, Admission,
Prescrit, Sortie — le sous-ensemble qui, selon la feuille de route,
« résout déjà le problème principal du service ».
"""

from __future__ import annotations

from datetime import date, datetime

import streamlit as st

from rea import analytes as cat, config, listes
from rea.db import obtenir_base
from rea.domaine import prescription as dom
from rea.domaine.dates import age_ans, format_date_fr, jour_hospitalisation, lendemain
from rea.services import bilans as bilans_service
from rea.services import dispositifs as dispositifs_service
from rea.services import evolution as evolution_service
from rea.services import explorations as explorations_service
from rea.services import lits as lits_service
from rea.services import pancarte as pancarte_service
from rea.services import prescriptions as prescriptions_service
from rea.services import sejours as sejours_service
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
        st.rerun()
    st.caption(f"Réanimation polyvalente · {config.NB_LITS} lits")
    st.caption("SPEC.md — voir le dépôt pour l'état d'avancement")


def _aujourdhui() -> str:
    return date.today().isoformat()


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

    st.markdown("### Tableau des lits")
    c1, c2, c3, c4, c5, _vide = st.columns([1, 1, 1, 1, 1, 3])
    c1.metric("Occupés", f"{len(occupes)}/{config.NB_LITS}")
    c2.metric("Libres", config.NB_LITS - len(occupes))
    c3.metric("Occupation", f"{round(100 * len(occupes) / config.NB_LITS)} %")
    c4.metric("Intubés", intubes)
    c5.metric("Sédatés", sedates)

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
    """Ce qui demande une décision aujourd'hui, calculé depuis ce qui est
    déjà saisi : rien à ressaisir, rien à cocher."""
    aujourdhui = _aujourdhui()
    demain = str(lendemain(aujourdhui))

    echeances: list[str] = []
    dispositifs_anciens: list[str] = []
    a_preparer: list[str] = []

    for lit in occupes:
        nom = lit["nom_affichage"]
        pancarte = prescriptions_service.pancarte_du_jour(base, lit["sejour_id"], aujourdhui)
        for ligne in pancarte["lignes"]:
            if ligne["statut"] != "active":
                continue
            etiquette = dom.etiquette_jour(ligne, aujourdhui)
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

        for e in resumes.get(lit["sejour_id"], []):
            if e.en_place and e.jour >= 7 and e.type in (
                "kt_central", "kta", "sonde_urinaire", "picc", "ktsp", "intubation"
            ):
                dispositifs_anciens.append(
                    f"<b>Lit {lit['lit']} · {nom}</b> — {e.texte}"
                )

        journee = base.une_ligne(
            "SELECT preparee_le FROM journee WHERE sejour_id = ? AND date_jour = ? "
            "AND supprime = 0",
            (lit["sejour_id"], demain),
        )
        if not journee or not journee["preparee_le"]:
            a_preparer.append(f"Lit {lit['lit']} · {nom}")

    if not occupes:
        return

    g, m, d = st.columns(3)
    with g:
        theme.bloc(
            "Antibiothérapies à revoir",
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
            f"Pancartes de demain à préparer ({len(a_preparer)})",
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
            sexe = st.selectbox("Sexe", listes.codes(listes.SEXES), format_func=lambda c: listes.libelle(listes.SEXES, c))
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
        pid = sejours_service.creer_patient(
            base,
            matricule=matricule,
            nom_affichage=nom_affichage or "Non identifié",
            date_naissance=str(date_naissance) if date_naissance else None,
            sexe=sexe,
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
        st.success("Séjour créé.")
        st.rerun()


# --------------------------------------------------------------------------
# Fiche patient — Identité, Prescrit, Évolution, Sortie
# --------------------------------------------------------------------------

def onglet_identite(sejour: dict) -> None:
    age = age_ans(sejour["date_naissance"])
    c_identite, c_motif, c_antecedents = st.columns(3)

    with c_identite:
        theme.bloc(
            "Identité",
            [
                f"<b>{sejour['nom_affichage']}</b>",
                f"Matricule {sejour['matricule']}",
                f"{age if age is not None else '?'} ans · {listes.libelle(listes.SEXES, sejour['sexe'])}",
                f"Lit {sejour['lit_admission']} · admis le {format_date_fr(sejour['date_admission'][:10])}",
                f"Provenance : {listes.libelle(listes.PROVENANCES, sejour['provenance_type'], 'non renseignée')}",
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
            st.success(f"Pancarte enregistrée — version {snap['version']}.")
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
                nb_ampoules = st.number_input("Nombre d'ampoules", min_value=0.0, step=1.0, value=0.0)
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
                else:
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
        with st.expander("Aperçu de la dernière impression", expanded=True):
            st.components.v1.html(st.session_state["derniere_impression"], height=600, scrolling=True)


def onglet_evolution(sejour: dict) -> None:
    date_jour = st.date_input("Jour", value=date.today(), key="date_evolution")
    date_jour_str = str(date_jour)
    entree = evolution_service.obtenir_ou_creer(base, sejour["id"], date_jour_str, utilisateur_id=utilisateur_id)

    saisie, rendu = st.columns([1.15, 1])
    with saisie:
        with st.form("evolution_form"):
            valeurs = {}
            plans = list(evolution_service.PLANS)
            for rangee in (plans[:2], plans[2:]):
                cols = st.columns(2)
                for col, cle in zip(cols, rangee):
                    with col:
                        valeurs[cle] = st.text_area(
                            evolution_service.LIBELLES_PLANS[cle],
                            value=entree.get(cle) or "", height=110,
                        )
            valeurs["conduite"] = st.text_area(
                "Conduite", value=entree.get("conduite") or "", height=90
            )
            if st.form_submit_button("Enregistrer", use_container_width=True):
                evolution_service.enregistrer(
                    base, sejour["id"], date_jour_str, valeurs, utilisateur_id=utilisateur_id
                )
                st.rerun()
    with rendu:
        texte = evolution_service.texte_genere(base, sejour["id"], date_jour_str)
        st.text_area("Prêt à copier dans le DMI", value=texte, height=520)


def onglet_sortie(sejour: dict) -> None:
    if sejour["date_sortie"]:
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
        if st.form_submit_button("Clôturer le séjour"):
            sejours_service.cloturer_sejour(
                base, sejour["id"], date_heure_sortie=date_heure_sortie, mode_sortie=mode_sortie,
                destination=destination or None, meme_etablissement=meme_etablissement,
                complication_statut=complication_statut, complication_texte=complication_texte or None,
                ordonnance_sortie=ordonnance or None, consultation_externe=consultation or None,
                utilisateur_id=utilisateur_id,
            )
            st.rerun()


def onglet_bilans(sejour: dict) -> None:
    """Lecture d'abord, saisie ensuite : au lit du malade on consulte les
    bilans bien plus souvent qu'on n'en saisit."""
    vue_cinetique(sejour)

    st.subheader("Texte généré")
    date_affichee = st.date_input("Jour", value=date.today(), key="date_bilan_texte")
    texte = bilans_service.texte_genere(base, sejour["id"], str(date_affichee))
    st.text_area("Prêt à coller dans l'évolution", value=texte or "(aucun bilan ce jour-là)", height=200)


    with st.expander("➕ Saisir un bilan"):
        unite_lipides = st.radio(
            "Saisie des lipides en", ["mmol/L", "g/L"], horizontal=True, key="unite_lipides"
        )

        with st.form("bilans_form"):
            date_heure = st.text_input(
                "Date / heure du prélèvement", value=datetime.now().isoformat(timespec="minutes")
            )

            valeurs: dict[str, float | None] = {}

            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**NFS**")
                for a in [a for g in cat.GROUPES if g.code == "nfs" for a in g.analytes]:
                    valeurs[a.id] = st.number_input(
                        f"{a.libelle} ({a.unite})" if a.unite else a.libelle,
                        min_value=0.0, step=0.1, value=0.0, key=f"bilan_{a.id}",
                    )
            with col2:
                st.markdown("**Hémostase**")
                for a in [a for g in cat.GROUPES if g.code == "hemostase" for a in g.analytes]:
                    valeurs[a.id] = st.number_input(
                        f"{a.libelle} ({a.unite})" if a.unite else a.libelle,
                        min_value=0.0, step=0.1, value=0.0, key=f"bilan_{a.id}",
                    )

            st.markdown("**Ionogramme & rénale**")
            cols = st.columns(4)
            for i, a in enumerate(
                [a for code in ("ionogramme", "renale", "inflammation") for g in cat.GROUPES if g.code == code for a in g.analytes]
            ):
                with cols[i % 4]:
                    valeurs[a.id] = st.number_input(
                        f"{a.libelle} ({a.unite})" if a.unite else a.libelle,
                        min_value=0.0, step=0.1, value=0.0, key=f"bilan_{a.id}",
                    )

            st.markdown("**Gaz du sang & ventilation**")
            c1, c2, c3 = st.columns(3)
            mode_vent = c1.selectbox("Mode ventilatoire", ["—", *cat.MODES_VENTILATOIRES])
            debit_o2 = c2.number_input("Débit O₂ (L/min, si masque/lunette)", min_value=0.0, step=0.5, value=0.0)
            fio2 = c3.number_input("FiO₂ (%)", min_value=0.0, max_value=100.0, step=1.0, value=0.0)
            c4, c5, c6 = st.columns(3)
            pep = c4.number_input("PEP (cmH₂O)", min_value=0.0, step=1.0, value=0.0)
            fr = c5.number_input("FR (/min)", min_value=0.0, step=1.0, value=0.0)
            spo2 = c6.number_input("SpO₂ (%)", min_value=0.0, max_value=100.0, step=1.0, value=0.0)
            c7, c8, c9, c10 = st.columns(4)
            ph = c7.number_input("pH", min_value=0.0, step=0.01, value=0.0, format="%.2f")
            pao2 = c8.number_input("PaO₂ (mmHg)", min_value=0.0, step=1.0, value=0.0)
            paco2 = c9.number_input("PaCO₂ (mmHg)", min_value=0.0, step=1.0, value=0.0)
            hco3 = c10.number_input("HCO₃⁻ (mmol/L)", min_value=0.0, step=0.1, value=0.0)
            lactate = st.number_input("Lactates (mmol/L)", min_value=0.0, step=0.1, value=0.0)

            st.markdown("**Bilan hépatique**")
            cols = st.columns(4)
            for i, a in enumerate([a for g in cat.GROUPES if g.code == "hepatique" for a in g.analytes if not a.calcule]):
                with cols[i % 4]:
                    valeurs[a.id] = st.number_input(
                        f"{a.libelle} ({a.unite})" if a.unite else a.libelle,
                        min_value=0.0, step=0.1, value=0.0, key=f"bilan_{a.id}",
                    )

            st.markdown(f"**Bilan lipidique** (saisi en {unite_lipides})")
            cols = st.columns(4)
            lipides_saisis: dict[str, float | None] = {}
            for i, a in enumerate([a for g in cat.GROUPES if g.code == "lipidique" for a in g.analytes]):
                with cols[i % 4]:
                    lipides_saisis[a.id] = st.number_input(
                        a.libelle, min_value=0.0, step=0.01, value=0.0, key=f"bilan_{a.id}",
                    )

            if st.form_submit_button("Enregistrer les bilans"):
                valeurs_non_nulles = {k: (v or None) for k, v in valeurs.items()}
                for id_lipide, v in lipides_saisis.items():
                    if not v:
                        continue
                    valeurs_non_nulles[id_lipide] = (
                        v if unite_lipides == "mmol/L" else bilans_service.gl_vers_mmol(id_lipide, v)
                    )
                bilans_service.enregistrer_resultats(
                    base, sejour["id"], date_heure, valeurs_non_nulles, utilisateur_id=utilisateur_id
                )
                if mode_vent != "—" or any([fio2, pep, fr, spo2, ph, pao2, paco2, hco3, lactate]):
                    bilans_service.enregistrer_gaz_du_sang(
                        base, sejour["id"], date_heure,
                        ph=ph or None, pao2=pao2 or None, paco2=paco2 or None, hco3=hco3 or None,
                        lactate=lactate or None, mode_ventilatoire=None if mode_vent == "—" else mode_vent,
                        debit_o2=debit_o2 or None, fio2=fio2 or None, pep=pep or None, fr=fr or None,
                        spo2=spo2 or None, utilisateur_id=utilisateur_id,
                    )
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
            if st.form_submit_button("Enregistrer"):
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
if st.session_state.get("sejour_id"):
    ecran_fiche(st.session_state["sejour_id"])
else:
    ecran_lits()
