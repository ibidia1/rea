"""Remplissage de la feuille de réanimation du service (couche C3).

La maquette est un fichier fourni par le service — `modeles/feuille_reanimation
_kairouan.html` — et ce module n'y met que des valeurs. Il ne dessine rien, ne
décide rien, et surtout **ne remplit jamais ce que le service écrit à la
main** : les constantes horaires, les bilans de la garde et les zones libres
restent vides sur la feuille imprimée.

Ce qu'il apporte de vraiment nouveau par rapport à une feuille vierge :

* les **bilans des deux derniers jours** déjà reportés, colonne par jour, la
  colonne du jour restant libre pour la garde ;
* les **examens demandés la veille** inscrits à leur ligne, avec l'heure à
  cocher ;
* un **rond par prise** sur la ligne du médicament, à l'heure calculée : c'est
  l'infirmier qui le coche, le logiciel ne fait que placer les ronds.

Le logiciel n'imprime que ce qui a été prescrit. Il ne propose ni ne calcule
aucune dose (SPEC §3.1) : la colonne « dose » restitue ce que le médecin a
saisi, telle quelle.
"""

from __future__ import annotations

import html
from datetime import date, timedelta
from pathlib import Path

from .. import analytes as cat, config, listes, referentiels
from ..db import Base
from ..domaine import calculs, prescription as dom
from ..domaine.dates import format_date_fr, jour_hospitalisation, parse_date
from ..services import bilans as bilans_service
from ..services import dispositifs as dispositifs_service
from ..services import microbiologie as micro_service
from ..services import prescriptions as prescriptions_service
from ..services import sejours as sejours_service
from .gabarit import Brut, rendre

MODELE = Path(__file__).resolve().parent.parent.parent / "modeles" / "feuille_reanimation_kairouan.html"

# Nombre de lignes pré-imprimées par bloc : c'est la maquette qui commande.
# Dépasser ferait déborder la page, alors on remplit et on complète à vide.
LIGNES_PAR_VOIE = {
    "ENTREES": ("entRows", 3),
    "PSE": ("pseRows", 6),
    "IV": ("ivRows", 8),
    "SC": ("scRows", 2),
    "PO": ("poRows", 5),
    "AEROSOL": ("aeroRows", 2),
    "KINE": ("kineRows", 2),
    "SOINS": ("soinsRows", 2),
}
LIGNES_BILANS_A_FAIRE = 2
LIGNES_MICROBIO = 6
NB_JOURS_BIOLOGIE = 3       # deux jours remplis + le jour en cours, laissé libre
NB_CRENEAUX_PAR_JOUR = 4


# --------------------------------------------------------------------------
# Petits fragments de mise en forme
# --------------------------------------------------------------------------

def _grille_heures(heures: set[int], *, symbole: str = "○") -> Brut:
    """Vingt-quatre cases, un rond aux heures d'administration.

    Le rond est vide : c'est l'infirmier qui le coche après avoir administré.
    Le logiciel dit *quand*, il ne dit jamais que c'est fait.
    """
    # Le service écrit « 24 h » pour minuit ; la grille imprimée va de 0 à 23.
    # Sans ce repli, la prise de minuit d'un ×4/j n'apparaîtrait nulle part.
    heures = {h % 24 for h in heures}
    cases = []
    for heure in range(24):
        contenu = (
            f'<span style="font-size:11px;line-height:1;color:#14595c">{symbole}</span>'
            if heure in heures else ""
        )
        cases.append(
            '<div style="display:flex;align-items:center;justify-content:center">'
            f"{contenu}</div>"
        )
    return Brut(
        '<div style="position:absolute;inset:0;display:grid;'
        'grid-template-columns:repeat(24,1fr)">' + "".join(cases) + "</div>"
    )


