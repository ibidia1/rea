"""Ce que le surveillant a besoin de savoir, sans avoir à le chercher
(SPEC §5.9).

Trois questions, trois réponses, et c'est tout l'écran :

1. **Qui s'occupe de qui ?** — pour appeler la bonne personne.
2. **Que faut-il commander ?** — la liste des médicaments par patient, à
   présenter à la pharmacie.
3. **Qu'est-ce qui a changé ?** — le point le plus important. Aujourd'hui, le
   surveillant relit chaque pancarte pour repérer les nouveautés de la garde ;
   il en manque, et un antibiotique commencé à 4 h du matin n'est commandé
   qu'à midi. Ce module retourne le problème : les changements viennent à lui,
   en phrases, avec le matricule.

Le journal d'audit contient déjà tout cela, mais sous une forme technique —
« modification de prescription_ligne 8f3a… ». On repart donc des lignes
elles-mêmes : elles portent leur date de création et leur date d'arrêt, ce qui
suffit à raconter ce qui s'est passé, et se lit sans décoder.
"""

from __future__ import annotations

from datetime import date, timedelta

from ..db import Base
from ..domaine import prescription as dom
from ..domaine.dates import format_date_fr, parse_date

#: Voies qui donnent lieu à une commande à la pharmacie. Les soins, la kiné et
#: la surveillance n'en sont pas — les faire figurer sur un bon de commande
#: noierait ce qu'il faut vraiment aller chercher.
VOIES_A_COMMANDER = ("PO", "IV", "PSE", "SC", "AEROSOL", "ENTREES")


def medicaments_par_patient(base: Base, date_jour: str) -> list[dict]:
    """Ce qu'il faut avoir en stock aujourd'hui, patient par patient."""
    from . import prescriptions as prescriptions_service

    resultat = []
    for sejour in _sejours_ouverts(base):
        lignes = [
            ligne
            for ligne in prescriptions_service.lignes_actives_le(
                base, sejour["id"], date_jour
            )
            if ligne["voie"] in VOIES_A_COMMANDER
        ]
        if not lignes:
            continue
        resultat.append({
            "sejour_id": sejour["id"],
            "lit": sejour["lit_admission"],
            "patient": sejour["nom_affichage"],
            "matricule": sejour["matricule"],
            "lignes": [_ligne_a_commander(ligne, date_jour) for ligne in lignes],
        })
    return resultat


def nouveautes(base: Base, *, depuis_jours: int = 2) -> list[dict]:
    """Ce qui a changé dans les prescriptions, en phrases lisibles.

    « Ajout de Tienam 1 g × 3/j pendant 7 jours — M. X, matricule 123456 ».
    Le matricule est là parce que c'est lui qu'on donne à la pharmacie, et
    qu'un nom ne suffit pas quand deux patients s'appellent pareil.

    Les arrêts comptent autant que les ajouts : un antibiotique arrêté est une
    commande à ne pas passer.
    """
    depuis = (date.today() - timedelta(days=depuis_jours)).isoformat()
    evenements = []

    for ligne in base.requete(
        "SELECT l.*, p.nom_affichage, p.matricule, s.lit_admission, "
        "       u.nom AS auteur "
        "FROM prescription_ligne l "
        "JOIN sejour s ON s.id = l.sejour_id "
        "JOIN patient p ON p.id = s.patient_id "
        "LEFT JOIN utilisateur u ON u.id = l.cree_par "
        "WHERE l.supprime = 0 AND s.supprime = 0 AND l.cree_le >= ? "
        "ORDER BY l.cree_le DESC",
        (depuis,),
    ):
        evenements.append(_evenement(ligne, "ajout", ligne["cree_le"]))

    for ligne in base.requete(
        "SELECT l.*, p.nom_affichage, p.matricule, s.lit_admission, "
        "       u.nom AS auteur "
        "FROM prescription_ligne l "
        "JOIN sejour s ON s.id = l.sejour_id "
        "JOIN patient p ON p.id = s.patient_id "
        "LEFT JOIN utilisateur u ON u.id = l.modifie_par "
        "WHERE l.supprime = 0 AND s.supprime = 0 AND l.statut = 'arretee' "
        "AND l.date_arret >= ? ORDER BY l.date_arret DESC",
        (depuis,),
    ):
        evenements.append(
            _evenement(ligne, "arret", ligne["modifie_le"] or ligne["date_arret"])
        )

    return sorted(evenements, key=lambda e: e["quand"] or "", reverse=True)


def _texte_du_traitement(ligne: dict) -> str:
    """« Tienam 1 g x3/j » — le découpage vit dans le domaine, pas ici."""
    return " ".join(
        m for m in (dom.libelle_court(ligne), dom.dose_affichee(ligne)) if m
    )


def _ligne_a_commander(ligne: dict, date_jour: str) -> dict:
    etiquette, produit, dose = dom.parties_ligne(ligne, date_jour)
    return {
        "produit": ligne["produit"],
        "voie": ligne["voie"],
        "detail": " ".join(m for m in (produit, dose) if m),
        "jour": etiquette.texte,
    }


def _evenement(ligne: dict, genre: str, quand: str | None) -> dict:
    verbe = "Ajout de" if genre == "ajout" else "Arrêt de"
    texte = f"{verbe} {_texte_du_traitement(ligne)}"
    duree = _duree_prevue(ligne)
    if genre == "ajout" and duree:
        texte += f" pendant {duree}"
    texte += (
        f" — {ligne['nom_affichage']}, matricule {ligne['matricule']}, "
        f"lit {ligne['lit_admission']}"
    )
    return {
        "genre": genre,
        "texte": texte,
        "quand": quand,
        "quand_lisible": _quand_lisible(quand),
        "auteur": ligne.get("auteur") or "",
        "sejour_id": ligne["sejour_id"],
        "matricule": ligne["matricule"],
    }


def _duree_prevue(ligne: dict) -> str:
    jours = ligne.get("duree_prevue_jours")
    if not jours:
        return ""
    return f"{int(jours)} jour" + ("s" if jours > 1 else "")


def _quand_lisible(quand: str | None) -> str:
    if not quand:
        return ""
    jour = format_date_fr(quand[:10])
    heure = quand[11:16]
    return f"{jour} à {heure}" if heure else jour


def _sejours_ouverts(base: Base) -> list[dict]:
    return base.requete(
        "SELECT s.*, p.nom_affichage, p.matricule FROM sejour s "
        "JOIN patient p ON p.id = s.patient_id "
        "WHERE s.date_sortie IS NULL AND s.supprime = 0 "
        "ORDER BY s.lit_admission"
    )


def sejours_ouverts(base: Base) -> list[dict]:
    """Les patients présents — c'est parmi eux que l'infirmier choisit."""
    return _sejours_ouverts(base)


def parse_jour(valeur) -> date | None:
    return parse_date(valeur)
