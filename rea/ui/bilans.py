"""Onglet Bilans — saisie des résultats, cinétique, microbiologie.
"""

from __future__ import annotations

from datetime import date, datetime

import streamlit as st

from .. import analytes as cat, listes
from ..domaine import calculs, coherence
from ..domaine.dates import age_ans, format_date_fr
from ..services import bilans as bilans_service, microbiologie as micro_service
from . import contexte, theme

from . import champs


def _plage_normale(a) -> str:
    """Texte gris affiché dans le champ vide : la plage attendue."""
    if a.borne_basse is not None and a.borne_haute is not None:
        return f"{champs.format_valeur(a.borne_basse)} – {champs.format_valeur(a.borne_haute)}"
    if a.borne_haute is not None:
        return f"< {champs.format_valeur(a.borne_haute)}"
    if a.borne_basse is not None:
        return f"> {champs.format_valeur(a.borne_basse)}"
    return ""


def _champ_analyte(a, cle_widget: str) -> float | None:
    """Un champ de saisie : vide au départ, la plage normale en gris dedans,
    un signalement rouge sous le champ si la valeur en sort."""
    texte = st.text_input(
        f"{a.libelle} ({a.unite})" if a.unite else a.libelle,
        value="",
        placeholder=_plage_normale(a),
        key=cle_widget,
    )
    if not texte.strip():
        return None
    valeur = champs.nombre_saisi(texte)
    if valeur is None:
        st.markdown(
            f"<span style='color:{theme.ROUGE};font-size:.74rem'>valeur non numérique</span>",
            unsafe_allow_html=True,
        )
        return None

    # Deux niveaux, comme le veut le bloc 4 : « anormal » n'est pas
    # « impossible ». Le premier informe, le second alerte.
    impossible = coherence.verifier_bilan({a.id: valeur})
    if impossible:
        st.markdown(
            f"<span style='color:{theme.ROUGE};font-size:.74rem;font-weight:700'>"
            f"⚠ hors bornes physiologiques</span>",
            unsafe_allow_html=True,
        )
    else:
        alerte = a.hors_bornes(valeur)
        if alerte:
            fleche = "↑" if alerte == "haut" else "↓"
            st.markdown(
                f"<span style='color:{theme.ROUGE};font-size:.74rem;font-weight:600'>"
                f"{fleche} hors plage usuelle</span>",
                unsafe_allow_html=True,
            )
    return valeur


def onglet_bilans(sejour: dict) -> None:
    """Deux usages, deux ordres de lecture. Par défaut on vient saisir un
    bilan, souvent avec le DMI ouvert à côté et la fenêtre en demi-écran :
    la saisie est donc en premier, sur deux colonnes qui tiennent dans cette
    largeur. La cinétique suit."""
    saisie_bilan(sejour)

    st.divider()
    panneau_microbiologie(sejour)

    st.divider()
    vue_cinetique(sejour)

    st.subheader("Texte généré")
    date_affichee = st.date_input("Jour", value=date.today(), key="date_bilan_texte")
    texte = bilans_service.texte_genere(contexte.base(), sejour["id"], str(date_affichee))
    st.text_area(
        "Prêt à coller dans l'évolution",
        value=texte or "(aucun bilan ce jour-là)",
        height=200,
    )


