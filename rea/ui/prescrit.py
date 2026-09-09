"""Onglet Prescrit — la pancarte du jour, son impression, son historique.

C'est l'écran qui justifie le logiciel (SPEC §1.3) : le prescrit du
lendemain arrive pré-rempli, l'interne vérifie et complète.
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from .. import config, listes
from ..domaine import coherence, prescription as dom
from ..domaine.dates import format_date_fr, lendemain
from ..services import dispositifs as dispositifs_service
from ..services import pancarte as pancarte_service
from ..services import prescriptions as prescriptions_service
from ..services import vitesses as vitesses_service
from . import contexte, theme

from . import champs


def _pancarte_de_demain(sejour: dict, date_jour_str: str) -> None:
    """Préparer, puis valider, puis seulement alors imprimer.

    Préparer ne fait que reconduire les lignes actives — un geste mécanique,
    sans relecture. Le service a demandé une étape de validation entre les
    deux : imprimer une pancarte jamais relue serait imprimer une erreur de
    reconduction telle quelle.
    """
    demain = str(lendemain(date_jour_str))
    journee_demain = prescriptions_service.etat_journee(contexte.base(), sejour["id"], demain)
    preparee = bool(journee_demain and journee_demain.get("preparee_le"))
    validee = bool(journee_demain and journee_demain.get("validee_le"))

    st.markdown(f"**Pancarte du {format_date_fr(demain)}**")
    if not preparee:
        if st.button("Préparer la pancarte de demain", use_container_width=True):
            prescriptions_service.preparer_pancarte_de_demain(
                contexte.base(), sejour["id"], aujourdhui=date_jour_str, utilisateur_id=contexte.utilisateur_id()
            )
            st.rerun()
        return

    if not validee:
        st.caption("Préparée — à relire avant impression.")
        if st.button("Valider la pancarte de demain", use_container_width=True):
            prescriptions_service.valider_pancarte_de_demain(
                contexte.base(), sejour["id"], aujourdhui=date_jour_str, utilisateur_id=contexte.utilisateur_id()
            )
            st.rerun()
        return

    st.caption(f"Validée le {format_date_fr(journee_demain['validee_le'][:10])}.")
    if st.button("Imprimer la pancarte de demain", type="primary", use_container_width=True):
        snap = pancarte_service.imprimer(
            contexte.base(), sejour["id"], demain, utilisateur_id=contexte.utilisateur_id()
        )
        st.session_state["derniere_impression"] = snap["html"]
        st.session_state["nom_impression"] = f"feuille-lit{sejour['lit_admission']}-{demain}.html"
        st.success(f"Feuille de demain enregistrée — version {snap['version']}.")


def onglet_prescrit(sejour: dict) -> None:
    date_jour = st.date_input("Jour affiché", value=date.today(), key="date_prescrit")
    date_jour_str = str(date_jour)

    pancarte = prescriptions_service.pancarte_du_jour(contexte.base(), sejour["id"], date_jour_str)

    # La sédation est posée comme dispositif, pas prescrite en ligne : sans
    # cette reprise, la seule vitesse que l'infirmier règle sur une pompe
    # n'apparaissait nulle part sur l'écran du prescrit (demande du service,
    # 8 septembre). Elle est déjà reportée ainsi sur la feuille imprimée.
    sedation = _ligne_sedation(sejour, date_jour_str)
    voies_remplies = [
        v for v in listes.ORDRE_VOIES
        if pancarte["lignes_par_voie"].get(v) or (v == "PSE" and sedation)
    ]
    zone_pancarte, zone_ajout = st.columns([2.1, 1])

    # Les vitesses réglées dans la journée, lues une fois pour toutes : la
    # pancarte les affiche, le panneau du dessous les complète.
    vitesses_jour = {
        ligne["id"]: vitesses_service.par_heure(
            contexte.base(), vitesses_service.LIGNE, ligne["id"],
            ligne["vitesse"], date_jour_str,
        )
        for ligne in pancarte["lignes"] if ligne.get("vitesse") is not None
    }

    with zone_pancarte:
        st.metric("Entrées calculées / 24 h", f"{pancarte['bilan_entrees'].total_ml:.0f} mL")
        gauche, droite = st.columns(2)
        _afficher_pancarte(
            voies_remplies, pancarte, date_jour_str, gauche, droite, sedation, vitesses_jour,
        )
        _panneau_vitesses(sejour, pancarte, date_jour_str)
        _panneau_posologie(sejour, pancarte, date_jour_str)

    # Le panneau d'ajout reste à l'écran en permanence à côté de la pancarte
    # (capture du service) plutôt que dans un tiroir qu'il faut rouvrir à
    # chaque ligne — c'est le geste le plus répété de tout l'écran.
    with zone_ajout:
        if st.button("Imprimer la pancarte de ce jour", use_container_width=True):
            snap = pancarte_service.imprimer(
                contexte.base(), sejour["id"], date_jour_str, utilisateur_id=contexte.utilisateur_id()
            )
            st.session_state["derniere_impression"] = snap["html"]
            st.session_state["nom_impression"] = (
                f"feuille-lit{sejour['lit_admission']}-{date_jour_str}.html"
            )
            st.success(f"Feuille enregistrée — version {snap['version']}.")

        _pancarte_de_demain(sejour, date_jour_str)

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

        st.divider()
        _panneau_ajouter_ligne(sejour, date_jour_str)

    _actions_prescrit(sejour, pancarte, date_jour_str)


def _historique_fiches(sejour: dict) -> None:
    """Retrouver une fiche imprimée un autre jour.

    Chaque impression est un instantané figé (`pancarte_snapshot`) : le
    revoir montre la fiche telle qu'elle est sortie ce jour-là, même si le
    dossier a changé depuis — c'est la seule lecture fidèle d'un historique
    médico-légal.
    """
    snapshots = pancarte_service.snapshots_du_sejour(contexte.base(), sejour["id"])
    if not snapshots:
        return
    with st.expander(f"Anciennes fiches imprimées ({len(snapshots)})"):
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
        ancienne = pancarte_service.snapshot(contexte.base(), choix)
        if not ancienne:
            st.caption("Fiche introuvable — a-t-elle été purgée ?")
            return
        st.caption(
            f"Imprimée le {format_date_fr(ancienne['date_jour'])}"
            + (f" par {ancienne['imprime_par_nom']}" if ancienne.get("imprime_par_nom") else "")
        )
        st.download_button(
            "Télécharger cette version",
            data=ancienne["html"],
            file_name=f"feuille-lit{sejour['lit_admission']}-{ancienne['date_jour']}"
                      f"-v{ancienne['version']}.html",
            mime="text/html",
            key=f"dl_hist_{choix}",
        )
        st.components.v1.html(ancienne["html"], height=700, scrolling=True)


def _sedation_en_place(sejour: dict, date_jour_str: str):
    """La sédation en cours, s'il y en a une.

    Elle n'est pas prescrite en ligne : elle est posée comme dispositif, dans
    l'écran « Explorations et actes », avec sa molécule et sa vitesse. Mais
    c'est une seringue électrique comme une autre pour l'infirmier qui règle
    la pompe — elle se lit et se règle là où les seringues se règlent.
    """
    etats = dispositifs_service.etats(contexte.base(), sejour["id"], date_jour_str)
    return next((e for e in etats if e.type == "sedation" and e.en_place), None)


def _ligne_sedation(sejour: dict, date_jour_str: str) -> str | None:
    sedation = _sedation_en_place(sejour, date_jour_str)
    if sedation is None:
        return None
    details = sedation.details or {}
    texte = details.get("molecules") or "Sédation"
    par_heure = vitesses_service.par_heure(
        contexte.base(), vitesses_service.DISPOSITIF, sedation.id,
        details.get("vitesse"), date_jour_str,
    )
    if par_heure:
        texte += f" — {_texte_vitesses(par_heure)}"
    return f"{texte} <span style='color:{theme.GRIS}'>· {sedation.texte}</span>"


def _texte_vitesses(par_heure: dict[int, float]) -> str:
    """« 8 h : 25 · 16 h : 15 » — dans l'ordre de la journée du service."""
    return " · ".join(
        f"{heure} h : {champs.format_valeur(par_heure[heure])}"
        for heure in dom.heures_de_la_journee() if heure in par_heure
    )


