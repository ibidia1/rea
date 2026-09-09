"""Onglet Évolution — check-list quotidienne, rappels, scores, quatre plans,
avis spécialisés.
"""

from __future__ import annotations

import json
from datetime import date

import streamlit as st

from .. import listes
from ..db import ConflitDeVersion
from ..domaine import avis as dom_avis
from ..domaine import prescription as dom
from ..domaine.dates import format_date_fr, parse_date
from ..services import aides as aides_service
from ..services import avis as avis_service
from ..services import definitions_cliniques
from ..services import evolution as evolution_service
from ..services import prescriptions as prescriptions_service
from ..services import scores as scores_service
from . import contexte, theme

from . import champs


_STYLE_GRAVITE = {
    "alerte": theme.ROUGE,
    "attention": theme.ORANGE,
    "info": theme.BLEU,
}


def _texte_nombre(valeur) -> str:
    """« 96 » et « 38,6 », jamais « 96.0 ».

    Les valeurs reviennent de colonnes REAL : sans ce passage, une fréquence
    cardiaque relue le lendemain s'affichait « 96,0 », et le zéro décimal se
    réenregistrait tel quel à chaque relecture.
    """
    if valeur is None:
        return ""
    return champs.format_valeur(valeur).replace(".", ",")


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
                value=_texte_nombre(valeur_actuelle),
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


def _champs_drains(sejour: dict, date_jour_str: str, elements: dict, prefixe: str) -> None:
    """Un champ par drain en place — et rien du tout s'il n'y en a pas.

    Le volume recueilli se relève drain par drain (demande du service,
    8 septembre) : c'est ce qui entre dans les sorties du bilan hydrique, à
    côté de la diurèse.
    """
    drains = evolution_service.drains_du_jour(contexte.base(), sejour["id"], date_jour_str)
    if not drains:
        return
    st.caption("Recueil des drains")
    for drain in drains:
        elements[drain["cle"]] = champs.nombre_saisi(
            st.text_input(
                f"{drain['libelle']} (mL)",
                value=_texte_nombre(drain["valeur"]),
                placeholder="mL /24 h",
                key=f"{prefixe}_{drain['cle']}",
            )
        )


def _valeur_en_cours(prefixe: str, cle: str, sauvegardees: dict) -> float | None:
    """La valeur telle qu'elle est à l'écran, sinon celle déjà enregistrée.

    Le bilan hydrique se recalcule pendant qu'on tape, avant d'enregistrer :
    il lit donc les champs affichés. La température, saisie dans le plan
    infectieux, est rendue après le plan hémodynamique — d'où la lecture par
    clé de widget plutôt que par la variable, qui n'existe pas encore.
    """
    saisie = st.session_state.get(f"{prefixe}_{cle}")
    if isinstance(saisie, str):
        valeur = champs.nombre_saisi(saisie)
        if valeur is not None:
            return valeur
    sauvegardee = sauvegardees.get(cle)
    return sauvegardee if isinstance(sauvegardee, (int, float)) else None


def _bloc_bilan_hydrique(sejour: dict, date_jour_str: str, elements: dict,
                         prefixe: str, sauvegardees: dict) -> None:
    """Entrées − (diurèse + drains + pertes insensibles).

    Formule arrêtée par le service le 8 septembre 2026 ; ses constantes sont
    dans `referentiels/bilan_hydrique.json`, pas dans le code. Le bilan
    n'affiche rien tant qu'il manque une donnée : un chiffre inventé dans un
    bilan hydrique est pire que pas de chiffre du tout.
    """
    drains = [
        (d["libelle"], float(elements[d["cle"]]))
        for d in evolution_service.drains_du_jour(contexte.base(), sejour["id"], date_jour_str)
        if elements.get(d["cle"]) is not None
    ]
    bilan = dom.bilan_hydrique(
        prescriptions_service.lignes_actives_le(contexte.base(), sejour["id"], date_jour_str),
        diurese_ml=_valeur_en_cours(prefixe, "diurese_24h", sauvegardees),
        drains=drains,
        poids_kg=sejour.get("poids_kg"),
        temperature_c=_valeur_en_cours(prefixe, "temperature", sauvegardees),
    )

    if bilan.net_ml is None:
        theme.bloc_html(
            "Bilan hydrique /24 h",
            "<span style='color:#94a3b8'>Non calculable — il manque "
            + " et ".join(bilan.manquants) + ".</span>",
            theme.GRIS,
        )
        return

    detail = [
        f"Entrées {champs.format_valeur(round(bilan.entrees_ml))} mL",
        f"Diurèse {champs.format_valeur(round(bilan.diurese_ml))} mL",
    ]
    if bilan.drains_ml:
        detail.append(f"Drains {champs.format_valeur(round(bilan.drains_ml))} mL")
    detail.append(
        f"Pertes insensibles {champs.format_valeur(round(bilan.pertes_insensibles_ml))} mL"
    )
    signe = "+" if bilan.net_ml > 0 else ""
    note = f"{bilan.formule_insensibles} — {_texte_nombre(bilan.poids_kg)} kg"
    if bilan.majoration_fievre_ml:
        note += (
            f", {_texte_nombre(bilan.temperature_c)} °C "
            f"(+ {_texte_nombre(round(bilan.majoration_fievre_ml))} mL)"
        )
    theme.bloc_html(
        "Bilan hydrique /24 h",
        f"<span style='font-size:1.4rem;font-weight:600'>{signe}"
        f"{champs.format_valeur(round(bilan.net_ml))} mL</span>"
        f"<br><span style='font-size:.8rem'>{' · '.join(detail)}</span>"
        f"<br><span style='color:#94a3b8;font-size:.75rem'>{note}</span>",
        theme.BLEU,
    )


