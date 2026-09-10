"""Le compte administrateur de départ, et son code qui ne protège rien.

Un service qui installe le logiciel un matin ne doit pas rester devant un
écran sans porte : sans administrateur, personne ne peut créer de compte. Le
compte « Slah » ouvre cette porte avec un code écrit dans `config.py`.

Ce fichier tient les deux bouts. Le code de départ est **public** — il est
dans le dépôt : il ne doit donc jamais servir à autre chose qu'à entrer une
première fois, et jamais sur une base où quelqu'un s'était déjà protégé.
"""

import importlib

import pytest

from rea import config


def _service():
    return importlib.import_module("rea.services.utilisateurs")


def test_le_compte_de_depart_est_administrateur(base):
    u = _service()
    identifiant = u.creer_compte_initial(base)
    compte = u.par_id(base, identifiant)
    assert compte["nom"] == config.COMPTE_INITIAL_NOM
    assert compte["role"] == "admin"
    assert u.code_correct(config.CODE_INITIAL, compte["pin"])


def test_il_est_marque_provisoire(base):
    """Sans cette marque, un code public passerait pour une protection."""
    u = _service()
    u.creer_compte_initial(base)
    provisoires = [c["nom"] for c in u.comptes_a_code_provisoire(base)]
    assert provisoires == [config.COMPTE_INITIAL_NOM]


def test_poser_un_vrai_code_leve_la_marque(base):
    u = _service()
    identifiant = u.creer_compte_initial(base)
    u.definir_code(base, identifiant, "884411", utilisateur_id=identifiant)
    compte = u.par_id(base, identifiant)
    assert compte["code_provisoire"] == 0
    assert u.comptes_a_code_provisoire(base) == []
    assert u.code_correct("884411", compte["pin"])
    assert not u.code_correct(config.CODE_INITIAL, compte["pin"])


def test_une_base_qui_a_deja_un_administrateur_le_refuse(base):
    u = _service()
    u.creer(base, "Dr Karaa", "admin", code="884411")
    with pytest.raises(ValueError, match="déjà un administrateur"):
        u.creer_compte_initial(base)


def test_une_base_deja_protegee_le_refuse(base):
    """Le point qui compte : ajouter un compte au code public à une base où
    quelqu'un s'était protégé rendrait cette protection illusoire — n'importe
    qui lisant le dépôt entrerait administrateur."""
    u = _service()
    u.creer(base, "Dr Ben Salah", "senior", code="884411")
    assert u.sans_administrateur(base) is True
    with pytest.raises(ValueError, match="code d'accès"):
        u.creer_compte_initial(base)
    assert u.par_nom(base, config.COMPTE_INITIAL_NOM) is None


def test_une_base_sans_aucun_code_l_accepte(base):
    """Là, il n'y a pas de serrure à forcer : le raccourci ne retire rien."""
    u = _service()
    u.creer(base, "Dr Ben Salah", "senior")
    u.creer(base, "Inf. Amira", "infirmier")
    assert u.rien_n_est_protege(base) is True
    identifiant = u.creer_compte_initial(base)
    assert u.par_id(base, identifiant)["role"] == "admin"


def test_un_compte_du_meme_nom_deja_la_est_repris(base):
    """« Slah » existe en infirmier sans code : on le promeut au lieu de
    refuser sur un doublon de nom, qui laisserait la base sans issue."""
    u = _service()
    ancien = u.creer(base, config.COMPTE_INITIAL_NOM, "infirmier")
    identifiant = u.creer_compte_initial(base)
    assert identifiant == ancien
    compte = u.par_id(base, identifiant)
    assert compte["role"] == "admin"
    assert compte["code_provisoire"] == 1


def test_le_code_de_depart_est_assez_long(base):
    """Il doit passer la règle qu'on impose à tout le monde, sinon le compte
    se retrouverait avec un code que le logiciel refuse de reproduire."""
    assert _service().code_acceptable(config.CODE_INITIAL) is None