def _elements_qui_coulent(sejour: dict, pancarte: dict, date_jour_str: str) -> list[dict]:
    """Tout ce qui coule ce jour-là : les lignes prescrites qui portent une
    vitesse, et la sédation posée comme dispositif."""
    elements = [
        {
            "cible": vitesses_service.LIGNE,
            "id": ligne["id"],
            "libelle": ligne["produit"],
            "initiale": ligne["vitesse"],
        }
        for ligne in pancarte["lignes"]
        if ligne.get("vitesse") is not None and ligne["statut"] == "active"
    ]
    sedation = _sedation_en_place(sejour, date_jour_str)
    if sedation is not None:
        details = sedation.details or {}
        elements.append({
            "cible": vitesses_service.DISPOSITIF,
            "id": sedation.id,
            "libelle": f"{details.get('molecules') or 'Sédation'} — sédation",
            "initiale": details.get("vitesse"),
        })
    return elements


def _panneau_vitesses(sejour: dict, pancarte: dict, date_jour_str: str) -> None:
    """Régler une vitesse à une heure donnée (demande du service, 8 septembre).

    Une seringue ne se règle pas une fois pour toutes : elle part à 25 cc/h et
    on la descend à 15 à 16 h. Jusqu'ici seule la vitesse de départ existait, et
    la suite se réécrivait à la main sur chaque feuille. Ce qui est noté ici
    s'imprime dans les cases horaires, à l'heure du réglage.
    """
    elements = _elements_qui_coulent(sejour, pancarte, date_jour_str)
    if not elements:
        return
    with st.expander("Vitesses des seringues et perfusions"):
        st.caption(
            "La journée du service va de 8 h à 8 h : une vitesse notée à 2 h "
            "appartient à la nuit de cette feuille-là, pas à la suivante."
        )
        heures = dom.heures_de_la_journee()
        for element in elements:
            par_heure = vitesses_service.par_heure(
                contexte.base(), element["cible"], element["id"],
                element["initiale"], date_jour_str,
            )
            st.markdown(f"**{element['libelle']}**")
            st.caption(_texte_vitesses(par_heure) or "Aucune vitesse notée ce jour-là.")
            cle = f"{element['cible']}_{element['id']}"
            c_heure, c_vitesse, c_bouton = st.columns([1, 1, 1])
            heure = c_heure.selectbox(
                "Heure", heures, format_func=lambda h: f"{h} h", key=f"vh_{cle}",
            )
            nouvelle = champs.nombre_saisi(c_vitesse.text_input(
                "Vitesse (cc/h)", value="", placeholder="ex. 15", key=f"vv_{cle}",
            ))
            if c_bouton.button("Noter", key=f"vb_{cle}", use_container_width=True):
                if nouvelle is None:
                    st.error("Indiquer la vitesse en cc/h.")
                else:
                    horodatage = dom.horodatage_dans_journee(date_jour_str, heure)
                    if element["cible"] == vitesses_service.DISPOSITIF:
                        # Un dispositif porte aussi sa vitesse courante sur sa
                        # carte : le service des dispositifs tient les deux.
                        dispositifs_service.regler_vitesse(
                            contexte.base(), element["id"], date_heure=horodatage,
                            vitesse=nouvelle, utilisateur_id=contexte.utilisateur_id(),
                        )
                    else:
                        vitesses_service.regler(
                            contexte.base(), cible=element["cible"], cible_id=element["id"],
                            date_heure=horodatage, vitesse=nouvelle,
                            utilisateur_id=contexte.utilisateur_id(),
                        )
                    st.rerun()


