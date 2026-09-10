"""Essayer un rôle sans changer d'identité (SPEC §2.5).

Un administrateur qui met le service en route veut vérifier ce que chacun
trouve à son écran. Les deux seuls moyens jusqu'ici étaient mauvais : créer un
compte d'essai par rôle — qui encombre la liste d'ouverture de comptes qui ne
soignent personne — ou demander son code à quelqu'un, ce qui apprend au
service à se prêter les codes.

Ce que ces tests tiennent, c'est la seule propriété qui compte vraiment :
**l'essai change ce qu'on voit, jamais qui signe.** Une observation signée du
nom d'un infirmier qui ne l'a pas écrite serait un faux dans un dossier
médical.
"""

import importlib
import pathlib

import pytest


def _ui():
    return importlib.import_module("rea.ui.utilisateur")


def _session(module, role):
    """Un compte connecté, sans passer par Streamlit."""
    module.st.session_state.clear()
    module.st.session_state["utilisateur_id"] = "u1"
    module.st.session_state["utilisateur_nom"] = "Dr Karaa"
    module.st.session_state["utilisateur_role"] = role


def _source(module: str) -> str:
    return (pathlib.Path(__file__).resolve().parent.parent / "rea" / "ui"
            / f"{module}.py").read_text(encoding="utf-8")


# -- ce que l'essai change --------------------------------------------------

def test_l_essai_change_les_droits_vus_par_les_ecrans(base):
    ui = _ui()
    _session(ui, "admin")
    assert ui.peut("comptes") is True
    ui.essayer_role("infirmier")
    assert ui.role_courant() == "infirmier"
    assert ui.peut("comptes") is False        # un infirmier ne gère pas les comptes
    assert ui.peut("dossier_ecrire") is False  # ni ne modifie le prescrit
    assert ui.peut("constantes") is True       # mais note la surveillance


def test_quitter_l_essai_rend_ses_droits(base):
    ui = _ui()
    _session(ui, "admin")
    ui.essayer_role("surveillant")
    assert ui.peut("comptes") is False
    ui.essayer_role(None)
    assert ui.role_courant() == "admin"
    assert ui.peut("comptes") is True


# -- ce que l'essai ne change jamais ---------------------------------------

def test_l_identite_qui_signe_ne_change_pas(base):
    """La propriété qui compte. Tout ce qui s'écrit pendant l'essai reste
    signé par l'administrateur."""
    ui = _ui()
    _session(ui, "admin")
    ui.essayer_role("infirmier")
    assert ui.st.session_state["utilisateur_id"] == "u1"
    assert ui.nom_utilisateur_courant() == "Dr Karaa"
    assert ui.role_reel() == "admin"


def test_seul_un_administrateur_peut_essayer(base):
    """L'essai ne doit jamais devenir un moyen de gagner des droits."""
    ui = _ui()
    _session(ui, "senior")
    with pytest.raises(PermissionError):
        ui.essayer_role("admin")
    assert ui.role_courant() == "senior"


def test_un_role_inconnu_est_refuse(base):
    ui = _ui()
    _session(ui, "admin")
    with pytest.raises(ValueError):
        ui.essayer_role("chirurgien")


def test_l_essai_ne_donne_jamais_plus_que_le_compte(base):
    """Un administrateur les a tous : quel que soit le rôle essayé, l'essai ne
    peut que retirer des droits."""
    ui = _ui()
    droits = importlib.import_module("rea.domaine.droits")
    _session(ui, "admin")
    tous = droits.droits_du_role("admin")
    for role in droits.roles():
        ui.essayer_role(role)
        assert droits.droits_du_role(ui.role_courant()) <= tous, role


def test_changer_d_utilisateur_efface_l_essai(base):
    """Sinon le compte suivant hériterait d'un essai qu'il n'a pas demandé."""
    ui = _ui()
    _session(ui, "admin")
    ui.essayer_role("infirmier")
    assert "role_essai" in _source("utilisateur")
    # `changer_utilisateur` appelle st.rerun() : on vérifie la liste des clés.
    debut = _source("utilisateur").index("def changer_utilisateur")
    assert '"role_essai"' in _source("utilisateur")[debut:debut + 400]


# -- le rappel permanent ----------------------------------------------------

def test_le_bandeau_d_essai_est_permanent_et_dit_qui_signe():
    """Un message qui passe se serait oublié : on prescrit, et l'écriture
    porte le nom de l'administrateur sur une ligne qu'un infirmier semblait
    avoir faite."""
    source = _source("bandeau")
    assert "Essai en cours" in source
    assert "jamais qui signe" in source
    assert "Quitter l'essai" in source


def test_l_acces_admin_est_dans_la_bande_du_haut():
    """La barre latérale se replie sur un téléphone ; l'administration doit
    rester à portée depuis n'importe quel écran."""
    source = _source("bandeau")
    assert 'st.button("Admin"' in source
    assert 'aller_a("administration")' in source
    # Rendue avant tout le reste, donc en haut de la page.
    entree = (pathlib.Path(__file__).resolve().parent.parent
              / "rea_app.py").read_text(encoding="utf-8")
    assert entree.index("bandeau_ui.haut_de_page()") < entree.index("with st.sidebar")
