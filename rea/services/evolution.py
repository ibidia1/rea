"""Écran 6 — Évolution quotidienne (SPEC §8).

Seuls les quatre plans et la conduite sont saisis à la main ; le reste est
généré : dispositifs en place avec leur compteur de jours, explorations du
jour (SPEC §6), bilan du jour (SPEC §7) et prescrit actif.
"""

from __future__ import annotations

from .. import config, listes
from ..db import Base
from ..domaine import calculs
from ..domaine import dispositifs as dom_dispositifs
from ..domaine import prescription as dom
from ..domaine.dates import format_date_fr, jour_hospitalisation
from ..domaine import avis as dom_avis
from . import avis as avis_service
from . import bilans as bilans_service
from . import constantes as constantes_service
from . import dispositifs as dispositifs_service
from . import explorations as explorations_service
from . import prescriptions as prescriptions_service
from . import sejours as sejours_service
from . import vitesses as vitesses_service

PLANS = ("plan_neurologique", "plan_respiratoire", "plan_hemodynamique", "plan_infectieux")
LIBELLES_PLANS = {
    "plan_neurologique": "Sur le plan Neurologique",
    "plan_respiratoire": "Sur le plan respiratoire",
    "plan_hemodynamique": "Sur le plan hémodynamique",
    "plan_infectieux": "Sur le plan Infectieux",
}


def journee(base: Base, sejour_id: str, date_jour: str) -> dict | None:
    """L'évolution d'un jour, ou rien — sans jamais l'écrire.

    Lire n'est pas remplir : un écran de consultation qui appelle
    `obtenir_ou_creer` sème une ligne vide pour chaque jour que quelqu'un a
    seulement regardé, et « cette journée existe » cesse de vouloir dire
    « quelqu'un l'a remplie ».
    """
    return base.une_ligne(
        "SELECT * FROM evolution_jour WHERE sejour_id = ? AND date_jour = ? AND supprime = 0",
        (sejour_id, date_jour),
    )


def obtenir_ou_creer(base: Base, sejour_id: str, date_jour: str, *, utilisateur_id: str | None = None) -> dict:
    existante = journee(base, sejour_id, date_jour)
    if existante:
        return existante
    id_ = base.inserer(
        "evolution_jour", {"sejour_id": sejour_id, "date_jour": date_jour}, utilisateur_id=utilisateur_id
    )
    return base.une_ligne("SELECT * FROM evolution_jour WHERE id = ?", (id_,))


def enregistrer(
    base: Base, sejour_id: str, date_jour: str, valeurs: dict, *, utilisateur_id: str | None = None
) -> None:
    """`valeurs` : sous-ensemble de PLANS + 'conduite'."""
    entree = obtenir_ou_creer(base, sejour_id, date_jour, utilisateur_id=utilisateur_id)
    champs_valides = {k: v for k, v in valeurs.items() if k in PLANS + ("conduite",)}
    base.mettre_a_jour("evolution_jour", entree["id"], champs_valides, utilisateur_id=utilisateur_id)


def enregistrer_journee(
    base: Base,
    sejour_id: str,
    date_jour: str,
    *,
    elements: dict,
    textes: dict,
    version_attendue: int | None = None,
    utilisateur_id: str | None = None,
) -> None:
    """L'évolution d'un jour, mesures et textes ensemble, en une écriture.

    Les deux vont ensemble : enregistrer les mesures puis échouer sur les
    textes laisserait une observation à moitié écrite, et personne ne saurait
    laquelle des deux moitiés est la bonne.

    `version_attendue` est la version lue à l'ouverture de l'écran. Si elle a
    bougé, quelqu'un d'autre a enregistré cette évolution entre-temps :
    l'écriture est refusée (`ConflitDeVersion`) plutôt que d'écraser en
    silence. Deux internes sur le même patient le même jour, c'est le cas
    ordinaire d'un service, pas un cas limite.
    """
    with base.transaction():
        entree = obtenir_ou_creer(base, sejour_id, date_jour, utilisateur_id=utilisateur_id)
        base.verifier_version("evolution_jour", entree["id"], version_attendue)
        enregistrer_elements(
            base, sejour_id, date_jour, elements, utilisateur_id=utilisateur_id
        )
        champs_valides = {k: v for k, v in textes.items() if k in PLANS + ("conduite",)}
        base.mettre_a_jour(
            "evolution_jour", entree["id"], champs_valides, utilisateur_id=utilisateur_id
        )


