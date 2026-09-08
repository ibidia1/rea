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


# --- imprimer le jour choisi, pas le jour courant --------------------------
#
# Vérification demandée par le service (8 septembre) : « si je choisis un jour
# différent et que je clique sur imprimer la pancarte de ce jour, est-ce que
# ça imprime le jour sélectionné ou le jour actuel ? » — c'est bien le jour
# sélectionné, et ces tests le tiennent.

def test_imprimer_un_autre_jour_date_la_fiche_de_ce_jour_la(base):
    from rea.services import prescriptions

    sid = _sejour(base, "M9", 9, date_admission="2026-09-01")
    prescriptions.ajouter_ligne(base, sejour_id=sid, voie="PO", produit="Kardégic",
                                date_debut="2026-09-01", dose=75, unite="mg",
                                rythme="x1/j")
    fiche = pancarte.imprimer(base, sid, "2026-09-03")
    assert fiche["date_jour"] == "2026-09-03"
    assert "03/09/2026" in fiche["html"]
    assert "J3" in fiche["html"]          # troisième jour d'hospitalisation


def test_une_ligne_commencee_plus_tard_nest_pas_sur_la_fiche_du_jour_choisi(base):
    """La pancarte d'un jour passé est celle de ce jour-là : un traitement
    introduit depuis n'y figure pas."""
    from rea.services import prescriptions

    sid = _sejour(base, "M10", 10, date_admission="2026-09-01")
    prescriptions.ajouter_ligne(base, sejour_id=sid, voie="PO", produit="Tienam",
                                date_debut="2026-09-05", dose=1, unite="g",
                                rythme="x3/j")
    fiche = pancarte.imprimer(base, sid, "2026-09-02")
    assert "Tienam" not in fiche["html"]


def test_deux_jours_differents_donnent_deux_fiches_distinctes(base):
    sid = _sejour(base, "M11", 11, date_admission="2026-09-01")
    veille = pancarte.imprimer(base, sid, "2026-09-02")
    jour = pancarte.imprimer(base, sid, "2026-09-03")
    assert veille["date_jour"] != jour["date_jour"]
    assert veille["html"] != jour["html"]
    # Chaque jour repart à la version 1 : la version compte les impressions
    # d'une même journée, pas celles du séjour.
    assert veille["version"] == jour["version"] == 1
