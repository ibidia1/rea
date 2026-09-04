"""Moteur de gabarit minimal pour les documents imprimés (couche C3).

La feuille de réanimation est dessinée par le service, pas par le programme :
elle vit dans `modeles/*.html` et se remplace sans reprogrammer quoi que ce
soit (feuille de route, règles R2 et R3). Ce module est le strict minimum
nécessaire pour y injecter des valeurs.

Trois constructions, pas une de plus :

    {{ nom }}                          une valeur
    {{ nom.champ }}                    un champ d'une valeur composée
    <sc-for list="{{ liste }}" as="x">…</sc-for>    répété par élément

Tout est échappé par défaut. Un fragment déjà balisé — les vingt-quatre cases
horaires d'une ligne de prescription, par exemple — doit être marqué `Brut`
pour passer tel quel : impossible d'injecter du HTML par mégarde.

Un gabarit dont il reste des trous n'est pas rendu à moitié : `rendre()`
signale les variables inconnues plutôt que de laisser un « {{ nom }} » sur une
feuille imprimée et donnée à l'infirmier.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Brut:
    """Un fragment HTML déjà construit, à insérer sans échappement."""

    html: str


# Les commentaires HTML sont laissés strictement tranquilles : la maquette du
# service documente sa propre syntaxe avec des exemples ({{ … }}, <sc-for>), et
# les traiter comme du contenu ferait échouer le rendu sur son mode d'emploi.
_COMMENTAIRE = re.compile(r"<!--.*?-->", re.S)

_OUVERTURE = re.compile(
    r'<sc-for\s+list="\{\{\s*(?P<liste>[\w.]+)\s*\}\}"\s+as="(?P<var>\w+)"[^>]*>'
)
_FERMETURE = "</sc-for>"
_VARIABLE = re.compile(r"\{\{\s*(?P<nom>[\w.]+)\s*\}\}")


class VariableInconnue(KeyError):
    """Le gabarit demande une valeur que l'appelant n'a pas fournie."""


def _texte(valeur) -> str:
    if isinstance(valeur, Brut):
        return valeur.html
    if valeur is None:
        return ""
    return html.escape(str(valeur))


def _resoudre(nom: str, contexte: dict, strict: bool):
    morceaux = nom.split(".")
    valeur = contexte
    for morceau in morceaux:
        if isinstance(valeur, dict) and morceau in valeur:
            valeur = valeur[morceau]
        elif hasattr(valeur, morceau):
            valeur = getattr(valeur, morceau)
        elif strict:
            raise VariableInconnue(nom)
        else:
            return None
    return valeur


def rendre(gabarit: str, contexte: dict, *, strict: bool = True) -> str:
    """Remplit le gabarit. Les boucles d'abord, les variables ensuite."""
    morceaux = []
    position = 0
    for commentaire in _COMMENTAIRE.finditer(gabarit):
        morceaux.append(_rendre_fragment(gabarit[position:commentaire.start()],
                                         contexte, strict))
        morceaux.append(commentaire.group(0))
        position = commentaire.end()
    morceaux.append(_rendre_fragment(gabarit[position:], contexte, strict))
    return "".join(morceaux)


def _rendre_fragment(gabarit: str, contexte: dict, strict: bool) -> str:

    sortie = _developper_boucles(gabarit, contexte, strict)

    def _variable(correspondance: re.Match) -> str:
        nom = correspondance.group("nom")
        valeur = _resoudre(nom, contexte, strict)
        if valeur is None and strict and nom not in contexte:
            raise VariableInconnue(nom)
        return _texte(valeur)

    return _VARIABLE.sub(_variable, sortie)


def _fin_de_boucle(gabarit: str, depuis: int) -> int:
    """Position du `</sc-for>` qui ferme la boucle ouverte avant `depuis`.

    Les boucles s'imbriquent — les créneaux dans les jours, sur la feuille de
    biologie — et un simple « jusqu'au prochain </sc-for> » refermerait la
    boucle extérieure sur la fermeture de l'intérieure : la moitié du tableau
    disparaîtrait sans erreur visible.
    """
    profondeur = 1
    position = depuis
    while profondeur:
        suivante_ouverture = _OUVERTURE.search(gabarit, position)
        suivante_fermeture = gabarit.find(_FERMETURE, position)
        if suivante_fermeture == -1:
            raise ValueError("<sc-for> non refermé dans le gabarit")
        if suivante_ouverture and suivante_ouverture.start() < suivante_fermeture:
            profondeur += 1
            position = suivante_ouverture.end()
        else:
            profondeur -= 1
            position = suivante_fermeture + len(_FERMETURE)
    return position - len(_FERMETURE)


def _developper_boucles(gabarit: str, contexte: dict, strict: bool) -> str:
    sortie = []
    position = 0
    while True:
        ouverture = _OUVERTURE.search(gabarit, position)
        if not ouverture:
            sortie.append(gabarit[position:])
            return "".join(sortie)
        sortie.append(gabarit[position:ouverture.start()])
        fin_corps = _fin_de_boucle(gabarit, ouverture.end())
        corps = gabarit[ouverture.end():fin_corps]
        liste = _resoudre(ouverture.group("liste"), contexte, strict) or ()
        variable = ouverture.group("var")
        for element in liste:
            sortie.append(rendre(corps, {**contexte, variable: element}, strict=strict))
        position = fin_corps + len(_FERMETURE)


def variables_attendues(gabarit: str) -> set[str]:
    """Les noms que le gabarit réclame de l'appelant.

    Sert à vérifier qu'aucun trou ne reste après un changement de maquette par
    le service. Les variables locales aux boucles (`n`, `n.dose`…) n'en font
    pas partie : c'est la boucle qui les fournit.
    """
    utile = _COMMENTAIRE.sub("", gabarit)
    locales = {m.group("var") for m in _OUVERTURE.finditer(utile)}
    hors_boucles = []
    position = 0
    while True:
        ouverture = _OUVERTURE.search(utile, position)
        if not ouverture:
            hors_boucles.append(utile[position:])
            break
        hors_boucles.append(utile[position:ouverture.start()])
        position = _fin_de_boucle(utile, ouverture.end()) + len(_FERMETURE)
    noms = {m.group("nom") for m in _VARIABLE.finditer("".join(hors_boucles))}
    noms |= {m.group("liste") for m in _OUVERTURE.finditer(utile)}
    return {n for n in noms if n.split(".")[0] not in locales}
