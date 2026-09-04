"""Impression de la pancarte (SPEC §2.2, §5, exception à la règle 5).

⚠️ Mise en page **provisoire**. Le fichier PDF du prescrit réellement utilisé
au service n'a pas encore été fourni (SPEC §7.1, « documents attendus ») ;
cette page reprend la structure décrite dans le pptx de présentation, mais
sera reprise trait pour trait sur le PDF réel dès qu'il arrive. Le format se
bascule en une ligne (`rea.config.FORMAT_PAGE`) pour passer en A3.
"""

from __future__ import annotations

import html as html_module

from .. import config, listes
from ..db import Base, maintenant
from ..domaine import prescription as dom
from ..domaine.dates import age_ans, format_date_fr, jour_hospitalisation
from . import prescriptions as prescriptions_service
from . import sejours as sejours_service


def _e(texte) -> str:
    return html_module.escape(str(texte)) if texte is not None else ""


def _css(format_page: str) -> str:
    taille, orientation = (format_page.split(" ", 1) + [""])[:2]
    return f"""
    @page {{ size: {taille} {orientation}; margin: 12mm; }}
    * {{ box-sizing: border-box; }}
    body {{ font-family: Arial, Helvetica, sans-serif; font-size: 11px; color: #111; margin: 0; }}
    .entete {{ display: flex; justify-content: space-between; align-items: baseline;
        border-bottom: 2px solid #111; padding-bottom: 4px; margin-bottom: 6px; }}
    .entete h1 {{ font-size: 16px; margin: 0; }}
    .entete .jour {{ font-size: 14px; font-weight: bold; }}
    .brouillon {{ background: #fff3cd; border: 1px solid #d6a900; color: #6b5300;
        padding: 3px 6px; margin-bottom: 6px; font-size: 9px; }}
    .allergie {{ background: #ffdddd; border: 1.5px solid #b00000; color: #7a0000;
        font-weight: bold; padding: 4px 8px; margin-bottom: 6px; }}
    table.voie {{ width: 100%; border-collapse: collapse; margin-bottom: 6px; }}
    table.voie caption {{ text-align: left; font-weight: bold; background: #eee;
        padding: 2px 4px; border: 1px solid #999; }}
    table.voie td {{ border: 1px solid #999; padding: 2px 4px; vertical-align: top; }}
    .arretee {{ text-decoration: line-through; color: #777; }}
    .echue {{ background: #fff2cc; }}
    .bilans span {{ display: inline-block; margin-right: 10px; }}
    .entrees-total {{ font-weight: bold; margin-bottom: 6px; }}
    .zone-manuscrite {{ border: 1px solid #999; min-height: 90px; margin-bottom: 6px; padding: 4px; }}
    .zone-manuscrite .titre {{ font-weight: bold; font-size: 10px; color: #555; }}
    .pied {{ font-size: 9px; color: #666; margin-top: 8px; }}
    """


def generer_html(base: Base, sejour_id: str, date_jour: str) -> str:
    """La feuille du service, remplie.

    La mise en page vient de `modeles/feuille_reanimation_kairouan.html`, la
    maquette A3 fournie par le service : ce module ne la redessine pas, il
    demande son remplissage à la couche de rendu (règle R3). Remplacer la
    maquette suffit à changer la feuille.
    """
    from ..rendu import feuille

    return feuille.generer(base, sejour_id, date_jour)


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
