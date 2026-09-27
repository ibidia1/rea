"""Écran Recherche — cohortes, indicateurs, export (blocs 13 à 18).

Le service saisit déjà tout ce qu'il faut ; ce qui manquait, c'est de pouvoir
le relire en bloc. Cet écran ne calcule rien lui-même : il assemble une
cohorte, la donne aux services d'analyse, et affiche ce qu'ils rendent — y
compris quand ils rendent « incalculable ».
"""

from __future__ import annotations


import streamlit as st

from .. import listes
from ..database import Base
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
        "Mois par mois": lambda: _mois_par_mois(base, selection),
        "Gravité et mortalité": lambda: _gravite(base, selection),
        "Croisements": lambda: _croisements(base, selection),
        "Délai d'apyrexie": lambda: _apyrexie(base, selection),
        "Antibiotiques": lambda: _antibiotiques(base, selection),
        "Qualité des données": lambda: _qualite(base, selection),
        "Méthode": _methode,
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
    km = r.kaplan_meier
    c3.metric(
        "Délai médian (Kaplan-Meier)",
        f"{km.mediane:.0f} j" if km.mediane is not None else "non atteint",
        help="Tient compte des patients qui n'ont pas décroché (censurés à la "
             "fin du traitement). « Non atteint » : moins de la moitié a "
             "décroché — c'est en soi le résultat.",
    )
    if km.temps:
        st.caption("Part des patients apyrétiques selon le jour de traitement :")
        st.line_chart(
            {"jour": [0, *km.temps], "apyrétiques (%)": [0, *[round((1 - s) * 100) for s in km.survie]]},
            x="jour", y="apyrétiques (%)", height=220,
        )
    if r.delais:
        st.caption(
            "Délais observés chez ceux qui ont décroché (jours) : "
            + ", ".join(str(d) for d in sorted(r.delais))
            + (f" · médiane de ces seuls patients : {r.delai_median:.0f} j — "
               "optimiste, elle ignore ceux qui n'ont pas décroché."
               if r.delai_median is not None else "")
        )
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
    if morts["ic_mortalite"]:
        ic = morts["ic_mortalite"]
        st.caption(
            f"Mortalité : {morts['deces']}/{morts['sejours_clos']} — intervalle de "
            f"confiance à 95 % : **{ic.bas * 100:.0f} à {ic.haut * 100:.0f} %**. "
            "C'est la fourchette compatible avec ces données : plus la cohorte "
            "est petite, plus elle est large."
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
        ic = taux.intervalle
        detail = (
            "Incalculable : aucun jour-dispositif enregistré."
            if taux.valeur is None
            else f"{taux.numerateur} infections / {taux.denominateur} jours-dispositif"
                 f" · IC95 {ic.bas:.1f}–{ic.haut:.1f}".replace(".", ",")
        )
        theme.bloc_html(
            taux.libelle,
            f"<span style='font-size:1.5rem;font-weight:600'>{valeur}</span> "
            f"<span style='color:#94a3b8'>{taux.unite}</span><br>"
            f"<span style='color:#94a3b8;font-size:0.82rem'>{detail} · {taux.note}</span>",
            couleur,
        )

    _ventilation(base, selection)

    st.subheader("Mortalité")
    if morts["rapport_observe_attendu"] is not None:
        ic = morts["ic_rapport"]
        theme.bloc(
            "Rapport observé / attendu (IGS II)",
            [
                f"{morts['rapport_observe_attendu']}"
                + (f" — IC95 {ic.bas:.2f} à {ic.haut:.2f}".replace(".", ",") if ic else ""),
                f"{morts['deces']} décès observés pour {morts['deces_attendus']} attendus",
                "Un intervalle qui contient 1 ne permet de dire ni mieux ni "
                "moins bien que prévu.",
                "Un rapport < 1 ne prouve pas une meilleure prise en charge : "
                "l'étalonnage de l'IGS II vieillit et dépend du recrutement.",
            ],
            theme.BLEU,
        )
    else:
        st.info(morts["note"] or "Rapport observé/attendu non calculable.")


def _ventilation(base: Base, selection: list[dict]) -> None:
    st.subheader("Ventilation mécanique")
    v = stats.indicateurs_ventilation(base, selection)
    c1, c2, c3 = st.columns(3)
    c1.metric(
        "Ratio d'utilisation", f"{v['ratio_utilisation']:.2f}".replace(".", ",")
        if v["ratio_utilisation"] is not None else "—",
        help="Jours de ventilation / journées d'hospitalisation (ECDC). C'est "
             "le contexte de tout taux de PAVM : un service qui ventile peu "
             "et un service qui ventile beaucoup ne se comparent pas.",
    )
    tnp = v["taux_non_programmees"]
    c2.metric(
        "Extubations non programmées",
        f"{tnp.valeur:.1f} / 100 j VM".replace(".", ",") if tnp else "—",
        help=(f"{v['extubations_non_programmees']} sur {v['jours_vm']} jours de "
              f"ventilation · IC95 {tnp.bas:.1f}–{tnp.haut:.1f}".replace(".", ",")
              if tnp else "aucun jour de ventilation"),
    )
    echec = v["taux_echec"]
    c3.metric(
        "Échec d'extubation (réintubation ≤ 48 h)",
        f"{v['echecs_extubation']}/{v['extubations_programmees']}"
        + (f" ({echec.valeur * 100:.0f} %)" if echec else ""),
        help=(f"IC95 {echec.bas * 100:.0f}–{echec.haut * 100:.0f} %. Repère "
              "habituel : 10 à 20 %. Trop bas peut signifier qu'on extube "
              "trop tard, trop haut trop tôt." if echec else None),
    )


def _mois_par_mois(base: Base, selection: list[dict]) -> None:
    """Carte de contrôle : distinguer un vrai changement du bruit.

    Un mois à 40 % de mortalité après un mois à 15 % n'est pas forcément un
    signal — avec huit sorties, c'est souvent le hasard. La carte trace la
    moyenne et des limites qui dépendent de l'effectif du mois ; seuls les
    points hors limites, ou une série de huit du même côté, méritent qu'on
    cherche une cause.
    """
    import altair as alt
    import pandas as pd

    tendances = stats.tendances_mensuelles(base, selection)
    if len(tendances) < 3:
        st.info("Il faut au moins trois mois de données pour lire une tendance.")
        return
    centre, points = stats.carte_mortalite(tendances)
    st.caption(
        "**Carte de contrôle de la mortalité** (mois de sortie). La ligne est "
        "la moyenne de la période, la bande grise la variation attendue du "
        "seul fait du hasard (± 3 écarts-types, plus large les mois à petit "
        "effectif). Un point rouge est un **signal** : hors de la bande, ou "
        "dans une série d'au moins huit mois du même côté de la moyenne. Le "
        "reste est du bruit — ne pas chercher d'explication mois par mois."
    )
    lignes = [
        {"mois": p.periode, "mortalité": p.proportion * 100 if p.proportion is not None else None,
         "bas": (p.limite_basse or 0) * 100, "haut": (p.limite_haute or 0) * 100,
         "sorties": p.n, "décès": p.evenements, "signal": p.signal or "—"}
        for p in points if p.n
    ]
    if centre is not None and lignes:
        df = pd.DataFrame(lignes)
        base_chart = alt.Chart(df).encode(x=alt.X("mois:O", title=None))
        bande = base_chart.mark_area(opacity=0.18, color="#64748b").encode(
            y=alt.Y("bas:Q", title="Mortalité (%)"), y2="haut:Q")
        moyenne = alt.Chart(pd.DataFrame({"m": [centre * 100]})).mark_rule(
            color="#475569", strokeDash=[4, 3]).encode(y="m:Q")
        ligne = base_chart.mark_line(color="#1d4ed8").encode(y="mortalité:Q")
        pts = base_chart.mark_circle(size=70).encode(
            y="mortalité:Q",
            color=alt.condition(alt.datum.signal != "—", alt.value("#dc2626"),
                                alt.value("#1d4ed8")),
            tooltip=["mois", "sorties", "décès", alt.Tooltip("mortalité:Q", format=".0f"),
                     "signal"],
        )
        st.altair_chart(bande + moyenne + ligne + pts, use_container_width=True)
        signaux = [p for p in points if p.signal]
        if signaux:
            st.warning("Signaux : " + " · ".join(f"{p.periode} ({p.signal})" for p in signaux))
        else:
            st.success(
                f"Aucun signal : la mortalité varie autour de {centre * 100:.0f} % "
                "dans les limites du hasard."
            )
    st.caption("Activité mois par mois :")
    st.dataframe(
        {
            "mois": [m["mois"] for m in tendances],
            "admissions": [m["admissions"] for m in tendances],
            "ventilés": [m["ventiles"] for m in tendances],
            "sorties": [m["sorties"] for m in tendances],
            "décès": [m["deces"] for m in tendances],
            "durée médiane (j)": [m["duree_mediane"] for m in tendances],
        },
        use_container_width=True, hide_index=True,
    )


def _gravite(base: Base, selection: list[dict]) -> None:
    """L'IGS II sur nos patients : prédit-il bien, et pour qui ?"""
    cal = stats.calibration_igs2(base, selection)
    if cal["n"] < 10:
        st.info(
            f"{cal['n']} séjour(s) clos avec un IGS II complet : il en faut "
            "au moins une dizaine pour lire une calibration. Compléter l'IGS II "
            "(voir « Qualité des données »)."
        )
        if not cal["n"]:
            return
    st.caption(
        "**Calibration** : dans chaque classe de risque prédit, les décès "
        "observés face aux décès attendus. Un rapport O/A global proche de 1 "
        "peut cacher une surmortalité chez les patients peu graves compensée "
        "chez les plus graves — c'est ce tableau qui le montre."
    )
    corps = "".join(
        f"<tr><td>{c['classe']}</td><td style='text-align:right'>{c['n']}</td>"
        f"<td style='text-align:right'>{c['predite'] * 100:.0f} %</td>"
        f"<td style='text-align:right'>{c['observes']}/{c['n']} ({c['mortalite'].valeur * 100:.0f} %)</td>"
        f"<td style='text-align:right;color:#64748b'>{c['mortalite'].bas * 100:.0f}–"
        f"{c['mortalite'].haut * 100:.0f} %</td>"
        f"<td style='text-align:right'>{c['attendus']}</td></tr>"
        for c in cal["classes"]
    )
    st.markdown(
        "<table style='width:100%;font-size:.9rem'><tr style='color:#64748b'>"
        "<th style='text-align:left'>Risque prédit</th><th>n</th>"
        "<th>Mortalité prédite</th><th>Observée</th><th>IC95</th>"
        "<th>Décès attendus</th></tr>" + corps + "</table>",
        unsafe_allow_html=True,
    )
    auc = cal["auroc"]
    if auc:
        st.metric(
            "Discrimination (aire sous la courbe ROC)",
            f"{auc.valeur:.2f}".replace(".", ","),
            help=f"IC95 {auc.bas:.2f}–{auc.haut:.2f}. 0,5 = pas mieux que le "
                 "hasard ; ≥ 0,8 = bonne discrimination. Le score classe-t-il "
                 "plus haut ceux qui meurent ?".replace(".", ","),
        )
    st.caption(
        "L'IGS II date de 1993 : il surestime souvent la mortalité actuelle. "
        "Un écart ici décrit l'outil autant que le service."
    )


def _qualite(base: Base, selection: list[dict]) -> None:
    """Ce qui manque, et chez qui : compléter avant d'analyser."""
    st.caption(
        "Une analyse ne vaut que ce que valent ses données manquantes. Un "
        "IGS II incomplet rend le rapport observé/attendu incalculable ; un "
        "statut J28 manquant biaise la mortalité à J28 vers les survivants. "
        "Cette liste dit **quels dossiers compléter** — idéalement chaque "
        "semaine, pendant que le dossier est encore frais."
    )
    for ligne in stats.qualite_des_donnees(base, selection):
        concernes, renseignes = ligne["concernes"], ligne["renseignes"]
        if not concernes:
            continue
        part = renseignes / concernes
        couleur = theme.VERT if part >= 0.95 else theme.ORANGE if part >= 0.8 else theme.ROUGE
        manquants = ligne["manquants"]
        titre = (f"{ligne['donnee']} — {renseignes}/{concernes} "
                 f"({part * 100:.0f} %)")
        if not manquants:
            theme.bloc_html(titre, "Complet.", couleur)
            continue
        with st.expander(f"{'🟢' if part >= 0.95 else '🟠' if part >= 0.8 else '🔴'} {titre}"):
            st.dataframe(
                {
                    "lit": [s.get("lit_admission") for s in manquants],
                    "matricule": [s.get("matricule") or "" for s in manquants],
                    "admission": [(s.get("date_admission") or "")[:10] for s in manquants],
                    "sortie": [(s.get("date_sortie") or "")[:10] for s in manquants],
                },
                use_container_width=True, hide_index=True,
            )


def _methode() -> None:
    """Comment tirer de ces données ce qu'elles peuvent vraiment dire."""
    st.markdown(METHODE)


#: Le guide de lecture, affiché tel quel.
METHODE = """
#### Bien utiliser les chiffres du service

**1. Poser la question avant de regarder les données.** Écrire en une phrase
la question, le critère de jugement (ex. mortalité à J28) et la population
*avant* de filtrer. Tester vingt croisements jusqu'à en trouver un « qui
marche », c'est fabriquer un faux positif : sur vingt essais, un sort au hasard.

**2. Lire l'intervalle de confiance, pas seulement le pourcentage.** Dans un
service de 12 lits, « 30 % de mortalité » sur 10 patients veut dire « entre 11
et 60 % ». Deux groupes dont les intervalles se recouvrent largement ne sont
pas différents au vu de ces données.

**3. Distinguer un signal du bruit dans le temps.** Un mauvais mois n'est pas
une dégradation : la carte de contrôle (*Mois par mois*) dit si l'écart dépasse
ce que le hasard produit. Ne réagir qu'aux signaux.

**4. Ajuster sur la gravité avant de comparer.** Une mortalité brute plus haute
cette année peut simplement refléter des patients plus graves. Le rapport
observé/attendu (IGS II) et le tableau de calibration (*Gravité et mortalité*)
en tiennent compte ; un croisement univarié, non.

**5. Rapporter aux bons dénominateurs.** Infections pour 1000 jours-dispositif
(ECDC), antibiotiques pour 1000 journées, extubations non programmées pour 100
jours de ventilation — jamais « pour 100 patients ».

**6. Tenir compte des délais incomplets.** Pour un délai (apyrexie, sevrage),
les patients chez qui l'événement n'est pas survenu comptent : c'est ce que fait
Kaplan-Meier. La médiane des seuls « répondeurs » est toujours trop optimiste.

**7. Association n'est pas causalité.** Les patients qui reçoivent tel
antibiotique sont souvent les plus graves : leur mortalité plus haute ne dit
rien du médicament (biais d'indication). Les croisements fabriquent des
**hypothèses** ; les confirmer demande un ajustement multivarié (régression
logistique, sur l'export) ou un essai.

**8. Des données complètes d'abord.** Compléter chaque semaine ce que liste
*Qualité des données* — surtout l'IGS II, le mode de sortie et le **statut à
J28** (appeler les patients sortis). Au-delà de 10–20 % de manquants sur une
variable, un résultat qui en dépend est fragile.

**9. Pour un mémoire, une thèse ou un article.**
- geler la base (*Export → Geler la base*) le jour de l'analyse : le chiffre
  publié doit pouvoir être retrouvé ;
- exporter la cohorte pseudonymisée et analyser sous R, SPSS ou Stata ;
- suivre la check-list **STROBE** (études observationnelles) et décrire les
  données manquantes ;
- règle pratique pour une régression logistique : environ **10 événements par
  variable** (30 décès → 3 variables d'ajustement au plus) ;
- une étude sur les données du service relève d'un avis du comité d'éthique
  de l'hôpital, même rétrospective.

**10. Ce que ces données permettent bien.** Audit de pratiques et
indicateurs qualité (infections, extubations, antibiotiques), description
d'une population (Tableau descriptif), comparaison avant/après un changement
de protocole (carte de contrôle), et génération d'hypothèses pour une étude
prospective.
"""


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
