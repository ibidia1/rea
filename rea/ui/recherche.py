"""Écran Recherche — cohortes, indicateurs, export (blocs 13 à 18).

Le service saisit déjà tout ce qu'il faut ; ce qui manquait, c'est de pouvoir
le relire en bloc. Cet écran ne calcule rien lui-même : il assemble une
cohorte, la donne aux services d'analyse, et affiche ce qu'ils rendent — y
compris quand ils rendent « incalculable ».
"""

from __future__ import annotations


import streamlit as st

from .. import listes
from ..db import Base
from ..services import export as export_service
from ..services import croisements as croisements_service
from ..services import statistiques as stats
from . import theme


def ecran(base: Base, utilisateur_id: str | None = None) -> None:
    st.title("Recherche et indicateurs")
    filtres = _filtres()
    selection = stats.cohorte(base, filtres)
    pluriel = "s" if len(selection) > 1 else ""
    st.caption(f"**{len(selection)} séjour{pluriel}** — {filtres.resume()}")
    if not selection:
        st.info("Aucun séjour ne correspond à ces filtres.")
        return

    # Un sélecteur, pas des onglets : chaque vue interroge la cohorte entière,
    # et `st.tabs` les calculerait toutes à chaque clic (voir `ui/fiche.py`).
    vues = {
        "Tableau descriptif": lambda: _table_1(base, selection),
        "Indicateurs de service": lambda: _indicateurs(base, selection),
        "Croisements": lambda: _croisements(base, selection),
        "Délai d'apyrexie": lambda: _apyrexie(base, selection),
        "Antibiotiques": lambda: _antibiotiques(base, selection),
        "Export": lambda: _export(base, selection, filtres, utilisateur_id),
    }
    noms = list(vues)
    choix = st.segmented_control(
        "Vue", noms, default=st.session_state.get("vue_recherche", noms[0]),
        key="segments_recherche", label_visibility="collapsed",
    ) or st.session_state.get("vue_recherche", noms[0])
    st.session_state["vue_recherche"] = choix
    vues[choix]()