def _afficher_pancarte(
    voies_remplies, pancarte, date_jour_str, gauche, droite,
    sedation: str | None = None, vitesses_jour: dict | None = None,
) -> None:
    """Chaque traitement porte sa propre croix « X » : l'arrêter est un
    geste sur la ligne elle-même, plus une liste séparée à rouvrir."""
    for i, code_voie in enumerate(voies_remplies):
        lignes = pancarte["lignes_par_voie"].get(code_voie, [])
        colonne = gauche if i % 2 == 0 else droite
        couleur = theme.COULEUR_VOIE.get(code_voie, theme.GRIS)
        with colonne:
            with st.container(border=True):
                st.markdown(
                    f'<div class="rea-bloc-titre" style="color:{couleur}">'
                    f'{listes.VOIES[code_voie]["titre"]}</div>',
                    unsafe_allow_html=True,
                )
                if code_voie == "PSE" and sedation:
                    # Pas de croix : une sédation s'arrête depuis l'écran des
                    # actes, là où elle a été posée, avec sa date de retrait.
                    st.markdown(
                        f'<div style="font-size:.82rem;margin-left:2.3rem">{sedation}</div>',
                        unsafe_allow_html=True,
                    )
                for ligne in lignes:
                    # Trois colonnes plutôt qu'une phrase : le compteur, le
                    # produit, la dose. C'est le découpage du domaine, pour que
                    # la dose ne soit pas retranchée d'un texte déjà composé —
                    # elle finissait par s'afficher deux fois.
                    etiquette, produit, dose = dom.parties_ligne(ligne, date_jour_str)
                    classe_j = "rea-j" + (" rea-fin" if etiquette.dernier_jour else "")
                    marque = "" if etiquette.introduction else etiquette.texte
                    texte = (f'<span class="{classe_j}">{marque}</span> ' if marque else "") + produit
                    if etiquette.dernier_jour:
                        texte += ' <span class="rea-fin">← dernier jour</span>'
                    if etiquette.introduction:
                        texte = f'<span class="rea-j">Introduction</span> {produit}'

                    # Une vitesse réglée plusieurs fois dans la journée se lit
                    # heure par heure ; une seule valeur est déjà dans le
                    # libellé de la ligne.
                    # La suite des vitesses va sous la ligne, pas dedans : en
                    # ligne, elle repoussait la dose et cassait l'alignement
                    # de la colonne qu'on descend pour vérifier une posologie.
                    par_heure = (vitesses_jour or {}).get(ligne["id"]) or {}
                    sous_ligne = (
                        f'<div style="font-size:.78rem;color:{theme.GRIS};'
                        f'margin:-2px 0 2px 0">{_texte_vitesses(par_heure)}</div>'
                        if len(par_heure) > 1 else ""
                    )
                    active = ligne["statut"] == "active"
                    classe = "rea-p-ligne" + ("" if active else " arretee")
                    col_croix, col_texte = st.columns([1, 7])
                    with col_croix:
                        if active and st.button(
                            "X", key=f"arret_{ligne['id']}",
                            help="Arrêter ce traitement",
                        ):
                            prescriptions_service.arreter_ligne(
                                contexte.base(), ligne["id"], date_arret=date_jour_str,
                                utilisateur_id=contexte.utilisateur_id(),
                            )
                            st.rerun()
                    with col_texte:
                        # La dose part à droite, alignée d'une ligne à
                        # l'autre : c'est la colonne que l'œil descend pour
                        # vérifier une posologie.
                        st.markdown(
                            f'<div class="{classe}">'
                            f'<span class="rea-p-produit">{texte}</span>'
                            + (f'<span class="rea-p-dose">{dose}</span>' if dose else "")
                            + "</div>" + sous_ligne,
                            unsafe_allow_html=True,
                        )


