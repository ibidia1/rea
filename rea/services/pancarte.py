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
    sejour = sejours_service.sejour_avec_patient(base, sejour_id)
    pancarte = prescriptions_service.pancarte_du_jour(base, sejour_id, date_jour)
    allergies = sejours_service.allergies_du_patient(base, sejour["patient_id"])
    age = age_ans(sejour["date_naissance"])
    jour_hosp = jour_hospitalisation(sejour["date_admission"], date_jour)

    m = [f"<style>{_css(config.FORMAT_PAGE)}</style>"]
    m.append('<div class="brouillon">Mise en page provisoire — sera reprise sur le PDF du prescrit réel</div>')
    m.append('<div class="entete">')
    m.append(
        f"<div><h1>{_e(sejour['nom_affichage'])}</h1>"
        f"Lit {_e(sejour['lit_admission'])} · "
        f"{_e(age) if age is not None else '?'} ans · matricule {_e(sejour['matricule'])}</div>"
    )
    m.append(f'<div class="jour">{_e(format_date_fr(date_jour))} — J{jour_hosp}</div>')
    m.append("</div>")

    if allergies:
        libelles = ", ".join(_e(a["libelle"]) for a in allergies)
        m.append(f'<div class="allergie">⚠ ALLERGIE : {libelles}</div>')

    for code_voie in listes.ORDRE_VOIES:
        lignes = pancarte["lignes_par_voie"].get(code_voie, [])
        if not lignes:
            continue
        titre = listes.VOIES[code_voie]["titre"]
        m.append('<table class="voie">')
        m.append(f"<caption>{_e(titre)}</caption>")
        for ligne in lignes:
            etiquette = dom.etiquette_jour(ligne, date_jour)
            classes = []
            if ligne["statut"] == "arretee":
                classes.append("arretee")
            if etiquette.echue:
                classes.append("echue")
            classe_attr = f' class="{" ".join(classes)}"' if classes else ""
            m.append(f"<tr><td{classe_attr}>{_e(dom.libelle_ligne(ligne, date_jour))}</td></tr>")
        m.append("</table>")

    if pancarte["bilans_demandes"]:
        m.append('<div class="bilans"><b>Bilans demandés :</b> ')
        for b in pancarte["bilans_demandes"]:
            libelle = listes.libelle(listes.EXAMENS_A_DEMANDER, b["examen_code"])
            m.append(f'<span>☐ {_e(libelle)} ({_e(b["heure_prelevement"])})</span>')
        m.append("</div>")

    m.append(
        f'<div class="entrees-total">Entrées calculées sur 24 h : '
        f'{pancarte["bilan_entrees"].total_ml:.0f} mL</div>'
    )

    for titre in ("Constantes horaires", "Diurèse / drains", "Observations"):
        m.append(f'<div class="zone-manuscrite"><div class="titre">{titre}</div></div>')

    m.append(f'<div class="pied">Généré le {_e(format_date_fr(date_jour))} — format {_e(config.FORMAT_PAGE)}</div>')
    return "\n".join(m)


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
    return base.requete(
        "SELECT id, date_jour, version, imprime_le, imprime_par FROM pancarte_snapshot "
        "WHERE sejour_id = ? ORDER BY date_jour DESC, version DESC",
        (sejour_id,),
    )
