"""Ce qu'il faut lire en base pour imprimer une feuille de réanimation.

Existe pour tenir la règle R3 : *le rendu ne calcule rien et ne va rien
chercher*. Avant, `rea/rendu/feuille.py` ouvrait lui-même la base et appelait
six services — c'était la dépendance la plus lourde du dépôt, et elle allait
dans le mauvais sens (le rendu commandait le métier, et `services/pancarte.py`
rappelait le rendu en retour).

Ici on ne fait que lire et rassembler. Aucune mise en forme : pas de date en
français, pas de rond à cocher, pas de HTML. Tout cela reste au rendu, qui
reçoit ce dossier et n'a plus besoin de connaître ni la base ni les services.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from ..db import Base
from ..domaine import prescription as dom
from ..domaine.dates import parse_date
from . import avis as avis_service
from . import bilans as bilans_service
from . import dispositifs as dispositifs_service
from . import microbiologie as micro_service
from . import prescriptions as prescriptions_service
from . import scores as scores_service
from . import sejours as sejours_service
from . import vitesses as vitesses_service


@dataclass(frozen=True)
class DossierFeuille:
    """Tout ce que la feuille d'un jour donné a besoin de savoir.

    Volontairement des dicts et des listes ordinaires : ce dossier traverse la
    frontière entre le métier et le rendu, et rien de ce qui le compose ne doit
    obliger le rendu à réinterroger quoi que ce soit.
    """

    sejour_id: str
    date_jour: str
    sejour: dict
    pancarte: dict
    lignes_par_voie: dict
    pancarte_demain: dict
    etats_dispositifs: tuple = ()
    resultats: list = field(default_factory=list)
    gaz_du_sang: list = field(default_factory=list)
    microbiologie: list = field(default_factory=list)
    allergies: list = field(default_factory=list)
    scores: list = field(default_factory=list)
    regions_traumatiques: list = field(default_factory=list)
    motifs: list = field(default_factory=list)
    antecedents: list = field(default_factory=list)
    avis: list = field(default_factory=list)
    etat_antecedents: str = "non_renseigne"
    # Vitesse heure par heure de tout ce qui coule ce jour-là, par identifiant
    # de ligne de prescription ou de dispositif : {id: {heure: vitesse}}.
    vitesses: dict = field(default_factory=dict)


def _vitesses(base: Base, sejour_id: str, date_jour: str, lignes: list, etats) -> dict:
    """La vitesse heure par heure de tout ce qui coule, ce jour-là.

    Le calcul est fait ici, pas au rendu : décider quelle vitesse est en
    vigueur à l'ouverture de la journée est une question métier (règle R3).
    """
    reglages = vitesses_service.reglages_du_sejour(base, sejour_id)
    par_cible: dict[str, dict[int, float]] = {}
    coulantes = [
        (ligne["id"], ligne.get("vitesse")) for ligne in lignes
    ] + [
        (etat.id, (etat.details or {}).get("vitesse"))
        for etat in etats if etat.en_place and etat.id
    ]
    for cible_id, vitesse_initiale in coulantes:
        if vitesse_initiale is None and cible_id not in reglages:
            continue
        par_heure = dom.vitesses_par_heure(
            vitesse_initiale, reglages.get(cible_id, []), date_jour
        )
        if par_heure:
            par_cible[cible_id] = par_heure
    return par_cible


def rassembler(base: Base, sejour_id: str, date_jour: str) -> DossierFeuille:
    """Toutes les lectures nécessaires à une feuille, en un seul endroit."""
    sejour = sejours_service.sejour_avec_patient(base, sejour_id)
    if sejour is None:
        raise ValueError(f"Séjour inconnu : {sejour_id}")

    pancarte = prescriptions_service.pancarte_du_jour(base, sejour_id, date_jour)
    demain = (parse_date(date_jour) + timedelta(days=1)).isoformat()
    etats = tuple(dispositifs_service.etats(base, sejour_id, date_jour))

    sofa = scores_service.sofa(base, sejour_id, date_jour)
    igs2 = scores_service.igs2(base, sejour_id)

    return DossierFeuille(
        sejour_id=sejour_id,
        date_jour=date_jour,
        sejour=sejour,
        pancarte=pancarte,
        lignes_par_voie=prescriptions_service.lignes_par_voie(pancarte["lignes"]),
        pancarte_demain=prescriptions_service.pancarte_du_jour(base, sejour_id, demain),
        etats_dispositifs=etats,
        resultats=list(bilans_service.resultats_du_sejour(base, sejour_id)),
        gaz_du_sang=list(bilans_service.gaz_du_sang_du_sejour(base, sejour_id)),
        microbiologie=list(micro_service.du_sejour(base, sejour_id)),
        avis=list(avis_service.du_sejour(base, sejour_id)),
        allergies=list(sejours_service.allergies_du_patient(base, sejour["patient_id"])),
        # Les scores sont déjà du texte : ce sont eux que la feuille imprime,
        # et le rendu n'a pas à savoir comment ils se calculent.
        scores=[
            f"SOFA {sofa.total}" + ("" if sofa.complet else " (incomplet)"),
            f"IGS II {igs2.total}" + ("" if igs2.complet else " (incomplet)"),
        ],
        regions_traumatiques=list(sejours_service.regions_traumatiques_detail(base, sejour_id)),
        motifs=list(sejours_service.motifs_du_sejour(base, sejour_id)),
        # Jamais ressaisi sur la feuille : l'interrogatoire a déjà eu lieu à
        # l'admission, sur l'onglet Identité — les allergies restent à part,
        # dans leur propre encart rouge, pas dupliquées ici.
        antecedents=[
            a for a in sejours_service.antecedents_du_patient(base, sejour["patient_id"])
            if a["categorie"] != "allergie"
        ],
        etat_antecedents=sejours_service.etat_antecedents(base, sejour["patient_id"]),
        vitesses=_vitesses(base, sejour_id, date_jour, pancarte["lignes"], etats),
    )