def _panneau_posologie(sejour: dict, pancarte: dict, date_jour_str: str) -> None:
    """Changer la dose d'un traitement en cours, sans le rouvrir (SPEC §5.1).

    C'est le geste que ce panneau existe pour rendre naturel. Sans lui, adapter
    un Tienam à la fonction rénale se faisait en ajoutant une seconde ligne —
    et le compteur repartait à J1, alors que l'antibiothérapie court depuis la
    première dose. La durée rendue au comité des infections était fausse.

    Le changement vaut à partir du jour affiché : la pancarte des jours passés
    continue de montrer la dose qui y a été donnée.
    """
    modifiables = [
        ligne for ligne in pancarte["lignes"]
        if ligne["statut"] == "active" and ligne["voie"] not in ("SOINS", "KINE")
    ]
    if not modifiables:
        return
    with st.expander("Changer la dose d'un traitement en cours"):
        st.caption(
            "Le traitement garde sa date de début et son compteur de jours : "
            "seule la posologie change, à partir du jour affiché."
        )
        libelles = {
            ligne["id"]: f"{ligne['produit']} — {dom.dose_affichee(ligne) or 'sans dose'}"
            for ligne in modifiables
        }
        choix = st.selectbox(
            "Traitement", list(libelles), format_func=lambda i: libelles[i],
            index=None, placeholder="Choisir un traitement",
        )
        if not choix:
            return
        versions = prescriptions_service.posologies(contexte.base(), choix)
        if len(versions) > 1:
            st.caption("Historique : " + " · ".join(
                f"{format_date_fr(v['date_debut'])} : {dom.dose_affichee(v) or '—'}"
                + (f" ({v['motif_changement']})" if v["motif_changement"] else "")
                for v in versions
            ))
        courante = next(l for l in modifiables if l["id"] == choix)
        c1, c2, c3 = st.columns(3)
        dose = champs.nombre_saisi(c1.text_input(
            "Nouvelle dose", value="", placeholder="ex. 500", key=f"pd_{choix}"))
        unites = list(listes.UNITES)
        unite = c2.selectbox(
            "Unité", unites, key=f"pu_{choix}",
            index=unites.index(courante["unite"]) if courante["unite"] in unites else 0,
        )
        rythmes = listes.codes(listes.RYTHMES)
        rythme = c3.selectbox(
            "Rythme", rythmes, key=f"pr_{choix}",
            format_func=lambda c: listes.libelle(listes.RYTHMES, c),
            index=rythmes.index(courante["rythme"]) if courante["rythme"] in rythmes else 0,
        )
        motif = st.text_input(
            "Motif du changement", value="", key=f"pm_{choix}",
            placeholder="ex. adaptation à la fonction rénale",
        )
        if st.button("Enregistrer la nouvelle posologie", key=f"pb_{choix}",
                     type="primary"):
            if dose is None:
                st.error("Indiquer la nouvelle dose.")
            else:
                cree = prescriptions_service.changer_posologie(
                    contexte.base(), choix, a_partir_du=date_jour_str,
                    dose=dose, unite=unite, rythme=rythme,
                    motif=motif or None, utilisateur_id=contexte.utilisateur_id(),
                )
                if cree is None:
                    st.info("Posologie inchangée : rien n'a été enregistré.")
                else:
                    st.rerun()


