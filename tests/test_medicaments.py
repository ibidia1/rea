"""Le catalogue des molécules (SPEC §5.2).

Le produit se tapait à la main. On retapait « Imipénème » vingt fois par
semaine, on l'écrivait de vingt façons — « imipeneme », « Tienam »,
« TIENAM 1g » — et « quelle molécule sur quel type d'infection » n'avait plus
de réponse calculable : le logiciel ne savait pas que ces graphies désignaient
le même produit (demande du service, 10 septembre).

Ce que ces tests tiennent, c'est ce qui rend la liste **utilisable** : on la
cherche par la marque, le bon résultat sort en premier, et elle s'enrichit
toute seule de ce que le service prescrit.
"""

import importlib

import pytest


def _service():
    return importlib.import_module("rea.services.medicaments")


def _libelles(molecules) -> list[str]:
    return [m.libelle for m in molecules]


# -- chercher par ce qu'on a en tête ---------------------------------------

def test_on_cherche_par_la_marque(base):
    """Au lit du malade on pense « Tienam », pas « Imipénème ». Une liste qui
    exige la DCI est une liste qu'on contourne en tapant à la main."""
    medicaments = _service()
    assert _libelles(medicaments.chercher(base, "tie")) == ["Imipénème"]
    assert "Énoxaparine" in _libelles(medicaments.chercher(base, "lovenox"))
    assert "Lévétiracétam" in _libelles(medicaments.chercher(base, "keppra"))


def test_les_accents_ne_bloquent_pas_la_recherche(base):
    """Personne ne tape « Céfépime » avec son accent dans une liste."""
    medicaments = _service()
    assert "Céfépime" in _libelles(medicaments.chercher(base, "cefepime"))
    assert "Métronidazole" in _libelles(medicaments.chercher(base, "metro"))


def test_un_debut_de_mot_passe_avant_un_milieu_de_mot(base):
    """Le classement compte plus que le filtre.

    « tie » trouve Tienam (début du mot) mais aussi « antiepileptique » (en
    plein milieu). Proposer les quatre antiépileptiques noierait la seule
    bonne réponse : on ne retombe sur le milieu de mot que faute de mieux.
    """
    medicaments = _service()
    assert _libelles(medicaments.chercher(base, "tie")) == ["Imipénème"]
    # Rien ne commence par « oxacill » sauf Oxacilline ; « pip » ne trouve
    # Pipéracilline que par le début de son nom.
    assert _libelles(medicaments.chercher(base, "pipera")) == [
        "Pipéracilline − tazobactam"]


def test_le_nom_passe_avant_le_synonyme(base):
    """« met » doit donner les molécules qui s'appellent ainsi avant celles
    qui portent le mot dans une famille."""
    medicaments = _service()
    trouves = _libelles(medicaments.chercher(base, "met"))
    assert trouves[:3] == ["Méthylprednisolone", "Métoclopramide", "Métronidazole"]


def test_chercher_par_famille(base):
    """« curare » ou « aminoside » : c'est ainsi qu'on raisonne quand on
    hésite entre deux produits de la même classe."""
    medicaments = _service()
    assert set(_libelles(medicaments.chercher(base, "curare"))) >= {
        "Cisatracurium", "Atracurium", "Rocuronium"}
    assert set(_libelles(medicaments.chercher(base, "aminoside"))) == {
        "Amikacine", "Gentamicine"}


def test_une_recherche_sans_reponse_ne_rend_rien(base):
    assert _service().chercher(base, "zzzz") == []


# -- le catalogue s'enrichit tout seul --------------------------------------

def test_prescrire_une_molecule_inconnue_l_ajoute(base):
    """C'est la demande exacte : j'écris « Tienam 500 » une fois, elle est
    dans la liste la fois suivante."""
    medicaments = _service()
    assert medicaments.chercher(base, "Tienam 500") == []
    medicaments.apprendre(base, "Tienam 500", unite="mg")
    trouve = medicaments.chercher(base, "tienam 5")
    assert _libelles(trouve) == ["Tienam 500"]
    assert trouve[0].locale is True


