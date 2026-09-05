"""Impression de la feuille et conservation de ce qui a été imprimé
(SPEC §2.2, §5, exception à la règle 5).

Ce module ne dessine rien : la mise en page est la maquette A3 du service
(`modeles/feuille_reanimation_kairouan.html`), remplie par `rea/rendu/`. Ici
on rassemble les données, on demande le rendu, et on garde une copie figée de
ce qui est sorti sur l'imprimante — c'est cette copie qui fait foi, pas une
feuille regénérée plus tard à partir de données qui ont bougé depuis.
"""

from __future__ import annotations

from .. import config
from ..db import Base, maintenant
from . import feuille_dossier


def generer_html(base: Base, sejour_id: str, date_jour: str) -> str:
    """La feuille du service, remplie.

    La mise en page vient de `modeles/feuille_reanimation_kairouan.html`, la
    maquette A3 fournie par le service : ce module ne la redessine pas, il
    demande son remplissage à la couche de rendu (règle R3). Remplacer la
    maquette suffit à changer la feuille.

    Les deux temps sont séparés : on rassemble d'abord tout ce qu'il faut lire
    en base, puis on le passe au rendu — qui n'a plus aucun moyen d'aller
    chercher quoi que ce soit lui-même.
    """
    from ..rendu import feuille

    return feuille.generer(feuille_dossier.rassembler(base, sejour_id, date_jour))


def imprimer(base: Base, sejour_id: str, date_jour: str, *, utilisateur_id: str | None = None) -> dict:
    html_genere = generer_html(base, sejour_id, date_jour)
    derniere = base.une_ligne(
        "SELECT MAX(version) AS v FROM pancarte_snapshot WHERE sejour_id = ? AND date_jour = ?",
        (sejour_id, date_jour),
    )
    version = (derniere["v"] or 0) + 1 if derniere else 1
    id_ = base.inserer(
        "pancarte_snapshot",
        {
            "sejour_id": sejour_id,
            "date_jour": date_jour,
            "version": version,
            "html": html_genere,
            "format_page": config.FORMAT_PAGE,
            "imprime_le": maintenant(),
            "imprime_par": utilisateur_id,
        },
        utilisateur_id=utilisateur_id,
        action="impression",
    )
    return base.une_ligne("SELECT * FROM pancarte_snapshot WHERE id = ?", (id_,))


def snapshots_du_sejour(base: Base, sejour_id: str) -> list[dict]:
    """La liste des fiches déjà imprimées pour ce séjour — pas leur contenu,
    trop lourd pour un simple historique. Voir `snapshot()` pour le relire."""
    return base.requete(
        "SELECT id, date_jour, version, imprime_le, imprime_par FROM pancarte_snapshot "
        "WHERE sejour_id = ? ORDER BY date_jour DESC, version DESC",
        (sejour_id,),
    )


def snapshot(base: Base, snapshot_id: str) -> dict | None:
    """Relit une fiche telle qu'elle a été imprimée.

    Le HTML rendu à ce moment-là est stocké tel quel (règle de conception 6 —
    le texte est calculé, sauf les instantanés de pancarte, qui sont
    immuables) : c'est la seule façon de revoir une fiche exactement comme
    elle était le jour où elle est sortie, même si le dossier a changé depuis.
    """
    return base.une_ligne(
        "SELECT p.*, u.nom AS imprime_par_nom FROM pancarte_snapshot p "
        "LEFT JOIN utilisateur u ON u.id = p.imprime_par WHERE p.id = ?",
        (snapshot_id,),
    )


def snapshots_par_date(base: Base, date_jour: str) -> list[dict]:
    """Toutes les fiches imprimées un jour donné, tous patients confondus —
    la relecture « qu'y avait-il dans le service ce jour-là »."""
    return base.requete(
        "SELECT p.id, p.sejour_id, p.date_jour, p.version, p.imprime_le, "
        "s.lit_admission, pt.nom_affichage, u.nom AS imprime_par_nom "
        "FROM pancarte_snapshot p "
        "JOIN sejour s ON s.id = p.sejour_id "
        "JOIN patient pt ON pt.id = s.patient_id "
        "LEFT JOIN utilisateur u ON u.id = p.imprime_par "
        "WHERE p.date_jour = ? ORDER BY s.lit_admission, p.version DESC",
        (date_jour,),
    )


def dates_avec_impression(base: Base) -> list[str]:
    """Les jours pour lesquels au moins une fiche existe — sert à peupler le
    sélecteur de date sans proposer des jours vides."""
    lignes = base.requete(
        "SELECT DISTINCT date_jour FROM pancarte_snapshot ORDER BY date_jour DESC"
    )
    return [l["date_jour"] for l in lignes]
