"""Chargement des règles d'aide (feuille de route, bloc 7, règle R4).

Même discipline que les protocoles : un fichier, une version, une source, et
une signature de senior. Une règle non signée reste visible — elle est utile
tout de suite — mais elle est affichée comme telle, pour que personne ne la
prenne pour une position validée du service.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .domaine.regles import Regle

DOSSIER = Path(__file__).resolve().parent.parent / "regles"


@lru_cache(maxsize=1)
def _fichiers() -> tuple[dict, ...]:
    if not DOSSIER.exists():
        return ()
    return tuple(
        json.loads(p.read_text(encoding="utf-8")) for p in sorted(DOSSIER.glob("*.json"))
    )


def toutes_les_regles() -> tuple[Regle, ...]:
    return tuple(
        Regle.depuis_dict(r)
        for fichier in _fichiers()
        for r in fichier.get("regles", ())
    )


def checklist() -> dict:
    """Le fichier de la check-list quotidienne (FAST HUG), ou {} s'il manque."""
    for fichier in _fichiers():
        if fichier.get("items"):
            return fichier
    return {}


def bareme(code: str) -> dict:
    """Le barème d'un score (`score_sofa`, `score_igs2`), ou {} s'il manque."""
    for fichier in _fichiers():
        if fichier.get("variables") and fichier.get("code") == code:
            return fichier
    return {}


def baremes() -> tuple[dict, ...]:
    return tuple(f for f in _fichiers() if f.get("variables"))


def inventaire() -> tuple[dict, ...]:
    """Quels jeux de règles, dans quelle version, signés par qui."""
    return tuple(
        {
            "code": f.get("code", ""),
            "titre": f.get("titre", ""),
            "version": f.get("version", ""),
            "valide": bool(f.get("valide")),
            "signe_par": f.get("signe_par"),
            "source": f.get("source", ""),
            "nb": len(f.get("regles", f.get("items", f.get("variables", ())))),
        }
        for f in _fichiers()
    )


def recharger() -> None:
    _fichiers.cache_clear()
