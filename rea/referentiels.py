"""Chargement des référentiels depuis des fichiers (feuille de route, règle R2).

« Un référentiel est un fichier, pas du code. » Tant que les listes codées
vivaient dans `listes.py`, ajouter un motif d'admission demandait de modifier
un `.py`, donc de redéployer le logiciel — autant dire que personne ne l'aurait
fait, et que la liste serait restée fausse.

Ici, chaque liste vit dans `referentiels/<nom>.json`, avec une **version**.
La version est affichée dans l'application (SPEC §4.5) : une statistique
produite avec la version 2026-09-03.1 n'est pas comparable à une statistique
produite après un remaniement de la liste, et il faut pouvoir le voir.

Le chargement gèle les listes en tuples : un référentiel est en lecture seule
pendant l'exécution, et une modification accidentelle lève une erreur au lieu
de corrompre silencieusement une liste partagée par tout le programme.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

DOSSIER = Path(
    os.environ.get("REA_REFERENTIELS")
    or Path(__file__).resolve().parent.parent / "referentiels"
)


class ReferentielIntrouvable(FileNotFoundError):
    """Un référentiel attendu n'est pas sur le disque — le programme ne peut
    pas continuer avec une liste vide : il dirait « aucun motif possible »."""


def _geler(valeur):
    """Listes → tuples, récursivement. Les dictionnaires restent des
    dictionnaires (les clés sont des codes, l'ordre du fichier est conservé)."""
    if isinstance(valeur, list):
        return tuple(_geler(v) for v in valeur)
    if isinstance(valeur, dict):
        return {cle: _geler(v) for cle, v in valeur.items()}
    return valeur


@lru_cache(maxsize=None)
def _fichier(nom: str) -> dict:
    chemin = DOSSIER / f"{nom}.json"
    if not chemin.exists():
        raise ReferentielIntrouvable(
            f"Référentiel « {nom} » introuvable dans {DOSSIER}. "
            "Le dossier referentiels/ est livré avec le logiciel ; s'il manque, "
            "l'installation est incomplète."
        )
    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    for cle in ("nom", "version", "valeurs"):
        if cle not in donnees:
            raise ValueError(f"Référentiel « {nom} » : clé « {cle} » manquante.")
    return donnees


def charger(nom: str, sous_cle: str | None = None):
    """Les valeurs d'un référentiel, gelées.

    `sous_cle` sert aux fichiers qui regroupent deux listes indissociables
    (les voies et leur ordre d'affichage, les escarres et leurs grades).
    """
    valeurs = _fichier(nom)["valeurs"]
    if sous_cle is not None:
        if sous_cle not in valeurs:
            raise ValueError(f"Référentiel « {nom} » : pas de section « {sous_cle} ».")
        valeurs = valeurs[sous_cle]
    return _geler(valeurs)


def annexe(nom: str, cle: str, defaut=()):
    """Une donnée qui accompagne un référentiel sans en être une valeur.

    Exemple : quelles provenances appellent un détail écrit. C'est une
    propriété de la liste, elle doit voyager avec le fichier de la liste et
    non rester en dur dans le code.
    """
    valeur = _fichier(nom).get(cle)
    return _geler(valeur) if valeur is not None else defaut


def version(nom: str) -> str:
    return _fichier(nom)["version"]


def noms() -> tuple[str, ...]:
    """Les référentiels présents sur le disque, par ordre alphabétique."""
    if not DOSSIER.exists():
        return ()
    return tuple(sorted(p.stem for p in DOSSIER.glob("*.json")))


def inventaire() -> tuple[dict, ...]:
    """De quoi afficher « quelles listes, dans quelle version » (SPEC §4.5)."""
    lignes = []
    for nom in noms():
        donnees = _fichier(nom)
        valeurs = donnees["valeurs"]
        lignes.append(
            {
                "nom": nom,
                "libelle": donnees.get("libelle", nom),
                "version": donnees["version"],
                "date": donnees.get("date", ""),
                "nb_valeurs": _compter(valeurs),
            }
        )
    return tuple(lignes)


def _compter(valeurs) -> int:
    if isinstance(valeurs, dict):
        return sum(_compter(v) for v in valeurs.values())
    if isinstance(valeurs, (list, tuple)):
        return len(valeurs)
    return 1


def recharger() -> None:
    """Vide le cache : les fichiers viennent d'être modifiés à chaud.

    Les noms exportés par `listes` sont liés au chargement du module ; après un
    rechargement, il faut redémarrer l'application pour que l'écran suive. Cette
    fonction sert aux tests et à l'écran d'administration.
    """
    _fichier.cache_clear()


def rechercher(nom: str, texte: str, limite: int = 25) -> tuple:
    """Recherche libre dans un référentiel de paires (code, libellé).

    Cherche dans le code et dans le libellé, sans tenir compte des accents ni
    de la casse : un utilisateur qui tape « pneumo » ou « J18 » doit tomber sur
    la même ligne.
    """
    import unicodedata

    def _pliage(valeur: str) -> str:
        return "".join(
            c for c in unicodedata.normalize("NFD", valeur.lower())
            if unicodedata.category(c) != "Mn"
        )

    requete = _pliage(texte.strip())
    if not requete:
        return ()
    mots = requete.split()
    resultats = []
    for entree in charger(nom):
        cible = _pliage(" ".join(str(x) for x in entree))
        if all(mot in cible for mot in mots):
            resultats.append(entree)
        if len(resultats) >= limite:
            break
    return tuple(resultats)
