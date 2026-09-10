"""Aucun « lire puis écrire » ne doit rester hors transaction (SPEC §2.4).

Le test de charge du 10 septembre 2026 a trouvé onze écritures perdues sur
36 587 : les services notaient « s'il existe une ligne, la mettre à jour,
sinon l'insérer » sans transaction. Deux fils lisent tous les deux « rien », et
le second heurte l'index unique — ou, là où il n'y a pas d'index, range un
doublon **en silence**, ce qui est pire.

Corriger les cas trouvés ne suffisait pas : rien n'empêchait le motif de
revenir à la prochaine fonction écrite. Ce test lit le code source de tous les
services et refuse toute fonction qui lit la base puis y écrit sans avoir
ouvert de transaction.

Il connaît une seule exception, nommée et justifiée ci-dessous.
"""

import ast
import pathlib

LECTURES = {"une_ligne", "requete"}
ECRITURES = {"inserer", "mettre_a_jour", "supprimer_logiquement", "executer"}

#: Les fonctions dont le « lire puis écrire » est couvert par la transaction
#: de leur appelant. À garder très court : chaque nom ici est une garantie
#: tenue à la main plutôt que par le langage.
DELEGUEES = {
    # Appelée uniquement depuis `constantes.enregistrer`, qui ouvre la
    # transaction avant d'appeler — la découper ainsi garde la fonction
    # lisible sans lui faire perdre son atomicité.
    ("constantes.py", "_ecrire_les_mesures"),
}


def _appels_base(noeud):
    for n in ast.walk(noeud):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and isinstance(n.func.value, ast.Name)
                and n.func.value.id == "base"):
            yield n.func.attr, n.lineno


def _lignes_sous_transaction(fonction):
    couvertes = set()
    for n in ast.walk(fonction):
        if not isinstance(n, ast.With):
            continue
        for item in n.items:
            contexte = item.context_expr
            if (isinstance(contexte, ast.Call)
                    and isinstance(contexte.func, ast.Attribute)
                    and contexte.func.attr == "transaction"):
                for enfant in ast.walk(n):
                    if hasattr(enfant, "lineno"):
                        couvertes.add(enfant.lineno)
    return couvertes


def _fonctions_a_risque():
    risquees = []
    dossier = pathlib.Path(__file__).resolve().parent.parent / "rea" / "services"
    for chemin in sorted(dossier.glob("*.py")):
        arbre = ast.parse(chemin.read_text(encoding="utf-8"))
        for f in [n for n in ast.walk(arbre) if isinstance(n, ast.FunctionDef)]:
            if (chemin.name, f.name) in DELEGUEES:
                continue
            couvertes = _lignes_sous_transaction(f)
            appels = list(_appels_base(f))
            lectures = [l for m, l in appels if m in LECTURES and l not in couvertes]
            ecritures = [l for m, l in appels if m in ECRITURES and l not in couvertes]
            if lectures and ecritures and min(lectures) < max(ecritures):
                risquees.append(f"{chemin.name}:{f.lineno} {f.name}()")
    return risquees


def test_aucun_service_ne_lit_puis_ecrit_hors_transaction():
    """Le garde-fou qui empêche la course de revenir.

    Si ce test échoue sur une fonction que vous venez d'écrire : entourez son
    « lire puis écrire » d'un `with base.transaction():`. Et gardez hors de la
    transaction tout ce qui est long — composer un HTML, calculer un score —
    car le verrou bloque aussi les lecteurs.
    """
    risquees = _fonctions_a_risque()
    assert risquees == [], (
        "Ces fonctions lisent la base puis y écrivent sans transaction :\n  "
        + "\n  ".join(risquees)
    )


def test_l_exception_declaree_existe_vraiment():
    """Une liste d'exceptions qui nomme une fonction disparue ne protège plus
    rien, et personne ne s'en aperçoit."""
    dossier = pathlib.Path(__file__).resolve().parent.parent / "rea" / "services"
    for fichier, fonction in DELEGUEES:
        source = (dossier / fichier).read_text(encoding="utf-8")
        assert f"def {fonction}(" in source, f"{fichier}:{fonction}"