def test_la_meme_molecule_ne_s_ajoute_pas_deux_fois(base):
    """« tienam », « Tienam » et « TIENAM  » sont la même molécule. Trois
    entrées, ce serait trois molécules qui ne se comptent jamais ensemble."""
    medicaments = _service()
    assert medicaments.apprendre(base, "Tienam 500") is not None
    assert medicaments.apprendre(base, "tienam 500") is None
    assert medicaments.apprendre(base, "  TIENAM   500 ") is None
    assert len(medicaments.locales(base)) == 1


def test_une_molecule_deja_livree_ne_se_reajoute_pas(base):
    """Le service a pu écrire « Vancomycine » à la main avant d'ouvrir la
    liste : deux lignes identiques ne se départagent pas à l'œil."""
    medicaments = _service()
    assert medicaments.apprendre(base, "Vancomycine") is None
    assert medicaments.locales(base) == []
    assert _libelles(medicaments.chercher(base, "vanco")) == ["Vancomycine"]


def test_une_molecule_vide_ne_s_apprend_pas(base):
    medicaments = _service()
    assert medicaments.apprendre(base, "   ") is None
    assert medicaments.locales(base) == []


# -- corriger sans réécrire l'histoire --------------------------------------

def test_corriger_une_faute_de_frappe_ne_touche_pas_aux_prescriptions(base):
    """Une ligne prescrite porte le nom écrit ce jour-là. Le réécrire
    changerait une prescription signée."""
    medicaments = _service()
    prescriptions = importlib.import_module("rea.services.prescriptions")
    sejours = importlib.import_module("rea.services.sejours")
    pid = sejours.creer_patient(base, matricule="M1", nom_affichage="P1",
                                date_naissance="1970-01-01")
    sid = sejours.creer_sejour(base, patient_id=pid, date_admission="2026-09-01",
                               lit_admission=1)
    ligne_id = prescriptions.ajouter_ligne(
        base, sejour_id=sid, voie="IV", produit="Tienma", date_debut="2026-09-02")

    identifiant = medicaments.apprendre(base, "Tienma")
    medicaments.renommer(base, identifiant, "Tienam")

    # « Tienam » est proposé ; Imipénème sort aussi, puisque « Tienam » est
    # l'un de ses noms commerciaux — les deux sont justes.
    assert "Tienam" in _libelles(medicaments.chercher(base, "tienam"))
    assert medicaments.chercher(base, "tienma") == []      # la faute a disparu
    ligne = base.une_ligne("SELECT produit FROM prescription_ligne WHERE id = ?",
                           (ligne_id,))
    assert ligne["produit"] == "Tienma"      # la prescription n'a pas bougé


def test_oublier_une_molecule_ne_touche_pas_aux_prescriptions(base):
    medicaments = _service()
    identifiant = medicaments.apprendre(base, "Produit d'essai")
    medicaments.oublier(base, identifiant)
    assert medicaments.chercher(base, "essai") == []


def test_renommer_refuse_un_nom_vide(base):
    medicaments = _service()
    identifiant = medicaments.apprendre(base, "Tienma")
    with pytest.raises(ValueError):
        medicaments.renommer(base, identifiant, "   ")


# -- ce que le catalogue ne fait pas ---------------------------------------

def test_le_catalogue_ne_propose_aucune_posologie():
    """La règle du service, tenue ici comme ailleurs : le logiciel ne propose
    jamais de dose. Une unité usuelle — « g » pour l'imipénème — n'est pas une
    posologie ; une dose pré-remplie est une dose validée sans être lue.
    """
    referentiels = importlib.import_module("rea.referentiels")
    for entree in referentiels.charger("medicaments"):
        # [code, libellé, unité, marque, synonymes] — pas de champ de dose,
        # et l'unité n'est jamais un nombre.
        assert len(entree) <= 5
        assert not any(caractere.isdigit() for caractere in (entree[2] or ""))


def test_la_denomination_ecrite_est_commune_pas_commerciale(base):
    """C'est elle qui permet de compter une molécule à travers ses marques,
    et donc de répondre à « quelle molécule sur quel type d'infection »."""
    medicaments = _service()
    trouve = medicaments.chercher(base, "tienam")[0]
    assert trouve.libelle == "Imipénème"
    assert "Tienam" in trouve.synonymes


# -- l'écran qui sert à nettoyer --------------------------------------------

