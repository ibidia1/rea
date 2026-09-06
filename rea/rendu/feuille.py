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
from datetime import timedelta
from pathlib import Path

from .. import config, listes, referentiels
from ..domaine import calculs, prescription as dom
from ..domaine.dates import format_date_fr, jour_hospitalisation, parse_date
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

# La journée du service commence à 8 h, pas à minuit : la relève du matin
# ouvre la feuille, et la colonne « 0 » en tête n'a jamais rien voulu dire
# pour personne. La grille imprimée suit cet ordre plutôt que 0-23.
ORDRE_HEURES = tuple(range(8, 24)) + tuple(range(0, 8))


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
    for heure in ORDRE_HEURES:
        contenu = (
            f'<span style="font-size:15px;font-weight:700;line-height:1;'
            f'color:#14595c">{symbole}</span>'
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
    return {"numero": numero, "produit": "", "dose": "", "grille": Brut("")}


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

def _ligne_sedation_pse(dossier) -> list[dict]:
    """La sédation en cours, reportée dans le bloc P.S.E. en plus des abords.

    Elle est déjà cochée dans les abords, avec son compteur de jours : c'est
    la lecture neurologique. Mais la vitesse qui la fait couler est aussi une
    consigne infirmière, au même titre qu'une noradrénaline ou un midazolam
    prescrit en ligne — elle doit donc être là où les seringues électriques
    se règlent, pas seulement dans la case des dispositifs.
    """
    sedation = next((e for e in dossier.etats_dispositifs if e.type == "sedation" and e.en_place), None)
    if sedation is None:
        return []
    details = sedation.details or {}
    produit = details.get("molecules") or "Sédation"
    dose = f"{_nombre(details['vitesse'])} cc/h" if details.get("vitesse") else ""
    return [{
        "numero": "1",
        "produit": Brut(
            f'{html.escape(produit)} <span style="font-size:7.5px;color:#5e6d6c">'
            "— sédation</span>"
        ),
        "dose": dose,
        "grille": Brut(""),
    }]


def _lignes_prescription(dossier) -> dict:
    """Une ligne par prescription active, un rond par prise."""
    par_voie = dossier.lignes_par_voie
    blocs: dict[str, list] = {}
    debordements: list[str] = []
    taux_remplissage: dict[str, float] = {}

    # La sédation posée comme dispositif occupe une ligne du bloc P.S.E. avant
    # les lignes prescrites — elle vient du dossier, pas d'une prescription.
    lignes_synthetiques = {"PSE": _ligne_sedation_pse(dossier)}

    for voie, (nom_liste, nb_lignes) in LIGNES_PAR_VOIE.items():
        synthetiques = lignes_synthetiques.get(voie, [])
        rendues = list(synthetiques)
        # Les lignes arrêtées ce jour-là restent imprimées, barrées : une ligne
        # qui disparaît sans laisser de trace, c'est une administration
        # poursuivie par habitude, ou un arrêt que personne ne remarque.
        lignes = list(par_voie.get(voie, []))
        place_restante = max(nb_lignes - len(synthetiques), 0)
        for ligne in lignes[:place_restante]:
            arretee = ligne["statut"] != "active"
            heures = () if arretee else dom.horaires_pour_rythme(
                ligne.get("rythme"), ligne.get("horaires_override")
            )
            produit = ligne.get("produit") or ""
            if voie == "ENTREES" and ligne.get("sous_type"):
                # La colonne Voie a disparu (les blocs sont déjà organisés par
                # voie) ; ce qu'elle portait d'utile pour les entrées —
                # perfusion ou nutrition — reste lisible, accolé au produit.
                sous_type = listes.libelle(listes.SOUS_TYPES_ENTREES, ligne["sous_type"])
                produit = f"{produit} ({sous_type})"
            if arretee:
                produit = Brut(
                    '<span class="arretee" style="text-decoration:line-through;'
                    f'color:#6d7c7b">{html.escape(produit)}</span>'
                    '<span style="font-size:8px;color:#a33b2a;margin-left:5px">'
                    "ARRÊTÉ</span>"
                )
            rendues.append({
                "numero": str(len(rendues) + 1),
                "produit": produit,
                "dose": _dose(ligne),
                "grille": _grille_heures(set(heures)),
            })
        total_demande = len(synthetiques) + len(lignes)
        if total_demande > nb_lignes:
            debordements.append(
                f"{listes.VOIES[voie]['titre']} : {total_demande - nb_lignes} ligne(s) "
                "de plus que la feuille"
            )
        # Plus de la moitié des lignes prévues sont vides : un texte plus grand
        # se lit mieux depuis le pied du lit, et la place ne manque pas.
        taux_remplissage[nom_liste] = len(rendues) / nb_lignes if nb_lignes else 1.0
        while len(rendues) < nb_lignes:
            rendues.append(_ligne_vide(str(len(rendues) + 1)))
        blocs[nom_liste] = rendues
    return {"blocs": blocs, "debordements": debordements, "taux_remplissage": taux_remplissage}


def _dose(ligne: dict) -> str:
    """Ce que le médecin a saisi, restitué tel quel — jamais recalculé.

    Une vitesse de seringue électrique prime sur tout le reste : c'est le
    seul nombre qu'un infirmier règle sur la pompe. Sinon, le nombre de
    comprimés ou d'ampoules par prise s'affiche à côté du dosage — le mot
    suit la voie (comprimé en PO, ampoule ailleurs) — parce qu'un dosage en
    milligrammes ne dit pas combien de boîtes ouvrir.
    """
    if ligne.get("vitesse"):
        morceaux = [f"{_nombre(ligne['vitesse'])} cc/h"]
        if ligne.get("dilution"):
            morceaux.append(str(ligne["dilution"]))
        return " · ".join(morceaux)

    morceaux = []
    if ligne.get("dose"):
        morceaux.append(_nombre(ligne["dose"]) + (f" {ligne['unite']}" if ligne.get("unite") else ""))
    if ligne.get("nb_ampoules"):
        mot = "cp" if ligne.get("voie") == "PO" else "amp"
        morceaux.append(f"{_nombre(ligne['nb_ampoules'])} {mot}")
    if ligne.get("volume_24h"):
        morceaux.append(f"{_nombre(ligne['volume_24h'])} mL")
    if ligne.get("dilution") and not morceaux:
        morceaux.append(str(ligne["dilution"]))
    return " · ".join(morceaux)


def _bilans_a_faire(dossier) -> list[dict]:
    """Les examens demandés la veille pour aujourd'hui, à leur ligne.

    C'est la demande faite hier soir qui devient la consigne d'aujourd'hui :
    sans ce report, elle ne vit que dans la tête de celui qui l'a écrite.
    """
    veille = (parse_date(dossier.date_jour) - timedelta(days=1)).isoformat()
    demandes = dossier.pancarte["bilans_demandes"]
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
    dossier, jours: list[str], lignes_spec: list[tuple], source: str,
) -> list[dict]:
    """Une ligne par paramètre, ses valeurs rangées par jour et par créneau.

    Le jour en cours est laissé vide : les bilans de la garde s'y écrivent à la
    main pendant la nuit et sont ressaisis le lendemain matin.

    `lignes_spec` : (code, libellé) ou (codes, libellé) — une ligne peut
    combiner plusieurs paramètres (« TP / INR », « Ca²⁺ / Mg²⁺ / Phosphore »),
    affichés côte à côte dans la même case, séparés par « / » (remarque du
    service, 6 septembre : une ligne par paramètre isolé prenait trop de place
    pour des valeurs toujours lues ensemble).
    """
    lignes = []
    for codes, libelle in lignes_spec:
        if isinstance(codes, str):
            codes = (codes,)
        cellules_par_code = []
        for code in codes:
            cellules: list[str] = []
            for index_jour, jour in enumerate(jours):
                dernier = index_jour == len(jours) - 1
                creneaux = [""] * NB_CRENEAUX_PAR_JOUR
                if not dernier:
                    creneaux = _creneaux_du_jour(dossier, jour, code, source)
                cellules.extend(creneaux)
            cellules_par_code.append(cellules)
        cellules_combinees = [
            "/".join(v for v in valeurs_du_creneau if v)
            for valeurs_du_creneau in zip(*cellules_par_code)
        ]
        lignes.append({
            "libelle": libelle,
            "valeurs": _cellules_valeurs(
                cellules_combinees, NB_JOURS_BIOLOGIE * NB_CRENEAUX_PAR_JOUR
            ),
        })
    return lignes


