"""Ce qui est prélevé, et ce qui ne l'a pas été (SPEC §5.8).

`bilan_demande` dit ce qu'il faut prélever et à quelle heure. Cette table-ci
dit si ça a été fait. Les deux ne se confondent pas, et c'est tout l'objet :
un bilan demandé la veille au soir et jamais prélevé ne laissait aucune trace,
et personne ne s'en apercevait avant que le résultat manque à la visite
(demande du service, 10 septembre).

Les radios et l'ECG passent par le même chemin que la biologie : ils sont dans
le même référentiel d'examens à demander, portent la même heure, et se cochent
de la même façon. Une radio de 8 h oubliée coûte la même visite qu'une NFS
oubliée.

Même forme que `administrations`, et pour la même raison : ce qui n'a pas été
fait doit dire **pourquoi**, dans une liste et non en texte libre.
"""

from __future__ import annotations

from datetime import datetime

from .. import listes
from ..db import Base
from ..domaine import vacations as dom_vacations

FAIT = "fait"
NON_FAIT = "non_fait"

STATUTS = {FAIT: "Prélevé", NON_FAIT: "Non prélevé"}

#: Ce que déclenche un motif, et chez qui. Repris tel quel des motifs de
#: non-administration : un motif qui ne remonte à personne ne sert qu'à
#: fermer une ligne.
ACTIONS = {
    "laboratoire": "à voir avec le laboratoire",
    "abord": "demande une voie d'abord",
    "medical": "demande une décision médicale",
    "aucune": "sans suite particulière",
}


def libelle_motif(code: str | None) -> str:
    return listes.libelle(listes.MOTIFS_NON_PRELEVEMENT, code) if code else ""


def action_du_motif(code: str | None) -> str | None:
    for entree in listes.MOTIFS_NON_PRELEVEMENT:
        if entree[0] == code:
            action = entree[2] if len(entree) > 2 else "aucune"
            return None if action == "aucune" else action
    return None


def _heure(heure_prelevement: str | None) -> int:
    """« 06:00 » → 6. Une heure illisible tombe à 8 h plutôt que de faire
    disparaître l'examen : un bilan qu'on n'affiche pas est un bilan qu'on ne
    prélève pas."""
    try:
        return int(str(heure_prelevement or "").split(":")[0])
    except ValueError:
        return 8


def demandes_du_jour(base: Base, sejour_id: str, date_jour: str) -> list[dict]:
    """Les examens demandés ce jour-là, avec leur heure et leur libellé."""
    journee = base.une_ligne(
        "SELECT id FROM journee WHERE sejour_id = ? AND date_jour = ? AND supprime = 0",
        (sejour_id, date_jour),
    )
    if not journee:
        return []
    return [
        {
            "examen_code": ligne["examen_code"],
            "libelle": listes.libelle(listes.EXAMENS_A_DEMANDER, ligne["examen_code"]),
            "heure": _heure(ligne["heure_prelevement"]),
        }
        for ligne in base.requete(
            "SELECT examen_code, heure_prelevement FROM bilan_demande "
            "WHERE journee_id = ? AND supprime = 0 ORDER BY heure_prelevement, examen_code",
            (journee["id"],),
        )
    ]


def de_la_vacation(
    base: Base, sejour_id: str, date_jour: str, vacation: str
) -> list[dict]:
    """Ce que cette équipe-là doit prélever, dans l'ordre de son poste.

    L'équipe du matin prépare les tubes du matin. Lui montrer les examens de
    la journée entière reviendrait à lui demander de retrouver les siens dans
    une liste dont les deux tiers ne la concernent pas — c'est le même
    raisonnement que pour les prises de traitement.
    """
    heures = dom_vacations.heures(vacation)
    rang = {heure: i for i, heure in enumerate(heures)}
    retenus = [d for d in demandes_du_jour(base, sejour_id, date_jour)
               if d["heure"] in rang]
    return sorted(retenus, key=lambda d: (rang[d["heure"]], d["libelle"]))


