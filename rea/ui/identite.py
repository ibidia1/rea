"""Onglet Identité — état civil, correction d'admission.
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
from .admission import choix_motif_principal, choix_motifs_associes, precisions_regions


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
    # Trois blocs à parts égales, en grand : ce sont les seules lignes de
    # l'écran qu'on relit debout, à distance (demande du service, 8 septembre).
    # « Modifier l'admission » a quitté cette rangée pour rejoindre
    # « Transférer vers un autre lit », plus bas.
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
            grand=True,
        )

    with c_motif:
        if sejour["traumatique"]:
            regions = sejours_service.regions_traumatiques_detail(contexte.base(), sejour["id"])
            elements = [
                listes.libelle(listes.REGIONS_TRAUMATIQUES, r["region"])
                + (f" : {r['precision']}" if r["precision"] else "")
                for r in regions
            ] or ["Régions non précisées"]
            if sejours_service.est_polytraumatise(contexte.base(), sejour["id"]):
                elements.insert(0, "<b>Polytraumatisé</b> (calculé)")
            if sejour["mecanisme"]:
                elements.append(
                    f"Mécanisme : {listes.libelle(listes.MECANISMES, sejour['mecanisme'])}"
                )
            # La région tient lieu de motif principal, mais des complications
            # non traumatiques peuvent y être associées (traumatisme
            # thoracique + embolie pulmonaire + SDRA…) — sans quoi elles
            # seraient enregistrées sans jamais apparaître nulle part.
            associes = sejours_service.motifs_du_sejour(contexte.base(), sejour["id"])
            if associes:
                elements.append(
                    "Associé : " + ", ".join(listes.libelle_motif(m["code"]) for m in associes)
                )
            theme.bloc("Motif traumatique", elements, theme.ORANGE, grand=True)
        else:
            motifs = sejours_service.motifs_du_sejour(contexte.base(), sejour["id"])
            principal = next((m for m in motifs if m["principal"]), None)
            associes = [m for m in motifs if not m["principal"]]
            elements = []
            if principal:
                elements.append(f"<b>{listes.libelle_motif(principal['code'])}</b>")
            elements += [listes.libelle_motif(m["code"]) for m in associes]
            theme.bloc(
                "Motif d'admission", elements or ["Non renseigné"], theme.ORANGE, grand=True
            )

    antecedents = sejours_service.antecedents_du_patient(contexte.base(), sejour["patient_id"])
    allergies = [a for a in antecedents if a["categorie"] == "allergie"]
    with c_antecedents:
        if allergies:
            theme.bloc(
                "Allergies",
                [f"<b>{a['libelle']}</b>" for a in allergies],
                theme.ROUGE,
                grand=True,
            )
        theme.bloc(
            "Antécédents",
            [
                _texte_antecedent(a)
                for a in antecedents if a["categorie"] != "allergie"
            ] or ["Aucun antécédent enregistré"],
            theme.GRIS,
            grand=True,
        )

    _transferer_lit(sejour)
    # Deux gestes occasionnels, deux tiroirs de même forme, l'un sous l'autre
    # (demande du service, 8 septembre) : transférer déplace un patient,
    # modifier répare une saisie — ni l'un ni l'autre ne mérite un bandeau
    # permanent en haut de l'écran.
    with st.expander("Modifier l'admission"):
        _modifier_admission(sejour)

    st.markdown("**Antécédents**")
    _antecedents_editeur(sejour)


def _texte_antecedent(a: dict) -> str:
    texte = a["libelle"]
    if a.get("quantification_valeur") is not None:
        texte += f" — {champs.format_valeur(a['quantification_valeur'])} {a['quantification_unite']}"
    if a.get("precision"):
        texte += f" — {a['precision']}"
    return texte


def _antecedents_editeur(sejour: dict) -> None:
    """Le patient a-t-il des antécédents ? Oui / Non / Inconnu (SPEC §4.2
    bis) — « Inconnu » se traite comme « sans antécédent connu » à
    l'affichage, mais reste distingué en base (trois états, pas deux).

    Volontairement sans `st.form` : la bascule Oui/Non/Inconnu puis la
    cascade catégorie → sous-catégorie doivent se réafficher à chaque clic,
    ce qu'un formulaire Streamlit ne fait pas tant qu'il n'est pas soumis."""
    base = contexte.base()
    patient_id = sejour["patient_id"]
    prefixe = f"atcd_{sejour['id']}"
    etat_actuel = sejours_service.etat_antecedents(base, patient_id)

    if etat_actuel == "oui":
        _liste_antecedents(sejour)
        st.caption("Ajouter un autre antécédent :")
        _formulaire_categorie(sejour, prefixe)
        return

    valeurs = ["oui", "non", "inconnu"]
    defaut = "non" if etat_actuel == "absent" else "inconnu"
    reponse = st.radio(
        "Le patient a-t-il des antécédents ?",
        valeurs,
        format_func=lambda v: {"oui": "Oui", "non": "Non", "inconnu": "Inconnu"}[v],
        index=valeurs.index(defaut),
        horizontal=True,
        key=f"{prefixe}_reponse",
    )
    if reponse == "non" and etat_actuel != "absent":
        sejours_service.definir_etat_antecedents(
            base, patient_id, "absent", utilisateur_id=contexte.utilisateur_id()
        )
        st.rerun()
    elif reponse == "inconnu" and etat_actuel != "non_renseigne":
        sejours_service.definir_etat_antecedents(
            base, patient_id, "non_renseigne", utilisateur_id=contexte.utilisateur_id()
        )
        st.rerun()
    elif reponse == "oui":
        _formulaire_categorie(sejour, prefixe)


