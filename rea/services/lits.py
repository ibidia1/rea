"""Écran 1 — le tableau des lits (SPEC §4.1, pptx slide 4)."""

from __future__ import annotations

from .. import config
from ..db import Base
from ..domaine.dates import jour_hospitalisation


def etat_des_lits(base: Base) -> list[dict]:
    """Un dict par lit, 1 à NB_LITS : occupé (avec séjour + patient) ou libre."""
    sejours_ouverts = base.requete(
        """
        SELECT s.*, p.nom_affichage, p.date_naissance, p.matricule
        FROM sejour s
        JOIN patient p ON p.id = s.patient_id
        WHERE s.date_sortie IS NULL AND s.supprime = 0
        """
    )
    par_lit = {s["lit_admission"]: s for s in sejours_ouverts}

    resultat = []
    for lit in range(1, config.NB_LITS + 1):
        sejour = par_lit.get(lit)
        if sejour is None:
            resultat.append(
                {"lit": lit, "chambre": config.chambre_du_lit(lit), "occupe": False}
            )
            continue
        resultat.append(
            {
                "lit": lit,
                "chambre": config.chambre_du_lit(lit),
                "occupe": True,
                "sejour_id": sejour["id"],
                "patient_id": sejour["patient_id"],
                "nom_affichage": sejour["nom_affichage"],
                "jour_hospitalisation": jour_hospitalisation(sejour["date_admission"]),
                "traumatique": bool(sejour["traumatique"]) if sejour["traumatique"] is not None else None,
            }
        )
    return resultat


def lits_libres(base: Base) -> list[int]:
    return [l["lit"] for l in etat_des_lits(base) if not l["occupe"]]


def mouvements_du_jour(base: Base, date_jour: str) -> dict[str, int]:
    """Admissions et sorties d'une journée — les deux chiffres du bandeau.

    Ici, et pas dans l'écran : une requête écrite dans une vue échappe aux
    tests, se recopie au prochain écran qui en a besoin, et personne ne sait
    plus où elle vit (§2.4, invariant 3).
    """
    return {
        "admissions": base.une_ligne(
            "SELECT COUNT(*) AS n FROM sejour "
            "WHERE date_admission LIKE ? AND supprime = 0",
            (f"{date_jour}%",),
        )["n"],
        "sorties": base.une_ligne(
            "SELECT COUNT(*) AS n FROM sejour "
            "WHERE date_sortie LIKE ? AND supprime = 0",
            (f"{date_jour}%",),
        )["n"],
    }