def _cellules_valeurs(valeurs: list[str], colonnes: int) -> Brut:
    """Une valeur par créneau, posée sur le fond réglé de la maquette."""
    cases = []
    for i in range(colonnes):
        texte = html.escape(valeurs[i]) if i < len(valeurs) and valeurs[i] else ""
        cases.append(
            '<div style="display:flex;align-items:center;justify-content:center;'
            'font-size:8px;line-height:1;overflow:hidden">'
            f"{texte}</div>"
        )
    return Brut(
        '<div style="position:absolute;inset:0;display:grid;'
        f'grid-template-columns:repeat({colonnes},1fr)">' + "".join(cases) + "</div>"
    )


def _ligne_vide(numero: str = "") -> dict:
    return {"numero": numero, "produit": "", "dose": "", "voie": "",
            "grille": Brut("")}


def _nombre(valeur) -> str:
    if valeur is None:
        return ""
    if isinstance(valeur, float):
        texte = f"{valeur:.2f}".rstrip("0").rstrip(".")
    else:
        texte = str(valeur)
    return texte.replace(".", ",")


# --------------------------------------------------------------------------
# Les blocs
# --------------------------------------------------------------------------

def _lignes_prescription(base: Base, sejour_id: str, date_jour: str) -> dict:
    """Une ligne par prescription active, un rond par prise."""
    pancarte = prescriptions_service.pancarte_du_jour(base, sejour_id, date_jour)
    par_voie = prescriptions_service.lignes_par_voie(pancarte["lignes"])
    blocs: dict[str, list] = {}
    debordements: list[str] = []

    for voie, (nom_liste, nb_lignes) in LIGNES_PAR_VOIE.items():
        # Les lignes arrêtées ce jour-là restent imprimées, barrées : une ligne
        # qui disparaît sans laisser de trace, c'est une administration
        # poursuivie par habitude, ou un arrêt que personne ne remarque.
        lignes = list(par_voie.get(voie, []))
        rendues = []
        for i, ligne in enumerate(lignes[:nb_lignes], start=1):
            arretee = ligne["statut"] != "active"
            heures = () if arretee else dom.horaires_pour_rythme(
                ligne.get("rythme"), ligne.get("horaires_override")
            )
            produit = ligne.get("produit") or ""
            if arretee:
                produit = Brut(
                    '<span class="arretee" style="text-decoration:line-through;'
                    f'color:#6d7c7b">{html.escape(produit)}</span>'
                    '<span style="font-size:8px;color:#a33b2a;margin-left:5px">'
                    "ARRÊTÉ</span>"
                )
            rendues.append({
                "numero": str(i),
                "produit": produit,
                "dose": _dose(ligne),
                "voie": listes.libelle(listes.SOUS_TYPES_ENTREES, ligne.get("sous_type"), "")
                        if voie == "ENTREES" else "",
                "grille": _grille_heures(set(heures)),
            })
        if len(lignes) > nb_lignes:
            debordements.append(
                f"{listes.VOIES[voie]['titre']} : {len(lignes) - nb_lignes} ligne(s) "
                "de plus que la feuille"
            )
        while len(rendues) < nb_lignes:
            rendues.append(_ligne_vide(str(len(rendues) + 1)))
        blocs[nom_liste] = rendues
    return {"blocs": blocs, "debordements": debordements}


def _dose(ligne: dict) -> str:
    """Ce que le médecin a saisi, restitué tel quel — jamais recalculé."""
    morceaux = []
    if ligne.get("dose"):
        morceaux.append(_nombre(ligne["dose"]) + (f" {ligne['unite']}" if ligne.get("unite") else ""))
    if ligne.get("vitesse"):
        morceaux.append(f"{_nombre(ligne['vitesse'])} cc/h")
    if ligne.get("volume_24h"):
        morceaux.append(f"{_nombre(ligne['volume_24h'])} mL")
    if ligne.get("dilution"):
        morceaux.append(str(ligne["dilution"]))
    return " · ".join(morceaux)