def panneau_microbiologie(sejour: dict) -> None:
    """Prélèvements et infections acquises (bloc 14).

    Un prélèvement dont le résultat n'est jamais revenu est ce qu'on oublie le
    plus sûrement : les prélèvements en attente sont donc affichés en premier
    et en orange, tant qu'ils ne sont pas complétés.
    """
    st.markdown("##### 🦠 Microbiologie")
    lignes = micro_service.du_sejour(contexte.base(), sejour["id"])
    attente = [l for l in lignes if l["resultat"] == "en_cours"]

    gauche, droite = st.columns([1, 1.2], gap="large")
    with gauche:
        with st.form(f"micro_{sejour['id']}"):
            c1, c2 = st.columns(2)
            date_prelevement = c1.date_input("Date", value=date.today(),
                                             key="micro_date")
            type_prelevement = c2.selectbox(
                "Prélèvement", listes.codes(listes.PRELEVEMENTS),
                format_func=lambda c: listes.libelle(listes.PRELEVEMENTS, c),
            )
            if st.form_submit_button("Enregistrer le prélèvement"):
                micro_service.enregistrer(
                    contexte.base(), sejour_id=sejour["id"], date_prelevement=str(date_prelevement),
                    type_prelevement=type_prelevement, utilisateur_id=contexte.utilisateur_id(),
                )
                st.rerun()

        with st.expander("Déclarer une infection acquise"):
            with st.form(f"nosoco_{sejour['id']}"):
                type_infection = st.selectbox(
                    "Type", listes.codes(listes.INFECTIONS_NOSOCOMIALES),
                    format_func=lambda c: listes.libelle(listes.INFECTIONS_NOSOCOMIALES, c),
                )
                date_diagnostic = st.date_input("Date du diagnostic", value=date.today())
                germe_nosoco = st.text_input("Germe (si connu)")
                if st.form_submit_button("Déclarer"):
                    micro_service.declarer_infection_nosocomiale(
                        contexte.base(), sejour_id=sejour["id"], type_=type_infection,
                        date_diagnostic=str(date_diagnostic),
                        germe=germe_nosoco or None, utilisateur_id=contexte.utilisateur_id(),
                    )
                    st.rerun()
            st.caption(
                "Seules les infections diagnostiquées au moins 48 h après "
                "l'admission comptent dans les taux du service : avant, "
                "l'infection est réputée importée."
            )

    with droite:
        if attente:
            for ligne in attente:
                with st.form(f"resultat_{ligne['id']}"):
                    st.markdown(
                        f"**{listes.libelle(listes.PRELEVEMENTS, ligne['type_prelevement'])}** "
                        f"du {format_date_fr(ligne['date_prelevement'])} — en attente"
                    )
                    c1, c2 = st.columns([1, 1.4])
                    resultat = c1.selectbox(
                        "Résultat", listes.codes(listes.RESULTATS_MICROBIO),
                        format_func=lambda c: listes.libelle(listes.RESULTATS_MICROBIO, c),
                        key=f"res_{ligne['id']}",
                    )
                    germe = c2.text_input("Germe", key=f"germe_{ligne['id']}")
                    antibiogramme = st.text_area(
                        "Antibiogramme", key=f"atb_{ligne['id']}", height=70
                    )
                    if st.form_submit_button("Enregistrer le résultat"):
                        micro_service.completer(
                            contexte.base(), ligne["id"],
                            {"resultat": resultat, "germe": germe or None,
                             "antibiogramme": antibiogramme or None},
                            utilisateur_id=contexte.utilisateur_id(),
                        )
                        st.rerun()
        rendus = [l for l in lignes if l["resultat"] != "en_cours"]
        if rendus:
            theme.bloc(
                "Résultats rendus",
                [
                    f"{format_date_fr(l['date_prelevement'])} · "
                    f"{listes.libelle(listes.PRELEVEMENTS, l['type_prelevement'])} — "
                    f"{listes.libelle(listes.RESULTATS_MICROBIO, l['resultat'])}"
                    + (f" : {l['germe']}" if l["germe"] else "")
                    for l in rendus
                ],
                theme.VIOLET,
            )
        infections = micro_service.infections_du_sejour(contexte.base(), sejour["id"])
        if infections:
            theme.bloc(
                "Infections déclarées",
                [
                    f"{format_date_fr(i['date_diagnostic'])} · "
                    f"{listes.libelle(listes.INFECTIONS_NOSOCOMIALES, i['type'])}"
                    + (f" ({i['germe']})" if i["germe"] else "")
                    + ("" if micro_service.acquise_en_reanimation(sejour, i)
                       else " — présente à l'admission, non comptée comme acquise")
                    for i in infections
                ],
                theme.ROUGE,
            )
        if not lignes and not micro_service.infections_du_sejour(contexte.base(), sejour["id"]):
            st.caption("Aucun prélèvement enregistré pour ce séjour.")