def texte_genere(base: Base, sejour_id: str, date_jour: str) -> str:
    """Format cible SPEC §8.1, prêt à copier dans le DMI."""
    sejour = sejours_service.sejour_avec_patient(base, sejour_id)
    entree = base.une_ligne(
        "SELECT * FROM evolution_jour WHERE sejour_id = ? AND date_jour = ? AND supprime = 0",
        (sejour_id, date_jour),
    ) or {}
    jour_hosp = jour_hospitalisation(sejour["date_admission"], date_jour)

    lignes = [f"{format_date_fr(date_jour)}, J{jour_hosp} d'hospitalisation :"]

    # Les dispositifs qui ne relèvent d'aucun plan (SNG, cathéters, sondes)
    # restent en tête ; l'intubation, la sédation et l'épuration sont reprises
    # dans le plan qui les concerne, pour ne pas les écrire deux fois.
    ailleurs = ("intubation", "sedation", "tracheotomie", "eer")
    autres = [
        e.texte for e in dispositifs_service.etats(base, sejour_id, date_jour)
        if e.en_place and e.type not in ailleurs
    ]
    if autres:
        lignes.append(" · ".join(autres))

    elements = elements_du_jour(base, sejour_id, date_jour)
    for cle in PLANS:
        plan = cle.replace("plan_", "")
        lignes.append(f"{LIBELLES_PLANS[cle]} :")
        # 1. Ce que le logiciel sait déjà — « Sédaté J4 », « Intubé J5 »,
        #    les amines en cours, les antibiotiques, les escarres.
        automatique = _elements_automatiques(base, sejour_id, plan, date_jour)
        if automatique:
            lignes.append(automatique)
        # 2. Les éléments fixes saisis en un geste — FC, TA, diurèse, T°.
        mesures = _texte_elements(plan, elements)
        if mesures:
            lignes.append(mesures)
        # 3. Ce que le médecin écrit lui-même.
        if entree.get(cle):
            lignes.append(entree[cle])

    lignes.append("Explorations :")
    explorations_texte = explorations_service.texte_du_jour(base, sejour_id, date_jour)
    if explorations_texte:
        lignes.append(explorations_texte)

    lignes.append("Bilan du jour :")
    bilan_texte = bilans_service.texte_genere(base, sejour_id, date_jour)
    if bilan_texte:
        lignes.append(bilan_texte)

    lignes.append("Sous le traitement :")
    pancarte = prescriptions_service.pancarte_du_jour(base, sejour_id, date_jour)
    lignes_traitement = [
        # Sans les heures de prise : dans l'observation collée au dossier, le
        # « (8h-20h) » derriere chaque produit alourdit sans rien apprendre —
        # c'est la pancarte qui porte les heures (demande du service,
        # 12 septembre).
        dom.libelle_ligne(l, date_jour, avec_horaires=False)
        for l in pancarte["lignes"] if l["statut"] == "active"
    ]
    if lignes_traitement:
        lignes.extend(lignes_traitement)

    # Les avis rendus CE jour-la, juste avant la conduite : c'est l'avis du
    # jour qui pese sur la decision qu'on ecrit dessous (demande du service,
    # 12 septembre). Les avis anciens restent au dossier, pas dans le texte du
    # jour.
    avis_du_jour = [
        dom_avis.ligne_avis(a) for a in avis_service.du_sejour(base, sejour_id)
        if a.get("date_avis") == date_jour
    ]
    if avis_du_jour:
        lignes.append("Avis :")
        lignes.extend(avis_du_jour)

    lignes.append("Conduite :")
    if entree.get("conduite"):
        lignes.append(entree["conduite"])
    else:
        lignes.append("==>")

    texte = "\n".join(lignes)
    if not config.SYMBOLES_UNICODE:
        texte = texte.replace("HCO₃⁻", "HCO3-").replace("PaO₂", "PaO2").replace("PaCO₂", "PaCO2")
    return texte

