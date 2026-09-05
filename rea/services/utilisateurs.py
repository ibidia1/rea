"""Qui utilise le logiciel (SPEC §1.2).

Pas de gestion de droits en v1 : tout le monde saisit tout. Ce qui compte,
c'est que chaque ligne écrite porte le nom de quelqu'un — c'est ce qui rend le
journal d'audit exploitable, et c'est pour ça que le sélecteur est obligatoire
à l'ouverture.

Ce module existe pour tenir la règle R1 : l'écran choisissait l'utilisateur
*et* l'écrivait en base lui-même. Une écriture faite depuis un écran échappe à
tout ce que la couche service garantit — transaction et trace comprises.
"""

from __future__ import annotations

from ..db import Base


def actifs(base: Base) -> list[dict]:
    return base.requete(
        "SELECT * FROM utilisateur WHERE actif = 1 AND supprime = 0 ORDER BY nom"
    )


def creer(base: Base, nom: str, role: str) -> str:
    return base.inserer("utilisateur", {"nom": nom.strip(), "role": role})


def par_nom(base: Base, nom: str) -> dict | None:
    """Retrouve un utilisateur sur son nom, sans tenir compte de la casse.

    Un nom déjà pris n'est pas une erreur : on se reconnecte comme cette
    personne plutôt que d'échouer sur la contrainte d'unicité — à six heures du
    matin, personne n'a envie de comprendre pourquoi son propre nom est refusé.
    """
    cible = nom.strip().lower()
    return next(
        (u for u in actifs(base) if u["nom"].strip().lower() == cible), None
    )
