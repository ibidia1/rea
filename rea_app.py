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
from rea.domaine.dates import age_ans, format_date_fr, jour_hospitalisation
from rea.services import bilans as bilans_service
from rea.services import evolution as evolution_service
from rea.services import lits as lits_service
from rea.services import pancarte as pancarte_service
from rea.services import prescriptions as prescriptions_service
from rea.services import sejours as sejours_service
from rea.ui import utilisateur as utilisateur_ui

st.set_page_config(page_title="Réanimation polyvalente", layout="wide")

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

def ecran_lits() -> None:
    st.title("🛏 Tableau des lits")
    etat = lits_service.etat_des_lits(base)

    for chambre in (1, 2, 3):
        st.subheader(f"Chambre {chambre}")
        colonnes = st.columns(config.LITS_PAR_CHAMBRE)
        for i, lit_info in enumerate(l for l in etat if l["chambre"] == chambre):
            with colonnes[i]:
                if lit_info["occupe"]:
                    trauma = " · traumatique" if lit_info["traumatique"] else ""
                    if st.button(
                        f"**Lit {lit_info['lit']}**\n\n{lit_info['nom_affichage']}\n\n"
                        f"J{lit_info['jour_hospitalisation']}{trauma}",
                        key=f"lit_{lit_info['lit']}",
                        use_container_width=True,
                    ):
                        st.session_state["sejour_id"] = lit_info["sejour_id"]
                        st.rerun()
                else:
                    if st.button(
                        f"Lit {lit_info['lit']}\n\n— libre —",
                        key=f"lit_{lit_info['lit']}",
                        use_container_width=True,
                    ):
                        st.session_state["lit_admission_choisi"] = lit_info["lit"]
                        st.session_state["mode"] = "nouvelle_admission"
                        st.rerun()

    if st.session_state.get("mode") == "nouvelle_admission":
        ecran_nouvelle_admission(st.session_state.get("lit_admission_choisi"))


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
    st.write(
        f"**{sejour['nom_affichage']}** · matricule {sejour['matricule']} · "
        f"{age if age is not None else '?'} ans · Lit {sejour['lit_admission']}"
    )
    allergies = sejours_service.allergies_du_patient(base, sejour["patient_id"])
    if allergies:
        st.error("⚠ ALLERGIE : " + ", ".join(a["libelle"] for a in allergies))

    if sejour["traumatique"]:
        regions = sejours_service.regions_traumatiques(base, sejour["id"])
        libelles = [listes.libelle(listes.REGIONS_TRAUMATIQUES, r) for r in regions]
        poly = " · **polytraumatisé**" if sejours_service.est_polytraumatise(base, sejour["id"]) else ""
        st.write(f"Traumatique — {', '.join(libelles) or 'régions non précisées'}{poly}")
    else:
        motifs = sejours_service.motifs_du_sejour(base, sejour["id"])
        principal = next((m for m in motifs if m["principal"]), None)
        if principal:
            st.write(f"Motif : {listes.libelle_motif(principal['code'])}")

    st.subheader("Antécédents")
    antecedents = sejours_service.antecedents_du_patient(base, sejour["patient_id"])
    for a in antecedents:
        st.write(f"- {a['libelle']} ({listes.libelle(listes.TROIS_ETATS_PRESENCE, a['statut'])})")

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

    for code_voie in listes.ORDRE_VOIES:
        lignes = pancarte["lignes_par_voie"].get(code_voie, [])
        if not lignes:
            continue
        st.markdown(f"**{listes.VOIES[code_voie]['titre']}**")
        for ligne in lignes:
            texte = dom.libelle_ligne(ligne, date_jour_str)
            col1, col2 = st.columns([5, 1])
            with col1:
                if ligne["statut"] == "arretee":
                    st.markdown(f"~~{texte}~~")
                else:
                    st.write(texte)
            with col2:
                if ligne["statut"] == "active" and st.button("Arrêter", key=f"arret_{ligne['id']}"):
                    prescriptions_service.arreter_ligne(
                        base, ligne["id"], date_arret=date_jour_str, utilisateur_id=utilisateur_id
                    )
                    st.rerun()

    st.info(f"Entrées calculées sur 24 h : **{pancarte['bilan_entrees'].total_ml:.0f} mL**")

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

            date_debut = st.date_input("Date de début", value=date_jour, key=f"debut_{voie}")

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
        demain = str(date_jour)
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

    col1, col2 = st.columns(2)
    with col1:
        if st.button("📅 Préparer la pancarte de demain", use_container_width=True):
            prescriptions_service.preparer_pancarte_de_demain(
                base, sejour["id"], aujourdhui=date_jour_str, utilisateur_id=utilisateur_id
            )
            st.success("Journée de demain préparée — les bilans peuvent y être ajoutés.")
    with col2:
        if st.button("🖨 Imprimer la pancarte de ce jour", use_container_width=True):
            snap = pancarte_service.imprimer(base, sejour["id"], date_jour_str, utilisateur_id=utilisateur_id)
            st.session_state["derniere_impression"] = snap["html"]
            st.success(f"Pancarte enregistrée — version {snap['version']}.")

    if st.session_state.get("derniere_impression"):
        with st.expander("Aperçu de la dernière impression", expanded=True):
            st.components.v1.html(st.session_state["derniere_impression"], height=600, scrolling=True)