def _liste_antecedents(sejour: dict) -> None:
    """Les antécédents déjà saisis, chacun avec sa croix pour le retirer
    (demande du service, 8 septembre).

    Un antécédent se saisit vite et se trompe vite — coché sur le mauvais
    patient, tapé deux fois, ou démenti par la famille le lendemain. Sans
    moyen de le retirer, il se recopie ensuite sur chaque feuille imprimée.
    La suppression est logique : la ligne reste en base, tracée au journal.
    """
    antecedents = sejours_service.antecedents_du_patient(
        contexte.base(), sejour["patient_id"]
    )
    if not antecedents:
        return
    for a in antecedents:
        col_croix, col_texte = st.columns([1, 20])
        if col_croix.button(
            "X", key=f"suppr_atcd_{a['id']}", help="Retirer cet antécédent"
        ):
            sejours_service.supprimer_antecedent(
                contexte.base(), a["id"], utilisateur_id=contexte.utilisateur_id()
            )
            st.rerun()
        categorie = listes.libelle(listes.CATEGORIES_ANTECEDENT, a["categorie"], "")
        col_texte.markdown(
            f"<span style='font-size:.9rem'>{_texte_antecedent(a)}"
            + (f" <span style='color:{theme.GRIS};font-size:.78rem'>· {categorie}</span>"
               if categorie else "")
            + "</span>",
            unsafe_allow_html=True,
        )


def _formulaire_categorie(sejour: dict, prefixe: str) -> None:
    groupes = ["familial", "personnel_large", "habitude"]
    groupe = st.radio(
        "Catégorie",
        groupes,
        format_func=lambda v: {
            "familial": "Familiaux",
            "personnel_large": "Personnels (chirurgical, médical, allergies)",
            "habitude": "Habitudes de vie",
        }[v],
        horizontal=True,
        key=f"{prefixe}_groupe",
    )
    if groupe == "familial":
        _formulaire_antecedent_libre(sejour, categorie="familial", key_prefixe=f"{prefixe}_familial")
    elif groupe == "personnel_large":
        sous_categories = ["personnel", "chirurgical", "allergie"]
        sous_categorie = st.radio(
            "Type",
            sous_categories,
            format_func=lambda c: listes.libelle(listes.CATEGORIES_ANTECEDENT, c),
            horizontal=True,
            key=f"{prefixe}_sous_categorie",
        )
        _formulaire_antecedent_libre(
            sejour, categorie=sous_categorie, key_prefixe=f"{prefixe}_{sous_categorie}"
        )
    else:
        _formulaire_habitude(sejour, key_prefixe=f"{prefixe}_habitude")


