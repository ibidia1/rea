"""La surveillance horaire, vue par le médecin (SPEC §5.8).

L'infirmier la remplit heure par heure ; jusqu'ici personne d'autre ne la
voyait. Le médecin ouvrait l'évolution du jour avec une seule valeur par
constante — celle qu'on lui disait à la visite — alors que vingt-quatre
étaient dans la base (demande du service, 10 septembre).

Or c'est le contraire de ce qu'on cherche en réanimation : une PA moyenne de
75 sur la journée ne dit pas si le patient a passé la nuit à 55. On lit une
**courbe**, et les deux chiffres qui décident sont les extrêmes, pas la
moyenne.

Cet écran n'écrit rien : la saisie appartient à celui qui est au lit du
malade. Le médecin lit, et reporte dans son évolution ce qu'il retient — il
ne corrige pas à distance un relevé qu'il n'a pas fait.

Trois précautions de lecture, portées par le rendu lui-même :

* les heures sont dans l'ordre du poste (7 → 6), pas de minuit à minuit,
  sinon la fin de la nuit s'afficherait avant le matin qui l'a précédée ;
* les vacations sont séparées, parce qu'un décrochage à la relève se lit
  autrement qu'un décrochage en pleine garde ;
* on ne totalise que ce qui se totalise : min-max pour les constantes,
  somme pour les sorties. La somme des températures d'une journée n'existe
  pas.
"""

from __future__ import annotations

import html

import streamlit as st

from ..domaine import vacations as dom_vacations
from ..domaine.dates import format_date_fr
from ..services import affectations as affectations_service
from ..services import constantes as constantes_service
from . import theme


def bloc_du_jour(base, sejour_id: str, date_jour: str, *, titre: str | None = None) -> None:
    """La grille des 24 h relevées ce jour-là, en lecture seule."""
    grille = constantes_service.du_jour(base, sejour_id, date_jour)
    if not grille:
        st.caption(
            f"Aucun relevé horaire saisi pour le {format_date_fr(date_jour)}. "
            "La surveillance se note dans l'écran « Mon poste » de l'infirmier."
        )
        return
    heures = dom_vacations.heures_du_jour()
    theme.bloc_html(
        titre or f"Surveillance horaire du {format_date_fr(date_jour)}",
        _tableau(grille, heures) + _signatures(base, sejour_id, date_jour),
        theme.BLEU,
    )


def _tableau(grille: dict, heures) -> str:
    bornes = _bornes_de_vacation()
    entetes = "".join(
        f"<th style='padding:.15rem .3rem;font-weight:600{_bord(h, bornes)}'>"
        f"{h:02d}</th>"
        for h in heures
    )
    lignes = ""
    for cle, libelle, unite in constantes_service.CLES:
        valeurs = [grille.get(h, {}).get(cle) for h in heures]
        if not any(v is not None for v in valeurs):
            continue
        cases = "".join(
            f"<td style='text-align:center;padding:.15rem .3rem{_bord(h, bornes)}'>"
            f"{_nombre(v)}</td>"
            for h, v in zip(heures, valeurs)
        )
        lignes += (
            "<tr>"
            f"<td style='padding:.15rem .4rem;white-space:nowrap;font-weight:600'>"
            f"{html.escape(libelle)}</td>"
            f"<td style='padding:.15rem .5rem;white-space:nowrap;"
            f"border-right:1px solid #94a3b8'>{_resume(cle, valeurs, unite)}</td>"
            f"{cases}</tr>"
        )
    # Le résumé **avant** les heures, et non après. Vingt-quatre colonnes ne
    # tiennent pas dans la moitié droite d'un écran de visite : le tableau
    # défile, et ce qui dépasse est ce qu'on met à droite. Or la colonne qu'on
    # vient lire est justement celle-là — les extrêmes de la nuit, le total de
    # la diurèse. Les heures, elles, se déroulent quand on les cherche.
    return (
        "<div style='overflow-x:auto'><table style='font-size:.78rem;"
        "border-collapse:collapse'>"
        f"<tr style='color:#64748b'><th></th>"
        "<th style='padding:.15rem .5rem;border-right:1px solid #94a3b8;"
        "font-weight:600'>Journée</th>"
        f"{entetes}</tr>{lignes}</table></div>"
    )


def _resume(cle: str, valeurs, unite: str) -> str:
    """Min-max pour ce qui se surveille, total pour ce qui se perd.

    C'est la seule colonne que le médecin regarde vraiment quand il remplit
    son évolution, et se tromper de résumé la rendrait fausse : additionner
    des Glasgow ou moyenner une diurèse ne veut rien dire.
    """
    connues = [v for v in valeurs if v is not None]
    if not connues:
        return ""
    if cle in constantes_service.CLES_SOMMABLES:
        return (
            f"<b>{_nombre(sum(connues))}</b> {html.escape(unite)} "
            f"<span style='color:#94a3b8'>/ {len(connues)} h</span>"
        )
    bas, haut = min(connues), max(connues)
    if bas == haut:
        return f"<b>{_nombre(bas)}</b> {html.escape(unite)}"
    return f"<b>{_nombre(bas)} – {_nombre(haut)}</b> {html.escape(unite)}"


def _signatures(base, sejour_id: str, date_jour: str) -> str:
    """Qui a relevé, vacation par vacation — pour l'appeler, pas pour le
    contrôler. Un chiffre surprenant se vérifie en une conversation."""
    lignes = affectations_service.du_sejour(base, sejour_id, date_jour)
    if not lignes:
        return ""
    # Dans l'ordre des postes, pas dans celui où la base les rend : la
    # signature se lit comme la grille, du matin à la nuit.
    rang = {code: i for i, code in enumerate(dom_vacations.codes())}
    lignes = sorted(lignes, key=lambda l: rang.get(l.get("vacation"), 99))
    morceaux = []
    for ligne in lignes:
        texte = (
            f"{dom_vacations.libelle(ligne['vacation'])} : "
            f"{html.escape(ligne.get('soignant') or '—')}"
        )
        if ligne.get("telephone"):
            texte += f" ({html.escape(str(ligne['telephone']))})"
        morceaux.append(texte)
    par_vacation = " · ".join(morceaux)
    return (
        f"<div style='margin-top:.4rem;font-size:.75rem;color:#64748b'>"
        f"Relevé par — {par_vacation}</div>"
    )


def _bornes_de_vacation() -> set[int]:
    """Les heures qui ouvrent une vacation : c'est là que passe le trait."""
    return {dom_vacations.bornes(code)[0] for code in dom_vacations.codes()}


def _bord(heure: int, bornes: set[int]) -> str:
    return ";border-left:1px solid #94a3b8" if heure in bornes else ""


def _nombre(valeur) -> str:
    if valeur is None:
        return ""
    return str(int(valeur)) if float(valeur).is_integer() else f"{valeur:.1f}"
