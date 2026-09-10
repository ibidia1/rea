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


def site_en_incise(site: str) -> str:
    """« Droit » devient « droit », « Thoracique haute (T4-T6) » ne bouge pas.

    Passer tout le site en minuscules abîmait les abréviations : « T4-T6 »
    s'écrivait « t4-t6 », et un repère anatomique en minuscules ne se lit plus
    comme un repère. Seule la majuscule initiale tombe, et seulement quand le
    reste du mot n'en porte aucune.
    """
    if not site:
        return ""
    if any(c.isupper() for c in site[1:]):
        return site
    return site[0].lower() + site[1:]


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
    # L'identifiant de la ligne dont cet état est tiré : c'est par lui que se
    # retrouvent les réglages de vitesse d'une sédation.
    id: str | None = None
    site: str | None = None
    details: dict | None = None
    date_pose: str | None = None
    date_retrait: str | None = None
    # Rang de l'épisode pour ce type chez ce patient : 1 pour le premier,
    # 2 pour le suivant… C'est ce qui distingue une intubation d'une
    # réintubation (demande du service, 8 septembre).
    rang: int = 1
    motif_retrait: str | None = None

    @property
    def libelle_type(self) -> str:
        config = listes.TYPES_DISPOSITIF.get(self.type, {})
        if self.rang > 1 and config.get("libelle_repete"):
            return config["libelle_repete"]
        return listes.libelle_dispositif(self.type)


def lire_details(ligne: dict) -> dict:
    """Les détails d'un dispositif, stockés en JSON dans une colonne texte.

    Tolérante à dessein : une colonne vide ou abîmée rend un dictionnaire
    vide plutôt que de faire tomber l'écran d'un patient.
    """
    brut = ligne.get("details")
    if not brut:
        return {}
    try:
        return json.loads(brut)
    except (TypeError, ValueError):
        return {}


def _texte_valeur(valeur) -> str:
    """« 4 » plutôt que « 4.0 » : ces valeurs viennent de colonnes REAL, et un
    zéro décimal de plus sur une vitesse de pompe n'apprend rien à personne."""
    if isinstance(valeur, float) and valeur.is_integer():
        return str(int(valeur))
    return str(valeur)


def _precisions(ligne: dict, details: dict) -> str:
    """Site et champs propres au type, ex. « radiale gauche », « 55 cm »."""
    morceaux = []
    if ligne.get("site"):
        morceaux.append(site_en_incise(str(ligne["site"])))
    for cle, valeur in details.items():
        if valeur in (None, "", 0):
            continue
        _libelle, prefixe, unite = listes.CHAMPS_DISPOSITIF.get(cle, (cle, "", ""))
        morceaux.append(" ".join(m for m in (prefixe, _texte_valeur(valeur), unite) if m))
    return ", ".join(morceaux)


def libelle_motif_retrait(type_: str, code: str | None) -> str:
    """Le motif de retrait en toutes lettres, ex. « Extubation accidentelle ».

    Les motifs sont déclarés par type dans `types_dispositif.json` : un
    dispositif qui n'en propose aucun n'en affiche aucun.
    """
    if not code:
        return ""
    motifs = listes.TYPES_DISPOSITIF.get(type_, {}).get("motifs_retrait") or []
    return next((l for c, l in motifs if c == code), code)


def etat(ligne: dict, a_la_date: str | date | None = None, rang: int = 1) -> EtatDispositif:
    """État d'un dispositif à une date donnée, compteur compris.

    Un dispositif retiré reste affiché : c'est ce qui permet de lire
    « Extubé J2 » ou « KT retiré J4 » sans rien ressaisir.

    `rang` est le numéro de l'épisode pour ce type chez ce patient. Au-delà du
    premier, un type peut porter un autre nom : une deuxième intubation est
    une réintubation, et ça ne se lit pas pareil au pied du lit.
    """
    config = listes.TYPES_DISPOSITIF.get(ligne["type"], {})
    details = lire_details(ligne)
    precisions = _precisions(ligne, details)

    if ligne.get("date_retrait"):
        jour = jours_depuis(ligne["date_retrait"], a_la_date)
        base = config.get("apres", ligne["type"])
        texte = f"{base} J{jour}"
        en_place = False
    else:
        jour = jour_en_cours(ligne["date_pose"], a_la_date)
        cle = "en_cours_repete" if rang > 1 and config.get("en_cours_repete") else "en_cours"
        base = config.get(cle, ligne["type"])
        texte = f"{base} J{jour}"
        en_place = True

    if precisions:
        texte = f"{texte} ({precisions})"
    # Une extubation accidentelle ne se lit pas comme une extubation
    # programmée : le motif suit le compteur, sur la même ligne.
    motif = libelle_motif_retrait(ligne["type"], ligne.get("motif_retrait"))
    if motif and not en_place:
        texte = f"{texte} — {motif.lower()}"

    return EtatDispositif(
        type=ligne["type"],
        en_place=en_place,
        jour=jour,
        texte=texte,
        id=ligne.get("id"),
        site=ligne.get("site"),
        details=details,
        date_pose=ligne.get("date_pose"),
        date_retrait=ligne.get("date_retrait"),
        rang=rang,
        motif_retrait=ligne.get("motif_retrait"),
    )


