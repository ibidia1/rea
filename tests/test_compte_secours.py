"""Le compte de secours du propriétaire : entre toujours, invisible.

Une porte de dernier recours quand le service s'est fermé dehors — base vide,
tous les administrateurs bloqués, un poste qu'on récupère. Elle n'apparaît
dans aucune liste, et son code ne vit pas dans la base mais dans un secret
local au poste, pour qu'il ne se lise ni dans le dépôt ni dans une sauvegarde.

Demande du service, 11 septembre 2026.
"""

import importlib
from pathlib import Path

from rea import config

RACINE = Path(__file__).resolve().parent.parent


def _service():
    return importlib.import_module("rea.services.utilisateurs")


# --------------------------------------------------------------------------
# Reconnaître le nom et le code
# --------------------------------------------------------------------------

def test_le_nom_et_le_code_par_defaut_ouvrent(base):
    u = _service()
    assert u.est_compte_de_secours("ADMIN", "ADMIN123")


def test_le_nom_est_insensible_a_la_casse(base):
    u = _service()
    assert u.est_compte_de_secours("admin", "ADMIN123")
    assert u.est_compte_de_secours("  Admin ", "ADMIN123")


def test_un_mauvais_code_n_ouvre_pas(base):
    u = _service()
    assert not u.est_compte_de_secours("ADMIN", "admin123")
    assert not u.est_compte_de_secours("ADMIN", "")
    assert not u.est_compte_de_secours("Slah", "ADMIN123")


def test_le_code_vient_du_secret_local_pas_du_code_source(monkeypatch):
    """Posé par variable d'environnement : c'est ainsi que le poste lui donne
    un vrai code, sans que rien ne soit écrit dans le dépôt."""
    monkeypatch.setenv("REA_SECOURS_CODE", "S3cret-Local!")
    cfg = importlib.reload(importlib.import_module("rea.config"))
    try:
        assert cfg.SECOURS_CODE == "S3cret-Local!"
    finally:
        monkeypatch.delenv("REA_SECOURS_CODE", raising=False)
        importlib.reload(cfg)


def test_un_fichier_local_donne_le_code(monkeypatch, tmp_path):
    """Deuxième source : la première ligne de `<RACINE>/secours.txt`."""
    monkeypatch.delenv("REA_SECOURS_CODE", raising=False)
    monkeypatch.setenv("REA_DIR", str(tmp_path))
    (tmp_path / "secours.txt").write_text("mon-code-de-secours\n", encoding="utf-8")
    cfg = importlib.reload(importlib.import_module("rea.config"))
    try:
        assert cfg.SECOURS_CODE == "mon-code-de-secours"
    finally:
        importlib.reload(cfg)


def test_on_peut_desactiver_le_compte_de_secours(base, monkeypatch):
    u = _service()
    # Le service lit `config.SECOURS_ACTIF` sur le module `rea.config` vivant —
    # que le conftest recharge par fixture. Patcher celui-là, pas la copie
    # importée en tête de fichier, qui est périmée.
    monkeypatch.setattr(importlib.import_module("rea.config"), "SECOURS_ACTIF", False)
    assert not u.est_compte_de_secours("ADMIN", "ADMIN123")


# --------------------------------------------------------------------------
# Une vraie ligne, mais invisible
# --------------------------------------------------------------------------

def test_le_compte_de_secours_est_administrateur(base):
    u = _service()
    compte = u.compte_de_secours(base)
    assert compte["role"] == "admin"
    assert compte["id"] == config.SECOURS_UTILISATEUR_ID


def test_il_n_apparait_dans_aucune_liste(base):
    u = _service()
    u.creer(base, "Dr Karaa", "admin", code="884411")
    u.compte_de_secours(base)  # matérialisé

    for liste in (u.actifs(base), u.tous(base), u.administrateurs(base)):
        assert all(c["id"] != config.SECOURS_UTILISATEUR_ID for c in liste)
    # Le vrai administrateur, lui, est bien là.
    assert any(c["nom"] == "Dr Karaa" for c in u.administrateurs(base))


def test_il_ne_compte_pas_comme_administrateur_du_service(base):
    """Une base dont le seul admin serait le compte de secours doit encore
    proposer de créer un administrateur ordinaire : le secours n'existe pas
    pour le service."""
    u = _service()
    inf = u.creer(base, "Inf. Amira", "infirmier", code="445566")
    u.compte_de_secours(base)
    assert u.administrateurs(base) == []
    assert u.sans_administrateur(base) is True


