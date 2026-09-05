"""Écran 2 — admission d'un patient dans un lit libre (SPEC §4.1).
"""

from __future__ import annotations

from datetime import date, datetime

import streamlit as st

from .. import listes, protocoles, referentiels
from ..domaine import coherence
from ..services import prescriptions as prescriptions_service
from ..services import sejours as sejours_service
from . import contexte

from . import champs


def _protocoles_proposes(
    *, traumatique: bool, regions_choisies: list[str],
    motif_principal: str | None, motifs_associes: list[str],
) -> list:
    """Les protocoles validés et signés dont le déclencheur correspond au
    motif choisi (SPEC §4.5, règle de sécurité 1) — jamais un brouillon non
    signé, quoi qu'il contienne."""
    trouves: dict[str, object] = {}
    if traumatique:
        for region in regions_choisies:
            for p in protocoles.protocoles_pour_region_traumatique(region):
                trouves[p.code] = p
    for motif in ([motif_principal] if motif_principal else []) + list(motifs_associes):
        for p in protocoles.protocoles_pour_motif(motif):
            trouves[p.code] = p
    return list(trouves.values())


def choix_protocoles(cle: str, protocoles_proposes: list) -> list:
    """Une case par protocole — jamais appliqué tout seul (règle de sécurité
    1) : chaque ligne qui en découle reste une ligne de prescription
    ordinaire, modifiable et supprimable comme n'importe quelle autre."""
    if not protocoles_proposes:
        return []
    st.markdown("**Protocoles proposés**")
    choisis = []
    for p in protocoles_proposes:
        coche = st.checkbox(
            f"{p.titre} — validé le {p.date_version}, signé {p.signe_par}",
            key=f"{cle}_{p.code}",
        )
        if p.consignes:
            st.caption(" · ".join(p.consignes))
        if coche:
            choisis.append(p)
    return choisis


def appliquer_protocoles(base, sejour_id: str, protocoles_choisis: list, *, date_debut: str, utilisateur_id: str | None) -> None:
    """Pose les lignes de prescription du protocole, tracées comme telles.

    Chaque ligne part sans dose (SPEC §3.1 — le logiciel ne calcule ni ne
    propose de dose) : le protocole ne porte que voie, produit, rythme —
    exactement ce qu'un protocole signé a le droit de préremplir.
    """
    for p in protocoles_choisis:
        for ligne in p.lignes_prescription:
            if not ligne.get("voie") or not ligne.get("produit"):
                continue
            prescriptions_service.ajouter_ligne(
                base, sejour_id=sejour_id, voie=ligne["voie"], produit=ligne["produit"],
                date_debut=date_debut, rythme=ligne.get("rythme") or None,
                condition_texte=ligne.get("note") or None,
                protocole_code=p.code, protocole_version=p.version,
                utilisateur_id=utilisateur_id,
            )


def choix_motif_principal(cle: str, *, defaut: str | None = None) -> str | None:
    """Catégorie puis motif, plutôt qu'une liste à plat de près de quarante
    entrées — et ça suit le regroupement du fichier de référence
    (`referentiels/motifs_non_traumatiques.json`), comme au SPEC §4.4."""
    categories = list(listes.MOTIFS_NON_TRAUMATIQUES.keys())
    categorie_defaut = next(
        (g for g, entrees in listes.MOTIFS_NON_TRAUMATIQUES.items()
         if defaut in {c for c, _l, _p in entrees}),
        categories[0],
    )
    categorie = st.selectbox(
        "Catégorie du motif", categories, index=categories.index(categorie_defaut),
        key=f"{cle}_categorie",
    )
    entrees = listes.MOTIFS_NON_TRAUMATIQUES[categorie]
    paires = [(c, l) for c, l, _p in entrees]
    codes = [c for c, _l in paires]
    return st.selectbox(
        "Motif principal", codes,
        index=codes.index(defaut) if defaut in codes else 0,
        format_func=lambda c: listes.libelle(paires, c),
        key=f"{cle}_motif",
    )


