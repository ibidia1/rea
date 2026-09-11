"""L'état des pupilles au relevé infirmier : diamètre et réactivité.

Les deux ensemble — une pupille à 5 mm réactive n'est pas une pupille à 5 mm
aréactive — et relevés comme un état, jamais comme un nombre : « aréactive »
ne se moyenne pas. Demande du service, 11 septembre 2026.
"""

import importlib
from pathlib import Path

from rea import listes

RACINE = Path(__file__).resolve().parent.parent


def _service():
    return importlib.import_module("rea.services.constantes")


def test_les_reactivites_viennent_du_referentiel():
    codes = listes.codes(listes.REACTIVITES_PUPILLE)
    assert codes == ("reactive", "lente", "areactive")


def test_le_diametre_et_la_reactivite_voyagent_ensemble():
    c = _service()
    assert c.etat_pupille("3", "reactive") == "3|reactive"
    assert c.lire_etat_pupille("3|reactive") == ("3", "reactive")


def test_l_un_ou_l_autre_peut_manquer():
    c = _service()
    assert c.lire_etat_pupille(c.etat_pupille("4", None)) == ("4", None)
    assert c.lire_etat_pupille(c.etat_pupille("", "areactive")) == ("", "areactive")


def test_rien_a_noter_ne_s_ecrit_pas():
    c = _service()
    assert c.etat_pupille("", None) is None
    assert c.etat_pupille("  ", "") is None


def test_la_pupille_est_un_etat_pas_un_recueil():
    """Elle ne se totalise jamais : ni volume, ni moyenne."""
    c = _service()
    assert c.est_recueil(c.PUPILLES[0][0]) is False


def test_les_deux_pupilles_sont_relevees(base):
    """Écrites comme état (valeur_texte), relues heure par heure."""
    c = _service()
    sejours = importlib.import_module("rea.services.sejours")
    pid = sejours.creer_patient(base, matricule="P-1", nom_affichage="K. A.",
                                date_naissance="1970-01-01", sexe="M")
    sid = sejours.creer_sejour(base, patient_id=pid, lit_admission=1,
                               date_admission="2026-09-11")
    droite, gauche = c.PUPILLES[0][0], c.PUPILLES[1][0]
    c.enregistrer(base, sid, "2026-09-11", 8, {},
                  textes={droite: c.etat_pupille("3", "reactive"),
                          gauche: c.etat_pupille("5", "areactive")})
    etats = c.etats_du_jour(base, sid, "2026-09-11")
    assert c.lire_etat_pupille(etats[8][droite]) == ("3", "reactive")
    assert c.lire_etat_pupille(etats[8][gauche]) == ("5", "areactive")


# --------------------------------------------------------------------------
# Ce que les écrans doivent porter (lu en source)
# --------------------------------------------------------------------------

def test_le_poste_infirmier_releve_les_pupilles():
    src = (RACINE / "rea" / "ui" / "infirmier.py").read_text(encoding="utf-8")
    assert "def _pupilles(" in src
    assert "_pupilles(patient, heure, etats_saisis)" in src


def test_la_surveillance_affiche_les_pupilles():
    src = (RACINE / "rea" / "ui" / "surveillance.py").read_text(encoding="utf-8")
    assert "PUPILLES" in src
    assert "_abrege_pupille" in src
