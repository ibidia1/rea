"""Listes codées (SPEC §4) — chargées depuis `referentiels/` (règle R2).

Chaque valeur a un **code stable** et un libellé affiché. Le code est ce qui
part en base et en export ; le libellé peut être réécrit sans casser les
statistiques déjà produites. Rien dans le programme ne doit stocker un libellé.

Ce module ne contient plus les listes elles-mêmes : elles vivent dans des
fichiers JSON versionnés, modifiables sans toucher au code (feuille de route,
règle R2). Il ne reste ici que les noms exportés, les quelques constantes qui
relèvent d'une règle de conception plutôt que d'un choix de service, et les
fonctions d'accès.
"""

from __future__ import annotations

from . import referentiels

_charger = referentiels.charger

# --------------------------------------------------------------------------
# Utilisateurs (SPEC §1.2)
# --------------------------------------------------------------------------
ROLES = _charger("roles")

# --------------------------------------------------------------------------
# Trois états explicites (règle de conception 7)
# --------------------------------------------------------------------------
# Ces trois-là ne sont pas un référentiel : c'est une règle de conception du
# logiciel (« ne pas savoir » n'est pas « absent »). Les sortir en fichier
# laisserait croire qu'on peut les modifier — on ne peut pas, tout le code de
# lecture repose dessus.
TROIS_ETATS = (
    ("non_renseigne", "Non renseigné"),
    ("aucune", "Aucune"),
    ("presente", "Présente"),
)
TROIS_ETATS_PRESENCE = (
    ("non_renseigne", "Non renseigné"),
    ("present", "Présent"),
    ("absent", "Absent"),
)
OUI_NON = (
    ("non_renseigne", "Non renseigné"),
    ("oui", "Oui"),
    ("non", "Non"),
)

# --------------------------------------------------------------------------
# Identité et séjour (SPEC §4.1)
# --------------------------------------------------------------------------
SEXES = _charger("sexes")
PROVENANCES = _charger("provenances")
# Provenances qui appellent un détail écrit (nom du service, de l'hôpital).
PROVENANCES_AVEC_DETAIL = referentiels.annexe("provenances", "avec_detail")
MODES_SORTIE = _charger("modes_sortie")

# --------------------------------------------------------------------------
# Antécédents (SPEC §4.2)
# --------------------------------------------------------------------------
CATEGORIES_ANTECEDENT = _charger("categories_antecedent")
# Liste courte en accès direct — à valider par un senior (SPEC §4.2).
ANTECEDENTS_COURTS = _charger("antecedents_courts")
# Conditions chroniques alignées sur le dictionnaire ANZICS (SPEC §9.5).
CONDITIONS_CHRONIQUES = _charger("conditions_chroniques")

# --------------------------------------------------------------------------
# Motif traumatique (SPEC §4.3)
# --------------------------------------------------------------------------
REGIONS_TRAUMATIQUES = _charger("regions_traumatiques")
MECANISMES = _charger("mecanismes")
MECANISMES_AVEC_DETAIL = referentiels.annexe("mecanismes", "avec_detail")

# --------------------------------------------------------------------------
# Motif non traumatique (SPEC §4.4)
# --------------------------------------------------------------------------
# Structure : groupe → (code, libellé, champs de précision attendus).
MOTIFS_NON_TRAUMATIQUES: dict[str, tuple[tuple[str, str, tuple[str, ...]], ...]] = (
    _charger("motifs_non_traumatiques")
)
PORTES_ENTREE_SEPSIS = _charger("portes_entree_sepsis")
PROFONDEURS_BRULURE = _charger("profondeurs_brulure")
AGENTS_BRULURE = _charger("agents_brulure")

# --------------------------------------------------------------------------
# Interventions (SPEC §4.6) — liste provisoire, question ouverte 10
# --------------------------------------------------------------------------
GESTES_CHIRURGICAUX = _charger("gestes_chirurgicaux")

# --------------------------------------------------------------------------
# Prescription (SPEC §5.2)
# --------------------------------------------------------------------------
# Chaque voie déclare les champs que le formulaire doit demander — et donc
# aussi ceux qu'il ne doit pas demander.
VOIES: dict[str, dict] = _charger("voies", "voies")
ORDRE_VOIES = _charger("voies", "ordre")

# Sous-types de la voie « Entrées » : une perfusion se prescrit en cc/h, une
# nutrition en volume sur 24 h. Les deux comptent dans le bilan des entrées.
SOUS_TYPES_ENTREES = _charger("sous_types_entrees")

# Ce qui passe dans une voie « Entrées », et ce qu'on ajoute dans le flacon.
# Les deux étaient des champs libres : « SG5 », « G5% » et « sérum glucosé 5 »
# désignaient le même soluté sans jamais se compter ensemble, et « KCl 2 »,
# « 2 amp KCl » et « +2K » la même ampoule (demande du service, 8 septembre).
PRODUITS_ENTREES = _charger("produits_entrees")
ADDITIFS_PERFUSION = _charger("additifs_perfusion")
RYTHMES = _charger("rythmes")
UNITES = _charger("unites")
STATUTS_LIGNE = _charger("statuts_ligne")

