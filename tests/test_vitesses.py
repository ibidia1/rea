"""Les vitesses réglées dans la journée (demande du service, 8 septembre).

Une seringue ne se règle pas une fois pour toutes : elle part à 25 cc/h et on
la descend à 15 à 16 h. Ce qui est vérifié ici, c'est que la feuille sait
écrire cette suite heure par heure — et qu'elle range chaque réglage dans la
bonne journée, sachant que la journée du service va de 8 h à 8 h.
"""

from rea.domaine import prescription as dom
from rea.services import dispositifs, prescriptions, sejours, vitesses


def _sejour(base):
    pid = sejours.creer_patient(base, matricule="M1", nom_affichage="Test",
                                date_naissance=None)
    return sejours.creer_sejour(base, patient_id=pid, date_admission="2026-09-06",
                                lit_admission=1)


def _reglage(date_heure, vitesse):
    return {"date_heure": date_heure, "vitesse": vitesse}


# --- la journée du service : 8 h → 8 h -------------------------------------

def test_la_journee_commence_a_huit_heures():
    assert dom.heures_de_la_journee()[0] == 8
    assert dom.heures_de_la_journee()[-1] == 7
    assert len(dom.heures_de_la_journee()) == 24


def test_une_heure_du_petit_matin_appartient_a_la_journee_ouverte_la_veille():
    """La grille imprimée finit à 7 h : la nuit d'une feuille est celle qui
    suit sa matinée, pas celle qui la précède."""
    assert dom.horodatage_dans_journee("2026-09-08", 16) == "2026-09-08T16:00"
    assert dom.horodatage_dans_journee("2026-09-08", 2) == "2026-09-09T02:00"
    assert dom.horodatage_dans_journee("2026-09-08", 8) == "2026-09-08T08:00"


def test_la_fenetre_dune_journee_va_de_huit_a_huit():
    assert dom.fenetre_journee("2026-09-08") == (
        "2026-09-08T08:00", "2026-09-09T08:00"
    )


# --- la vitesse heure par heure --------------------------------------------

def test_sans_reglage_la_vitesse_de_depart_souvre_la_journee():
    assert dom.vitesses_par_heure(25, [], "2026-09-08") == {8: 25}


def test_un_changement_en_cours_de_journee_sinscrit_a_son_heure():
    """L'exemple du service : à 16 h la vitesse passe de 25 à 15."""
    reglages = [_reglage("2026-09-08T16:00", 15)]
    assert dom.vitesses_par_heure(25, reglages, "2026-09-08") == {8: 25, 16: 15}


def test_plusieurs_changements_dans_la_meme_journee():
    reglages = [
        _reglage("2026-09-08T12:00", 20),
        _reglage("2026-09-08T16:00", 15),
        _reglage("2026-09-08T22:00", 10),
    ]
    assert dom.vitesses_par_heure(25, reglages, "2026-09-08") == {
        8: 25, 12: 20, 16: 15, 22: 10
    }


def test_un_reglage_anterieur_fixe_la_vitesse_douverture():
    """Descendue à 15 hier soir, la seringue ouvre la journée à 15 — pas à la
    vitesse prescrite au départ, qui date de trois jours."""
    reglages = [_reglage("2026-09-07T22:00", 15)]
    assert dom.vitesses_par_heure(25, reglages, "2026-09-08") == {8: 15}


def test_un_reglage_a_huit_heures_pile_prime_sur_la_vitesse_douverture():
    reglages = [_reglage("2026-09-08T08:00", 18)]
    assert dom.vitesses_par_heure(25, reglages, "2026-09-08") == {8: 18}


def test_un_reglage_de_la_nuit_tombe_dans_la_journee_precedente():
    """2 h du matin le 9 appartient à la feuille du 8 : c'est la nuit de la
    garde qui a ouvert cette feuille-là."""
    reglages = [_reglage("2026-09-09T02:00", 12)]
    assert dom.vitesses_par_heure(25, reglages, "2026-09-08") == {8: 25, 2: 12}
    # Et cette même nuit ne réapparaît pas sur la feuille du lendemain ; elle
    # y fixe seulement la vitesse d'ouverture.
    assert dom.vitesses_par_heure(25, reglages, "2026-09-09") == {8: 12}


