"""Le bilan hydrique des 24 h (convention du service, 8 septembre 2026).

    entrées − (diurèse + drains + pertes insensibles)

Pertes insensibles : 0,5 mL/kg/h à 37 °C, majorées de 2 mL/kg/24 h par degré
au-dessus. Les constantes sont dans `referentiels/bilan_hydrique.json`, et ces
tests les lisent de là — changer le fichier ne doit pas faire échouer un test
qui vérifie la mécanique, seulement ceux qui vérifient la convention en cours.

Ce qui compte le plus ici : le bilan ne s'affiche pas tant qu'il manque une
donnée. Un chiffre inventé dans un bilan hydrique est pire que pas de chiffre.
"""

from rea import referentiels
from rea.domaine import prescription as dom
from rea.services import dispositifs, evolution, prescriptions, sejours

REGLAGES = referentiels.charger("bilan_hydrique")


def _sejour(base, poids=70):
    pid = sejours.creer_patient(base, matricule="M1", nom_affichage="Test",
                                date_naissance=None)
    return sejours.creer_sejour(base, patient_id=pid, date_admission="2026-09-06",
                                lit_admission=1, poids_kg=poids)


# --- pertes insensibles ----------------------------------------------------

def test_pertes_de_base_a_temperature_normale():
    """0,5 mL/kg/h × 24 h : 840 mL pour 70 kg."""
    base, majoration, _formule = dom.pertes_insensibles_24h(70, 37)
    assert base == 840
    assert majoration == 0


def test_pas_de_majoration_en_dessous_de_la_reference():
    _base, majoration, _f = dom.pertes_insensibles_24h(70, 36.2)
    assert majoration == 0


def test_la_fievre_majore_par_degre_au_dessus():
    """39 °C chez 70 kg : deux degrés × 2 mL/kg/24 h = 280 mL."""
    _base, majoration, _f = dom.pertes_insensibles_24h(70, 39)
    assert majoration == 280


def test_un_demi_degre_majore_de_moitie():
    _base, majoration, _f = dom.pertes_insensibles_24h(70, 37.5)
    assert majoration == 70


def test_sans_poids_rien_nest_calcule():
    """Une perte insensible sans poids n'existe pas."""
    base, majoration, formule = dom.pertes_insensibles_24h(None, 39)
    assert base is None and majoration is None
    assert "mL/kg/h" in formule          # la formule reste affichable


def test_sans_temperature_aucune_majoration():
    """Une température non relevée n'est pas une apyrexie — mais elle ne
    justifie aucune majoration non plus."""
    base, majoration, _f = dom.pertes_insensibles_24h(70, None)
    assert base == 840 and majoration == 0


def test_le_mode_forfait_applique_un_nombre_fixe_par_degre():
    """Le service peut basculer sur le forfait — c'est une ligne du fichier de
    réglages, pas une ligne de code."""
    forfait = {**REGLAGES, "majoration_fievre_mode": "forfait"}
    _base, majoration, formule = dom.pertes_insensibles_24h(70, 39, forfait)
    assert majoration == 2 * REGLAGES["majoration_fievre_forfait_ml_par_degre"]
    assert "par degré" in formule


def test_le_mode_par_kilo_est_celui_du_fichier_livre():
    assert REGLAGES["majoration_fievre_mode"] == "ml_kg"


# --- le bilan complet ------------------------------------------------------

def _lignes():
    """1 560 mL d'entrées : 5 cc/h de PSE et 60 cc/h de perfusion."""
    return [
        {"voie": "PSE", "produit": "Noradrénaline", "vitesse": 5},
        {"voie": "ENTREES", "sous_type": "perfusion", "produit": "Ringer", "vitesse": 60},
    ]


def test_le_net_suit_la_formule_du_service():
    """1560 − (1200 + 150 + 840 + 280) = −910."""
    bilan = dom.bilan_hydrique(
        _lignes(), diurese_ml=1200, drains=[("Redon", 150)],
        poids_kg=70, temperature_c=39,
    )
    assert bilan.entrees_ml == 1560
    assert bilan.pertes_insensibles_ml == 1120
    assert bilan.sorties_ml == 2470
    assert bilan.net_ml == -910


