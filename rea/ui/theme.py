"""Habillage visuel commun (CSS injecté une fois par page).

Trois contraintes, dans cet ordre :

1. **Densité** — un écran de réanimation doit montrer beaucoup d'un coup.
   On préfère toujours élargir plutôt qu'allonger : le défilement fait
   perdre le fil, la largeur non.
2. **Contraste** — l'écran est lu debout, parfois de loin, dans une pièce
   éclairée.
3. **Un code couleur constant** dans toute l'application :

   * rouge   — alerte : allergie, décès, valeur trop haute, dernier jour
   * orange  — attention : dispositif invasif, échéance proche
   * bleu    — information calculée par le logiciel (compteurs, totaux)
   * vert    — stable, disponible
   * violet  — examens et explorations
"""

from __future__ import annotations

import streamlit as st

from .. import listes

ROUGE = "#D62839"
ORANGE = "#E8850C"
BLEU = "#1D6FB8"
VERT = "#1E8E6A"
VIOLET = "#7048B6"
GRIS = "#5B6470"
BORDURE = "#DDE3EC"

# Couleur d'accent par voie d'administration : la pancarte se lit d'un coup
# d'œil parce que chaque voie a toujours la même couleur.
COULEUR_VOIE = {
    "PO": VERT,
    "IV": ROUGE,
    "PSE": ORANGE,
    "SC": BLEU,
    "AEROSOL": VIOLET,
    "SOINS": GRIS,
    "KINE": GRIS,
    "ENTREES": BLEU,
}

# Un bouton par voie : le sélecteur de voie du panneau « Ajouter une ligne »
# retrouve, bouton par bouton, la couleur que cette voie porte déjà sur la
# pancarte — sans quoi les deux ne se répondraient pas visuellement.
#
# Le CSS vise les boutons par leur rang (`nth-of-type`), il suit donc l'ordre
# des voies à l'écran, et non celui de `COULEUR_VOIE`. Les deux ont coïncidé
# jusqu'au jour où l'ordre des blocs a changé (10 septembre 2026) : les
# couleurs se sont alors décalées d'un cran, chaque bouton portant celle de
# son voisin. `tests/test_ordre_des_voies.py` interdit que cela recommence.
_CSS_BOUTONS_VOIES = "\n".join(
    f'div[data-testid="stButtonGroup"] button[data-variant="segmented_control"]:nth-of-type({i}) {{'
    f" border-color:{couleur} !important; }}\n"
    f'div[data-testid="stButtonGroup"] button[data-variant="segmented_control"]:nth-of-type({i})[aria-checked="true"] {{'
    f" background:{couleur} !important; border-color:{couleur} !important; }}\n"
    f'div[data-testid="stButtonGroup"] button[data-variant="segmented_control"]:nth-of-type({i})[aria-checked="true"] p {{'
    f" color:#fff !important; }}"
    for i, couleur in enumerate(
        (COULEUR_VOIE.get(voie, GRIS) for voie in listes.ORDRE_VOIES), start=1
    )
)

# Idem pour les familles de dispositifs.
COULEUR_DISPOSITIF = {
    "intubation": ROUGE, "sedation": ROUGE, "tracheotomie": ROUGE,
    "sng": ORANGE, "gastrostomie": ORANGE,
    "kt_central": VIOLET, "picc": VIOLET, "kta": VIOLET, "voie_peripherique": VIOLET,
    "sonde_urinaire": BLEU, "ktsp": BLEU,
    "drain_thoracique": GRIS, "drain_abdominal": GRIS, "dve": GRIS, "eer": GRIS,
}

