
from rea.domaine import prescription as p


def test_horaires_x1j():
    assert p.horaires_pour_rythme("x1/j") == (8,)


def test_horaires_x4j_tranche_v1_3():
    # SPEC §5.3, question ouverte 6 tranchée en v1.3 : 6-12-18-24.
    assert p.horaires_pour_rythme("x4/j") == (6, 12, 18, 24)


def test_horaires_x6j():
    assert p.horaires_pour_rythme("x6/j") == (4, 8, 12, 16, 20, 24)


def test_horaires_continu_est_vide():
    assert p.horaires_pour_rythme("continu") == ()


def test_horaires_override_prevaut_sur_le_rythme():
    assert p.horaires_pour_rythme("x4/j", override="9,15,21") == (9, 15, 21)


def test_horaires_affiches():
    assert p.horaires_affiches("x2/j") == "8h-20h"


def test_ligne_active_avant_le_debut_est_fausse():
    ligne = {"statut": "active", "date_debut": "2026-09-05", "date_arret": None}
    assert p.ligne_active_le(ligne, "2026-09-01") is False


def test_ligne_active_apres_le_debut_est_vraie():
    ligne = {"statut": "active", "date_debut": "2026-09-01", "date_arret": None}
    assert p.ligne_active_le(ligne, "2026-09-05") is True


def test_ligne_arretee_apres_larret_est_fausse():
    ligne = {"statut": "arretee", "date_debut": "2026-08-01", "date_arret": "2026-08-20"}
    assert p.ligne_active_le(ligne, "2026-08-25") is False


def test_ligne_arretee_le_jour_meme_reste_visible():
    # « Arrêt d'un traitement : la ligne reste visible, barrée » (SPEC §5.1)
    ligne = {"statut": "arretee", "date_debut": "2026-08-01", "date_arret": "2026-08-20"}
    assert p.ligne_active_le(ligne, "2026-08-20") is True


def test_etiquette_jour_introduction():
    ligne = {"date_debut": "2026-09-01", "duree_prevue_jours": None}
    etiquette = p.etiquette_jour(ligne, "2026-09-01")
    assert etiquette.introduction is True
    assert etiquette.texte == "Introduction de"


def test_etiquette_jour_sans_duree():
    ligne = {"date_debut": "2026-09-01", "duree_prevue_jours": None}
    etiquette = p.etiquette_jour(ligne, "2026-09-02")
    assert etiquette.texte == "J2"


def test_etiquette_jour_avec_duree_dernier_jour():
    ligne = {"date_debut": "2026-08-27", "duree_prevue_jours": 7}
    etiquette = p.etiquette_jour(ligne, "2026-09-02")
    assert etiquette.jour == 7
    assert etiquette.texte == "J7/7"
    assert etiquette.dernier_jour is True


def test_etiquette_jour_echue_au_dela_de_la_duree():
    ligne = {"date_debut": "2026-08-27", "duree_prevue_jours": 5}
    etiquette = p.etiquette_jour(ligne, "2026-09-02")
    assert etiquette.echue is True


def test_libelle_ligne_targocid_introduction():
    ligne = {
        "produit": "Targocid",
        "dose": 400,
        "unite": "mg",
        "rythme": "x2/j",
        "date_debut": "2026-09-01",
        "duree_prevue_jours": None,
    }
    assert p.libelle_ligne(ligne, "2026-09-01") == "Introduction de Targocid 400mg x2/j (8h-20h)"


def test_libelle_ligne_avec_ampoules():
    ligne = {
        "produit": "Noradrénaline",
        "dose": None,
        "rythme": "continu",
        "vitesse": 2,
        "nb_ampoules": 3,
        "date_debut": "2026-09-01",
        "duree_prevue_jours": None,
    }
    texte = p.libelle_ligne(ligne, "2026-09-01")
    assert "vitesse 2" in texte
    assert "(3 amp)" in texte


def test_nb_prises_par_jour():
    assert p.nb_prises_par_jour("x3/j") == 3
    assert p.nb_prises_par_jour("continu") == 0
    assert p.nb_prises_par_jour(None) == 0


def test_volume_entrees_24h_pse():
    lignes = [{"voie": "PSE", "produit": "Noradrénaline", "vitesse": 2}]
    bilan = p.volume_entrees_24h(lignes)
    assert bilan.total_ml == 48.0


def test_volume_entrees_24h_perfusion():
    lignes = [
        {"voie": "ENTREES", "sous_type": "perfusion", "produit": "Ringer Lactate", "vitesse": 40}
    ]
    bilan = p.volume_entrees_24h(lignes)
    assert bilan.total_ml == 960.0


def test_volume_entrees_24h_nutrition():
    lignes = [
        {
            "voie": "ENTREES",
            "sous_type": "nutrition_enterale",
            "produit": "Nutrition entérale",
            "volume_24h": 1500,
        }
    ]
    assert p.volume_entrees_24h(lignes).total_ml == 1500.0


def test_volume_entrees_24h_iv_avec_dilution():
    lignes = [
        {"voie": "IV", "produit": "Perfalgan", "volume_dilution": 100, "rythme": "x3/j"}
    ]
    assert p.volume_entrees_24h(lignes).total_ml == 300.0


def test_volume_entrees_24h_ignore_po():
    lignes = [{"voie": "PO", "produit": "Kardégic", "dose": 160, "rythme": "x1/j"}]
    assert p.volume_entrees_24h(lignes).total_ml == 0.0


def test_volume_entrees_24h_cumule_plusieurs_sources():
    lignes = [
        {"voie": "PSE", "produit": "Noradrénaline", "vitesse": 2},
        {"voie": "ENTREES", "sous_type": "perfusion", "produit": "Ringer Lactate", "vitesse": 40},
        {
            "voie": "ENTREES",
            "sous_type": "nutrition_enterale",
            "produit": "Nutrition entérale",
            "volume_24h": 1500,
        },
        {"voie": "IV", "produit": "Perfalgan", "volume_dilution": 100, "rythme": "x3/j"},
    ]
    bilan = p.volume_entrees_24h(lignes)
    assert bilan.total_ml == 2808.0
    assert len(bilan.detail) == 4