# --------------------------------------------------------------------------
# Bilans à demander pour le lendemain (SPEC §5.2 bis) — à valider
# --------------------------------------------------------------------------
EXAMENS_A_DEMANDER = _charger("examens_a_demander")

# --------------------------------------------------------------------------
# Explorations (SPEC §6) — liste à compléter avec un senior
# --------------------------------------------------------------------------
# Chaque type déclare ses valeurs chiffrées : (clé, libellé, unité, type).
TYPES_EXPLORATION: dict[str, dict] = _charger("types_exploration")

# --------------------------------------------------------------------------
# Microbiologie (SPEC §7.4)
# --------------------------------------------------------------------------
PRELEVEMENTS = _charger("prelevements")
RESULTATS_MICROBIO = _charger("resultats_microbio")
# Molécules proposées à la saisie d'un antibiogramme (S / I / R) — une liste
# fermée, pour qu'une même molécule s'écrive toujours pareil et se compte.
ANTIBIOTIQUES_ANTIBIOGRAMME = _charger("antibiotiques_antibiogramme")

# --------------------------------------------------------------------------
# Infections nosocomiales (SPEC §9.2)
# --------------------------------------------------------------------------
INFECTIONS_NOSOCOMIALES = _charger("infections_nosocomiales")

# --------------------------------------------------------------------------
# Dispositifs et actes invasifs (écran « Explorations et actes »)
# --------------------------------------------------------------------------
# Chaque type déclare :
#   - le libellé affiché
#   - `sites`   : liste de sites possibles, vide si la notion n'a pas de sens
#   - `champs`  : champs supplémentaires demandés à la pose
#   - `en_cours`/`apres` : comment le compteur de jours se lit une fois posé
#     puis une fois retiré (ex. « Intubé J3 » → « Extubé J2 »)
#
# Le compteur est calculé, jamais saisi : c'est tout l'intérêt de la table.
TYPES_DISPOSITIF: dict[str, dict] = _charger("types_dispositif", "types")
ORDRE_DISPOSITIFS = _charger("types_dispositif", "ordre")
# Champs supplémentaires : libellé du formulaire, puis préfixe et unité pour
# l'affichage compact (« repère 22 cm », « 3 voies »).
CHAMPS_DISPOSITIF: dict[str, tuple[str, str, str]] = _charger(
    "types_dispositif", "champs"
)

# --------------------------------------------------------------------------
# Éléments fixes des quatre plans de l'évolution (SPEC §8.1)
# --------------------------------------------------------------------------
# Ce que l'interne écrivait à la main tous les jours, devenu saisissable en un
# geste — et donc exploitable en cinétique.
#   (clé, libellé, unité, type, plage affichée en gris)
ELEMENTS_PLAN: dict[str, tuple[tuple[str, str, str, str, str], ...]] = _charger(
    "elements_plan"
)
PUPILLES = _charger("pupilles")

# Escarres — grades NPUAP/EPUAP
LOCALISATIONS_ESCARRE = _charger("escarres", "localisations")
GRADES_ESCARRE = _charger("escarres", "grades")


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def libelle(liste, code: str | None, defaut: str = "") -> str:
    """Libellé d'un code dans une liste de paires (code, libellé, …)."""
    if code is None:
        return defaut
    for entree in liste:
        if entree[0] == code:
            return entree[1]
    return code


def sous_type_du_produit(produit: str | None) -> str | None:
    """Perfusion ou nutrition ? Le catalogue le sait déjà pour ses produits.

    Comparé sur le libellé et non sur le code : c'est le libellé qui est
    enregistré sur la ligne, et c'est lui qu'on relit en rouvrant une
    prescription.
    """
    if not produit:
        return None
    nom = produit.strip().lower()
    for entree in PRODUITS_ENTREES:
        if entree[1].lower() == nom:
            return entree[2] if len(entree) > 2 else None
    return None


def codes(liste) -> tuple[str, ...]:
    return tuple(entree[0] for entree in liste)


def motifs_a_plat() -> tuple[tuple[str, str, str], ...]:
    """Tous les motifs non traumatiques : (code, libellé, groupe)."""
    return tuple(
        (code, lib, groupe)
        for groupe, entrees in MOTIFS_NON_TRAUMATIQUES.items()
        for code, lib, _precisions in entrees
    )


def libelle_motif(code: str | None) -> str:
    if not code:
        return ""
    for c, lib, _groupe in motifs_a_plat():
        if c == code:
            return lib
    return code


def precisions_motif(code: str) -> tuple[str, ...]:
    for _groupe, entrees in MOTIFS_NON_TRAUMATIQUES.items():
        for c, _lib, precisions in entrees:
            if c == code:
                return precisions
    return ()


def libelle_dispositif(code: str | None) -> str:
    if not code:
        return ""
    return TYPES_DISPOSITIF.get(code, {}).get("libelle", code)
