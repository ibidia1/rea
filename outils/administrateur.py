"""Reprendre la main sur les comptes, depuis le PC serveur (SPEC §2.5).

Il manquait une porte de secours, et le service s'en est aperçu en testant
l'application (10 septembre). Les comptes se gèrent dans *Administration →
Comptes*, mais cet écran demande le droit `comptes`, que seul un
administrateur possède. Trois situations enferment donc dehors :

* la base porte des comptes mais **aucun administrateur** — l'écran de
  première ouverture ne s'affiche plus, et personne ne peut en créer ;
* le seul compte administrateur a été **désactivé** ;
* son **code d'accès est perdu**.

Sans cet outil, le seul recours serait d'ouvrir la base SQLite à la main.

**Pourquoi c'est un programme à part et non un bouton dans l'application.**
Un bouton « devenir administrateur » serait atteignable depuis n'importe quel
téléphone du service, et rendrait inutile tout le reste. Ici il faut un accès
aux fichiers du PC serveur — c'est-à-dire l'accès qui permettrait de toute
façon de modifier la base directement. La barrière reste au bon endroit : la
session Windows du poste serveur.

Chaque geste passe par les services habituels, donc **le journal d'audit
l'enregistre** comme n'importe quelle autre modification.

Usage (dans le dossier de l'application) :

    python outils/administrateur.py --lister
    python outils/administrateur.py --promouvoir "Dr Karaa"
    python outils/administrateur.py --creer "Dr Karaa"
    python outils/administrateur.py --code "Dr Karaa"
    python outils/administrateur.py --reactiver "Dr Karaa"
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rea import config                                    # noqa: E402
from rea.db import Base                                   # noqa: E402
from rea.services import utilisateurs                     # noqa: E402


def _lister(base: Base) -> None:
    comptes = utilisateurs.tous(base)
    if not comptes:
        print("Aucun compte : ouvrez l'application, elle proposera de créer "
              "le premier administrateur.")
        return
    largeur = max(len(c["nom"]) for c in comptes)
    for c in comptes:
        etat = "actif" if c["actif"] else "désactivé"
        code = "code posé" if c["pin"] else "SANS CODE"
        print(f"  {c['nom']:<{largeur}}  {c['role']:<12} {etat:<10} {code}")
    if not any(c["role"] == "admin" and c["actif"] for c in comptes):
        print("\n  Aucun administrateur actif : --promouvoir ou --creer.")


def _compte(base: Base, nom: str) -> dict:
    """Cherche parmi **tous** les comptes, désactivés compris.

    `utilisateurs.par_nom` ne regarde que les comptes actifs — ce qui est
    juste pour l'écran d'ouverture, et faux ici : le compte qu'on vient
    réactiver est précisément celui qui ne l'est plus.
    """
    cible = (nom or "").strip().lower()
    compte = next(
        (c for c in utilisateurs.tous(base) if c["nom"].strip().lower() == cible),
        None,
    )
    if compte is None:
        raise SystemExit(
            f"Aucun compte « {nom} ». --lister donne les noms exacts."
        )
    return compte


def _demander_code() -> str | None:
    """Le code se tape sans s'afficher, et jamais en argument de commande.

    Un code passé sur la ligne de commande reste dans l'historique du terminal
    et dans la liste des processus — c'est-à-dire lisible par quelqu'un qui
    n'aurait jamais dû le voir.
    """
    code = getpass.getpass("Nouveau code d'accès (vide = aucun) : ")
    if not code:
        return None
    refus = utilisateurs.code_acceptable(code)
    if refus:
        raise SystemExit(refus)
    if code != getpass.getpass("Confirmer : "):
        raise SystemExit("Les deux saisies diffèrent : rien n'a été changé.")
    return code


def principal() -> None:
    analyseur = argparse.ArgumentParser(
        description="Reprendre la main sur les comptes, depuis le PC serveur.",
    )
    analyseur.add_argument("--lister", action="store_true",
                           help="les comptes, leur rôle et leur état")
    analyseur.add_argument("--promouvoir", metavar="NOM",
                           help="passe ce compte en administrateur")
    analyseur.add_argument("--creer", metavar="NOM",
                           help="crée un compte administrateur")
    analyseur.add_argument("--code", metavar="NOM",
                           help="pose ou remplace le code d'accès d'un compte")
    analyseur.add_argument("--reactiver", metavar="NOM",
                           help="réactive un compte désactivé")
    arguments = analyseur.parse_args()

    if not any(vars(arguments).values()):
        analyseur.print_help()
        return

    print(f"Base : {config.DOSSIER_DONNEES}\n")
    base = Base()
    try:
        if arguments.lister:
            _lister(base)

        if arguments.reactiver:
            compte = _compte(base, arguments.reactiver)
            utilisateurs.reactiver(base, compte["id"])
            print(f"« {compte['nom']} » est réactivé.")

        if arguments.promouvoir:
            compte = _compte(base, arguments.promouvoir)
            utilisateurs.modifier_role(base, compte["id"], "admin")
            print(f"« {compte['nom']} » est désormais administrateur.")

        if arguments.creer:
            code = _demander_code()
            utilisateurs.creer(base, arguments.creer, "admin", code=code)
            print(f"Compte administrateur « {arguments.creer} » créé.")
            if code is None:
                print("  Sans code : à poser avant d'ouvrir l'accès Wi-Fi.")

        if arguments.code:
            compte = _compte(base, arguments.code)
            utilisateurs.definir_code(base, compte["id"], _demander_code())
            print(f"Code de « {compte['nom']} » enregistré.")
    finally:
        base.fermer()


if __name__ == "__main__":
    principal()
