"""Les analytes que le service dose et que le catalogue ne connaît pas (§8).

Le catalogue de biologie (`rea/analytes.py`) est du code : y ajouter la
troponine demande une nouvelle version du logiciel. Un service qui se met à
doser quelque chose ne peut pas attendre ça — il le noterait dans un
commentaire libre, où le résultat ne se compare pas d'un jour à l'autre et ne
sort dans aucune statistique (demande du service, 9 septembre).

Ces analytes vivent dans la base et non dans `referentiels/` : ce sont des
données du service, pas du logiciel. Ils sont donc sauvegardés et restaurés
avec elle, alors qu'un fichier de référentiel réécrit à l'exécution cesserait
d'être versionné.
"""

from __future__ import annotations

import unicodedata

from .. import analytes as cat
from ..db import Base


def code_depuis_libelle(libelle: str) -> str:
    """« D-dimères » devient « d_dimeres ».

    Le code est ce qui est écrit sur chaque résultat : il doit être stable et
    sans accent, parce qu'il finira dans un export lu par un tableur dont on ne
    choisit pas l'encodage.
    """
    sans_accent = "".join(
        c for c in unicodedata.normalize("NFD", libelle.strip().lower())
        if unicodedata.category(c) != "Mn"
    )
    code = "".join(c if c.isalnum() else "_" for c in sans_accent).strip("_")
    while "__" in code:
        code = code.replace("__", "_")
    return code


def ajouter(
    base: Base,
    *,
    libelle: str,
    unite: str | None = None,
    borne_basse: float | None = None,
    borne_haute: float | None = None,
    utilisateur_id: str | None = None,
) -> str:
    """Ajoute un analyte au catalogue du service, et le rend saisissable tout
    de suite.

    Refuse un code déjà pris — par le catalogue du logiciel comme par un
    analyte du service : deux analytes sous le même code, ce sont deux séries
    de valeurs mélangées, et rien ne permettrait ensuite de les démêler.
    """
    # Repartir de ce que contient CETTE base : le catalogue en mémoire est
    # global au processus et peut porter les analytes d'une base ouverte
    # auparavant — restauration d'une sauvegarde, essai sur une autre base.
    # Refuser un code d'après un état périmé bloquerait un ajout légitime.
    charger_dans_le_catalogue(base)
    libelle = (libelle or "").strip()
    if not libelle:
        raise ValueError("Le libellé de l'analyte est obligatoire.")
    code = code_depuis_libelle(libelle)
    if not code:
        raise ValueError(f"« {libelle} » ne donne aucun code utilisable.")
    if cat.connu(code):
        raise ValueError(
            f"« {cat.analyte(code).libelle} » existe déjà sous le code {code}."
        )
    identifiant = base.inserer(
        "analyte_local",
        {"code": code, "libelle": libelle, "unite": unite or None,
         "borne_basse": borne_basse, "borne_haute": borne_haute},
        utilisateur_id=utilisateur_id,
    )
    charger_dans_le_catalogue(base)
    return identifiant


def tous(base: Base) -> list[dict]:
    return base.requete(
        "SELECT * FROM analyte_local WHERE supprime = 0 ORDER BY libelle"
    )


def retirer(base: Base, identifiant: str, *, utilisateur_id: str | None = None) -> None:
    """Retire un analyte de la liste à saisir. Les valeurs déjà enregistrées
    sous ce code restent en base et restent lisibles : ce qui a été mesuré a
    été mesuré."""
    base.supprimer_logiquement("analyte_local", identifiant, utilisateur_id=utilisateur_id)
    charger_dans_le_catalogue(base)


def charger_dans_le_catalogue(base: Base) -> None:
    """Rend les analytes du service visibles au reste du programme.

    Appelé à l'ouverture de l'écran des bilans, et après chaque ajout : c'est
    ce qui fait qu'un analyte ajouté porte son libellé partout — saisie,
    observation générée, export — et non son code brut.
    """
    cat.enregistrer_locaux(tous(base))
