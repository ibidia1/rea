"""Relecture des fiches déjà imprimées (instantanés figés, jour par jour)."""

from rea.services import pancarte, sejours


def _sejour(base, matricule, lit, date_admission="2026-09-01"):
    pid = sejours.creer_patient(base, matricule=matricule, nom_affichage=matricule,
                                date_naissance="1980-01-01")
    return sejours.creer_sejour(base, patient_id=pid, date_admission=date_admission,
                                lit_admission=lit)


def test_snapshot_relit_le_html_exact_de_l_epoque(base):
    """Le dossier change après coup ; la fiche relue ne doit pas bouger."""
    uid = base.inserer("utilisateur", {"nom": "Dr Test", "role": "interne"})
    sid = _sejour(base, "M1", 1)
    premiere = pancarte.imprimer(base, sid, "2026-09-01", utilisateur_id=uid)
    sejours.modifier_admission(
        base, sid, date_admission="2026-09-01", provenance_type="urgences",
        provenance_detail=None, poids_kg=99, taille_cm=190, creatinine_base=None,
        type_admission="medicale", maladie_chronique_igs2="aucune", traumatique=False,
        motif_principal="choc_septique",
    )
    relue = pancarte.snapshot(base, premiere["id"])
    assert relue["html"] == premiere["html"]
    assert "99" not in relue["html"] or "99" in premiere["html"]  # pas de recalcul
    assert relue["imprime_par_nom"] == "Dr Test"


def test_deux_impressions_le_meme_jour_incrementent_la_version(base):
    sid = _sejour(base, "M2", 2)
    v1 = pancarte.imprimer(base, sid, "2026-09-01")
    v2 = pancarte.imprimer(base, sid, "2026-09-01")
    assert v1["version"] == 1
    assert v2["version"] == 2
    liste = pancarte.snapshots_du_sejour(base, sid)
    assert [s["version"] for s in liste] == [2, 1]      # la plus récente d'abord


def test_snapshots_par_date_couvre_tout_le_service(base):
    sid1 = _sejour(base, "M3", 3)
    sid2 = _sejour(base, "M4", 4)
    pancarte.imprimer(base, sid1, "2026-09-01")
    pancarte.imprimer(base, sid2, "2026-09-01")
    pancarte.imprimer(base, sid1, "2026-09-02")

    du_1er = pancarte.snapshots_par_date(base, "2026-09-01")
    assert {f["lit_admission"] for f in du_1er} == {3, 4}
    du_2 = pancarte.snapshots_par_date(base, "2026-09-02")
    assert {f["lit_admission"] for f in du_2} == {3}


def test_dates_avec_impression_ignore_les_jours_vides(base):
    sid = _sejour(base, "M5", 5)
    assert pancarte.dates_avec_impression(base) == []
    pancarte.imprimer(base, sid, "2026-09-03")
    assert pancarte.dates_avec_impression(base) == ["2026-09-03"]


def test_snapshot_introuvable_rend_none(base):
    assert pancarte.snapshot(base, "id-inexistant") is None