def _creneaux_du_jour(dossier, jour: str, code: str, source: str) -> list[str]:
    """Les valeurs d'un paramètre un jour donné, dans l'ordre des heures."""
    if source == "bilan":
        lignes = [
            l for l in dossier.resultats
            if l["analyte"] == code and (l["date_heure"] or "").startswith(jour)
        ]
        valeurs = [_nombre(l["valeur_num"]) for l in lignes]
    else:
        lignes = [
            g for g in dossier.gaz_du_sang
            if (g["date_heure"] or "").startswith(jour)
        ]
        valeurs = [_nombre(g.get(code)) for g in lignes]
    valeurs = [v for v in valeurs if v]
    return (valeurs + [""] * NB_CRENEAUX_PAR_JOUR)[:NB_CRENEAUX_PAR_JOUR]


def _rapport_pf(dossier, jours: list[str]) -> Brut:
    """Le rapport PaO₂/FiO₂, recalculé pour chaque gaz du sang.

    C'est le seul chiffre de la feuille qui n'est ni saisi ni recopié : il se
    déduit de deux valeurs déjà là, et le recalculer à la main à chaque gaz du
    sang est exactement le genre d'arithmétique qu'on finit par ne plus faire.

    Il n'est écrit que là où les deux ingrédients existent : une case vide dit
    « pas de gaz du sang », jamais « rapport normal ».
    """
    cellules: list[str] = []
    for index_jour, jour in enumerate(jours):
        creneaux = [""] * NB_CRENEAUX_PAR_JOUR
        if index_jour < len(jours) - 1:          # le jour en cours reste à la garde
            valeurs = []
            for gaz in dossier.gaz_du_sang:
                if not (gaz["date_heure"] or "").startswith(jour):
                    continue
                rapport = calculs.rapport_pao2_fio2(gaz.get("pao2"), gaz.get("fio2"))
                if rapport.disponible:
                    valeurs.append(_nombre(rapport.valeur))
            creneaux = (valeurs + [""] * NB_CRENEAUX_PAR_JOUR)[:NB_CRENEAUX_PAR_JOUR]
        cellules.extend(creneaux)
    return _cellules_valeurs(cellules, NB_JOURS_BIOLOGIE * NB_CRENEAUX_PAR_JOUR)


