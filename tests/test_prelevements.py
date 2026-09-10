"""Les bilans et les radios du poste (SPEC §5.8).

`bilan_demande` dit ce qu'il faut prélever et à quelle heure. Rien ne disait
si ça avait été fait : un bilan demandé la veille au soir et jamais prélevé ne
laissait aucune trace, et personne ne s'en apercevait avant que le résultat
manque à la visite (demande du service, 10 septembre).

L'équipe du matin doit voir **ses** examens, pas ceux des vingt-quatre heures.
"""

import importlib

import pytest


def _services(nom):
    return importlib.import_module(f"rea.services.{nom}")


def _sejour(base):
    sejours = _services("sejours")
    pid = sejours.creer_patient(base, matricule="M1", nom_affichage="P1",
                                date_naissance="1970-01-01")
    return sejours.creer_sejour(base, patient_id=pid, date_admission="2026-09-01",
                                lit_admission=1)


def _demander(base, sid, jour, examens):
    """`examens` : {code: heure} — comme le médecin les demande au prescrit."""
    prescriptions = _services("prescriptions")
    prescriptions.definir_bilans_demandes(
        base, sid, jour, [(code, heure) for code, heure in examens.items()])


# -- chaque équipe voit les siens ------------------------------------------

def test_l_equipe_du_matin_voit_les_bilans_du_matin(base):
    """Lui montrer les examens de la journée entière reviendrait à lui
    demander de retrouver les siens dans une liste dont les deux tiers ne la
    concernent pas."""
    prelevements = _services("prelevements")
    sid = _sejour(base)
    _demander(base, sid, "2026-09-09",
              {"nfs": "08:00", "crp": "08:00", "gds": "16:00", "ionogramme": "22:00"})

    matin = prelevements.de_la_vacation(base, sid, "2026-09-09", "matin")
    assert {d["examen_code"] for d in matin} == {"nfs", "crp"}
    apres_midi = prelevements.de_la_vacation(base, sid, "2026-09-09", "apres_midi")
    assert {d["examen_code"] for d in apres_midi} == {"gds"}
    nuit = prelevements.de_la_vacation(base, sid, "2026-09-09", "nuit")
    assert {d["examen_code"] for d in nuit} == {"ionogramme"}


def test_les_radios_sont_dans_la_meme_liste(base):
    """Une radio de 8 h oubliée coûte la même visite qu'une NFS oubliée : rien
    ne justifie de la ranger ailleurs sous prétexte qu'il n'y a pas de tube."""
    prelevements = _services("prelevements")
    sid = _sejour(base)
    _demander(base, sid, "2026-09-09",
              {"rx_thorax": "08:00", "ecg": "08:00", "nfs": "08:00"})
    matin = prelevements.de_la_vacation(base, sid, "2026-09-09", "matin")
    assert {d["examen_code"] for d in matin} == {"rx_thorax", "ecg", "nfs"}
    assert "Radiographie de thorax" in {d["libelle"] for d in matin}


def test_une_heure_illisible_ne_fait_pas_disparaitre_l_examen(base):
    """Un bilan qu'on n'affiche pas est un bilan qu'on ne prélève pas."""
    prelevements = _services("prelevements")
    assert prelevements._heure("bizarre") == 8
    assert prelevements._heure(None) == 8
    assert prelevements._heure("06:00") == 6


def test_sans_examen_demande_la_liste_est_vide(base):
    prelevements = _services("prelevements")
    sid = _sejour(base)
    assert prelevements.de_la_vacation(base, sid, "2026-09-09", "matin") == []


# -- cocher, et décocher ----------------------------------------------------

