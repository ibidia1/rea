"""Préparer, valider, imprimer — trois étapes distinctes pour la pancarte du
lendemain, sur demande explicite du service.

Avant cette étape, « préparer » et « imprimer » n'étaient séparées par rien :
on pouvait imprimer une reconduction jamais relue. `validee_le` sur `journee`
rend l'étape de relecture vérifiable, pas seulement une convention d'écran.
"""

import pytest

from rea.services import prescriptions, sejours


def _sejour(base):
    pid = sejours.creer_patient(base, matricule="M", nom_affichage="M", date_naissance=None)
    return sejours.creer_sejour(base, patient_id=pid, date_admission="2026-09-01", lit_admission=1)


def test_avant_preparation_aucune_journee_n_existe(base):
    sid = _sejour(base)
    assert prescriptions.etat_journee(base, sid, "2026-09-02") is None


def test_preparer_ne_valide_pas(base):
    sid = _sejour(base)
    prescriptions.preparer_pancarte_de_demain(base, sid, aujourdhui="2026-09-01")
    etat = prescriptions.etat_journee(base, sid, "2026-09-02")
    assert etat["preparee_le"] is not None
    assert etat["validee_le"] is None


def test_valider_sans_avoir_prepare_echoue(base):
    sid = _sejour(base)
    with pytest.raises(ValueError):
        prescriptions.valider_pancarte_de_demain(base, sid, aujourdhui="2026-09-01")


def test_valider_apres_preparation_pose_validee_le(base):
    sid = _sejour(base)
    uid = base.inserer("utilisateur", {"nom": "Dr Test", "role": "interne"})
    prescriptions.preparer_pancarte_de_demain(base, sid, aujourdhui="2026-09-01")
    prescriptions.valider_pancarte_de_demain(
        base, sid, aujourdhui="2026-09-01", utilisateur_id=uid,
    )
    etat = prescriptions.etat_journee(base, sid, "2026-09-02")
    assert etat["validee_le"] is not None
    assert etat["validee_par"] == uid


def test_valider_est_journalise(base):
    sid = _sejour(base)
    prescriptions.preparer_pancarte_de_demain(base, sid, aujourdhui="2026-09-01")
    avant = len(base.journal())
    prescriptions.valider_pancarte_de_demain(base, sid, aujourdhui="2026-09-01")
    actions = [j["action"] for j in base.journal()]
    assert len(base.journal()) == avant + 1
    assert "validation_pancarte" in actions


def test_imprimer_ne_verifie_pas_lui_meme_la_validation(base):
    """La règle est tenue par l'écran (bouton actif ou non), pas par le
    service d'impression : celui-ci reste utilisable pour n'importe quelle
    date, y compris une date jamais préparée/validée (aujourd'hui, hier)."""
    sid = _sejour(base)
    from rea.services import pancarte

    snap = pancarte.imprimer(base, sid, "2026-09-01")
    assert snap["version"] == 1