def onglet_evolution(sejour: dict) -> None:
    date_jour = st.date_input("Jour", value=date.today(), key="date_evolution")
    date_jour_str = str(date_jour)
    entree = evolution_service.obtenir_ou_creer(base, sejour["id"], date_jour_str, utilisateur_id=utilisateur_id)

    with st.form("evolution_form"):
        valeurs = {}
        for cle in evolution_service.PLANS:
            valeurs[cle] = st.text_area(evolution_service.LIBELLES_PLANS[cle], value=entree.get(cle) or "", height=70)
        valeurs["conduite"] = st.text_area("Conduite", value=entree.get("conduite") or "")
        if st.form_submit_button("Enregistrer"):
            evolution_service.enregistrer(base, sejour["id"], date_jour_str, valeurs, utilisateur_id=utilisateur_id)
            st.rerun()

    st.subheader("Texte généré")
    texte = evolution_service.texte_genere(base, sejour["id"], date_jour_str)
    st.text_area("Prêt à copier dans le DMI", value=texte, height=450)


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

    st.subheader("Texte généré")
    date_affichee = st.date_input("Jour", value=date.today(), key="date_bilan_texte")
    texte = bilans_service.texte_genere(base, sejour["id"], str(date_affichee))
    st.text_area("Prêt à coller dans l'évolution", value=texte or "(aucun bilan ce jour-là)", height=200)

    resultats = bilans_service.resultats_du_sejour(base, sejour["id"])
    if resultats:
        with st.expander("📈 Courbe de cinétique"):
            ids_disponibles = sorted({r["analyte"] for r in resultats})
            choix = st.selectbox(
                "Analyte", ids_disponibles, format_func=lambda i: cat.analyte(i).libelle
            )
            historique = bilans_service.historique_analyte(base, sejour["id"], choix)
            if len(historique) >= 1:
                import pandas as pd

                df = pd.DataFrame(historique).set_index("date_heure")
                st.line_chart(df["valeur_num"])


def ecran_fiche(sejour_id: str) -> None:
    sejour = sejours_service.sejour_avec_patient(base, sejour_id)
    if sejour is None:
        st.session_state.pop("sejour_id", None)
        st.rerun()
        return

    st.title(f"Lit {sejour['lit_admission']} — {sejour['nom_affichage']}")
    onglets = st.tabs(["Identité", "Prescrit", "Bilans", "Évolution", "Sortie"])
    with onglets[0]:
        onglet_identite(sejour)
    with onglets[1]:
        onglet_prescrit(sejour)
    with onglets[2]:
        onglet_bilans(sejour)
    with onglets[3]:
        onglet_evolution(sejour)
    with onglets[4]:
        onglet_sortie(sejour)


# --------------------------------------------------------------------------
# Routage
# --------------------------------------------------------------------------
if st.session_state.get("sejour_id"):
    ecran_fiche(st.session_state["sejour_id"])
else:
    ecran_lits()
