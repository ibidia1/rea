"""Écran 3 — Le prescrit (SPEC §5). Le cœur du logiciel.

Décision de modèle (v1.3, journal SPEC) : une ligne de prescription n'est
JAMAIS dupliquée pour le lendemain. Elle porte `date_debut` / `date_arret` ;
la pancarte d'un jour donné est calculée par intersection avec cette
période. « Préparer la pancarte de demain » ne copie donc aucune ligne — il
crée une `journee` (pour les bilans à demander) et calcule à l'affichage
quelles lignes seront actives, reconduites, échues.
"""

from __future__ import annotations

from ..db import Base
from ..domaine import prescription as dom
from ..domaine.dates import lendemain


# --------------------------------------------------------------------------
# Ajout / modification / arrêt d'une ligne (SPEC §5.1, §5.2)
# --------------------------------------------------------------------------

def ajouter_ligne(
    base: Base,
    *,
    sejour_id: str,
    voie: str,
    produit: str,
    date_debut: str,
    dose: float | None = None,
    unite: str | None = None,
    rythme: str | None = None,
    condition_texte: str | None = None,
    dilution: str | None = None,
    nb_ampoules: float | None = None,
    vitesse: float | None = None,
    volume_dilution: float | None = None,
    volume_24h: float | None = None,
    additifs: str | None = None,
    sous_type: str | None = None,
    duree_prevue_jours: int | None = None,
    horaires_override: str | None = None,
    code_atc: str | None = None,
    protocole_code: str | None = None,
    protocole_version: str | None = None,
    utilisateur_id: str | None = None,
) -> str:
    return base.inserer(
        "prescription_ligne",
        {
            "sejour_id": sejour_id,
            "voie": voie,
            "sous_type": sous_type,
            "produit": produit,
            "dose": dose,
            "unite": unite,
            "rythme": rythme,
            "condition_texte": condition_texte,
            "dilution": dilution,
            "nb_ampoules": nb_ampoules,
            "vitesse": vitesse,
            "volume_dilution": volume_dilution,
            "volume_24h": volume_24h,
            "additifs": additifs,
            "date_debut": date_debut,
            "duree_prevue_jours": duree_prevue_jours,
            # L'heure de prise choisie à la ligne (SPEC §5.3) : ce qui a été
            # prescrit reste ce qui s'imprime, même si les horaires standards
            # du service changent plus tard.
            "horaires_override": horaires_override,
            # Posé même vide : sans lui, la consommation en DDD du bloc 14
            # demanderait de recoder des milliers de lignes (§5).
            "code_atc": code_atc,
            "statut": "active",
            "protocole_code": protocole_code,
            "protocole_version": protocole_version,
        },
        utilisateur_id=utilisateur_id,
    )


def modifier_ligne(
    base: Base, ligne_id: str, valeurs: dict, *, utilisateur_id: str | None = None
) -> None:
    """Toute ligne — y compris issue d'un protocole — reste modifiable sans
    exception (SPEC §4.5, règle de sécurité 4)."""
    base.mettre_a_jour("prescription_ligne", ligne_id, valeurs, utilisateur_id=utilisateur_id)


def arreter_ligne(
    base: Base,
    ligne_id: str,
    *,
    date_arret: str,
    motif_arret: str | None = None,
    utilisateur_id: str | None = None,
) -> None:
    """La ligne reste visible, barrée à l'affichage. Jamais supprimée
    (SPEC §5.1)."""
    base.mettre_a_jour(
        "prescription_ligne",
        ligne_id,
        {"statut": "arretee", "date_arret": date_arret, "motif_arret": motif_arret},
        utilisateur_id=utilisateur_id,
        action="arret",
    )


def horaires_ligne(
    base: Base, ligne_id: str, horaires: str, *, utilisateur_id: str | None = None
) -> None:
    """Horaires modifiables ligne par ligne (SPEC §5.3)."""
    base.mettre_a_jour(
        "prescription_ligne",
        ligne_id,
        {"horaires_override": horaires},
        utilisateur_id=utilisateur_id,
    )


# --------------------------------------------------------------------------
# Lecture de la pancarte à une date donnée
# --------------------------------------------------------------------------

def toutes_les_lignes(base: Base, sejour_id: str) -> list[dict]:
    return base.requete(
        "SELECT * FROM prescription_ligne WHERE sejour_id = ? AND supprime = 0 "
        "ORDER BY voie, cree_le",
        (sejour_id,),
    )


def lignes_actives_le(base: Base, sejour_id: str, a_la_date: str) -> list[dict]:
    """Lignes en vigueur ce jour-là, groupées par voie à l'affichage (SPEC
    §5.2) — l'ordre est laissé à l'appelant (UI)."""
    return [
        ligne
        for ligne in toutes_les_lignes(base, sejour_id)
        if dom.ligne_active_le(ligne, a_la_date)
    ]


def lignes_par_voie(lignes: list[dict]) -> dict[str, list[dict]]:
    from .. import listes

    groupes: dict[str, list[dict]] = {code: [] for code in listes.ORDRE_VOIES}
    for ligne in lignes:
        groupes.setdefault(ligne["voie"], []).append(ligne)
    return groupes


