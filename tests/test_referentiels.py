"""Les référentiels sont des fichiers, pas du code (feuille de route, R2).

Le critère de fin du bloc 1 est vérifiable : ajouter une valeur à un fichier
JSON doit la faire apparaître dans le programme sans qu'aucun `.py` change.
"""

import json
import sys
from pathlib import Path

import pytest

from rea import referentiels


def test_tous_les_referentiels_se_chargent():
    assert referentiels.noms(), "aucun fichier de référentiel trouvé"
    for nom in referentiels.noms():
        assert referentiels.charger(nom) is not None


def test_chaque_referentiel_porte_une_version():
    for ligne in referentiels.inventaire():
        assert ligne["version"], f"{ligne['nom']} sans version"
        assert ligne["nb_valeurs"] > 0, f"{ligne['nom']} vide"


def test_les_valeurs_sont_gelees():
    """Un référentiel est partagé par tout le programme : s'il était modifiable,
    un écran pourrait le vider pour les autres."""
    provenances = referentiels.charger("provenances")
    assert isinstance(provenances, tuple)
    with pytest.raises(AttributeError):
        provenances.append(("x", "X"))


def test_referentiel_absent_est_une_erreur_explicite():
    with pytest.raises(referentiels.ReferentielIntrouvable):
        referentiels.charger("liste_qui_nexiste_pas")


def test_ajouter_une_valeur_sans_toucher_au_code(tmp_path, monkeypatch):
    """Critère de fin du bloc 1 : le service ajoute une provenance en éditant
    un fichier, redémarre, et la voit dans l'écran d'admission."""
    dossier = tmp_path / "referentiels"
    dossier.mkdir()
    for fichier in referentiels.DOSSIER.glob("*.json"):
        (dossier / fichier.name).write_text(
            fichier.read_text(encoding="utf-8"), encoding="utf-8"
        )

    chemin = dossier / "provenances.json"
    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    donnees["valeurs"].append(["samu", "SAMU"])
    donnees["version"] = "2099-01-01.1"
    chemin.write_text(json.dumps(donnees, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setenv("REA_REFERENTIELS", str(dossier))
    for module in list(sys.modules):
        if module == "rea" or module.startswith("rea."):
            del sys.modules[module]
    from rea import listes

    assert ("samu", "SAMU") in listes.PROVENANCES
    assert listes.libelle(listes.PROVENANCES, "samu") == "SAMU"

    from rea import referentiels as rechargé

    assert rechargé.version("provenances") == "2099-01-01.1"

    for module in list(sys.modules):
        if module == "rea" or module.startswith("rea."):
            del sys.modules[module]


def test_le_code_ne_contient_plus_de_listes_en_dur():
    """Garde-fou : `listes.py` doit rester un module d'accès, pas de données.
    S'il regrossit, c'est que quelqu'un a recommencé à écrire des listes dans
    le code — la règle R2 se reperd exactement comme ça."""
    source = (Path(referentiels.__file__).parent / "listes.py").read_text(
        encoding="utf-8"
    )
    assert len(source.splitlines()) < 250