def _texte_abrege_dispositif(etat) -> str:
    """La forme compacte d'un dispositif pour la ligne « Abords » imprimée.

    Les écrans du logiciel gardent le libellé complet (`etat.texte`) — c'est
    seulement sur le papier, où la ligne est haute de deux centimètres, que la
    place manque. Les abréviations viennent d'un fichier
    (`referentiels/feuille_abreviations.json`), pas du code : le service peut
    en changer sans reprogrammer.
    """
    abrev_types = referentiels.charger("feuille_abreviations", "types")
    abrev_sites = referentiels.charger("feuille_abreviations", "sites")
    nom = abrev_types.get(etat.type, listes.libelle_dispositif(etat.type))
    site = abrev_sites.get(etat.site, etat.site) if etat.site else None
    details = etat.details or {}

    parametres: list[str] = []
    if etat.type == "intubation":
        if details.get("taille_sonde"):
            parametres.append(_nombre(details["taille_sonde"]))
        if details.get("reperage_cm"):
            parametres.append(f"{_nombre(details['reperage_cm'])}cm")
    elif etat.type == "tracheotomie" and details.get("taille_sonde"):
        parametres.append(f"n°{_nombre(details['taille_sonde'])}")
    elif etat.type == "sng" and details.get("fixation_cm"):
        if site:
            parametres.append(site)
        parametres.append(f"{_nombre(details['fixation_cm'])}cm")
    elif etat.type == "kt_central" and details.get("nb_voies"):
        if site:
            parametres.append(site)
        parametres.append(f"{_nombre(details['nb_voies'])} voies")
    elif site:
        parametres.append(site)

    texte = nom
    if parametres:
        texte += f" ({', '.join(parametres)})"
    if etat.jour:
        texte += f" J{etat.jour}"
    return texte


