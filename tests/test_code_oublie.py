"""Un code perdu, et la personne ne peut plus entrer.

Elle ne peut pas le remettre elle-même — ce serait une porte ouverte à qui
saurait un nom. Elle dépose une **demande**, que l'administrateur voit et à
laquelle il répond : c'est lui qui sait si la personne devant lui est bien
celle du compte. Le logiciel, lui, ne voit qu'un nom dans une liste.

Demande du service, 11 septembre 2026.
"""

import importlib

import pytest

from rea import config


def _service():
    return importlib.import_module("rea.services.utilisateurs")


def test_une_demande_se_depose_et_se_retrouve(base):
    u = _service()
    amira = u.creer(base, "Inf. Amira", "infirmier", code="445566")
    u.demander_un_code(base, amira)
    demandes = u.demandes_de_code(base)
    assert [d["nom"] for d in demandes] == ["Inf. Amira"]
    assert demandes[0]["etat"] == u.EN_ATTENTE


def test_appuyer_trois_fois_ne_donne_pas_trois_demandes(base):
    """Trois lignes identiques à traiter, ce serait trois fois le même
    travail pour l'administrateur."""
    u = _service()
    amira = u.creer(base, "Inf. Amira", "infirmier", code="445566")
    premiere = u.demander_un_code(base, amira)
    assert u.demander_un_code(base, amira) == premiere
    assert len(u.demandes_de_code(base)) == 1


def test_un_compte_desactive_ne_demande_rien(base):
    u = _service()
    admin = u.creer(base, "Dr Karaa", "admin", code="884411")
    parti = u.creer(base, "Inf. Amira", "infirmier", code="445566")
    u.desactiver(base, parti, utilisateur_id=admin)
    with pytest.raises(ValueError, match="introuvable"):
        u.demander_un_code(base, parti)


def test_la_remise_a_zero_rend_le_code_de_depart(base):
    u = _service()
    admin = u.creer(base, "Dr Karaa", "admin", code="884411")
    amira = u.creer(base, "Inf. Amira", "infirmier", code="445566")
    demande = u.demander_un_code(base, amira)

    nom = u.reinitialiser_le_code(base, demande, utilisateur_id=admin)
    assert nom == "Inf. Amira"
    compte = u.par_id(base, amira)
    assert u.code_correct(config.CODE_INITIAL, compte["pin"])
    assert not u.code_correct("445566", compte["pin"])


def test_le_code_remis_est_provisoire(base):
    """Il est écrit dans le logiciel, donc public : la personne en choisira
    un vrai dès son entrée, et rien ne s'ouvrira avant."""
    u = _service()
    admin = u.creer(base, "Dr Karaa", "admin", code="884411")
    amira = u.creer(base, "Inf. Amira", "infirmier", code="445566")
    u.reinitialiser_le_code(base, u.demander_un_code(base, amira),
                            utilisateur_id=admin)
    assert u.par_id(base, amira)["code_provisoire"] == 1
    assert [c["nom"] for c in u.comptes_a_code_provisoire(base)] == ["Inf. Amira"]


def test_la_remise_a_zero_leve_le_blocage(base):
    """Sans cela, quelqu'un qui s'est bloqué en cherchant son code recevrait
    un nouveau code et se verrait quand même refuser l'entrée pendant dix
    minutes — le temps de rappeler l'administrateur pour lui dire que ça ne
    marche pas."""
    u = _service()
    admin = u.creer(base, "Dr Karaa", "admin", code="884411")
    amira = u.creer(base, "Inf. Amira", "infirmier", code="445566")
    for _ in range(config.ESSAIS_AVANT_BLOCAGE):
        u.noter_echec("Inf. Amira")
    assert u.blocage_restant("Inf. Amira") > 0

    u.reinitialiser_le_code(base, u.demander_un_code(base, amira),
                            utilisateur_id=admin)
    assert u.blocage_restant("Inf. Amira") == 0


def test_la_demande_traitee_quitte_la_liste(base):
    u = _service()
    admin = u.creer(base, "Dr Karaa", "admin", code="884411")
    amira = u.creer(base, "Inf. Amira", "infirmier", code="445566")
    demande = u.demander_un_code(base, amira)
    u.reinitialiser_le_code(base, demande, utilisateur_id=admin)
    assert u.demandes_de_code(base) == []


def test_une_demande_ne_se_traite_pas_deux_fois(base):
    """Deux administrateurs devant le même écran ne doivent pas remettre le
    code deux fois : le second geste ne doit rien faire."""
    u = _service()
    admin = u.creer(base, "Dr Karaa", "admin", code="884411")
    amira = u.creer(base, "Inf. Amira", "infirmier", code="445566")
    demande = u.demander_un_code(base, amira)
    u.reinitialiser_le_code(base, demande, utilisateur_id=admin)
    with pytest.raises(ValueError, match="déjà été traitée"):
        u.reinitialiser_le_code(base, demande, utilisateur_id=admin)


def test_une_demande_refusee_quitte_la_liste_sans_toucher_au_code(base):
    """L'administrateur a vu et a dit non. Le code ne bouge pas."""
    u = _service()
    admin = u.creer(base, "Dr Karaa", "admin", code="884411")
    amira = u.creer(base, "Inf. Amira", "infirmier", code="445566")
    demande = u.demander_un_code(base, amira)
    u.refuser_la_demande(base, demande, utilisateur_id=admin)

    assert u.demandes_de_code(base) == []
    assert u.code_correct("445566", u.par_id(base, amira)["pin"])


