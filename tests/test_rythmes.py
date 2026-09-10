"""Les rythmes de prise, de une fois par jour à toutes les heures
(demande du service, 10 septembre 2026).

Ces horaires ne sont plus dans `config.py` mais dans
`referentiels/rythmes.json` : l'heure d'une prise est une habitude de
service, pas une règle de programme (règle R2). Ce fichier vérifie que le
domaine les y lit vraiment, et que la liste reste cohérente — un rythme
dont l'intervalle ne divise pas la journée ne se donne pas.
"""

import importlib

from rea import listes
from rea.domaine import prescription as p

# Rythmes réguliers : code -> nombre de prises attendu dans la journée.
REGULIERS = {
    "x1/j": 1,
    "x2/j": 2,
    "x3/j": 3,
    "x4/j": 4,
    "x6/j": 6,
    "x8/j": 8,
    "x12/j": 12,
    "x24/j": 24,
}


def test_les_nouveaux_rythmes_existent_dans_la_liste():
    codes = listes.codes(listes.RYTHMES)
    for code in REGULIERS:
        assert code in codes, f"{code} absent de la liste déroulante"


def test_chaque_rythme_regulier_donne_le_bon_nombre_de_prises():
    for code, prises in REGULIERS.items():
        assert len(p.horaires_pour_rythme(code)) == prises, code


def test_x24j_est_bien_toutes_les_heures():
    assert p.horaires_pour_rythme("x24/j") == tuple(range(1, 25))


def test_x8j_toutes_les_trois_heures():
    assert p.horaires_pour_rythme("x8/j") == (3, 6, 9, 12, 15, 18, 21, 24)


def test_x12j_toutes_les_deux_heures():
    assert p.horaires_pour_rythme("x12/j") == (2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24)


def test_les_horaires_sont_dans_la_journee_et_ordonnes():
    for code in listes.codes(listes.RYTHMES):
        heures = p.horaires_pour_rythme(code)
        assert list(heures) == sorted(heures), code
        assert len(set(heures)) == len(heures), f"{code} : heure en double"
        for h in heures:
            assert 1 <= h <= 24, f"{code} : {h} hors de la journée"


def test_les_prises_sont_regulierement_espacees():
    """Un antibiotique x3/j se donne toutes les 8 h, pas quand ça tombe.

    Les deux exceptions sont voulues et calées sur la vie du service :
    ×1/j propose 8 h (l'heure de la visite) et ×2/j 8 h − 20 h.
    """
    for code, prises in REGULIERS.items():
        if code in ("x1/j", "x2/j"):
            continue
        heures = p.horaires_pour_rythme(code)
        intervalle = 24 // prises
        assert heures == tuple(range(intervalle, 25, intervalle)), code


def test_les_horaires_viennent_du_referentiel_pas_du_code():
    """Règle R2 : changer le fichier change le logiciel, sans reprogrammer.

    Les modules sont retrouvés ici et non en tête de fichier : les fixtures
    rechargent `rea.*` entre deux tests, et le domaine lit le référentiel
    par `sys.modules` au moment de l'appel. Remplacer le `charger` d'un
    module périmé ne remplacerait rien du tout.
    """
    domaine = importlib.import_module("rea.domaine.prescription")
    refs = importlib.import_module("rea.referentiels")
    domaine._horaires_du_referentiel.cache_clear()
    vrai_charger = refs.charger

    def faux_charger(nom, *args, **kwargs):
        if nom == "rythmes":
            return [["x3/j", "×3/j", [7, 15, 23]]]
        return vrai_charger(nom, *args, **kwargs)

    refs.charger = faux_charger
    try:
        assert domaine.horaires_pour_rythme("x3/j") == (7, 15, 23)
    finally:
        refs.charger = vrai_charger
        domaine._horaires_du_referentiel.cache_clear()


def test_config_ne_porte_plus_les_horaires():
    config = importlib.import_module("rea.config")
    assert not hasattr(config, "HORAIRES_PAR_RYTHME")


def test_un_rythme_inconnu_ne_fait_pas_tomber_l_ecran():
    assert p.horaires_pour_rythme("x5/j") == ()
    assert p.horaires_pour_rythme(None) == ()


# --------------------------------------------------------------------------
# Affichage : douze horaires collés au nom du produit ne se lisent pas
# --------------------------------------------------------------------------

def test_jusqu_a_six_prises_les_horaires_sont_ecrits_en_entier():
    assert p.horaires_affiches("x2/j") == "8h-20h"
    assert p.horaires_affiches("x6/j") == "4h-8h-12h-16h-20h-24h"


def test_au_dela_de_six_prises_la_liste_se_replie():
    assert p.horaires_affiches("x8/j") == "toutes les 3h dès 3h"
    assert p.horaires_affiches("x12/j") == "toutes les 2h dès 2h"


def test_une_prise_horaire_se_dit_en_trois_mots():
    assert p.horaires_affiches("x24/j") == "toutes les heures"


def test_un_horaire_irregulier_reste_ecrit_en_entier():
    """Replier suppose un pas constant ; sans lui, on n'invente rien."""
    assert p.horaires_affiches("x8/j", "1,3,4,9,13,17,22") == "1h-3h-4h-9h-13h-17h-22h"


def test_la_ligne_de_pancarte_reste_courte_a_toutes_les_heures():
    ligne = {
        "produit": "Insuline rapide", "voie": "SC", "rythme": "x24/j",
        "dose": 4, "unite": "UI", "date_debut": "2026-09-10", "statut": "active",
    }
    _, produit, _ = p.parties_ligne(ligne, "2026-09-10")
    assert produit == "Insuline rapide (toutes les heures)"
