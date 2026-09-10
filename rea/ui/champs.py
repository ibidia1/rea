"""Petites lectures de champs de saisie, partagées par plusieurs écrans.

Rien de médical ici : seulement « ce que l'utilisateur a tapé » traduit
en valeur exploitable, avec la distinction vide / zéro que le reste du
logiciel tient partout (règle de conception 6).
"""

from __future__ import annotations


def nombre_saisi(texte: str | None) -> float | None:
    """Lit un nombre tapé à la main. La virgule décimale est acceptée : au lit
    du malade on tape « 9,2 », pas « 9.2 »."""
    if not texte or not texte.strip():
        return None
    try:
        return float(texte.strip().replace(",", ".").replace(" ", ""))
    except ValueError:
        return None


def format_valeur(valeur: float | None) -> str:
    if valeur is None:
        return "—"
    return str(int(valeur)) if float(valeur) == int(valeur) else f"{valeur:g}"


# --------------------------------------------------------------------------
# Survivre à un référentiel qui change (R2)
# --------------------------------------------------------------------------
# Les référentiels sont des données : on y ajoute une entrée, on en retire
# une, on renomme un code. Une valeur enregistrée il y a six mois peut donc ne
# plus exister dans la liste d'aujourd'hui — et Streamlit refuse une valeur
# par défaut absente des options, en levant une exception qui emporte **tout
# l'écran**, pas seulement le champ.
#
# C'est arrivé pour de vrai : un bilan enregistré sous le code `gaz_du_sang`,
# code disparu depuis du référentiel des examens, rendait l'écran Prescrit
# entièrement inaccessible pour ce patient. Le dossier était intact, mais on
# ne pouvait plus prescrire.

def index_ou_zero(options: list, valeur, defaut: int = 0) -> int:
    """La position d'une valeur dans les options, ou `defaut` si elle n'y est
    plus. Ne lève jamais."""
    try:
        return list(options).index(valeur)
    except ValueError:
        return defaut


def valeurs_connues(options, valeurs) -> list:
    """Ne garde que ce qui existe encore dans les options.

    Rend une liste, dans l'ordre des options — c'est celui que l'écran
    affiche, et une sélection qui se réordonne toute seule inquiète.
    """
    presentes = set(valeurs or ())
    return [o for o in options if o in presentes]


def valeurs_oubliees(options, valeurs) -> list:
    """Ce qui a été enregistré autrefois et n'existe plus.

    À afficher, jamais à taire : une case qui se décoche toute seule entre
    deux ouvertures est pire qu'un message qui explique pourquoi.
    """
    connues = set(options)
    return [v for v in (valeurs or ()) if v not in connues]