def saisie_bilan(sejour: dict) -> None:
    st.markdown("##### Saisir un bilan")
    haut1, haut2 = st.columns(2)
    date_heure = haut1.text_input(
        "Date / heure du prélèvement",
        value=datetime.now().isoformat(timespec="minutes"),
        key="bilan_date_heure",
    )
    unite_lipides = haut2.radio(
        "Lipides en", ["mmol/L", "g/L"], horizontal=True, key="unite_lipides"
    )

    valeurs: dict[str, float | None] = {}

    # Deux colonnes : c'est ce qui tient dans une fenêtre en demi-écran, à
    # côté du DMI.
    for groupe in cat.GROUPES:
        st.markdown(f"**{groupe.titre}**")
        colonnes = st.columns(2)
        saisissables = [a for a in groupe.analytes if not a.calcule]
        for i, a in enumerate(saisissables):
            with colonnes[i % 2]:
                valeur = _champ_analyte(a, f"bilan_{a.id}")
                if groupe.code == "lipidique" and valeur is not None and unite_lipides == "g/L":
                    valeur = bilans_service.gl_vers_mmol(a.id, valeur)
                valeurs[a.id] = valeur

    st.markdown("**Gaz du sang & ventilation**")
    g1, g2 = st.columns(2)
    mode_vent = g1.selectbox("Mode ventilatoire", ["—", *cat.MODES_VENTILATOIRES], key="gds_mode")
    debit_o2 = champs.nombre_saisi(
        g2.text_input("Débit O₂ (L/min)", value="", placeholder="si masque ou lunette",
                      key="gds_debit")
    )
    gaz: dict[str, float | None] = {}
    champs_gaz = [
        ("fio2", "FiO₂ (%)", "21 – 100"), ("pep", "PEP (cmH₂O)", "0 – 20"),
        ("fr", "FR (/min)", "12 – 25"), ("spo2", "SpO₂ (%)", "≥ 94"),
        ("ph", "pH", "7,35 – 7,45"), ("pao2", "PaO₂ (mmHg)", "80 – 100"),
        ("paco2", "PaCO₂ (mmHg)", "35 – 45"), ("hco3", "HCO₃⁻ (mmol/L)", "22 – 26"),
        ("lactate", "Lactates (mmol/L)", "< 2"),
    ]
    colonnes_gaz = st.columns(2)
    for i, (cle, libelle, plage) in enumerate(champs_gaz):
        with colonnes_gaz[i % 2]:
            texte = st.text_input(libelle, value="", placeholder=plage, key=f"gds_{cle}")
            valeur = champs.nombre_saisi(texte)
            if texte.strip() and valeur is None:
                st.markdown(
                    f"<span style='color:{theme.ROUGE};font-size:.74rem'>valeur non numérique</span>",
                    unsafe_allow_html=True,
                )
            elif valeur is not None and coherence.verifier_gaz_du_sang({cle: valeur}):
                st.markdown(
                    f"<span style='color:{theme.ROUGE};font-size:.74rem;font-weight:700'>"
                    f"⚠ hors bornes physiologiques</span>",
                    unsafe_allow_html=True,
                )
            gaz[cle] = valeur

    # Valeurs dérivées, affichées dès que leurs ingrédients sont là.
    age = age_ans(sejour.get("date_naissance"))
    derivees = [
        v for v in calculs.toutes_les_valeurs(
            resultats=valeurs, gaz=gaz, poids_kg=sejour.get("poids_kg"),
            taille_cm=sejour.get("taille_cm"), age_ans=age, sexe=sejour.get("sexe"),
        )
        if v.disponible
    ]
    if derivees:
        theme.bloc(
            "Calculé automatiquement",
            [
                f"<b>{v.libelle}</b> : {champs.format_valeur(v.valeur)} {v.unite}"
                f" <span style='color:{theme.GRIS};font-size:.78rem'>— {v.formule}</span>"
                for v in derivees
            ],
            theme.BLEU,
        )
    if not sejour.get("poids_kg"):
        st.caption(
            "Poids non renseigné à l'admission : la clairance de la créatinine "
            "ne peut pas être calculée."
        )

    avertissements = (
        coherence.verifier_bilan(valeurs) + coherence.verifier_gaz_du_sang(gaz)
    )
    forcer = False
    if avertissements:
        for a in avertissements:
            st.warning(a.message)
        forcer = st.checkbox(
            "Forcer l'enregistrement malgré les avertissements",
            key="bilan_forcer",
            help="La valeur est enregistrée et marquée comme forcée, pour qu'un "
                 "relecteur puisse la retrouver.",
        )

    saisi = any(v is not None for v in valeurs.values()) or any(
        v is not None for v in gaz.values()
    ) or mode_vent != "—"

    if st.button("Enregistrer le bilan", type="primary", use_container_width=True,
                 disabled=not saisi):
        if avertissements and not forcer:
            st.error(
                "Corrigez les valeurs signalées, ou cochez « Forcer "
                "l'enregistrement » puis validez à nouveau."
            )
            return
        bilans_service.enregistrer_resultats(
            contexte.base(), sejour["id"], date_heure, valeurs,
            utilisateur_id=contexte.utilisateur_id(), saisie_forcee=forcer,
        )
        if mode_vent != "—" or any(v is not None for v in gaz.values()):
            bilans_service.enregistrer_gaz_du_sang(
                contexte.base(), sejour["id"], date_heure,
                mode_ventilatoire=None if mode_vent == "—" else mode_vent,
                debit_o2=debit_o2, utilisateur_id=contexte.utilisateur_id(), **gaz,
            )
        for cle in list(st.session_state):
            if cle.startswith(("bilan_", "gds_")) and cle != "bilan_date_heure":
                del st.session_state[cle]
        st.success("Bilan enregistré.")
        st.rerun()