def _bilans_a_faire(base: Base, sejour_id: str, date_jour: str) -> list[dict]:
    """Les examens demandés la veille pour aujourd'hui, à leur ligne.

    C'est la demande faite hier soir qui devient la consigne d'aujourd'hui :
    sans ce report, elle ne vit que dans la tête de celui qui l'a écrite.
    """
    veille = (parse_date(date_jour) - timedelta(days=1)).isoformat()
    demandes = prescriptions_service.pancarte_du_jour(
        base, sejour_id, date_jour
    )["bilans_demandes"]
    heure_defaut = int(config.HEURE_PRELEVEMENT_DEFAUT.split(":")[0])
    lignes = []
    for demande in demandes[:LIGNES_BILANS_A_FAIRE]:
        heure = demande.get("heure_prelevement") or config.HEURE_PRELEVEMENT_DEFAUT
        try:
            heures = {int(str(heure).split(":")[0])}
        except (ValueError, TypeError):
            heures = {heure_defaut}
        lignes.append({
            "libelle": listes.libelle(
                listes.EXAMENS_A_DEMANDER, demande["examen_code"],
                demande["examen_code"],
            ),
            "origine": f"dem. {format_date_fr(veille)[:5]}",
            "grille": _grille_heures(heures, symbole="◻"),
        })
    while len(lignes) < LIGNES_BILANS_A_FAIRE:
        lignes.append({"libelle": "", "origine": "", "grille": Brut("")})
    return lignes


def _jours_biologie(date_jour: str) -> list[str]:
    """Les colonnes de jours : les précédents d'abord, le jour en cours en
    dernier — c'est celui-là que la garde remplira à la main."""
    aujourdhui = parse_date(date_jour)
    return [
        (aujourdhui - timedelta(days=n)).isoformat()
        for n in range(NB_JOURS_BIOLOGIE - 1, -1, -1)
    ]


def _valeurs_biologie(
    base: Base, sejour_id: str, jours: list[str], codes: list[tuple[str, str]],
    source: str,
) -> list[dict]:
    """Une ligne par paramètre, ses valeurs rangées par jour et par créneau.

    Le jour en cours est laissé vide : les bilans de la garde s'y écrivent à la
    main pendant la nuit et sont ressaisis le lendemain matin.
    """
    lignes = []
    for code, libelle in codes:
        cellules: list[str] = []
        for index_jour, jour in enumerate(jours):
            dernier = index_jour == len(jours) - 1
            creneaux = [""] * NB_CRENEAUX_PAR_JOUR
            if not dernier:
                creneaux = _creneaux_du_jour(base, sejour_id, jour, code, source)
            cellules.extend(creneaux)
        lignes.append({
            "libelle": libelle,
            "valeurs": _cellules_valeurs(
                cellules, NB_JOURS_BIOLOGIE * NB_CRENEAUX_PAR_JOUR
            ),
        })
    return lignes


def _creneaux_du_jour(
    base: Base, sejour_id: str, jour: str, code: str, source: str
) -> list[str]:
    """Les valeurs d'un paramètre un jour donné, dans l'ordre des heures."""
    if source == "bilan":
        lignes = [
            l for l in bilans_service.resultats_du_sejour(base, sejour_id)
            if l["analyte"] == code and (l["date_heure"] or "").startswith(jour)
        ]
        valeurs = [_nombre(l["valeur_num"]) for l in lignes]
    else:
        lignes = [
            g for g in bilans_service.gaz_du_sang_du_sejour(base, sejour_id)
            if (g["date_heure"] or "").startswith(jour)
        ]
        valeurs = [_nombre(g.get(code)) for g in lignes]
    valeurs = [v for v in valeurs if v]
    return (valeurs + [""] * NB_CRENEAUX_PAR_JOUR)[:NB_CRENEAUX_PAR_JOUR]


