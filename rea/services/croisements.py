"""Croiser deux variables d'une cohorte (bloc 19).

Les indicateurs de `statistiques.py` répondent à « comment va le service ? ».
Ce module répond à une autre famille de questions, celles qu'on se pose en
staff : *la mortalité est-elle différente selon le rapport PaO₂/FiO₂ ? selon
le E/e' ? combien de temps un patient reste-t-il ventilé sous telle molécule ?*

Le principe est volontairement simple et se tient en une phrase : on découpe
la cohorte en tranches selon un **facteur**, et on affiche un **résultat** par
tranche, avec l'effectif de chaque tranche à côté.

**Ce qu'on peut croiser n'est pas une liste écrite ici.** Les exemples cités
plus haut sont des exemples, pas le catalogue : ce qui doit être croisable,
c'est *ce que le dossier contient*. Les facteurs sont donc dérivés des
données elles-mêmes — les colonnes du séjour, tous les analytes de biologie
(y compris ceux que le service a ajoutés), tous les champs des gaz du sang,
toutes les mesures des quatre plans, les produits réellement prescrits, les
dispositifs réellement posés, les germes réellement isolés, les antécédents
réellement saisis. Une donnée nouvelle dans le dossier devient un facteur
sans que personne ait à toucher à ce fichier.

Ce que ce module refuse de faire, parce que ce sont les erreurs qui font
publier des choses fausses :

* **Afficher un taux sur trois patients.** Sous `EFFECTIF_MINIMAL`, la tranche
  garde son effectif mais son résultat est marqué non interprétable. Dans un
  service de douze lits, un croisement à quatre tranches vide les cases très
  vite, et « 100 % de mortalité » sur deux patients n'est pas un résultat.
* **Confondre absence et zéro.** Un séjour dont le facteur n'est pas
  renseigné n'entre dans aucune tranche : il est compté à part, et ce nombre
  est affiché. Une variable renseignée chez un tiers des patients produit un
  croisement sur un tiers des patients, et il faut le voir.
* **Laisser croire à une causalité.** Aucun test statistique n'est calculé
  ici, et c'est délibéré : un p-value affiché à côté d'un tableau descriptif
  univarié, monocentrique et non ajusté serait lu comme une preuve. Ce que
  produit ce module, ce sont des hypothèses à vérifier — et chaque résultat
  le dit.

Ce qu'il faut savoir pour lire ce qui en sort : les tranches d'une variable
continue sont découpées sur **la distribution de la cohorte elle-même**
(quartiles) sauf si on donne des seuils cliniques — pour le PaO₂/FiO₂, les
seuils de Berlin sont proposés par défaut.
"""

from __future__ import annotations

import datetime
import statistics
from dataclasses import dataclass, field

from .. import analytes as catalogue
from .. import listes
from ..db import Base
from ..domaine import temperature as temp_dom
from ..domaine.dates import age_ans, parse_date
from . import dispositifs as dispositifs_service
from . import scores as scores_service
from . import statistiques as stats

#: En deçà, une proportion n'est pas affichée comme un résultat. Ce n'est pas
#: un seuil statistique — c'est le nombre en dessous duquel un chiffre en
#: pourcentage induit franchement en erreur.
EFFECTIF_MINIMAL = 5

#: Seuils cliniques proposés par défaut pour certains facteurs continus.
#: Ailleurs, on découpe en quartiles de la cohorte.
SEUILS_CLINIQUES: dict[str, tuple[float, ...]] = {
    "pafi_min": (100, 200, 300),      # définition de Berlin
    "age": (40, 65, 80),
    "igs2": (30, 50, 70),
}


@dataclass(frozen=True)
class Variable:
    code: str
    libelle: str
    genre: str          # "continu" ou "categoriel"
    unite: str = ""
    note: str = ""
    #: Le groupe sous lequel la variable est proposée. Avec plusieurs
    #: centaines de facteurs, une liste à plat n'est plus une liste.
    famille: str = "Résultats"


@dataclass
class Strate:
    libelle: str
    effectif: int
    renseignes: int
    texte: str
    valeur: float | None = None
    interpretable: bool = True


@dataclass
class Croisement:
    facteur: Variable
    resultat: Variable
    strates: list[Strate] = field(default_factory=list)
    non_renseignes: int = 0
    total: int = 0
    avertissements: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# Ce qu'on peut croiser
# --------------------------------------------------------------------------

