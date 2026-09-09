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
from ..domaine import avis as dom_avis
from ..domaine import calculs, prescription as dom
from ..domaine.dates import age_ans, format_date_fr, jour_hospitalisation, parse_date
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
# La largeur du récapitulatif de biologie, en colonnes. Elle ne bouge pas : la
# maquette est imprimée, et une page ne s'élargit pas.
NB_COLONNES_BIOLOGIE = NB_JOURS_BIOLOGIE * NB_CRENEAUX_PAR_JOUR
# Ce que le jour en cours garde, quoi qu'il arrive : la garde y écrit ses
# bilans à la main pendant la nuit, et lui reprendre ses créneaux reviendrait à
# lui demander d'écrire dans la marge.
COLONNES_JOUR_EN_COURS = NB_CRENEAUX_PAR_JOUR
# Jusqu'où remonter pour remplir les colonnes restantes. Un séjour de trois
# mois ne justifie pas de parcourir trois mois de dates à chaque impression.
JOURS_REMONTEE_MAXIMALE = 60

# La journée du service commence à 8 h, pas à minuit (config.HEURE_DEBUT_
# JOURNEE) : la relève du matin ouvre la feuille, et la colonne « 0 » en tête
# n'a jamais rien voulu dire pour personne.
ORDRE_HEURES = dom.heures_de_la_journee()


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


def _grille_vitesses(par_heure: dict[int, float]) -> Brut:
    """Vingt-quatre cases, la vitesse écrite aux heures où elle est réglée.

    Un rond dit « donner à cette heure-ci » ; un nombre dit « la pompe est à
    tant ». La vitesse d'ouverture s'écrit à 8 h, et chaque changement de la
    journée à son heure : « 25 » à 8 h, « 15 » à 16 h se relit d'un coup d'œil,
    là où la colonne dose ne pouvait montrer qu'un seul chiffre.
    """
    cases = []
    for heure in ORDRE_HEURES:
        vitesse = par_heure.get(heure % 24)
        contenu = (
            '<span style="font-size:9px;font-weight:700;line-height:1;'
            f'color:#14595c">{html.escape(_nombre(vitesse))}</span>'
            if vitesse is not None else ""
        )
        cases.append(
            '<div style="display:flex;align-items:center;justify-content:center">'
            f"{contenu}</div>"
        )
    return Brut(
        '<div style="position:absolute;inset:0;display:grid;'
        'grid-template-columns:repeat(24,1fr)">' + "".join(cases) + "</div>"
    )


