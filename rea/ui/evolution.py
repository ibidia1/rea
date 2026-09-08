"""Onglet Évolution — check-list quotidienne, rappels, scores, quatre plans.
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from .. import listes
from ..domaine.dates import format_date_fr
from ..services import aides as aides_service
from ..services import definitions_cliniques
from ..services import evolution as evolution_service
from ..services import scores as scores_service
from . import contexte, theme

from . import champs


_STYLE_GRAVITE = {
    "alerte": theme.ROUGE,
    "attention": theme.ORANGE,
    "info": theme.BLEU,
}


def _champ_element(cle: str, libelle: str, unite: str, type_: str, plage: str,
                   valeur_actuelle, prefixe: str):
    """Un élément fixe d'un plan. Même principe que les bilans : champ vide,
    plage normale en gris, et l'unité dans le libellé."""
    etiquette = f"{libelle} ({unite})" if unite else libelle
    cle_widget = f"{prefixe}_{cle}"
    if type_ == "nombre":
        return champs.nombre_saisi(
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


def panneau_aides(sejour: dict, date_jour_str: str) -> None:
    """Rappels du jour — des questions, jamais des consignes.

    La check-list FAST HUG occupait la moitié de l'écran pour redire ce que
    l'interne relit déjà dans les quatre plans juste en dessous ; le service
    l'a fait retirer (8 septembre). Le moteur de règles qui la calculait
    (`regles/*.json`, `services.aides.checklist`) reste en place : ce sont les
    mêmes règles qui produisent les rappels ci-dessous, et la check-list se
    rebranche en une ligne si le service la redemande.
    """
    rappels = aides_service.rappels(contexte.base(), sejour["id"], date_jour_str)
    if rappels:
        # En colonnes plutôt qu'empilés : un rappel par bloc pleine largeur
        # repousserait les quatre plans hors de l'écran.
        colonnes = st.columns(min(len(rappels), 3))
        for i, r in enumerate(rappels):
            note = "" if r["valide"] else (
                "<br><span style='color:#94a3b8;font-size:0.78rem'>"
                "Règle de service non encore signée par un senior.</span>"
            )
            with colonnes[i % len(colonnes)]:
                theme.bloc_html(
                    r["libelle"], r["message"] + note,
                    _STYLE_GRAVITE.get(r["gravite"], theme.GRIS),
                )
    else:
        theme.bloc_html("Rappels", "Aucun rappel déclenché aujourd'hui.", theme.VERT)
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
    with st.expander("Scores de gravité"):
        # Le score du jour est affiché de toute façon : autant garder une
        # trace datée pour la recherche (bloc 9), plutôt qu'un calcul qui ne
        # laisse rien derrière lui une fois l'écran refermé.
        scores_service.historiser(
            contexte.base(), sejour["id"], date_jour_str, utilisateur_id=contexte.utilisateur_id()
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            _bloc_score(scores_service.sofa(contexte.base(), sejour["id"], date_jour_str))
            st.caption(
                "Composante circulatoire limitée à la PAM : les paliers "
                "supérieurs dépendent de la dose de vasopresseur, que le "
                "logiciel ne saisit pas."
            )
        with c2:
            score = scores_service.igs2(contexte.base(), sejour["id"])
            mortalite = scores_service.mortalite_predite(contexte.base(), sejour["id"])
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
            jsv = scores_service.jours_sans_ventilation(contexte.base(), sejour["id"])
            theme.bloc_html(
                "Jours sans ventilation (J28)",
                f"<span style='font-size:1.6rem;font-weight:600'>{jsv}</span>"
                if jsv is not None else
                "<span style='color:#94a3b8'>Pas encore calculable — "
                "période de 28 jours non écoulée.</span>",
                theme.BLEU if jsv is not None else theme.GRIS,
            )
            st.caption("Un patient décédé compte 0, quelle qu'ait été sa durée de ventilation.")

        serie = scores_service.evolution_sofa(contexte.base(), sejour["id"])
        if len(serie) >= 2:
            st.caption("SOFA jour par jour — c'est sa variation qui informe.")
            theme.courbe([(str(d), v) for d, v in serie], hauteur=140)

    panneau_definitions(sejour, date_jour_str)


def _bloc_definition(verdict) -> None:
    if not verdict.applicable:
        theme.bloc_html(
            verdict.definition,
            "<span style='color:#94a3b8'>Non applicable — manque "
            f"{', '.join(verdict.manquants)}</span>",
            theme.GRIS,
        )
        return
    theme.bloc_html(
        verdict.definition,
        f"<span style='font-size:1.15rem;font-weight:600'>{verdict.texte.split(': ', 1)[-1]}</span>",
        theme.ROUGE if verdict.rempli else theme.BLEU,
    )


def panneau_definitions(sejour: dict, date_jour_str: str) -> None:
    """Définitions standard du bloc 15 : SDRA (Berlin), IRA (KDIGO), qSOFA,
    Sepsis-3. Le logiciel signale que les critères sont réunis, il ne code
    rien à la place du médecin (feuille de route, bloc 15).

    Sepsis-3 demande un jugement clinique (infection suspectée) qu'aucune
    donnée saisie ne permet de déduire — un antibiotique peut être
    prophylactique. Les cases ci-dessous ne sont donc pas enregistrées : elles
    ne font que composer l'affichage du jour, comme un calcul de tête qu'on
    évite de refaire. Le lactate se relit du dernier gaz du sang quand il y en
    a un ; le champ ne sert qu'à combler son absence.
    """
    with st.expander("Définitions (Berlin, KDIGO, Sepsis-3)"):
        c1, c2 = st.columns(2)
        with c1:
            _bloc_definition(definitions_cliniques.sdra(contexte.base(), sejour["id"], date_jour_str))
        with c2:
            _bloc_definition(definitions_cliniques.ira(contexte.base(), sejour["id"], date_jour_str))

        st.divider()
        c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
        infection = c1.checkbox("Infection suspectée", key=f"def_infect_{sejour['id']}_{date_jour_str}")
        vaso = c2.checkbox("Vasopresseurs", key=f"def_vaso_{sejour['id']}_{date_jour_str}")
        hypotension = c3.checkbox(
            "Hypotension persistante", key=f"def_hypo_{sejour['id']}_{date_jour_str}"
        )
        lactate_txt = c4.text_input("Lactate (mmol/L)", key=f"def_lactate_{sejour['id']}_{date_jour_str}")
        c1, c2 = st.columns(2)
        with c1:
            _bloc_definition(definitions_cliniques.qsofa(contexte.base(), sejour["id"], date_jour_str))
        with c2:
            _bloc_definition(definitions_cliniques.sepsis(
                contexte.base(), sejour["id"], date_jour_str,
                infection_suspectee=infection, vasopresseurs=vaso,
                hypotension_persistante=hypotension,
                lactate=champs.nombre_saisi(lactate_txt),
            ))


def _bloc_escarres(sejour: dict, date_jour_str: str) -> None:
    """Une escarre est un risque infectieux — elle vit avec le plan
    infectieux, pas dans un tiroir séparé sans rapport (remarque du
    service, 6 septembre)."""
    st.caption("Escarres")
    existantes = evolution_service.escarres(contexte.base(), sejour["id"])
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
                contexte.base(), e["id"], {"date_guerison": date_jour_str},
                utilisateur_id=contexte.utilisateur_id(),
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
                contexte.base(), sejour_id=sejour["id"], localisation=localisation,
                grade=grade, date_constat=date_jour_str,
                utilisateur_id=contexte.utilisateur_id(),
            )
            st.rerun()


def onglet_evolution(sejour: dict) -> None:
    date_jour = st.date_input("Jour", value=date.today(), key="date_evolution")
    date_jour_str = str(date_jour)
    panneau_aides(sejour, date_jour_str)
    entree = evolution_service.obtenir_ou_creer(
        contexte.base(), sejour["id"], date_jour_str, utilisateur_id=contexte.utilisateur_id()
    )
    elements_existants = evolution_service.elements_du_jour(
        contexte.base(), sejour["id"], date_jour_str
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
                            contexte.base(), sejour["id"], plan, date_jour_str
                        )
                        if auto:
                            st.caption(auto)
                        for champ in listes.ELEMENTS_PLAN.get(plan, ()):
                            cle, libelle, unite, type_, plage = champ
                            elements[cle] = _champ_element(
                                cle, libelle, unite, type_, plage,
                                elements_existants.get(cle), f"evo_{date_jour_str}",
                            )
                        if cle_plan == "plan_infectieux":
                            _bloc_escarres(sejour, date_jour_str)
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
                contexte.base(), sejour["id"], date_jour_str, mesures, utilisateur_id=contexte.utilisateur_id()
            )
            evolution_service.enregistrer(
                contexte.base(), sejour["id"], date_jour_str,
                {
                    **{p: elements.get(f"__libre__{p}", "") for p in plans},
                    "conduite": conduite,
                },
                utilisateur_id=contexte.utilisateur_id(),
            )
            st.success("Évolution enregistrée.")
            st.rerun()

    with rendu:
        texte = evolution_service.texte_genere(contexte.base(), sejour["id"], date_jour_str)
        st.text_area("Prêt à copier dans le DMI", value=texte, height=640)