RESULTATS: tuple[Variable, ...] = (
    Variable("deces", "Mortalité en réanimation", "proportion", note="séjours clos"),
    Variable("deces_j28", "Mortalité à J28", "proportion",
             note="d'après le statut J28, quand il est renseigné"),
    Variable("duree_sejour", "Durée de séjour", "duree", "jours"),
    Variable("duree_ventilation", "Durée de ventilation mécanique", "duree", "jours"),
    Variable("jours_sans_ventilation", "Jours sans ventilation à J28", "duree", "jours",
             note="un patient décédé avant J28 compte 0 — c'est la définition"),
    Variable("infection_nosocomiale", "Infection nosocomiale déclarée", "proportion"),
    Variable("readmission", "Séjour de réadmission", "proportion"),
)

#: Colonnes du séjour utilisables comme facteur, avec leur libellé et leur
#: genre. Tout ce qui n'est pas ici est écarté volontairement : identifiants,
#: colonnes d'audit, textes libres (« complication_texte » ne se met pas en
#: tranches, et il peut porter un nom de patient).
_COLONNES_SEJOUR: tuple[tuple[str, str, str, str], ...] = (
    ("poids_kg", "Poids", "continu", "kg"),
    ("taille_cm", "Taille", "continu", "cm"),
    ("creatinine_base", "Créatinine de base", "continu", "µmol/L"),
    ("glasgow_initial", "Glasgow à l'admission", "continu", "/15"),
    ("lit_admission", "Lit d'admission", "categoriel", ""),
    ("provenance_type", "Provenance", "categoriel", ""),
    ("type_admission", "Type d'admission", "categoriel", ""),
    ("maladie_chronique_igs2", "Maladie chronique (IGS II)", "categoriel", ""),
    ("traumatique", "Admission traumatique", "categoriel", ""),
    ("mecanisme", "Mécanisme du traumatisme", "categoriel", ""),
    ("mode_sortie", "Mode de sortie", "categoriel", ""),
    ("destination", "Destination", "categoriel", ""),
    ("complication_statut", "Complication", "categoriel", ""),
    ("statut_j28", "Statut à J28", "categoriel", ""),
    ("est_readmission", "Réadmission", "categoriel", ""),
)

_FACTEURS_FIXES: tuple[Variable, ...] = (
    Variable("age", "Âge", "continu", "ans", famille="Dossier"),
    Variable("sexe", "Sexe", "categoriel", famille="Dossier"),
    Variable("imc", "IMC", "continu", "kg/m²", famille="Dossier"),
    Variable("duree_sejour", "Durée de séjour", "continu", "jours",
             famille="Dossier"),
    Variable("igs2", "IGS II à l'admission", "continu", "points",
             famille="Scores"),
    Variable("sofa_max", "SOFA maximal du séjour", "continu", "points",
             famille="Scores"),
    Variable("sofa_admission", "SOFA à l'admission", "continu", "points",
             famille="Scores"),
    Variable("pafi_min", "PaO₂/FiO₂ le plus bas", "continu", "mmHg",
             famille="Gaz du sang", note="tranches de Berlin par défaut"),
)

#: Champs numériques des gaz du sang, croisables comme les analytes.
_CHAMPS_GAZ: tuple[tuple[str, str, str], ...] = (
    ("ph", "pH", ""), ("pao2", "PaO₂", "mmHg"), ("paco2", "PaCO₂", "mmHg"),
    ("hco3", "HCO₃⁻", "mmol/L"), ("lactate", "Lactates", "mmol/L"),
    ("fio2", "FiO₂", "%"), ("pep", "PEP", "cmH₂O"), ("vt", "Vt", "mL"),
    ("spo2", "SpO₂", "%"),
)

#: Comment résumer une série de valeurs en une valeur par séjour.
MODES_ANALYTE = {
    "premier": "première valeur",
    "min": "valeur la plus basse",
    "max": "valeur la plus haute",
    "dernier": "dernière valeur",
}


