"""L'ordre des voies : entrées, PSE, IV, PO, SC, aérosols, soins locaux, kiné.

C'est l'ordre de la visite — on commence par ce qui coule, on finit par ce
qui se fait au lit — demandé par le service le 10 septembre 2026. Il vaut
partout où les traitements se suivent : écran Prescrit, mode Visite,
regroupement par voie du service, observation générée.
"""

import re

from rea import listes
from rea.services import prescriptions as prescriptions_service

ORDRE_DEMANDE = ("ENTREES", "PSE", "IV", "PO", "SC", "AEROSOL", "SOINS", "KINE")


def test_l_ordre_du_referentiel_est_celui_du_service():
    assert listes.ORDRE_VOIES == ORDRE_DEMANDE


def test_toutes_les_voies_declarees_sont_dans_l_ordre():
    """Une voie oubliée dans « ordre » ne s'afficherait nulle part."""
    assert set(listes.ORDRE_VOIES) == set(listes.VOIES)


def test_le_regroupement_par_voie_suit_cet_ordre():
    lignes = [
        {"voie": "PO", "produit": "Paracétamol"},
        {"voie": "ENTREES", "produit": "SG5"},
        {"voie": "IV", "produit": "Imipénème"},
        {"voie": "PSE", "produit": "Noradrénaline"},
    ]
    groupes = prescriptions_service.lignes_par_voie(lignes)
    assert list(groupes) == list(ORDRE_DEMANDE)


def test_une_voie_inconnue_ne_perd_pas_sa_ligne():
    """Un ancien enregistrement dont la voie a disparu du référentiel reste
    affiché, à la fin, plutôt que d'être escamoté."""
    groupes = prescriptions_service.lignes_par_voie([{"voie": "XXX", "produit": "?"}])
    assert groupes["XXX"] == [{"voie": "XXX", "produit": "?"}]


def test_la_couleur_des_boutons_suit_l_ordre_des_voies():
    """Le CSS vise les boutons par leur rang : s'il suit un autre ordre que
    celui de l'écran, chaque bouton porte la couleur de son voisin."""
    from rea.ui import theme

    couleurs = re.findall(
        r'nth-of-type\((\d+)\) \{ border-color:(#[0-9a-fA-F]{6})',
        theme._CSS_BOUTONS_VOIES,
    )
    assert [int(rang) for rang, _ in couleurs] == list(range(1, len(listes.ORDRE_VOIES) + 1))
    for (_, couleur), voie in zip(couleurs, listes.ORDRE_VOIES):
        assert couleur.lower() == theme.COULEUR_VOIE[voie].lower(), voie


def test_les_ecrans_ne_reordonnent_pas_les_voies_dans_leur_code():
    """Règle R2 : l'ordre se change dans le référentiel, pas dans le code."""
    from pathlib import Path

    racine = Path(__file__).resolve().parent.parent
    for chemin in [racine / "rea" / "ui" / "prescrit.py",
                   racine / "rea" / "ui" / "visite.py"]:
        source = chemin.read_text(encoding="utf-8")
        assert "ORDRE_VOIES" in source, chemin.name
        assert "sorted(listes.ORDRE_VOIES" not in source, chemin.name