def _filtres() -> stats.Filtres:
    with st.expander("Définir la cohorte", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        debut = c1.date_input("Admissions depuis", value=None, key="coh_debut")
        fin = c2.date_input("Jusqu'au", value=None, key="coh_fin")
        type_admission = c3.selectbox(
            "Type de motif", ["Tous", "Traumatique", "Non traumatique"]
        )
        statut = c4.selectbox("Séjours", ["Tous", "Clos seulement", "Décédés", "Survivants"])

        c5, c6, c7 = st.columns(3)
        age_min = c5.number_input("Âge minimum", 0, 120, 0)
        age_max = c6.number_input("Âge maximum", 0, 120, 120)
        provenances = c7.multiselect(
            "Provenance", listes.codes(listes.PROVENANCES),
            format_func=lambda c: listes.libelle(listes.PROVENANCES, c),
            placeholder="Toutes",
        )
        dispositifs = st.multiselect(
            "Ayant eu au moins un de ces dispositifs",
            listes.ORDRE_DISPOSITIFS, format_func=listes.libelle_dispositif,
            placeholder="Aucun filtre",
        )
    return stats.Filtres(
        date_debut=str(debut) if debut else None,
        date_fin=str(fin) if fin else None,
        traumatique={"Tous": None, "Traumatique": True, "Non traumatique": False}[type_admission],
        age_min=age_min or None,
        age_max=age_max if age_max < 120 else None,
        provenances=tuple(provenances),
        dispositifs=tuple(dispositifs),
        decedes={"Tous": None, "Clos seulement": None, "Décédés": True, "Survivants": False}[statut],
        sejours_clos_seulement=statut != "Tous",
    )


def _croisements(base: Base, selection: list[dict]) -> None:
    """Deux listes déroulantes, un tableau : « ce résultat, selon ce facteur ».

    C'est la forme des questions qu'on se pose en staff — la mortalité
    change-t-elle avec le PaO₂/FiO₂, avec le E/e', sous telle molécule — et
    elle se pose en deux choix parce qu'elle n'a pas besoin de plus. Le reste
    de l'écran sert à dire ce que le tableau ne prouve pas.
    """
    st.caption(
        "Choisir un **résultat** et un **facteur** : la cohorte est découpée "
        "en tranches selon le facteur, et le résultat est affiché tranche par "
        "tranche, avec son effectif. Les facteurs ne sont pas une liste écrite "
        "d'avance — ils sortent de vos données : les champs du dossier, tous "
        "les analytes (y compris ceux que vous avez ajoutés), les gaz du sang, "
        "les mesures des quatre plans, les produits prescrits, les dispositifs "
        "posés, les germes isolés, les antécédents saisis."
    )

    facteurs = croisements_service.facteurs_disponibles(base)
    resultats = list(croisements_service.RESULTATS)

    # Plusieurs centaines de facteurs : une liste à plat n'est plus une liste.
    # On choisit d'abord la famille — dossier, biologie, gaz du sang,
    # traitements, dispositifs, microbiologie, antécédents.
    familles: dict[str, list] = {}
    for v in facteurs:
        familles.setdefault(v.famille, []).append(v)

    c1, c2, c3 = st.columns([2, 1.4, 2])
    resultat = c1.selectbox(
        "Résultat à expliquer", resultats, format_func=lambda v: v.libelle,
    )
    famille = c2.selectbox(
        "Famille du facteur", sorted(familles), index=None,
        placeholder="Choisir",
    )
    facteur = c3.selectbox(
        "Croisé avec", familles.get(famille, []), format_func=lambda v: v.libelle,
        index=None, placeholder="Choisir un facteur",
        disabled=famille is None,
    )
    if facteur is None:
        st.info(
            f"**{len(facteurs)} facteurs** disponibles dans "
            f"{len(familles)} familles, tous issus de ce que contient la base. "
            "Quelques exemples de ce que ça permet de demander : mortalité "
            "selon le PaO₂/FiO₂ le plus bas · durée de ventilation selon le "
            "SOFA maximal · mortalité selon un antécédent · durée de séjour "
            "selon le germe isolé · jours sans ventilation selon la durée "
            "d'une molécule. Ce ne sont que des exemples : le choix est libre."
        )
        return

    seuils = None
    if facteur.genre == "continu":
        defaut = croisements_service.SEUILS_CLINIQUES.get(facteur.code)
        saisie = st.text_input(
            "Seuils des tranches (séparés par des virgules)",
            value=", ".join(str(s) for s in defaut) if defaut else "",
            placeholder="laisser vide pour découper en quartiles de la cohorte",
            help="Des seuils cliniques valent mieux que des quartiles quand ils "
                 "existent : 100, 200, 300 pour le PaO₂/FiO₂ sont ceux de "
                 "Berlin. Décimales avec un point (1.5), la virgule sépare "
                 "les seuils.",
        )
        seuils = _lire_seuils(saisie)
        if saisie.strip() and seuils is None:
            st.error("Seuils illisibles — des nombres séparés par des virgules.")
            return

    croisement = croisements_service.croiser(
        base, selection, code_facteur=facteur.code,
        code_resultat=resultat.code, seuils=seuils,
    )
    _afficher_croisement(croisement)


def _apyrexie(base: Base, selection: list[dict]) -> None:
    """« À partir de combien de jours un patient décroche sous telle
    molécule ? » — décrocher, c'est ne plus être fébrile.

    C'est un délai jusqu'à un événement, pas un croisement en tranches : il a
    son propre écran. Ce qu'il affiche à côté de la médiane est aussi
    important qu'elle — le nombre de patients qui n'ont **pas** décroché.
    """
    st.caption(
        "Pour chaque traitement commencé **chez un patient fébrile**, le "
        "nombre de jours jusqu'au premier jour apyrétique. Un patient "
        "subfébrile n'a pas décroché ; une température non mesurée n'est "
        "jamais lue comme une apyrexie."
    )
    produits = [
        v.code.split(":", 1)[1]
        for v in croisements_service.facteurs_disponibles(base)
        if v.code.startswith("produit:")
    ]
    if not produits:
        st.info("Aucune molécule prescrite à au moins deux patients.")
        return
    produit = st.selectbox("Molécule", produits, index=None,
                           placeholder="Choisir une molécule")
    if not produit:
        return

    r = croisements_service.delai_apyrexie(base, selection, produit)
    if not r.episodes:
        st.info(
            f"Aucun traitement par {produit} n'a commencé chez un patient "
            "fébrile dans cette cohorte — il n'y a rien à mesurer."
        )
        for note in r.avertissements:
            st.caption(note)
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Traitements commencés chez un fébrile", r.episodes)
    c2.metric(
        "Devenus apyrétiques",
        f"{r.decroches}/{r.episodes}"
        + (f" ({r.part_decroches * 100:.0f} %)" if r.part_decroches is not None else ""),
    )
    c3.metric(
        "Délai médian",
        f"{r.delai_median:.0f} j" if r.delai_median is not None else "—",
        help="parmi ceux qui ont décroché uniquement",
    )
    if r.delais:
        st.caption("Délais observés (jours) : " + ", ".join(
            str(d) for d in sorted(r.delais)
        ))
    for note in r.avertissements:
        st.caption(note)


def _lire_seuils(saisie: str) -> tuple[float, ...] | None:
    """« 100, 200, 300 » → (100.0, 200.0, 300.0). None si c'est illisible.

    Séparateurs : virgule, point-virgule ou espace. Le séparateur décimal est
    le **point** — la virgule sert déjà à séparer les seuils, et accepter les
    deux rendrait « 1,5 » indécidable entre un seuil et deux.
    """
    if not saisie.strip():
        return None
    morceaux = saisie.replace(";", " ").replace(",", " ").split()
    try:
        valeurs = tuple(float(m) for m in morceaux)
    except ValueError:
        return None
    return tuple(sorted(valeurs)) or None


def _afficher_croisement(croisement) -> None:
    # Pas de `.lower()` sur le libellé du facteur : il mangeait les
    # abréviations — « selon pao₂/fio₂ le plus bas ».
    st.markdown(
        f"#### {croisement.resultat.libelle} selon {croisement.facteur.libelle}"
    )
    lignes = "".join(
        f"<tr>"
        f"<td style='padding:.35rem .6rem'>{s.libelle}</td>"
        f"<td style='padding:.35rem .6rem;text-align:right'>{s.effectif}</td>"
        f"<td style='padding:.35rem .6rem;"
        f"color:{'#94a3b8' if not s.interpretable else 'inherit'}'>{s.texte}</td>"
        f"</tr>"
        for s in croisement.strates
    )
    retenus = croisement.total - croisement.non_renseignes
    theme.bloc_html(
        f"{retenus} séjour{'s' if retenus > 1 else ''} dans le tableau",
        "<table style='width:100%;font-size:.9rem'>"
        "<tr style='color:#64748b;font-size:.78rem'>"
        "<th style='text-align:left'>Tranche</th><th>n</th>"
        "<th style='text-align:left'>&nbsp;Résultat</th></tr>"
        + lignes + "</table>",
        theme.BLEU,
    )
    for note in croisement.avertissements:
        st.caption(note)


def _table_1(base: Base, selection: list[dict]) -> None:
    st.caption(
        "Tableau descriptif au format attendu par STROBE. Chaque ligne indique "
        "sur combien de dossiers elle est calculée : une donnée manquante est "
        "déclarée, jamais diluée dans un pourcentage."
    )
    lignes = stats.table_1(base, selection)
    corps = "".join(
        f"<tr><td>{l.libelle}</td>"
        f"<td style='text-align:right;font-weight:600'>{l.valeur}</td>"
        f"<td style='text-align:right;color:{'#94a3b8' if not l.manquants else theme.ORANGE}'>"
        f"{l.renseignes}/{l.total}</td>"
        f"<td style='color:#94a3b8;font-size:0.8rem'>{l.note}</td></tr>"
        for l in lignes
    )
    st.markdown(
        "<table style='width:100%;border-collapse:collapse;font-size:0.9rem'>"
        "<thead><tr style='text-align:left;color:#64748b'><th>Caractéristique</th>"
        "<th style='text-align:right'>Valeur</th><th style='text-align:right'>Renseignés</th>"
        "<th>Note</th></tr></thead><tbody>" + corps + "</tbody></table>",
        unsafe_allow_html=True,
    )


def _indicateurs(base: Base, selection: list[dict]) -> None:
    journees = stats.journees_hospitalisation(base, selection)
    c1, c2, c3 = st.columns(3)
    c1.metric("Séjours", len(selection))
    c2.metric("Journées d'hospitalisation", journees)
    morts = stats.mortalite(base, selection)
    c3.metric(
        "Mortalité observée",
        f"{morts['mortalite_observee'] * 100:.0f} %" if morts["mortalite_observee"] is not None else "—",
        help=f"sur {morts['sejours_clos']} séjours clos",
    )

    st.subheader("Infections liées aux dispositifs")
    st.caption(
        "Dénominateur en jours-dispositif (protocole ECDC) : rapporter les "
        "infections au nombre de patients ferait paraître bon un service qui "
        "ventile peu, et mauvais un service qui ventile longtemps."
    )
    for taux in stats.taux_infections_dispositifs(base, selection):
        couleur = theme.GRIS if taux.valeur is None else theme.BLEU
        valeur = "—" if taux.valeur is None else f"{taux.valeur}"
        detail = (
            "Incalculable : aucun jour-dispositif enregistré."
            if taux.valeur is None
            else f"{taux.numerateur} infections / {taux.denominateur} jours-dispositif"
        )
        theme.bloc_html(
            taux.libelle,
            f"<span style='font-size:1.5rem;font-weight:600'>{valeur}</span> "
            f"<span style='color:#94a3b8'>{taux.unite}</span><br>"
            f"<span style='color:#94a3b8;font-size:0.82rem'>{detail} · {taux.note}</span>",
            couleur,
        )

    st.subheader("Mortalité")
    if morts["rapport_observe_attendu"] is not None:
        theme.bloc(
            "Rapport observé / attendu (IGS II)",
            [
                f"{morts['rapport_observe_attendu']}",
                f"{morts['deces']} décès observés pour {morts['deces_attendus']} attendus",
                "Un rapport < 1 ne prouve pas une meilleure prise en charge : "
                "l'étalonnage de l'IGS II vieillit et dépend du recrutement.",
            ],
            theme.BLEU,
        )
    else:
        st.info(morts["note"] or "Rapport observé/attendu non calculable.")


def _antibiotiques(base: Base, selection: list[dict]) -> None:
    resultat = stats.consommation_antibiotiques(base, selection)
    c1, c2 = st.columns(2)
    c1.metric("Jours de traitement antibiotique", resultat["jours_de_traitement"])
    c2.metric(
        "Pour 1000 journées d'hospitalisation",
        resultat["dot_pour_1000_journees"] if resultat["dot_pour_1000_journees"] is not None else "—",
    )
    if resultat["note"]:
        st.caption(resultat["note"])
    if resultat["par_molecule"]:
        st.caption("Jours de traitement par molécule reconnue dans le prescrit :")
        st.dataframe(
            {"molécule": list(resultat["par_molecule"].keys()),
             "jours": list(resultat["par_molecule"].values())},
            use_container_width=True, hide_index=True,
        )
    else:
        st.info(
            "Aucun antibiotique reconnu dans le prescrit de cette cohorte. La "
            "reconnaissance se fait par nom : compléter la liste dans "
            "`referentiels/antibiotiques_ddd.json` si une molécule manque."
        )


def _export(base: Base, selection: list[dict], filtres: stats.Filtres,
            utilisateur_id: str | None) -> None:
    st.caption(
        "L'export ne contient ni matricule, ni nom, ni date de naissance : le "
        "patient y est désigné par son identifiant d'étude, et l'âge remplace "
        "la date de naissance. Il emporte son dictionnaire des données et la "
        "version de chaque référentiel."
    )
    motif = st.text_input("Motif de l'export (noté dans le journal)", value="")
    texte_libre = st.checkbox(
        "Inclure les zones de texte libre (déconseillé)",
        help="Un commentaire d'évolution peut contenir un nom, un lieu, un "
             "numéro de chambre. Cochée, cette case rend l'export non "
             "pseudonymisé de façon fiable.",
    )
    if texte_libre:
        st.warning(
            "L'export contiendra du texte libre : il n'est alors plus "
            "pseudonymisé de façon fiable et se traite comme un dossier "
            "nominatif.", icon="⚠️",
        )
    c1, c2 = st.columns(2)
    if c1.button("Exporter la cohorte", type="primary", use_container_width=True):
        dossier = export_service.exporter(
            base, sejour_ids=[s["id"] for s in selection],
            avec_texte_libre=texte_libre, motif=motif or filtres.resume(),
            utilisateur_id=utilisateur_id,
        )
        st.success(f"Export écrit dans `{dossier}`")
        st.caption(
            "Un export reste une donnée de santé : il se conserve et se "
            "transmet comme telle."
        )
    if c2.button("Geler la base pour analyse", use_container_width=True):
        gel = export_service.geler(
            base, motif=motif or "analyse", utilisateur_id=utilisateur_id
        )
        st.success(f"Base gelée : `{gel['fichier']}` ({gel['nb_sejours']} séjours)")
        st.caption(
            "Une étude qui tourne pendant que les données bougent n'est pas "
            "reproductible : ce gel garde l'état exact ayant servi à l'analyse."
        )