def facteurs_disponibles(base: Base) -> list[Variable]:
    """Tout ce que le dossier permet de croiser, dérivé des données.

    Rien de ce qui suit n'est une liste de codes écrite à la main : les
    analytes viennent du catalogue (y compris ceux que le service a ajoutés),
    les produits, dispositifs, germes et antécédents viennent de ce qui a
    réellement été saisi. Une donnée nouvelle devient un facteur sans qu'on
    touche à ce fichier — c'est ce qui distingue « croiser mes données » de
    « croiser les six variables que le programmeur avait prévues ».

    Les facteurs vides sont écartés : proposer « a reçu X » pour un produit
    donné à un seul patient noie les cent facteurs utiles dans mille inutiles.
    """
    from . import analytes_locaux

    analytes_locaux.charger_dans_le_catalogue(base)
    variables = list(_FACTEURS_FIXES)

    variables += [
        Variable(f"sejour:{colonne}", libelle, genre, unite, famille="Dossier")
        for colonne, libelle, genre, unite in _COLONNES_SEJOUR
    ]

    # `GROUPES` est le catalogue livré ; `groupe_local()` porte les analytes
    # que le service a ajoutés lui-même. Oublier le second rendrait
    # impossible de croiser une mesure que le service a inventée hier.
    groupes = list(catalogue.GROUPES)
    local = catalogue.groupe_local()
    if local:
        groupes.append(local)
    for groupe in groupes:
        for analyte in groupe.analytes:
            for mode, libelle_mode in MODES_ANALYTE.items():
                variables.append(Variable(
                    f"bio:{analyte.id}:{mode}",
                    f"{analyte.libelle} — {libelle_mode}",
                    "continu", analyte.unite, famille=f"Biologie · {groupe.titre}",
                ))

    for champ, libelle, unite in _CHAMPS_GAZ:
        for mode, libelle_mode in MODES_ANALYTE.items():
            variables.append(Variable(
                f"gaz:{champ}:{mode}", f"{libelle} — {libelle_mode}",
                "continu", unite, famille="Gaz du sang",
            ))

    variables += _facteurs_evolution(base)
    variables += _facteurs_produits(base)
    variables += _facteurs_dispositifs(base)
    variables += _facteurs_germes(base)
    variables += _facteurs_antecedents(base)
    return variables


def _facteurs_evolution(base: Base) -> list[Variable]:
    """Les mesures des quatre plans effectivement saisies (FC, PA, RASS…)."""
    variables = []
    for ligne in base.requete(
        "SELECT DISTINCT cle FROM evolution_element WHERE supprime = 0 "
        "AND valeur_num IS NOT NULL ORDER BY cle"
    ):
        cle = ligne["cle"]
        for mode, libelle_mode in MODES_ANALYTE.items():
            variables.append(Variable(
                f"evo:{cle}:{mode}", f"{_libelle_element(cle)} — {libelle_mode}",
                "continu", famille="Surveillance quotidienne",
            ))
    return variables


def _libelle_element(cle: str) -> str:
    for elements in listes.ELEMENTS_PLAN.values():
        for champ in elements:
            if champ[0] == cle:
                return champ[1]
    return cle


def _facteurs_produits(base: Base) -> list[Variable]:
    """Un facteur « a reçu ce produit » par molécule réellement prescrite,
    et un facteur « combien de jours » pour la durée du traitement."""
    variables = []
    for p in base.requete(
        "SELECT produit, COUNT(DISTINCT sejour_id) AS n FROM prescription_ligne "
        "WHERE supprime = 0 GROUP BY produit HAVING n >= 2 ORDER BY n DESC"
    ):
        variables.append(Variable(
            f"produit:{p['produit']}", f"A reçu {p['produit']}", "categoriel",
            famille="Traitements", note=f"{p['n']} séjours",
        ))
        variables.append(Variable(
            f"duree_produit:{p['produit']}", f"Durée de {p['produit']}",
            "continu", "jours", famille="Traitements",
        ))
    return variables


def _facteurs_dispositifs(base: Base) -> list[Variable]:
    variables = []
    for d in base.requete(
        "SELECT type, COUNT(DISTINCT sejour_id) AS n FROM dispositif "
        "WHERE supprime = 0 GROUP BY type HAVING n >= 2 ORDER BY n DESC"
    ):
        libelle = listes.libelle_dispositif(d["type"])
        variables.append(Variable(
            f"dispositif:{d['type']}", f"A eu un(e) {libelle}", "categoriel",
            famille="Dispositifs", note=f"{d['n']} séjours",
        ))
        variables.append(Variable(
            f"duree_dispositif:{d['type']}", f"Durée du/de la {libelle}",
            "continu", "jours", famille="Dispositifs",
        ))
    return variables


