"""Bloc 4 de la feuille de route — contrôles de cohérence.

Critère de fin fixé par la feuille de route : « dix erreurs de frappe
volontaires sur dix sont signalées ». C'est littéralement le premier test.
"""

from rea import analytes as cat
from rea.domaine import coherence as c


def test_dix_erreurs_volontaires_sur_dix_sont_signalees():
    erreurs = [
        # 1. Kaliémie à 45 — l'exemple de la feuille de route
        lambda: c.verifier_bilan({"k": 45}),
        # 2. Hémoglobine à 92 au lieu de 9.2 — virgule oubliée
        lambda: c.verifier_bilan({"hb": 92}),
        # 3. Créatinine en mg/L saisie comme des µmol/L
        lambda: c.verifier_bilan({"creat": 12000}),
        # 4. Plaquettes à 0 — zéro tapé par erreur
        lambda: c.verifier_bilan({"plq": 0}),
        # 5. pH à 74 au lieu de 7.4
        lambda: c.verifier_gaz_du_sang({"ph": 74}),
        # 6. FiO2 à 5 % — impossible
        lambda: c.verifier_gaz_du_sang({"fio2": 5}),
        # 7. Sortie avant l'admission
        lambda: c.verifier_sejour(
            date_admission="2026-09-01", date_sortie="2026-08-20", aujourdhui="2026-09-03"
        ),
        # 8. Extubation avant l'intubation — l'autre exemple de la feuille de route
        lambda: c.verifier_dispositif(
            date_pose="2026-09-02", date_retrait="2026-08-30", aujourdhui="2026-09-03"
        ),
        # 9. Naissance dans le futur
        lambda: c.verifier_sejour(
            date_admission="2026-09-01", date_naissance="2030-01-01", aujourdhui="2026-09-03"
        ),
        # 10. Dose de 5 000 000 — erreur d'unité
        lambda: c.verifier_prescription(date_debut="2026-09-01", dose=5_000_000),
    ]
    signalees = [i for i, verifier in enumerate(erreurs, 1) if verifier()]
    assert len(signalees) == 10, f"non signalées : {set(range(1, 11)) - set(signalees)}"


# --- ne pas crier au loup -------------------------------------------------

def test_des_valeurs_anormales_mais_reelles_ne_sont_pas_signalees():
    # Une kaliémie à 6,2 est hors normes mais parfaitement réelle en réanimation :
    # elle est signalée par les bornes usuelles, pas par les contrôles de saisie.
    assert c.verifier_bilan({"k": 6.2}) == []
    assert c.verifier_bilan({"crp": 380}) == []
    assert c.verifier_bilan({"creat": 900}) == []
    assert c.verifier_gaz_du_sang({"ph": 7.05, "fio2": 100, "pep": 18}) == []


def test_les_deux_jeux_de_bornes_sont_bien_distincts():
    # Bornes usuelles : « anormal ». Bornes physiologiques : « impossible ».
    assert cat.analyte("k").hors_bornes(6.2) == "haut"   # anormal
    assert c.verifier_bilan({"k": 6.2}) == []            # mais pas impossible


def test_valeur_absente_nest_jamais_signalee():
    assert c.verifier_bilan({"k": None, "hb": None}) == []
    assert c.verifier_sejour(date_admission=None) == []


def test_analyte_sans_bornes_physiologiques_ne_leve_rien():
    assert c.verifier_bilan({"bili_i": 99999}) == []


# --- dates ---------------------------------------------------------------

def test_sejour_coherent_ne_leve_rien():
    assert c.verifier_sejour(
        date_admission="2026-08-29", date_sortie="2026-09-02",
        date_naissance="1978-03-14", aujourdhui="2026-09-03",
    ) == []


def test_admission_dans_le_futur():
    avertissements = c.verifier_sejour(date_admission="2026-12-01", aujourdhui="2026-09-03")
    assert avertissements[0].gravite == "impossible"


def test_naissance_apres_admission():
    avertissements = c.verifier_sejour(
        date_admission="2026-09-01", date_naissance="2026-09-02", aujourdhui="2026-09-03"
    )
    assert any("naissance suit l'admission" in a.message for a in avertissements)


def test_age_de_plus_de_120_ans():
    avertissements = c.verifier_sejour(
        date_admission="2026-09-01", date_naissance="1880-01-01", aujourdhui="2026-09-03"
    )
    assert any("Âge calculé" in a.message for a in avertissements)


def test_dispositif_pose_avant_admission_est_signale_sans_etre_impossible():
    avertissements = c.verifier_dispositif(
        date_pose="2026-08-25", date_admission="2026-08-29", aujourdhui="2026-09-03"
    )
    assert len(avertissements) == 1
    assert avertissements[0].gravite == "improbable"


def test_dispositif_coherent_ne_leve_rien():
    assert c.verifier_dispositif(
        date_pose="2026-08-30", date_retrait="2026-09-02",
        date_admission="2026-08-29", aujourdhui="2026-09-03",
    ) == []


# --- prescription --------------------------------------------------------

def test_prescription_duree_absurde():
    assert c.verifier_prescription(date_debut="2026-09-01", duree_prevue_jours=400)


def test_prescription_vitesse_absurde():
    assert c.verifier_prescription(date_debut="2026-09-01", vitesse=900)


def test_prescription_normale_ne_leve_rien():
    assert c.verifier_prescription(
        date_debut="2026-08-29", duree_prevue_jours=7, dose=1, vitesse=2,
        date_admission="2026-08-29",
    ) == []


def test_resume_lisible():
    avertissements = c.verifier_bilan({"k": 45, "hb": 92})
    assert " · " in c.resume(avertissements)