CSS = f"""
<style>
/* ---- Occuper la largeur, économiser la hauteur ---------------------- */
.block-container {{
    /* 2.6rem en haut : moins que le défaut, mais assez pour passer sous la
       barre d'outils fixe de Streamlit, qui masquerait le premier titre. */
    padding: 2.6rem 1.4rem 2rem 1.4rem !important;
    max-width: 100% !important;
}}

/* ---- La barre d'outils de Streamlit ----------------------------------
   On retire ses ACTIONS de droite (« Deploy », le menu ⋮), pour deux raisons :
   « Deploy » n'a aucun sens dans un service — le logiciel tourne déjà sur le
   PC de la réanimation — et elles occupent le coin en haut à droite,
   précisément là où se trouve notre accès Admin, qui passait dessous.

   Mais on NE cache PAS toute la barre d'outils : c'est elle qui, à gauche,
   porte la flèche pour rouvrir la barre latérale une fois repliée. La cacher,
   c'était la replier sans pouvoir la rouvrir — exactement le piège que le
   service a signalé (11 septembre). On vise donc « Deploy » et le menu ⋮
   nommément, et non leur conteneur. */
div[data-testid="stToolbarActions"],
div[data-testid="stAppDeployButton"],
div[data-testid="stMainMenu"],
[data-testid="stMainMenuButton"] {{ display: none !important; }}
div[data-testid="stVerticalBlock"] {{ gap: .4rem; }}
div[data-testid="stHorizontalBlock"] {{ gap: .7rem; }}

/* ---- La poignée qui plie et déplie la barre latérale -----------------
   Elle existe déjà, mais Streamlit la dessine minuscule et pâle : le service
   ne la trouvait pas, et croyait la barre disparue. On la rend bien visible —
   entourée, plus grande — sans jamais la masquer, pour qu'on puisse toujours
   replier la barre et la rouvrir (demande du service, 11 septembre).

   La flèche qui rouvre la barre une fois repliée (en haut à gauche) reçoit le
   même traitement : c'est elle qu'on cherche quand l'écran paraît vide. */
button[data-testid="stSidebarCollapseButton"],
button[data-testid="stExpandSidebarButton"],
div[data-testid="stSidebarCollapsedControl"] button,
div[data-testid="collapsedControl"] button {{
    border: 1px solid {ROUGE} !important;
    border-radius: 8px !important;
    color: {ROUGE} !important;
    background: #ffffff !important;
    width: 2rem !important; height: 2rem !important;
    opacity: 1 !important;
}}

/* ---- Échelle typographique -------------------------------------------
   Volontairement plus petite que le défaut de Streamlit : les cartes sont
   étroites (six par rangée), un texte trop grand les fait paraître pleines
   à craquer alors qu'elles portent trois informations. */
html, body, [class*="css"] {{ font-size: 15px; }}
h1 {{ font-size: 1.45rem !important; font-weight: 700 !important; margin-bottom: .15rem !important; }}
h2 {{ font-size: 1.1rem !important; margin: .2rem 0 .1rem 0 !important; }}
h3, h4, h5 {{ font-size: .95rem !important; margin: .1rem 0 !important; }}
hr {{ margin: .45rem 0 !important; }}
p, li, .stMarkdown {{ font-size: .86rem; }}
label, .stSelectbox label, .stTextInput label {{ font-size: .82rem !important; }}

/* ---- Boutons compacts ------------------------------------------------ */
div[data-testid="stButton"] > button {{
    padding: .28rem .7rem; font-size: .84rem; border-radius: 8px;
    border: 1px solid {BORDURE}; min-height: 0;
}}
div[data-testid="stButton"] > button:hover {{ border-color: {ROUGE}; color: {ROUGE}; }}
div[data-testid="stExpander"] details {{ border-radius: 9px; border-color: {BORDURE}; }}
div[data-testid="stExpander"] summary p {{ font-size: .86rem; }}

/* ---- Métriques compactes -------------------------------------------- */
div[data-testid="stMetric"] {{
    background: #FFF; border: 1px solid {BORDURE}; border-radius: 9px;
    padding: .4rem .6rem; border-left: 3px solid {BLEU};
}}
div[data-testid="stMetricLabel"] p {{ font-size: .7rem !important; color: {GRIS}; font-weight: 600; }}
div[data-testid="stMetricValue"] {{ font-size: 1.15rem !important; font-weight: 700; }}
div[data-testid="stMetricDelta"] {{ font-size: .74rem !important; }}

/* ---- Cartes : de l'air à l'intérieur, des bords nets ---------------- */
div[data-testid="stVerticalBlockBorderWrapper"] {{
    border-radius: 10px !important; border-color: {BORDURE} !important;
}}
div[data-testid="stVerticalBlockBorderWrapper"] > div > div[data-testid="stVerticalBlock"] {{
    padding: .15rem .1rem;
}}

/* ---- Tuiles de lit --------------------------------------------------- */
.rea-lit {{ line-height: 1.3; }}
.rea-lit-num {{ font-size: .66rem; font-weight: 700; letter-spacing: .07em;
    text-transform: uppercase; color: {GRIS}; }}
.rea-lit-nom {{ font-size: .92rem; font-weight: 700; margin: 2px 0 1px 0;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.rea-lit-motif {{ font-size: .76rem; color: {GRIS}; margin-bottom: 3px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.rea-lit-libre {{ font-size: .84rem; color: {VERT}; font-weight: 600; margin: 2px 0 4px 0; }}

/* ---- Pastilles d'état ------------------------------------------------ */
.rea-chips {{ display: flex; flex-wrap: wrap; gap: 3px; margin: 1px 0 6px 0; }}
.rea-chip {{
    display: inline-flex; align-items: center; padding: 0 6px; border-radius: 999px;
    font-size: .68rem; font-weight: 600; line-height: 1.6; border: 1px solid transparent;
    white-space: nowrap; max-width: 100%; overflow: hidden; text-overflow: ellipsis;
}}
.rea-chip.alerte    {{ background: #FCE4E7; color: #96131F; border-color: #F3BFC5; }}
.rea-chip.attention {{ background: #FDF0DC; color: #8A5200; border-color: #F5D9AE; }}
.rea-chip.info      {{ background: #E4EEF9; color: #144E7F; border-color: #C2D9F0; }}
.rea-chip.ok        {{ background: #E1F2EC; color: #14624A; border-color: #B9E0D2; }}
.rea-chip.examen    {{ background: #EEE8F8; color: #4C2E86; border-color: #D6C8F0; }}
.rea-chip.neutre    {{ background: #EEF1F6; color: #454C58; border-color: {BORDURE}; }}

/* ---- Blocs de section colorés --------------------------------------- */
.rea-bloc {{
    border: 1px solid {BORDURE}; border-left: 3px solid {GRIS};
    border-radius: 8px; padding: 7px 10px 6px 10px; background: #fff; margin-bottom: 6px;
}}
.rea-bloc-titre {{
    font-size: .64rem; font-weight: 800; letter-spacing: .085em;
    text-transform: uppercase; margin-bottom: 3px;
}}
.rea-bloc ul {{ margin: 0; padding-left: .95rem; }}
.rea-bloc li {{ font-size: .82rem; line-height: 1.55; }}
/* Variante « grand » — pour les trois blocs de tête de l'écran Identité, lus
   de loin et rarement plus de six lignes : la place est là (demande du
   service, 8 septembre). */
.rea-bloc.grand {{ padding: 10px 13px 9px 13px; }}
.rea-bloc.grand .rea-bloc-titre {{ font-size: .72rem; margin-bottom: 6px; }}
.rea-bloc.grand li {{ font-size: 1rem; line-height: 1.75; }}
.rea-bloc li.arretee, .rea-bloc li span.arretee, .arretee {{ text-decoration: line-through; color: {GRIS}; }}
.rea-j {{ font-weight: 700; color: {BLEU}; }}
.rea-fin {{ color: {ROUGE}; font-weight: 700; }}

/* ---- Mode visite : lu debout, à un mètre de l'écran ------------------
   Le reste de l'application est lu assis, à cinquante centimètres, en train
   de saisir. La visite, c'est l'inverse : on ne tape rien, on lit un
   portable posé sur le chariot, et ce qu'on cherche est toujours la même
   chose — quel traitement, à quel jour, à quelle dose. D'où une échelle
   nettement plus grande et une seule colonne de valeurs alignées : l'œil
   descend, il ne balaie pas (demande du service, 9 septembre). */
.rea-v-bloc {{
    border: 1px solid {BORDURE}; border-left: 4px solid {GRIS};
    border-radius: 10px; background: #fff; margin-bottom: 9px; overflow: hidden;
}}
.rea-v-titre {{
    font-size: .7rem; font-weight: 800; letter-spacing: .09em;
    text-transform: uppercase; padding: 6px 12px 5px 12px;
    border-bottom: 1px solid {BORDURE};
}}
.rea-v-ligne {{
    display: flex; align-items: baseline; gap: 10px;
    padding: 6px 12px; border-bottom: 1px solid #EEF1F6; font-size: 1.02rem;
}}
.rea-v-ligne:last-child {{ border-bottom: none; }}
.rea-v-ligne:nth-child(even) {{ background: #FAFBFD; }}
/* Le compteur de jours, en tête et de largeur fixe : c'est la colonne que
   l'œil suit pour trouver « J7/7 » sans lire les lignes une à une. */
.rea-v-j {{
    flex: none; min-width: 3.5rem; font-weight: 700; font-size: .84rem;
    color: {BLEU}; text-align: right;
}}
.rea-v-j.fin {{ color: {ROUGE}; }}
.rea-v-produit {{ flex: 1 1 auto; font-weight: 600; }}
.rea-v-dose {{
    flex: none; font-variant-numeric: tabular-nums; font-weight: 700;
    color: #1A2430; white-space: nowrap;
}}
.rea-v-detail {{ font-size: .8rem; color: {GRIS}; font-weight: 400; }}
.rea-v-ligne.arretee .rea-v-produit {{ text-decoration: line-through; color: {GRIS}; }}
.rea-v-vide {{ padding: 8px 12px; font-size: .86rem; color: {GRIS}; }}

/* Une valeur de biologie et sa précédente : le chiffre gros, la cinétique
   petite à côté. Une valeur seule ne dit pas si le rein décroche. */
.rea-v-mesure {{
    display: flex; align-items: baseline; gap: 8px;
    padding: 5px 12px; border-bottom: 1px solid #EEF1F6; font-size: .95rem;
}}
.rea-v-mesure:last-child {{ border-bottom: none; }}
.rea-v-nom {{ flex: 1 1 auto; color: {GRIS}; }}
.rea-v-val {{ font-weight: 700; font-size: 1.08rem; font-variant-numeric: tabular-nums; }}
.rea-v-val.haut {{ color: {ROUGE}; }}
.rea-v-val.bas {{ color: {BLEU}; }}
.rea-v-avant {{ font-size: .78rem; color: {GRIS}; font-variant-numeric: tabular-nums; }}
.rea-v-texte {{ padding: 7px 12px; font-size: .95rem; line-height: 1.55; }}

/* ---- Prescrit : la ligne de pancarte, lisible sans se pencher --------
   Elle était en .82rem, la taille d'une légende. C'est pourtant la ligne la
   plus lue du logiciel. */
.rea-p-ligne {{ display: flex; align-items: baseline; gap: 8px; font-size: .95rem; }}
.rea-p-produit {{ flex: 1 1 auto; }}
.rea-p-dose {{ flex: none; font-variant-numeric: tabular-nums; font-weight: 700; }}

/* ---- Tableaux plus denses ------------------------------------------- */
div[data-testid="stDataFrame"] {{ font-size: .8rem; }}

/* ---- Sélecteur de voie (panneau « Ajouter une ligne ») --------------- */
div[data-testid="stButtonGroup"] > div[role="radiogroup"] {{ flex-wrap: wrap; }}
{_CSS_BOUTONS_VOIES}

/* ---- Au doigt, pas à la souris ---------------------------------------
   Les infirmiers ouvrent leur poste sur un téléphone, au lit du malade,
   parfois avec des gants. Une cible de 16 px se rate une fois sur trois —
   et se rater ici veut dire cocher le traitement du dessous. 44 px est le
   minimum recommandé pour le doigt ; on le tient sur tout ce qui se
   touche, pas seulement sur l'écran infirmier : les mêmes doigts ouvrent
   les autres écrans sur la même tablette. */
@media (max-width: 640px) {{
    /* Les marges latérales se resserrent, pas celle du haut : la barre
       d'outils de Streamlit est fixe et masquerait le titre de l'écran. */
    .block-container {{ padding: 2.6rem .7rem 2rem .7rem !important; }}
    button {{ min-height: 46px !important; }}
    input[type="text"], input[type="number"], input[type="password"] {{
        min-height: 44px !important;
        /* Sous 16 px, iOS zoome de lui-même à chaque champ touché, et la
           page reste zoomée ensuite. */
        font-size: 16px !important;
    }}
    div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {{
        min-height: 44px !important;
    }}
    div[data-testid="stCheckbox"] label {{ min-height: 40px; align-items: center; }}
    h1 {{ font-size: 1.35rem !important; }}
    h2, h3 {{ font-size: 1.1rem !important; }}
    /* Un tableau large défile seul plutôt que d'élargir la page. */
    .rea-bloc table {{ min-width: max-content; }}
}}
</style>
"""