def test_un_bilan_positif_reste_positif():
    bilan = dom.bilan_hydrique(
        _lignes(), diurese_ml=200, poids_kg=70, temperature_c=37,
    )
    assert bilan.net_ml == 1560 - (200 + 840)


def test_sans_diurese_le_bilan_ne_se_calcule_pas():
    """Une diurèse non relevée n'est pas une diurèse nulle."""
    bilan = dom.bilan_hydrique(_lignes(), diurese_ml=None, poids_kg=70, temperature_c=37)
    assert bilan.net_ml is None
    assert bilan.sorties_ml is None
    assert "la diurèse des 24 h" in bilan.manquants


def test_sans_poids_le_bilan_ne_se_calcule_pas():
    bilan = dom.bilan_hydrique(_lignes(), diurese_ml=1200, poids_kg=None, temperature_c=37)
    assert bilan.net_ml is None
    assert "le poids (pertes insensibles)" in bilan.manquants


def test_sans_drain_les_sorties_nen_comptent_aucun():
    bilan = dom.bilan_hydrique(_lignes(), diurese_ml=1200, poids_kg=70, temperature_c=37)
    assert bilan.drains_ml == 0
    assert bilan.detail_drains == []


def test_plusieurs_drains_sadditionnent():
    bilan = dom.bilan_hydrique(
        _lignes(), diurese_ml=1200, drains=[("Redon 1", 120), ("Drain thoracique", 80)],
        poids_kg=70, temperature_c=37,
    )
    assert bilan.drains_ml == 200


def test_le_detail_des_entrees_reste_lisible():
    """Un bilan positif ne se lit pas pareil selon qu'il vient d'un
    remplissage ou d'une nutrition : le détail suit le total."""
    bilan = dom.bilan_hydrique(_lignes(), diurese_ml=1200, poids_kg=70, temperature_c=37)
    assert [libelle for libelle, _v in bilan.detail_entrees] == [
        "Noradrénaline (PSE)", "Ringer"
    ]


# --- les drains du jour, lus depuis les dispositifs en place ---------------

def test_seuls_les_dispositifs_draines_demandent_un_volume(base):
    """La sonde urinaire n'en est pas : son volume, c'est la diurèse, et
    l'ajouter la compterait deux fois."""
    sid = _sejour(base)
    dispositifs.poser(base, sejour_id=sid, type_="redon", date_pose="2026-09-07",
                      site="Site opératoire")
    dispositifs.poser(base, sejour_id=sid, type_="sonde_urinaire", date_pose="2026-09-07")
    dispositifs.poser(base, sejour_id=sid, type_="kt_central", date_pose="2026-09-07")

    drains = evolution.drains_du_jour(base, sid, "2026-09-08")
    assert [d["libelle"] for d in drains] == ["Redon (site opératoire)"]


def test_un_drain_retire_ne_demande_plus_de_volume(base):
    sid = _sejour(base)
    did = dispositifs.poser(base, sejour_id=sid, type_="drain_thoracique",
                            date_pose="2026-09-06", site="Droit")
    assert len(evolution.drains_du_jour(base, sid, "2026-09-07")) == 1
    dispositifs.retirer(base, did, date_retrait="2026-09-07")
    assert evolution.drains_du_jour(base, sid, "2026-09-08") == []


def test_le_volume_dun_drain_senregistre_et_se_relit(base):
    """La clé porte l'identifiant du dispositif : un patient n'a pas toujours
    les mêmes drains, elle ne peut pas être dans la liste fixe des éléments."""
    sid = _sejour(base)
    dispositifs.poser(base, sejour_id=sid, type_="redon", date_pose="2026-09-07")
    cle = evolution.drains_du_jour(base, sid, "2026-09-08")[0]["cle"]

    evolution.enregistrer_elements(base, sid, "2026-09-08", {cle: 150})

    assert evolution.drains_du_jour(base, sid, "2026-09-08")[0]["valeur"] == 150
    ligne = base.une_ligne(
        "SELECT plan FROM evolution_element WHERE cle = ? AND supprime = 0", (cle,)
    )
    assert ligne["plan"] == "hemodynamique"


