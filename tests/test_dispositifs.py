from rea.domaine import dispositifs as dom
from rea.services import dispositifs, evolution, explorations, sejours


def _sejour(base):
    pid = sejours.creer_patient(base, matricule="M1", nom_affichage="Test", date_naissance=None)
    return sejours.creer_sejour(base, patient_id=pid, date_admission="2026-08-29", lit_admission=1)


# --- compteurs de jours : le cœur de la demande ---------------------------

def test_jour_en_cours_le_jour_de_la_pose_est_j1():
    assert dom.jour_en_cours("2026-09-02", "2026-09-02") == 1


def test_jour_en_cours_troisieme_jour():
    assert dom.jour_en_cours("2026-08-31", "2026-09-02") == 3


def test_jours_depuis_le_jour_meme_est_j0():
    # Convention « J0 = jour de l'événement », comme « J2 post-opératoire ».
    assert dom.jours_depuis("2026-09-02", "2026-09-02") == 0


def test_jours_depuis_deux_jours_apres():
    assert dom.jours_depuis("2026-08-31", "2026-09-02") == 2


def test_etat_intube_en_cours():
    ligne = {"type": "intubation", "date_pose": "2026-08-31", "date_retrait": None,
             "site": None, "details": '{"reperage_cm": 22}'}
    etat = dom.etat(ligne, "2026-09-02")
    assert etat.en_place is True
    assert etat.texte == "Intubé J3 (repère 22 cm)"


def test_etat_apres_extubation():
    ligne = {"type": "intubation", "date_pose": "2026-08-29", "date_retrait": "2026-08-31",
             "site": None, "details": None}
    etat = dom.etat(ligne, "2026-09-02")
    assert etat.en_place is False
    assert etat.texte == "Extubé J2"


def test_etat_apres_arret_sedation():
    ligne = {"type": "sedation", "date_pose": "2026-08-29", "date_retrait": "2026-09-01",
             "site": None, "details": None}
    assert dom.etat(ligne, "2026-09-02").texte == "Arrêt sédation J1"


def test_etat_kt_avec_site_et_voies():
    ligne = {"type": "kt_central", "date_pose": "2026-08-29", "date_retrait": None,
             "site": "Jugulaire interne droite", "details": '{"nb_voies": 3}'}
    assert dom.etat(ligne, "2026-09-02").texte == (
        "KT central J5 (jugulaire interne droite, 3 voies)"
    )


def test_etat_sng_avec_fixation():
    ligne = {"type": "sng", "date_pose": "2026-09-01", "date_retrait": None,
             "site": "Narine droite", "details": '{"fixation_cm": 55}'}
    assert dom.etat(ligne, "2026-09-02").texte == "SNG J2 (narine droite, fixée à 55 cm)"


def test_details_json_invalide_ne_casse_pas():
    ligne = {"type": "kta", "date_pose": "2026-09-01", "date_retrait": None,
             "site": None, "details": "pas du json"}
    assert dom.etat(ligne, "2026-09-02").texte == "KTA J2"


def test_resume_ne_garde_que_ce_qui_est_en_place():
    lignes = [
        {"type": "intubation", "date_pose": "2026-08-31", "date_retrait": None, "site": None, "details": None},
        {"type": "sedation", "date_pose": "2026-08-31", "date_retrait": "2026-09-01", "site": None, "details": None},
    ]
    resume = dom.resume(lignes, "2026-09-02")
    assert resume == "Intubé J3"


def test_duree_totale_additionne_les_episodes():
    lignes = [
        {"type": "intubation", "date_pose": "2026-08-20", "date_retrait": "2026-08-25", "site": None, "details": None},
        {"type": "intubation", "date_pose": "2026-08-30", "date_retrait": "2026-09-01", "site": None, "details": None},
    ]
    assert dom.duree_totale_jours(lignes, "intubation", "2026-09-02") == 7


# --- service ---------------------------------------------------------------