# --------------------------------------------------------------------------
# Éléments fixes des quatre plans (FC, TA, diurèse, température, RASS…)
# --------------------------------------------------------------------------

def enregistrer_elements(
    base: Base,
    sejour_id: str,
    date_jour: str,
    elements: dict[str, float | str | None],
    *,
    utilisateur_id: str | None = None,
) -> None:
    """Un élément par clé. Une valeur vide efface l'élément du jour plutôt que
    d'enregistrer un zéro qui serait lu comme une mesure."""
    with base.transaction():
        for cle, valeur in elements.items():
            plan = _plan_de(cle)
            if plan is None:
                continue
            existant = base.une_ligne(
                "SELECT id FROM evolution_element WHERE sejour_id = ? AND date_jour = ? "
                "AND cle = ?",
                (sejour_id, date_jour, cle),
            )
            est_vide = valeur is None or valeur == "" or valeur == "non_renseigne"
            champs = {
                "valeur_num": float(valeur) if isinstance(valeur, (int, float)) else None,
                "valeur_texte": valeur if isinstance(valeur, str) else None,
                "supprime": int(est_vide),
            }
            if existant:
                base.mettre_a_jour(
                    "evolution_element", existant["id"], champs, utilisateur_id=utilisateur_id
                )
            elif not est_vide:
                base.inserer(
                    "evolution_element",
                    {"sejour_id": sejour_id, "date_jour": date_jour, "plan": plan,
                     "cle": cle, **champs},
                    utilisateur_id=utilisateur_id,
                )


# Le volume recueilli par un drain se relève un drain à la fois, et un patient
# n'a pas toujours les mêmes : la clé porte donc l'identifiant du dispositif et
# ne peut pas figurer dans la liste fixe des éléments de plan.
PREFIXE_VOLUME_DRAIN = "volume_drain_"


def _plan_de(cle: str) -> str | None:
    if cle.startswith(PREFIXE_VOLUME_DRAIN):
        return "hemodynamique"
    for plan, elements in listes.ELEMENTS_PLAN.items():
        if any(c == cle for c, *_reste in elements):
            return plan
    return None


