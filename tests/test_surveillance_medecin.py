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


# -- la colonne de synthèse ------------------------------------------------

def test_les_constantes_se_resument_par_leurs_extremes():
    """Les deux chiffres qui décident : le plus bas et le plus haut. Une PA
    moyenne à 75 ne dit pas qu'on a passé la nuit à 55."""
    vue = importlib.import_module("rea.ui.surveillance")
    resume = vue._extremes([60.0, 110.0, 90.0], "/min")
    assert "60" in resume and "110" in resume


def test_une_valeur_unique_ne_s_affiche_pas_comme_un_intervalle():
    vue = importlib.import_module("rea.ui.surveillance")
    resume = vue._extremes([None, 88.0, None], "/min")
    assert "88" in resume and "–" not in resume


def test_une_ligne_sans_aucune_mesure_ne_produit_pas_de_resume():
    vue = importlib.import_module("rea.ui.surveillance")
    assert vue._extremes([None, None], "/min") == ""


def test_les_recueils_ne_passent_pas_par_le_resume_des_constantes():
    """Un recueil n'a pas de min-max : sa case porte un niveau, et ce qu'on
    veut en lire est le volume calculé. Les deux familles ne se rendent donc
    pas de la même façon, et c'est le seul endroit où l'écart se voit."""
    constantes = importlib.import_module("rea.services.constantes")
    vitales = {c for c, _l, _u in constantes.VITALES}
    assert not (vitales & set(constantes.CLES_NIVEAU))
    assert "diurese" in constantes.CLES_NIVEAU


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
    trous, et un total partiel affiché comme une mesure entrerait tel quel
    dans le bilan hydrique."""
    source = _source("evolution")
    assert "_releve_infirmier" in source
    assert "Relevé infirmier" in source
    # Proposé par une légende, jamais par la valeur du champ de saisie.
    evo = importlib.import_module("rea.ui.evolution")
    assert set(evo._RELEVE_HORAIRE) == {"diurese_24h"}


def test_le_medecin_voit_les_volumes_calcules_pas_les_niveaux_seuls():
    """Afficher les seuls niveaux ferait prendre « 900 à 13 h » pour une
    diurèse horaire de 900 mL."""
    assert "sorties_du_jour(" in _source("surveillance")


def test_un_total_incomplet_le_dit_au_medecin():
    """Un total amputé qui se présente comme complet est pire qu'un total
    absent : il se recopie dans l'observation."""
    assert "incomplet" in _source("evolution")
    assert "_reserves" in _source("surveillance")