def test_un_reglage_dun_autre_jour_ne_deborde_pas():
    reglages = [_reglage("2026-09-10T16:00", 5)]
    assert dom.vitesses_par_heure(25, reglages, "2026-09-08") == {8: 25}


def test_sans_vitesse_ni_reglage_il_ny_a_rien_a_ecrire():
    """Une ligne qui ne coule pas ne doit pas se voir attribuer une case."""
    assert dom.vitesses_par_heure(None, [], "2026-09-08") == {}


# --- l'enregistrement des réglages -----------------------------------------

def test_regler_conserve_lhistorique(base):
    """Une vitesse réglée reste : c'est ce qui permet de relire la conduite
    d'une sédation sur plusieurs jours."""
    sid = _sejour(base)
    ligne = prescriptions.ajouter_ligne(
        base, sejour_id=sid, voie="PSE", produit="Noradrénaline",
        date_debut="2026-09-08", vitesse=25, rythme="continu",
    )
    vitesses.regler(base, cible=vitesses.LIGNE, cible_id=ligne,
                    date_heure="2026-09-08T16:00", vitesse=15)
    vitesses.regler(base, cible=vitesses.LIGNE, cible_id=ligne,
                    date_heure="2026-09-08T22:00", vitesse=10)
    notes = vitesses.reglages(base, vitesses.LIGNE, ligne)
    assert [n["vitesse"] for n in notes] == [15, 10]


def test_par_heure_relit_les_reglages_dune_ligne(base):
    sid = _sejour(base)
    ligne = prescriptions.ajouter_ligne(
        base, sejour_id=sid, voie="PSE", produit="Noradrénaline",
        date_debut="2026-09-08", vitesse=25, rythme="continu",
    )
    vitesses.regler(base, cible=vitesses.LIGNE, cible_id=ligne,
                    date_heure="2026-09-08T16:00", vitesse=15)
    assert vitesses.par_heure(base, vitesses.LIGNE, ligne, 25, "2026-09-08") == {8: 25, 16: 15}


def test_annuler_retire_un_reglage_sans_leffacer(base):
    sid = _sejour(base)
    ligne = prescriptions.ajouter_ligne(
        base, sejour_id=sid, voie="PSE", produit="Noradrénaline",
        date_debut="2026-09-08", vitesse=25, rythme="continu",
    )
    rid = vitesses.regler(base, cible=vitesses.LIGNE, cible_id=ligne,
                          date_heure="2026-09-08T16:00", vitesse=15)
    vitesses.annuler(base, rid)
    assert vitesses.reglages(base, vitesses.LIGNE, ligne) == []
    reste = base.une_ligne("SELECT supprime FROM vitesse_reglage WHERE id = ?", (rid,))
    assert reste["supprime"] == 1


def test_les_reglages_du_sejour_couvrent_lignes_et_dispositifs(base):
    """La sédation est posée comme dispositif, la noradrénaline prescrite en
    ligne : les deux coulent, les deux se règlent, une seule lecture."""
    sid = _sejour(base)
    ligne = prescriptions.ajouter_ligne(
        base, sejour_id=sid, voie="PSE", produit="Noradrénaline",
        date_debut="2026-09-08", vitesse=25, rythme="continu",
    )
    sedation = dispositifs.poser(base, sejour_id=sid, type_="sedation",
                                 date_pose="2026-09-08",
                                 details={"molecules": "Midazolam", "vitesse": 6})
    vitesses.regler(base, cible=vitesses.LIGNE, cible_id=ligne,
                    date_heure="2026-09-08T16:00", vitesse=15)
    vitesses.regler(base, cible=vitesses.DISPOSITIF, cible_id=sedation,
                    date_heure="2026-09-08T14:00", vitesse=4)

    par_cible = vitesses.reglages_du_sejour(base, sid)
    assert [r["vitesse"] for r in par_cible[ligne]] == [15]
    # La pose ouvre l'historique du dispositif à sa vitesse de départ : sans
    # ce premier point, la vitesse courante tiendrait aussi lieu de vitesse
    # d'origine, et redescendre une sédation réécrirait les jours passés.
    assert [r["vitesse"] for r in par_cible[sedation]] == [6, 4]


