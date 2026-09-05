"""Export pseudonymisé (bloc 13).

Le test le plus important du fichier est le premier : qu'aucun identifiant
direct ne se retrouve dans les fichiers produits. C'est la promesse faite au
patient, et elle doit être vérifiée mécaniquement, pas relue.
"""

import csv
import json

from rea.services import bilans, dispositifs, evolution, export, sejours


def _dossier_complet(base):
    pid = sejours.creer_patient(
        base, matricule="2026-04187", nom_affichage="K. Abdelaziz",
        date_naissance="1978-03-14", sexe="M",
    )
    sid = sejours.creer_sejour(
        base, patient_id=pid, date_admission="2026-09-01", lit_admission=3,
        poids_kg=70, taille_cm=175, provenance_type="urgences",
    )
    bilans.enregistrer_resultats(
        base, sejour_id=sid, date_heure="2026-09-01T06:00", valeurs={"k": 4.1}
    )
    evolution.enregistrer(
        base, sid, "2026-09-01",
        {"plan_neurologique": "Patient vu par le Dr Untel, chambre 12."},
    )
    dispositifs.poser(base, sejour_id=sid, type_="intubation", date_pose="2026-09-01")
    return pid, sid


def _tout_le_texte(dossier):
    return "\n".join(
        f.read_text(encoding="utf-8") for f in dossier.iterdir() if f.is_file()
    )


def test_aucun_identifiant_direct_dans_l_export(base, tmp_path):
    _dossier_complet(base)
    dossier = export.exporter(base, dossier=tmp_path / "export")
    texte = _tout_le_texte(dossier)
    assert "2026-04187" not in texte      # matricule
    assert "Abdelaziz" not in texte       # nom affiché
    assert "1978-03-14" not in texte      # date de naissance


def test_l_age_remplace_la_date_de_naissance(base, tmp_path):
    _dossier_complet(base)
    dossier = export.exporter(base, dossier=tmp_path / "export")
    with (dossier / "sejour.csv").open(encoding="utf-8") as f:
        ligne = next(csv.DictReader(f, delimiter=";"))
    assert ligne["age_admission"] == "48"


def test_le_texte_libre_est_retire_par_defaut(base, tmp_path):
    """Un commentaire d'évolution peut contenir un nom ou un lieu."""
    _dossier_complet(base)
    dossier = export.exporter(base, dossier=tmp_path / "export")
    assert "Dr Untel" not in _tout_le_texte(dossier)

    avec = export.exporter(base, dossier=tmp_path / "export2", avec_texte_libre=True)
    assert "Dr Untel" in _tout_le_texte(avec)
    manifeste = json.loads((avec / "manifeste.json").read_text(encoding="utf-8"))
    assert manifeste["texte_libre_inclus"] is True
    assert "TEXTE LIBRE INCLUS" in manifeste["avertissements"][0]


def test_l_identifiant_d_etude_est_exporte_et_stable(base, tmp_path):
    pid, _sid = _dossier_complet(base)
    attendu = base.une_ligne(
        "SELECT identifiant_etude FROM patient WHERE id = ?", (pid,)
    )["identifiant_etude"]
    dossier = export.exporter(base, dossier=tmp_path / "export")
    assert attendu in (dossier / "patient.csv").read_text(encoding="utf-8")


def test_les_valeurs_manquantes_sont_codees(base, tmp_path):
    _dossier_complet(base)
    dossier = export.exporter(base, dossier=tmp_path / "export")
    assert export.NON_RENSEIGNE in (dossier / "sejour.csv").read_text(encoding="utf-8")


def test_le_dictionnaire_decrit_chaque_colonne_exportee(base, tmp_path):
    _dossier_complet(base)
    dossier = export.exporter(base, dossier=tmp_path / "export")
    with (dossier / "dictionnaire.csv").open(encoding="utf-8") as f:
        lignes = list(csv.DictReader(f, delimiter=";"))
    decrites = {(l["table"], l["colonne"]) for l in lignes}
    with (dossier / "sejour.csv").open(encoding="utf-8") as f:
        colonnes = next(csv.reader(f, delimiter=";"))
    for colonne in colonnes:
        if colonne == "age_admission":
            continue
        assert ("sejour", colonne) in decrites


def test_le_manifeste_porte_les_versions(base, tmp_path):
    _dossier_complet(base)
    dossier = export.exporter(base, dossier=tmp_path / "export", motif="test")
    manifeste = json.loads((dossier / "manifeste.json").read_text(encoding="utf-8"))
    assert manifeste["versions_referentiels"]["provenances"]
    assert manifeste["versions_regles"]
    assert manifeste["nb_sejours"] == 1
    assert manifeste["loinc_valide"] is False


def test_l_export_restreint_a_une_cohorte(base, tmp_path):
    _pid, sid = _dossier_complet(base)
    autre = sejours.creer_patient(
        base, matricule="X", nom_affichage="Y", date_naissance=None
    )
    sejours.creer_sejour(
        base, patient_id=autre, date_admission="2026-09-02", lit_admission=4
    )
    dossier = export.exporter(base, dossier=tmp_path / "export", sejour_ids=[sid])
    manifeste = json.loads((dossier / "manifeste.json").read_text(encoding="utf-8"))
    assert manifeste["nb_sejours"] == 1


def test_l_export_est_journalise(base, tmp_path):
    _dossier_complet(base)
    export.exporter(base, dossier=tmp_path / "export")
    assert "export" in [j["action"] for j in base.journal()]


def test_l_export_laisse_une_seule_trace_pas_deux(base, tmp_path):
    """`inserer("journal", ...)` journaliserait sa propre écriture en plus :
    une trace fantôme « table_cible=journal » à côté de la vraie."""
    _dossier_complet(base)
    avant = len(base.journal())
    export.exporter(base, dossier=tmp_path / "export")
    apres = base.journal()
    assert len(apres) == avant + 1
    assert not any(j["table_cible"] == "journal" for j in apres)


def test_le_gel_garde_une_copie_et_se_journalise(base):
    _dossier_complet(base)
    avant = len(base.journal())
    gel = export.geler(base, motif="étude PAVM")
    from pathlib import Path

    assert Path(gel["fichier"]).exists()
    assert gel["nb_sejours"] == 1
    apres = base.journal()
    assert len(apres) == avant + 1, "le gel ne doit laisser qu'une seule trace"
    assert "gel" in [j["action"] for j in base.journal()]


def test_les_colonnes_de_texte_libre_existent_vraiment(base):
    """Un nom de colonne erroné dans la liste des textes libres ne se voit
    pas : la colonne continue simplement d'être exportée. Ce test rattrape
    la faute de frappe qui ferait fuiter un commentaire."""
    for table, colonnes in list(export.TEXTE_LIBRE.items()) + list(
        export.IDENTIFIANTS_DIRECTS.items()
    ):
        reelles = {l["name"] for l in base.requete(f"PRAGMA table_info({table})")}
        assert reelles, f"table inconnue : {table}"
        for colonne in colonnes:
            assert colonne in reelles, f"{table}.{colonne} n'existe pas"
