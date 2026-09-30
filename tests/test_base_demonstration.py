"""La base de démonstration : complète, à part, et incapable d'effacer une
vraie base.

Elle s'ouvre par sa propre icône et vit dans son propre dossier. Ce qui est
vérifié ici : qu'elle contient bien de quoi parcourir tout le logiciel — deux
patients hospitalisés, un service qui tourne, un passé pour la Recherche —
et que son nettoyage quotidien ne peut pas toucher la base du service, même
lancé au mauvais endroit.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))


@pytest.fixture()
def demo(base):
    import base_demonstration

    return base_demonstration.construire(base)


def test_deux_patients_hospitalises_et_un_passe(base, demo):
    ouverts = base.requete("SELECT lit_admission FROM sejour WHERE date_sortie IS NULL "
                           "AND supprime = 0 ORDER BY lit_admission")
    assert [s["lit_admission"] for s in ouverts] == [1, 2]
    clos = base.une_ligne("SELECT COUNT(*) n FROM sejour WHERE date_sortie IS NOT NULL")["n"]
    assert clos >= 30
    deces = base.une_ligne("SELECT COUNT(*) n FROM sejour WHERE mode_sortie = 'deces'")["n"]
    assert 0 < deces < clos


def test_un_compte_par_role_avec_le_code_de_demonstration(base, demo):
    import base_demonstration
    from rea.models import droits
    from rea.services import utilisateurs

    roles = {u["role"] for u in utilisateurs.actifs(base)}
    assert roles == set(droits.roles())
    compte = utilisateurs.par_nom(base, "Démo — Senior")
    assert utilisateurs.code_correct(base_demonstration.CODE_DEMONSTRATION, compte["pin"])
    assert not compte["code_provisoire"]


def test_la_patiente_montre_ce_que_le_polytraumatise_ne_montre_pas(base, demo):
    from rea.printing import feuille
    from rea.services import feuille_dossier
    import patient_demonstration as p

    dossier = feuille_dossier.rassembler(base, demo["patiente"], p.AUJ)
    abords = [a["texte"] for a in feuille.contexte(dossier)["abords"]]
    assert "☐ Extubé J2" in abords and "☐ J2 d'AS" in abords
    assert {g["mode_ventilatoire"] for g in dossier.gaz_du_sang} == {
        "vac", "optiflow", "masque", "lunette"}
    assert any(c.produit == "Sulfate de magnésium" for c in dossier.cures_terminees)
    html = feuille.generer(dossier)
    assert feuille.COULEUR_VOIE_EMPRUNTEE not in html          # chaque ligne dans son bloc
    assert "⚠" not in feuille.contexte(dossier)["pied"]


def test_le_service_tourne(base, demo):
    """Qui soigne qui aujourd'hui, les prises de la veille — dont trois non
    données, avec leur motif — et les relevés horaires."""
    import patient_demonstration as p

    affectations = base.une_ligne(
        "SELECT COUNT(*) n FROM affectation WHERE date_jour = ?", (p.AUJ,))["n"]
    assert affectations == 6
    non_donnees = base.requete(
        "SELECT motif_code FROM administration WHERE statut = 'non_donne'")
    assert {n["motif_code"] for n in non_donnees} == {
        "pas_de_sng", "rupture_stock", "patient_absent"}
    assert base.une_ligne("SELECT COUNT(*) n FROM constante_horaire")["n"] > 200


def test_la_recherche_a_de_quoi_montrer(base, demo):
    from rea.services import statistiques as stats

    cohorte = stats.cohorte(base)
    ventilation = stats.indicateurs_ventilation(base, cohorte)
    assert ventilation["jours_vm"] > 0
    assert stats.a_relancer_j28(cohorte)          # la liste des appels à passer


def test_refaite_chaque_jour(tmp_path):
    import base_demonstration as b

    assert b.a_refaire(tmp_path)
    (tmp_path / b.TEMOIN).write_text(date.today().isoformat(), encoding="utf-8")
    assert not b.a_refaire(tmp_path)
    assert b.a_refaire(tmp_path, date.today() + timedelta(days=1))


def test_n_efface_jamais_une_vraie_base(tmp_path):
    """Lancé par erreur sur le dossier du service — une base, pas de témoin —
    le nettoyage refuse, et la base reste."""
    import base_demonstration as b

    (tmp_path / "donnees").mkdir()
    vraie = tmp_path / "donnees" / "rea.db"
    vraie.write_bytes(b"base du service")
    with pytest.raises(RuntimeError):
        b.effacer(tmp_path)
    assert vraie.read_bytes() == b"base du service"
