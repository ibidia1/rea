"""Transfert de lit — jusqu'ici un service écrit et jamais câblé à un écran.

`changer_de_lit` écrivait dans `sejour_lit` mais ne touchait jamais
`sejour.lit_admission`, le champ que `lits.etat_des_lits()` lit réellement
pour savoir qui est où. Un transfert restait donc invisible : le patient
apparaissait toujours dans son ancien lit, et le nouveau restait « libre ».
"""

import pytest

from rea.services import lits, sejours


def _sejour(base, lit=1):
    pid = sejours.creer_patient(base, matricule=f"M{lit}", nom_affichage="X", date_naissance=None)
    return sejours.creer_sejour(base, patient_id=pid, date_admission="2026-09-01", lit_admission=lit)


def test_le_tableau_des_lits_reflete_le_transfert(base):
    sid = _sejour(base, lit=1)
    sejours.changer_de_lit(base, sid, 5)

    etat = {l["lit"]: l for l in lits.etat_des_lits(base)}
    assert etat[1]["occupe"] is False, "l'ancien lit doit se libérer"
    assert etat[5]["occupe"] is True
    assert etat[5]["sejour_id"] == sid


def test_on_ne_peut_pas_transferer_vers_un_lit_deja_occupe(base):
    sid1 = _sejour(base, lit=1)
    _sejour(base, lit=2)

    with pytest.raises(ValueError):
        sejours.changer_de_lit(base, sid1, 2)

    assert lits.etat_des_lits(base)[0]["sejour_id"] == sid1  # lit 1 inchangé


def test_l_historique_des_lits_garde_la_trace_du_lit_precedent(base):
    sid = _sejour(base, lit=1)
    sejours.changer_de_lit(base, sid, 5)

    historique = base.requete(
        "SELECT lit, date_fin FROM sejour_lit WHERE sejour_id = ? ORDER BY date_debut", (sid,)
    )
    assert [h["lit"] for h in historique] == [5]


def test_deux_transferts_successifs_ferment_bien_l_historique_precedent(base):
    sid = _sejour(base, lit=1)
    sejours.changer_de_lit(base, sid, 5)
    sejours.changer_de_lit(base, sid, 8)

    historique = base.requete(
        "SELECT lit, date_fin FROM sejour_lit WHERE sejour_id = ? ORDER BY date_debut", (sid,)
    )
    assert [h["lit"] for h in historique] == [5, 8]
    assert historique[0]["date_fin"] is not None
    assert historique[1]["date_fin"] is None

    assert lits.etat_des_lits(base)[7]["sejour_id"] == sid  # lit 8 (index 7)


def test_transferer_vers_son_propre_lit_ne_plante_pas(base):
    sid = _sejour(base, lit=3)
    sejours.changer_de_lit(base, sid, 3)
    assert lits.etat_des_lits(base)[2]["sejour_id"] == sid
