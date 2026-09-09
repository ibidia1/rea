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


def protocoles_pour_regle(code_regle: str) -> tuple[Protocole, ...]:
    """Les protocoles attachés à une règle d'aide.

    Les deux premiers déclencheurs — motif d'admission, région traumatique —
    ne servent qu'à l'admission : ils décrivent le patient qui arrive. Or la
    plupart des protocoles d'un service de réanimation répondent à quelque
    chose qui *survient* : une kaliémie à 2,6 le quatrième jour, une fièvre
    sous cathéter. Ce déclencheur-là attache un protocole au code d'une règle
    d'aide (`regles/*.json`) : quand la règle se déclenche, le protocole est
    proposé, au même endroit et au même moment que le rappel.

    La règle de sécurité 1 ne bouge pas d'un pouce : `protocoles_valides()`
    filtre d'abord, un brouillon n'est jamais proposé.
    """
    return tuple(
        p
        for p in protocoles_valides()
        if p.declencheur.get("type") == "regle"
        and p.declencheur.get("valeur") == code_regle
    )


def protocoles_pour_motif(code_motif: str) -> tuple[Protocole, ...]:
    return tuple(
        p
        for p in protocoles_valides()
        if p.declencheur.get("type") == "motif" and p.declencheur.get("valeur") == code_motif
    )


# --------------------------------------------------------------------------
# Édition (Administration → Protocoles)
# --------------------------------------------------------------------------
# Comme pour les règles d'aide : le fichier reste la vérité, ces fonctions ne
# font que le lire et le réécrire pour quelqu'un qui n'a pas de raison
# d'ouvrir un éditeur de texte. La règle de sécurité 1 ne change pas : tant
# que `valide` n'est pas coché et `signe_par` rempli, le protocole reste un
# brouillon que `protocoles_valides()` ignore.

def codes() -> tuple[str, ...]:
    if not config.DOSSIER_PROTOCOLES.exists():
        return ()
    return tuple(sorted(p.stem for p in config.DOSSIER_PROTOCOLES.glob("*.json")))


def lire_fichier(code: str) -> dict:
    chemin = config.DOSSIER_PROTOCOLES / f"{code}.json"
    if not chemin.exists():
        raise FileNotFoundError(f"Protocole introuvable : {code}")
    return json.loads(chemin.read_text(encoding="utf-8"))


def enregistrer(code: str, contenu: dict) -> None:
    """Réécrit le protocole. La date de version est toujours celle du jour de
    l'enregistrement : c'est elle qui doit apparaître sur toute pancarte
    imprimée à partir de ce protocole."""
    from datetime import date

    from .domaine.regles import prochaine_version

    contenu = dict(contenu)
    contenu["code"] = code
    contenu["version"] = prochaine_version(contenu.get("version", ""))
    contenu["date_version"] = date.today().isoformat()
    config.DOSSIER_PROTOCOLES.mkdir(parents=True, exist_ok=True)
    chemin = config.DOSSIER_PROTOCOLES / f"{code}.json"
    chemin.write_text(json.dumps(contenu, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _tous.cache_clear()


def supprimer(code: str) -> None:
    chemin = config.DOSSIER_PROTOCOLES / f"{code}.json"
    chemin.unlink(missing_ok=True)
    _tous.cache_clear()
