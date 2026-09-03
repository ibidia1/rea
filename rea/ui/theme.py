"""Habillage visuel commun (CSS injecté une fois par page).

L'écran est lu debout, parfois de loin, dans une pièce éclairée : on
privilégie le contraste et la taille des cibles cliquables sur l'esthétique.
Le code couleur est constant dans toute l'application :

* rouge   — alerte : allergie, décès, valeur hors norme haute, dernier jour
* orange  — attention : échéance proche, valeur hors norme basse
* bleu    — information calculée par le logiciel (compteurs, totaux)
* vert    — situation stable / lit libre
"""

from __future__ import annotations

import streamlit as st

ROUGE = "#E63946"
ORANGE = "#F4A261"
BLEU = "#1D6FB8"
VERT = "#2A9D8F"
GRIS = "#6B7280"

CSS = f"""
<style>
/* --- Densité : une pancarte tient à l'écran sans défilement inutile --- */
.block-container {{ padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1400px; }}
h1 {{ font-size: 1.9rem !important; font-weight: 700 !important; }}
h2 {{ font-size: 1.35rem !important; }}
h3 {{ font-size: 1.1rem !important; }}

/* --- Tuiles de lit --- */
div[data-testid="stButton"] > button {{
    border-radius: 10px;
    border: 1px solid #E2E6EE;
    transition: border-color .12s, box-shadow .12s, transform .06s;
}}
div[data-testid="stButton"] > button:hover {{
    border-color: {ROUGE};
    box-shadow: 0 2px 10px rgba(0,0,0,.07);
}}
div[data-testid="stButton"] > button:active {{ transform: scale(.99); }}

/* --- Bandeaux d'état du patient --- */
.rea-chips {{ display: flex; flex-wrap: wrap; gap: 6px; margin: 2px 0 14px 0; }}
.rea-chip {{
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 11px; border-radius: 999px;
    font-size: .82rem; font-weight: 600; line-height: 1.5;
    border: 1px solid transparent; white-space: nowrap;
}}
.rea-chip.alerte  {{ background: #FDE8EA; color: #9B1C26; border-color: #F5C2C7; }}
.rea-chip.attention {{ background: #FEF3E2; color: #8A5200; border-color: #F8D9A8; }}
.rea-chip.info    {{ background: #E7F0FA; color: #14507F; border-color: #C5DCF2; }}
.rea-chip.ok      {{ background: #E6F5F3; color: #1E6F65; border-color: #BEE3DE; }}
.rea-chip.neutre  {{ background: #F1F4F9; color: #4B5563; border-color: #E2E6EE; }}

/* --- Cartes de section --- */
.rea-carte {{
    border: 1px solid #E2E6EE; border-radius: 12px;
    padding: 14px 16px; background: #fff; margin-bottom: 12px;
}}
.rea-carte-titre {{
    font-size: .72rem; font-weight: 700; letter-spacing: .09em;
    text-transform: uppercase; color: {GRIS}; margin-bottom: 8px;
}}

/* --- Lignes de prescription --- */
.rea-ligne {{ padding: 3px 0; font-size: .95rem; }}
.rea-ligne.arretee {{ text-decoration: line-through; color: {GRIS}; }}
.rea-compteur {{ font-weight: 700; color: {BLEU}; }}
.rea-dernier-jour {{ color: {ROUGE}; font-weight: 600; }}

/* --- Valeurs de bilan --- */
.rea-haut {{ color: {ROUGE}; font-weight: 700; }}
.rea-bas  {{ color: {BLEU}; font-weight: 700; }}

/* --- Onglets un peu plus lisibles --- */
button[data-baseweb="tab"] {{ font-size: 1rem !important; font-weight: 600 !important; }}
</style>
"""


def appliquer() -> None:
    """À appeler une fois, au début du script."""
    st.markdown(CSS, unsafe_allow_html=True)


def chips(elements: list[tuple[str, str]]) -> None:
    """Bandeau de pastilles d'état. `elements` : (texte, style) où style vaut
    alerte / attention / info / ok / neutre."""
    if not elements:
        return
    html = '<div class="rea-chips">' + "".join(
        f'<span class="rea-chip {style}">{texte}</span>' for texte, style in elements
    ) + "</div>"
    st.markdown(html, unsafe_allow_html=True)


def carte(titre: str, contenu_html: str) -> None:
    st.markdown(
        f'<div class="rea-carte"><div class="rea-carte-titre">{titre}</div>{contenu_html}</div>',
        unsafe_allow_html=True,
    )
