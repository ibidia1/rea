"""Qui s'occupe de qui, sur quelle vacation (SPEC §5.8).

L'infirmier choisit son malade en prenant son poste ; le surveillant lit la
même table à l'envers pour savoir qui appeler. C'est le seul endroit du
logiciel où l'on écrit le nom d'un soignant à côté de celui d'un patient, et
ça n'a qu'un but : qu'à trois heures du matin, personne n'ait à demander qui
s'occupe du lit 7.

Le jour porté par une affectation est celui de la **prise de poste**. La nuit
ouverte le 9 à 19 h se termine le 10 à 7 h : elle reste datée du 9, sinon
l'infirmière de nuit verrait son poste se vider à minuit.
"""

from __future__ import annotations

from datetime import date, datetime

from ..db import Base
from ..domaine import vacations as dom


def affecter(
    base: Base,
    *,
    sejour_id: str,
    soignant_id: str,
    date_jour: str,
    vacation: str,
    utilisateur_id: str | None = None,
) -> str:
    """Confie un patient à un soignant. Deux fois le même couple ne crée
    qu'une affectation : on reprend celle qui existe."""
    if vacation not in dom.codes():
        raise ValueError(f"Vacation inconnue : {vacation}")
    existante = base.une_ligne(
        "SELECT id FROM affectation WHERE sejour_id = ? AND utilisateur_id = ? "
        "AND date_jour = ? AND vacation = ? AND supprime = 0",
        (sejour_id, soignant_id, date_jour, vacation),
    )
    if existante:
        return existante["id"]
    return base.inserer(
        "affectation",
        {"sejour_id": sejour_id, "utilisateur_id": soignant_id,
         "date_jour": date_jour, "vacation": vacation},
        utilisateur_id=utilisateur_id,
    )


def retirer(base: Base, affectation_id: str, *, utilisateur_id: str | None = None) -> None:
    base.supprimer_logiquement("affectation", affectation_id,
                               utilisateur_id=utilisateur_id)


def du_soignant(
    base: Base, soignant_id: str, date_jour: str, vacation: str
) -> list[dict]:
    """Les patients d'un soignant sur sa vacation, avec de quoi les nommer."""
    return base.requete(
        "SELECT a.*, s.lit_admission, p.nom_affichage, p.matricule "
        "FROM affectation a "
        "JOIN sejour s ON s.id = a.sejour_id "
        "JOIN patient p ON p.id = s.patient_id "
        "WHERE a.utilisateur_id = ? AND a.date_jour = ? AND a.vacation = ? "
        "AND a.supprime = 0 AND s.supprime = 0 "
        "ORDER BY s.lit_admission",
        (soignant_id, date_jour, vacation),
    )


def du_jour(base: Base, date_jour: str, vacation: str | None = None) -> list[dict]:
    """Toutes les affectations d'un jour — la vue du surveillant."""
    sql = (
        "SELECT a.*, s.lit_admission, p.nom_affichage, p.matricule, "
        "       u.nom AS soignant, u.telephone "
        "FROM affectation a "
        "JOIN sejour s ON s.id = a.sejour_id "
        "JOIN patient p ON p.id = s.patient_id "
        "JOIN utilisateur u ON u.id = a.utilisateur_id "
        "WHERE a.date_jour = ? AND a.supprime = 0 AND s.supprime = 0 "
    )
    parametres: tuple = (date_jour,)
    if vacation:
        sql += "AND a.vacation = ? "
        parametres += (vacation,)
    return base.requete(sql + "ORDER BY a.vacation, s.lit_admission", parametres)


def du_sejour(base: Base, sejour_id: str, date_jour: str) -> list[dict]:
    """Qui s'est occupé de ce patient aujourd'hui, vacation par vacation."""
    return base.requete(
        "SELECT a.*, u.nom AS soignant, u.telephone FROM affectation a "
        "JOIN utilisateur u ON u.id = a.utilisateur_id "
        "WHERE a.sejour_id = ? AND a.date_jour = ? AND a.supprime = 0",
        (sejour_id, date_jour),
    )


def poste_courant(instant: datetime | None = None) -> tuple[str, str]:
    """La vacation en cours et son jour de prise de poste, en chaînes."""
    vacation, jour = dom.jour_de_vacation(instant)
    return vacation, (jour.isoformat() if isinstance(jour, date) else str(jour))