def _lignes_atcd(dossier) -> list[str]:
    """Un antécédent par ligne — pas une phrase à reparser, une liste à lire
    d'un coup d'œil. « Inconnu » et « sans antécédent connu » s'affichent
    identiquement à la garde — le tiret qui les distingue reste en base
    (SPEC §4.2 bis), pas sur une feuille que l'infirmier n'a pas à
    interpréter."""
    if not dossier.antecedents:
        return ["Non renseignés" if dossier.etat_antecedents == "non_renseigne" else "Aucun connu"]
    lignes = []
    for a in dossier.antecedents:
        texte = a["libelle"]
        if a.get("quantification_valeur") is not None:
            texte += f" ({_nombre(a['quantification_valeur'])} {a.get('quantification_unite') or ''})"
        elif a.get("precision"):
            texte += f" ({a['precision']})"
        lignes.append(texte)
    return lignes


def _circonstances_texte(dossier) -> str | None:
    """Le mécanisme, en toutes lettres — absent si non traumatique ou si
    jamais renseigné (rien à afficher plutôt qu'une ligne vide)."""
    sejour = dossier.sejour
    if not sejour.get("traumatique") or not sejour.get("mecanisme"):
        return None
    if sejour["mecanisme"] == "non_renseigne":
        return None
    texte = listes.libelle(listes.MECANISMES, sejour["mecanisme"])
    if sejour.get("mecanisme_detail"):
        texte += f" — {sejour['mecanisme_detail']}"
    return texte


def _transport_texte(dossier) -> str:
    sejour = dossier.sejour
    libelle = listes.libelle(listes.PROVENANCES, sejour.get("provenance_type"), "Non renseignée")
    if sejour.get("provenance_detail"):
        libelle += f" ({sejour['provenance_detail']})"
    if sejour.get("est_readmission"):
        libelle += " — réadmission"
    return libelle


def _lignes_motif(dossier) -> list[str]:
    """Reprend le motif d'admission saisi une fois sur l'onglet Identité —
    l'interne n'a plus à le retranscrire à la main sur la feuille. Une
    région ou un motif associé par ligne, jamais recomposés en une seule
    phrase à virgules."""
    sejour = dossier.sejour
    if sejour.get("traumatique"):
        lignes = [
            listes.libelle(listes.REGIONS_TRAUMATIQUES, r["region"])
            + (f" : {r['precision']}" if r.get("precision") else "")
            for r in dossier.regions_traumatiques
        ] or ["Régions non précisées"]
        lignes += [
            listes.libelle_motif(m["code"]) for m in dossier.motifs if not m["principal"]
        ]
        return lignes
    principal = next((m for m in dossier.motifs if m["principal"]), None)
    lignes = [listes.libelle_motif(principal["code"])] if principal else []
    lignes += [listes.libelle_motif(m["code"]) for m in dossier.motifs if not m["principal"]]
    return lignes or ["Non renseigné"]