def _facteurs_germes(base: Base) -> list[Variable]:
    return [
        Variable(f"germe:{g['germe']}", f"A isolé {g['germe']}", "categoriel",
                 famille="Microbiologie", note=f"{g['n']} séjours")
        for g in base.requete(
            "SELECT germe, COUNT(DISTINCT sejour_id) AS n FROM microbiologie "
            "WHERE supprime = 0 AND germe IS NOT NULL AND germe != '' "
            "GROUP BY germe HAVING n >= 2 ORDER BY n DESC"
        )
    ]


def _facteurs_antecedents(base: Base) -> list[Variable]:
    return [
        Variable(f"atcd:{a['libelle']}", f"Antécédent : {a['libelle']}",
                 "categoriel", famille="Antécédents", note=f"{a['n']} patients")
        for a in base.requete(
            "SELECT libelle, COUNT(DISTINCT patient_id) AS n FROM antecedent "
            "WHERE supprime = 0 AND statut = 'present' "
            "GROUP BY libelle HAVING n >= 2 ORDER BY n DESC"
        )
    ]


def variable(code: str, base: Base | None = None) -> Variable | None:
    """Retrouver une variable depuis son code, sans relire toute la base.

    Les facteurs dérivés des données sont des centaines : les reconstruire
    pour en retrouver un seul coûterait une dizaine de requêtes à chaque
    croisement. Le code se suffit à lui-même, et son préfixe dit tout.
    """
    for v in _FACTEURS_FIXES + RESULTATS:
        if v.code == code:
            return v
    if ":" not in code:
        return None
    prefixe, reste = code.split(":", 1)

    if prefixe == "sejour":
        for colonne, libelle, genre, unite in _COLONNES_SEJOUR:
            if colonne == reste:
                return Variable(code, libelle, genre, unite, famille="Dossier")
        return Variable(code, reste, "categoriel", famille="Dossier")
    if prefixe == "bio":
        id_analyte, mode = reste.split(":", 1)
        analyte = catalogue.analyte(id_analyte)
        return Variable(code, f"{analyte.libelle} — {MODES_ANALYTE.get(mode, mode)}",
                        "continu", analyte.unite, famille="Biologie")
    if prefixe == "gaz":
        champ, mode = reste.split(":", 1)
        libelle, unite = next(
            ((l, u) for c, l, u in _CHAMPS_GAZ if c == champ), (champ, ""))
        return Variable(code, f"{libelle} — {MODES_ANALYTE.get(mode, mode)}",
                        "continu", unite, famille="Gaz du sang")
    if prefixe == "evo":
        cle, mode = reste.split(":", 1)
        return Variable(code, f"{_libelle_element(cle)} — {MODES_ANALYTE.get(mode, mode)}",
                        "continu", famille="Surveillance quotidienne")
    if prefixe == "produit":
        return Variable(code, f"A reçu {reste}", "categoriel", famille="Traitements")
    if prefixe == "duree_produit":
        return Variable(code, f"Durée de {reste}", "continu", "jours",
                        famille="Traitements")
    if prefixe == "dispositif":
        return Variable(code, f"A eu un(e) {listes.libelle_dispositif(reste)}",
                        "categoriel", famille="Dispositifs")
    if prefixe == "duree_dispositif":
        return Variable(code, f"Durée du/de la {listes.libelle_dispositif(reste)}",
                        "continu", "jours", famille="Dispositifs")
    if prefixe == "germe":
        return Variable(code, f"A isolé {reste}", "categoriel", famille="Microbiologie")
    if prefixe == "atcd":
        return Variable(code, f"Antécédent : {reste}", "categoriel",
                        famille="Antécédents")
    return None


# --------------------------------------------------------------------------
# Lire une valeur par séjour
# --------------------------------------------------------------------------

