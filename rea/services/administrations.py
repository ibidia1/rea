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

STATUTS = {
    DONNE: "Donné",
    NON_DONNE: "Non donné",
}

#: Motifs dont quelqu'un doit s'occuper, par destinataire. Un « non donné »
#: pour rupture de stock n'est pas une case cochée : c'est une commande à
#: passer, et si personne ne la voit, la prise suivante est ratée aussi.
ACTIONS = {
    "pharmacie": "À commander",
    "abord": "Voie ou sonde à poser",
    "medical": "Avis médical à prendre",
}


def libelle_motif(code: str | None) -> str:
    from .. import listes

    if not code:
        return ""
    return listes.libelle(listes.MOTIFS_NON_ADMINISTRATION, code)


def action_du_motif(code: str | None) -> str | None:
    """Qui doit agir : « pharmacie », « abord », « medical », ou rien.

    C'est ce champ qui décide de ce qui remonte au surveillant et au médecin.
    Il vient du référentiel : déplacer un motif d'une action à l'autre est une
    décision de service, pas une modification de programme.
    """
    from .. import listes

    for entree in listes.MOTIFS_NON_ADMINISTRATION:
        if entree[0] == code:
            action = entree[2] if len(entree) > 2 else "aucune"
            return action if action in ACTIONS else None
    return None


def noter(
    base: Base,
    *,
    sejour_id: str,
    ligne_id: str,
    date_jour: str,
    heure_prevue: int,
    statut: str,
    motif_code: str | None = None,
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
    # Lire puis écrire n'est atomique que dans une transaction. Sans elle, deux
    # fils — deux téléphones, ou un seul doigt qui appuie deux fois sur un
    # réseau lent — lisent tous les deux « rien de noté » et insèrent tous les
    # deux : le second heurte l'index unique et la note est perdue. Mesuré sur
    # seize écrivains simultanés (10 septembre) : onze échecs sur trente-six
    # mille écritures, tous de cette forme.
    with base.transaction():
        existante = base.une_ligne(
            "SELECT id, version FROM administration WHERE ligne_id = ? "
            "AND date_jour = ? AND heure_prevue = ? AND supprime = 0",
            (ligne_id, date_jour, heure_prevue),
        )
        valeurs = {
            "statut": statut,
            "motif_code": motif_code or None,
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


def a_traiter(base: Base, date_jour: str) -> list[dict]:
    """Les prises non données qui demandent que quelqu'un fasse quelque chose.

    Un traitement sauté faute de produit ou faute de voie ne se règle pas
    tout seul : sans cette liste, la prise suivante est ratée aussi, et
    l'antibiotique du soir manque comme celui du matin. Le surveillant la lit
    pour commander, le médecin la voit sur le prescrit de son patient.

    Ce qui n'appelle aucune action — patient au bloc, à jeun — n'y figure
    pas : une liste qui contient tout ne se lit plus.
    """
    lignes = base.requete(
        "SELECT a.*, l.produit, l.voie, p.nom_affichage, p.matricule, "
        "       s.lit_admission, u.nom AS soignant "
        "FROM administration a "
        "JOIN prescription_ligne l ON l.id = a.ligne_id "
        "JOIN sejour s ON s.id = a.sejour_id "
        "JOIN patient p ON p.id = s.patient_id "
        "LEFT JOIN utilisateur u ON u.id = a.cree_par "
        "WHERE a.date_jour = ? AND a.statut = ? AND a.supprime = 0 "
        "AND s.supprime = 0 AND l.supprime = 0 "
        "ORDER BY a.heure_prevue",
        (date_jour, NON_DONNE),
    )
    resultat = []
    for ligne in lignes:
        action = action_du_motif(ligne["motif_code"])
        if not action:
            continue
        resultat.append({**ligne, "action": action,
                         "libelle_motif": libelle_motif(ligne["motif_code"])})
    return resultat


def non_donnees_du_sejour(base: Base, sejour_id: str, date_jour: str) -> list[dict]:
    """Ce qui n'a pas été donné à ce patient ce jour-là, motif compris.

    Affiché au médecin sur le prescrit : prescrire à nouveau sans savoir que
    la dose d'hier n'est pas passée, c'est croire à un échec du traitement.
    """
    return [
        {**ligne, "libelle_motif": libelle_motif(ligne["motif_code"]),
         "action": action_du_motif(ligne["motif_code"])}
        for ligne in base.requete(
            "SELECT a.*, l.produit, l.voie, u.nom AS soignant "
            "FROM administration a "
            "JOIN prescription_ligne l ON l.id = a.ligne_id "
            "LEFT JOIN utilisateur u ON u.id = a.cree_par "
            "WHERE a.sejour_id = ? AND a.date_jour = ? AND a.statut = ? "
            "AND a.supprime = 0 AND l.supprime = 0 ORDER BY a.heure_prevue",
            (sejour_id, date_jour, NON_DONNE),
        )
    ]
