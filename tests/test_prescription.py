
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


# --- heure de prise choisie à la ligne (demande du service, 8 septembre) ----

def test_horaires_par_defaut_suit_le_rythme():
    assert p.horaires_par_defaut("Perfalgan", "x3/j") == (8, 16, 24)


def test_enoxaparine_en_une_prise_est_du_soir():
    """Une HBPM préventive se donne le soir. Prescrite à 8 h par défaut, il
    fallait corriger l'horaire à chaque ligne."""
    assert p.horaires_par_defaut("Enoxaparine 4000 UI", "x1/j") == (20,)
    assert p.horaires_par_defaut("Lovenox", "x1/j") == (20,)


def test_la_regle_enoxaparine_ne_vaut_que_pour_une_prise_par_jour():
    """En deux prises, c'est une dose curative : elle reprend les horaires du
    rythme, matin et soir."""
    assert p.horaires_par_defaut("Enoxaparine", "x2/j") == (8, 20)


def test_le_produit_est_reconnu_sans_accent_ni_casse():
    assert p.horaires_par_defaut("ENOXAPARINE", "x1/j") == (20,)


def test_un_produit_quelconque_garde_lhoraire_du_rythme():
    assert p.horaires_par_defaut("Augmentin", "x1/j") == (8,)


def test_analyser_horaires_accepte_ce_qui_se_tape_au_lit_du_malade():
    assert p.analyser_horaires("20") == "20"
    assert p.analyser_horaires("8h 20h") == "8,20"
    assert p.analyser_horaires("8, 14, 20") == "8,14,20"


def test_analyser_horaires_ignore_une_saisie_illisible():
    """Rien d'exploitable ne doit pas écraser silencieusement l'horaire du
    rythme : mieux vaut None, et le défaut s'applique."""
    assert p.analyser_horaires("") is None
    assert p.analyser_horaires("le matin") is None
    assert p.analyser_horaires("99") is None


def test_un_horaire_choisi_prime_sur_le_rythme():
    assert p.horaires_pour_rythme("x1/j", "20") == (20,)


# -- les trois colonnes d'une ligne de pancarte ------------------------------

def test_les_parties_dune_ligne_separent_le_produit_de_la_dose():
    """Reconstituer les colonnes en retranchant la dose d'une phrase déjà
    composée marche jusqu'au jour où un horaire se glisse derrière elle — et
    alors la dose s'affiche deux fois."""
    ligne = {"produit": "Kardégic", "voie": "PO", "dose": 75, "unite": "mg",
             "rythme": "x1/j", "horaires_override": "8", "date_debut": "2026-09-08"}
    etiquette, produit, dose = p.parties_ligne(ligne, "2026-09-09")
    assert etiquette.texte == "J2"
    assert produit == "Kardégic (8h)"
    assert dose == "75mg x1/j"
    assert dose not in produit


def test_les_additifs_restent_du_cote_du_produit():
    """C'est ce qu'il y a dans le flacon, pas la posologie."""
    ligne = {"produit": "Ringer Lactate", "voie": "ENTREES", "vitesse": 60,
             "additifs": "+ (3 KCl)", "rythme": "continu", "date_debut": "2026-09-08"}
    _e, produit, dose = p.parties_ligne(ligne, "2026-09-09")
    assert produit == "Ringer Lactate + (3 KCl)"
    assert dose == "60 cc/h"


def test_une_seringue_porte_sa_dilution_du_cote_de_la_dose():
    """C'est le nombre que l'infirmier règle sur la pompe."""
    ligne = {"produit": "Noradrénaline", "voie": "PSE", "dilution": "0,5 mg/cc",
             "vitesse": 25, "rythme": "continu", "date_debut": "2026-09-08"}
    _e, produit, dose = p.parties_ligne(ligne, "2026-09-09")
    assert produit == "Noradrénaline"
    assert dose == "0,5 mg/cc 25 cc/h"


def test_un_traitement_conditionnel_montre_sa_condition():
    ligne = {"produit": "Paracétamol", "voie": "IV", "dose": 1, "unite": "g",
             "rythme": "conditionnel", "condition_texte": "T ≥ 38,5 °C",
             "date_debut": "2026-09-08"}
    _e, produit, _dose = p.parties_ligne(ligne, "2026-09-09")
    assert produit == "Paracétamol si T ≥ 38,5 °C"
