"""Le catalogue des molécules — choisir au lieu de retaper (SPEC §5.2).

Le produit d'une ligne de prescription se tapait à la main. Trois
conséquences, et la troisième est la plus coûteuse. On retape « Imipénème »
vingt fois par semaine. On l'écrit de vingt façons — « imipeneme »,
« Tienam », « TIENAM 1g » — et une faute de frappe devient une molécule
distincte. Et surtout, « quelle molécule sur quel type d'infection »
n'a plus de réponse calculable : le logiciel ne sait pas que ces vingt
graphies sont le même produit (demande du service, 10 septembre).

Deux sources, une seule liste :

* `referentiels/medicaments.json`, livré avec le logiciel — les molécules
  courantes d'une réanimation polyvalente, avec leur unité usuelle et leurs
  **noms commerciaux en synonymes**. On tape « tie » et Imipénème sort, parce
  que « Tienam » est ce qu'on a en tête au lit du malade ;
* la table `medicament_local`, que le service remplit **sans le savoir** : la
  première prescription d'une molécule absente l'y inscrit, et elle est
  proposée dès la suivante. Personne n'a de catalogue à remplir avant de
  pouvoir travailler.

Ce qui est écrit sur la prescription reste la **dénomination commune** et non
la marque : c'est elle qui permet de compter une molécule à travers les noms
commerciaux. Les marques servent à la chercher, pas à la nommer.

**Aucune posologie n'est proposée.** Le catalogue porte l'unité usuelle — « g »
plutôt que « mg » pour l'imipénème — ce qui est une unité, pas une dose. La
dose reste écrite par le prescripteur, comme partout ailleurs dans ce
logiciel : une posologie pré-remplie est une posologie qu'on valide sans la
lire.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

from ..db import Base


@dataclass(frozen=True)
class Medicament:
    code: str
    libelle: str
    unite: str | None = None
    #: Le nom commercial, **à part** des synonymes parce qu'il s'affiche : le
    #: prescrit écrit « Imipénème (Tienam) ». Les synonymes, eux, ne servent
    #: qu'à chercher — sans cette séparation on lirait « Imipénème
    #: (carbapeneme) », ce qui est une famille et non un produit qu'on demande
    #: à la pharmacie.
    marque: str | None = None
    synonymes: tuple[str, ...] = ()
    #: Ajoutée par le service en la prescrivant, plutôt que livrée avec le
    #: logiciel. L'écran des référentiels les montre à part : ce sont celles
    #: qu'un senior voudra relire.
    locale: bool = False
    _recherche: str = field(default="", repr=False, compare=False)

    @property
    def nom_affiche(self) -> str:
        """« Imipénème (Tienam) » — la DCI, et la marque pour la reconnaître.

        Ce qui est **enregistré** reste la seule DCI : la parenthèse est
        ajoutée à l'affichage. L'écrire dans la base ramènerait le problème
        qu'on vient de résoudre — « Imipénème (Tienam) » et « Imipénème » ne
        se compteraient plus ensemble.
        """
        return f"{self.libelle} ({self.marque})" if self.marque else self.libelle

    def correspond(self, requete: str) -> bool:
        return normaliser(requete) in self._recherche

    def rang(self, requete: str) -> int | None:
        """0 = le nom commence ainsi, 1 = un mot commence ainsi, 2 = ailleurs.

        None si la molécule ne correspond pas du tout.
        """
        requete = normaliser(requete)
        if not requete:
            return 0
        if normaliser(self.libelle).startswith(requete):
            return 0
        if any(mot.startswith(requete) for mot in self._recherche.split()):
            return 1
        return 2 if requete in self._recherche else None


def normaliser(texte: str) -> str:
    """La forme sur laquelle on compare : sans accents, sans casse, resserrée.

    C'est elle qui empêche « tienam », « Tienam » et « TIENAM  » de devenir
    trois molécules qui ne se comptent jamais ensemble. Sans accents parce que
    personne ne tape « Céfépime » avec son accent dans une barre de recherche.
    """
    texte = unicodedata.normalize("NFD", (texte or "").strip().lower())
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")
    return " ".join(texte.split())


def _du_referentiel() -> list[Medicament]:
    from .. import referentiels

    molecules = []
    for entree in referentiels.charger("medicaments"):
        code, libelle, unite = entree[0], entree[1], entree[2]
        marque = entree[3] if len(entree) > 3 else None
        synonymes = tuple(entree[4]) if len(entree) > 4 else ()
        molecules.append(Medicament(
            code=code, libelle=libelle, unite=unite or None,
            marque=marque or None, synonymes=synonymes,
            _recherche=normaliser(" ".join((libelle, marque or "", *synonymes))),
        ))
    return molecules


def catalogue(base: Base) -> list[Medicament]:
    """Le catalogue livré et celui du service, dans l'ordre alphabétique.

    Une molécule locale portant le même nom qu'une molécule livrée n'apparaît
    qu'une fois : le service a pu écrire « Vancomycine » avant que quiconque
    ouvre le catalogue, et deux lignes identiques dans une liste de choix
    ne se départagent pas à l'œil.
    """
    molecules = _du_referentiel()
    connues = {normaliser(m.libelle) for m in molecules}
    for ligne in base.requete(
        "SELECT cle, libelle, unite FROM medicament_local WHERE supprime = 0"
    ):
        if ligne["cle"] in connues:
            continue
        connues.add(ligne["cle"])
        molecules.append(Medicament(
            code=f"local:{ligne['cle']}", libelle=ligne["libelle"],
            unite=ligne["unite"] or None, locale=True,
            _recherche=normaliser(ligne["libelle"]),
        ))
    return sorted(molecules, key=lambda m: normaliser(m.libelle))


def chercher(base: Base, requete: str, limite: int = 12) -> list[Medicament]:
    """Les molécules qui répondent à ce qu'on tape, les plus probables devant.

    Le classement compte plus que le filtre. Trois rangs :

    0. le **nom** commence par ce qu'on tape — « met » donne Métronidazole ;
    1. un **mot** commence par ce qu'on tape — « tie » donne Imipénème, parce
       que son synonyme « Tienam » commence par « tie » ;
    2. le reste, en plein milieu d'un mot.

    Sans ce classement, « tie » remontait les antiépileptiques : le mot
    « antiepileptique » contient « tie ». Trois molécules justes noyées sous
    quatre qui n'ont rien à voir, c'est une liste qu'on cesse d'utiliser.
    """
    requete = normaliser(requete)
    if not requete:
        return catalogue(base)[:limite]
    trouvees: list[tuple[int, Medicament]] = []
    for molecule in catalogue(base):
        rang = molecule.rang(requete)
        if rang is not None:
            trouvees.append((rang, molecule))
    trouvees.sort(key=lambda paire: (paire[0], normaliser(paire[1].libelle)))
    # Dès qu'un début de mot correspond, le milieu de mot est du bruit : « tie »
    # a trouvé Tienam, proposer en plus les antiépileptiques (« antiepileptique »
    # contient « tie ») ne fait que rallonger la liste de ce qu'on ne cherche
    # pas. On ne retombe sur le milieu de mot que s'il n'y a rien d'autre.
    if trouvees and trouvees[0][0] <= 1:
        trouvees = [paire for paire in trouvees if paire[0] <= 1]
    return [molecule for _rang, molecule in trouvees][:limite]


def par_libelle(base: Base, libelle: str) -> Medicament | None:
    cle = normaliser(libelle)
    return next((m for m in catalogue(base) if normaliser(m.libelle) == cle), None)


def nom_affiche(base: Base, produit: str) -> str:
    """Le nom d'un produit tel qu'il doit se lire : « Imipénème (Tienam) ».

    Rend le produit **inchangé** s'il n'est pas au catalogue — une ligne
    ancienne, une molécule ajoutée à la main. Un écran ne doit jamais perdre
    ce qui a été écrit sous prétexte qu'il ne le reconnaît pas.
    """
    molecule = par_libelle(base, produit)
    return molecule.nom_affiche if molecule else produit


def apprendre(
    base: Base, libelle: str, *, unite: str | None = None,
    utilisateur_id: str | None = None,
) -> str | None:
    """Inscrit une molécule que le service vient de prescrire.

    Rend son identifiant si elle a été ajoutée, None si elle était déjà connue
    — d'un côté ou de l'autre du catalogue. Ce geste est **silencieux** : on
    ne demande pas à un médecin de confirmer qu'il veut enrichir un catalogue
    au moment où il prescrit.
    """
    libelle = (libelle or "").strip()
    cle = normaliser(libelle)
    if not cle or par_libelle(base, libelle) is not None:
        return None
    return base.inserer(
        "medicament_local",
        {"cle": cle, "libelle": libelle, "unite": (unite or "").strip() or None},
        utilisateur_id=utilisateur_id,
    )


def locales(base: Base) -> list[dict]:
    """Celles que le service a ajoutées — l'écran des référentiels les montre."""
    return base.requete(
        "SELECT * FROM medicament_local WHERE supprime = 0 ORDER BY libelle"
    )


def renommer(
    base: Base, medicament_id: str, libelle: str, *,
    unite: str | None = None, utilisateur_id: str | None = None,
) -> None:
    """Corriger une faute de frappe entrée par la prescription.

    Ne touche pas aux lignes déjà prescrites : elles portent le nom tel qu'il
    a été écrit ce jour-là, et le réécrire changerait une prescription signée.
    Le catalogue, lui, propose désormais la forme corrigée.
    """
    libelle = (libelle or "").strip()
    if not libelle:
        raise ValueError("Le nom de la molécule est obligatoire.")
    base.mettre_a_jour(
        "medicament_local", medicament_id,
        {"libelle": libelle, "cle": normaliser(libelle),
         "unite": (unite or "").strip() or None},
        utilisateur_id=utilisateur_id,
    )


def oublier(base: Base, medicament_id: str, *, utilisateur_id: str | None = None) -> None:
    """Retire une molécule du catalogue du service, sans toucher aux
    prescriptions qui la portent."""
    base.supprimer_logiquement("medicament_local", medicament_id,
                               utilisateur_id=utilisateur_id)
