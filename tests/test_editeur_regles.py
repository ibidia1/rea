"""Édition des règles et protocoles sans toucher au JSON (Administration).

Le fichier reste la vérité — ces fonctions ne font que le lire et le
réécrire. Elles doivent laisser le format exploitable par le moteur
(rea/domaine/regles.py) exactement comme un fichier écrit à la main.
"""

import json

import pytest

from rea import aides, protocoles
from rea.domaine import regles


@pytest.fixture(autouse=True)
def _dossiers_isoles(tmp_path, monkeypatch):
    """Ne jamais écrire dans les vrais regles/ ou protocoles/ du dépôt."""
    dossier_regles = tmp_path / "regles"
    dossier_regles.mkdir()
    for fichier in aides.DOSSIER.glob("*.json"):
        (dossier_regles / fichier.name).write_text(
            fichier.read_text(encoding="utf-8"), encoding="utf-8"
        )
    monkeypatch.setattr(aides, "DOSSIER", dossier_regles)
    aides.recharger()

    dossier_protocoles = tmp_path / "protocoles"
    dossier_protocoles.mkdir()
    # Patcher protocoles.config (et non un rea.config ré-importé à part) :
    # conftest.base purge sys.modules["rea.*"], ce qui peut faire pointer un
    # `import rea.config` frais vers un objet différent de celui que ce
    # module `protocoles` a déjà capturé via `from . import config`.
    monkeypatch.setattr(protocoles.config, "DOSSIER_PROTOCOLES", dossier_protocoles)
    protocoles._tous.cache_clear()
    yield
    aides.recharger()
    protocoles._tous.cache_clear()


# -- règles -------------------------------------------------------------

def test_creer_puis_lire_un_nouveau_fichier():
    contenu = aides.creer_fichier("mes_rappels", "Mes rappels")
    assert contenu["regles"] == []
    assert contenu["valide"] is False
    assert "mes_rappels" in aides.noms_fichiers()


def test_creer_un_fichier_qui_existe_deja_echoue():
    aides.creer_fichier("mes_rappels", "Mes rappels")
    with pytest.raises(FileExistsError):
        aides.creer_fichier("mes_rappels", "Encore")


def test_ajouter_une_regle_et_la_voir_s_appliquer():
    """Une règle enregistrée doit être identique, pour le moteur, à une règle
    écrite à la main dans le fichier."""
    aides.creer_fichier("mes_rappels", "Mes rappels")
    contenu = aides.lire_fichier("mes_rappels")
    contenu["regles"].append({
        "code": "test_plaquettes",
        "libelle": "Test",
        "message": "Plaquettes à {plaquettes}",
        "gravite": "alerte",
        "conditions": [{"fait": "plaquettes", "op": "<", "valeur": 50}],
    })
    aides.enregistrer_fichier("mes_rappels", contenu)

    regle = next(r for r in aides.toutes_les_regles() if r.code == "test_plaquettes")
    assert regles.declenchee(regle, {"plaquettes": 30})
    assert not regles.declenchee(regle, {"plaquettes": 80})


def test_enregistrer_incremente_la_version():
    aides.creer_fichier("mes_rappels", "Mes rappels")
    v1 = aides.lire_fichier("mes_rappels")["version"]
    aides.enregistrer_fichier("mes_rappels", aides.lire_fichier("mes_rappels"))
    v2 = aides.lire_fichier("mes_rappels")["version"]
    assert v1 != v2


def test_le_garde_fou_posologie_est_partage_par_le_moteur_et_l_editeur():
    assert regles.contient_une_posologie("Donner 5 mg/kg") == "mg/kg"
    assert regles.contient_une_posologie("Plaquettes basses") is None


def test_fichier_modifie_reste_lisible_par_le_moteur_normal():
    """Après édition, le fichier doit rester un JSON strictement valide,
    rechargeable comme n'importe quel autre."""
    aides.creer_fichier("mes_rappels", "Mes rappels")
    chemin = aides.DOSSIER / "mes_rappels.json"
    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    assert donnees["code"] == "mes_rappels"


# -- protocoles -----------------------------------------------------------

def test_enregistrer_un_protocole_puis_le_relire():
    protocoles.enregistrer("mon_protocole", {
        "titre": "Mon protocole", "version": "v1", "signe_par": None,
        "valide": False, "declencheur": {"type": "motif", "valeur": "choc_septique"},
        "lignes_prescription": [], "explorations_proposees": [], "consignes": [],
    })
    relu = protocoles.lire_fichier("mon_protocole")
    assert relu["titre"] == "Mon protocole"
    assert relu["date_version"]        # posée automatiquement
    assert "mon_protocole" in protocoles.codes()


def test_un_protocole_non_valide_n_est_jamais_propose():
    protocoles.enregistrer("brouillon", {
        "titre": "Brouillon", "version": "v1", "signe_par": None, "valide": False,
        "declencheur": {"type": "motif", "valeur": "choc_septique"},
        "lignes_prescription": [], "explorations_proposees": [], "consignes": [],
    })
    assert protocoles.protocoles_pour_motif("choc_septique") == ()


def test_un_protocole_valide_et_signe_est_propose():
    protocoles.enregistrer("signe", {
        "titre": "Signé", "version": "v1", "signe_par": "Pr. Test", "valide": True,
        "declencheur": {"type": "motif", "valeur": "choc_septique"},
        "lignes_prescription": [], "explorations_proposees": [], "consignes": [],
    })
    trouves = protocoles.protocoles_pour_motif("choc_septique")
    assert len(trouves) == 1
    assert trouves[0].code == "signe"


def test_supprimer_un_protocole():
    protocoles.enregistrer("a_supprimer", {
        "titre": "X", "version": "v1", "signe_par": None, "valide": False,
        "declencheur": {}, "lignes_prescription": [], "explorations_proposees": [],
        "consignes": [],
    })
    assert "a_supprimer" in protocoles.codes()
    protocoles.supprimer("a_supprimer")
    assert "a_supprimer" not in protocoles.codes()
