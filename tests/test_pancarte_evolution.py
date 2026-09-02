from rea.services import evolution, pancarte, prescriptions as pr, sejours


def _sejour_type(base):
    pid = sejours.creer_patient(
        base, matricule="2026-04187", nom_affichage="K. Abdelaziz", date_naissance="1978-03-14"
    )
    sid = sejours.creer_sejour(
        base, patient_id=pid, date_admission="2026-08-28", lit_admission=1, traumatique=True
    )
    return pid, sid


def test_impression_produit_un_snapshot_versionne(base):
    pid, sid = _sejour_type(base)
    pr.ajouter_ligne(
        base, sejour_id=sid, voie="IV", produit="Tienam", dose=1, unite="g",
        rythme="x3/j", date_debut="2026-08-28",
    )
    premiere = pancarte.imprimer(base, sid, "2026-09-01")
    assert premiere["version"] == 1
    deuxieme = pancarte.imprimer(base, sid, "2026-09-01")
    assert deuxieme["version"] == 2
    # Le premier snapshot reste inchangé — immuabilité (règle de conception 5, exception).
    snapshots = pancarte.snapshots_du_sejour(base, sid)
    assert len(snapshots) == 2


def test_pancarte_signale_les_allergies(base):
    pid, sid = _sejour_type(base)
    sejours.ajouter_antecedent(
        base, patient_id=pid, categorie="allergie", libelle="Pénicilline", statut="present"
    )
    html = pancarte.generer_html(base, sid, "2026-09-01")
    assert "ALLERGIE" in html
    assert "Pénicilline" in html


def test_pancarte_barre_une_ligne_arretee(base):
    pid, sid = _sejour_type(base)
    ligne_id = pr.ajouter_ligne(
        base, sejour_id=sid, voie="PO", produit="Kardégic", dose=160, unite="mg",
        rythme="x1/j", date_debut="2026-08-28",
    )
    pr.arreter_ligne(base, ligne_id, date_arret="2026-08-30")
    html = pancarte.generer_html(base, sid, "2026-08-30")
    assert 'class="arretee"' in html


def test_evolution_texte_reprend_le_traitement_actif(base):
    pid, sid = _sejour_type(base)
    pr.ajouter_ligne(
        base, sejour_id=sid, voie="IV", produit="Tienam", dose=1, unite="g",
        rythme="x3/j", date_debut="2026-08-28",
    )
    texte = evolution.texte_genere(base, sid, "2026-09-01")
    assert "Tienam 1g x3/j" in texte
    assert "Sous le traitement :" in texte
    assert "Conduite :" in texte


def test_evolution_conserve_les_plans_saisis(base):
    pid, sid = _sejour_type(base)
    evolution.enregistrer(base, sid, "2026-09-01", {"plan_neurologique": "RASS -4"})
    texte = evolution.texte_genere(base, sid, "2026-09-01")
    assert "RASS -4" in texte


def test_inserer_sur_table_sans_cree_le_ne_leve_pas(base):
    # Non-régression : pancarte_snapshot et journal n'ont pas de colonne
    # cree_le ; inserer() ne doit pas tenter de l'y écrire.
    id_ = base.inserer("sauvegarde", {"date_heure": "2026-09-01T00:00:00", "fichier": "x", "motif": "test"})
    assert id_
