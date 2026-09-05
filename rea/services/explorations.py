"""Écran « Explorations et actes » — partie explorations (SPEC §6).

Les explorations sont enregistrées avec leurs **valeurs chiffrées** (format
long, règle de conception 4) et non comme un simple compte rendu : c'est ce
qui permet la cinétique de l'IP au DTC ou de la FEVG, et l'exploitation en
recherche.
"""

from __future__ import annotations

from .. import listes
from ..db import Base


def enregistrer(
    base: Base,
    *,
    sejour_id: str,
    date_heure: str,
    type_: str,
    valeurs: dict[str, float | str | None] | None = None,
    conclusion: str | None = None,
    operateur: str | None = None,
    utilisateur_id: str | None = None,
) -> str:
    with base.transaction():
        exploration_id = base.inserer(
            "exploration",
            {
                "sejour_id": sejour_id,
                "date_heure": date_heure,
                "type": type_,
                "conclusion": conclusion,
                "operateur": operateur,
            },
            utilisateur_id=utilisateur_id,
        )
        definition = listes.TYPES_EXPLORATION.get(type_, {})
        unites = {cle: unite for cle, _lib, unite, _type in definition.get("valeurs", ())}
        for cle, valeur in (valeurs or {}).items():
            if valeur in (None, ""):
                continue
            est_nombre = isinstance(valeur, (int, float))
            base.inserer(
                "exploration_valeur",
                {
                    "exploration_id": exploration_id,
                    "cle": cle,
                    "valeur_num": float(valeur) if est_nombre else None,
                    "valeur_texte": None if est_nombre else str(valeur),
                    "unite": unites.get(cle, ""),
                },
                utilisateur_id=utilisateur_id,
            )
        return exploration_id


def du_sejour(base: Base, sejour_id: str) -> list[dict]:
    return base.requete(
        "SELECT * FROM exploration WHERE sejour_id = ? AND supprime = 0 "
        "ORDER BY date_heure DESC",
        (sejour_id,),
    )


def valeurs(base: Base, exploration_id: str) -> list[dict]:
    return base.requete(
        "SELECT * FROM exploration_valeur WHERE exploration_id = ? AND supprime = 0",
        (exploration_id,),
    )


def historique_valeur(base: Base, sejour_id: str, type_: str, cle: str) -> list[dict]:
    """Cinétique d'une valeur chiffrée — ex. l'IP droit au DTC (SPEC §6.0.3)."""
    return base.requete(
        """
        SELECT e.date_heure, v.valeur_num
        FROM exploration_valeur v
        JOIN exploration e ON e.id = v.exploration_id
        WHERE e.sejour_id = ? AND e.type = ? AND v.cle = ?
          AND e.supprime = 0 AND v.supprime = 0 AND v.valeur_num IS NOT NULL
        ORDER BY e.date_heure
        """,
        (sejour_id, type_, cle),
    )


def _libelle_valeur(type_: str, cle: str) -> str:
    for c, libelle, _unite, _t in listes.TYPES_EXPLORATION.get(type_, {}).get("valeurs", ()):
        if c == cle:
            return libelle
    return cle


def texte_exploration(base: Base, exploration: dict) -> str:
    """Une exploration en une ligne, ex.
    « DTC (08h) : IP 1.35 D / 1.28 G ; Vm 42 D / 45 G — hypoperfusion droite »."""
    definition = listes.TYPES_EXPLORATION.get(exploration["type"], {})
    libelle = definition.get("libelle", exploration["type"])
    heure = exploration["date_heure"][11:16] if len(exploration["date_heure"]) >= 16 else ""
    morceaux = []
    for v in valeurs(base, exploration["id"]):
        valeur = v["valeur_num"] if v["valeur_num"] is not None else v["valeur_texte"]
        if valeur is None:
            continue
        if isinstance(valeur, float) and valeur == int(valeur):
            valeur = int(valeur)
        unite = f" {v['unite']}" if v["unite"] else ""
        morceaux.append(f"{_libelle_valeur(exploration['type'], v['cle'])} {valeur}{unite}")
    ligne = f"- {libelle}"
    if heure:
        ligne += f" ({heure})"
    if morceaux:
        ligne += " : " + " ; ".join(morceaux)
    if exploration["conclusion"]:
        ligne += f" — {exploration['conclusion']}" if morceaux else f" : {exploration['conclusion']}"
    return ligne


def texte_du_jour(base: Base, sejour_id: str, date_jour: str) -> str:
    """Rubrique « Explorations » de l'évolution du jour (SPEC §8.2) —
    reprise automatique, sans aucune ressaisie."""
    lignes = [
        texte_exploration(base, e)
        for e in reversed(du_sejour(base, sejour_id))
        if e["date_heure"].startswith(date_jour)
    ]
    return "\n".join(lignes)