def valeur_facteur(base: Base, sejour: dict, code: str):
    """La valeur du facteur pour ce séjour, ou None si non renseignée.

    None veut dire « on ne sait pas », jamais « zéro » ni « non » : c'est ce
    qui fait qu'un séjour sans la donnée sort du croisement au lieu d'aller
    grossir une tranche par défaut. Seule exception assumée, les facteurs
    « a reçu / a eu / a isolé » : là, l'absence de ligne *est* un non, et le
    dire « inconnu » viderait le croisement de sa moitié utile.
    """
    if code == "age":
        return age_ans(sejour.get("date_naissance"), sejour.get("date_admission"))
    if code == "sexe":
        return sejour.get("sexe") or None
    if code == "imc":
        poids, taille = sejour.get("poids_kg"), sejour.get("taille_cm")
        if not poids or not taille:
            return None
        return round(poids / (taille / 100) ** 2, 1)
    if code == "duree_sejour":
        return stats.duree_sejour_jours(sejour)
    if code == "igs2":
        return scores_service.igs2(base, sejour["id"]).total
    if code in ("sofa_max", "sofa_admission"):
        serie = [total for _jour, total in scores_service.evolution_sofa(base, sejour["id"])]
        if not serie:
            return None
        return max(serie) if code == "sofa_max" else serie[0]
    if code == "pafi_min":
        return _pafi_min(base, sejour["id"])

    if ":" not in code:
        return None
    prefixe, reste = code.split(":", 1)

    if prefixe == "sejour":
        return _valeur_colonne_sejour(sejour, reste)
    if prefixe == "bio":
        id_analyte, mode = reste.split(":", 1)
        return _resume(_serie_analyte(base, sejour["id"], id_analyte), mode)
    if prefixe == "gaz":
        champ, mode = reste.split(":", 1)
        return _resume(_serie_gaz(base, sejour["id"], champ), mode)
    if prefixe == "evo":
        cle, mode = reste.split(":", 1)
        return _resume(_serie_evolution(base, sejour["id"], cle), mode)
    if prefixe == "produit":
        return _oui_non(base.une_ligne(
            "SELECT 1 AS oui FROM prescription_ligne WHERE sejour_id = ? "
            "AND produit = ? AND supprime = 0 LIMIT 1",
            (sejour["id"], reste),
        ))
    if prefixe == "duree_produit":
        return _duree_produit(base, sejour, reste)
    if prefixe == "dispositif":
        return _oui_non(base.une_ligne(
            "SELECT 1 AS oui FROM dispositif WHERE sejour_id = ? AND type = ? "
            "AND supprime = 0 LIMIT 1",
            (sejour["id"], reste),
        ))
    if prefixe == "duree_dispositif":
        return _duree_dispositif(base, sejour, reste)
    if prefixe == "germe":
        return _oui_non(base.une_ligne(
            "SELECT 1 AS oui FROM microbiologie WHERE sejour_id = ? AND germe = ? "
            "AND supprime = 0 LIMIT 1",
            (sejour["id"], reste),
        ))
    if prefixe == "atcd":
        return _oui_non(base.une_ligne(
            "SELECT 1 AS oui FROM antecedent WHERE patient_id = ? AND libelle = ? "
            "AND statut = 'present' AND supprime = 0 LIMIT 1",
            (sejour["patient_id"], reste),
        ))
    return None


def _oui_non(ligne) -> str:
    return "Oui" if ligne else "Non"


#: Colonnes entières qui portent un oui/non/inconnu, où 0 et 1 à l'écran ne
#: veulent rien dire.
_COLONNES_BOOLEENNES = {"traumatique", "est_readmission", "meme_etablissement",
                        "deces_reanimation"}


def _valeur_colonne_sejour(sejour: dict, colonne: str):
    valeur = sejour.get(colonne)
    if valeur is None or valeur == "":
        return None
    if colonne in _COLONNES_BOOLEENNES:
        return "Oui" if valeur else "Non"
    return valeur


def _resume(valeurs: list[float], mode: str):
    """Une série de mesures ramenée à une valeur par séjour."""
    if not valeurs:
        return None
    return {"premier": valeurs[0], "dernier": valeurs[-1],
            "min": min(valeurs), "max": max(valeurs)}.get(mode)


def _serie_analyte(base: Base, sejour_id: str, id_analyte: str) -> list[float]:
    return [
        ligne["valeur_num"]
        for ligne in base.requete(
            "SELECT valeur_num FROM bilan_resultat WHERE sejour_id = ? "
            "AND analyte = ? AND supprime = 0 AND valeur_num IS NOT NULL "
            "ORDER BY date_heure",
            (sejour_id, id_analyte),
        )
    ]


def _serie_gaz(base: Base, sejour_id: str, champ: str) -> list[float]:
    # Le nom de colonne vient de `_CHAMPS_GAZ`, jamais de l'utilisateur : il
    # ne peut pas être interpolé autrement qu'avec une valeur de cette liste.
    if champ not in {c for c, _l, _u in _CHAMPS_GAZ}:
        return []
    return [
        ligne[champ]
        for ligne in base.requete(
            f"SELECT {champ} FROM gaz_du_sang WHERE sejour_id = ? AND supprime = 0 "
            f"AND {champ} IS NOT NULL ORDER BY date_heure",
            (sejour_id,),
        )
    ]


