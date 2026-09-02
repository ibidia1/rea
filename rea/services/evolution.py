"""Écran 6 — Évolution quotidienne (SPEC §8).

Seuls les quatre plans et la conduite sont saisis à la main ; le reste est
généré. En v1, le générateur ne reprend que l'en-tête et le prescrit — les
sections Explorations et Bilan du jour restent vides tant que ces écrans ne
sont pas construits (voir SPEC §8.2, blocs 4 et 5).
"""

from __future__ import annotations

from .. import config
from ..db import Base
from ..domaine import prescription as dom
from ..domaine.dates import format_date_fr, jour_hospitalisation
from . import prescriptions as prescriptions_service
from . import sejours as sejours_service

PLANS = ("plan_neurologique", "plan_respiratoire", "plan_hemodynamique", "plan_infectieux")
LIBELLES_PLANS = {
    "plan_neurologique": "Sur le plan Neurologique",
    "plan_respiratoire": "Sur le plan respiratoire",
    "plan_hemodynamique": "Sur le plan hémodynamique",
    "plan_infectieux": "Sur le plan Infectieux",
}


def obtenir_ou_creer(base: Base, sejour_id: str, date_jour: str, *, utilisateur_id: str | None = None) -> dict:
    existante = base.une_ligne(
        "SELECT * FROM evolution_jour WHERE sejour_id = ? AND date_jour = ? AND supprime = 0",
        (sejour_id, date_jour),
    )
    if existante:
        return existante
    id_ = base.inserer(
        "evolution_jour", {"sejour_id": sejour_id, "date_jour": date_jour}, utilisateur_id=utilisateur_id
    )
    return base.une_ligne("SELECT * FROM evolution_jour WHERE id = ?", (id_,))


def enregistrer(
    base: Base, sejour_id: str, date_jour: str, valeurs: dict, *, utilisateur_id: str | None = None
) -> None:
    """`valeurs` : sous-ensemble de PLANS + 'conduite'."""
    entree = obtenir_ou_creer(base, sejour_id, date_jour, utilisateur_id=utilisateur_id)
    champs_valides = {k: v for k, v in valeurs.items() if k in PLANS + ("conduite",)}
    base.mettre_a_jour("evolution_jour", entree["id"], champs_valides, utilisateur_id=utilisateur_id)


def texte_genere(base: Base, sejour_id: str, date_jour: str) -> str:
    """Format cible SPEC §8.1, prêt à copier dans le DMI."""
    sejour = sejours_service.sejour_avec_patient(base, sejour_id)
    entree = base.une_ligne(
        "SELECT * FROM evolution_jour WHERE sejour_id = ? AND date_jour = ? AND supprime = 0",
        (sejour_id, date_jour),
    ) or {}
    jour_hosp = jour_hospitalisation(sejour["date_admission"], date_jour)

    hco3 = "HCO₃⁻" if config.SYMBOLES_UNICODE else "HCO3-"
    pao2 = "PaO₂" if config.SYMBOLES_UNICODE else "PaO2"

    lignes = [f"{format_date_fr(date_jour)}, J{jour_hosp} d'hospitalisation :"]
    for cle in PLANS:
        lignes.append(f"{LIBELLES_PLANS[cle]} :")
        if entree.get(cle):
            lignes.append(entree[cle])

    # Explorations et Bilan du jour : sections prévues, non alimentées tant
    # que les écrans Explorations et Bilans ne sont pas construits.
    lignes.append("Explorations :")
    lignes.append("Bilan du jour :")

    lignes.append("Sous le traitement :")
    pancarte = prescriptions_service.pancarte_du_jour(base, sejour_id, date_jour)
    lignes_traitement = [
        dom.libelle_ligne(l, date_jour) for l in pancarte["lignes"] if l["statut"] == "active"
    ]
    if lignes_traitement:
        lignes.extend(lignes_traitement)

    lignes.append("Conduite :")
    if entree.get("conduite"):
        lignes.append(entree["conduite"])
    else:
        lignes.append("==>")

    texte = "\n".join(lignes)
    if not config.SYMBOLES_UNICODE:
        texte = texte.replace("HCO₃⁻", "HCO3-").replace("PaO₂", "PaO2").replace("PaCO₂", "PaCO2")
    return texte