def du_jour(base: Base, sejour_id: str, date_jour: str) -> dict[tuple[str, int], dict]:
    """(code d'examen, heure) -> ce qui a été noté."""
    return {
        (ligne["examen_code"], ligne["heure_prevue"]): ligne
        for ligne in base.requete(
            "SELECT p.*, u.nom AS soignant FROM prelevement p "
            "LEFT JOIN utilisateur u ON u.id = p.cree_par "
            "WHERE p.sejour_id = ? AND p.date_jour = ? AND p.supprime = 0",
            (sejour_id, date_jour),
        )
    }


def noter(
    base: Base,
    *,
    sejour_id: str,
    date_jour: str,
    examen_code: str,
    heure_prevue: int,
    statut: str,
    motif_code: str | None = None,
    motif: str = "",
    utilisateur_id: str | None = None,
) -> str:
    if statut not in STATUTS:
        raise ValueError(f"Statut inconnu : {statut}")
    if statut == NON_FAIT and not motif_code:
        raise ValueError("Un examen non prélevé doit dire pourquoi.")
    # Lire puis écrire n'est atomique que dans une transaction. Sans elle, deux
    # fils — deux téléphones, ou un seul doigt qui appuie deux fois sur un
    # réseau lent — lisent tous les deux « rien de noté » et insèrent tous les
    # deux : le second heurte l'index unique et la note est perdue. Mesuré sur
    # seize écrivains simultanés (10 septembre) : onze échecs sur trente-six
    # mille écritures, tous de cette forme.
    with base.transaction():
        existante = base.une_ligne(
            "SELECT id FROM prelevement WHERE sejour_id = ? AND date_jour = ? "
            "AND examen_code = ? AND heure_prevue = ? AND supprime = 0",
            (sejour_id, date_jour, examen_code, heure_prevue),
        )
        valeurs = {
            "statut": statut, "motif_code": motif_code or None,
            "motif": (motif or "").strip() or None,
            "date_heure_reelle": datetime.now().isoformat(timespec="minutes"),
        }
        if existante:
            base.mettre_a_jour("prelevement", existante["id"], valeurs,
                               utilisateur_id=utilisateur_id)
            return existante["id"]
        return base.inserer(
            "prelevement",
            {"sejour_id": sejour_id, "date_jour": date_jour,
             "examen_code": examen_code, "heure_prevue": heure_prevue, **valeurs},
            utilisateur_id=utilisateur_id,
        )


def effacer(
    base: Base, *, sejour_id: str, date_jour: str, examen_code: str,
    heure_prevue: int, utilisateur_id: str | None = None,
) -> None:
    """Décocher : la note disparaît, l'examen redevient « pas encore fait ».

    Corriger doit coûter le même nombre de gestes que noter, sinon on corrige
    sur le papier.
    """
    # Lire puis effacer n'est atomique que dans une transaction : deux doigts
    # sur le même bouton effaceraient sinon deux fois la même ligne.
    with base.transaction():
        ligne = base.une_ligne(
            "SELECT id FROM prelevement WHERE sejour_id = ? AND date_jour = ? "
            "AND examen_code = ? AND heure_prevue = ? AND supprime = 0",
            (sejour_id, date_jour, examen_code, heure_prevue),
        )
        if ligne:
            base.supprimer_logiquement("prelevement", ligne["id"],
                                       utilisateur_id=utilisateur_id)


def non_faits_du_sejour(base: Base, sejour_id: str, date_jour: str) -> list[dict]:
    """Ce qui n'a pas été prélevé ce jour-là — pour le médecin et le
    surveillant, qui apprenaient jusqu'ici l'absence d'un résultat en le
    cherchant."""
    return [
        {**ligne,
         "libelle": listes.libelle(listes.EXAMENS_A_DEMANDER, ligne["examen_code"]),
         "libelle_motif": libelle_motif(ligne["motif_code"])}
        for ligne in base.requete(
            "SELECT p.*, u.nom AS soignant FROM prelevement p "
            "LEFT JOIN utilisateur u ON u.id = p.cree_par "
            "WHERE p.sejour_id = ? AND p.date_jour = ? AND p.statut = ? "
            "AND p.supprime = 0 ORDER BY p.heure_prevue",
            (sejour_id, date_jour, NON_FAIT),
        )
    ]