# --- le bilan tel que l'écran et le texte généré le voient -----------------

def test_le_service_assemble_le_bilan_du_dossier(base):
    sid = _sejour(base, poids=70)
    prescriptions.ajouter_ligne(base, sejour_id=sid, voie="ENTREES", produit="Ringer",
                                sous_type="perfusion", vitesse=60,
                                date_debut="2026-09-07")
    dispositifs.poser(base, sejour_id=sid, type_="redon", date_pose="2026-09-07")
    cle = evolution.drains_du_jour(base, sid, "2026-09-08")[0]["cle"]
    evolution.enregistrer_elements(base, sid, "2026-09-08", {
        "diurese_24h": 1200, "temperature": 39, cle: 150,
    })

    bilan = evolution.bilan_hydrique(base, sid, "2026-09-08")
    assert bilan.entrees_ml == 1440          # 60 cc/h × 24
    assert bilan.diurese_ml == 1200
    assert bilan.drains_ml == 150
    assert bilan.pertes_insensibles_ml == 840 + 280
    assert bilan.net_ml == 1440 - (1200 + 150 + 1120)


def test_le_texte_genere_porte_le_bilan_et_son_detail(base):
    sid = _sejour(base, poids=70)
    prescriptions.ajouter_ligne(base, sejour_id=sid, voie="ENTREES", produit="Ringer",
                                sous_type="perfusion", vitesse=60,
                                date_debut="2026-09-07")
    evolution.enregistrer_elements(base, sid, "2026-09-08", {
        "diurese_24h": 1200, "temperature": 37,
    })
    texte = evolution.texte_bilan_hydrique(base, sid, "2026-09-08")
    assert texte.startswith("Bilan hydrique -600 mL")
    assert "entrées 1440 mL" in texte
    assert "diurèse 1200 mL" in texte
    assert "pertes insensibles 840 mL" in texte


def test_le_texte_reste_muet_tant_quil_manque_une_donnee(base):
    """Un bilan à moitié calculé se recopierait dans l'observation comme s'il
    était complet."""
    sid = _sejour(base, poids=70)
    assert evolution.texte_bilan_hydrique(base, sid, "2026-09-08") == ""


def test_le_bilan_apparait_dans_le_plan_hemodynamique(base):
    sid = _sejour(base, poids=70)
    prescriptions.ajouter_ligne(base, sejour_id=sid, voie="ENTREES", produit="Ringer",
                                sous_type="perfusion", vitesse=60,
                                date_debut="2026-09-07")
    evolution.enregistrer_elements(base, sid, "2026-09-08", {
        "diurese_24h": 1200, "temperature": 37,
    })
    texte = evolution.texte_genere(base, sid, "2026-09-08")
    lignes = texte.splitlines()
    debut = lignes.index("Sur le plan hémodynamique :")
    suite = lignes[debut + 1:debut + 4]
    assert any("Bilan hydrique" in l for l in suite)


def test_un_drain_pose_apres_coup_napparait_pas_les_jours_davant(base):
    """Un drain posé aujourd'hui n'a rien recueilli avant-hier : le bilan
    hydrique d'un jour passé ne doit pas changer parce qu'on pose un drain
    aujourd'hui."""
    sid = _sejour(base)
    dispositifs.poser(base, sejour_id=sid, type_="redon", date_pose="2026-09-08")
    assert [d["libelle"] for d in evolution.drains_du_jour(base, sid, "2026-09-08")] == ["Redon"]
    assert evolution.drains_du_jour(base, sid, "2026-09-07") == []


def test_un_drain_apparait_des_le_jour_de_sa_pose(base):
    sid = _sejour(base)
    dispositifs.poser(base, sejour_id=sid, type_="drain_abdominal", date_pose="2026-09-07")
    assert len(evolution.drains_du_jour(base, sid, "2026-09-07")) == 1
    assert len(evolution.drains_du_jour(base, sid, "2026-09-09")) == 1