def _panneau_ajouter_ligne(sejour: dict, date_jour_str: str) -> None:
    """« AJOUTER UNE LIGNE » — panneau permanent, pas un tiroir à rouvrir.

    La voie se choisit d'un clic sur un bouton (une par voie, toujours les
    mêmes couleurs qu'à l'affichage de la pancarte), plutôt que dans une
    liste déroulante : c'est le geste le plus répété de l'écran, capturé
    tel que le service l'a demandé.
    """
    st.markdown("**Ajouter une ligne**")
    voie = st.segmented_control(
        "Voie",
        listes.ORDRE_VOIES,
        format_func=lambda c: listes.VOIES[c]["titre"],
        default=listes.ORDRE_VOIES[0],
        key=f"voie_choisie_{sejour['id']}",
        label_visibility="collapsed",
    )
    if not voie:
        st.caption("Choisir une voie ci-dessus.")
        return

    # La date de début est hors du formulaire, à dessein : c'est elle qui fixe
    # le compteur de jours, et un traitement introduit pendant la garde se
    # saisit le lendemain (demande du service, 8 septembre). Dans le
    # formulaire, elle ne pourrait pas dire tout de suite quel « J » elle
    # produit — un formulaire Streamlit ne se réaffiche qu'une fois soumis.
    date_debut = st.date_input(
        "Début du traitement", value=date.fromisoformat(date_jour_str),
        key=f"debut_{voie}_{sejour['id']}",
    )
    jour_affiche = dom.etiquette_jour({"date_debut": str(date_debut)}, date_jour_str)
    if str(date_debut) != date_jour_str:
        st.caption(
            f"Introduit le {format_date_fr(str(date_debut))} — la pancarte du "
            f"{format_date_fr(date_jour_str)} l'affichera « {jour_affiche.texte} »."
        )

    champs_voie = listes.VOIES[voie]["champs"]
    with st.form(f"ajout_ligne_{voie}"):
        if voie == "ENTREES":
            # Les solutés se choisissent dans le catalogue : « SG5 », « G5% » et
            # « sérum glucosé 5 » désignaient le même produit sans jamais se
            # compter ensemble (demande du service, 8 septembre). La liste reste
            # ouverte — un produit absent s'écrit toujours à la main.
            catalogue = listes.PRODUITS_ENTREES
            connu = st.selectbox(
                "Produit", listes.codes(catalogue),
                format_func=lambda c: listes.libelle(catalogue, c),
                index=None, placeholder="Choisir un soluté ou une nutrition",
            )
            libre = st.text_input(
                "Autre produit", value="",
                placeholder="si absent de la liste ci-dessus",
            )
            produit = libre.strip() or (listes.libelle(catalogue, connu) if connu else "")
        else:
            produit = st.text_input("Produit / libellé")
        dose = unite = rythme = condition = None
        dilution = None
        nb_ampoules = vitesse = volume_dilution = volume_24h = None
        additifs = None
        sous_type = None
        duree_prevue = None

        # Chaque champ part vide, jamais à « 0 » : un zéro pré-rempli est
        # une valeur qu'il faut remarquer et effacer avant de taper la
        # vraie — une perte de temps répétée à chaque ligne de la pancarte.
        if "dilution" in champs_voie:
            dilution = st.text_input("Dilution (ex. 0,5 mg/cc)")
        if "dose" in champs_voie:
            c1, c2 = st.columns(2)
            dose = champs.nombre_saisi(c1.text_input("Dose", value="", placeholder="ex. 40"))
            unite = c2.selectbox("Unité", listes.UNITES)
        if "nb_ampoules" in champs_voie:
            # PO se compte en comprimés, les autres voies en ampoules — le
            # mot change, la valeur reste un nombre saisi par le médecin,
            # jamais déduit du dosage (SPEC §3.1).
            etiquette_unites = "Nombre de comprimés" if voie == "PO" else "Nombre d'ampoules"
            nb_ampoules = champs.nombre_saisi(
                st.text_input(etiquette_unites, value="", placeholder="ex. 1")
            )
        if "vitesse" in champs_voie:
            vitesse = champs.nombre_saisi(
                st.text_input("Vitesse (cc/h)", value="", placeholder="ex. 2")
            )
        heures_saisies = None
        if "rythme" in champs_voie:
            rythme = st.selectbox("Rythme", listes.codes(listes.RYTHMES), format_func=lambda c: listes.libelle(listes.RYTHMES, c))
            # L'heure de prise se choisit à la ligne. Laissée vide, elle suit
            # l'horaire habituel du produit et du rythme : 8 h pour une prise
            # unique, 20 h pour l'enoxaparine (demande du service,
            # 8 septembre). Le champ reste libre parce que le formulaire ne se
            # réaffiche pas tant qu'il n'est pas soumis : proposer une valeur
            # calculée ici la figerait au rythme affiché à l'ouverture.
            heures_saisies = st.text_input(
                "Heure(s) de prise", value="",
                placeholder="ex. 20 ou 8,14,20 — vide : horaire habituel",
            )
        if "condition" in champs_voie:
            condition = st.text_input("Condition (si conditionnel)")
        if "volume_dilution" in champs_voie:
            volume_dilution = champs.nombre_saisi(
                st.text_input("Volume de dilution (mL/prise)", value="", placeholder="ex. 50")
            )
        if "additifs" in champs_voie:
            # Chaque additif se coche avec son nombre d'ampoules, au lieu d'être
            # retapé en toutes lettres : « KCl 2 », « 2 amp KCl » et « +2K »
            # désignaient la même chose sans jamais se relire d'une feuille à
            # l'autre (demande du service, 8 septembre).
            choisis = st.multiselect(
                "Additifs", listes.codes(listes.ADDITIFS_PERFUSION),
                format_func=lambda c: listes.libelle(listes.ADDITIFS_PERFUSION, c),
                placeholder="Aucun additif",
            )
            quantites = []
            if choisis:
                colonnes = st.columns(min(len(choisis), 3))
                for i, code in enumerate(choisis):
                    nom = listes.libelle(listes.ADDITIFS_PERFUSION, code)
                    nombre = champs.nombre_saisi(colonnes[i % len(colonnes)].text_input(
                        nom, value="1", key=f"add_{voie}_{code}",
                    ))
                    quantites.append((nom, nombre))
            additifs = dom.texte_additifs(quantites)
        if "sous_type" in champs_voie:
            # Le catalogue sait déjà si le produit est une perfusion ou une
            # nutrition : la case s'ouvre dessus, sans empêcher d'en changer.
            sous_types = listes.codes(listes.SOUS_TYPES_ENTREES)
            attendu = listes.sous_type_du_produit(produit)
            sous_type = st.selectbox(
                "Type", sous_types,
                format_func=lambda c: listes.libelle(listes.SOUS_TYPES_ENTREES, c),
                index=sous_types.index(attendu) if attendu in sous_types else 0,
            )
        if "volume_24h" in champs_voie:
            volume_24h = champs.nombre_saisi(
                st.text_input("Volume /24 h (mL)", value="", placeholder="ex. 1500")
            )
        indication = None
        if voie not in ("SOINS", "KINE"):
            # Troisième élément d'identité de l'épisode, avec le produit et la
            # date de début (SPEC §5.1) : le même produit redonné pour autre
            # chose est un autre traitement, et sa durée se compte à part.
            indication = st.text_input(
                "Indication", value="", placeholder="ex. pneumopathie nosocomiale"
            )
        if voie in ("IV", "PSE"):
            duree_prevue = champs.nombre_saisi(
                st.text_input(
                    "Durée prévue (jours, si antibiotique)", value="", placeholder="ex. 7"
                )
            )

        if st.form_submit_button("Ajouter à la pancarte", type="primary", use_container_width=True):
            if not produit:
                st.error("Le produit est obligatoire.")
            elif contexte.controle(
                f"ligne_{voie}",
                coherence.verifier_prescription(
                    date_debut=date_debut,
                    duree_prevue_jours=int(duree_prevue) if duree_prevue else None,
                    dose=dose or None, vitesse=vitesse or None,
                    volume_24h=volume_24h or None,
                    date_admission=sejour["date_admission"],
                ),
                cible="prescription_ligne",
                ligne_id=sejour["id"],
            ):
                horaires = dom.analyser_horaires(heures_saisies)
                if horaires is None and rythme:
                    heures = dom.horaires_par_defaut(produit, rythme)
                    horaires = ",".join(str(h) for h in heures) or None
                prescriptions_service.ajouter_ligne(
                    contexte.base(), sejour_id=sejour["id"], voie=voie, produit=produit,
                    date_debut=str(date_debut), horaires_override=horaires,
                    dose=dose or None, unite=unite, rythme=rythme,
                    condition_texte=condition or None, dilution=dilution or None,
                    nb_ampoules=nb_ampoules or None, vitesse=vitesse or None,
                    volume_dilution=volume_dilution or None, volume_24h=volume_24h or None,
                    additifs=additifs or None, sous_type=sous_type,
                    duree_prevue_jours=int(duree_prevue) if duree_prevue else None,
                    indication=indication or None,
                    utilisateur_id=contexte.utilisateur_id(),
                )
                st.rerun()


