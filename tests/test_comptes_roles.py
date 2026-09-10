"""Comptes, rôles et code d'accès (SPEC §2.5).

Ce que ces tests protègent, dans l'ordre d'importance :

* **on ne se ferme pas la porte de l'extérieur** : retirer le dernier compte
  capable de gérer les comptes laisserait le service sans aucun moyen d'en
  créer un autre ;
* un compte qui part est **désactivé, jamais effacé** — sinon des années de
  prescriptions deviennent anonymes (règle de conception 2) ;
* le code d'accès n'est **jamais gardé en clair** : une base copiée sur une
  clé rendrait sinon tous les codes du service, et les gens les réutilisent
  ailleurs ;
* un rôle inconnu n'a **aucun droit** — une faute de frappe dans le fichier
  de rôles doit fermer des portes, pas en ouvrir.
"""

import pytest

from rea.domaine import droits
from rea.services import utilisateurs


def _admin(base, nom="Chef"):
    return utilisateurs.creer(base, nom, "admin")


# --- la table des droits ---------------------------------------------------

def test_le_referentiel_des_roles_est_coherent():
    """Un droit mal orthographié ne lève rien à l'exécution : il retire
    seulement l'accès, et personne ne fait le rapprochement."""
    assert droits.verifier_referentiel() == []


def test_chaque_role_a_les_droits_annonces():
    assert droits.peut("senior", "protocoles")
    assert not droits.peut("resident", "protocoles")
    assert not droits.peut("surveillant", "protocoles")
    assert droits.peut("surveillant", "dossier_ecrire")
    assert droits.peut("surveillant", "supervision")
    assert not droits.peut("infirmier", "dossier_ecrire")
    assert droits.peut("infirmier", "dossier_lire")
    assert droits.peut("infirmier", "administrations")
    assert droits.peut("admin", "comptes")


def test_un_role_inconnu_n_a_aucun_droit():
    assert droits.droits_du_role("visiteur") == frozenset()
    assert droits.droits_du_role(None) == frozenset()
    assert not droits.peut("visiteur", "dossier_lire")


# --- créer, modifier ------------------------------------------------------

def test_creer_un_compte_et_lire_son_role(base):
    uid = utilisateurs.creer(base, "Inf. Amel", "infirmier")
    assert utilisateurs.role_de(base, uid) == "infirmier"
    assert utilisateurs.peut(base, uid, "administrations")
    assert not utilisateurs.peut(base, uid, "dossier_ecrire")


def test_un_nom_deja_pris_est_refuse(base):
    utilisateurs.creer(base, "Dr Ben Salah", "senior")
    with pytest.raises(ValueError, match="existe déjà"):
        utilisateurs.creer(base, "dr ben salah", "resident")


def test_un_role_inconnu_est_refuse_a_la_creation(base):
    with pytest.raises(ValueError, match="Rôle inconnu"):
        utilisateurs.creer(base, "Quelqu'un", "chef_supreme")


def test_un_nom_vide_est_refuse(base):
    with pytest.raises(ValueError, match="obligatoire"):
        utilisateurs.creer(base, "   ", "infirmier")


# --- le dernier administrateur --------------------------------------------

def test_on_ne_peut_pas_desactiver_le_dernier_gestionnaire_de_comptes(base):
    uid = _admin(base)
    utilisateurs.creer(base, "Inf. Amel", "infirmier")
    with pytest.raises(ValueError, match="dernier compte"):
        utilisateurs.desactiver(base, uid)


def test_on_ne_peut_pas_lui_retirer_son_role_non_plus(base):
    """L'autre façon de se fermer la porte : le rétrograder."""
    uid = _admin(base)
    with pytest.raises(ValueError, match="dernier compte"):
        utilisateurs.modifier_role(base, uid, "infirmier")


def test_avec_deux_administrateurs_on_peut_en_retirer_un(base):
    premier = _admin(base, "Chef")
    _admin(base, "Adjoint")
    utilisateurs.desactiver(base, premier)
    assert premier not in {u["id"] for u in utilisateurs.actifs(base)}


def test_un_compte_desactive_garde_ses_ecritures(base):
    """On désactive, on n'efface pas : sinon le journal d'audit perd son sens."""
    _admin(base, "Chef")
    autre = _admin(base, "Adjoint")
    utilisateurs.desactiver(base, autre)
    compte = utilisateurs.par_id(base, autre)
    assert compte is not None and compte["nom"] == "Adjoint"
    assert compte["actif"] == 0


# --- le code d'accès -------------------------------------------------------

def test_le_code_n_est_jamais_garde_en_clair(base):
    uid = utilisateurs.creer(base, "Dr Ben Salah", "senior", code="4271")
    compte = utilisateurs.par_id(base, uid)
    assert compte["pin"] and "4271" not in compte["pin"]
    assert compte["pin"].startswith("pbkdf2$")