def test_tous_les_types_de_drains_du_referentiel_sont_proposables(base):
    """Redon, drain thoracique, drain abdominal, DVE : les quatre se posent
    depuis l'écran des actes et se retrouvent dans l'évolution."""
    from rea import listes

    sid = _sejour(base)
    draines = [c for c, t in listes.TYPES_DISPOSITIF.items() if t.get("draine")]
    assert set(draines) == {"redon", "drain_thoracique", "drain_abdominal", "dve"}
    for code in draines:
        assert code in listes.ORDRE_DISPOSITIFS      # proposé dans la liste de pose
        dispositifs.poser(base, sejour_id=sid, type_=code, date_pose="2026-09-07")
    assert len(evolution.drains_du_jour(base, sid, "2026-09-08")) == len(draines)


# --- les vitesses suivies réglage par réglage ------------------------------
#
# Le calcul comptait la vitesse d'ouverture pendant 24 h. Une noradrénaline
# montée la nuit et redescendue le matin valait donc sa valeur de départ toute
# la journée, et le bilan — celui qui décide d'une déplétion ou d'un
# remplissage — était faux des deux côtés (demande du service, 9 septembre).

def test_volume_perfuse_integre_chaque_reglage():
    """25 cc/h jusqu'à midi puis 10 : 4 h × 25 + 20 h × 10 = 300 mL, pas 600."""
    reglages = [{"date_heure": "2026-09-09T12:00", "vitesse": 10}]
    assert dom.volume_perfuse(25, reglages, "2026-09-09") == 300.0


def test_volume_perfuse_sans_reglage_vaut_la_vitesse_pendant_24_h():
    assert dom.volume_perfuse(25, [], "2026-09-09") == 600.0


def test_volume_perfuse_compte_la_journee_de_service_pas_le_jour_civil():
    """La journée court de 8 h à 8 h : un réglage noté à 3 h du matin
    appartient à la feuille ouverte la veille, comme la grille imprimée."""
    reglages = [
        {"date_heure": "2026-09-08T22:00", "vitesse": 12},   # avant : fixe l'ouverture
        {"date_heure": "2026-09-10T03:00", "vitesse": 4},    # la nuit de cette feuille
    ]
    # 8 h → 3 h le lendemain = 19 h à 12, puis 5 h à 4.
    assert dom.volume_perfuse(25, reglages, "2026-09-09") == 19 * 12 + 5 * 4


def test_volume_perfuse_ignore_un_horodatage_illisible():
    """Un réglage mal saisi ne doit pas empêcher le bilan de s'afficher."""
    reglages = [{"date_heure": "2026-09-09Tmidi", "vitesse": 10}]
    assert dom.volume_perfuse(25, reglages, "2026-09-09") >= 0


def test_les_entrees_du_dossier_suivent_les_changements_de_vitesse(base):
    """Bout en bout : le service lit l'historique, le bilan le reflète."""
    from rea.services import vitesses

    sid = _sejour(base, poids=70)
    ligne_id = prescriptions.ajouter_ligne(
        base, sejour_id=sid, voie="ENTREES", produit="Ringer",
        sous_type="perfusion", vitesse=60, date_debut="2026-09-07",
    )
    vitesses.regler(base, cible=vitesses.LIGNE, cible_id=ligne_id,
                    date_heure="2026-09-08T20:00", vitesse=20)
    evolution.enregistrer_elements(base, sid, "2026-09-08",
                                   {"diurese_24h": 1200, "temperature": 37})

    bilan = evolution.bilan_hydrique(base, sid, "2026-09-08")
    # 8 h → 20 h à 60 cc/h, puis 20 h → 8 h à 20 cc/h.
    assert bilan.entrees_ml == 12 * 60 + 12 * 20
    assert bilan.entrees_ml != 60 * 24


