"""Onglet Explorations et actes — dispositifs invasifs et leurs compteurs.
"""

from __future__ import annotations

from datetime import date, datetime

import streamlit as st

from .. import listes
from ..domaine import coherence
from ..domaine.dates import format_date_fr
from ..services import dispositifs as dispositifs_service
from ..services import explorations as explorations_service
from . import contexte, theme

from . import champs


def _reglage_vitesse(ligne: dict, etat_disp) -> None:
    """Régler la vitesse d'un dispositif qui coule — la sédation aujourd'hui.

    Une sédation se conduit surtout en descendant : l'allègement quotidien est
    le geste qui raccourcit la ventilation, et jusqu'ici la vitesse ne se
    saisissait qu'une fois, à la pose (demande du service, 8 septembre). La
    valeur réglée ici part telle quelle au bloc P.S.E. de la feuille imprimée,
    là où l'infirmier règle la pompe.
    """
    details = dict(etat_disp.details or {})
    actuelle = details.get("vitesse")
    c1, c2 = st.columns([1.3, 1])
    saisie = champs.nombre_saisi(c1.text_input(
        "Vitesse (cc/h)",
        value="" if actuelle is None else champs.format_valeur(actuelle),
        key=f"vitesse_{ligne['id']}", label_visibility="collapsed",
        placeholder="vitesse (cc/h)",
    ))
    if c2.button(
        "Régler", key=f"regler_vitesse_{ligne['id']}", use_container_width=True,
        help="Monter ou descendre la vitesse — la feuille imprimée suit.",
    ):
        if saisie is None:
            st.error("Indiquer la vitesse en cc/h.")
        else:
            # Le réglage est horodaté : c'est lui qui s'imprimera dans la case
            # de son heure, et c'est lui qui met à jour la vitesse courante du
            # dispositif. Sans cette trace, redescendre une sédation effacerait
            # la vitesse d'avant et réécrirait les feuilles des jours passés.
            dispositifs_service.regler_vitesse(
                contexte.base(), ligne["id"],
                date_heure=datetime.now().isoformat(timespec="minutes"),
                vitesse=saisie, utilisateur_id=contexte.utilisateur_id(),
            )
            st.rerun()