def _formulaire_antecedent_libre(sejour: dict, *, categorie: str, key_prefixe: str) -> None:
    """Empiler plusieurs antécédents avant de valider une seule fois : taper
    « dia », Entrée ajoute Diabète, taper un antécédent absent de la liste
    courte, Entrée l'ajoute aussi (`accept_new_options`) — sans forcer
    l'interne à reparcourir toute la liste à chaque antécédent."""
    options = [(c, l) for c, l, cat in listes.ANTECEDENTS_COURTS if cat == categorie]
    choisis = st.multiselect(
        "Antécédent(s)",
        [c for c, _l in options],
        format_func=lambda c: listes.libelle(options, c),
        placeholder="Taper pour chercher (ex. « dia »), ou écrire un antécédent puis Entrée",
        accept_new_options=True,
        key=f"{key_prefixe}_choix",
    )
    if st.button("Ajouter", key=f"{key_prefixe}_valider") and choisis:
        for entree in choisis:
            connu = entree in [c for c, _l in options]
            sejours_service.ajouter_antecedent(
                contexte.base(), patient_id=sejour["patient_id"], categorie=categorie,
                libelle=listes.libelle(options, entree), code=entree if connu else None,
                utilisateur_id=contexte.utilisateur_id(),
            )
        st.rerun()


def _formulaire_habitude(sejour: dict, *, key_prefixe: str) -> None:
    """Trois habitudes prêtes par défaut (SPEC §4.2 bis), plus « Autre » en
    recherche libre : tabagisme quantifié en paquets-années, éthylisme,
    toxicomanie avec la ou les substances précisées — jamais un simple
    « présent/absent » qui ferait perdre l'information clinique utile."""
    habitude = st.radio(
        "Habitude",
        ["tabagisme", "ethylisme", "toxicomanie", "autre"],
        format_func=lambda v: {
            "tabagisme": "Tabagisme", "ethylisme": "Éthylisme",
            "toxicomanie": "Toxicomanie", "autre": "Autre",
        }[v],
        horizontal=True,
        key=f"{key_prefixe}_type",
    )
    base = contexte.base()
    patient_id = sejour["patient_id"]
    uid = contexte.utilisateur_id()

    if habitude == "tabagisme":
        pa = champs.nombre_saisi(
            st.text_input("Paquets-années", value="", placeholder="ex. 20", key=f"{key_prefixe}_pa")
        )
        if st.button("Ajouter", key=f"{key_prefixe}_valider"):
            sejours_service.ajouter_antecedent(
                base, patient_id=patient_id, categorie="habitude", libelle="Tabagisme",
                code="tabagisme", quantification_valeur=pa,
                quantification_unite="paquets-année" if pa is not None else None,
                utilisateur_id=uid,
            )
            st.rerun()
    elif habitude == "ethylisme":
        precision = st.text_input("Précision (facultatif)", key=f"{key_prefixe}_precision")
        if st.button("Ajouter", key=f"{key_prefixe}_valider"):
            sejours_service.ajouter_antecedent(
                base, patient_id=patient_id, categorie="habitude", libelle="Éthylisme",
                code="ethylisme", precision=precision or None, utilisateur_id=uid,
            )
            st.rerun()
    elif habitude == "toxicomanie":
        substances = st.text_input(
            "Substance(s)", placeholder="ex. cannabis, cocaïne", key=f"{key_prefixe}_substances"
        )
        if st.button("Ajouter", key=f"{key_prefixe}_valider") and substances:
            sejours_service.ajouter_antecedent(
                base, patient_id=patient_id, categorie="habitude", libelle="Toxicomanie",
                code="toxicomanie", precision=substances, utilisateur_id=uid,
            )
            st.rerun()
    else:
        libelle_libre = st.text_input("Libellé", key=f"{key_prefixe}_libelle")
        precision = st.text_input("Précision (facultatif)", key=f"{key_prefixe}_precision")
        if st.button("Ajouter", key=f"{key_prefixe}_valider") and libelle_libre:
            sejours_service.ajouter_antecedent(
                base, patient_id=patient_id, categorie="habitude", libelle=libelle_libre,
                precision=precision or None, utilisateur_id=uid,
            )
            st.rerun()


def _transferer_lit(sejour: dict) -> None:
    """Change le patient de lit — un transfert, pas une correction de saisie.

    Séparé de `_modifier_admission` à dessein : celle-ci répare une erreur de
    frappe, ceci déplace réellement un patient. Les deux ne doivent pas se
    confondre dans un même formulaire.
    """
    from ..services import lits as lits_service

    with st.expander("Transférer vers un autre lit"):
        libres = lits_service.lits_libres(contexte.base())
        if not libres:
            st.caption("Aucun autre lit n'est libre actuellement.")
            return
        nouveau_lit = st.selectbox(
            "Nouveau lit", libres, format_func=lambda l: f"Lit {l}", key=f"lit_{sejour['id']}"
        )
        if st.button("Transférer", key=f"transferer_{sejour['id']}"):
            sejours_service.changer_de_lit(
                contexte.base(), sejour["id"], nouveau_lit,
                utilisateur_id=contexte.utilisateur_id(),
            )
            st.success(f"Transféré vers le lit {nouveau_lit}.")
            st.rerun()