def rangs(lignes: list[dict]) -> list[int]:
    """Numéro d'épisode de chaque ligne, par type — liste parallèle à `lignes`.

    `lignes` arrive du plus récent au plus ancien (ordre de lecture en base) ;
    le rang, lui, se compte du plus ancien au plus récent, sans quoi la
    première intubation serait celle d'aujourd'hui. Rien d'autre n'est exigé
    des lignes que leur type et leur date de pose : ce module se lit aussi
    depuis un test, avec des dictionnaires écrits à la main.
    """
    chronologique = sorted(
        range(len(lignes)),
        key=lambda i: (lignes[i].get("date_pose") or "", lignes[i].get("cree_le") or ""),
    )
    numeros = [1] * len(lignes)
    compteur: dict[str, int] = {}
    for i in chronologique:
        type_ = lignes[i]["type"]
        compteur[type_] = compteur.get(type_, 0) + 1
        numeros[i] = compteur[type_]
    return numeros


def etats(lignes: list[dict], a_la_date: str | date | None = None) -> list[EtatDispositif]:
    """L'état de chaque ligne, son rang d'épisode calculé sur l'ensemble."""
    return [
        etat(ligne, a_la_date, rang)
        for ligne, rang in zip(lignes, rangs(lignes))
    ]


def pose_le_jour(ligne: dict, a_la_date: str | date | None = None) -> bool:
    """Un dispositif posé aujourd'hui — utile pour signaler la nouveauté."""
    return parse_date(ligne["date_pose"]) == (parse_date(a_la_date) or date.today())


# --------------------------------------------------------------------------
# Nommer deux drains posés au même endroit (demande du service, 10 septembre)
# --------------------------------------------------------------------------

def libelles_distincts(etats_en_place: list[EtatDispositif]) -> dict[str, str]:
    """id du dispositif -> le nom sous lequel on le désigne au lit du malade.

    Un patient peut avoir deux redons dans l'abdomen. « Redon (abdomen) »
    pour les deux, c'est un volume noté sur le mauvais, et deux courbes qui
    se mélangent : on les numérote — « Redon (abdomen) 1 », « Redon
    (abdomen) 2 » — dans l'ordre où ils ont été posés, celui dans lequel le
    chirurgien en parle.

    Le numéro n'apparaît **que** s'il y a de quoi confondre : un redon seul
    reste « Redon (abdomen) ». Numéroter systématiquement ferait lire
    « Drain thoracique (droit) 1 » à un patient qui n'en a qu'un, et le 1
    donnerait à chercher le 2.

    Le rang d'épisode ne convient pas ici : il compte les poses successives
    sur tout le séjour, si bien qu'un redon retiré lundi ferait appeler
    « Redon 2 » celui qu'on pose mardi — seul en place, et pourtant numéroté.
    Il sert en revanche à départager deux drains posés **le même jour** : la
    date ne les sépare pas, mais lui suit l'ordre de saisie, qui est celui du
    bloc. Sans ce départage, on retombait sur l'identifiant — un UUID, donc
    un ordre tiré au sort, et le premier redon appelé « 2 ».
    """
    par_place: dict[tuple[str, str], list[EtatDispositif]] = {}
    for etat_ in etats_en_place:
        par_place.setdefault((etat_.type, etat_.site or ""), []).append(etat_)

    libelles: dict[str, str] = {}
    for groupe in par_place.values():
        ordonnes = sorted(
            groupe, key=lambda e: (e.date_pose or "", e.rang, e.id or "")
        )
        for numero, etat_ in enumerate(ordonnes, start=1):
            if etat_.id is None:
                continue
            nom = etat_.libelle_type
            if etat_.site:
                nom += f" ({etat_.site.lower()})"
            if len(ordonnes) > 1:
                nom += f" {numero}"
            libelles[etat_.id] = nom
    return libelles


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
    lus = etats(lignes, a_la_date)
    if en_place_seulement:
        lus = [e for e in lus if e.en_place]
    ordre = {code: i for i, code in enumerate(listes.ORDRE_DISPOSITIFS)}
    lus.sort(key=lambda e: ordre.get(e.type, 99))
    return " · ".join(e.texte for e in lus)
