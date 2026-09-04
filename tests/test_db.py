from rea.domaine.dates import jour_hospitalisation


def test_inserer_et_relire(base):
    uid = base.inserer("utilisateur", {"nom": "Dr Test", "role": "interne"})
    ligne = base.une_ligne("SELECT * FROM utilisateur WHERE id = ?", (uid,))
    assert ligne["nom"] == "Dr Test"
    assert ligne["cree_le"]


def test_mettre_a_jour_journalise(base):
    uid = base.inserer("utilisateur", {"nom": "Dr Test", "role": "interne"})
    base.mettre_a_jour("utilisateur", uid, {"actif": 0}, utilisateur_id=uid)
    actions = [j["action"] for j in base.requete("SELECT action FROM journal")]
    assert actions == ["creation", "modification"]


def test_supprimer_logiquement_ne_retire_pas_la_ligne(base):
    uid = base.inserer("utilisateur", {"nom": "Dr Test", "role": "interne"})
    base.supprimer_logiquement("utilisateur", uid)
    ligne = base.une_ligne("SELECT * FROM utilisateur WHERE id = ?", (uid,))
    assert ligne is not None
    assert ligne["supprime"] == 1


def test_sauvegarde_produit_un_fichier(base):
    chemin = base.sauvegarder(motif="test")
    assert chemin.exists()
    assert chemin.stat().st_size > 0


def test_admission_puis_lit_occupe(base):
    from rea.services import sejours, lits

    pid = sejours.creer_patient(
        base, matricule="M1", nom_affichage="K. Abdelaziz", date_naissance="1978-03-14"
    )
    sid = sejours.creer_sejour(
        base, patient_id=pid, date_admission="2026-08-28", lit_admission=1
    )
    etat = lits.etat_des_lits(base)
    lit1 = next(l for l in etat if l["lit"] == 1)
    assert lit1["occupe"] is True
    assert lit1["sejour_id"] == sid
    assert lit1["jour_hospitalisation"] == jour_hospitalisation("2026-08-28")


def test_polytraumatise_calcule_automatiquement(base):
    from rea.services import sejours

    pid = sejours.creer_patient(base, matricule="M2", nom_affichage="B. Test", date_naissance=None)
    sid = sejours.creer_sejour(
        base, patient_id=pid, date_admission="2026-09-01", lit_admission=2, traumatique=True
    )
    sejours.definir_regions_traumatiques(base, sid, ["cranien"])
    assert sejours.est_polytraumatise(base, sid) is False
    sejours.definir_regions_traumatiques(base, sid, ["cranien", "thoracique"])
    assert sejours.est_polytraumatise(base, sid) is True


def test_cloture_sejour_libere_le_lit(base):
    from rea.services import sejours, lits

    pid = sejours.creer_patient(base, matricule="M3", nom_affichage="X. Test", date_naissance=None)
    sid = sejours.creer_sejour(base, patient_id=pid, date_admission="2026-09-01", lit_admission=3)
    sejours.cloturer_sejour(
        base, sid, date_heure_sortie="2026-09-05T10:00", mode_sortie="domicile"
    )
    etat = lits.etat_des_lits(base)
    lit3 = next(l for l in etat if l["lit"] == 3)
    assert lit3["occupe"] is False


# -- restauration (feuille de route, critère de fin du bloc 0) --------------

def test_restaurer_ramene_l_etat_de_la_sauvegarde(base):
    """« Une sauvegarde jamais restaurée n'existe pas. »"""
    base.inserer("utilisateur", {"nom": "Avant", "role": "interne"})
    sauvegarde = base.sauvegarder(motif="test")
    base.inserer("utilisateur", {"nom": "Après", "role": "interne"})
    assert len(base.requete("SELECT id FROM utilisateur")) == 2

    base.restaurer(sauvegarde)

    noms = [u["nom"] for u in base.requete("SELECT nom FROM utilisateur")]
    assert noms == ["Avant"]


def test_restaurer_sauvegarde_d_abord_l_etat_courant(base):
    """Restaurer par erreur ne doit jamais être irréversible."""
    base.inserer("utilisateur", {"nom": "Avant", "role": "interne"})
    sauvegarde = base.sauvegarder(motif="test")
    base.inserer("utilisateur", {"nom": "Après", "role": "interne"})

    filet = base.restaurer(sauvegarde)
    assert filet.exists()

    base.restaurer(filet)
    noms = sorted(u["nom"] for u in base.requete("SELECT nom FROM utilisateur"))
    assert noms == ["Après", "Avant"]


def test_restaurer_journalise(base):
    sauvegarde = base.sauvegarder(motif="test")
    base.restaurer(sauvegarde)
    actions = [j["action"] for j in base.journal()]
    assert "restauration" in actions


def test_restaurer_une_sauvegarde_absente_leve(base, tmp_path):
    import pytest

    with pytest.raises(FileNotFoundError):
        base.restaurer(tmp_path / "inexistant.db")


def test_journal_lisible_avec_le_nom_de_l_utilisateur(base):
    from rea.services import sejours

    uid = base.inserer("utilisateur", {"nom": "Dr Test", "role": "interne"})
    sejours.creer_patient(
        base, matricule="M9", nom_affichage="X", date_naissance=None,
        utilisateur_id=uid,
    )
    lignes = base.journal(table="patient")
    assert lignes and lignes[0]["utilisateur_nom"] == "Dr Test"


def test_sauvegardes_disponibles_les_plus_recentes_d_abord(base):
    base.sauvegarder(motif="un")
    base.sauvegarder(motif="deux")
    dispo = base.sauvegardes_disponibles()
    assert len(dispo) >= 2
    assert dispo[0]["date"] >= dispo[1]["date"]