def test_rien_n_est_protege_est_faux_des_qu_un_compte_a_un_code(base):
    u = _service()
    u.creer(base, "Inf. Amira", "infirmier")
    assert u.rien_n_est_protege(base) is True
    u.creer(base, "Dr Ben Salah", "senior", code="884411")
    assert u.rien_n_est_protege(base) is False


def test_un_compte_desactive_ne_compte_pas_comme_protection(base):
    """Un compte parti du service n'a plus de porte à défendre."""
    u = _service()
    parti = u.creer(base, "Dr Ben Salah", "senior", code="884411")
    autre = u.creer(base, "Dr Karaa", "senior", code="884412")
    u.desactiver(base, parti, utilisateur_id=autre)
    assert u.rien_n_est_protege(base) is False
    u.definir_code(base, autre, None, utilisateur_id=autre)
    assert u.rien_n_est_protege(base) is True


# --------------------------------------------------------------------------
# Le code qu'un administrateur pose pour quelqu'un d'autre
# --------------------------------------------------------------------------
# Sur le réseau, un compte sans code est refusé à l'entrée : il ne pourrait
# donc jamais entrer pour poser le sien. L'administrateur lui en donne un, le
# lui dit — et le compte en réclame un vrai à la première ouverture.

def test_un_compte_cree_avec_un_code_provisoire_le_reste(base):
    u = _service()
    identifiant = u.creer(base, "Inf. Amira", "infirmier", code="112233",
                          code_provisoire=True)
    assert u.par_id(base, identifiant)["code_provisoire"] == 1
    assert [c["nom"] for c in u.comptes_a_code_provisoire(base)] == ["Inf. Amira"]


def test_un_compte_cree_sans_le_dire_n_est_pas_provisoire(base):
    """La valeur par défaut ne change pas le comportement des appels existants."""
    u = _service()
    identifiant = u.creer(base, "Dr Karaa", "admin", code="884411")
    assert u.par_id(base, identifiant)["code_provisoire"] == 0


def test_un_compte_sans_code_n_est_pas_provisoire(base):
    """Provisoire qualifie un code ; sans code, il n'y a rien à qualifier."""
    u = _service()
    identifiant = u.creer(base, "Inf. Amira", "infirmier", code_provisoire=True)
    compte = u.par_id(base, identifiant)
    assert compte["pin"] is None
    assert compte["code_provisoire"] == 0


def test_la_personne_pose_le_sien_et_la_marque_tombe(base):
    u = _service()
    identifiant = u.creer(base, "Inf. Amira", "infirmier", code="112233",
                          code_provisoire=True)
    u.definir_code(base, identifiant, "445566", utilisateur_id=identifiant)
    compte = u.par_id(base, identifiant)
    assert compte["code_provisoire"] == 0
    assert u.code_correct("445566", compte["pin"])
    assert not u.code_correct("112233", compte["pin"])


def test_un_code_reinitialise_par_l_administrateur_redevient_provisoire(base):
    """Un code oublié qu'on remet est connu de deux personnes, comme le premier."""
    u = _service()
    admin = u.creer(base, "Dr Karaa", "admin", code="884411")
    amira = u.creer(base, "Inf. Amira", "infirmier", code="445566")
    assert u.par_id(base, amira)["code_provisoire"] == 0
    u.definir_code(base, amira, "778899", provisoire=True, utilisateur_id=admin)
    assert u.par_id(base, amira)["code_provisoire"] == 1


def test_retirer_le_code_efface_aussi_la_marque(base):
    u = _service()
    identifiant = u.creer(base, "Inf. Amira", "infirmier", code="112233",
                          code_provisoire=True)
    u.definir_code(base, identifiant, None, provisoire=True)
    compte = u.par_id(base, identifiant)
    assert compte["pin"] is None
    assert compte["code_provisoire"] == 0
