"""Supprimer une admission créée par erreur, pour ne pas fausser les stats.

Une fausse admission — mauvais patient, double saisie, essai — gonfle le nombre
d'entrées. L'administrateur la retire ; la ligne reste en base (jamais de
suppression physique), avec le motif et qui l'a faite.

Demande du service, 12 septembre 2026.
"""

import importlib

import pytest


def _svc(nom):
    return importlib.import_module(f"rea.services.{nom}")


def _sejour(base):
    s = _svc("sejours")
    pid = s.creer_patient(base, matricule="F-1", nom_affichage="Faux Patient",
                          date_naissance="1970-01-01", sexe="M")
    return s.creer_sejour(base, patient_id=pid, lit_admission=2,
                          date_admission="2026-09-12")


def test_l_admission_supprimee_quitte_les_lits(base):
    s, sup = _svc("sejours"), _svc("supervision")
    sid = _sejour(base)
    assert len(sup.sejours_ouverts(base)) == 1
    s.supprimer_admission(base, sid, motif="créée deux fois")
    assert sup.sejours_ouverts(base) == []


def test_la_ligne_reste_en_base_avec_son_motif(base):
    s = _svc("sejours")
    sid = _sejour(base)
    s.supprimer_admission(base, sid, motif="erreur de patient")
    ligne = base.une_ligne("SELECT supprime, motif_suppression FROM sejour WHERE id = ?",
                           (sid,))
    assert ligne["supprime"] == 1
    assert ligne["motif_suppression"] == "erreur de patient"


def test_le_motif_est_obligatoire(base):
    s = _svc("sejours")
    sid = _sejour(base)
    with pytest.raises(ValueError, match="motif"):
        s.supprimer_admission(base, sid, motif="   ")


def test_une_admission_inconnue_est_refusee(base):
    s = _svc("sejours")
    with pytest.raises(ValueError, match="introuvable"):
        s.supprimer_admission(base, "pas-un-id", motif="x")


def test_seul_l_administrateur_voit_le_bouton():
    """Lu en source : le tiroir de suppression est derrière le droit
    « comptes », celui de l'administrateur."""
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "rea" / "ui"
           / "identite.py").read_text(encoding="utf-8")
    debut = src.index("def _supprimer_admission")
    fin = src.index("def _transferer_lit")
    bloc = src[debut:fin]
    assert 'peut("comptes")' in bloc
    assert "Oui, supprimer" in bloc  # confirmation en deux temps