def test_les_reglages_dun_autre_sejour_ne_se_melangent_pas(base):
    sid_a = _sejour(base)
    pid_b = sejours.creer_patient(base, matricule="M2", nom_affichage="Autre",
                                  date_naissance=None)
    sid_b = sejours.creer_sejour(base, patient_id=pid_b, date_admission="2026-09-06",
                                 lit_admission=2)
    ligne_b = prescriptions.ajouter_ligne(
        base, sejour_id=sid_b, voie="PSE", produit="Noradrénaline",
        date_debut="2026-09-08", vitesse=30, rythme="continu",
    )
    vitesses.regler(base, cible=vitesses.LIGNE, cible_id=ligne_b,
                    date_heure="2026-09-08T16:00", vitesse=20)
    assert vitesses.reglages_du_sejour(base, sid_a) == {}
    assert list(vitesses.reglages_du_sejour(base, sid_b)) == [ligne_b]


# --- la vitesse courante d'un dispositif ne réécrit pas les jours passés ----

def test_regler_une_sedation_met_a_jour_sa_vitesse_courante(base):
    """La carte du dispositif et la pastille du bandeau annoncent la vitesse
    du moment : deux chiffres différents pour la même pompe, c'est exactement
    ce qu'une feuille de réanimation doit éviter."""
    sid = _sejour(base)
    did = dispositifs.poser(base, sejour_id=sid, type_="sedation",
                            date_pose="2026-09-07",
                            details={"molecules": "Midazolam", "vitesse": 6})
    dispositifs.regler_vitesse(base, did, date_heure="2026-09-08T14:00", vitesse=4)
    etat = next(e for e in dispositifs.etats(base, sid, "2026-09-08") if e.en_place)
    assert etat.details["vitesse"] == 4
    assert "4 cc/h" in etat.texte


def test_baisser_une_sedation_ne_reecrit_pas_la_feuille_de_la_veille(base):
    """Le défaut qu'il fallait éviter : la vitesse courante servait aussi de
    vitesse d'origine, et descendre la sédation aujourd'hui faisait afficher
    la nouvelle valeur sur toutes les feuilles précédentes."""
    sid = _sejour(base)
    did = dispositifs.poser(base, sejour_id=sid, type_="sedation",
                            date_pose="2026-09-07",
                            details={"molecules": "Midazolam", "vitesse": 6})
    dispositifs.regler_vitesse(base, did, date_heure="2026-09-08T14:00", vitesse=4)

    courante = next(e for e in dispositifs.etats(base, sid, "2026-09-08")
                    if e.en_place).details["vitesse"]
    # Hier : 6 toute la journée. Aujourd'hui : 6 puis 4 à 14 h.
    assert vitesses.par_heure(base, vitesses.DISPOSITIF, did, courante, "2026-09-07") == {8: 6}
    assert vitesses.par_heure(base, vitesses.DISPOSITIF, did, courante, "2026-09-08") == {8: 6, 14: 4}


def test_un_reglage_antidate_ne_defait_pas_celui_du_jour(base):
    """C'est la dernière vitesse dans le temps qui devient la courante, pas la
    dernière saisie."""
    sid = _sejour(base)
    did = dispositifs.poser(base, sejour_id=sid, type_="sedation",
                            date_pose="2026-09-07",
                            details={"molecules": "Midazolam", "vitesse": 6})
    dispositifs.regler_vitesse(base, did, date_heure="2026-09-08T14:00", vitesse=4)
    dispositifs.regler_vitesse(base, did, date_heure="2026-09-08T09:00", vitesse=5)
    etat = next(e for e in dispositifs.etats(base, sid, "2026-09-08") if e.en_place)
    assert etat.details["vitesse"] == 4


def test_un_dispositif_sans_vitesse_nouvre_aucun_historique(base):
    """Une intubation ne coule pas : rien à noter."""
    sid = _sejour(base)
    did = dispositifs.poser(base, sejour_id=sid, type_="intubation",
                            date_pose="2026-09-07", details={"taille_sonde": 7.5})
    assert vitesses.reglages(base, vitesses.DISPOSITIF, did) == []
