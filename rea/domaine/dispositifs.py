"""Compteurs de jours des dispositifs et actes.

Deux conventions, celles employées au lit du malade :

* **en cours** — le jour de la pose est J1. « Intubé J3 » = troisième jour
  d'intubation. Même convention que le jour d'hospitalisation et que les
  compteurs de prescription (SPEC §5.4).
* **après retrait** — le jour de l'événement est J0. « Extubé J2 » = deux
  jours après l'extubation, comme « J2 post-opératoire ».

Rien n'est stocké : tout se calcule depuis `date_pose` / `date_retrait`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

from .. import listes
from .dates import parse_date


def jour_en_cours(date_debut: str | date, a_la_date: str | date | None = None) -> int:
    """J1 le jour de la pose, J2 le lendemain…"""
    debut = parse_date(date_debut)
    reference = parse_date(a_la_date) or date.today()
    return (reference - debut).days + 1


def jours_depuis(date_evenement: str | date, a_la_date: str | date | None = None) -> int:
    """J0 le jour de l'événement, J1 le lendemain…"""
    evenement = parse_date(date_evenement)
    reference = parse_date(a_la_date) or date.today()
    return (reference - evenement).days


@dataclass
class EtatDispositif:
    """Ce qu'on affiche pour un dispositif un jour donné."""

    type: str
    en_place: bool
    jour: int
    texte: str            # « Intubé J3 », « Extubé J2 », « KTA radial G J5 »
    site: str | None = None
    details: dict | None = None
    date_pose: str | None = None
    date_retrait: str | None = None

    @property
    def libelle_type(self) -> str:
        return listes.libelle_dispositif(self.type)


def _details(ligne: dict) -> dict:
    brut = ligne.get("details")
    if not brut:
        return {}
    try:
        return json.loads(brut)
    except (TypeError, ValueError):
        return {}


def _precisions(ligne: dict, details: dict) -> str:
    """Site et champs propres au type, ex. « radiale gauche », « 55 cm »."""
    morceaux = []
    if ligne.get("site"):
        morceaux.append(str(ligne["site"]).lower())
    for cle, valeur in details.items():
        if valeur in (None, "", 0):
            continue
        _libelle, prefixe, unite = listes.CHAMPS_DISPOSITIF.get(cle, (cle, "", ""))
        morceaux.append(" ".join(m for m in (prefixe, str(valeur), unite) if m))
    return ", ".join(morceaux)


def etat(ligne: dict, a_la_date: str | date | None = None) -> EtatDispositif:
    """État d'un dispositif à une date donnée, compteur compris.

    Un dispositif retiré reste affiché : c'est ce qui permet de lire
    « Extubé J2 » ou « KT retiré J4 » sans rien ressaisir.
    """
    config = listes.TYPES_DISPOSITIF.get(ligne["type"], {})
    details = _details(ligne)
    precisions = _precisions(ligne, details)

    if ligne.get("date_retrait"):
        jour = jours_depuis(ligne["date_retrait"], a_la_date)
        base = config.get("apres", ligne["type"])
        texte = f"{base} J{jour}"
        en_place = False
    else:
        jour = jour_en_cours(ligne["date_pose"], a_la_date)
        base = config.get("en_cours", ligne["type"])
        texte = f"{base} J{jour}"
        en_place = True

    if precisions:
        texte = f"{texte} ({precisions})"

    return EtatDispositif(
        type=ligne["type"],
        en_place=en_place,
        jour=jour,
        texte=texte,
        site=ligne.get("site"),
        details=details,
        date_pose=ligne.get("date_pose"),
        date_retrait=ligne.get("date_retrait"),
    )


def pose_le_jour(ligne: dict, a_la_date: str | date | None = None) -> bool:
    """Un dispositif posé aujourd'hui — utile pour signaler la nouveauté."""
    return parse_date(ligne["date_pose"]) == (parse_date(a_la_date) or date.today())


def duree_totale_jours(lignes: list[dict], type_: str, a_la_date: str | date | None = None) -> int:
    """Somme des jours pour un type donné, épisodes multiples compris —
    c'est la durée de ventilation ou d'épuration du socle de recherche
    (SPEC §9.2), calculée, jamais saisie."""
    total = 0
    for ligne in lignes:
        if ligne["type"] != type_:
            continue
        fin = parse_date(ligne.get("date_retrait")) or (parse_date(a_la_date) or date.today())
        debut = parse_date(ligne["date_pose"])
        total += max((fin - debut).days, 0)
    return total


def resume(lignes: list[dict], a_la_date: str | date | None = None, en_place_seulement: bool = True) -> str:
    """Ligne compacte pour la pancarte et l'évolution, ex.
    « Intubé J3 · Sédaté J3 · KT central J5 (jugulaire interne droite) »."""
    etats = [etat(l, a_la_date) for l in lignes]
    if en_place_seulement:
        etats = [e for e in etats if e.en_place]
    ordre = {code: i for i, code in enumerate(listes.ORDRE_DISPOSITIFS)}
    etats.sort(key=lambda e: ordre.get(e.type, 99))
    return " · ".join(e.texte for e in etats)