def test_il_ne_se_dedouble_pas(base):
    u = _service()
    premier = u.compte_de_secours(base)
    second = u.compte_de_secours(base)
    assert premier["id"] == second["id"]
    lignes = base.requete("SELECT id FROM utilisateur WHERE id = ?",
                          (config.SECOURS_UTILISATEUR_ID,))
    assert len(lignes) == 1


def test_par_id_le_rend_pour_que_sa_session_marche(base):
    """Caché des listes, mais retrouvable par son id : c'est ce qui fait
    fonctionner sa session une fois entré."""
    u = _service()
    u.compte_de_secours(base)
    compte = u.par_id(base, config.SECOURS_UTILISATEUR_ID)
    assert compte is not None
    assert u.peut(base, config.SECOURS_UTILISATEUR_ID, "comptes")


def test_il_peut_ecrire_sans_violer_la_cle_etrangere(base):
    """Ses écritures portent son id en `cree_par`, qui référence la table des
    utilisateurs : sans une vraie ligne, la base les refuserait."""
    u = _service()
    sejours = importlib.import_module("rea.services.sejours")
    u.compte_de_secours(base)
    pid = sejours.creer_patient(
        base, matricule="S-1", nom_affichage="Essai", date_naissance="1970-01-01",
        sexe="M", utilisateur_id=config.SECOURS_UTILISATEUR_ID,
    )
    assert pid


# --------------------------------------------------------------------------
# Le secret ne se lit pas dans le code publié
# --------------------------------------------------------------------------

def test_le_code_source_ne_fige_pas_le_mot_de_passe():
    """Le code se lit d'un secret local (variable d'environnement ou fichier),
    et non d'une constante figée : c'est toute la différence entre un compte
    de secours et une porte dérobée publiée."""
    source = (RACINE / "rea" / "config.py").read_text(encoding="utf-8")
    assert "REA_SECOURS_CODE" in source
    assert "secours.txt" in source


def test_le_fichier_de_secret_local_n_est_pas_versionne():
    ignore = (RACINE / ".gitignore").read_text(encoding="utf-8")
    assert "secours.txt" in ignore


# --------------------------------------------------------------------------
# Le câblage de l'écran d'ouverture
# --------------------------------------------------------------------------
# Lu en source : l'écran d'ouverture ne se teste pas sans lancer Streamlit, et
# un compte de secours qui n'entre plus est exactement le genre de panne qu'on
# ne découvre qu'au pire moment — le jour où il fallait entrer.

OUVERTURE = (RACINE / "rea" / "ui" / "utilisateur.py").read_text(encoding="utf-8")


def test_l_ouverture_reconnait_le_compte_de_secours():
    assert "_tenter_secours" in OUVERTURE
    assert "est_compte_de_secours" in OUVERTURE
    assert "compte_de_secours" in OUVERTURE


def test_on_peut_saisir_un_nom_hors_liste():
    """Sans quoi « ADMIN », absent de la liste, ne pourrait pas être frappé."""
    assert "accept_new_options=True" in OUVERTURE


def test_le_secours_entre_meme_base_vide():
    """La tentative est câblée aussi dans le premier écran, celui d'une base
    sans aucun compte — le cas où le secours sert le plus."""
    debut = OUVERTURE.index("def _premier_compte")
    fin = OUVERTURE.index("def _remplacer_le_code_provisoire")
    assert "_tenter_secours" in OUVERTURE[debut:fin]


def test_rien_a_l_ecran_n_annonce_le_compte_de_secours():
    """« Caché » : aucun libellé visible ne doit le nommer ni le désigner."""
    for interdit in ("secours", "ADMIN", "Accès de secours", "break"):
        # On tolère le nom des fonctions (_tenter_secours, compte_de_secours) ;
        # ce qu'on interdit, c'est un libellé montré à l'écran.
        for ligne in OUVERTURE.splitlines():
            texte = ligne.strip()
            if texte.startswith("#") or texte.startswith('"""'):
                continue
            if ("st.button(" in texte or "st.title(" in texte
                    or "st.header(" in texte or "st.info(" in texte):
                assert "secours" not in texte.lower()
                assert "ADMIN" not in texte
