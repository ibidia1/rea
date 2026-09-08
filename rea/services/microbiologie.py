"""Microbiologie et consommation d'antibiotiques (bloc 14)."""

from __future__ import annotations

from .. import listes
from ..db import Base
from ..domaine.dates import parse_date

# Ordre d'écriture d'un antibiogramme : sensible, intermédiaire, résistant.
# C'est l'ordre dans lequel on le lit à la visite — ce à quoi le germe répond
# d'abord, ce qui ne marchera pas ensuite.
CATEGORIES_ANTIBIOGRAMME = (("S", "sensibles"), ("I", "intermediaires"), ("R", "resistants"))


def texte_antibiogramme(
    sensibles: list[str] | None = None,
    intermediaires: list[str] | None = None,
    resistants: list[str] | None = None,
) -> str | None:
    """Compose l'antibiogramme à partir des molécules cochées, S / I / R.

    Le champ était libre jusqu'ici (demande du service, 8 septembre) : chacun
    écrivait « Pipé-tazo », « pip/tazo » ou « TZP », et rien ne se comptait
    d'un séjour à l'autre. Les molécules viennent maintenant d'une liste
    fermée (`referentiels/antibiotiques_antibiogramme.json`) ; ce texte n'est
    que leur mise en forme, lisible telle quelle dans le dossier.
    """
    molecules = listes.ANTIBIOTIQUES_ANTIBIOGRAMME
    parties = []
    for lettre, cles in zip(
        [c for c, _n in CATEGORIES_ANTIBIOGRAMME],
        (sensibles or [], intermediaires or [], resistants or []),
    ):
        if cles:
            noms = ", ".join(listes.libelle(molecules, c, c) for c in cles)
            parties.append(f"{lettre} : {noms}")
    return " · ".join(parties) or None


def enregistrer(
    base: Base,
    *,
    sejour_id: str,
    date_prelevement: str,
    type_prelevement: str,
    resultat: str = "en_cours",
    germe: str | None = None,
    antibiogramme: str | None = None,
    utilisateur_id: str | None = None,
) -> str:
    return base.inserer(
        "microbiologie",
        {
            "sejour_id": sejour_id,
            "date_prelevement": date_prelevement,
            "type_prelevement": type_prelevement,
            "resultat": resultat,
            "germe": germe,
            "antibiogramme": antibiogramme,
        },
        utilisateur_id=utilisateur_id,
    )


def completer(base: Base, id_ligne: str, valeurs: dict, *, utilisateur_id=None) -> None:
    base.mettre_a_jour("microbiologie", id_ligne, valeurs, utilisateur_id=utilisateur_id)


def du_sejour(base: Base, sejour_id: str) -> list[dict]:
    return base.requete(
        "SELECT * FROM microbiologie WHERE sejour_id = ? AND supprime = 0 "
        "ORDER BY date_prelevement DESC",
        (sejour_id,),
    )


def en_attente(base: Base, sejour_id: str) -> list[dict]:
    """Les prélèvements dont le résultat n'est pas revenu — ceux qu'on oublie."""
    return [l for l in du_sejour(base, sejour_id) if l["resultat"] == "en_cours"]


def germes_du_sejour(base: Base, sejour_id: str) -> list[str]:
    return sorted(
        {l["germe"] for l in du_sejour(base, sejour_id)
         if l["resultat"] == "positif" and l["germe"]}
    )


def declarer_infection_nosocomiale(
    base: Base,
    *,
    sejour_id: str,
    type_: str,
    date_diagnostic: str,
    germe: str | None = None,
    commentaire: str | None = None,
    utilisateur_id: str | None = None,
) -> str:
    return base.inserer(
        "infection_nosocomiale",
        {
            "sejour_id": sejour_id,
            "type": type_,
            "date_diagnostic": date_diagnostic,
            "germe": germe,
            "commentaire": commentaire,
        },
        utilisateur_id=utilisateur_id,
    )


def infections_du_sejour(base: Base, sejour_id: str) -> list[dict]:
    return base.requete(
        "SELECT * FROM infection_nosocomiale WHERE sejour_id = ? AND supprime = 0 "
        "ORDER BY date_diagnostic",
        (sejour_id,),
    )


def acquise_en_reanimation(sejour: dict, infection: dict, delai_jours: int = 2) -> bool:
    """Une infection présente à l'admission n'est pas nosocomiale.

    Le délai conventionnel est de 48 h : avant, l'infection est réputée
    importée. Sans cette distinction, le service se compte des infections
    qu'il n'a pas provoquées — et l'indicateur devient inexploitable.
    """
    admission = parse_date(sejour.get("date_admission"))
    diagnostic = parse_date(infection.get("date_diagnostic"))
    if not admission or not diagnostic:
        return False
    return (diagnostic - admission).days >= delai_jours