def vue_cinetique(sejour: dict) -> None:
    """Ce qu'un clinicien regarde vraiment : la dernière valeur et sa
    variation depuis la veille, puis la ligne complète à travers les jours,
    puis la courbe. Dans cet ordre."""
    presents = bilans_service.analytes_renseignes(contexte.base(), sejour["id"])
    if not presents:
        st.caption("Aucun bilan enregistré pour ce séjour.")
        return

    st.subheader("Cinétique")

    panels = [(c, t, [a for a in ids if a in presents])
              for c, t, ids in bilans_service.PANELS]
    panels = [p for p in panels if p[2]]
    noms_panels = [t for _c, t, _ids in panels] + ["Tout"]
    choix_panel = st.radio(
        "Panneau", noms_panels, horizontal=True, key="panel_cinetique",
        label_visibility="collapsed",
    )
    if choix_panel == "Tout":
        ids_affiches = presents
    else:
        ids_affiches = next(ids for _c, t, ids in panels if t == choix_panel)

    # 1. Dernière valeur et variation depuis le prélèvement précédent
    variations = bilans_service.dernieres_variations(contexte.base(), sejour["id"], ids_affiches)
    variations = [v for v in variations if v.valeur is not None]
    if variations:
        colonnes = st.columns(min(len(variations), 5))
        for i, v in enumerate(variations):
            with colonnes[i % len(colonnes)]:
                st.metric(
                    f"{v.libelle} ({v.unite})" if v.unite else v.libelle,
                    champs.format_valeur(v.valeur),
                    delta=None if v.delta in (None, 0) else champs.format_valeur(v.delta),
                    delta_color="off",
                )
                if v.alerte:
                    couleur = theme.ROUGE if v.alerte == "haut" else theme.BLEU
                    mot = "au-dessus" if v.alerte == "haut" else "en dessous"
                    a = cat.analyte(v.analyte)
                    borne = a.borne_haute if v.alerte == "haut" else a.borne_basse
                    st.markdown(
                        f"<span style='color:{couleur};font-size:.75rem;font-weight:600'>"
                        f"{mot} de {champs.format_valeur(borne)}</span>",
                        unsafe_allow_html=True,
                    )

    # 2. Le tableau analytes × dates — la lecture de fond
    dates, matrice = bilans_service.tableau_par_date(contexte.base(), sejour["id"], ids_affiches)
    if dates:
        import pandas as pd

        colonnes_dates = dates[-8:]  # les huit derniers prélèvements tiennent à l'écran
        tableau = {}
        for id_analyte in ids_affiches:
            if id_analyte not in matrice:
                continue
            a = cat.analyte(id_analyte)
            etiquette = f"{a.libelle} ({a.unite})" if a.unite else a.libelle
            tableau[etiquette] = [
                champs.format_valeur(matrice[id_analyte].get(d)) for d in colonnes_dates
            ]
        if tableau:
            entetes = [format_date_fr(d[:10]) + (f" {d[11:16]}" if len(d) >= 16 else "")
                       for d in colonnes_dates]
            st.dataframe(
                pd.DataFrame(tableau, index=entetes).T,
                use_container_width=True,
            )
            st.caption(
                "Valeurs telles que saisies. Les bornes usuelles servant à signaler "
                "une anomalie restent à valider par un senior (question ouverte 8)."
            )

    # 3. Les courbes, une par analyte du panneau
    traçables = [i for i in ids_affiches
                 if len(bilans_service.historique_analyte(contexte.base(), sejour["id"], i)) >= 2]
    if traçables:
        with st.expander("📈 Courbes", expanded=len(traçables) <= 4):
            import pandas as pd

            colonnes = st.columns(2)
            for i, id_analyte in enumerate(traçables):
                a = cat.analyte(id_analyte)
                historique = bilans_service.historique_analyte(contexte.base(), sejour["id"], id_analyte)
                with colonnes[i % 2]:
                    st.caption(f"{a.libelle} ({a.unite})" if a.unite else a.libelle)
                    df = pd.DataFrame(historique)
                    df["date_heure"] = pd.to_datetime(df["date_heure"])
                    st.line_chart(df.set_index("date_heure")["valeur_num"], height=180)