def _modifier_admission(sejour: dict) -> None:
    """Modifie une admission — erreur de saisie ou complément découvert après
    coup (matricule, nom, date, poids, motif, un antécédent appris plus tard).

    Ce n'est pas un nouveau séjour : les mêmes lignes sont mises à jour, avec
    trace dans le journal de qui a corrigé et quand (règle de conception 2 —
    jamais de suppression physique). Le lit n'est pas modifiable ici : changer
    de lit est un transfert, une autre opération, avec d'autres contrôles.

    Dans un `st.popover` — un bouton compact plutôt qu'un bandeau permanent :
    modifier une admission est un geste occasionnel, il ne doit pas peser sur
    l'écran en continu.

    Pas de `st.form` : la moitié des champs sont conditionnels (traumatique ou
    non, mécanisme avec précision) — un `st.form` fige leur affichage jusqu'à
    la soumission, ce qui les rend impossibles à choisir correctement dans le
    même geste (voir `admission.ecran_nouvelle_admission`, même remarque).
    """
    st.caption(
        "Pour une erreur de saisie — matricule, nom, date, poids, motif "
        "coché du mauvais côté, ou un antécédent découvert après coup. "
        "Le lit ne se change pas ici."
    )
    prefixe = f"corr_{sejour['id']}"
    col1, col2 = st.columns(2)
    with col1:
        matricule = st.text_input(
            "Matricule", value=sejour.get("matricule") or "", key=f"{prefixe}_matricule"
        )
        nom_affichage = st.text_input(
            "Nom affiché", value=sejour.get("nom_affichage") or "", key=f"{prefixe}_nom"
        )
        date_naissance = st.date_input(
            "Date de naissance",
            value=parse_date(sejour.get("date_naissance")),
            min_value=date(1900, 1, 1), max_value=date.today(),
            key=f"{prefixe}_naissance",
        )
        c_sexe, c_groupe = st.columns(2)
        sexe = c_sexe.selectbox(
            "Sexe", listes.codes(listes.SEXES),
            index=listes.codes(listes.SEXES).index(sejour.get("sexe") or "non_renseigne"),
            format_func=lambda c: listes.libelle(listes.SEXES, c),
            key=f"{prefixe}_sexe",
        )
        groupes = referentiels.charger("groupes_sanguins")
        codes_groupes = listes.codes(groupes)
        groupe_sanguin = c_groupe.selectbox(
            "Groupe sanguin", codes_groupes,
            index=codes_groupes.index(sejour.get("groupe_sanguin") or "non_renseigne"),
            format_func=lambda c: listes.libelle(groupes, c),
            key=f"{prefixe}_groupe",
        )
        c_poids, c_taille = st.columns(2)
        poids_kg = champs.nombre_saisi(c_poids.text_input(
            "Poids (kg)", value=_valeur_texte(sejour.get("poids_kg")), key=f"{prefixe}_poids"
        ))
        taille_cm = champs.nombre_saisi(c_taille.text_input(
            "Taille (cm)", value=_valeur_texte(sejour.get("taille_cm")), key=f"{prefixe}_taille"
        ))
        creatinine_base = champs.nombre_saisi(st.text_input(
            "Créatinine antérieure (µmol/L)",
            value=_valeur_texte(sejour.get("creatinine_base")), key=f"{prefixe}_creatinine",
        ))
        glasgow_initial = champs.nombre_saisi(st.text_input(
            "Glasgow à l'arrivée (3-15)",
            value=_valeur_texte(sejour.get("glasgow_initial")), key=f"{prefixe}_glasgow",
        ))
    with col2:
        date_admission = st.date_input(
            "Date d'admission",
            value=parse_date(sejour["date_admission"]) or date.today(),
            key=f"{prefixe}_date_admission",
        )
        provenance_type = st.selectbox(
            "Provenance", listes.codes(listes.PROVENANCES),
            index=listes.codes(listes.PROVENANCES).index(sejour.get("provenance_type"))
                  if sejour.get("provenance_type") in listes.codes(listes.PROVENANCES) else 0,
            format_func=lambda c: listes.libelle(listes.PROVENANCES, c),
            key=f"{prefixe}_provenance",
        )
        provenance_detail = st.text_input(
            "Préciser la provenance", value=sejour.get("provenance_detail") or "",
            key=f"{prefixe}_provenance_detail",
        )
        types_admission = referentiels.charger("types_admission")
        codes_types = listes.codes(types_admission)
        type_admission = st.selectbox(
            "Type d'admission (IGS II)", codes_types,
            index=codes_types.index(sejour.get("type_admission"))
                  if sejour.get("type_admission") in codes_types else 0,
            format_func=lambda c: listes.libelle(types_admission, c),
            key=f"{prefixe}_type_admission",
        )
        maladies = referentiels.charger("maladies_chroniques_igs2")
        codes_maladies = listes.codes(maladies)
        maladie_chronique_igs2 = st.selectbox(
            "Maladie chronique (IGS II)", codes_maladies,
            index=codes_maladies.index(sejour.get("maladie_chronique_igs2"))
                  if sejour.get("maladie_chronique_igs2") in codes_maladies else 0,
            format_func=lambda c: listes.libelle(maladies, c),
            key=f"{prefixe}_maladie_chronique",
        )

    st.markdown("**Motif d'admission**")
    traumatique = st.radio(
        "Type", ["Traumatique", "Non traumatique"], horizontal=True,
        index=0 if sejour.get("traumatique") else 1,
        key=f"{prefixe}_type_motif",
    ) == "Traumatique"

    regions_choisies: list[str] = []
    precisions_regions_choisies: dict[str, str] = {}
    mecanisme = None
    mecanisme_detail = None
    motif_principal = None
    motifs_associes: list[str] = []
    motifs_actuels = sejours_service.motifs_du_sejour(contexte.base(), sejour["id"])
    associes_actuels = [m["code"] for m in motifs_actuels if not m["principal"]]
    if traumatique:
        regions_actuelles = sejours_service.regions_traumatiques_detail(contexte.base(), sejour["id"])
        precisions_actuelles = {r["region"]: r["precision"] or "" for r in regions_actuelles}
        regions_choisies = st.multiselect(
            "Régions atteintes", listes.codes(listes.REGIONS_TRAUMATIQUES),
            default=[r for r in precisions_actuelles if r in listes.codes(listes.REGIONS_TRAUMATIQUES)],
            format_func=lambda c: listes.libelle(listes.REGIONS_TRAUMATIQUES, c),
            placeholder="Aucune",
            key=f"{prefixe}_regions",
        )
        precisions_regions_choisies = precisions_regions(
            regions_choisies, precisions_actuelles, key_prefixe=prefixe,
        )
        codes_mecanismes = listes.codes(listes.MECANISMES)
        mecanisme = st.selectbox(
            "Mécanisme", codes_mecanismes,
            index=codes_mecanismes.index(sejour.get("mecanisme"))
                  if sejour.get("mecanisme") in codes_mecanismes else 0,
            format_func=lambda c: listes.libelle(listes.MECANISMES, c),
            key=f"{prefixe}_mecanisme",
        )
        mecanisme_detail = ""
        if mecanisme in listes.MECANISMES_AVEC_DETAIL:
            mecanisme_detail = st.text_input(
                "Préciser le mécanisme", value=sejour.get("mecanisme_detail") or "",
                key=f"{prefixe}_mecanisme_detail",
            )
        motifs_associes = choix_motifs_associes(
            f"{prefixe}_trauma", defaut=associes_actuels,
        )
    else:
        principal_actuel = next((m["code"] for m in motifs_actuels if m["principal"]), None)
        motif_principal = choix_motif_principal(
            f"{prefixe}_nontrauma", defaut=principal_actuel,
        )
        motifs_associes = choix_motifs_associes(
            f"{prefixe}_nontrauma", exclure=motif_principal, defaut=associes_actuels,
        )

    if st.button("Enregistrer les corrections", type="primary", key=f"{prefixe}_valider"):
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
            glasgow_initial=int(glasgow_initial) if glasgow_initial else None,
            traumatique=traumatique,
            regions_traumatiques_choisies=regions_choisies,
            regions_traumatiques_precisions=precisions_regions_choisies,
            mecanisme=mecanisme, mecanisme_detail=mecanisme_detail or None,
            motif_principal=motif_principal, motifs_associes=motifs_associes,
            utilisateur_id=contexte.utilisateur_id(),
        )
        st.success("Admission modifiée.")
        st.rerun()


def _valeur_texte(valeur) -> str:
    if valeur is None:
        return ""
    return str(valeur).replace(".", ",") if isinstance(valeur, float) else str(valeur)