def drains_du_jour(base: Base, sejour_id: str, date_jour: str) -> list[dict]:
    """Les drains en place ce jour-là, avec le volume déjà relevé.

    « Drainé » veut dire : dispositif dont `types_dispositif.json` déclare
    `draine`. La sonde urinaire n'en est pas — son volume, c'est la diurèse,
    comptée à part, et l'ajouter la compterait deux fois.

    « Ce jour-là » compte dans les deux sens : un drain posé aujourd'hui n'a
    rien recueilli avant-hier, et ne doit pas apparaître en rouvrant
    l'évolution d'avant-hier — sans quoi le bilan hydrique d'un jour passé
    changerait chaque fois qu'on pose un drain.
    """
    valeurs = elements_du_jour(base, sejour_id, date_jour)
    en_place = [
        etat for etat in dispositifs_service.etats(base, sejour_id, date_jour)
        if etat.en_place
        and listes.TYPES_DISPOSITIF.get(etat.type, {}).get("draine")
        and not (etat.date_pose and etat.date_pose > date_jour)
    ]
    # Deux redons dans le même abdomen se distinguent par un numéro, sinon
    # c'est un volume noté sur le mauvais drain (demande du service).
    noms = dom_dispositifs.libelles_distincts(en_place)
    drains = []
    for etat in en_place:
        cle = f"{PREFIXE_VOLUME_DRAIN}{etat.id}"
        # Le volume du jour vient de deux endroits, et l'un prime : ce que
        # l'infirmier a relevé heure par heure est une mesure ; ce que le
        # médecin reporte dans son observation est une reprise. Dès qu'une
        # heure a été relevée, c'est le relevé qui compte — sinon le chiffre
        # changerait selon l'écran qu'on regarde.
        #
        # « Dès qu'une heure a été relevée », et non « si le total est
        # complet » : sans aucun relevé, `total_du_jour` rend un total vide
        # qui se dit complet — il l'est, il ne manque rien à rien — et
        # écraserait la valeur du médecin par un blanc.
        releve = constantes_service.total_du_jour(
            base, sejour_id, date_jour, constantes_service.cle_drain(etat.id)
        )
        du_chevet = releve.volume_ml if releve.heures_comptees else None
        drains.append({
            "cle": cle,
            "libelle": noms.get(etat.id, etat.libelle_type),
            "valeur": du_chevet if du_chevet is not None else valeurs.get(cle),
            "releve_infirmier": du_chevet,
            "dispositif_id": etat.id,
            # Le type, parce que tous les drains ne se surveillent pas pareil :
            # seul un drain thoracique est clampé, en siphonnage ou en
            # aspiration. Poser la question a un redon lui ferait dire
            # n'importe quoi.
            "type": etat.type,
        })
    return drains


def bilan_hydrique(base: Base, sejour_id: str, date_jour: str) -> dom.BilanHydrique:
    """Le bilan des 24 h : entrées prescrites, sorties relevées, pertes
    insensibles calculées.

    Les entrées se lisent du prescrit, les sorties de l'évolution du jour :
    rien n'est ressaisi deux fois, et rien n'est deviné — sans diurèse ni
    poids, le bilan le dit au lieu d'afficher un chiffre faux.
    """
    sejour = base.une_ligne("SELECT * FROM sejour WHERE id = ?", (sejour_id,))
    elements = elements_du_jour(base, sejour_id, date_jour)
    drains = [
        (d["libelle"], float(d["valeur"]))
        for d in drains_du_jour(base, sejour_id, date_jour)
        if d["valeur"] is not None
    ]
    return dom.bilan_hydrique(
        prescriptions_service.lignes_actives_le(base, sejour_id, date_jour),
        diurese_ml=_nombre_ou_none(elements.get("diurese_24h")),
        drains=drains,
        poids_kg=(sejour or {}).get("poids_kg"),
        temperature_c=_nombre_ou_none(elements.get("temperature")),
        # Ce qui coule en continu se compte réglage par réglage : une
        # noradrénaline montée la nuit et redescendue le matin ne vaut pas sa
        # vitesse d'ouverture pendant 24 h. Une seule requête pour tout le
        # séjour, pas une par seringue.
        reglages_par_ligne=vitesses_service.reglages_du_sejour(base, sejour_id),
        date_jour=date_jour,
    )


def _nombre_ou_none(valeur) -> float | None:
    return float(valeur) if isinstance(valeur, (int, float)) else None


def elements_du_jour(base: Base, sejour_id: str, date_jour: str) -> dict[str, float | str]:
    lignes = base.requete(
        "SELECT cle, valeur_num, valeur_texte FROM evolution_element "
        "WHERE sejour_id = ? AND date_jour = ? AND supprime = 0",
        (sejour_id, date_jour),
    )
    return {
        l["cle"]: (l["valeur_num"] if l["valeur_num"] is not None else l["valeur_texte"])
        for l in lignes
    }


def historique_element(base: Base, sejour_id: str, cle: str) -> list[dict]:
    """Cinétique d'un élément — la température ou la diurèse sur le séjour."""
    return base.requete(
        "SELECT date_jour, valeur_num FROM evolution_element "
        "WHERE sejour_id = ? AND cle = ? AND supprime = 0 AND valeur_num IS NOT NULL "
        "ORDER BY date_jour",
        (sejour_id, cle),
    )