def onglet_actes(sejour: dict) -> None:
    lignes = dispositifs_service.du_sejour(contexte.base(), sejour["id"])
    etats = dispositifs_service.etats(contexte.base(), sejour["id"])

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
                    config_type = listes.TYPES_DISPOSITIF.get(ligne["type"], {})
                    if config_type.get("champs") and "vitesse" in config_type["champs"]:
                        _reglage_vitesse(ligne, etat_disp)
                    # Un type peut déclarer ses motifs de retrait : une
                    # extubation accidentelle et une extubation programmée ne
                    # se lisent pas pareil, et seule la première est un
                    # événement à compter.
                    motifs = config_type.get("motifs_retrait") or []
                    motif_retrait = None
                    if motifs:
                        motif_retrait = st.selectbox(
                            "Motif du retrait", [c for c, _l in motifs],
                            format_func=lambda c: listes.libelle(motifs, c),
                            key=f"motif_retrait_{ligne['id']}",
                            label_visibility="collapsed",
                        )
                    c1, c2 = st.columns([1.3, 1])
                    date_retrait = c1.date_input(
                        "Date", value=date.today(), key=f"retrait_date_{ligne['id']}",
                        label_visibility="collapsed",
                    )
                    if c2.button(
                        config_type.get("verbe_retrait", "Retirer"),
                        key=f"retrait_{ligne['id']}", use_container_width=True,
                    ) and contexte.controle(
                        f"retrait_{ligne['id']}",
                        coherence.verifier_dispositif(
                            date_pose=etat_disp.date_pose,
                            date_retrait=date_retrait,
                            date_admission=sejour["date_admission"],
                        ),
                        cible="dispositif",
                        ligne_id=ligne["id"],
                    ):
                        dispositifs_service.retirer(
                            contexte.base(), ligne["id"], date_retrait=str(date_retrait),
                            motif_retrait=motif_retrait,
                            utilisateur_id=contexte.utilisateur_id(),
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

    with st.expander("Poser un dispositif / noter un acte"):
        type_ = st.selectbox(
            "Type", listes.ORDRE_DISPOSITIFS, format_func=listes.libelle_dispositif,
            key="type_dispositif",
        )
        config_type = listes.TYPES_DISPOSITIF[type_]
        # Un deuxième épisode du même type ne porte pas le même nom : après une
        # extubation, réintuber n'est pas intuber (demande du service,
        # 8 septembre). Le logiciel le dit avant la saisie, et le compteur
        # d'épisodes s'en charge ensuite tout seul.
        deja = [l for l in lignes if l["type"] == type_]
        if deja and config_type.get("libelle_repete"):
            st.caption(
                f"Déjà {len(deja)} épisode(s) enregistré(s) : celui-ci comptera "
                f"comme une {config_type['libelle_repete'].lower()}."
            )
        # Poser le drain ici, en relever le volume là-bas : le dire évite de
        # chercher un champ « volume » qui n'existe pas sur cet écran.
        if config_type.get("draine"):
            st.caption(
                "Une fois posé, son recueil des 24 h se relève dans "
                "l'évolution, plan hémodynamique — il entre alors dans le "
                "bilan hydrique."
            )
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
                    details[champ] = champs.nombre_saisi(st.text_input(etiquette, value=""))
            commentaire = st.text_input("Commentaire (facultatif)")
            if st.form_submit_button("Enregistrer") and contexte.controle(
                f"pose_{type_}",
                coherence.verifier_dispositif(
                    date_pose=date_pose, date_admission=sejour["date_admission"]
                ),
                cible="dispositif",
                ligne_id=sejour["id"],
            ):
                dispositifs_service.poser(
                    contexte.base(), sejour_id=sejour["id"], type_=type_, date_pose=str(date_pose),
                    site=site, details={k: v for k, v in details.items() if v},
                    commentaire=commentaire or None, utilisateur_id=contexte.utilisateur_id(),
                )
                st.rerun()

    st.divider()
    explos = explorations_service.du_sejour(contexte.base(), sejour["id"])
    if not explos:
        st.caption("Aucune exploration enregistrée.")
    else:
        theme.bloc(
            "Explorations du séjour",
            [
                f"<span style='color:{theme.GRIS}'>{format_date_fr(e['date_heure'][:10])}</span> "
                f"{explorations_service.texte_exploration(contexte.base(), e)[2:]}"
                for e in explos[:15]
            ],
            theme.VIOLET,
        )

    with st.expander("Ajouter une exploration"):
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
            champs_exploration = definition["valeurs"]
            if champs_exploration:
                cols = st.columns(min(len(champs_exploration), 4))
                for i, (cle, libelle_v, unite, type_v) in enumerate(champs_exploration):
                    etiquette = f"{libelle_v} ({unite})" if unite else libelle_v
                    with cols[i % len(cols)]:
                        if type_v == "nombre":
                            valeurs[cle] = champs.nombre_saisi(st.text_input(
                                etiquette, value="", key=f"expl_{type_expl}_{cle}",
                            ))
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
                    contexte.base(), sejour_id=sejour["id"], date_heure=date_heure, type_=type_expl,
                    valeurs={k: v for k, v in valeurs.items() if v not in (None, "", 0, 0.0)},
                    conclusion=conclusion or None, operateur=operateur or None,
                    utilisateur_id=contexte.utilisateur_id(),
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
        with st.expander("Cinétique d'une valeur d'exploration"):
            choix = st.selectbox(
                "Valeur", candidats,
                format_func=lambda x: f"{listes.TYPES_EXPLORATION[x[0]]['libelle']} — {x[2]}",
            )
            historique = explorations_service.historique_valeur(contexte.base(), sejour["id"], choix[0], choix[1])
            if len(historique) >= 2:
                theme.courbe(
                    [(h["date_heure"][:16].replace("T", " "), h["valeur_num"]) for h in historique]
                )
            else:
                st.caption("Au moins deux mesures sont nécessaires pour tracer une courbe.")
