"""Supprimer un bilan saisi à tort — une concentration fausse, validée trop vite.

La valeur quitte la cinétique, la visite et la feuille ; la ligne reste en base
(jamais de suppression physique) et le journal garde le motif.

Demande du service, 27 septembre 2026.
"""

import pytest

from rea.services import bilans, sejours


def _sejour(base, matricule="B-1"):
    pid = sejours.creer_patient(base, matricule=matricule, nom_affichage="Patient",
                                date_naissance="1970-01-01", sexe="M")
    return sejours.creer_sejour(base, patient_id=pid, lit_admission=4,
                                date_admission="2026-09-20")


def test_une_valeur_fausse_disparait_mais_reste_en_base(base):
    sid = _sejour(base)
    ids = bilans.enregistrer_resultats(base, sid, "2026-09-21T08:00",
                                       {"k": 7.9, "na": 139})
    k_id = next(i for i in ids if base.une_ligne(
        "SELECT analyte FROM bilan_resultat WHERE id = ?", (i,))["analyte"] == "k")
    assert bilans.supprimer_valeurs(base, sid, resultats=[k_id],
                                    motif="erreur de concentration") == 1
    restants = {l["analyte"] for l in bilans.resultats_du_sejour(base, sid)}
    assert restants == {"na"}
    ligne = base.une_ligne("SELECT supprime FROM bilan_resultat WHERE id = ?", (k_id,))
    assert ligne["supprime"] == 1
    trace = base.une_ligne(
        "SELECT * FROM journal WHERE ligne_id = ? AND action = 'motif_suppression'",
        (k_id,))
    assert trace and "erreur de concentration" in str(trace)


def test_tout_un_prelevement_avec_son_gaz_du_sang(base):
    sid = _sejour(base)
    ids = bilans.enregistrer_resultats(base, sid, "2026-09-21T08:00", {"hb": 3.1})
    gid = bilans.enregistrer_gaz_du_sang(base, sid, "2026-09-21T08:00", ph=6.5)
    prelevement = bilans.prelevements_du_sejour(base, sid)[0]
    assert prelevement["date_heure"] == "2026-09-21T08:00"
    assert [g["id"] for g in prelevement["gaz"]] == [gid]
    bilans.supprimer_valeurs(base, sid, resultats=ids, gaz=[gid], motif="mauvais patient")
    assert bilans.prelevements_du_sejour(base, sid) == []
    assert bilans.gaz_du_sang_du_sejour(base, sid) == []


def test_le_motif_est_obligatoire(base):
    sid = _sejour(base)
    ids = bilans.enregistrer_resultats(base, sid, "2026-09-21T08:00", {"hb": 3.1})
    with pytest.raises(ValueError):
        bilans.supprimer_valeurs(base, sid, resultats=ids, motif="  ")
    assert len(bilans.resultats_du_sejour(base, sid)) == 1


def test_on_ne_touche_pas_au_bilan_d_un_autre_patient(base):
    sid = _sejour(base)
    autre = _sejour(base, matricule="B-2")
    ids = bilans.enregistrer_resultats(base, autre, "2026-09-21T08:00", {"hb": 9})
    assert bilans.supprimer_valeurs(base, sid, resultats=ids, motif="x") == 0
    assert len(bilans.resultats_du_sejour(base, autre)) == 1