def _cellules_valeurs(
    valeurs: list[str], colonnes: int, bornes: set[int] | None = None
) -> Brut:
    """Une valeur par créneau, chaque case portant son propre filet.

    Les traits étaient dessinés par un dégradé de fond régulier, ce qui
    supposait des colonnes toutes de la même largeur. Depuis que chaque jour
    prend autant de colonnes qu'il a de bilans, les séparateurs de jour ne
    tombent plus à intervalle fixe : ce sont les cases elles-mêmes qui les
    portent, à `bornes` — un trait fin entre deux créneaux d'un même jour, un
    trait épais quand le jour change.

    Une valeur longue — « 184 (32) » pour une créatinine et sa clairance —
    passe en plus petit plutôt que d'être coupée : une clairance tronquée se
    lit comme un autre nombre.
    """
    bornes = bornes or set()
    cases = []
    for i in range(colonnes):
        texte = html.escape(valeurs[i]) if i < len(valeurs) and valeurs[i] else ""
        # Une valeur longue passe en plus petit plutôt que d'être coupée :
        # « 184 (41) » pour une créatinine et sa clairance, « 2,05/0,62/0,71 »
        # pour trois ions lus ensemble. Un chiffre tronqué se lit comme un
        # autre chiffre, ce qui est pire que de le lire en petit.
        taille = 6 if len(texte) > 10 else 7 if len(texte) > 6 else 8
        if i == 0:
            filet = ""
        elif i in bornes:
            filet = "border-left:1.5px solid #16201f;"
        else:
            filet = "border-left:1px solid #c3cfce;"
        cases.append(
            f'<div style="{filet}display:flex;align-items:center;'
            f'justify-content:center;font-size:{taille}px;line-height:1;'
            'overflow:hidden">'
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

def _lignes_dispositifs_pse(dossier) -> list[dict]:
    """Les dispositifs qui coulent, reportés dans le bloc P.S.E.

    Ils sont déjà cochés dans les abords, avec leur compteur de jours : c'est
    la lecture clinique. Mais la vitesse qui les fait couler est aussi une
    consigne infirmière, au même titre qu'une noradrénaline prescrite en
    ligne — elle doit donc être là où les seringues électriques se règlent,
    pas seulement dans la case des dispositifs.

    La sédation était le seul cas, et cette fonction ne connaissait qu'elle.
    Une péridurale thoracique coule exactement pareil et l'anesthésique local
    n'apparaissait nulle part sur la pancarte (demande du service,
    8 septembre) : c'est le fichier des types qui déclare maintenant lesquels
    y vont, avec `pse`.
    """
    lignes = []
    for etat in dossier.etats_dispositifs:
        if not etat.en_place:
            continue
        config = listes.TYPES_DISPOSITIF.get(etat.type, {})
        if not config.get("pse"):
            continue
        details = etat.details or {}
        # Le site n'est pas répété ici : il est déjà sur le bandeau des abords,
        # en haut de la même page, pour le même dispositif. L'écrire deux fois
        # faisait passer la ligne sur deux hauteurs et cassait la grille des
        # seringues — la ligne P.S.E. répond à « qu'est-ce qui coule, à quel
        # débit », le bandeau répond à « où ».
        produit = details.get("molecules") or config.get("libelle", etat.type)
        suffixe = config.get("suffixe_pse") or config.get("libelle", "").lower()
        # Ce qui coule en continu s'écrit heure par heure, comme une seringue
        # prescrite : une sédation qu'on allège et une péridurale qu'on
        # descend se relisent de la même façon.
        par_heure = dossier.vitesses.get(etat.id) or {}
        lignes.append({
            "numero": str(len(lignes) + 1),
            "produit": Brut(
                f'{html.escape(produit)} <span style="font-size:7.5px;color:#5e6d6c">'
                f"— {html.escape(suffixe)}</span>"
            ),
            "dose": f"{_nombre(details['vitesse'])} cc/h" if details.get("vitesse") else "",
            "grille": _grille_vitesses(par_heure) if par_heure else Brut(""),
        })
    return lignes


def _lignes_prescription(dossier) -> dict:
    """Une ligne par prescription active, un rond par prise."""
    par_voie = dossier.lignes_par_voie
    blocs: dict[str, list] = {}
    debordements: list[str] = []
    taux_remplissage: dict[str, float] = {}

    # La sédation posée comme dispositif occupe une ligne du bloc P.S.E. avant
    # les lignes prescrites — elle vient du dossier, pas d'une prescription.
    lignes_synthetiques = {"PSE": _lignes_dispositifs_pse(dossier)}

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
            if voie == "ENTREES":
                # La colonne Voie a disparu (les blocs sont déjà organisés par
                # voie) ; ce qu'elle portait d'utile pour les entrées —
                # perfusion ou nutrition — reste lisible, accolé au produit.
                # L'unité qui suit le libellé du sous-type est déjà dans la
                # colonne Dose : la répéter mangeait la place des additifs.
                if ligne.get("sous_type"):
                    sous_type = listes.libelle(
                        listes.SOUS_TYPES_ENTREES, ligne["sous_type"]
                    ).split(" (")[0]
                    produit = f"{produit} ({sous_type.lower()})"
                # Ce qu'on a mis dans le flacon se lit sur la même ligne que le
                # flacon. Écrit nulle part sur la feuille imprimée jusqu'ici :
                # l'infirmière préparait d'après la pancarte, et la pancarte ne
                # disait pas les additifs (demande du service, 8 septembre).
                if ligne.get("additifs"):
                    produit = f"{produit} {ligne['additifs']}"
            if arretee:
                produit = Brut(
                    '<span class="arretee" style="text-decoration:line-through;'
                    f'color:#6d7c7b">{html.escape(produit)}</span>'
                    '<span style="font-size:8px;color:#a33b2a;margin-left:5px">'
                    "ARRÊTÉ</span>"
                )
            # Ce qui coule porte sa vitesse dans les cases, ce qui se donne à
            # heure fixe porte un rond : deux consignes différentes, deux
            # écritures différentes.
            par_heure = {} if arretee else (dossier.vitesses.get(ligne["id"]) or {})
            rendues.append({
                "numero": str(len(rendues) + 1),
                "produit": produit,
                "dose": _dose(ligne),
                "grille": _grille_vitesses(par_heure) if par_heure
                          else _grille_heures(set(heures)),
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
        dose = _nombre(ligne["dose"]) + (f" {ligne['unite']}" if ligne.get("unite") else "")
        # « 1 g × 3 » plutôt que « 1 g » : la dose d'une prise ne dit pas la
        # dose de la journée, et c'est celle-là qu'on relit pour juger d'une
        # posologie (demande du service, 8 septembre). Une prise unique ne
        # gagne rien à porter un « × 1 » ; un jour sur deux non plus.
        prises = dom.nb_prises_par_jour(ligne.get("rythme"))
        if prises >= 2 and float(prises).is_integer():
            dose += f" × {int(prises)}"
        morceaux.append(dose)
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


def _repartition_biologie(dossier, date_jour: str, source: str) -> list[dict]:
    """Comment les douze colonnes du récapitulatif se partagent les jours.

    Douze colonnes, toujours : la page est imprimée, elle ne s'élargit pas.
    Quatre restent au jour en cours, vides — la garde y écrit ses bilans de la
    nuit. Les huit autres vont aux jours passés, **chacun prenant autant de
    colonnes qu'il a réellement de prélèvements** (demande du service,
    8 septembre).

    Avant, chaque jour prenait quatre colonnes qu'il ait eu un bilan ou
    quatre : deux jours suffisaient à remplir la page, et un patient prélevé
    une fois par jour perdait six colonnes sur huit en cases vides. En
    remontant plus loin quand les jours récents sont maigres, la feuille montre
    une semaine de cinétique au lieu de deux jours — et une cinétique de
    créatinine sur une semaine, c'est ce qui fait voir une insuffisance rénale
    qui s'installe.

    Un jour sans aucun prélèvement ne prend aucune colonne : il n'aurait rien
    à y écrire, et sa place sert à montrer un jour plus ancien qui, lui, a des
    valeurs. Si le séjour est trop court pour remplir les huit, les colonnes
    qui restent sont laissées libres devant les autres, en papier réglé.
    """
    aujourdhui = parse_date(date_jour)
    admission = parse_date((dossier.sejour or {}).get("date_admission")) or aujourdhui
    restant = NB_COLONNES_BIOLOGIE - COLONNES_JOUR_EN_COURS

    passes: list[dict] = []
    for recul in range(1, JOURS_REMONTEE_MAXIMALE + 1):
        if restant <= 0:
            break
        jour = aujourdhui - timedelta(days=recul)
        if jour < admission:
            break
        nombre = _nb_prelevements_du_jour(dossier, jour.isoformat(), source)
        if nombre == 0:
            continue
        colonnes = min(nombre, restant)
        passes.append({"jour": jour.isoformat(), "colonnes": colonnes,
                       "en_cours": False})
        restant -= colonnes

    repartition = list(reversed(passes))          # du plus ancien au plus récent
    # Ce qui reste — séjour trop court, ou pas encore de bilan — va au jour en
    # cours, qui est le seul à avoir de vraies raisons d'avoir des cases
    # libres : la garde y écrit ses bilans de la nuit. Il n'y a donc aucune
    # colonne anonyme sur la feuille. Un bloc sans date entre le 07 et le 08 se
    # lisait comme un jour manquant, ce qui est exactement ce qu'il ne fallait
    # pas laisser croire.
    repartition.append({"jour": date_jour,
                        "colonnes": COLONNES_JOUR_EN_COURS + max(restant, 0),
                        "en_cours": True})
    return repartition


def _bornes_de_jour(repartition: list[dict]) -> set[int]:
    """Les colonnes qui ouvrent un jour : c'est là que le trait épais tombe."""
    bornes, position = set(), 0
    for groupe in repartition:
        bornes.add(position)
        position += groupe["colonnes"]
    return bornes


def _nb_prelevements_du_jour(dossier, jour: str, source: str) -> int:
    """Combien de fois ce tableau-là a quelque chose à écrire, ce jour-là.

    Compté **par source**, et c'est tout le point. En comptant les bilans et
    les gaz du sang ensemble, un jour à deux bilans et deux gaz recevait
    quatre colonnes dans le récapitulatif de chimie, qui n'en remplissait que
    deux : la troisième restait vide au milieu d'un jour, pendant qu'un autre
    jour, faute de place, n'était pas montré du tout.
    """
    lignes = dossier.resultats if source == "bilan" else dossier.gaz_du_sang
    return len({
        l["date_heure"] for l in lignes
        if (l["date_heure"] or "").startswith(jour)
    })


def _entetes_jours(repartition: list[dict]) -> list[dict]:
    """Les colonnes de jours, larges de ce que leur jour a de prélèvements.

    Un jour n'a plus ses quatre créneaux numérotés quoi qu'il arrive : il en a
    autant qu'il a de bilans, et ils ne sont numérotés que s'il y en a
    plusieurs — un « 1 » solitaire au-dessus d'une seule valeur n'apprend rien.
    Le jour en cours garde ses quatre créneaux numérotés : il est manuscrit
    d'un bout à l'autre, et les quatre disent justement combien de bilans y
    tiennent.
    """
    entetes = []
    for groupe in repartition:
        colonnes = groupe["colonnes"]
        # Le groupe sans date est du papier réglé : le numéroter promettrait
        # des créneaux d'un jour qui n'existe pas.
        numerote = groupe["en_cours"] or (colonnes > 1 and groupe["jour"])
        entetes.append({
            "libelle": format_date_fr(groupe["jour"])[:5] if groupe["jour"] else "",
            "poids": str(colonnes),
            "slots": [str(i + 1) for i in range(colonnes)] if numerote
                     else [""] * colonnes,
        })
    return entetes


def _valeurs_biologie(
    dossier, repartition: list[dict], lignes_spec: list[tuple], source: str,
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
    bornes = _bornes_de_jour(repartition)
    lignes = []
    for codes, libelle in lignes_spec:
        if isinstance(codes, str):
            codes = (codes,)
        cellules_par_code = []
        for code in codes:
            cellules: list[str] = []
            for groupe in repartition:
                if groupe["en_cours"] or groupe["jour"] is None:
                    cellules.extend([""] * groupe["colonnes"])
                else:
                    cellules.extend(_creneaux_du_jour(
                        dossier, groupe["jour"], code, source, groupe["colonnes"]
                    ))
            cellules_par_code.append(cellules)
        cellules_combinees = [
            "/".join(v for v in valeurs_du_creneau if v)
            for valeurs_du_creneau in zip(*cellules_par_code)
        ]
        lignes.append({
            "libelle": libelle,
            "valeurs": _cellules_valeurs(
                cellules_combinees, NB_COLONNES_BIOLOGIE, bornes
            ),
        })
    return lignes


#: Ce qui dépend du mode ventilatoire, par opposition au gaz du sang lui-même :
#: une seringue de sang artériel se lit pareil qu'on soit ventilé ou non.
_PARAMETRES_VENTILATOIRES = ("fio2", "pep", "fr", "vt", "ai", "debit_o2")


def _creneaux_du_jour(
    dossier, jour: str, code: str, source: str, colonnes: int
) -> list[str]:
    """Les valeurs d'un paramètre un jour donné, dans l'ordre des heures."""
    if source == "bilan":
        lignes = [
            l for l in dossier.resultats
            if l["analyte"] == code and (l["date_heure"] or "").startswith(jour)
        ]
        if code == "creat":
            # La clairance suit la créatinine entre parenthèses (demande du
            # service, 8 septembre) : c'est elle qui dit si le rein décroche,
            # et une créatinine à 120 ne veut pas dire la même chose chez un
            # homme de 40 ans de 90 kg et chez une femme de 80 ans de 45.
            # Calculée, jamais saisie — et rien affiché quand il manque le
            # poids, l'âge ou le sexe.
            valeurs = [_creatinine_avec_clairance(dossier, l) for l in lignes]
        else:
            valeurs = [_nombre(l["valeur_num"]) for l in lignes]
    else:
        lignes = [
            g for g in dossier.gaz_du_sang
            if (g["date_heure"] or "").startswith(jour)
        ]
        if code == "mode_ventilatoire":
            # Le mode est enregistré sous son code : la feuille imprime le
            # sigle que le service emploie, pas « vs_ai ».
            valeurs = [listes.libelle_mode_court(g.get(code)) for g in lignes]
        else:
            # Un paramètre qui n'a pas de sens pour ce mode-là n'est pas
            # imprimé même s'il traîne en base : une PEP sous air ambiant
            # viendrait forcément d'une saisie antérieure au filtrage.
            valeurs = [
                _nombre(g.get(code))
                if code not in _PARAMETRES_VENTILATOIRES
                or code in listes.parametres_du_mode(g.get("mode_ventilatoire"))
                else ""
                for g in lignes
            ]
    valeurs = [v for v in valeurs if v]
    return (valeurs + [""] * colonnes)[:colonnes]


def _creatinine_avec_clairance(dossier, ligne: dict) -> str:
    """« 184 (32) » — la créatinine, puis sa clairance de Cockcroft-Gault.

    La clairance reste une grandeur physiologique : le logiciel ne déduit
    jamais de posologie de ce chiffre (SPEC §3.1). Il l'écrit parce que le
    recalculer de tête à chaque bilan est exactement l'arithmétique qu'on finit
    par ne plus faire.
    """
    texte = _nombre(ligne["valeur_num"])
    if not texte:
        return ""
    sejour = dossier.sejour or {}
    clairance = calculs.clairance_cockcroft_gault(
        creatinine_umol_l=ligne["valeur_num"],
        poids_kg=sejour.get("poids_kg"),
        age_ans=age_ans(sejour.get("date_naissance"), dossier.date_jour),
        sexe=sejour.get("sexe"),
    )
    if not clairance.disponible:
        return texte
    return f"{texte} ({_nombre(round(clairance.valeur))})"


def _rapport_pf(dossier, repartition: list[dict]) -> Brut:
    """Le rapport PaO₂/FiO₂, recalculé pour chaque gaz du sang.

    C'est le seul chiffre de la feuille qui n'est ni saisi ni recopié : il se
    déduit de deux valeurs déjà là, et le recalculer à la main à chaque gaz du
    sang est exactement le genre d'arithmétique qu'on finit par ne plus faire.

    Il n'est écrit que là où les deux ingrédients existent : une case vide dit
    « pas de gaz du sang », jamais « rapport normal ».
    """
    cellules: list[str] = []
    for groupe in repartition:
        colonnes = groupe["colonnes"]
        if groupe["en_cours"] or groupe["jour"] is None:
            cellules.extend([""] * colonnes)     # le jour en cours reste à la garde
            continue
        valeurs = []
        for gaz in dossier.gaz_du_sang:
            if not (gaz["date_heure"] or "").startswith(groupe["jour"]):
                continue
            rapport = calculs.rapport_pao2_fio2(gaz.get("pao2"), gaz.get("fio2"))
            if rapport.disponible:
                valeurs.append(_nombre(rapport.valeur))
        cellules.extend((valeurs + [""] * colonnes)[:colonnes])
    return _cellules_valeurs(
        cellules, NB_COLONNES_BIOLOGIE, _bornes_de_jour(repartition)
    )


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
    # Sous le transport, parce que c'est le même moment : ce que valait le
    # patient en arrivant. À J3 sous midazolam, personne ne sait plus s'il est
    # arrivé à 15 ou à 6, et c'est un facteur pronostique majeur du
    # traumatisme crânien (demande du service, 8 septembre).
    if sejour.get("glasgow_initial") is not None:
        corps += ligne("Glasgow initial", str(int(sejour["glasgow_initial"])))
    corps += bloc("Motif", _lignes_motif(dossier))
    ttt = sejour.get("traitement_habituel")
    if ttt:
        corps += ligne("Ttt habituel", ttt)
    return Brut(f'<div style="font-size:9.5px;line-height:1.35;overflow:hidden">{corps}</div>')


#: Combien d'avis la feuille imprime au plus. Le bloc partage sa hauteur avec
#: la conduite à tenir, qui reste manuscrite : au-delà, ce sont les plus
#: récents qui comptent pour la visite du jour.
LIGNES_AVIS = 6


def _avis_specialises(dossier) -> Brut:
    """« Avis CCVT (09/09) : Rsdt X : Pas d'indication chirurgicale ».

    Un avis n'annule jamais le précédent, même de la même spécialité : c'est la
    suite des avis qui raconte l'évolution d'une décision chirurgicale, et le
    second ne se comprend souvent qu'à la lumière du premier. Ils s'impriment
    donc tous, dans l'ordre où ils ont été donnés.

    Le bloc garde des lignes vides sous les avis : la conduite à tenir s'écrit
    à la main au même endroit, à la visite.
    """
    lignes = [dom_avis.ligne_avis(a) for a in dossier.avis][-LIGNES_AVIS:]
    if not lignes:
        return Brut("")
    corps = "".join(
        '<div style="font-size:8.5px;line-height:1.5;padding:0 4px;'
        'border-bottom:1px solid #d3dcdb;white-space:nowrap;overflow:hidden">'
        f"{html.escape(l)}</div>"
        for l in lignes
    )
    return Brut(corps)


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
    """« Bilans infectieux » : une ligne par type de prélèvement, avec sa
    cinétique — « 07/09 : 210 → 08/09 : 185 → 10/09 : 56 ».

    Le bloc listait les six derniers résultats tous types confondus, du plus
    récent au plus ancien. Deux hémocultures et une CRP suffisaient à faire
    disparaître l'ECBU de la veille, et la cinétique d'une CRP ne se lisait
    nulle part — alors que c'est elle, plus que sa valeur du jour, qui dit si
    l'antibiothérapie marche (demande du service, 8 septembre).

    Chaque ligne existe même vide : une ligne « PL » sans rien en face se lit
    « pas de ponction lombaire », ce qui est une information ; une ligne
    absente ne se lit pas du tout.
    """
    lignes = []
    for code, libelle, source in referentiels.charger("feuille_bilan_infectieux"):
        if source == "analyte":
            points = _cinetique_analyte(dossier, code)
        else:
            points = _cinetique_prelevement(dossier, code)
        lignes.append({
            "prelevement": libelle,
            "resultat": " → ".join(points[-LIMITE_CINETIQUE:]),
        })
    return lignes


#: Combien de résultats une ligne du bilan infectieux montre au plus. Au-delà,
#: ce sont les plus récents qui restent : une CRP d'il y a douze jours
#: n'éclaire plus l'antibiothérapie d'aujourd'hui, et la ligne déborderait.
LIMITE_CINETIQUE = 6


def _cinetique_analyte(dossier, code: str) -> list[str]:
    lignes = sorted(
        (l for l in dossier.resultats
         if l["analyte"] == code and l.get("valeur_num") is not None),
        key=lambda l: l["date_heure"] or "",
    )
    return [
        f"{format_date_fr(l['date_heure'])[:5]} : {_nombre(l['valeur_num'])}"
        for l in lignes
    ]


def _cinetique_prelevement(dossier, code: str) -> list[str]:
    lignes = sorted(
        (m for m in dossier.microbiologie if m["type_prelevement"] == code),
        key=lambda m: m["date_prelevement"] or "",
    )
    points = []
    for ligne in lignes:
        resultat = listes.libelle(listes.RESULTATS_MICROBIO, ligne["resultat"])
        if ligne["resultat"] == "positif" and ligne.get("germe"):
            resultat = ligne["germe"]
        points.append(f"{format_date_fr(ligne['date_prelevement'])[:5]} : {resultat}")
    return points


def _avec_date(libelle: str, date_heure: str) -> str:
    return f"{libelle} ({format_date_fr(date_heure)[:5]})"


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
    # Deux tableaux, deux répartitions : le récapitulatif de chimie compte ses
    # bilans, le tableau des gaz du sang compte ses gaz. Une répartition
    # commune donnait à l'un des colonnes que l'autre remplissait.
    repartition = _repartition_biologie(dossier, date_jour, "bilan")
    repartition_gaz = _repartition_biologie(dossier, date_jour, "gaz")
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
        "avisRows": _avis_specialises(dossier),
        "abords": _abords(dossier),
        "hours": [str(h) for h in ORDRE_HEURES],
        # Prescription
        **prescrit["blocs"],
        "bilanPrescRows": _bilans_a_faire(dossier),
        # Verso — surveillance laissée manuscrite
        "survRowsA": _lignes_manuscrites(lignes_ref["surveillance_a"]),
        "survRowsB": _lignes_manuscrites(lignes_ref["surveillance_b"]),
        "survRowsC": _lignes_manuscrites(lignes_ref["surveillance_c"]),
        "bilanRows": _lignes_sorties(dossier, lignes_ref["sorties_drains"]),
        # Verso — biologie reportée
        "days": _entetes_jours(repartition),
        "daysGaz": _entetes_jours(repartition_gaz),
        "bioHemato": _valeurs_biologie(dossier, repartition, list(lignes_ref["hemato"]), "bilan"),
        "bioIono": _valeurs_biologie(dossier, repartition, list(lignes_ref["iono"]), "bilan"),
        "bioRenal": _valeurs_biologie(dossier, repartition, list(lignes_ref["renal"]), "bilan"),
        "bioHepat": _valeurs_biologie(dossier, repartition, list(lignes_ref["hepat"]), "bilan"),
        "bioAutres": _valeurs_biologie(dossier, repartition, list(lignes_ref["autres"]), "bilan"),
        "gdsGaz": _valeurs_biologie(dossier, repartition_gaz, list(lignes_ref["gaz"]), "gaz"),
        "pfRow": _rapport_pf(dossier, repartition_gaz),
        "gdsVent": _valeurs_biologie(dossier, repartition_gaz, list(lignes_ref["ventilation"]), "gaz"),
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


def _lignes_sorties(dossier, codes) -> list[dict]:
    """Les lignes de sorties, dont les emplacements de drains sont nommés.

    Un drain porte son nom sur la feuille : « Drain thoracique (droit) », pas
    « Drain 2 ». Sur du papier rempli à la main toutes les heures, l'infirmière
    n'a rien pour savoir lequel des trois emplacements est le thoracique et
    lequel est le redon de l'abdomen — et deux volumes intervertis, c'est une
    reprise chirurgicale décidée sur un chiffre qui n'est pas le bon.

    Les emplacements que les drains en place n'occupent pas gardent leur
    libellé générique : un drain posé après l'impression doit pouvoir
    s'écrire quelque part.

    Les valeurs, elles, restent manuscrites comme le reste de la surveillance
    horaire — le volume relevé dans l'évolution est celui des 24 h, pas celui
    de chaque heure, et l'imprimer ici le ferait lire pour autre chose.
    """
    drains = [
        etat for etat in dossier.etats_dispositifs
        if etat.en_place and listes.TYPES_DISPOSITIF.get(etat.type, {}).get("draine")
    ]
    lignes = []
    restants = list(drains)
    for code, libelle in codes:
        if code.startswith("drain_") and restants:
            etat = restants.pop(0)
            nom = listes.libelle_dispositif(etat.type)
            if etat.site:
                nom += f" ({etat.site.lower()})"
            libelle = f"{nom} (ml)"
        lignes.append({"libelle": libelle, "valeurs": Brut("")})
    return lignes


def _lignes_manuscrites(codes) -> list[dict]:
    """Des lignes que le logiciel étiquette mais ne remplit pas : les
    constantes horaires sont relevées au lit du malade, sur le papier."""
    return [{"libelle": libelle, "valeurs": Brut("")} for _code, libelle in codes]


def _age(sejour: dict, date_jour: str) -> str:
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
