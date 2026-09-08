"""Éléments fixes des quatre plans, et escarres."""

from rea.services import dispositifs, evolution as ev, prescriptions as pr, sejours


def _sejour(base):
    pid = sejours.creer_patient(
        base, matricule="M1", nom_affichage="Test", date_naissance="1978-03-14", sexe="M"
    )
    return sejours.creer_sejour(
        base, patient_id=pid, date_admission="2026-08-29", lit_admission=1, poids_kg=70
    )


def test_elements_enregistres_et_relus(base):
    sid = _sejour(base)
    ev.enregistrer_elements(base, sid, "2026-09-03", {"fc": 92, "temperature": 38.6})
    elements = ev.elements_du_jour(base, sid, "2026-09-03")
    assert elements["fc"] == 92
    assert elements["temperature"] == 38.6


def test_element_efface_quand_le_champ_est_vide(base):
    sid = _sejour(base)
    ev.enregistrer_elements(base, sid, "2026-09-03", {"fc": 92})
    ev.enregistrer_elements(base, sid, "2026-09-03", {"fc": None})
    assert "fc" not in ev.elements_du_jour(base, sid, "2026-09-03")


def test_non_renseigne_nest_pas_une_mesure(base):
    sid = _sejour(base)
    ev.enregistrer_elements(base, sid, "2026-09-03", {"signes_choc": "non_renseigne"})
    assert "signes_choc" not in ev.elements_du_jour(base, sid, "2026-09-03")


def test_elements_dun_autre_jour_ne_remontent_pas(base):
    sid = _sejour(base)
    ev.enregistrer_elements(base, sid, "2026-09-02", {"fc": 92})
    assert ev.elements_du_jour(base, sid, "2026-09-03") == {}


def test_cinetique_dun_element(base):
    sid = _sejour(base)
    ev.enregistrer_elements(base, sid, "2026-09-02", {"temperature": 38.6})
    ev.enregistrer_elements(base, sid, "2026-09-03", {"temperature": 37.2})
    historique = ev.historique_element(base, sid, "temperature")
    assert [h["valeur_num"] for h in historique] == [38.6, 37.2]


def test_pression_arterielle_ecrite_en_une_seule_fois(base):
    """« PA 105/58 (74) mmHg » : la PAM entre parenthèses est calculée, pas
    saisie — la case a disparu de l'écran."""
    sid = _sejour(base)
    ev.enregistrer_elements(base, sid, "2026-09-03", {"pas": 105, "pad": 58})
    texte = ev.texte_genere(base, sid, "2026-09-03")
    assert "PA 105/58 (74) mmHg" in texte
    assert "PA systolique" not in texte


def test_la_pam_ne_sort_pas_seule_sans_pression_diastolique(base):
    """Une PAM sans la PAD dont elle se déduit serait une valeur inventée."""
    sid = _sejour(base)
    ev.enregistrer_elements(base, sid, "2026-09-03", {"pas": 105})
    texte = ev.texte_genere(base, sid, "2026-09-03")
    assert "(" not in texte.split("PA systolique")[1].split("·")[0]


def test_la_case_pam_nexiste_plus(base):
    """Trois cases dont une déductible des deux autres, c'est une incohérence
    qui attend son tour : la PAM saisie n'est plus enregistrable."""
    sid = _sejour(base)
    ev.enregistrer_elements(base, sid, "2026-09-03", {"pas": 105, "pad": 58, "pam": 40})
    assert "pam" not in ev.elements_du_jour(base, sid, "2026-09-03")
    assert "(74)" in ev.texte_genere(base, sid, "2026-09-03")


def test_temperature_en_virgule_francaise(base):
    sid = _sejour(base)
    ev.enregistrer_elements(base, sid, "2026-09-03", {"temperature": 38.6})
    assert "38,6 °C" in ev.texte_genere(base, sid, "2026-09-03")


def test_arret_sedation_apparait_dans_le_plan_neurologique(base):
    # La demande explicite : « on ajoute des éléments fixes comme J4 arrêt sédation ».
    sid = _sejour(base)
    d = dispositifs.poser(base, sejour_id=sid, type_="sedation", date_pose="2026-08-29")
    dispositifs.retirer(base, d, date_retrait="2026-08-30")
    texte = ev.texte_genere(base, sid, "2026-09-03")
    lignes = texte.split("\n")
    index_neuro = lignes.index("Sur le plan Neurologique :")
    assert "Arrêt sédation J4" in lignes[index_neuro + 1]


def test_intubation_apparait_dans_le_plan_respiratoire(base):
    sid = _sejour(base)
    dispositifs.poser(base, sejour_id=sid, type_="intubation", date_pose="2026-08-30")
    lignes = ev.texte_genere(base, sid, "2026-09-03").split("\n")
    index = lignes.index("Sur le plan respiratoire :")
    assert "Intubé J5" in lignes[index + 1]


def test_amines_apparaissent_dans_le_plan_hemodynamique(base):
    sid = _sejour(base)
    pr.ajouter_ligne(
        base, sejour_id=sid, voie="PSE", produit="Noradrénaline", vitesse=2,
        rythme="continu", date_debut="2026-08-29",
    )
    lignes = ev.texte_genere(base, sid, "2026-09-03").split("\n")
    index = lignes.index("Sur le plan hémodynamique :")
    assert "Noradrénaline" in lignes[index + 1]


def test_antibiotiques_apparaissent_dans_le_plan_infectieux(base):
    sid = _sejour(base)
    pr.ajouter_ligne(
        base, sejour_id=sid, voie="IV", produit="Tienam", dose=1, unite="g",
        rythme="x3/j", date_debut="2026-08-29", duree_prevue_jours=7,
    )
    lignes = ev.texte_genere(base, sid, "2026-09-03").split("\n")
    index = lignes.index("Sur le plan Infectieux :")
    assert "Tienam" in lignes[index + 1]


def test_un_dispositif_nest_jamais_ecrit_deux_fois(base):
    # L'intubation est reprise dans le plan respiratoire : elle ne doit plus
    # figurer dans la ligne de tête des dispositifs.
    sid = _sejour(base)
    dispositifs.poser(base, sejour_id=sid, type_="intubation", date_pose="2026-08-30")
    dispositifs.poser(base, sejour_id=sid, type_="sng", date_pose="2026-08-30")
    texte = ev.texte_genere(base, sid, "2026-09-03")
    assert texte.count("Intubé J5") == 1
    assert "SNG J5" in texte


# --- escarres -------------------------------------------------------------

def test_escarre_apparait_dans_le_plan_infectieux_avec_son_grade(base):
    sid = _sejour(base)
    ev.ajouter_escarre(
        base, sejour_id=sid, localisation="Sacrum", grade=2, date_constat="2026-09-01"
    )
    texte = ev.texte_genere(base, sid, "2026-09-03")
    assert "Escarres : sacrum grade 2" in texte


def test_escarre_guerie_ne_figure_plus(base):
    sid = _sejour(base)
    eid = ev.ajouter_escarre(
        base, sejour_id=sid, localisation="Sacrum", grade=2, date_constat="2026-09-01"
    )
    ev.modifier_escarre(base, eid, {"date_guerison": "2026-09-02"})
    assert "Escarres" not in ev.texte_genere(base, sid, "2026-09-03")
    # Mais elle reste dans l'historique du séjour.
    assert len(ev.escarres(base, sid)) == 1
