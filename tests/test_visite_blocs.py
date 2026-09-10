"""Ce que le mode Visite montre, et sous quel titre.

Un écran de visite se lit debout, au lit du malade, dans l'ordre où les
questions se posent. Ces tests lisent la source plutôt que le rendu : les
écrans Streamlit ne s'exécutent pas hors du navigateur, et un bloc qui
disparaît d'un écran ne casse aucun test — c'est ainsi qu'un tableau des
variations était tombé sans qu'un seul des mille tests s'en aperçoive.
"""

from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
VISITE = (RACINE / "rea" / "ui" / "visite.py").read_text(encoding="utf-8")
SURVEILLANCE = (RACINE / "rea" / "ui" / "surveillance.py").read_text(encoding="utf-8")
PRESCRIT = (RACINE / "rea" / "ui" / "prescrit.py").read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# La sédation, qui n'est pas prescrite en ligne
# --------------------------------------------------------------------------

def test_la_sedation_s_affiche_dans_le_bloc_pse_de_la_visite():
    """Elle est posée comme dispositif : sans reprise explicite, la seule
    vitesse qu'un infirmier règle sur une pompe n'apparaît pas du tout."""
    assert "prescrit.ligne_sedation" in VISITE
    assert 'code_voie == "PSE"' in VISITE


def test_la_ligne_de_sedation_est_publique_et_partagee():
    """Une seconde copie dans visite.py finirait par diverger de l'original."""
    assert "def ligne_sedation(" in PRESCRIT
    assert "def _ligne_sedation(" not in PRESCRIT


def test_un_patient_sedate_sans_autre_traitement_voit_quand_meme_son_bloc():
    """Le bloc PSE ne doit pas être sauté quand la sédation est seule."""
    assert "if not lignes and not synthetique:" in VISITE
    assert "if not any(par_voie.values()) and not sedation:" in VISITE


# --------------------------------------------------------------------------
# Les blocs de l'écran
# --------------------------------------------------------------------------

@pytest.mark.parametrize("titre", [
    "Bilan entrées / sorties",
    "Bilan infectieux",
    "Avis spécialisés",
    "Explorations faites",
])
def test_chaque_bloc_demande_existe(titre):
    assert f'"{titre}' in VISITE, f"le bloc « {titre} » a disparu de la visite"


def test_les_avis_ne_sont_plus_ranges_sous_l_infectieux():
    """Un avis de chirurgie sous un titre qui parle de germes se cherche là
    où personne n'aurait l'idée de le chercher."""
    assert '"Infectieux et avis"' not in VISITE
    assert "def _avis(" in VISITE
    assert "def _infectieux(" in VISITE
    # Les avis sont bien sortis de la fonction infectieux.
    debut = VISITE.index("def _infectieux(")
    fin = VISITE.index("def _avis(")
    assert "avis_service" not in VISITE[debut:fin]


def test_l_infectieux_suit_immediatement_la_biologie():
    """Une CRP et une hémoculture se lisent l'une contre l'autre."""
    appels = VISITE[VISITE.index("with droite:"):VISITE.index("st.divider()")]
    ordre = [
        ligne.strip() for ligne in appels.splitlines()
        if ligne.strip().startswith("_") and "(sejour" in ligne
    ]
    assert ordre.index("_infectieux(sejour, date_jour_str)") == \
        ordre.index("_biologie(sejour, date_jour_str)") + 1


def test_le_bilan_est_sous_les_traitements():
    """Les entrées viennent des traitements : les séparer obligerait à
    remonter l'écran pour savoir d'où sort le chiffre."""
    gauche = VISITE[VISITE.index("with gauche:"):VISITE.index("with droite:")]
    assert "_traitements(sejour, date_jour_str)" in gauche
    assert "_bilan_entrees_sorties(sejour, date_jour_str)" in gauche


def test_le_bilan_donne_une_ligne_par_drain():
    """Deux redons qui donnent 90 et 410 ne se lisent pas comme deux qui
    donnent 250 chacun."""
    assert "bilan.detail_drains" in VISITE


def test_le_bilan_dit_ce_qui_manque_au_lieu_d_afficher_un_chiffre_faux():
    assert "motif_indisponible" in VISITE


# --------------------------------------------------------------------------
# Le tableau de surveillance
# --------------------------------------------------------------------------

def test_le_tableau_de_surveillance_a_ete_agrandi():
    """Il se lit debout, à distance : .78rem était la taille d'une note de
    bas de page (demande du service, 10 septembre)."""
    assert "font-size:.95rem" in SURVEILLANCE
    assert "font-size:.78rem" not in SURVEILLANCE


def test_le_tableau_montre_les_drains_et_pas_seulement_la_diurese():
    assert "_recueils_releves(grille)" in SURVEILLANCE
    assert "PREFIXE_DRAIN" in SURVEILLANCE


def test_les_drains_du_tableau_portent_un_nom_lisible():
    """« drain:8f3a-… » ne se lit pas au lit du malade."""
    assert "_noms_des_recueils" in SURVEILLANCE
    assert 'noms.get(cle, cle)' in SURVEILLANCE