# --------------------------------------------------------------------------
# Escarres — suivies dans le temps, comme un dispositif
# --------------------------------------------------------------------------

def ajouter_escarre(
    base: Base,
    *,
    sejour_id: str,
    localisation: str,
    grade: int | None,
    date_constat: str,
    commentaire: str | None = None,
    utilisateur_id: str | None = None,
) -> str:
    return base.inserer(
        "escarre",
        {"sejour_id": sejour_id, "localisation": localisation, "grade": grade,
         "date_constat": date_constat, "commentaire": commentaire},
        utilisateur_id=utilisateur_id,
    )


def modifier_escarre(
    base: Base, escarre_id: str, valeurs: dict, *, utilisateur_id: str | None = None
) -> None:
    base.mettre_a_jour("escarre", escarre_id, valeurs, utilisateur_id=utilisateur_id)


def escarres(base: Base, sejour_id: str, actives_seulement: bool = False) -> list[dict]:
    lignes = base.requete(
        "SELECT * FROM escarre WHERE sejour_id = ? AND supprime = 0 ORDER BY date_constat",
        (sejour_id,),
    )
    return [e for e in lignes if not e["date_guerison"]] if actives_seulement else lignes


def _texte_escarres(base: Base, sejour_id: str) -> str:
    actives = escarres(base, sejour_id, actives_seulement=True)
    if not actives:
        return ""
    morceaux = []
    for e in actives:
        grade = f" grade {e['grade']}" if e["grade"] else ""
        morceaux.append(f"{e['localisation'].lower()}{grade}")
    return "Escarres : " + ", ".join(morceaux)


# --------------------------------------------------------------------------
# Rendu des plans : éléments fixes + ce qui se calcule tout seul
# --------------------------------------------------------------------------

def _texte_elements(plan: str, elements: dict) -> str:
    """« FC 92/min · PA 105/58 mmHg · diurèse 1400 mL » — l'ordre du fichier de
    listes, seuls les éléments renseignés."""
    morceaux = []
    for cle, libelle, unite, type_, _plage in listes.ELEMENTS_PLAN.get(plan, ()):
        if cle not in elements:
            continue
        valeur = elements[cle]
        if type_ == "nombre":
            morceaux.append(f"{_libelle_court(libelle)} {_nombre_fr(valeur)}{_unite_collee(unite)}")
        elif type_ == "liste_pupilles":
            morceaux.append(listes.libelle(listes.PUPILLES, valeur))
        elif type_ == "oui_non":
            morceaux.append(f"{libelle} : {listes.libelle(listes.OUI_NON, valeur).lower()}")
        else:
            etat = listes.libelle(listes.TROIS_ETATS_PRESENCE, valeur).lower()
            morceaux.append(f"{libelle} : {etat}")
    # Une pression artérielle se lit « 105/58 (74) », jamais en trois morceaux.
    # La PAM entre parenthèses est calculée, pas saisie : la case a disparu de
    # l'évolution (demande du service, 8 septembre).
    pas, pad = elements.get("pas"), elements.get("pad")
    if pas is not None and pad is not None:
        position = next(
            (i for i, m in enumerate(morceaux) if m.startswith("PA systolique")),
            len(morceaux),
        )
        morceaux = [
            m for m in morceaux
            if not m.startswith(("PA systolique", "PA diastolique", "PAM"))
        ]
        pam = calculs.pression_arterielle_moyenne(pas=pas, pad=pad).valeur
        texte_pa = f"PA {_nombre_fr(pas)}/{_nombre_fr(pad)}"
        if pam is not None:
            texte_pa += f" ({_nombre_fr(pam)})"
        morceaux.insert(min(position, len(morceaux)), f"{texte_pa} mmHg")
    return " · ".join(morceaux)


def _libelle_court(libelle: str) -> str:
    """« Diurèse /24 h » se dit « Diurèse » dans une phrase."""
    return libelle.replace(" /24 h", "").replace(" clinique", "")


