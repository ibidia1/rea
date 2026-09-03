"""Valeurs dérivées d'un bilan. Chaque formule est testée avec sa référence —
une définition non testée est une définition qui changera silencieusement.
"""

import pytest

from rea.domaine import calculs


# --- clairance de la créatinine (Cockcroft-Gault, 1976) -------------------

def test_clairance_homme():
    # (140 − 48) × 70 × 1,23 / 210 = 37,7
    c = calculs.clairance_cockcroft_gault(
        creatinine_umol_l=210, poids_kg=70, age_ans=48, sexe="M"
    )
    assert c.valeur == pytest.approx(37.7, abs=0.1)
    assert c.unite == "mL/min"


def test_clairance_femme_utilise_le_coefficient_1_04():
    homme = calculs.clairance_cockcroft_gault(
        creatinine_umol_l=100, poids_kg=60, age_ans=50, sexe="M"
    ).valeur
    femme = calculs.clairance_cockcroft_gault(
        creatinine_umol_l=100, poids_kg=60, age_ans=50, sexe="F"
    ).valeur
    assert femme < homme
    assert femme == pytest.approx(homme * 1.04 / 1.23, abs=0.1)


def test_clairance_sans_poids_rend_none():
    # C'est précisément pourquoi le poids est demandé à l'admission.
    assert calculs.clairance_cockcroft_gault(
        creatinine_umol_l=210, poids_kg=None, age_ans=48, sexe="M"
    ).valeur is None


def test_clairance_sans_sexe_rend_none():
    assert calculs.clairance_cockcroft_gault(
        creatinine_umol_l=210, poids_kg=70, age_ans=48, sexe="non_renseigne"
    ).valeur is None


def test_clairance_ne_divise_jamais_par_zero():
    assert calculs.clairance_cockcroft_gault(
        creatinine_umol_l=0, poids_kg=70, age_ans=48, sexe="M"
    ).valeur is None


def test_clairance_porte_sa_reference():
    c = calculs.clairance_cockcroft_gault(
        creatinine_umol_l=210, poids_kg=70, age_ans=48, sexe="M"
    )
    assert "Cockcroft" in c.reference
    # Le logiciel calcule une grandeur, jamais une consigne de dose (SPEC §3.1).
    assert "adaptation de dose" in c.commentaire


# --- natrémie corrigée à la glycémie (Katz, 1973) -------------------------

def test_natremie_corrigee_en_hyperglycemie():
    # 130 + 1,6 × (25 − 5,6) / 5,6 = 135,5
    assert calculs.natremie_corrigee(
        natremie_mmol_l=130, glycemie_mmol_l=25
    ).valeur == pytest.approx(135.5, abs=0.1)


def test_natremie_non_corrigee_si_glycemie_normale():
    assert calculs.natremie_corrigee(
        natremie_mmol_l=138, glycemie_mmol_l=5.0
    ).valeur == 138


def test_natremie_sans_glycemie_rend_none():
    assert calculs.natremie_corrigee(natremie_mmol_l=138, glycemie_mmol_l=None).valeur is None


# --- calcémie corrigée à l'albumine (Payne, 1973) -------------------------

def test_calcemie_corrigee_en_hypoalbuminemie():
    # 2,0 + 0,02 × (40 − 20) = 2,40
    assert calculs.calcemie_corrigee(
        calcemie_mmol_l=2.0, albumine_g_l=20
    ).valeur == pytest.approx(2.40, abs=0.01)


def test_calcemie_inchangee_si_albumine_normale():
    assert calculs.calcemie_corrigee(calcemie_mmol_l=2.35, albumine_g_l=40).valeur == 2.35


# --- autres ---------------------------------------------------------------

def test_rapport_pf():
    assert calculs.rapport_pao2_fio2(80, 50).valeur == 160


def test_rapport_pf_sans_fio2():
    assert calculs.rapport_pao2_fio2(80, None).valeur is None


def test_trou_anionique():
    assert calculs.trou_anionique(na=140, cl=100, hco3=24).valeur == 16


def test_toutes_les_valeurs_ne_rend_que_ce_qui_est_calculable():
    valeurs = calculs.toutes_les_valeurs(
        resultats={"creat": 210, "na": 130, "glycemie": 25},
        gaz={"pao2": 80, "fio2": 50},
        poids_kg=70, age_ans=48, sexe="M",
    )
    disponibles = {v.cle for v in valeurs if v.disponible}
    assert {"clairance_cg", "na_corrige", "pf"} <= disponibles
    # Ni albumine ni chlore saisis : pas de calcémie corrigée, pas de trou anionique.
    assert "ca_corrige" not in disponibles
    assert "trou_anionique" not in disponibles


def test_toutes_les_valeurs_sur_un_bilan_vide():
    valeurs = calculs.toutes_les_valeurs(resultats={}, gaz={})
    assert all(not v.disponible for v in valeurs)
    # Les entrées existent quand même, avec leur formule : on peut expliquer
    # à l'utilisateur ce qui manque.
    assert all(v.formule and v.reference for v in valeurs)


# --- poids idéal (Devine, 1974) -------------------------------------------

def test_poids_ideal_homme():
    # 50 + 0,91 × (175 − 152,4) = 70,6
    assert calculs.poids_ideal_devine(taille_cm=175, sexe="M").valeur == pytest.approx(70.6, abs=0.1)


def test_poids_ideal_femme():
    # 45,5 + 0,91 × (165 − 152,4) = 57,0
    assert calculs.poids_ideal_devine(taille_cm=165, sexe="F").valeur == pytest.approx(57.0, abs=0.1)


def test_poids_ideal_a_la_taille_pivot():
    # À 152,4 cm, la formule rend exactement la constante de départ.
    assert calculs.poids_ideal_devine(taille_cm=152.4, sexe="M").valeur == 50.0
    assert calculs.poids_ideal_devine(taille_cm=152.4, sexe="F").valeur == 45.5


def test_poids_ideal_sans_taille_rend_none():
    assert calculs.poids_ideal_devine(taille_cm=None, sexe="M").valeur is None


def test_poids_ideal_sans_sexe_rend_none():
    # La formule diffère entre homme et femme : sans le sexe, pas de résultat.
    assert calculs.poids_ideal_devine(taille_cm=175, sexe="non_renseigne").valeur is None


def test_poids_ideal_hors_domaine_de_validite():
    # Sous 1,20 m la formule rendrait un poids absurde : on n'affiche rien.
    assert calculs.poids_ideal_devine(taille_cm=100, sexe="M").valeur is None


def test_poids_ideal_ne_remplace_pas_le_poids_reel():
    v = calculs.poids_ideal_devine(taille_cm=175, sexe="M")
    assert "ne remplace pas le poids réel" in v.commentaire
    assert "Devine" in v.reference


def test_poids_ideal_figure_dans_les_valeurs_derivees():
    valeurs = calculs.toutes_les_valeurs(
        resultats={}, gaz={}, taille_cm=175, sexe="M",
    )
    ideal = next(v for v in valeurs if v.cle == "poids_ideal")
    assert ideal.valeur == pytest.approx(70.6, abs=0.1)
