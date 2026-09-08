"""L'antibiogramme, coché plutôt que tapé (demande du service, 8 septembre).

Le champ était libre : chacun écrivait « Pipé-tazo », « pip/tazo » ou « TZP »,
et rien ne se comptait d'un séjour à l'autre. Les molécules viennent
maintenant d'une liste fermée ; ce qui est vérifié ici, c'est que le texte
produit reste lisible tel quel dans le dossier, et qu'une catégorie vide
n'écrit rien.
"""

from rea.services import microbiologie


def test_les_trois_categories_sont_ecrites_dans_lordre_de_lecture():
    """S puis I puis R : ce à quoi le germe répond d'abord, ce qui ne marchera
    pas ensuite."""
    texte = microbiologie.texte_antibiogramme(
        sensibles=["imipeneme"], intermediaires=["ceftazidime"], resistants=["amoxicilline"],
    )
    assert texte == "S : Imipénème · I : Ceftazidime · R : Amoxicilline"


def test_une_categorie_vide_nest_pas_ecrite():
    """Le laboratoire ne teste jamais tout : « I : » suivi de rien ferait
    croire à un résultat manquant."""
    texte = microbiologie.texte_antibiogramme(
        sensibles=["amikacine"], resistants=["ceftriaxone"],
    )
    assert texte == "S : Amikacine · R : Ceftriaxone"


def test_plusieurs_molecules_dans_une_categorie():
    texte = microbiologie.texte_antibiogramme(sensibles=["colistine", "amikacine"])
    assert texte == "S : Colistine, Amikacine"


def test_un_antibiogramme_vide_ne_vaut_rien():
    """Aucune molécule cochée : la colonne reste nulle, pas une chaîne vide
    qu'on prendrait pour un antibiogramme rendu."""
    assert microbiologie.texte_antibiogramme() is None
    assert microbiologie.texte_antibiogramme(sensibles=[], resistants=[]) is None


def test_une_molecule_inconnue_est_reprise_telle_quelle():
    """Si le référentiel change et qu'un code disparaît, l'ancien texte doit
    rester lisible plutôt que de faire tomber l'écran."""
    assert microbiologie.texte_antibiogramme(sensibles=["molecule_x"]) == "S : molecule_x"


def test_le_texte_compose_senregistre_avec_le_resultat(base):
    from rea.services import sejours

    pid = sejours.creer_patient(base, matricule="M1", nom_affichage="M1",
                                date_naissance=None)
    sid = sejours.creer_sejour(base, patient_id=pid, date_admission="2026-09-01",
                               lit_admission=1)
    ligne_id = microbiologie.enregistrer(
        base, sejour_id=sid, date_prelevement="2026-09-02",
        type_prelevement="hemoculture",
    )
    microbiologie.completer(base, ligne_id, {
        "resultat": "positif", "germe": "E. coli",
        "antibiogramme": microbiologie.texte_antibiogramme(
            sensibles=["imipeneme"], resistants=["amoxicilline"]
        ),
    })
    ligne = microbiologie.du_sejour(base, sid)[0]
    assert ligne["antibiogramme"] == "S : Imipénème · R : Amoxicilline"
