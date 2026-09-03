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
    padding: 2.6rem 1.6rem 2rem 1.6rem !important;
    max-width: 100% !important;
}}
div[data-testid="stVerticalBlock"] {{ gap: .45rem; }}
div[data-testid="stHorizontalBlock"] {{ gap: .6rem; }}
h1 {{ font-size: 1.55rem !important; font-weight: 700 !important; margin-bottom: .2rem !important; }}
h2 {{ font-size: 1.15rem !important; margin: .2rem 0 .1rem 0 !important; }}
h3, h4, h5 {{ font-size: .98rem !important; margin: .1rem 0 !important; }}
hr {{ margin: .5rem 0 !important; }}
p, li, .stMarkdown {{ font-size: .92rem; }}
div[data-testid="stExpander"] details {{ border-radius: 10px; border-color: {BORDURE}; }}

/* ---- Métriques compactes -------------------------------------------- */
div[data-testid="stMetric"] {{
    background: #FFF; border: 1px solid {BORDURE}; border-radius: 10px;
    padding: .45rem .7rem; border-left: 4px solid {BLEU};
}}
div[data-testid="stMetricLabel"] p {{ font-size: .72rem !important; color: {GRIS}; font-weight: 600; }}
div[data-testid="stMetricValue"] {{ font-size: 1.5rem !important; }}

/* ---- Tuiles et cartes ----------------------------------------------- */
div[data-testid="stVerticalBlockBorderWrapper"] {{
    border-radius: 11px !important; border-color: {BORDURE} !important;
}}
.rea-lit {{ line-height: 1.25; }}
.rea-lit-num {{ font-size: .7rem; font-weight: 700; letter-spacing: .06em;
    text-transform: uppercase; color: {GRIS}; }}
.rea-lit-nom {{ font-size: 1rem; font-weight: 700; margin: 1px 0; }}
.rea-lit-motif {{ font-size: .8rem; color: {GRIS}; margin-bottom: 4px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.rea-lit-libre {{ font-size: .9rem; color: {VERT}; font-weight: 600; }}

/* ---- Pastilles d'état ------------------------------------------------ */
.rea-chips {{ display: flex; flex-wrap: wrap; gap: 4px; margin: 2px 0 8px 0; }}
.rea-chip {{
    display: inline-flex; align-items: center; padding: 1px 8px; border-radius: 999px;
    font-size: .74rem; font-weight: 600; line-height: 1.55; border: 1px solid transparent;
    white-space: nowrap;
}}
.rea-chip.alerte    {{ background: #FCE4E7; color: #96131F; border-color: #F3BFC5; }}
.rea-chip.attention {{ background: #FDF0DC; color: #8A5200; border-color: #F5D9AE; }}
.rea-chip.info      {{ background: #E4EEF9; color: #144E7F; border-color: #C2D9F0; }}
.rea-chip.ok        {{ background: #E1F2EC; color: #14624A; border-color: #B9E0D2; }}
.rea-chip.examen    {{ background: #EEE8F8; color: #4C2E86; border-color: #D6C8F0; }}
.rea-chip.neutre    {{ background: #EEF1F6; color: #454C58; border-color: {BORDURE}; }}

/* ---- Blocs de section colorés --------------------------------------- */
.rea-bloc {{
    border: 1px solid {BORDURE}; border-left: 4px solid {GRIS};
    border-radius: 9px; padding: 8px 11px; background: #fff; margin-bottom: 7px;
}}
.rea-bloc-titre {{
    font-size: .68rem; font-weight: 800; letter-spacing: .09em;
    text-transform: uppercase; margin-bottom: 4px;
}}
.rea-bloc ul {{ margin: 0; padding-left: 1.05rem; }}
.rea-bloc li {{ font-size: .88rem; line-height: 1.5; }}
.rea-bloc li.arretee {{ text-decoration: line-through; color: {GRIS}; }}
.rea-j {{ font-weight: 700; color: {BLEU}; }}
.rea-fin {{ color: {ROUGE}; font-weight: 700; }}

/* ---- Tableaux plus denses ------------------------------------------- */
div[data-testid="stDataFrame"] {{ font-size: .85rem; }}
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


def bloc(titre: str, lignes_html: list[str], couleur: str = GRIS) -> None:
    """Bloc de section : un titre coloré et une liste. Bien plus compact
    qu'un `st.subheader` suivi de `st.write` ligne à ligne."""
    corps = "".join(f"<li>{l}</li>" for l in lignes_html) if lignes_html else ""
    st.markdown(
        f'<div class="rea-bloc" style="border-left-color:{couleur}">'
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