def test_la_pancarte_compte_les_entrees_comme_le_bilan(base):
    """La pancarte imprimée et le plan hémodynamique doivent annoncer le même
    volume : deux chiffres différents pour la même journée, et plus personne
    ne sait lequel croire."""
    from rea.services import vitesses

    sid = _sejour(base, poids=70)
    ligne_id = prescriptions.ajouter_ligne(
        base, sejour_id=sid, voie="PSE", produit="Noradrénaline",
        vitesse=25, date_debut="2026-09-07",
    )
    vitesses.regler(base, cible=vitesses.LIGNE, cible_id=ligne_id,
                    date_heure="2026-09-08T12:00", vitesse=10)

    pancarte = prescriptions.pancarte_du_jour(base, sid, "2026-09-08")
    bilan = evolution.bilan_hydrique(base, sid, "2026-09-08")
    assert pancarte["bilan_entrees"].total_ml == bilan.entrees_ml == 4 * 25 + 20 * 10


# --- une journée en cours n'a pas de bilan des 24 h ------------------------
#
# Le bilan et l'évolution se documentent après coup : on ne relève pas une
# diurèse des 24 h à 9 h du matin, et les entrées se compteraient sur la
# fenêtre entière d'une journée qui n'a que deux heures. On obtiendrait un
# chiffre qui n'est ni celui d'aujourd'hui ni celui d'hier, dans la case qui
# décide d'une déplétion ou d'un remplissage (remarque du service,
# 9 septembre).

from datetime import date as _date, datetime as _datetime


def test_la_journee_de_service_ouverte_a_6h_est_celle_de_la_veille():
    """La journée court de 8 h à 8 h : à 6 h le 9, on remplit encore la
    feuille ouverte le 8."""
    assert dom.jour_de_service(_datetime(2026, 9, 9, 6, 0)) == _date(2026, 9, 8)
    assert dom.jour_de_service(_datetime(2026, 9, 9, 9, 0)) == _date(2026, 9, 9)


def test_la_derniere_journee_close_est_celle_qu_on_documente_a_la_visite():
    """À 9 h le 9 septembre, la journée qui vient de finir est celle du 8."""
    assert dom.dernier_jour_clos(_datetime(2026, 9, 9, 9, 0)) == _date(2026, 9, 8)
    assert dom.dernier_jour_clos(_datetime(2026, 9, 9, 6, 0)) == _date(2026, 9, 7)


def test_une_journee_en_cours_n_est_pas_close():
    matin = _datetime(2026, 9, 9, 10, 0)
    assert not dom.journee_close("2026-09-09", matin)
    assert dom.journee_close("2026-09-08", matin)


def test_le_bilan_d_une_journee_en_cours_ne_rend_pas_de_net(base):
    """Même avec diurèse, poids et température saisis : les 24 h ne sont pas
    écoulées, il n'y a pas de bilan des 24 h."""
    bilan = dom.bilan_hydrique(
        _lignes(), diurese_ml=1200, poids_kg=70, temperature_c=37,
        date_jour="2026-09-09", instant=_datetime(2026, 9, 9, 10, 0),
    )
    assert bilan.net_ml is None
    assert not bilan.journee_close
    assert "Journée en cours" in bilan.motif_indisponible


def test_le_bilan_d_une_journee_close_se_calcule(base):
    bilan = dom.bilan_hydrique(
        _lignes(), diurese_ml=1200, poids_kg=70, temperature_c=37,
        date_jour="2026-09-08", instant=_datetime(2026, 9, 9, 10, 0),
    )
    assert bilan.journee_close
    assert bilan.net_ml is not None
    assert bilan.motif_indisponible is None


def test_le_motif_dit_ce_qui_manque_quand_la_journee_est_close(base):
    """Une journée close mais incomplète, ce n'est pas la même chose qu'une
    journée en cours : le message doit le distinguer."""
    bilan = dom.bilan_hydrique(
        _lignes(), diurese_ml=None, poids_kg=70, temperature_c=37,
        date_jour="2026-09-08", instant=_datetime(2026, 9, 9, 10, 0),
    )
    assert bilan.net_ml is None
    assert "Il manque" in bilan.motif_indisponible
    assert "Journée en cours" not in bilan.motif_indisponible
