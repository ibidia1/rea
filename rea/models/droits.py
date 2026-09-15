"""Qui a le droit de faire quoi (SPEC §2.5).

Jusqu'ici tout le monde saisissait tout : un seul poste, une seule personne à
la fois, et le sélecteur d'ouverture ne servait qu'à signer les écritures. Le
service ayant grandi, les rôles arrivent — mais il faut être exact sur ce
qu'ils font, et sur ce qu'ils ne font pas.

**Ces rôles organisent l'écran. Ils ne protègent rien tant qu'un compte n'a
pas de code d'accès.** N'importe qui peut choisir n'importe quel nom dans la
liste d'ouverture ; poser « infirmier » devant ce nom-là empêche une erreur,
pas une intrusion. La barrière, c'est le code d'accès (`utilisateur.pin`), et
elle ne vaut que pour les comptes qui en ont un. Dire l'inverse serait pire
que ne rien faire : on croirait le dossier protégé.

Ce que ces rôles évitent vraiment, et c'est déjà beaucoup : qu'un infirmier
modifie le prescrit par mégarde en cherchant à le lire, qu'un protocole soit
signé par quelqu'un qui n'en a pas la charge, qu'un compte disparaisse sur un
clic.

La table des droits est dans `referentiels/roles.json`, pas ici : déplacer un
droit d'un rôle à l'autre est une décision de service, pas une modification de
programme.
"""

from __future__ import annotations

from functools import lru_cache

#: Les droits reconnus. Un droit inconnu dans le fichier de rôles est une
#: faute de frappe qui passerait inaperçue : `verifier_referentiel` la
#: signale plutôt que de refuser silencieusement l'accès à tout le monde.
DROITS = (
    "dossier_lire",
    "dossier_ecrire",
    "protocoles",
    "comptes",
    "administrations",
    "constantes",
    "supervision",
    "recherche",
)


@lru_cache(maxsize=1)
def _table() -> dict[str, tuple[str, frozenset[str]]]:
    from .. import referentiels

    table = {}
    for entree in referentiels.charger("roles"):
        code, libelle = entree[0], entree[1]
        droits = frozenset(entree[2]) if len(entree) > 2 else frozenset()
        table[code] = (libelle, droits)
    return table


def roles() -> tuple[str, ...]:
    return tuple(_table())


def libelle(role: str | None) -> str:
    return _table().get(role or "", (role or "—", frozenset()))[0]


def droits_du_role(role: str | None) -> frozenset[str]:
    """Les droits d'un rôle. Un rôle inconnu n'a aucun droit.

    C'est volontairement le sens le plus restrictif : une faute de frappe dans
    un fichier de rôles doit fermer des portes, pas en ouvrir.
    """
    return _table().get(role or "", ("", frozenset()))[1]


def peut(role: str | None, droit: str) -> bool:
    return droit in droits_du_role(role)


def verifier_referentiel() -> list[str]:
    """Les incohérences du fichier de rôles, en clair.

    Appelé par un test : un droit mal orthographié dans le référentiel ne
    lève aucune erreur à l'exécution, il retire seulement l'accès — et
    personne ne fait le rapprochement.
    """
    problemes = []
    for code, (libelle_role, droits) in _table().items():
        if not libelle_role:
            problemes.append(f"Le rôle « {code} » n'a pas de libellé.")
        for droit in sorted(droits - set(DROITS)):
            problemes.append(
                f"Le rôle « {code} » porte un droit inconnu : « {droit} »."
            )
    if not any("comptes" in droits for _l, droits in _table().values()):
        problemes.append(
            "Aucun rôle ne porte le droit « comptes » : plus personne ne "
            "pourrait créer ni supprimer de compte."
        )
    return problemes