def test_poser_puis_retirer(base):
    sid = _sejour(base)
    did = dispositifs.poser(
        base, sejour_id=sid, type_="intubation", date_pose="2026-08-31", details={"reperage_cm": 22}
    )
    assert len(dispositifs.en_place(base, sid)) == 1
    dispositifs.retirer(base, did, date_retrait="2026-09-01")
    assert dispositifs.en_place(base, sid) == []
    # La ligne reste consultable — sinon on perdrait « Extubé J2 ».
    assert len(dispositifs.du_sejour(base, sid)) == 1


def test_duree_ventilation_calculee_depuis_les_dispositifs(base):
    sid = _sejour(base)
    did = dispositifs.poser(base, sejour_id=sid, type_="intubation", date_pose="2026-08-30")
    dispositifs.retirer(base, did, date_retrait="2026-09-02")
    assert dispositifs.duree_ventilation_jours(base, sid, "2026-09-02") == 3


def test_resume_du_service(base):
    sid = _sejour(base)
    dispositifs.poser(base, sejour_id=sid, type_="intubation", date_pose="2026-08-31")
    dispositifs.poser(
        base, sejour_id=sid, type_="kt_central", date_pose="2026-08-30",
        site="Jugulaire interne droite",
    )
    resume = dispositifs.resume(base, sid, "2026-09-02")
    assert "Intubé J3" in resume
    assert "KT central J4 (jugulaire interne droite)" in resume


# --- explorations ----------------------------------------------------------

def test_exploration_valeurs_chiffrees_et_texte(base):
    sid = _sejour(base)
    explorations.enregistrer(
        base, sejour_id=sid, date_heure="2026-09-02T08:00", type_="dtc",
        valeurs={"ip_droit": 1.35, "ip_gauche": 1.28}, conclusion="hypoperfusion droite",
    )
    texte = explorations.texte_du_jour(base, sid, "2026-09-02")
    assert "IP droit 1.35" in texte
    assert "hypoperfusion droite" in texte


def test_exploration_cinetique_dune_valeur(base):
    sid = _sejour(base)
    explorations.enregistrer(base, sejour_id=sid, date_heure="2026-09-01T08:00",
                             type_="dtc", valeurs={"ip_droit": 1.10})
    explorations.enregistrer(base, sejour_id=sid, date_heure="2026-09-02T08:00",
                             type_="dtc", valeurs={"ip_droit": 1.35})
    historique = explorations.historique_valeur(base, sid, "dtc", "ip_droit")
    assert [h["valeur_num"] for h in historique] == [1.10, 1.35]


# --- reprise dans l'évolution ---------------------------------------------

def test_evolution_reprend_dispositifs_et_explorations(base):
    sid = _sejour(base)
    dispositifs.poser(base, sejour_id=sid, type_="intubation", date_pose="2026-08-31")
    explorations.enregistrer(
        base, sejour_id=sid, date_heure="2026-09-02T08:00", type_="dtc",
        valeurs={"ip_droit": 1.35},
    )
    texte = evolution.texte_genere(base, sid, "2026-09-02")
    assert "Intubé J3" in texte
    assert "IP droit 1.35" in texte


def test_compte_rendu_sortie_reprend_la_ventilation(base):
    sid = _sejour(base)
    did = dispositifs.poser(base, sejour_id=sid, type_="intubation", date_pose="2026-08-30")
    dispositifs.retirer(base, did, date_retrait="2026-09-02")
    sejours.cloturer_sejour(
        base, sid, date_heure_sortie="2026-09-05T10:00", mode_sortie="domicile"
    )
    compte_rendu = sejours.compte_rendu_sortie(base, sid)
    assert "Ventilation du 30/08/2026 au 02/09/2026" in compte_rendu
    assert "Durée totale de ventilation : 3 jours" in compte_rendu


# --- réintubation et extubation accidentelle (demande du service, 8 sept.) --

def test_une_deuxieme_intubation_est_une_reintubation(base):
    """Après une extubation, réintuber n'est pas intuber : c'est l'échec de
    l'extubation précédente, et ça se lit au premier coup d'œil."""
    sid = _sejour(base)
    premier = dispositifs.poser(base, sejour_id=sid, type_="intubation", date_pose="2026-08-30")
    dispositifs.retirer(base, premier, date_retrait="2026-09-01")
    dispositifs.poser(base, sejour_id=sid, type_="intubation", date_pose="2026-09-02")

    etats = dispositifs.etats(base, sid, "2026-09-03")
    en_place = next(e for e in etats if e.en_place)
    assert en_place.rang == 2
    assert en_place.libelle_type == "Réintubation"
    assert en_place.texte.startswith("Réintubé J2")


