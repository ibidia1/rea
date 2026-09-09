"""Apyrétique, subfébrile, fébrile (SPEC §5.7).

« Fébrile » n'est pas « a de la température ». En réanimation on distingue
trois états, et la différence décide d'une conduite : on ne cherche pas un
foyer pour un patient à 37,7 °C comme pour un patient à 39. Le logiciel ne
disait rien de tout cela — il rangeait un nombre dans une case (demande du
service, 9 septembre).

Cette distinction sert deux fois : à l'écran, pour lire une température d'un
coup d'œil, et surtout dans l'analyse du **délai d'apyrexie** — « à partir de
combien de jours un patient décroche sous telle molécule ». Sans définition
partagée de « fébrile » et de « apyrétique », cette question n'a pas de
réponse calculable.

Les seuils sont dans `referentiels/temperature.json`, pas ici : ce sont eux
que le service voudra revoir, et ils changent le résultat de l'analyse.
"""

from __future__ import annotations

APYRETIQUE = "apyretique"
SUBFEBRILE = "subfebrile"
FEBRILE = "febrile"


def _reglages(reglages: dict | None = None) -> dict:
    if reglages is not None:
        return reglages
    from .. import referentiels

    return referentiels.charger("temperature")


def categorie(temperature_c: float | None, reglages: dict | None = None) -> str | None:
    """L'état thermique, ou None si la température n'est pas renseignée.

    None veut dire « non mesurée », jamais « apyrétique » : une température
    absente ne rend pas un patient afébrile, et compter l'un pour l'autre
    ferait décrocher, dans l'analyse du délai d'apyrexie, tous les patients
    qu'on a simplement cessé de mesurer.
    """
    if temperature_c is None:
        return None
    r = _reglages(reglages)
    if temperature_c < r["seuil_subfebrile_c"]:
        return APYRETIQUE
    if temperature_c < r["seuil_febrile_c"]:
        return SUBFEBRILE
    return FEBRILE


def libelle(code: str | None, reglages: dict | None = None) -> str:
    if code is None:
        return "non mesurée"
    for c in _reglages(reglages)["categories"]:
        if c["code"] == code:
            return c["libelle"]
    return code


def abrege(code: str | None, reglages: dict | None = None) -> str:
    if code is None:
        return ""
    for c in _reglages(reglages)["categories"]:
        if c["code"] == code:
            return c["abrege"]
    return code


def est_febrile(temperature_c: float | None, reglages: dict | None = None) -> bool:
    """Strictement fébrile — subfébrile ne compte pas.

    C'est le critère d'entrée de l'analyse du délai d'apyrexie : on ne peut
    pas mesurer le temps qu'un patient met à décrocher s'il n'était pas
    fébrile au départ.
    """
    return categorie(temperature_c, reglages) == FEBRILE


def est_apyretique(temperature_c: float | None, reglages: dict | None = None) -> bool:
    """Strictement apyrétique — un patient subfébrile n'a pas décroché."""
    return categorie(temperature_c, reglages) == APYRETIQUE