def _nombre_fr(valeur: float) -> str:
    """38.6 s'écrit 38,6 dans une observation française."""
    if float(valeur) == int(valeur):
        return str(int(valeur))
    return f"{valeur}".replace(".", ",")


def _unite_collee(unite: str) -> str:
    """« 92/min » et « 15 % » ne s'espacent pas pareil."""
    if not unite:
        return ""
    return unite if unite.startswith("/") else f" {unite}"


def texte_bilan_hydrique(base: Base, sejour_id: str, date_jour: str) -> str:
    """« Bilan hydrique −910 mL (entrées 1560 · diurèse 1200 · drains 150 ·
    pertes insensibles 1120) » — le net d'abord, son détail ensuite.

    Rien tant qu'il manque une donnée : un bilan à moitié calculé se recopie
    dans l'observation comme s'il était complet.
    """
    bilan = bilan_hydrique(base, sejour_id, date_jour)
    if bilan.net_ml is None:
        return ""
    detail = [
        f"entrées {_nombre_fr(round(bilan.entrees_ml))} mL",
        f"total pertes {_nombre_fr(round(bilan.sorties_ml))} mL",
        f"diurèse {_nombre_fr(round(bilan.diurese_ml))} mL",
    ]
    if bilan.drains_ml:
        detail.append(f"drains {_nombre_fr(round(bilan.drains_ml))} mL")
    detail.append(f"pertes insensibles {_nombre_fr(round(bilan.pertes_insensibles_ml))} mL")
    signe = "+" if bilan.net_ml > 0 else ""
    return (
        f"Bilan hydrique {signe}{_nombre_fr(round(bilan.net_ml))} mL "
        f"({' · '.join(detail)})"
    )


def _elements_automatiques(base: Base, sejour_id: str, plan: str, date_jour: str) -> str:
    """Ce que le logiciel sait déjà et que personne ne devrait retaper :
    « Sédaté J4 », « Extubé J2 », le mode ventilatoire du dernier gaz du sang,
    les antibiotiques en cours."""
    etats = dispositifs_service.etats(base, sejour_id, date_jour)
    morceaux: list[str] = []

    if plan == "neurologique":
        morceaux += [e.texte for e in etats if e.type == "sedation"]
    elif plan == "respiratoire":
        morceaux += [e.texte for e in etats if e.type in ("intubation", "tracheotomie")]
        gds = bilans_service.dernier_gaz_du_sang(base, sejour_id, date_jour)
        if gds and gds["mode_ventilatoire"]:
            vent = gds["mode_ventilatoire"]
            if gds["fio2"]:
                vent += f", FiO₂ {int(gds['fio2'])} %"
            if gds["pep"]:
                vent += f", PEP {int(gds['pep'])}"
            morceaux.append(vent)
    elif plan == "hemodynamique":
        amines = [
            l for l in prescriptions_service.lignes_actives_le(base, sejour_id, date_jour)
            if l["voie"] == "PSE" and l["statut"] == "active"
        ]
        morceaux += [
            f"{l['produit']} {dom._nombre(l['vitesse'])} cc/h" if l["vitesse"] else l["produit"]
            for l in amines
        ]
        morceaux += [e.texte for e in etats if e.type == "eer"]
        bilan = texte_bilan_hydrique(base, sejour_id, date_jour)
        if bilan:
            morceaux.append(bilan)
    elif plan == "infectieux":
        antibiotiques = [
            l for l in prescriptions_service.lignes_actives_le(base, sejour_id, date_jour)
            if l["statut"] == "active" and l["duree_prevue_jours"]
        ]
        morceaux += [
            f"{dom.etiquette_jour(l, date_jour).texte} {l['produit']}"
            for l in antibiotiques
        ]
        escarres_texte = _texte_escarres(base, sejour_id)
        if escarres_texte:
            morceaux.append(escarres_texte)

    return " · ".join(m for m in morceaux if m)