def _abords(base: Base, sejour_id: str, date_jour: str) -> list[dict]:
    """Les dispositifs en place, cochés, avec leur compteur de jours.

    Le compteur est calculé, jamais recopié : c'est la seule ligne de la
    feuille qu'un interne ne peut pas se tromper en reportant.
    """
    etats = dispositifs_service.etats(base, sejour_id, date_jour)
    lignes = []
    for etat in etats:
        coche = "☑" if etat.en_place else "☐"
        style = ("font-weight:600;color:#16201f" if etat.en_place
                 else "color:#6d7c7b")
        lignes.append({"texte": f"{coche} {etat.texte}", "style": style})
    if not lignes:
        lignes.append({"texte": "☐ Aucun dispositif enregistré",
                       "style": "color:#6d7c7b"})
    return lignes


def _examens_demain(base: Base, sejour_id: str, date_jour: str) -> list[dict]:
    """Les cases « à demander pour demain », cochées d'après la saisie."""
    demain = (parse_date(date_jour) + timedelta(days=1)).isoformat()
    demandes = {
        d["examen_code"]
        for d in prescriptions_service.pancarte_du_jour(
            base, sejour_id, demain
        )["bilans_demandes"]
    }
    lignes = []
    for codes, libelle in referentiels.charger("feuille_lignes", "examens_demain"):
        coche = bool(set(codes) & demandes)
        lignes.append({
            "case": "☑" if coche else "☐",
            "libelle": libelle,
            "style": "font-weight:700;color:#14595c" if coche else "",
        })
    return lignes


def _microbiologie(base: Base, sejour_id: str) -> list[dict]:
    lignes = []
    for ligne in micro_service.du_sejour(base, sejour_id)[:LIGNES_MICROBIO]:
        resultat = listes.libelle(listes.RESULTATS_MICROBIO, ligne["resultat"])
        if ligne["resultat"] == "positif" and ligne.get("germe"):
            resultat = ligne["germe"]
        lignes.append({
            "prelevement": listes.libelle(listes.PRELEVEMENTS, ligne["type_prelevement"]),
            "date": format_date_fr(ligne["date_prelevement"])[:5],
            "resultat": resultat,
        })
    while len(lignes) < LIGNES_MICROBIO:
        lignes.append({"prelevement": "", "date": "", "resultat": ""})
    return lignes


# --------------------------------------------------------------------------
# Assemblage
# --------------------------------------------------------------------------

def contexte(base: Base, sejour_id: str, date_jour: str) -> dict:
    sejour = sejours_service.sejour_avec_patient(base, sejour_id)
    if sejour is None:
        raise ValueError(f"Séjour inconnu : {sejour_id}")

    prescrit = _lignes_prescription(base, sejour_id, date_jour)
    jours = _jours_biologie(date_jour)
    lignes_ref = referentiels.charger("feuille_lignes")

    ideal = calculs.poids_ideal_devine(
        taille_cm=sejour.get("taille_cm"), sexe=sejour.get("sexe")
    )
    allergies = sejours_service.allergies_du_patient(base, sejour["patient_id"])

    ctx = {
        # En-tête
        "date_fr": format_date_fr(date_jour),
        "lit": sejour.get("lit_admission") or "",
        "jour_hosp": f"J{jour_hospitalisation(sejour['date_admission'], date_jour)}",
        "dossier": sejour.get("matricule") or "",
        "groupe_sanguin": "",          # non saisi : reste à écrire à la main
        "nom_patient": sejour.get("nom_affichage") or "",
        "age": _age(sejour, date_jour),
        "poids_ideal": f"{_nombre(ideal.valeur)} kg" if ideal.disponible else "",
        # Le mot « ALLERGIE » est écrit en toutes lettres : c'est la ligne
        # qu'un relecteur pressé doit voir sans la chercher.
        "allergies": (" · ".join(a["libelle"] for a in allergies)
                      if allergies else "ALLERGIE : non renseignée"),
        "scores": _scores(base, sejour_id, date_jour),
        "abords": _abords(base, sejour_id, date_jour),
        "hours": [str(h) for h in range(24)],
        # Prescription
        **prescrit["blocs"],
        "bilanPrescRows": _bilans_a_faire(base, sejour_id, date_jour),
        # Verso — surveillance laissée manuscrite
        "survRowsA": _lignes_manuscrites(lignes_ref["surveillance_a"]),
        "survRowsB": _lignes_manuscrites(lignes_ref["surveillance_b"]),
        "survRowsC": _lignes_manuscrites(lignes_ref["surveillance_c"]),
        "bilanRows": _lignes_manuscrites([("", "")] * 5),
        # Verso — biologie reportée
        "days": [format_date_fr(j)[:5] for j in jours],
        "slots": [str(i + 1) for i in range(NB_CRENEAUX_PAR_JOUR)],
        "bioHemato": _valeurs_biologie(base, sejour_id, jours, list(lignes_ref["hemato"]), "bilan"),
        "bioIono": _valeurs_biologie(base, sejour_id, jours, list(lignes_ref["iono"]), "bilan"),
        "bioRenal": _valeurs_biologie(base, sejour_id, jours, list(lignes_ref["renal"]), "bilan"),
        "bioHepat": _valeurs_biologie(base, sejour_id, jours, list(lignes_ref["hepat"]), "bilan"),
        "bioAutres": _valeurs_biologie(base, sejour_id, jours, list(lignes_ref["autres"]), "bilan"),
        "gdsGaz": _valeurs_biologie(base, sejour_id, jours, list(lignes_ref["gaz"]), "gaz"),
        "gdsVent": _valeurs_biologie(base, sejour_id, jours, list(lignes_ref["ventilation"]), "gaz"),
        "infRows": _microbiologie(base, sejour_id),
        "examensDemain": _examens_demain(base, sejour_id, date_jour),
        "pied": _pied(prescrit["debordements"]),
    }
    return ctx


