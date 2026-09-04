"""Scores de gravité (bloc 9).

La feuille de route rend les tests obligatoires pour ce bloc : un score faux
n'a aucun symptôme visible — il produit des chiffres plausibles.
"""

import pytest

from rea import aides as fichiers
from rea.domaine import scores
from rea.services import (
    bilans as bilans_service,
    dispositifs as dispositifs_service,
    evolution as evolution_service,
    scores as scores_service,
    sejours,
)


# -- moteur ------------------------------------------------------------------

def test_premier_palier_vrai_gagne():
    bareme = {
        "code": "t", "libelle": "T",
        "variables": [{
            "fait": "plaquettes", "libelle": "Plaquettes",
            "paliers": [
                {"si": [{"fait": "plaquettes", "op": "<", "valeur": 20}], "points": 4},
                {"si": [{"fait": "plaquettes", "op": "<", "valeur": 50}], "points": 3},
                {"si": [{"fait": "plaquettes", "op": "<", "valeur": 100}], "points": 2},
            ],
        }],
    }
    assert scores.calculer(bareme, {"plaquettes": 10}).total == 4
    assert scores.calculer(bareme, {"plaquettes": 30}).total == 3
    assert scores.calculer(bareme, {"plaquettes": 80}).total == 2


def test_une_variable_manquante_rend_le_score_incomplet():
    """Zéro point par convention, mais le score le dit."""
    bareme = {
        "code": "t", "libelle": "T",
        "variables": [{"fait": "glasgow", "libelle": "Glasgow",
                       "paliers": [{"si": [{"fait": "glasgow", "op": "<", "valeur": 6}],
                                    "points": 4}]}],
    }
    score = scores.calculer(bareme, {})
    assert score.total == 0
    assert not score.complet
    assert score.manquantes == ("Glasgow",)


# -- SOFA --------------------------------------------------------------------

def test_sofa_cas_construit():
    """Patient ventilé, PaO₂/FiO₂ 150 (3), plaquettes 45 (3), bilirubine 40 (2),
    PAM 60 (1), Glasgow 8 (3), créatinine 350 (3) → 15."""
    faits = {
        "ventile": True, "pao2_fio2": 150, "plaquettes": 45, "bilirubine": 40,
        "pam": 60, "glasgow": 8, "creatinine": 350, "diurese_24h": 800,
    }
    score = scores.calculer(fichiers.bareme("sofa"), faits)
    assert [c.points for c in score.composantes] == [3, 3, 2, 1, 3, 3]
    assert score.total == 15
    assert score.complet


def test_sofa_patient_sans_defaillance():
    faits = {
        "ventile": False, "pao2_fio2": 450, "plaquettes": 250, "bilirubine": 10,
        "pam": 80, "glasgow": 15, "creatinine": 70, "diurese_24h": 1500,
    }
    assert scores.calculer(fichiers.bareme("sofa"), faits).total == 0


def test_sofa_respiratoire_sans_ventilation_plafonne_a_2():
    """Les paliers 3 et 4 exigent un support ventilatoire : un patient non
    ventilé avec un rapport bas ne doit pas y tomber."""
    faits = {"ventile": False, "pao2_fio2": 90}
    respiration = scores.calculer(fichiers.bareme("sofa"), faits).composantes[0]
    assert respiration.points == 2


def test_sofa_renal_prend_le_pire_de_la_creatinine_et_de_la_diurese():
    faits = {"creatinine": 80, "diurese_24h": 150}
    rein = scores.calculer(fichiers.bareme("sofa"), faits).composantes[-1]
    assert rein.points == 4


# -- IGS II ------------------------------------------------------------------

def test_igs2_cas_construit():
    """Âge 72 (15), FC 130 (4), PAS 85 (5), T 39,5 (3), non ventilé (0),
    diurèse 1200 (0), urée 12 (6), GB 15 (0), K 4,2 (0), Na 140 (0),
    HCO₃ 18 (3), bilirubine 20 (0), Glasgow 11 (5), aucune maladie chronique (0),
    admission médicale (6) → 47."""
    faits = {
        "age": 72, "fc_max_24h": 130, "pas_min_24h": 85, "temperature_max_24h": 39.5,
        "ventile": False, "pao2_fio2": None, "diurese_24h": 1200, "uree": 12,
        "gb": 15, "kaliemie": 4.2, "natremie": 140, "bicarbonates": 18,
        "bilirubine": 20, "glasgow": 11, "maladie_chronique": "aucune",
        "type_admission": "medicale",
    }
    score = scores.calculer(fichiers.bareme("igs2"), faits)
    assert score.total == 47
    assert score.complet


def test_igs2_pao2_fio2_ne_compte_pas_sans_ventilation():
    faits = {"ventile": False, "pao2_fio2": 80}
    composante = next(
        c for c in scores.calculer(fichiers.bareme("igs2"), faits).composantes
        if c.code == "pao2_fio2"
    )
    assert composante.points == 0


def test_mortalite_predite_croit_avec_le_score():
    p30 = scores.mortalite_predite_igs2(30)
    p60 = scores.mortalite_predite_igs2(60)
    assert 0 < p30 < p60 < 1
    assert scores.mortalite_predite_igs2(None) is None


def test_le_bareme_igs2_est_marque_non_valide():
    """Il a été saisi de mémoire : tant qu'un senior ne l'a pas relu contre la
    publication, il ne doit pas se présenter comme validé."""
    assert fichiers.bareme("igs2")["valide"] is False


# -- jours sans ventilation --------------------------------------------------

def test_jours_sans_ventilation_un_deces_compte_zero():
    """C'est tout l'intérêt du critère : sans cette règle, mourir vite
    donnerait un bon résultat."""
    assert scores.jours_sans_ventilation(
        jours_ventile=3, decede=True, jours_observes=28) == 0


def test_jours_sans_ventilation_survivant():
    assert scores.jours_sans_ventilation(
        jours_ventile=6, decede=False, jours_observes=28) == 22


def test_jours_sans_ventilation_ventilation_plus_longue_que_la_periode():
    assert scores.jours_sans_ventilation(
        jours_ventile=40, decede=False, jours_observes=40) == 0


def test_jours_sans_ventilation_pas_encore_calculable():
    assert scores.jours_sans_ventilation(
        jours_ventile=2, decede=False, jours_observes=10) is None


# -- de bout en bout, depuis la base ----------------------------------------

def test_sofa_calcule_depuis_le_dossier(base):
    pid = sejours.creer_patient(
        base, matricule="M1", nom_affichage="K. A.", date_naissance="1954-01-01",
        sexe="M",
    )
    sid = sejours.creer_sejour(
        base, patient_id=pid, date_admission="2026-09-01", lit_admission=1,
        poids_kg=70, taille_cm=170, type_admission="medicale",
        maladie_chronique_igs2="aucune",
    )
    bilans_service.enregistrer_resultats(
        base, sejour_id=sid, date_heure="2026-09-01T06:00",
        valeurs={"plq": 45, "creat": 350, "bili": 40},
    )
    evolution_service.enregistrer_elements(
        base, sid, "2026-09-01", {"glasgow": 8, "pam": 60, "diurese_24h": 800}
    )
    dispositifs_service.poser(
        base, sejour_id=sid, type_="intubation", date_pose="2026-09-01"
    )
    score = scores_service.sofa(base, sid, "2026-09-01")
    # Sans gaz du sang saisis, la composante respiratoire manque : le score
    # doit le dire plutôt que de compter zéro en silence.
    assert "Respiration (PaO₂/FiO₂)" in score.manquantes
    assert not score.complet
    assert score.total == 12