def test_cocher_puis_decocher(base):
    """Corriger doit coûter le même nombre de gestes que noter, sinon on
    corrige sur le papier."""
    prelevements = _services("prelevements")
    sid = _sejour(base)
    prelevements.noter(base, sejour_id=sid, date_jour="2026-09-09",
                       examen_code="nfs", heure_prevue=8,
                       statut=prelevements.FAIT)
    assert prelevements.du_jour(base, sid, "2026-09-09")[("nfs", 8)]["statut"] == "fait"
    prelevements.effacer(base, sejour_id=sid, date_jour="2026-09-09",
                         examen_code="nfs", heure_prevue=8)
    assert ("nfs", 8) not in prelevements.du_jour(base, sid, "2026-09-09")


def test_un_non_preleve_doit_dire_pourquoi(base):
    """« Tube cassé » tapé à la main ne se compte pas et ne remonte à
    personne."""
    prelevements = _services("prelevements")
    sid = _sejour(base)
    with pytest.raises(ValueError):
        prelevements.noter(base, sejour_id=sid, date_jour="2026-09-09",
                           examen_code="nfs", heure_prevue=8,
                           statut=prelevements.NON_FAIT)


def test_le_non_preleve_remonte_au_medecin(base):
    """Il apprenait l'absence d'un résultat en le cherchant."""
    prelevements = _services("prelevements")
    sid = _sejour(base)
    prelevements.noter(base, sejour_id=sid, date_jour="2026-09-09",
                       examen_code="rx_thorax", heure_prevue=8,
                       statut=prelevements.NON_FAIT,
                       motif_code="appareil_indisponible",
                       motif="radiologie en panne depuis 6 h")
    non_faits = prelevements.non_faits_du_sejour(base, sid, "2026-09-09")
    assert len(non_faits) == 1
    assert non_faits[0]["libelle"] == "Radiographie de thorax"
    assert "Appareil indisponible" in non_faits[0]["libelle_motif"]
    assert "panne" in non_faits[0]["motif"]


def test_un_statut_inconnu_est_refuse(base):
    prelevements = _services("prelevements")
    sid = _sejour(base)
    with pytest.raises(ValueError):
        prelevements.noter(base, sejour_id=sid, date_jour="2026-09-09",
                           examen_code="nfs", heure_prevue=8, statut="peut_etre")


def test_noter_deux_fois_ne_cree_pas_deux_lignes(base):
    """Un doigt qui glisse ne doit pas produire deux prélèvements."""
    prelevements = _services("prelevements")
    sid = _sejour(base)
    for _ in range(3):
        prelevements.noter(base, sejour_id=sid, date_jour="2026-09-09",
                           examen_code="nfs", heure_prevue=8,
                           statut=prelevements.FAIT)
    lignes = base.requete(
        "SELECT id FROM prelevement WHERE sejour_id = ? AND supprime = 0", (sid,))
    assert len(lignes) == 1


# -- les motifs sont ceux d'un prélèvement, pas d'un médicament ------------

def test_les_motifs_ne_sont_pas_ceux_d_un_medicament():
    """Un bilan ne se rate pas pour rupture de stock : il se rate parce que le
    patient était au bloc."""
    referentiels = importlib.import_module("rea.referentiels")
    codes = {e[0] for e in referentiels.charger("motifs_non_prelevement")}
    assert "patient_absent" in codes and "tube_manquant" in codes
    assert "rupture_stock" not in codes and "pas_de_sng" not in codes


def test_chaque_motif_dit_a_qui_il_remonte():
    """Un motif qui ne remonte à personne ne sert qu'à fermer une ligne."""
    prelevements = _services("prelevements")
    referentiels = importlib.import_module("rea.referentiels")
    for code, _libelle, action in referentiels.charger("motifs_non_prelevement"):
        assert action in prelevements.ACTIONS, (code, action)


def test_l_ecran_infirmier_affiche_les_prelevements():
    """Un service calculé mais jamais branché ne se voit nulle part."""
    import pathlib

    source = (pathlib.Path(__file__).resolve().parent.parent
              / "rea" / "ui" / "infirmier.py").read_text(encoding="utf-8")
    assert '"À prélever"' in source
    assert "prelevements_service.de_la_vacation(" in source
    assert "prelevements_service.noter(" in source
