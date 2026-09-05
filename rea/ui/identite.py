"""Onglet Identité — état civil, correction d'admission, codage CIM-10.
"""

from __future__ import annotations

from datetime import date, datetime

import streamlit as st

from .. import listes, referentiels
from ..domaine import calculs, coherence
from ..domaine.dates import age_ans, format_date_fr, parse_date
from ..services import sejours as sejours_service
from . import contexte, theme

from . import champs


def _ligne_poids(sejour: dict) -> str:
    """Poids réel et poids idéal côte à côte : le réel entre dans la
    clairance, l'idéal sert de référence."""
    if not sejour.get("poids_kg"):
        return (
            "<span style='color:#B4442E'>Poids non renseigné — "
            "clairance incalculable</span>"
        )
    texte = f"Poids {champs.format_valeur(sejour['poids_kg'])} kg"
    if sejour.get("taille_cm"):
        texte += f" · {champs.format_valeur(sejour['taille_cm'])} cm"
    ideal = calculs.poids_ideal_devine(
        taille_cm=sejour.get("taille_cm"), sexe=sejour.get("sexe")
    )
    if ideal.disponible:
        texte += (
            f" · <span style='color:#5B6470'>poids idéal "
            f"{champs.format_valeur(ideal.valeur)} kg</span>"
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
            regions = sejours_service.regions_traumatiques(contexte.base(), sejour["id"])
            elements = [listes.libelle(listes.REGIONS_TRAUMATIQUES, r) for r in regions] or [
                "Régions non précisées"
            ]
            if sejours_service.est_polytraumatise(contexte.base(), sejour["id"]):
                elements.insert(0, "<b>Polytraumatisé</b> (calculé)")
            if sejour["mecanisme"]:
                elements.append(
                    f"Mécanisme : {listes.libelle(listes.MECANISMES, sejour['mecanisme'])}"
                )
            theme.bloc("Motif traumatique", elements, theme.ORANGE)
        else:
            motifs = sejours_service.motifs_du_sejour(contexte.base(), sejour["id"])
            principal = next((m for m in motifs if m["principal"]), None)
            associes = [m for m in motifs if not m["principal"]]
            elements = []
            if principal:
                elements.append(f"<b>{listes.libelle_motif(principal['code'])}</b>")
            elements += [listes.libelle_motif(m["code"]) for m in associes]
            theme.bloc("Motif d'admission", elements or ["Non renseigné"], theme.ORANGE)

    antecedents = sejours_service.antecedents_du_patient(contexte.base(), sejour["patient_id"])
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
                    contexte.base(), patient_id=sejour["patient_id"], categorie=categorie_auto,
                    libelle=libelle_txt, code=code_court, precision=precision or None,
                    utilisateur_id=contexte.utilisateur_id(),
                )
            elif libelle_libre:
                sejours_service.ajouter_antecedent(
                    contexte.base(), patient_id=sejour["patient_id"], categorie=categorie,
                    libelle=libelle_libre, precision=precision or None, utilisateur_id=contexte.utilisateur_id(),
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
                poids_kg = champs.nombre_saisi(c_poids.text_input(
                    "Poids (kg)", value=_valeur_texte(sejour.get("poids_kg"))
                ))
                taille_cm = champs.nombre_saisi(c_taille.text_input(
                    "Taille (cm)", value=_valeur_texte(sejour.get("taille_cm"))
                ))
                creatinine_base = champs.nombre_saisi(st.text_input(
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
                regions_actuelles = sejours_service.regions_traumatiques(contexte.base(), sejour["id"])
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
                motifs_actuels = sejours_service.motifs_du_sejour(contexte.base(), sejour["id"])
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
                if not contexte.controle(
                    f"correction_{sejour['id']}",
                    coherence.verifier_sejour(
                        date_admission=date_admission, date_naissance=date_naissance
                    ),
                    cible="sejour",
                    ligne_id=sejour["id"],
                ):
                    return
                sejours_service.modifier_identite(
                    contexte.base(), sejour["patient_id"], matricule=matricule,
                    nom_affichage=nom_affichage or "Non identifié",
                    date_naissance=str(date_naissance) if date_naissance else None,
                    sexe=sexe, groupe_sanguin=groupe_sanguin,
                    utilisateur_id=contexte.utilisateur_id(),
                )
                sejours_service.modifier_admission(
                    contexte.base(), sejour["id"],
                    date_admission=datetime.combine(date_admission, datetime.min.time()).isoformat(),
                    provenance_type=provenance_type, provenance_detail=provenance_detail or None,
                    poids_kg=poids_kg, taille_cm=taille_cm, creatinine_base=creatinine_base,
                    type_admission=type_admission, maladie_chronique_igs2=maladie_chronique_igs2,
                    traumatique=traumatique,
                    regions_traumatiques_choisies=regions_choisies, mecanisme=mecanisme,
                    motif_principal=motif_principal, motifs_associes=motifs_associes,
                    utilisateur_id=contexte.utilisateur_id(),
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
                    contexte.base(), sejour["id"], code, utilisateur_id=contexte.utilisateur_id()
                )
                st.rerun()
        st.caption(
            f"Référentiel CIM-10 version {referentiels.version('cim10')} — "
            "sous-ensemble partiel, chaque code est à vérifier sur le volume "
            "officiel avant usage statistique."
        )