def _lignes_manuscrites(codes) -> list[dict]:
    """Des lignes que le logiciel étiquette mais ne remplit pas : les
    constantes horaires sont relevées au lit du malade, sur le papier."""
    return [{"libelle": libelle, "valeurs": Brut("")} for _code, libelle in codes]


def _age(sejour: dict, date_jour: str) -> str:
    from ..domaine.dates import age_ans

    age = age_ans(sejour.get("date_naissance"), date_jour)
    return f"{age} ans" if age is not None else ""


def _scores(base: Base, sejour_id: str, date_jour: str) -> list[str]:
    from ..services import scores as scores_service

    sofa = scores_service.sofa(base, sejour_id, date_jour)
    igs2 = scores_service.igs2(base, sejour_id)
    return [
        f"SOFA {sofa.total}" + ("" if sofa.complet else " (incomplet)"),
        f"IGS II {igs2.total}" + ("" if igs2.complet else " (incomplet)"),
    ]


def _pied(debordements: list[str]) -> str:
    if debordements:
        return "⚠ " + " · ".join(debordements)
    return ""


def generer(base: Base, sejour_id: str, date_jour: str) -> str:
    """La feuille complète, prête à imprimer."""
    gabarit = MODELE.read_text(encoding="utf-8")
    corps = rendre(gabarit, contexte(base, sejour_id, date_jour))
    return _document(corps, date_jour)


def _document(corps: str, date_jour: str) -> str:
    """L'enveloppe imprimable : A3 paysage, une page par section.

    Pas de police téléchargée ni de script : la feuille doit s'imprimer d'un
    poste hors ligne, tout de suite, sans que rien ne manque au chargement.
    """
    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<title>Feuille de réanimation — {html.escape(format_date_fr(date_jour))}</title>
<style>
  @page {{ size: A3 landscape; margin: 0; }}
  html, body {{ margin: 0; padding: 0; background: #fff; }}
  section.page {{ page-break-after: always; break-after: page; }}
  section.page:last-of-type {{ page-break-after: auto; break-after: auto; }}
  @media screen {{
    body {{ background: #e8ebe9; padding: 12px; }}
    section.page {{ width: 420mm; margin: 0 auto 12px; box-shadow: 0 2px 10px #0003; }}
  }}
</style></head><body>
{corps}
</body></html>"""
