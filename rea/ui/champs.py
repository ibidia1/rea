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