def _pafi_min(base: Base, sejour_id: str) -> float | None:
    """Le pire rapport PaO₂/FiO₂ du séjour.

    Le rapport n'est pas stocké : il se recalcule à partir de chaque gaz du
    sang, et seuls ceux qui portent les deux valeurs comptent. Un gaz sans
    FiO₂ — air ambiant — n'a pas de rapport, il n'en vaut pas zéro : le
    compter ferait du patient le plus grave du service celui qui respire seul.
    """
    rapports = []
    for gaz in base.requete(
        "SELECT pao2, fio2 FROM gaz_du_sang WHERE sejour_id = ? AND supprime = 0",
        (sejour_id,),
    ):
        if gaz["pao2"] and gaz["fio2"]:
            rapports.append(gaz["pao2"] / (gaz["fio2"] / 100))
    return round(min(rapports)) if rapports else None


def _serie_evolution(base: Base, sejour_id: str, cle: str) -> list[float]:
    return [
        ligne["valeur_num"]
        for ligne in base.requete(
            "SELECT valeur_num FROM evolution_element WHERE sejour_id = ? "
            "AND cle = ? AND supprime = 0 AND valeur_num IS NOT NULL "
            "ORDER BY date_jour",
            (sejour_id, cle),
        )
    ]


def _duree_produit(base: Base, sejour: dict, produit: str) -> int | None:
    """Le nombre de jours cumulés sous ce produit, épisode par épisode.

    Un traitement encore en cours compte jusqu'à aujourd'hui — pas jusqu'à
    l'infini, et pas zéro non plus.
    """
    jours = 0
    trouve = False
    for ligne in base.requete(
        "SELECT date_debut, date_arret FROM prescription_ligne WHERE sejour_id = ? "
        "AND produit = ? AND supprime = 0",
        (sejour["id"], produit),
    ):
        trouve = True
        jours += _duree(ligne["date_debut"], ligne["date_arret"], sejour)
    return jours if trouve else None


def _duree_dispositif(base: Base, sejour: dict, type_: str) -> int | None:
    jours = 0
    trouve = False
    for ligne in base.requete(
        "SELECT date_pose, date_retrait FROM dispositif WHERE sejour_id = ? "
        "AND type = ? AND supprime = 0",
        (sejour["id"], type_),
    ):
        trouve = True
        jours += _duree(ligne["date_pose"], ligne["date_retrait"], sejour)
    return jours if trouve else None


def _duree(debut: str, fin: str | None, sejour: dict) -> int:
    depart = parse_date(debut)
    arrivee = (
        parse_date(fin)
        or parse_date(sejour.get("date_sortie"))
        or datetime.date.today()
    )
    return max(0, (arrivee - depart).days) + 1 if depart else 0


def valeur_resultat(base: Base, sejour: dict, code: str):
    if code == "deces":
        if not sejour.get("date_sortie"):
            return None          # séjour en cours : l'issue n'est pas connue
        return bool(stats._est_decede(sejour))
    if code == "deces_j28":
        statut = sejour.get("statut_j28")
        if statut in (None, "", "perdu_de_vue"):
            return None          # perdu de vue n'est pas « vivant »
        return statut == "decede"
    if code == "duree_sejour":
        return stats.duree_sejour_jours(sejour)
    if code == "duree_ventilation":
        return dispositifs_service.duree_ventilation_jours(base, sejour["id"])
    if code == "jours_sans_ventilation":
        return scores_service.jours_sans_ventilation(base, sejour["id"])
    if code == "infection_nosocomiale":
        return bool(base.une_ligne(
            "SELECT 1 AS oui FROM infection_nosocomiale WHERE sejour_id = ? "
            "AND supprime = 0 LIMIT 1",
            (sejour["id"],),
        ))
    if code == "readmission":
        return bool(sejour.get("est_readmission"))
    if code.startswith("duree_dispositif:"):
        return _duree_dispositif(base, sejour, code.split(":", 1)[1])
    return None


# --------------------------------------------------------------------------
# Le croisement lui-même
# --------------------------------------------------------------------------