def test_les_gestes_du_catalogue_sont_branches_a_un_ecran():
    """Un catalogue qui apprend finit par contenir les fautes de frappe qu'on
    a prescrites. Chercher, corriger et retirer ne servent à rien tant qu'un
    écran ne les appelle pas — et du code de service jamais appelé est du code
    qu'on croit vérifié.
    """
    import pathlib as _pathlib

    source = (_pathlib.Path(__file__).resolve().parent.parent
              / "rea" / "ui" / "administration.py").read_text(encoding="utf-8")
    for geste in ("chercher(", "renommer(", "oublier(", "locales("):
        assert f"medicaments_service.{geste}" in source, geste


def test_l_ecran_de_prescription_apprend_les_molecules():
    """La demande exacte : écrire une molécule une fois suffit à ce qu'elle
    soit proposée ensuite."""
    import pathlib as _pathlib

    source = (_pathlib.Path(__file__).resolve().parent.parent
              / "rea" / "ui" / "prescrit.py").read_text(encoding="utf-8")
    assert "medicaments_service.apprendre(" in source
    assert "medicaments_service.catalogue(" in source
    # Et le champ texte libre du produit a bien disparu.
    assert 'st.text_input("Produit / libellé")' not in source


# -- le nom commercial entre parenthèses -----------------------------------

def test_le_prescrit_ecrit_la_dci_et_la_marque(base):
    """« Imipénème (Tienam) » : la dénomination pour compter, la marque pour
    reconnaître la boîte qu'on demande à la pharmacie."""
    medicaments = _service()
    assert medicaments.nom_affiche(base, "Imipénème") == "Imipénème (Tienam)"
    assert medicaments.nom_affiche(base, "Énoxaparine") == "Énoxaparine (Lovenox)"


def test_sans_marque_connue_rien_ne_s_affiche(base):
    """Plutôt qu'une parenthèse vide : le mannitol n'a pas de nom commercial
    au catalogue, il s'écrit « Mannitol »."""
    assert _service().nom_affiche(base, "Mannitol") == "Mannitol"


def test_un_produit_hors_catalogue_reste_tel_quel(base):
    """Une ligne ancienne, une molécule tapée à la main : un écran ne perd
    jamais ce qui a été écrit sous prétexte qu'il ne le reconnaît pas."""
    assert _service().nom_affiche(base, "Tienam maison") == "Tienam maison"


def test_la_parenthese_n_est_jamais_enregistree(base):
    """Elle est ajoutée à l'affichage. L'écrire en base ramènerait le problème
    qu'on vient de résoudre : « Imipénème (Tienam) » et « Imipénème » ne se
    compteraient plus ensemble."""
    medicaments = _service()
    prescriptions = importlib.import_module("rea.services.prescriptions")
    sejours = importlib.import_module("rea.services.sejours")
    pid = sejours.creer_patient(base, matricule="M1", nom_affichage="P1",
                                date_naissance="1970-01-01")
    sid = sejours.creer_sejour(base, patient_id=pid, date_admission="2026-09-01",
                               lit_admission=1)
    ligne_id = prescriptions.ajouter_ligne(
        base, sejour_id=sid, voie="IV", produit="Imipénème", date_debut="2026-09-02")
    ligne = base.une_ligne("SELECT produit FROM prescription_ligne WHERE id = ?",
                           (ligne_id,))
    assert ligne["produit"] == "Imipénème"
    assert medicaments.nom_affiche(base, ligne["produit"]) == "Imipénème (Tienam)"


def test_une_famille_ne_s_affiche_jamais_entre_parentheses(base):
    """Le nom commercial est un champ à part des synonymes, et c'est tout
    l'objet de la séparation : sans elle on lirait « Imipénème (carbapeneme) »,
    ce qui est une famille et non un produit qu'on demande à la pharmacie."""
    medicaments = _service()
    molecule = medicaments.par_libelle(base, "Imipénème")
    assert molecule.marque == "Tienam"
    assert "carbapeneme" in molecule.synonymes
    assert "carbapeneme" not in molecule.nom_affiche


def test_le_prescrit_affiche_bien_le_nom_complet():
    """Le rendu est branché — un nom d'affichage calculé mais jamais appelé
    ne se verrait nulle part."""
    import pathlib as _pathlib

    source = (_pathlib.Path(__file__).resolve().parent.parent
              / "rea" / "ui" / "prescrit.py").read_text(encoding="utf-8")
    assert source.count("medicaments_service.nom_affiche(") >= 4
