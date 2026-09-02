"""Chargement des protocoles de pré-remplissage (SPEC §4.5).

Règles de sécurité non négociables :
1. Chaque protocole est écrit et signé par le chef de service.
2. Le fichier porte une date de version, affichée sur la pancarte imprimée.
3. Le pré-remplissage est proposé, jamais appliqué.
4. Toute ligne issue d'un protocole reste modifiable et supprimable.

Un protocole dont `valide` n'est pas `true` (ou `signe_par` absent) n'est
**jamais** proposé à l'écran — il reste visible dans le dépôt comme brouillon
de travail, mais `protocoles_valides()` l'exclut.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from . import config


@dataclass
class Protocole:
    code: str
    titre: str
    version: str
    date_version: str
    valide: bool
    signe_par: str | None
    declencheur: dict
    lignes_prescription: list[dict]
    explorations_proposees: list[dict]
    consignes: list[str]
    note: str = ""

    @classmethod
    def depuis_fichier(cls, chemin: Path) -> "Protocole":
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
        return cls(
            code=donnees["code"],
            titre=donnees["titre"],
            version=donnees["version"],
            date_version=donnees.get("date_version", ""),
            valide=bool(donnees.get("valide", False)),
            signe_par=donnees.get("signe_par"),
            declencheur=donnees.get("declencheur", {}),
            lignes_prescription=donnees.get("lignes_prescription", []),
            explorations_proposees=donnees.get("explorations_proposees", []),
            consignes=donnees.get("consignes", []),
            note=donnees.get("note", ""),
        )


@lru_cache(maxsize=1)
def _tous() -> tuple[Protocole, ...]:
    dossier = config.DOSSIER_PROTOCOLES
    if not dossier.exists():
        return ()
    return tuple(
        Protocole.depuis_fichier(chemin) for chemin in sorted(dossier.glob("*.json"))
    )


def tous_les_protocoles() -> tuple[Protocole, ...]:
    return _tous()


def protocoles_valides() -> tuple[Protocole, ...]:
    """Seuls ceux signés par le chef de service — règle de sécurité 1."""
    return tuple(p for p in _tous() if p.valide and p.signe_par)


def protocoles_pour_region_traumatique(region: str) -> tuple[Protocole, ...]:
    return tuple(
        p
        for p in protocoles_valides()
        if p.declencheur.get("type") == "region_traumatique"
        and p.declencheur.get("valeur") == region
    )


def protocoles_pour_motif(code_motif: str) -> tuple[Protocole, ...]:
    return tuple(
        p
        for p in protocoles_valides()
        if p.declencheur.get("type") == "motif" and p.declencheur.get("valeur") == code_motif
    )
