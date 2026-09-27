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


def test_l_admission_supprimee_sort_de_toutes_les_statistiques(base):
    """Cohorte, décompte des entrées et variables proposées aux croisements :
    une admission supprimée ne compte nulle part (question du service,
    27 septembre)."""
    s, stats, crois = _svc("sejours"), _svc("statistiques"), _svc("croisements")
    presc = _svc("prescriptions")
    vraies = []
    for i in range(2):
        pid = s.creer_patient(base, matricule=f"V-{i}", nom_affichage="Vrai",
                              date_naissance="1970-01-01", sexe="F")
        vraies.append(s.creer_sejour(base, patient_id=pid, lit_admission=5 + i,
                                     date_admission="2026-09-12"))
    fausses = [_sejour(base)]
    pid = s.creer_patient(base, matricule="F-2", nom_affichage="Faux 2",
                          date_naissance="1970-01-01", sexe="M")
    fausses.append(s.creer_sejour(base, patient_id=pid, lit_admission=9,
                                  date_admission="2026-09-12"))
    for sid in fausses:
        presc.ajouter_ligne(base, sejour_id=sid, voie="IV", produit="Produit fantôme",
                            date_debut="2026-09-12", rythme="x1/j")
    assert "produit:Produit fantôme" in {v.code for v in crois.facteurs_disponibles(base)}
    for sid in fausses:
        s.supprimer_admission(base, sid, motif="patient inexistant")

    assert {x["id"] for x in stats.cohorte(base)} == set(vraies)
    assert "produit:Produit fantôme" not in {v.code for v in crois.facteurs_disponibles(base)}