def _bloc_avis(sejour: dict, date_jour_str: str) -> None:
    """Les avis demandés aux autres spécialités — un bloc à part.

    Ce sont des consignes datées et signées, pas du commentaire : écrits dans
    le texte libre d'un plan, ils disparaissaient à sa première réécriture et
    personne ne savait plus qui avait dit quoi ni quand (demande du service,
    8 septembre).

    Ils ont d'abord été rangés sous le plan infectieux, parce que c'est là
    qu'on décide de rappeler un chirurgien. À l'usage c'était faux : on demande
    un avis de cardiologie sur un trouble du rythme, de néphrologie sur une
    épuration — la moitié des avis n'a rien d'infectieux. Ils sortent donc des
    quatre plans et forment leur propre section (demande du service,
    9 septembre).
    """
    liste, ajout = st.columns([3, 2])

    with liste:
        for a in avis_service.du_sejour(contexte.base(), sejour["id"]):
            col1, col2 = st.columns([8, 1])
            col1.markdown(
                f"<div style='font-size:.82rem'>{dom_avis.ligne_avis(a)}</div>",
                unsafe_allow_html=True,
            )
            if col2.button("X", key=f"avis_suppr_{a['id']}",
                           help="Retirer cet avis (saisi par erreur)"):
                avis_service.supprimer(contexte.base(), a["id"],
                                       utilisateur_id=contexte.utilisateur_id())
                st.rerun()

    with ajout, st.form(f"ajout_avis_{date_jour_str}"):
        c1, c2, c3 = st.columns([2, 2, 1])
        specialite = c1.selectbox(
            "Spécialité", listes.codes(listes.SPECIALITES_AVIS),
            format_func=lambda c: listes.SPECIALITES_AVIS[
                listes.codes(listes.SPECIALITES_AVIS).index(c)][2],
            index=None, placeholder="Choisir une spécialité",
        )
        nom = c2.text_input("Nom", value="", placeholder="ex. Ben Salah")
        grades = listes.codes(listes.GRADES_AVIS)
        grade = c3.selectbox(
            "Grade", grades,
            format_func=lambda g: listes.GRADES_AVIS[grades.index(g)][2],
        )
        # L'avis peut avoir été donné hier soir et n'être saisi que ce matin :
        # c'est sa date qui compte, pas celle de la frappe.
        date_avis = st.date_input("Date de l'avis", value=parse_date(date_jour_str))
        texte = st.text_area(
            "Avis", value="", height=70,
            placeholder="ex. Pas d'indication chirurgicale, adresser en consultation externe",
        )
        if st.form_submit_button("Ajouter l'avis"):
            if not specialite or not texte.strip():
                st.error("La spécialité et le texte de l'avis sont nécessaires.")
            else:
                avis_service.demander(
                    contexte.base(), sejour_id=sejour["id"], specialite=specialite,
                    texte=texte.strip(), date_avis=str(date_avis),
                    nom=nom.strip() or None, grade=grade,
                    utilisateur_id=contexte.utilisateur_id(),
                )
                st.rerun()


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


def _composant_html():
    """Le composant HTML de Streamlit, quel que soit son nom dans la version
    installée.

    `st.components.v1.html` est déprécié depuis la 1.63 au profit de
    `st.iframe`. Avoir suivi l'avertissement a cassé l'écran sur le poste du
    service, qui tourne une version antérieure où `st.iframe` n'existe pas
    encore : `AttributeError`, et l'Évolution ne s'affichait plus du tout.

    Le poste du service n'est pas mis à jour d'un clic — il est hors ligne, et
    on ne touche pas à son environnement pendant qu'il porte les patients. Le
    logiciel prend donc ce qui est là : le nom récent d'abord, l'ancien sinon.
    """
    return getattr(st, "iframe", None) or st.components.v1.html