def pancarte_du_jour(base: Base, sejour_id: str, date_jour: str) -> dict:
    """Tout ce qu'il faut pour afficher/imprimer la pancarte d'un jour :
    lignes actives par voie, étiquettes J{n}, bilan hydrique, bilans
    demandés, allergies en tête."""
    lignes = lignes_actives_le(base, sejour_id, date_jour)
    bilan = dom.volume_entrees_24h(lignes)
    journee = base.une_ligne(
        "SELECT * FROM journee WHERE sejour_id = ? AND date_jour = ? AND supprime = 0",
        (sejour_id, date_jour),
    )
    bilans_demandes = []
    if journee:
        bilans_demandes = base.requete(
            "SELECT * FROM bilan_demande WHERE journee_id = ? AND supprime = 0 "
            "ORDER BY examen_code",
            (journee["id"],),
        )
    return {
        "date_jour": date_jour,
        "lignes": lignes,
        "lignes_par_voie": lignes_par_voie(lignes),
        "bilan_entrees": bilan,
        "journee": journee,
        "bilans_demandes": bilans_demandes,
    }


# --------------------------------------------------------------------------
# Bilans à demander pour le lendemain (SPEC §5.2 bis)
# --------------------------------------------------------------------------

def obtenir_ou_creer_journee(
    base: Base, sejour_id: str, date_jour: str, *, utilisateur_id: str | None = None
) -> dict:
    existante = base.une_ligne(
        "SELECT * FROM journee WHERE sejour_id = ? AND date_jour = ? AND supprime = 0",
        (sejour_id, date_jour),
    )
    if existante:
        return existante
    id_ = base.inserer(
        "journee", {"sejour_id": sejour_id, "date_jour": date_jour}, utilisateur_id=utilisateur_id
    )
    return base.une_ligne("SELECT * FROM journee WHERE id = ?", (id_,))


def definir_bilans_demandes(
    base: Base,
    sejour_id: str,
    date_jour: str,
    examens: list[tuple[str, str]],
    *,
    utilisateur_id: str | None = None,
) -> None:
    """`examens` : liste de (code_examen, heure_prelevement)."""
    with base.transaction():
        journee = obtenir_ou_creer_journee(base, sejour_id, date_jour, utilisateur_id=utilisateur_id)
        base.executer(
            "UPDATE bilan_demande SET supprime = 1 WHERE journee_id = ?", (journee["id"],)
        )
        for code, heure in examens:
            deja = base.une_ligne(
                "SELECT id FROM bilan_demande WHERE journee_id = ? AND examen_code = ?",
                (journee["id"], code),
            )
            if deja:
                base.mettre_a_jour(
                    "bilan_demande",
                    deja["id"],
                    {"supprime": 0, "heure_prelevement": heure},
                    utilisateur_id=utilisateur_id,
                )
            else:
                base.inserer(
                    "bilan_demande",
                    {"journee_id": journee["id"], "examen_code": code, "heure_prelevement": heure},
                    utilisateur_id=utilisateur_id,
                )


# --------------------------------------------------------------------------
# « Préparer la pancarte de demain » (SPEC §5.5) — la fonction la plus
# importante du logiciel.
# --------------------------------------------------------------------------

def etat_journee(base: Base, sejour_id: str, date_jour: str) -> dict | None:
    """L'état de préparation/validation d'une journée, sans recalculer toute
    la pancarte — sert à décider si un bouton d'impression doit être actif."""
    return base.une_ligne(
        "SELECT * FROM journee WHERE sejour_id = ? AND date_jour = ? AND supprime = 0",
        (sejour_id, date_jour),
    )


def preparer_pancarte_de_demain(
    base: Base, sejour_id: str, *, aujourdhui: str | None = None, utilisateur_id: str | None = None
) -> dict:
    """Ne duplique rien : crée simplement la `journee` du lendemain, prête à
    recevoir les bilans à demander. Les lignes actives, les compteurs
    avancés et les échéances signalées se calculent à l'affichage
    (`pancarte_du_jour`) — c'est ce qui garantit qu'il n'existe jamais deux
    versions divergentes d'une même ligne (règle de conception 5)."""
    demain = str(lendemain(aujourdhui))
    journee = obtenir_ou_creer_journee(base, sejour_id, demain, utilisateur_id=utilisateur_id)
    base.mettre_a_jour(
        "journee",
        journee["id"],
        {"preparee_le": base.__class__.__module__ and _maintenant()},
        utilisateur_id=utilisateur_id,
        action="preparation_pancarte",
    )
    return pancarte_du_jour(base, sejour_id, demain)


def valider_pancarte_de_demain(
    base: Base, sejour_id: str, *, aujourdhui: str | None = None, utilisateur_id: str | None = None
) -> dict:
    """Une relecture avant impression, distincte de la préparation.

    Préparer ne fait que reconduire les lignes actives — un geste mécanique.
    Valider dit que quelqu'un a relu le résultat avant que la feuille ne soit
    imprimable : sur demande du service, l'impression de la pancarte du
    lendemain reste bloquée tant que cette étape n'a pas eu lieu.
    """
    demain = str(lendemain(aujourdhui))
    journee = base.une_ligne(
        "SELECT * FROM journee WHERE sejour_id = ? AND date_jour = ? AND supprime = 0",
        (sejour_id, demain),
    )
    if journee is None:
        raise ValueError("La pancarte du lendemain n'a pas encore été préparée.")
    base.mettre_a_jour(
        "journee", journee["id"], {"validee_le": _maintenant(), "validee_par": utilisateur_id},
        utilisateur_id=utilisateur_id, action="validation_pancarte",
    )
    return pancarte_du_jour(base, sejour_id, demain)


def _maintenant() -> str:
    from ..db import maintenant

    return maintenant()


def lignes_echues(base: Base, sejour_id: str, a_la_date: str) -> list[dict]:
    """Lignes actives dont la durée prévue est dépassée — à signaler
    visuellement, jamais arrêtées automatiquement (SPEC §5.5)."""
    return [
        ligne
        for ligne in lignes_actives_le(base, sejour_id, a_la_date)
        if dom.etiquette_jour(ligne, a_la_date).echue
    ]