def croiser(
    base: Base,
    sejours: list[dict],
    *,
    code_facteur: str,
    code_resultat: str,
    seuils: tuple[float, ...] | None = None,
) -> Croisement:
    facteur = variable(code_facteur, base) or Variable(code_facteur, code_facteur, "categoriel")
    resultat = variable(code_resultat) or Variable(code_resultat, code_resultat, "duree")

    couples = []
    non_renseignes = 0
    for sejour in sejours:
        v = valeur_facteur(base, sejour, code_facteur)
        if v is None:
            non_renseignes += 1
            continue
        couples.append((v, valeur_resultat(base, sejour, code_resultat)))

    if facteur.genre == "continu":
        groupes = _tranches_continues(couples, seuils or SEUILS_CLINIQUES.get(code_facteur))
    else:
        groupes = _tranches_categorielles(couples)

    croisement = Croisement(
        facteur=facteur, resultat=resultat,
        non_renseignes=non_renseignes, total=len(sejours),
    )
    for libelle, valeurs in groupes:
        croisement.strates.append(_resumer(libelle, valeurs, resultat))

    if non_renseignes:
        croisement.avertissements.append(
            f"{non_renseignes} séjour(s) sur {len(sejours)} n'ont pas cette "
            f"donnée : ils ne sont dans aucune tranche."
        )
    if any(not s.interpretable for s in croisement.strates):
        croisement.avertissements.append(
            f"Certaines tranches comptent moins de {EFFECTIF_MINIMAL} séjours : "
            "leur résultat n'est pas affiché en proportion."
        )
    croisement.avertissements.append(
        "Descriptif, univarié, non ajusté et monocentrique : ce tableau "
        "fabrique une hypothèse, il ne démontre rien."
    )
    return croisement


def _tranches_continues(couples, seuils):
    """Découpe par seuils cliniques si on en donne, par quartiles sinon."""
    valeurs = sorted(v for v, _r in couples)
    if not valeurs:
        return []
    if not seuils:
        if len(valeurs) < 4:
            return [("Toutes valeurs", couples)]
        q = statistics.quantiles(valeurs, n=4)
        seuils = tuple(round(x, 2) for x in q)
    bornes = [None, *seuils, None]
    groupes = []
    for i in range(len(bornes) - 1):
        bas, haut = bornes[i], bornes[i + 1]
        dedans = [
            (v, r) for v, r in couples
            if (bas is None or v >= bas) and (haut is None or v < haut)
        ]
        if bas is None:
            libelle = f"< {_nb(haut)}"
        elif haut is None:
            libelle = f"≥ {_nb(bas)}"
        else:
            libelle = f"{_nb(bas)} – {_nb(haut)}"
        groupes.append((libelle, dedans))
    return groupes


def _tranches_categorielles(couples):
    par_categorie: dict[str, list] = {}
    for v, r in couples:
        par_categorie.setdefault(str(v), []).append((v, r))
    return sorted(par_categorie.items())


def _resumer(libelle: str, couples: list, resultat: Variable) -> Strate:
    effectif = len(couples)
    renseignes = [r for _v, r in couples if r is not None]

    if not renseignes:
        return Strate(libelle, effectif, 0, "—", None, False)

    if resultat.genre == "proportion":
        positifs = sum(1 for r in renseignes if r)
        if len(renseignes) < EFFECTIF_MINIMAL:
            return Strate(
                libelle, effectif, len(renseignes),
                f"{positifs}/{len(renseignes)} — trop peu pour un pourcentage",
                None, False,
            )
        part = positifs / len(renseignes)
        return Strate(
            libelle, effectif, len(renseignes),
            f"{positifs}/{len(renseignes)} ({part * 100:.0f} %)", part * 100,
        )

    mediane = statistics.median(renseignes)
    if len(renseignes) >= 4:
        q1, _q2, q3 = statistics.quantiles(renseignes, n=4)
        detail = f" (IQR {_nb(q1)}–{_nb(q3)})"
    else:
        detail = ""
    return Strate(
        libelle, effectif, len(renseignes),
        f"médiane {_nb(mediane)} {resultat.unite}{detail}", float(mediane),
        len(renseignes) >= EFFECTIF_MINIMAL,
    )


def _nb(valeur: float) -> str:
    """Un nombre lisible : sans décimale quand il est entier."""
    if valeur is None:
        return "—"
    if float(valeur).is_integer():
        return str(int(valeur))
    return f"{valeur:.1f}".replace(".", ",")


