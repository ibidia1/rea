"""Chargement des règles d'aide (feuille de route, bloc 7, règle R4).

Même discipline que les protocoles : un fichier, une version, une source, et
une signature de senior. Une règle non signée reste visible — elle est utile
tout de suite — mais elle est affichée comme telle, pour que personne ne la
prenne pour une position validée du service.
"""

from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path

from .domaine import regles as domaine_regles
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


# --------------------------------------------------------------------------
# Édition (Administration → Règles d'aide)
# --------------------------------------------------------------------------
# Le fichier reste la vérité — ces fonctions ne font que le lire et le
# réécrire pour quelqu'un qui n'a pas de raison d'ouvrir un éditeur de texte.
# Une règle enregistrée ici s'applique tout de suite, comme si elle avait été
# tapée à la main dans le fichier : le badge « non signé » reste affiché tant
# que personne n'a coché la validation, mais il ne bloque rien (feuille de
# route, bloc 7) — c'est la même règle qu'avant l'éditeur.

def noms_fichiers() -> tuple[str, ...]:
    """Les fichiers de règles présents, hors check-list et barèmes de score
    (qui ont une autre forme et ne passent pas par cet éditeur)."""
    if not DOSSIER.exists():
        return ()
    noms = []
    for chemin in sorted(DOSSIER.glob("*.json")):
        contenu = json.loads(chemin.read_text(encoding="utf-8"))
        if "regles" in contenu:
            noms.append(chemin.stem)
    return tuple(noms)


def lire_fichier(nom: str) -> dict:
    """Le contenu brut d'un fichier de règles — pas les objets `Regle`, pour
    pouvoir le modifier et le réécrire tel quel."""
    chemin = DOSSIER / f"{nom}.json"
    if not chemin.exists():
        raise FileNotFoundError(f"Fichier de règles introuvable : {nom}")
    return json.loads(chemin.read_text(encoding="utf-8"))


def enregistrer_fichier(nom: str, contenu: dict) -> None:
    """Réécrit le fichier avec une version incrémentée, et vide le cache pour
    que la prochaine lecture voie le changement sans redémarrer le logiciel."""
    contenu = dict(contenu)
    contenu["version"] = domaine_regles.prochaine_version(contenu.get("version", ""))
    contenu["date"] = date.today().isoformat()
    chemin = DOSSIER / f"{nom}.json"
    chemin.write_text(json.dumps(contenu, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    recharger()


def creer_fichier(nom: str, titre: str) -> dict:
    """Un nouveau fichier de règles, vide, prêt à recevoir des lignes."""
    chemin = DOSSIER / f"{nom}.json"
    if chemin.exists():
        raise FileExistsError(f"Le fichier « {nom} » existe déjà.")
    contenu = {
        "code": nom,
        "titre": titre,
        "version": "",
        "date_version": "",
        "valide": False,
        "signe_par": None,
        "note": "Créé depuis l'éditeur de règles — à faire valider par un senior.",
        "regles": [],
    }
    enregistrer_fichier(nom, contenu)
    return lire_fichier(nom)