def _bouton_copier(texte: str) -> None:
    """Le compte rendu part au presse-papiers sans s'afficher.

    Il occupait la moitié droite de l'écran — 640 pixels de haut — pour n'être
    lu par personne : on le relit dans le DMI après l'avoir collé, pas ici. Les
    quatre plans, eux, se saisissaient dans ce qu'il restait. Le texte s'en va,
    la page entière revient à la saisie, et il ne reste qu'un bouton, en bas.

    Deux chemins vers le presse-papiers, parce qu'un seul ne suffit pas :
    `navigator.clipboard` quand le navigateur l'accorde, `execCommand('copy')`
    sinon — l'iframe d'un composant Streamlit n'a pas toujours la permission
    `clipboard-write`. Et si les deux échouent, le bouton le dit : un bouton
    qui ne copie rien en silence est pire que pas de bouton, puisqu'on colle
    dans le DMI sans regarder.
    """
    if not texte.strip():
        # Un bouton qui copie le vide se remarque au moment où on colle, dans
        # le DMI, c'est-à-dire trop tard.
        st.caption("Rien à copier : la journée n'est pas encore renseignée.")
        return

    # `json.dumps` échappe les guillemets, pas `</script>` : un commentaire qui
    # contiendrait cette suite fermerait la balise et casserait le bouton.
    charge = json.dumps(texte).replace("</", "<\\/")
    _composant_html()(
        f"""
        <style>
          body {{ margin: 0; }}
          button {{
            width: 100%; padding: .55rem; cursor: pointer;
            font: 600 .95rem/1.2 "Source Sans Pro", system-ui, sans-serif;
            color: {theme.BLEU}; background: #fff;
            border: 1px solid {theme.BORDURE}; border-radius: .5rem;
          }}
          button:hover {{ border-color: {theme.BLEU}; }}
        </style>
        <button id="copier">Copier le compte rendu du jour</button>
        <script>
          const texte = {charge};
          const bouton = document.getElementById("copier");
          const dire = (m) => {{
            bouton.textContent = m;
            setTimeout(() => bouton.textContent =
              "Copier le compte rendu du jour", 2000);
          }};
          bouton.onclick = async () => {{
            try {{
              await navigator.clipboard.writeText(texte);
              dire("Copié");
            }} catch (e) {{
              const zone = document.createElement("textarea");
              zone.value = texte;
              document.body.appendChild(zone);
              zone.select();
              const ok = document.execCommand("copy");
              zone.remove();
              dire(ok ? "Copié" : "Copie impossible — voir la feuille imprimée");
            }}
          }};
        </script>
        """,
        height=46,
    )


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
                    if cle_plan == "plan_hemodynamique":
                        _champs_drains(
                            sejour, date_jour_str, elements, f"evo_{date_jour_str}"
                        )
                    if cle_plan == "plan_infectieux":
                        _bloc_escarres(sejour, date_jour_str)
                    texte_libre = st.text_area(
                        "Commentaire", value=entree.get(cle_plan) or "", height=80,
                        key=f"evo_libre_{date_jour_str}_{cle_plan}",
                        label_visibility="collapsed", placeholder="Commentaire libre…",
                    )
                    elements[f"__libre__{cle_plan}"] = texte_libre
                    if cle_plan == "plan_hemodynamique":
                        # Sous la carte, pas dedans : le bilan est une
                        # synthèse, il se lit après ce qui le compose.
                        _bloc_bilan_hydrique(
                            sejour, date_jour_str, elements,
                            f"evo_{date_jour_str}", elements_existants,
                        )

    with st.container(border=True):
        st.markdown(
            f'<div class="rea-bloc-titre" style="color:{theme.BLEU}">'
            "Avis spécialisés</div>",
            unsafe_allow_html=True,
        )
        _bloc_avis(sejour, date_jour_str)

    conduite = st.text_area(
        "Conduite", value=entree.get("conduite") or "", height=90,
        key=f"evo_conduite_{date_jour_str}",
    )

    if st.button("Enregistrer l'évolution", type="primary", use_container_width=True):
        mesures = {k: v for k, v in elements.items() if not k.startswith("__libre__")}
        try:
            evolution_service.enregistrer_journee(
                contexte.base(), sejour["id"], date_jour_str,
                elements=mesures,
                textes={
                    **{p: elements.get(f"__libre__{p}", "") for p in plans},
                    "conduite": conduite,
                },
                # La version lue à l'ouverture de l'écran : si elle a bougé,
                # quelqu'un d'autre a enregistré entre-temps.
                version_attendue=entree["version"],
                utilisateur_id=contexte.utilisateur_id(),
            )
        except ConflitDeVersion:
            # Refuser, dire pourquoi, ne rien écraser. Pas de fusion : ce
            # qui est à l'écran reste à l'écran, le temps de relire.
            st.error(
                "Quelqu'un d'autre a enregistré cette évolution pendant que "
                "vous la remplissiez. Rien n'a été écrasé. Rouvrez le jour "
                "pour lire ce qui est enregistré, puis reportez vos ajouts."
            )
        else:
            st.success("Évolution enregistrée.")
            st.rerun()

    _bouton_copier(
        evolution_service.texte_genere(contexte.base(), sejour["id"], date_jour_str)
    )
