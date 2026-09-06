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
from ..services import pancarte as pancarte_service
from ..services import prescriptions as prescriptions_service
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

    voies_remplies = [
        v for v in listes.ORDRE_VOIES if pancarte["lignes_par_voie"].get(v)
    ]
    zone_pancarte, zone_ajout = st.columns([2.1, 1])

    with zone_pancarte:
        st.metric("Entrées calculées / 24 h", f"{pancarte['bilan_entrees'].total_ml:.0f} mL")
        gauche, droite = st.columns(2)
        _afficher_pancarte(voies_remplies, pancarte, date_jour_str, gauche, droite)

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

    champs_voie = listes.VOIES[voie]["champs"]
    with st.form(f"ajout_ligne_{voie}"):
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
        if "rythme" in champs_voie:
            rythme = st.selectbox("Rythme", listes.codes(listes.RYTHMES), format_func=lambda c: listes.libelle(listes.RYTHMES, c))
        if "condition" in champs_voie:
            condition = st.text_input("Condition (si conditionnel)")
        if "volume_dilution" in champs_voie:
            volume_dilution = champs.nombre_saisi(
                st.text_input("Volume de dilution (mL/prise)", value="", placeholder="ex. 50")
            )
        if "additifs" in champs_voie:
            additifs = st.text_input("Additifs (ex. + 3 KCl + 2 NaCl)")
        if "sous_type" in champs_voie:
            sous_type = st.selectbox("Type", listes.codes(listes.SOUS_TYPES_ENTREES), format_func=lambda c: listes.libelle(listes.SOUS_TYPES_ENTREES, c))
        if "volume_24h" in champs_voie:
            volume_24h = champs.nombre_saisi(
                st.text_input("Volume /24 h (mL)", value="", placeholder="ex. 1500")
            )
        if voie in ("IV", "PSE"):
            duree_prevue = champs.nombre_saisi(
                st.text_input(
                    "Durée prévue (jours, si antibiotique)", value="", placeholder="ex. 7"
                )
            )

        date_debut = st.date_input(
            "Début", value=date.fromisoformat(date_jour_str), key=f"debut_{voie}"
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
                prescriptions_service.ajouter_ligne(
                    contexte.base(), sejour_id=sejour["id"], voie=voie, produit=produit,
                    date_debut=str(date_debut),
                    dose=dose or None, unite=unite, rythme=rythme,
                    condition_texte=condition or None, dilution=dilution or None,
                    nb_ampoules=nb_ampoules or None, vitesse=vitesse or None,
                    volume_dilution=volume_dilution or None, volume_24h=volume_24h or None,
                    additifs=additifs or None, sous_type=sous_type,
                    duree_prevue_jours=int(duree_prevue) if duree_prevue else None,
                    utilisateur_id=contexte.utilisateur_id(),
                )
                st.rerun()


def _actions_prescrit(sejour: dict, pancarte: dict, date_jour_str: str) -> None:
    with st.expander("Arrêter une ligne"):
        actives = [l for l in pancarte["lignes"] if l["statut"] == "active"]
        if not actives:
            st.caption("Aucune ligne active.")
        for ligne in actives:
            col1, col2 = st.columns([6, 1])
            col1.write(dom.libelle_ligne(ligne, date_jour_str))
            if col2.button("Arrêter", key=f"arret_{ligne['id']}", use_container_width=True):
                prescriptions_service.arreter_ligne(
                    contexte.base(), ligne["id"], date_arret=date_jour_str, utilisateur_id=contexte.utilisateur_id()
                )
                st.rerun()

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