def appliquer() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def chips(elements: list[tuple[str, str]]) -> None:
    """Bandeau de pastilles. `elements` : (texte, style) où style vaut
    alerte / attention / info / ok / examen / neutre."""
    if not elements:
        return
    st.markdown(
        '<div class="rea-chips">'
        + "".join(f'<span class="rea-chip {s}">{t}</span>' for t, s in elements)
        + "</div>",
        unsafe_allow_html=True,
    )


def bloc(titre: str, lignes_html: list[str], couleur: str = GRIS, *, grand: bool = False) -> None:
    """Bloc de section : un titre coloré et une liste. Bien plus compact
    qu'un `st.subheader` suivi de `st.write` ligne à ligne.

    `grand` agrandit le texte : réservé aux blocs qu'on lit de loin et qui
    tiennent en quelques lignes (les trois blocs de tête de l'écran Identité).
    """
    corps = "".join(f"<li>{l}</li>" for l in lignes_html) if lignes_html else ""
    classe = "rea-bloc grand" if grand else "rea-bloc"
    st.markdown(
        f'<div class="{classe}" style="border-left-color:{couleur}">'
        f'<div class="rea-bloc-titre" style="color:{couleur}">{titre}</div>'
        f"<ul>{corps}</ul></div>",
        unsafe_allow_html=True,
    )