# --------------------------------------------------------------------------
# Délai d'apyrexie sous une molécule
# --------------------------------------------------------------------------
# « À partir de combien de jours un patient décroche sous telle molécule ? »
# Décrocher, c'est **ne plus être fébrile** (définition du service,
# 9 septembre) : ni fébrile ni subfébrile — apyrétique.
#
# Ce n'est pas un croisement en tranches mais un délai jusqu'à un événement,
# donc un module à part. Le piège de ce genre de calcul a un nom : ne compter
# que ceux qui ont décroché. Un patient encore fébrile à l'arrêt du traitement
# n'a pas un délai « très long », il n'a **pas** de délai — et l'oublier fait
# paraître efficace une molécule sous laquelle personne ne décroche.


@dataclass
class Apyrexie:
    produit: str
    episodes: int = 0            # traitements commencés chez un patient fébrile
    decroches: int = 0           # devenus apyrétiques avant la fin du traitement
    delais: list[int] = field(default_factory=list)
    jamais_decroches: int = 0
    sans_temperature: int = 0    # température non mesurée au départ
    avertissements: list[str] = field(default_factory=list)

    @property
    def delai_median(self) -> float | None:
        return statistics.median(self.delais) if self.delais else None

    @property
    def part_decroches(self) -> float | None:
        if self.episodes < EFFECTIF_MINIMAL:
            return None
        return self.decroches / self.episodes


def delai_apyrexie(base: Base, sejours: list[dict], produit: str) -> Apyrexie:
    """Combien de jours avant l'apyrexie, sous ce produit.

    Un épisode compte si le patient était **fébrile le jour où le traitement
    a commencé** : sans fièvre au départ, il n'y a rien à mesurer. Le délai
    est le nombre de jours jusqu'au premier jour apyrétique, le jour de début
    comptant pour J1 — la même convention que les compteurs J de la pancarte.

    Une température non mesurée n'est jamais lue comme une apyrexie : ce
    serait faire décrocher tout patient qu'on a simplement cessé de mesurer.
    """
    resultat = Apyrexie(produit=produit)
    for sejour in sejours:
        for episode in base.requete(
            "SELECT id, date_debut, date_arret FROM prescription_ligne "
            "WHERE sejour_id = ? AND produit = ? AND supprime = 0 "
            "ORDER BY date_debut",
            (sejour["id"], produit),
        ):
            _compter_episode(base, sejour, episode, resultat)

    if resultat.sans_temperature:
        resultat.avertissements.append(
            f"{resultat.sans_temperature} traitement(s) écartés : température "
            "non mesurée le jour du début."
        )
    if resultat.jamais_decroches:
        resultat.avertissements.append(
            f"{resultat.jamais_decroches} patient(s) sur {resultat.episodes} "
            "n'ont pas décroché avant la fin du traitement. Ils ne sont pas "
            "dans la médiane — la lire seule ferait paraître efficace une "
            "molécule sous laquelle personne ne décroche."
        )
    if resultat.episodes < EFFECTIF_MINIMAL:
        resultat.avertissements.append(
            f"Moins de {EFFECTIF_MINIMAL} traitements : rien à conclure."
        )
    resultat.avertissements.append(
        "Aucun ajustement sur la gravité, le germe ou les traitements "
        "associés : ce délai décrit, il ne compare pas."
    )
    return resultat


def _compter_episode(base: Base, sejour: dict, episode: dict, resultat: Apyrexie) -> None:
    temperatures = _temperatures_du_sejour(base, sejour["id"])
    debut = episode["date_debut"]
    if not temp_dom.est_febrile(temperatures.get(debut)):
        if temperatures.get(debut) is None:
            resultat.sans_temperature += 1
        return

    resultat.episodes += 1
    fin = episode["date_arret"] or sejour.get("date_sortie") or max(temperatures, default=debut)
    jours = sorted(j for j in temperatures if debut <= j <= str(fin)[:10])
    for jour in jours:
        if temp_dom.est_apyretique(temperatures[jour]):
            resultat.decroches += 1
            resultat.delais.append(
                (parse_date(jour) - parse_date(debut)).days + 1
            )
            return
    resultat.jamais_decroches += 1


def _temperatures_du_sejour(base: Base, sejour_id: str) -> dict[str, float]:
    """date_jour -> température relevée ce jour-là (plan infectieux)."""
    return {
        ligne["date_jour"]: ligne["valeur_num"]
        for ligne in base.requete(
            "SELECT date_jour, valeur_num FROM evolution_element "
            "WHERE sejour_id = ? AND cle = 'temperature' AND supprime = 0 "
            "AND valeur_num IS NOT NULL ORDER BY date_jour",
            (sejour_id,),
        )
    }
