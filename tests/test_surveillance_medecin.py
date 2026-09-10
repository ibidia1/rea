"""La surveillance horaire, ouverte au médecin (SPEC §5.8).

L'infirmier remplit vingt-quatre lignes par jour ; jusqu'ici personne d'autre
ne les voyait. Le médecin ouvrait son évolution avec une seule valeur par
constante — celle qu'on lui disait à la visite — alors que les vingt-quatre
étaient dans la base (demande du service, 10 septembre).

Ce qui se vérifie ici n'est pas l'affichage, c'est ce qui le rendrait faux :
l'ordre des heures, le résumé de fin de ligne, et le fait que les deux écrans
du médecin appellent réellement ce rendu — un bloc écrit mais jamais branché
est le bug que la suite de tests ne voit pas.
"""

import ast
import importlib
import pathlib


def _source(module: str) -> str:
    chemin = pathlib.Path(__file__).resolve().parent.parent / "rea" / "ui" / f"{module}.py"
    return chemin.read_text(encoding="utf-8")


# -- l'ordre des heures ----------------------------------------------------

def test_la_journee_commence_a_la_prise_de_poste_du_matin():
    """7 h → 6 h, pas minuit → minuit.

    Les relevés d'une nuit sont rangés sous le jour où l'équipe a pris son
    poste : une diurèse notée à 3 h appartient à la journée de la veille. Une
    grille partant de minuit afficherait la fin de la nuit **avant** le matin
    qui l'a précédée — la courbe se lirait à l'envers.
    """
    vacations = importlib.import_module("rea.domaine.vacations")
    heures = vacations.heures_du_jour()
    assert len(heures) == 24
    assert len(set(heures)) == 24
    assert heures[0] == 7
    assert heures[-1] == 6
    # La nuit se lit d'une traite : 23 h vient juste avant 0 h.
    assert heures.index(23) + 1 == heures.index(0)


# -- le résumé de fin de ligne ---------------------------------------------

def test_les_constantes_se_resument_en_min_max_et_les_sorties_en_total():
    """Se tromper de résumé rendrait la colonne fausse : additionner des
    Glasgow ou moyenner une diurèse ne veut rien dire."""
    vue = importlib.import_module("rea.ui.surveillance")
    assert "60" in vue._resume("fc", [60.0, 110.0, 90.0], "/min")
    assert "110" in vue._resume("fc", [60.0, 110.0, 90.0], "/min")
    # Une diurèse : la somme, et sur combien d'heures elle est faite.
    total = vue._resume("diurese", [100.0, None, 50.0], "mL")
    assert "150" in total and "2 h" in total


def test_une_valeur_unique_ne_s_affiche_pas_comme_un_intervalle():
    vue = importlib.import_module("rea.ui.surveillance")
    resume = vue._resume("fc", [None, 88.0, None], "/min")
    assert "88" in resume and "–" not in resume


def test_une_ligne_sans_aucune_mesure_ne_produit_pas_de_resume():
    vue = importlib.import_module("rea.ui.surveillance")
    assert vue._resume("fc", [None, None], "/min") == ""


# -- le branchement --------------------------------------------------------

def test_les_deux_ecrans_du_medecin_affichent_le_releve_infirmier():
    """Le bug que rien d'autre ne voit : un bloc écrit et jamais appelé.

    « Visite » pour le lire au pied du lit, « Évolution » pour le consulter
    en rédigeant les 24 h — ce sont les deux moments où la question se pose.
    """
    for ecran in ("visite", "evolution"):
        assert "surveillance.bloc_du_jour(" in _source(ecran), ecran


def test_l_ecran_medecin_ne_modifie_pas_le_releve_infirmier():
    """La saisie appartient à celui qui est au lit du malade. Un médecin qui
    corrige à distance un relevé qu'il n'a pas fait écrase une observation."""
    arbre = ast.parse(_source("surveillance"))
    appels = {
        n.func.attr for n in ast.walk(arbre)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    }
    for ecriture in ("enregistrer", "supprimer", "mettre_a_jour", "inserer"):
        assert ecriture not in appels, ecriture


def test_le_total_infirmier_est_propose_au_medecin_pas_ecrit_a_sa_place():
    """Le chiffre des 24 h reste celui du médecin : le relevé peut porter des
    trous, et une somme partielle affichée comme une mesure entrerait telle
    quelle dans le bilan hydrique."""
    source = _source("evolution")
    assert "_releve_infirmier" in source
    assert "Relevé infirmier" in source
    # Proposé par une légende, jamais par la valeur du champ de saisie.
    evo = importlib.import_module("rea.ui.evolution")
    assert set(evo._RELEVE_HORAIRE) == {"diurese_24h", "jetes_24h"}
