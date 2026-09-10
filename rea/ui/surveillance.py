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
from ..services import evolution as evolution_service
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
    # Les recueils de CE patient : la diurèse, et chacun de ses drains. La clé
    # d'un drain porte l'identifiant du dispositif — elle ne peut donc pas
    # être écrite d'avance, on prend celles que la journée a vues (demande du
    # service, 10 septembre).
    recueils = _recueils_releves(grille)
    sorties = {
        cle: constantes_service.sorties_du_jour(base, sejour_id, date_jour, cle)
        for cle in recueils
    }
    noms = _noms_des_recueils(base, sejour_id, date_jour)
    theme.bloc_html(
        titre or f"Surveillance horaire du {format_date_fr(date_jour)}",
        _tableau(grille, heures, sorties, recueils, noms)
        + _reserves(sorties, noms)
        + _signatures(base, sejour_id, date_jour),
        theme.BLEU,
    )


def _recueils_releves(grille: dict) -> list[str]:
    """Les clés de recueil qui portent au moins un relevé, dans l'ordre du
    papier : la diurèse d'abord, les drains ensuite."""
    vues = {cle for mesures in grille.values() for cle in mesures}
    fixes = [cle for cle in constantes_service.CLES_NIVEAU if cle in vues]
    drains = sorted(
        cle for cle in vues if cle.startswith(constantes_service.PREFIXE_DRAIN)
    )
    return fixes + drains


def _noms_des_recueils(base, sejour_id: str, date_jour: str) -> dict[str, str]:
    """Clé de recueil -> le nom sous lequel on le désigne au lit du malade.

    « drain:8f3a-… » ne se lit pas. Les drains portent le nom que le service
    leur donne, numéroté quand il y en a deux au même endroit.
    """
    noms = {cle: libelle for cle, libelle, _u in constantes_service.SORTIES}
    for drain in evolution_service.drains_du_jour(base, sejour_id, date_jour):
        noms[constantes_service.cle_drain(drain["dispositif_id"])] = drain["libelle"]
    return noms


def _reserves(sorties: dict, noms: dict[str, str]) -> str:
    """Ce qui empêche de lire un total comme une mesure — dit, pas caché.

    Un niveau en baisse sans sac déclaré jeté, une heure sans relevé de
    référence : le total reste affiché, mais il ne se recopie pas dans une
    observation sans qu'on sache ce qu'il vaut."""
    messages: list[str] = []
    for cle, par_heure in sorties.items():
        for sortie in par_heure.values():
            if sortie.anomalie:
                messages.append(
                    f"{noms.get(cle, constantes_service.libelle(cle))} à "
                    f"{sortie.instant.hour:02d} h — {sortie.anomalie}"
                )
    if not messages:
        return ""
    lignes = "".join(f"<div>⚠ {html.escape(m)}</div>" for m in messages)
    return (
        f"<div style='margin-top:.4rem;font-size:.75rem;color:#b45309'>{lignes}</div>"
    )


def _tableau(grille: dict, heures, sorties: dict, recueils: list[str],
             noms: dict[str, str]) -> str:
    bornes = _bornes_de_vacation()
    entetes = "".join(
        f"<th style='padding:.3rem .45rem;font-weight:600{_bord(h, bornes)}'>"
        f"{h:02d}</th>"
        for h in heures
    )
    lignes = ""
    for cle, libelle, unite in constantes_service.VITALES:
        valeurs = [grille.get(h, {}).get(cle) for h in heures]
        if not any(v is not None for v in valeurs):
            continue
        lignes += _rangee(libelle, _extremes(valeurs, unite), valeurs, heures, bornes)

    for cle in recueils:
        libelle = noms.get(cle, cle)
        unite = "mL"
        par_heure = sorties.get(cle, {})
        niveaux = [grille.get(h, {}).get(cle) for h in heures]
        if not any(v is not None for v in niveaux):
            continue
        # Le volume d'abord, le niveau ensuite et en gris : c'est le volume
        # qu'on vient lire, le niveau n'est là que pour qu'on puisse le
        # vérifier. L'ordre inverse ferait prendre 900 à 13 h pour une diurèse
        # horaire de 900 mL.
        volumes = [
            par_heure[h].volume_ml if h in par_heure else None for h in heures
        ]
        connus = [v for v in volumes if v is not None]
        total = (
            f"<b>{_nombre(sum(connus))}</b> {html.escape(unite)} "
            f"<span style='color:#94a3b8'>/ {len(connus)} h</span>"
            if connus else ""
        )
        lignes += _rangee(libelle, total, volumes, heures, bornes)
        marques = [
            (_nombre(v) + (" ↺" if h in par_heure and par_heure[h].sac_jete else ""))
            for h, v in zip(heures, niveaux)
        ]
        lignes += _rangee(
            f"{libelle} — niveau", "", marques, heures, bornes,
            couleur="#94a3b8", brut=True,
        )
    # Le résumé **avant** les heures, et non après. Vingt-quatre colonnes ne
    # tiennent pas dans la moitié droite d'un écran de visite : le tableau
    # défile, et ce qui dépasse est ce qu'on met à droite. Or la colonne qu'on
    # vient lire est justement celle-là — les extrêmes de la nuit, le total de
    # la diurèse. Les heures, elles, se déroulent quand on les cherche.
    return (
        "<div style='overflow-x:auto'><table style='font-size:.95rem;"
        "border-collapse:collapse'>"
        f"<tr style='color:#64748b'><th></th>"
        "<th style='padding:.3rem .6rem;border-right:1px solid #94a3b8;"
        "font-weight:600'>Journée</th>"
        f"{entetes}</tr>{lignes}</table></div>"
    )


def _extremes(valeurs, unite: str) -> str:
    """Les deux chiffres qui décident, pour une constante : le plus bas et le
    plus haut. Une PA moyenne à 75 ne dit pas qu'on a passé la nuit à 55."""
    connues = [v for v in valeurs if v is not None]
    if not connues:
        return ""
    bas, haut = min(connues), max(connues)
    if bas == haut:
        return f"<b>{_nombre(bas)}</b> {html.escape(unite)}"
    return f"<b>{_nombre(bas)} – {_nombre(haut)}</b> {html.escape(unite)}"


def _rangee(libelle, resume, valeurs, heures, bornes, *, couleur="", brut=False) -> str:
    style = f";color:{couleur}" if couleur else ";font-weight:600"
    # `nowrap` sur les cases : le ↺ du sac jeté passait à la ligne et faisait
    # doubler la hauteur de toute la rangée pour une seule heure.
    cases = "".join(
        f"<td style='text-align:center;white-space:nowrap;"
        f"padding:.3rem .45rem{_bord(h, bornes)}"
        f"{';color:' + couleur if couleur else ''}'>"
        f"{v if brut else _nombre(v)}</td>"
        for h, v in zip(heures, valeurs)
    )
    return (
        "<tr>"
        f"<td style='padding:.3rem .55rem;white-space:nowrap;font-weight:600{style}'>"
        f"{html.escape(libelle)}</td>"
        f"<td style='padding:.3rem .6rem;white-space:nowrap;"
        f"border-right:1px solid #94a3b8'>{resume}</td>"
        f"{cases}</tr>"
    )


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