def test_la_premiere_intubation_reste_une_intubation(base):
    sid = _sejour(base)
    dispositifs.poser(base, sejour_id=sid, type_="intubation", date_pose="2026-09-02")
    etat = dispositifs.etats(base, sid, "2026-09-02")[0]
    assert etat.rang == 1
    assert etat.libelle_type == "Intubation"
    assert etat.texte.startswith("Intubé J1")


def test_le_rang_se_compte_du_plus_ancien_au_plus_recent(base):
    """Les lignes sont lues du plus récent au plus ancien : compter dans cet
    ordre ferait de l'intubation d'aujourd'hui la première."""
    sid = _sejour(base)
    premier = dispositifs.poser(base, sejour_id=sid, type_="intubation", date_pose="2026-08-30")
    dispositifs.retirer(base, premier, date_retrait="2026-09-01")
    dispositifs.poser(base, sejour_id=sid, type_="intubation", date_pose="2026-09-02")
    rangs = {e.date_pose: e.rang for e in dispositifs.etats(base, sid, "2026-09-03")}
    assert rangs == {"2026-08-30": 1, "2026-09-02": 2}


def test_un_type_sans_libelle_repete_ne_change_pas_de_nom(base):
    """Un deuxième KT central reste un KT central : seuls les types qui
    déclarent `libelle_repete` changent de nom."""
    sid = _sejour(base)
    premier = dispositifs.poser(base, sejour_id=sid, type_="kt_central", date_pose="2026-08-30")
    dispositifs.retirer(base, premier, date_retrait="2026-09-01")
    dispositifs.poser(base, sejour_id=sid, type_="kt_central", date_pose="2026-09-02")
    en_place = next(e for e in dispositifs.etats(base, sid, "2026-09-03") if e.en_place)
    assert en_place.rang == 2
    assert en_place.libelle_type == "Cathéter veineux central (KT)"


def test_une_extubation_accidentelle_se_lit_sur_la_ligne(base):
    sid = _sejour(base)
    did = dispositifs.poser(base, sejour_id=sid, type_="intubation", date_pose="2026-08-30")
    dispositifs.retirer(base, did, date_retrait="2026-09-01", motif_retrait="accidentelle")
    etat = dispositifs.etats(base, sid, "2026-09-02")[0]
    assert etat.motif_retrait == "accidentelle"
    assert "extubation accidentelle" in etat.texte


def test_une_extubation_sans_motif_ne_dit_rien_de_plus(base):
    sid = _sejour(base)
    did = dispositifs.poser(base, sejour_id=sid, type_="intubation", date_pose="2026-08-30")
    dispositifs.retirer(base, did, date_retrait="2026-09-01")
    etat = dispositifs.etats(base, sid, "2026-09-02")[0]
    assert etat.texte == "Extubé J1"


def test_le_motif_ne_saffiche_pas_tant_que_le_dispositif_est_en_place(base):
    sid = _sejour(base)
    dispositifs.poser(base, sejour_id=sid, type_="intubation", date_pose="2026-08-30")
    etat = dispositifs.etats(base, sid, "2026-08-31")[0]
    assert "accidentelle" not in etat.texte


def test_le_repere_anatomique_garde_ses_majuscules_dans_le_texte(base):
    """« T4-T6 » écrit « t4-t6 » ne se lit plus comme un repère."""
    from rea.domaine import dispositifs as dom_disp
    assert dom_disp.site_en_incise("Thoracique haute (T4-T6)") == "Thoracique haute (T4-T6)"
    assert dom_disp.site_en_incise("Droit") == "droit"
    assert dom_disp.site_en_incise("Jugulaire interne droite") == "jugulaire interne droite"
    assert dom_disp.site_en_incise("") == ""