def _actions_prescrit(sejour: dict, pancarte: dict, date_jour_str: str) -> None:
    with st.expander("Bilans à demander pour le lendemain"):
        demain = date_jour_str
        journee_bilans = prescriptions_service.pancarte_du_jour(contexte.base(), sejour["id"], demain)["bilans_demandes"]
        deja_coches = {b["examen_code"] for b in journee_bilans}
        with st.form("bilans_demandes"):
            choisis = st.multiselect(
                "Examens", listes.codes(listes.EXAMENS_A_DEMANDER),
                default=list(deja_coches),
                format_func=lambda c: listes.libelle(listes.EXAMENS_A_DEMANDER, c),
                placeholder="Aucun",
            )
            heure = st.text_input("Heure de prélèvement", value=config.HEURE_PRELEVEMENT_DEFAUT)
            if st.form_submit_button("Enregistrer les bilans"):
                prescriptions_service.definir_bilans_demandes(
                    contexte.base(), sejour["id"], demain, [(c, heure) for c in choisis],
                    utilisateur_id=contexte.utilisateur_id(),
                )
                st.rerun()

    if st.session_state.get("derniere_impression"):
        # La feuille est en A3 paysage : l'aperçu dans un cadre étroit ne
        # remplace pas une impression. Le téléchargement ouvre la feuille dans
        # un vrai onglet, où Ctrl+P sort la bonne page.
        st.download_button(
            "Ouvrir la feuille pour l'imprimer (A3 paysage)",
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