def test_une_demande_refusee_reste_en_base(base):
    """Trois demandes refusées sur le même compte en une semaine ne se lisent
    pas comme un code oublié trois fois."""
    u = _service()
    admin = u.creer(base, "Dr Karaa", "admin", code="884411")
    amira = u.creer(base, "Inf. Amira", "infirmier", code="445566")
    demande = u.demander_un_code(base, amira)
    u.refuser_la_demande(base, demande, utilisateur_id=admin)
    ligne = base.une_ligne("SELECT * FROM demande_code WHERE id = ?", (demande,))
    assert ligne["etat"] == u.REFUSEE
    assert ligne["traitee_par"] == admin


def test_apres_la_remise_a_zero_la_personne_entre_et_choisit_son_code(base):
    """Le parcours complet, bout à bout."""
    u = _service()
    admin = u.creer(base, "Dr Karaa", "admin", code="884411")
    amira = u.creer(base, "Inf. Amira", "infirmier", code="445566")

    u.reinitialiser_le_code(base, u.demander_un_code(base, amira),
                            utilisateur_id=admin)
    compte = u.par_id(base, amira)
    assert u.code_correct(config.CODE_INITIAL, compte["pin"])

    u.definir_code(base, amira, "778899", utilisateur_id=amira)
    compte = u.par_id(base, amira)
    assert u.code_correct("778899", compte["pin"])
    assert not u.code_correct(config.CODE_INITIAL, compte["pin"])
    assert compte["code_provisoire"] == 0


# --------------------------------------------------------------------------
# Ce que les écrans doivent porter
# --------------------------------------------------------------------------
# Lus en source : un bouton qui disparaît d'un écran Streamlit ne casse aucun
# test, et c'est ainsi qu'un tableau entier était tombé sans qu'un seul des
# mille tests s'en aperçoive.

from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
ACCUEIL = (RACINE / "rea" / "ui" / "utilisateur.py").read_text(encoding="utf-8")
COMPTES = (RACINE / "rea" / "ui" / "comptes.py").read_text(encoding="utf-8")
APPLI = (RACINE / "rea_app.py").read_text(encoding="utf-8")


def test_l_accueil_propose_le_code_oublie():
    assert "J'ai oublié mon code d'accès" in ACCUEIL
    assert "demander_un_code" in ACCUEIL


def test_l_accueil_porte_l_acces_admin_avant_d_entrer():
    """En haut à droite de l'écran d'ouverture, pas une fois connecté :
    l'administrateur qui vient débloquer un collègue n'a pas de raison de
    traverser l'application d'abord."""
    assert "Accès admin" in ACCUEIL
    assert "_entete_accueil" in ACCUEIL


def test_l_acces_admin_ne_dispense_pas_du_code():
    """Il ne fait que filtrer la liste des noms. Une porte qui s'ouvrirait
    d'un clic ne serait pas une porte."""
    debut = ACCUEIL.index("def _entete_accueil")
    fin = ACCUEIL.index("def selecteur")
    entete = ACCUEIL[debut:fin]
    assert "_entrer(" not in entete
    assert "utilisateur_id" not in entete


def test_l_administrateur_confirme_avant_de_remettre_un_code():
    """Le geste donne un code connu de tous à un compte qui peut valoir un
    accès au dossier : deux clics, et le second dit ce qui va se passer."""
    assert "Confirmer la remise à zéro" in COMPTES
    assert "Oui, remettre le code à zéro" in COMPTES
    assert "Annuler" in COMPTES
    # Le bouton de confirmation est le seul à appeler le service.
    avant = COMPTES.split("Confirmer la remise à zéro")[0]
    assert "reinitialiser_le_code" not in avant


def test_la_confirmation_annonce_le_code_et_le_deblocage():
    assert "CODE_INITIAL" in COMPTES
    assert "blocage des essais ratés sera également levé" in COMPTES


def test_la_barre_laterale_porte_se_deconnecter():
    assert 'st.button("Se déconnecter"' in APPLI


def test_la_barre_laterale_est_depliee_par_defaut():
    """Repliée, elle se réduit à une flèche que personne ne cherche."""
    assert 'initial_sidebar_state="expanded"' in APPLI


def test_la_deconnexion_oublie_le_mode_admin():
    """Sinon l'écran d'ouverture resterait filtré aux administrateurs pour la
    personne suivante, qui ne trouverait plus son nom."""
    debut = ACCUEIL.index("def changer_utilisateur")
    assert "accueil_admin" in ACCUEIL[debut:debut + 500]


def test_la_version_se_lit_sur_l_ecran_d_ouverture():
    """Le seul écran sans barre latérale, et celui qu'on regarde quand on
    appelle pour dire que quelque chose manque. « Je ne vois pas la barre
    latérale » n'a pas de réponse tant qu'on ignore quelle version tourne :
    le service a signalé le 11 septembre une barre absente, corrigée le matin
    même sur une version que le poste n'avait pas."""
    assert "config.VERSION" in ACCUEIL
    assert "config.VERSION" in APPLI


def test_la_version_livree_existe_et_se_lit():
    from rea import config
    fichier = RACINE / "VERSION"
    assert fichier.exists(), "le fichier VERSION est livré avec le code"
    assert config.VERSION == fichier.read_text(encoding="utf-8").strip()
    assert config.VERSION != "inconnue"


def test_la_barre_reste_depliee_sur_un_ecran_etroit():
    """Mesuré : sans `initial_sidebar_state`, à 430 px la barre sortait de
    l'écran (x = −300, largeur 0) et aucune flèche ne permettait de la
    rouvrir. C'est l'écran que le service avait sous les yeux."""
    assert 'initial_sidebar_state="expanded"' in APPLI
    # Et l'appel doit être le premier geste Streamlit du fichier : après un
    # autre, Streamlit refuse la configuration de page.
    assert APPLI.index("st.set_page_config") < APPLI.index("theme.appliquer()")