def _motif_transport_atcd(dossier) -> Brut:
    """Antécédents, circonstances, transport puis motif — un élément par
    ligne, comme demandé par le service (remarque du 6 septembre) : une
    phrase à tirets se relit mal au pied du lit, une liste se relit d'un
    coup d'œil."""
    sejour = dossier.sejour

    def bloc(titre: str, lignes: list[str]) -> str:
        corps = "".join(f"<div>{html.escape(l)}</div>" for l in lignes)
        return f'<div style="margin-bottom:2px"><b>{html.escape(titre)} :</b>{corps}</div>'

    def ligne(titre: str, valeur: str) -> str:
        return f'<div style="margin-bottom:2px"><b>{html.escape(titre)} :</b> {html.escape(valeur)}</div>'

    corps = bloc("Antécédents", _lignes_atcd(dossier))
    circonstances = _circonstances_texte(dossier)
    if circonstances:
        corps += ligne("Circonstances", circonstances)
    corps += ligne("Transport", _transport_texte(dossier))
    corps += bloc("Motif", _lignes_motif(dossier))
    ttt = sejour.get("traitement_habituel")
    if ttt:
        corps += ligne("Ttt habituel", ttt)
    return Brut(f'<div style="font-size:9.5px;line-height:1.35;overflow:hidden">{corps}</div>')


def _abords(dossier) -> list[dict]:
    """Les dispositifs en place, cochés, avec leur compteur de jours.

    Le compteur est calculé, jamais recopié : c'est la seule ligne de la
    feuille qu'un interne ne peut pas se tromper en reportant.
    """
    etats = dossier.etats_dispositifs
    lignes = []
    for etat in etats:
        coche = "☑" if etat.en_place else "☐"
        style = ("font-weight:600;color:#16201f" if etat.en_place
                 else "color:#6d7c7b")
        lignes.append({"texte": f"{coche} {_texte_abrege_dispositif(etat)}", "style": style})
    if not lignes:
        lignes.append({"texte": "☐ Aucun dispositif enregistré",
                       "style": "color:#6d7c7b"})
    return lignes


