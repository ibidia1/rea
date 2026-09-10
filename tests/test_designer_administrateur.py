"""La sortie de secours quand une base n'a plus d'administrateur.

Un service qui tournait avant que les rôles n'existent a des comptes mais
aucun administrateur : personne ne peut alors créer de compte ni ouvrir le
bouton Admin, et la porte serait fermée de l'extérieur. Ce fichier vérifie
que la porte s'ouvre dans ce cas — et seulement dans ce cas.
"""

import importlib

import pytest


def _service():
    return importlib.import_module("rea.services.utilisateurs")


def test_une_base_sans_admin_est_reconnue(base):
    u = _service()
    u.creer(base, "Dr Ben Salah", "senior", code="884411")
    assert u.sans_administrateur(base) is True


def test_une_base_avec_admin_ne_l_est_pas(base):
    u = _service()
    u.creer(base, "Dr Karaa", "admin", code="884411")
    u.creer(base, "Inf. Amira", "infirmier", code="551122")
    assert u.sans_administrateur(base) is False
    assert [c["nom"] for c in u.administrateurs(base)] == ["Dr Karaa"]


def test_une_base_vide_n_est_pas_concernee(base):
    """Sans aucun compte, c'est la première ouverture qui répond."""
    assert _service().sans_administrateur(base) is False


def test_designer_avec_le_bon_code_donne_le_role(base):
    u = _service()
    cible = u.creer(base, "Dr Ben Salah", "senior", code="884411")
    u.designer_administrateur(base, cible, code="884411")
    assert u.par_id(base, cible)["role"] == "admin"
    assert u.sans_administrateur(base) is False


def test_le_mauvais_code_ne_donne_rien(base):
    u = _service()
    cible = u.creer(base, "Dr Ben Salah", "senior", code="884411")
    with pytest.raises(ValueError, match="incorrect"):
        u.designer_administrateur(base, cible, code="000000")
    assert u.par_id(base, cible)["role"] == "senior"


def test_un_compte_sans_code_doit_en_recevoir_un(base):
    """Sinon on donnerait les pleins pouvoirs à un nom que n'importe qui
    peut choisir dans la liste d'ouverture."""
    u = _service()
    cible = u.creer(base, "Dr Ben Salah", "senior")
    with pytest.raises(ValueError, match="code"):
        u.designer_administrateur(base, cible, code="")
    assert u.par_id(base, cible)["role"] == "senior"

    u.designer_administrateur(base, cible, code="", nouveau_code="884411")
    compte = u.par_id(base, cible)
    assert compte["role"] == "admin"
    assert u.code_correct("884411", compte["pin"])


def test_la_porte_se_referme_des_qu_un_admin_existe(base):
    u = _service()
    u.creer(base, "Dr Karaa", "admin", code="884411")
    cible = u.creer(base, "Inf. Amira", "infirmier", code="551122")
    with pytest.raises(ValueError, match="déjà un administrateur"):
        u.designer_administrateur(base, cible, code="551122")
    assert u.par_id(base, cible)["role"] == "infirmier"


def test_un_compte_desactive_ne_se_promeut_pas(base):
    """Un compte parti du service ne revient pas administrateur."""
    u = _service()
    u.creer(base, "Dr Ben Salah", "senior", code="884411")
    cible = u.creer(base, "Inf. Amira", "infirmier", code="551122")
    u.desactiver(base, cible)
    assert u.sans_administrateur(base) is True
    with pytest.raises(ValueError, match="introuvable"):
        u.designer_administrateur(base, cible, code="551122")


def test_le_dernier_administrateur_reste_protege(base):
    """La sortie de secours n'annule pas la règle qui l'a rendue nécessaire :
    on ne se ferme pas la porte de l'extérieur."""
    u = _service()
    seul = u.creer(base, "Dr Karaa", "admin", code="884411")
    with pytest.raises(ValueError, match="dernier compte"):
        u.modifier_role(base, seul, "senior")


def test_le_changement_de_code_est_ecrit(base):
    u = _service()
    cible = u.creer(base, "Dr Ben Salah", "senior", code="884411")
    u.designer_administrateur(base, cible, code="884411", nouveau_code="221100")
    compte = u.par_id(base, cible)
    assert compte["role"] == "admin"
    assert u.code_correct("221100", compte["pin"])