def choix_motifs_associes(
    cle: str, *, exclure: str | None = None, defaut: list[str] = ()
) -> list[str]:
    """Multi-sélection sur la liste complète, groupée par catégorie dans son
    libellé : une complication associée n'est pas forcément de la même
    catégorie que le motif principal (un SDRA peut compliquer un choc
    hémorragique aussi bien qu'un traumatisme)."""
    tous_motifs = [m for m in listes.motifs_a_plat() if m[0] != exclure]
    codes = [c for c, _l, _g in tous_motifs]
    return st.multiselect(
        "Motifs non traumatiques associés",
        codes,
        default=[c for c in defaut if c in codes and c != exclure],
        format_func=lambda c: f"{listes.libelle_motif(c)} — {next(g for cc, _l, g in tous_motifs if cc == c)}",
        key=f"{cle}_associes",
        placeholder="Aucun",
        help="Complications non traumatiques associées : embolie pulmonaire, "
             "SDRA, acidocétose… — s'ajoutent au motif principal, ne le remplacent pas.",
    )


def ecran_nouvelle_admission(lit: int | None) -> None:
    """Pas de `st.form` ici, volontairement : la moitié des champs de cet
    écran changent selon un autre champ (patient non identifié, traumatique
    ou non, mécanisme avec précision, provenance avec précision…). Un
    `st.form` gèle tout l'affichage jusqu'à la soumission — les sections
    conditionnelles ne se seraient jamais mises à jour avant qu'il ne soit
    trop tard pour les remplir. Chaque widget doit donc rester réactif ; le
    bouton en bas ne fait que lire leur valeur du moment, comme le ferait un
    `st.form_submit_button`.
    """
    st.divider()
    st.header(f"Nouvelle admission — Lit {lit}")

    col1, col2 = st.columns(2)
    with col1:
        non_identifie = st.checkbox("Patient non identifié", key="admission_non_identifie")
        matricule = (
            sejours_service.prochain_matricule_non_identifie(contexte.base())
            if non_identifie
            else st.text_input("Matricule", key="admission_matricule")
        )
        nom_affichage = (
            "Non identifié" if non_identifie
            else st.text_input("Nom affiché (ex. « K. Abdelaziz »)", key="admission_nom")
        )
        date_naissance = None if non_identifie else st.date_input(
            "Date de naissance", value=None, min_value=date(1900, 1, 1), max_value=date.today(),
            key="admission_date_naissance",
        )
        c_sexe, c_groupe = st.columns(2)
        sexe = c_sexe.selectbox(
            "Sexe", listes.codes(listes.SEXES),
            format_func=lambda c: listes.libelle(listes.SEXES, c),
            key="admission_sexe",
        )
        # Le groupe sanguin est demandé dès l'admission : il figure en tête
        # de la feuille imprimée, et le chercher à quatre heures du matin
        # n'est pas un moment pour le chercher.
        groupes = referentiels.charger("groupes_sanguins")
        groupe_sanguin = c_groupe.selectbox(
            "Groupe sanguin", listes.codes(groupes),
            format_func=lambda c: listes.libelle(groupes, c),
            key="admission_groupe",
        )
        c_poids, c_taille = st.columns(2)
        # Le poids conditionne la clairance de la créatinine : sans lui,
        # aucune formule pondérale n'est calculable ensuite.
        poids_kg = champs.nombre_saisi(
            c_poids.text_input("Poids (kg)", value="", placeholder="ex. 70", key="admission_poids")
        )
        taille_cm = champs.nombre_saisi(
            c_taille.text_input("Taille (cm)", value="", placeholder="ex. 175", key="admission_taille")
        )
        creatinine_base = champs.nombre_saisi(
            st.text_input(
                "Créatinine antérieure connue (µmol/L)", value="",
                placeholder="si connue — sert au diagnostic d'insuffisance rénale aiguë",
                key="admission_creatinine",
            )
        )
    with col2:
        date_admission = st.date_input(
            "Date d'admission", value=date.today(), key="admission_date_admission"
        )
        provenance_type = st.selectbox(
            "Provenance", listes.codes(listes.PROVENANCES),
            format_func=lambda c: listes.libelle(listes.PROVENANCES, c),
            key="admission_provenance",
        )
        provenance_detail = ""
        if provenance_type in listes.PROVENANCES_AVEC_DETAIL:
            provenance_detail = st.text_input(
                "Préciser le service / l'établissement", key="admission_provenance_detail"
            )
        est_readmission = st.checkbox("Réadmission", key="admission_readmission")
        motif_readmission = (
            st.text_input("Motif de réadmission", key="admission_motif_readmission")
            if est_readmission else ""
        )
        # Deux variables de l'IGS II qu'aucune autre donnée du dossier ne
        # permet de retrouver après coup.
        types_admission = referentiels.charger("types_admission")
        type_admission = st.selectbox(
            "Type d'admission", listes.codes(types_admission),
            format_func=lambda c: listes.libelle(types_admission, c),
            key="admission_type_admission",
        )
        maladies = referentiels.charger("maladies_chroniques_igs2")
        maladie_chronique_igs2 = st.selectbox(
            "Maladie chronique (IGS II)", listes.codes(maladies),
            format_func=lambda c: listes.libelle(maladies, c),
            key="admission_maladie_chronique",
        )

    st.markdown("**Motif d'admission**")
    traumatique = st.radio(
        "Type", ["Traumatique", "Non traumatique"], horizontal=True, key="admission_traumatique",
    ) == "Traumatique"

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
            key="admission_regions",
            placeholder="Aucune",
        )
        if len(regions_choisies) >= 2:
            st.info("Statut polytraumatisé — calculé automatiquement")
        mecanisme = st.selectbox(
            "Mécanisme", listes.codes(listes.MECANISMES),
            format_func=lambda c: listes.libelle(listes.MECANISMES, c),
            key="admission_mecanisme",
        )
        if mecanisme in listes.MECANISMES_AVEC_DETAIL:
            mecanisme_detail = st.text_input(
                "Préciser le mécanisme", key="admission_mecanisme_detail"
            )
        # La région tient lieu de motif principal, mais une complication
        # non traumatique peut s'y associer — traumatisme thoracique
        # associé à une embolie pulmonaire, un SDRA, une acidocétose.
        motifs_associes = choix_motifs_associes("admission_trauma")
    else:
        motif_principal = choix_motif_principal("admission")
        motifs_associes = choix_motifs_associes("admission_nontrauma", exclure=motif_principal)

    protocoles_choisis = choix_protocoles(
        "admission_protocole",
        _protocoles_proposes(
            traumatique=traumatique, regions_choisies=regions_choisies,
            motif_principal=motif_principal, motifs_associes=motifs_associes,
        ),
    )

    valide = st.button("Créer l'admission", type="primary", key="admission_valider")

    if valide:
        if not non_identifie and not matricule:
            st.error("Le matricule est obligatoire.")
            return
        if not contexte.controle(
            "admission",
            coherence.verifier_sejour(
                date_admission=date_admission, date_naissance=date_naissance
            ),
            cible="sejour",
        ):
            return
        pid = sejours_service.creer_patient(
            contexte.base(),
            matricule=matricule,
            nom_affichage=nom_affichage or "Non identifié",
            date_naissance=str(date_naissance) if date_naissance else None,
            sexe=sexe,
            groupe_sanguin=groupe_sanguin,
            non_identifie=non_identifie,
            utilisateur_id=contexte.utilisateur_id(),
        )
        sid = sejours_service.creer_sejour(
            contexte.base(),
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
            utilisateur_id=contexte.utilisateur_id(),
        )
        if traumatique and regions_choisies:
            sejours_service.definir_regions_traumatiques(contexte.base(), sid, regions_choisies, utilisateur_id=contexte.utilisateur_id())
        if motif_principal or motifs_associes:
            sejours_service.definir_motifs(
                contexte.base(), sid, motif_principal=motif_principal, motifs_associes=motifs_associes,
                utilisateur_id=contexte.utilisateur_id(),
            )
        if protocoles_choisis:
            appliquer_protocoles(
                contexte.base(), sid, protocoles_choisis,
                date_debut=str(date_admission), utilisateur_id=contexte.utilisateur_id(),
            )
        for cle in list(st.session_state):
            if cle.startswith("admission_"):
                del st.session_state[cle]
        st.session_state.pop("mode", None)
        st.session_state.pop("lit_admission_choisi", None)
        st.session_state["sejour_id"] = sid
        st.session_state.pop("ecran", None)
        st.success("Séjour créé.")
        st.rerun()
