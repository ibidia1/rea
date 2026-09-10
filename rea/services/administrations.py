"""Les prises données, cochées à leur heure (SPEC §5.8).

Une case vide et une prise refusée ne veulent pas dire la même chose, et c'est
toute la raison d'être de cette table. Ne rien écrire signifie « pas encore » ;
écrire `non_donne` signifie « quelqu'un a décidé de ne pas la donner, à telle
heure, et voici pourquoi ». Si l'on se contentait de cocher les prises
données, un traitement volontairement sauté serait indistinguable d'un
traitement oublié — et c'est précisément ce qu'on cherche à retrouver quand on
relit une nuit qui s'est mal passée.

L'heure prévue est celle de la pancarte, pas celle du clic. Elle identifie la
prise et ne bouge pas si l'infirmière coche à 8 h 20 ; le moment du clic est
gardé à côté.
"""

from __future__ import annotations

from datetime import datetime

from ..db import Base

DONNE = "donne"
NON_DONNE = "non_donne"
REFUSE = "refuse"

STATUTS = {
    DONNE: "Donné",
    NON_DONNE: "Non donné",
    REFUSE: "Refusé par le patient",
}


def noter(
    base: Base,
    *,
    sejour_id: str,
    ligne_id: str,
    date_jour: str,
    heure_prevue: int,
    statut: str,
    motif: str | None = None,
    utilisateur_id: str | None = None,
) -> str:
    """Note une prise. Repasser sur la même prise corrige la précédente.

    Une correction n'est pas une seconde administration : l'index unique
    l'interdit, et c'est voulu — deux lignes pour la même prise se
    compteraient deux fois dans toute relecture.
    """
    if statut not in STATUTS:
        raise ValueError(f"Statut inconnu : {statut}")
    existante = base.une_ligne(
        "SELECT id, version FROM administration WHERE ligne_id = ? "
        "AND date_jour = ? AND heure_prevue = ? AND supprime = 0",
        (ligne_id, date_jour, heure_prevue),
    )
    valeurs = {
        "statut": statut,
        "motif": (motif or "").strip() or None,
        "date_heure_reelle": datetime.now().isoformat(timespec="minutes"),
    }
    if existante:
        base.mettre_a_jour("administration", existante["id"], valeurs,
                           utilisateur_id=utilisateur_id)
        return existante["id"]
    return base.inserer(
        "administration",
        {"sejour_id": sejour_id, "ligne_id": ligne_id, "date_jour": date_jour,
         "heure_prevue": heure_prevue, **valeurs},
        utilisateur_id=utilisateur_id,
    )


def effacer(
    base: Base, *, ligne_id: str, date_jour: str, heure_prevue: int,
    utilisateur_id: str | None = None,
) -> None:
    """Décocher : la prise redevient « pas encore ».

    Nécessaire parce qu'on coche parfois la mauvaise ligne, et qu'un logiciel
    qui ne sait pas revenir en arrière se fait contourner sur le papier.
    """
    existante = base.une_ligne(
        "SELECT id FROM administration WHERE ligne_id = ? AND date_jour = ? "
        "AND heure_prevue = ? AND supprime = 0",
        (ligne_id, date_jour, heure_prevue),
    )
    if existante:
        base.supprimer_logiquement("administration", existante["id"],
                                   utilisateur_id=utilisateur_id)


def du_jour(base: Base, sejour_id: str, date_jour: str) -> dict[tuple[str, int], dict]:
    """(ligne_id, heure) -> l'administration notée, pour cocher l'écran."""
    return {
        (a["ligne_id"], a["heure_prevue"]): a
        for a in base.requete(
            "SELECT a.*, u.nom AS soignant FROM administration a "
            "LEFT JOIN utilisateur u ON u.id = a.cree_par "
            "WHERE a.sejour_id = ? AND a.date_jour = ? AND a.supprime = 0",
            (sejour_id, date_jour),
        )
    }


def manquantes(
    base: Base, sejour_id: str, date_jour: str, prises: list[tuple[int, dict]]
) -> list[tuple[int, dict]]:
    """Les prises du poste que personne n'a encore notées.

    C'est ce qu'on regarde en fin de vacation avant de passer la main.
    """
    notees = du_jour(base, sejour_id, date_jour)
    return [
        (heure, ligne) for heure, ligne in prises
        if (ligne["id"], heure) not in notees
    ]
