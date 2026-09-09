"""Un protocole déclenché par une règle d'aide, et non par le motif d'entrée.

Les deux premiers déclencheurs — motif, région traumatique — ne servent qu'à
l'admission : ils décrivent le patient qui arrive. La plupart des protocoles
d'un service répondent pourtant à quelque chose qui *survient* : une kaliémie
à 2,6 le quatrième jour. Ce troisième déclencheur attache un protocole au code
d'une règle d'aide (demande du service, 9 septembre).

Ce que ces tests protègent avant tout : la règle de sécurité 1 du §4.5. Un
protocole non signé n'est jamais proposé, quel que soit son déclencheur.
"""

import json

import pytest

from rea import config, protocoles
from rea.services import prescriptions, protocoles as protocoles_service, sejours


@pytest.fixture
def protocole_signe(tmp_path, monkeypatch):
    """Un protocole attaché à la règle « hypokaliemie », signé."""
    dossier = tmp_path / "protocoles"
    dossier.mkdir()
    (dossier / "kaliemie.json").write_text(json.dumps({
        "code": "kaliemie", "titre": "Correction d'une hypokaliémie",
        "version": "2026-09-09-v1", "date_version": "2026-09-09",
        "valide": True, "signe_par": "Pr Chef",
        "declencheur": {"type": "regle", "valeur": "hypokaliemie"},
        "lignes_prescription": [
            {"voie": "IV", "produit": "Chlorure de potassium", "dose": 1,
             "unite": "g", "rythme": "conditionnel", "vitesse": "0,5",
             "note": "sur voie centrale"},
            {"voie": "SOINS", "produit": "Scope", "rythme": "continu"},
        ],
        "explorations_proposees": [],
        "consignes": ["Vérifier la magnésémie"],
    }), encoding="utf-8")
    monkeypatch.setattr(config, "DOSSIER_PROTOCOLES", dossier)
    protocoles._tous.cache_clear()
    yield
    protocoles._tous.cache_clear()


def test_un_protocole_signe_est_propose_sur_sa_regle(protocole_signe):
    trouves = protocoles.protocoles_pour_regle("hypokaliemie")
    assert [p.code for p in trouves] == ["kaliemie"]


def test_aucun_protocole_sur_une_autre_regle(protocole_signe):
    assert protocoles.protocoles_pour_regle("hyperkaliemie") == ()


def test_un_brouillon_n_est_jamais_propose(tmp_path, monkeypatch):
    """Règle de sécurité 1 du §4.5 : signé, ou rien. Le déclencheur n'y change
    rien — c'est le point le plus important de ce fichier."""
    dossier = tmp_path / "protocoles"
    dossier.mkdir()
    (dossier / "brouillon.json").write_text(json.dumps({
        "code": "brouillon", "titre": "Essai", "version": "v1",
        "date_version": "2026-09-09", "valide": False, "signe_par": None,
        "declencheur": {"type": "regle", "valeur": "hypokaliemie"},
        "lignes_prescription": [{"voie": "IV", "produit": "KCl"}],
        "explorations_proposees": [], "consignes": [],
    }), encoding="utf-8")
    monkeypatch.setattr(config, "DOSSIER_PROTOCOLES", dossier)
    protocoles._tous.cache_clear()
    try:
        assert protocoles.protocoles_pour_regle("hypokaliemie") == ()
    finally:
        protocoles._tous.cache_clear()


def test_le_protocole_du_depot_reste_un_brouillon():
    """`protocoles/correction_hypokaliemie.json` est livré non signé : il
    montre le mécanisme, il ne prescrit rien tant qu'un senior ne l'a pas relu
    et signé dans l'écran Administration."""
    livres = {p.code: p for p in protocoles.tous_les_protocoles()}
    assert "correction_hypokaliemie" in livres
    assert not livres["correction_hypokaliemie"].valide
    assert protocoles.protocoles_pour_regle("hypokaliemie") == ()


def test_appliquer_reprend_la_posologie_du_protocole(base, protocole_signe):
    """Un protocole signé a le droit de porter une dose (décision du service,
    9 septembre). Le §3.1 tient toujours : ce n'est pas le logiciel qui la
    calcule, c'est le senior qui l'a écrite et signée. Un protocole de
    correction de kaliémie sans dose ne sert à rien — la dose *est* le
    protocole."""
    pid = sejours.creer_patient(base, matricule="M1", nom_affichage="T",
                                date_naissance=None)
    sid = sejours.creer_sejour(base, patient_id=pid, date_admission="2026-09-06",
                               lit_admission=1)
    protocole = protocoles.protocoles_pour_regle("hypokaliemie")[0]

    posees = protocoles_service.appliquer(
        base, sid, [protocole], date_debut="2026-09-09",
    )
    assert posees == 2

    lignes = {l["produit"]: l for l in prescriptions.toutes_les_lignes(base, sid)}
    assert set(lignes) == {"Chlorure de potassium", "Scope"}
    kcl = lignes["Chlorure de potassium"]
    assert kcl["voie"] == "IV"
    assert kcl["dose"] == 1
    assert kcl["unite"] == "g"
    assert kcl["rythme"] == "conditionnel"
    # « 0,5 » relu à la main dans un fichier doit passer.
    assert kcl["vitesse"] == 0.5
    # Ce que le protocole ne dit pas reste vide, il n'est pas deviné.
    assert lignes["Scope"]["dose"] is None
    # Six mois plus tard, on doit savoir de quelle version vient cette ligne.
    assert kcl["protocole_code"] == "kaliemie"
    assert kcl["protocole_version"] == "2026-09-09-v1"


def test_une_dose_illisible_reste_vide_au_lieu_de_valoir_zero(tmp_path,
                                                              monkeypatch, base):
    """Une dose à zéro dans une prescription se lit comme une décision.
    Ce qui n'est pas un nombre doit rester absent."""
    from rea.services import prescriptions as presc

    dossier = tmp_path / "protocoles"
    dossier.mkdir()
    (dossier / "flou.json").write_text(json.dumps({
        "code": "flou", "titre": "Essai", "version": "v1",
        "date_version": "2026-09-09", "valide": True, "signe_par": "Pr Chef",
        "declencheur": {"type": "regle", "valeur": "hypokaliemie"},
        "lignes_prescription": [
            {"voie": "IV", "produit": "KCl", "dose": "selon kaliémie"},
        ],
        "explorations_proposees": [], "consignes": [],
    }), encoding="utf-8")
    monkeypatch.setattr(config, "DOSSIER_PROTOCOLES", dossier)
    protocoles._tous.cache_clear()
    try:
        pid = sejours.creer_patient(base, matricule="M9", nom_affichage="T",
                                    date_naissance=None)
        sid = sejours.creer_sejour(base, patient_id=pid,
                                   date_admission="2026-09-06", lit_admission=1)
        protocole = protocoles.protocoles_pour_regle("hypokaliemie")[0]
        protocoles_service.appliquer(base, sid, [protocole],
                                     date_debut="2026-09-09")
        ligne = presc.toutes_les_lignes(base, sid)[0]
        assert ligne["dose"] is None
    finally:
        protocoles._tous.cache_clear()