def test_le_bon_code_est_reconnu_et_le_mauvais_refuse(base):
    uid = utilisateurs.creer(base, "Dr Ben Salah", "senior", code="4271")
    empreinte = utilisateurs.par_id(base, uid)["pin"]
    assert utilisateurs.code_correct("4271", empreinte)
    assert not utilisateurs.code_correct("4272", empreinte)
    assert not utilisateurs.code_correct("", empreinte)


def test_deux_comptes_au_meme_code_ont_des_empreintes_differentes(base):
    """Le sel : sans lui, deux codes identiques se voient dans la base, et
    l'un trouvé donne l'autre."""
    a = utilisateurs.creer(base, "Un", "infirmier", code="0000")
    b = utilisateurs.creer(base, "Deux", "infirmier", code="0000")
    assert utilisateurs.par_id(base, a)["pin"] != utilisateurs.par_id(base, b)["pin"]


def test_un_compte_sans_code_n_accepte_aucune_verification(base):
    """Sans code posé, `code_correct` répond non — c'est l'ouverture qui
    décide de ne pas demander, pas cette fonction de dire oui à tout."""
    uid = utilisateurs.creer(base, "Sans code", "infirmier")
    assert utilisateurs.par_id(base, uid)["pin"] is None
    assert not utilisateurs.code_correct("", None)
    assert not utilisateurs.code_correct("1234", None)


def test_poser_puis_retirer_un_code(base):
    uid = utilisateurs.creer(base, "Inf. Amel", "infirmier")
    utilisateurs.definir_code(base, uid, "9182")
    assert utilisateurs.code_correct("9182", utilisateurs.par_id(base, uid)["pin"])
    utilisateurs.definir_code(base, uid, None)
    assert utilisateurs.par_id(base, uid)["pin"] is None


# --- le verrou après plusieurs essais ratés --------------------------------
#
# Mesuré sur ce poste : un essai de code coûte 47 ms, donc les 10 000 codes à
# quatre chiffres tombent en huit minutes. Tant que l'application n'écoutait
# que la boucle locale, il fallait s'asseoir devant le clavier. Depuis qu'elle
# est joignable sur le Wi-Fi du service, c'est n'importe quel téléphone du
# couloir qui peut les enchaîner (demande du service, 10 septembre).

def test_le_compte_se_bloque_apres_plusieurs_essais_rates(base):
    from rea import config

    utilisateurs.oublier_echecs("Dr Ben Salah")
    for _ in range(config.ESSAIS_AVANT_BLOCAGE):
        assert utilisateurs.blocage_restant("Dr Ben Salah") == 0
        utilisateurs.noter_echec("Dr Ben Salah")
    assert utilisateurs.blocage_restant("Dr Ben Salah") > 0
    utilisateurs.oublier_echecs("Dr Ben Salah")


def test_une_entree_reussie_efface_l_ardoise(base):
    utilisateurs.noter_echec("Inf. Amel")
    utilisateurs.noter_echec("Inf. Amel")
    utilisateurs.oublier_echecs("Inf. Amel")
    assert utilisateurs.blocage_restant("Inf. Amel") == 0


def test_le_blocage_ne_depend_pas_de_la_casse(base):
    """Sinon il suffit de taper le nom en majuscules pour repartir à zéro."""
    from rea import config

    utilisateurs.oublier_echecs("inf. amel")
    for _ in range(config.ESSAIS_AVANT_BLOCAGE):
        utilisateurs.noter_echec("Inf. Amel")
    assert utilisateurs.blocage_restant("INF. AMEL") > 0
    utilisateurs.oublier_echecs("inf. amel")


# --- la solidité du code ---------------------------------------------------

def test_un_code_trop_court_est_refuse():
    assert utilisateurs.code_acceptable("1234")
    assert utilisateurs.code_acceptable("") == "Le code est obligatoire."
    assert utilisateurs.code_acceptable("492817") is None


def test_les_codes_les_plus_evidents_sont_refuses():
    for evident in ("000000", "123456", "111111"):
        assert utilisateurs.code_acceptable(evident)


# --- les comptes sans code -------------------------------------------------

def test_les_comptes_sans_code_sont_reperables(base):
    """C'est cette liste que l'ouverture affiche en rouge quand
    l'application écoute sur le réseau."""
    utilisateurs.creer(base, "Sans", "infirmier")
    utilisateurs.creer(base, "Avec", "infirmier", code="492817")
    sans = [u["nom"] for u in utilisateurs.comptes_sans_code(base)]
    assert sans == ["Sans"]
