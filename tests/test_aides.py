"""Les faits assemblés depuis le dossier, et les rappels qui en découlent."""

from rea.services import aides, bilans, dispositifs, prescriptions, sejours


def _sejour(base, date_admission="2026-09-01"):
    pid = sejours.creer_patient(
        base, matricule="M1", nom_affichage="K. A.", date_naissance="1960-01-01",
        sexe="M",
    )
    return sejours.creer_sejour(
        base, patient_id=pid, date_admission=date_admission, lit_admission=1,
        poids_kg=70, taille_cm=175,
    )


def test_faits_comptent_les_jours_de_dispositif(base):
    sid = _sejour(base)
    dispositifs.poser(base, sejour_id=sid, type_="kt_central",
                      date_pose="2026-09-01", site="Jugulaire interne droite")
    f = aides.faits(base, sid, "2026-09-08")
    assert f["jours_kt_central"] == 8      # J1 = jour de pose
    assert f["kt_central_en_place"] is True
    assert f["jours_intubation"] is None   # jamais posé : non renseigné, pas 0


def test_rappel_cathether_long_se_declenche(base):
    sid = _sejour(base)
    dispositifs.poser(base, sejour_id=sid, type_="kt_central", date_pose="2026-09-01")
    codes = [r["code"] for r in aides.rappels(base, sid, "2026-09-08")]
    assert "kt_central_duree" in codes
    assert "kt_central_duree" not in [
        r["code"] for r in aides.rappels(base, sid, "2026-09-03")
    ]


def test_le_message_du_rappel_porte_la_valeur(base):
    sid = _sejour(base)
    bilans.enregistrer_resultats(
        base, sejour_id=sid, date_heure="2026-09-02T06:00", valeurs={"k": 2.6}
    )
    message = next(
        r["message"] for r in aides.rappels(base, sid, "2026-09-02")
        if r["code"] == "hypokaliemie"
    )
    assert "2,6" in message


def test_checklist_reconnait_ce_qui_est_prescrit(base):
    sid = _sejour(base)
    prescriptions.ajouter_ligne(
        base, sejour_id=sid, voie="SC", produit="Enoxaparine 4000 UI",
        date_debut="2026-09-01",
    )
    etats = {i.code: i.etat for i in aides.checklist(base, sid, "2026-09-02")}
    assert etats["thrombo"] == "ok"
    assert etats["ulcer"] == "a_verifier"


def test_aucun_fait_ne_vaut_zero_par_defaut(base):
    """Un séjour vide ne doit produire aucun rappel : sans données, le
    logiciel n'a rien à dire."""
    sid = _sejour(base)
    assert aides.rappels(base, sid, "2026-09-01") == []