def _examens_demain(dossier) -> list[dict]:
    """Les cases « à demander pour demain », cochées d'après la saisie."""
    demandes = {
        d["examen_code"]
        for d in dossier.pancarte_demain["bilans_demandes"]
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


def _microbiologie(dossier) -> list[dict]:
    lignes = []
    for ligne in dossier.microbiologie[:LIGNES_MICROBIO]:
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

def contexte(dossier) -> dict:
    """Les valeurs à poser dans la maquette, à partir du dossier rassemblé.

    `dossier` est un `services.feuille_dossier.DossierFeuille` : tout est déjà
    lu. Ce module ne rouvre pas la base — c'est la règle R3.
    """
    sejour = dossier.sejour
    date_jour = dossier.date_jour

    prescrit = _lignes_prescription(dossier)
    jours = _jours_biologie(date_jour)
    lignes_ref = referentiels.charger("feuille_lignes")

    ideal = calculs.poids_ideal_devine(
        taille_cm=sejour.get("taille_cm"), sexe=sejour.get("sexe")
    )
    allergies = dossier.allergies

    ctx = {
        # En-tête
        "date_fr": format_date_fr(date_jour),
        "lit": sejour.get("lit_admission") or "",
        "jour_hosp": f"J{jour_hospitalisation(sejour['date_admission'], date_jour)}",
        "dossier": sejour.get("matricule") or "",
        "groupe_sanguin": sejour.get("groupe_sanguin") or "",
        "nom_patient": sejour.get("nom_affichage") or "",
        "age": _age(sejour, date_jour),
        "poids_ideal": f"{_nombre(ideal.valeur)} kg" if ideal.disponible else "",
        # Le mot « ALLERGIE » est écrit en toutes lettres : c'est la ligne
        # qu'un relecteur pressé doit voir sans la chercher.
        "allergies": (" · ".join(a["libelle"] for a in allergies)
                      if allergies else "ALLERGIE : non renseignée"),
        "scores": dossier.scores,
        "motifTransportAtcd": _motif_transport_atcd(dossier),
        "abords": _abords(dossier),
        "hours": [str(h) for h in ORDRE_HEURES],
        # Prescription
        **prescrit["blocs"],
        "bilanPrescRows": _bilans_a_faire(dossier),
        # Verso — surveillance laissée manuscrite
        "survRowsA": _lignes_manuscrites(lignes_ref["surveillance_a"]),
        "survRowsB": _lignes_manuscrites(lignes_ref["surveillance_b"]),
        "survRowsC": _lignes_manuscrites(lignes_ref["surveillance_c"]),
        "bilanRows": _lignes_manuscrites(lignes_ref["sorties_drains"]),
        # Verso — biologie reportée
        "days": [format_date_fr(j)[:5] for j in jours],
        "slots": [str(i + 1) for i in range(NB_CRENEAUX_PAR_JOUR)],
        "bioHemato": _valeurs_biologie(dossier, jours, list(lignes_ref["hemato"]), "bilan"),
        "bioIono": _valeurs_biologie(dossier, jours, list(lignes_ref["iono"]), "bilan"),
        "bioRenal": _valeurs_biologie(dossier, jours, list(lignes_ref["renal"]), "bilan"),
        "bioHepat": _valeurs_biologie(dossier, jours, list(lignes_ref["hepat"]), "bilan"),
        "bioAutres": _valeurs_biologie(dossier, jours, list(lignes_ref["autres"]), "bilan"),
        "gdsGaz": _valeurs_biologie(dossier, jours, list(lignes_ref["gaz"]), "gaz"),
        "pfRow": _rapport_pf(dossier, jours),
        "gdsVent": _valeurs_biologie(dossier, jours, list(lignes_ref["ventilation"]), "gaz"),
        "infRows": _microbiologie(dossier),
        "examensDemain": _examens_demain(dossier),
        "pied": _pied(prescrit["debordements"]),
        "styleDynamique": _style_remplissage(prescrit["taux_remplissage"]),
    }
    return ctx


_SLUGS_BLOCS = {
    "entRows": "ent", "pseRows": "pse", "ivRows": "iv", "scRows": "sc",
    "poRows": "po", "aeroRows": "aero", "kineRows": "kine", "soinsRows": "soins",
}
# (taux de remplissage maximal, taille de police) — la première ligne qui
# s'applique gagne. Un bloc largement vide n'a aucune raison de garder la
# petite taille prévue pour un bloc plein : la place est là, autant s'en servir.
_PALIERS_REMPLISSAGE = ((0.34, 13.5), (0.6, 11.5))
_TAILLE_DEFAUT = 9.5


def _style_remplissage(taux_remplissage: dict[str, float]) -> Brut:
    """Agrandit le texte des blocs dont la moitié des lignes ou plus restent
    vides — lisible depuis le pied du lit, sans rien déborder de la page."""
    regles = []
    for nom_liste, taux in taux_remplissage.items():
        slug = _SLUGS_BLOCS.get(nom_liste)
        if not slug:
            continue
        taille = next((v for seuil, v in _PALIERS_REMPLISSAGE if taux <= seuil), _TAILLE_DEFAUT)
        if taille != _TAILLE_DEFAUT:
            regles.append(f".txt-produit-{slug},.txt-dose-{slug}{{font-size:{taille}px}}")
    return Brut("".join(regles))


def _lignes_manuscrites(codes) -> list[dict]:
    """Des lignes que le logiciel étiquette mais ne remplit pas : les
    constantes horaires sont relevées au lit du malade, sur le papier."""
    return [{"libelle": libelle, "valeurs": Brut("")} for _code, libelle in codes]


def _age(sejour: dict, date_jour: str) -> str:
    from ..domaine.dates import age_ans

    age = age_ans(sejour.get("date_naissance"), date_jour)
    return f"{age} ans" if age is not None else ""


def _pied(debordements: list[str]) -> str:
    if debordements:
        return "⚠ " + " · ".join(debordements)
    return ""


def generer(dossier) -> str:
    """La feuille complète, prête à imprimer.

    Prend un `services.feuille_dossier.DossierFeuille`, jamais une base : ce
    module ne lit rien et ne décide rien de médical (règle R3). C'est
    l'appelant qui rassemble ; ici on ne fait que remplir la maquette.
    """
    gabarit = MODELE.read_text(encoding="utf-8")
    corps = rendre(gabarit, contexte(dossier))
    return _document(corps, dossier.date_jour)


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
