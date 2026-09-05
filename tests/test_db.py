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


# -- montée de version d'une base existante --------------------------------

def test_une_base_ancienne_recupere_les_colonnes_ajoutees(base, monkeypatch, tmp_path):
    """`CREATE TABLE IF NOT EXISTS` ne touche pas à une table déjà créée.

    Sans rattrapage, une base saisie par une version antérieure du logiciel
    n'a pas les colonnes ajoutées depuis, et l'écran patient plante au premier
    affichage — c'est exactement ce qui s'est produit sur le poste de test.
    """
    import sqlite3
    import uuid

    from rea.db import Base, maintenant

    # Une base « d'avant » : le séjour n'a que ses colonnes d'origine.
    chemin = tmp_path / "ancienne.db"
    vieille = sqlite3.connect(str(chemin))
    vieille.executescript(
        "CREATE TABLE meta (cle TEXT PRIMARY KEY, valeur TEXT);"
        "CREATE TABLE patient (id TEXT PRIMARY KEY, matricule TEXT, "
        "nom_affichage TEXT, identifiant_etude TEXT, cree_le TEXT);"
        "CREATE TABLE sejour (id TEXT PRIMARY KEY, patient_id TEXT, "
        "date_admission TEXT, lit_admission INTEGER, cree_le TEXT);"
    )
    pid, sid = str(uuid.uuid4()), str(uuid.uuid4())
    vieille.execute(
        "INSERT INTO patient VALUES (?,?,?,?,?)",
        (pid, "M1", "K. A.", "ETU-1", maintenant()),
    )
    vieille.execute(
        "INSERT INTO sejour VALUES (?,?,?,?,?)",
        (sid, pid, "2026-09-01", 1, maintenant()),
    )
    vieille.commit()
    vieille.close()

    rouverte = Base(chemin)
    try:
        colonnes = rouverte._colonnes("sejour")
        for attendue in ("poids_kg", "taille_cm", "creatinine_base",
                         "type_admission", "maladie_chronique_igs2", "code_icd10"):
            assert attendue in colonnes, f"{attendue} non rattrapée"
        # La ligne saisie avant existe toujours, et les nouvelles colonnes y
        # valent « non renseigné » — pas zéro.
        sejour = rouverte.une_ligne("SELECT * FROM sejour WHERE id = ?", (sid,))
        assert sejour["poids_kg"] is None
    finally:
        rouverte.arreter_sauvegardes_periodiques()
        rouverte.connexion.close()


# -- correction d'une admission (pas une suppression, une mise à jour tracée) -

def test_modifier_identite_corrige_sans_recreer(base):
    from rea.services import sejours

    pid = sejours.creer_patient(
        base, matricule="M1", nom_affichage="K. Abdelaziz",
        date_naissance="1980-01-01", sexe="M",
    )
    sejours.modifier_identite(
        base, pid, matricule="M1-corrige", nom_affichage="K. Abdelaziz",
        date_naissance="1978-01-01", sexe="M", groupe_sanguin="O+",
    )
    patient = base.une_ligne("SELECT * FROM patient WHERE id = ?", (pid,))
    assert patient["id"] == pid                    # même ligne, pas une nouvelle
    assert patient["matricule"] == "M1-corrige"
    assert patient["date_naissance"] == "1978-01-01"
    assert patient["groupe_sanguin"] == "O+"
    actions = [j["action"] for j in base.journal(table="patient")]
    assert "correction" in actions


def test_modifier_admission_bascule_de_non_traumatique_vers_traumatique(base):
    """Le motif coché du mauvais côté à l'admission doit pouvoir être corrigé
    sans laisser les deux catégories peuplées en même temps."""
    from rea.services import sejours

    pid = sejours.creer_patient(base, matricule="M2", nom_affichage="X",
                                date_naissance="1980-01-01")
    sid = sejours.creer_sejour(base, patient_id=pid, date_admission="2026-09-01",
                               lit_admission=1, traumatique=False)
    sejours.definir_motifs(base, sid, motif_principal="choc_septique")
    assert sejours.motifs_du_sejour(base, sid)

    sejours.modifier_admission(
        base, sid, date_admission="2026-09-01", provenance_type="urgences",
        provenance_detail=None, poids_kg=70, taille_cm=175, creatinine_base=None,
        type_admission="medicale", maladie_chronique_igs2="aucune",
        traumatique=True, regions_traumatiques_choisies=["cranien", "thoracique"],
        mecanisme="avp",
    )
    sejour = base.une_ligne("SELECT * FROM sejour WHERE id = ?", (sid,))
    assert sejour["traumatique"] == 1
    assert sejour["poids_kg"] == 70
    assert set(sejours.regions_traumatiques(base, sid)) == {"cranien", "thoracique"}
    assert sejours.motifs_du_sejour(base, sid) == []      # l'ancien motif ne traîne pas


def test_modifier_admission_bascule_de_traumatique_vers_non_traumatique(base):
    from rea.services import sejours

    pid = sejours.creer_patient(base, matricule="M3", nom_affichage="Y",
                                date_naissance="1980-01-01")
    sid = sejours.creer_sejour(base, patient_id=pid, date_admission="2026-09-01",
                               lit_admission=2, traumatique=True, mecanisme="avp")
    sejours.definir_regions_traumatiques(base, sid, ["thoracique"])

    sejours.modifier_admission(
        base, sid, date_admission="2026-09-01", provenance_type="urgences",
        provenance_detail=None, poids_kg=None, taille_cm=None, creatinine_base=None,
        type_admission=None, maladie_chronique_igs2=None,
        traumatique=False, motif_principal="choc_septique",
    )
    assert sejours.regions_traumatiques(base, sid) == []
    assert [m["code"] for m in sejours.motifs_du_sejour(base, sid)] == ["choc_septique"]


def test_modifier_admission_ne_touche_pas_au_lit(base):
    """Changer de lit est un transfert, pas une correction : cette fonction ne
    doit pas y toucher."""
    from rea.services import sejours

    pid = sejours.creer_patient(base, matricule="M4", nom_affichage="Z",
                                date_naissance="1980-01-01")
    sid = sejours.creer_sejour(base, patient_id=pid, date_admission="2026-09-01",
                               lit_admission=5, traumatique=False)
    sejours.definir_motifs(base, sid, motif_principal="choc_septique")
    sejours.modifier_admission(
        base, sid, date_admission="2026-09-02", provenance_type="bloc",
        provenance_detail=None, poids_kg=80, taille_cm=180, creatinine_base=70,
        type_admission="chirurgie_programmee", maladie_chronique_igs2="aucune",
        traumatique=False, motif_principal="choc_septique",
    )
    sejour = base.une_ligne("SELECT * FROM sejour WHERE id = ?", (sid,))
    assert sejour["lit_admission"] == 5
    assert sejour["date_admission"] == "2026-09-02"