def bloc_html(titre: str, contenu: str, couleur: str = GRIS) -> None:
    st.markdown(
        f'<div class="rea-bloc" style="border-left-color:{couleur}">'
        f'<div class="rea-bloc-titre" style="color:{couleur}">{titre}</div>'
        f"{contenu}</div>",
        unsafe_allow_html=True,
    )


def courbe(points: list[tuple[str, float]], *, hauteur: int = 160, couleur: str = BLEU) -> None:
    """Une courbe simple en SVG — pas `st.line_chart` (Altair), dont une
    version incompatible avec l'environnement Python du poste peut planter
    tout l'écran (remarque du service, 6 septembre). Chaque poste installe
    ses dépendances lui-même ; ce logiciel ne doit dépendre que de ce qui
    est indispensable.

    `points` : (étiquette, valeur), dans l'ordre chronologique.
    """
    valeurs = [v for _e, v in points]
    if len(valeurs) < 2:
        st.caption("Pas assez de points pour tracer une courbe.")
        return
    minimum, maximum = min(valeurs), max(valeurs)
    etendue = (maximum - minimum) or 1
    largeur, marge = 600, 8
    pas = (largeur - 2 * marge) / (len(points) - 1)

    def xy(i: int, v: float) -> tuple[float, float]:
        x = marge + i * pas
        y = hauteur - marge - ((v - minimum) / etendue) * (hauteur - 2 * marge)
        return x, y

    coords = [xy(i, v) for i, v in enumerate(valeurs)]
    polyligne = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    cercles = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{couleur}"/>' for x, y in coords
    )
    st.markdown(
        f'<svg viewBox="0 0 {largeur} {hauteur}" style="width:100%;height:{hauteur}px" '
        'preserveAspectRatio="none">'
        f'<line x1="{marge}" y1="{hauteur - marge}" x2="{largeur - marge}" y2="{hauteur - marge}" '
        f'stroke="{BORDURE}" stroke-width="1"/>'
        f'<polyline points="{polyligne}" fill="none" stroke="{couleur}" stroke-width="2" '
        'vector-effect="non-scaling-stroke"/>'
        f"{cercles}</svg>",
        unsafe_allow_html=True,
    )
    st.caption(
        f"{points[0][0]} → {points[-1][0]} · min {_virgule(minimum)} · "
        f"max {_virgule(maximum)}"
    )


def _virgule(valeur: float) -> str:
    from . import champs

    return champs.format_valeur(valeur).replace(".", ",")
