"""Écran 3 — Le prescrit (SPEC §5). Le cœur du logiciel.

Décision de modèle (v1.3, journal SPEC) : une ligne de prescription n'est
JAMAIS dupliquée pour le lendemain. Elle porte `date_debut` / `date_arret` ;
la pancarte d'un jour donné est calculée par intersection avec cette
période. « Préparer la pancarte de demain » ne copie donc aucune ligne — il
crée une `journee` (pour les bilans à demander) et calcule à l'affichage
quelles lignes seront actives, reconduites, échues.

Deux niveaux (v3.8) : `prescription_ligne` est l'**épisode** de traitement —
produit, indication, date de début — et c'est lui qui porte le compteur J{n}
et la durée d'antibiothérapie. `prescription_posologie` porte les **versions**
de dose et de rythme, chacune valable à partir d'un jour. Changer la dose
crée une version, pas un épisode : le compteur ne repart pas à J1, et la
posologie initiale reste lisible.

Les fonctions de lecture rendent l'épisode déjà recomposé avec la posologie
du jour demandé — un dictionnaire de ligne comme avant. Les écrans n'ont pas
à connaître les deux tables, et il n'y a qu'un seul endroit où la jointure se
fait.
"""

from __future__ import annotations

from datetime import date

from ..db import Base
from ..domaine import prescription as dom
from ..domaine.dates import lendemain


# --------------------------------------------------------------------------
# Ajout / modification / arrêt d'une ligne (SPEC §5.1, §5.2)
# --------------------------------------------------------------------------

def ajouter_ligne(
    base: Base,
    *,
    sejour_id: str,
    voie: str,
    produit: str,
    date_debut: str,
    dose: float | None = None,
    unite: str | None = None,
    rythme: str | None = None,
    condition_texte: str | None = None,
    dilution: str | None = None,
    nb_ampoules: float | None = None,
    vitesse: float | None = None,
    volume_dilution: float | None = None,
    volume_24h: float | None = None,
    additifs: str | None = None,
    sous_type: str | None = None,
    duree_prevue_jours: int | None = None,
    horaires_override: str | None = None,
    code_atc: str | None = None,
    protocole_code: str | None = None,
    protocole_version: str | None = None,
    indication: str | None = None,
    utilisateur_id: str | None = None,
) -> str:
    """Ouvre un épisode de traitement et sa première version de posologie.

    Les deux vont ensemble, dans la même transaction : un épisode sans
    posologie serait un traitement dont personne ne sait ce qu'il faut donner.
    """
    with base.transaction():
        ligne_id = base.inserer(
            "prescription_ligne",
            {
                "sejour_id": sejour_id,
                "voie": voie,
                "sous_type": sous_type,
                "produit": produit,
                # L'indication fait partie de l'identité de l'épisode : le même
                # produit redonné pour autre chose est un autre traitement.
                "indication": indication,
                "date_debut": date_debut,
                "duree_prevue_jours": duree_prevue_jours,
                # Posé même vide : sans lui, la consommation en DDD du bloc 14
                # demanderait de recoder des milliers de lignes (§5).
                "code_atc": code_atc,
                "statut": "active",
                "protocole_code": protocole_code,
                "protocole_version": protocole_version,
                # Posologie d'introduction, écrite une fois et jamais remise à
                # jour : ce qui s'applique un jour donné se lit dans
                # `prescription_posologie`.
                "dose": dose,
                "unite": unite,
                "rythme": rythme,
                "condition_texte": condition_texte,
                "dilution": dilution,
                "nb_ampoules": nb_ampoules,
                "vitesse": vitesse,
                "volume_dilution": volume_dilution,
                "volume_24h": volume_24h,
                "additifs": additifs,
                # L'heure de prise choisie à la ligne (SPEC §5.3) : ce qui a
                # été prescrit reste ce qui s'imprime, même si les horaires
                # standards du service changent plus tard.
                "horaires_override": horaires_override,
            },
            utilisateur_id=utilisateur_id,
        )
        _inserer_posologie(
            base, ligne_id, date_debut,
            {
                "dose": dose, "unite": unite, "rythme": rythme,
                "horaires_override": horaires_override,
                "condition_texte": condition_texte, "dilution": dilution,
                "nb_ampoules": nb_ampoules, "vitesse": vitesse,
                "volume_dilution": volume_dilution, "volume_24h": volume_24h,
                "additifs": additifs,
            },
            motif=None, utilisateur_id=utilisateur_id,
        )
    return ligne_id


def _inserer_posologie(
    base: Base, ligne_id: str, date_debut: str, champs: dict,
    *, motif: str | None, utilisateur_id: str | None,
) -> str:
    valeurs = {c: champs.get(c) for c in dom.CHAMPS_POSOLOGIE}
    valeurs.update({
        "ligne_id": ligne_id, "date_debut": date_debut, "motif_changement": motif,
    })
    return base.inserer("prescription_posologie", valeurs, utilisateur_id=utilisateur_id)


def changer_posologie(
    base: Base,
    ligne_id: str,
    *,
    a_partir_du: str,
    motif: str | None = None,
    utilisateur_id: str | None = None,
    **champs,
) -> str | None:
    """Une nouvelle dose, le même traitement.

    C'est la fonction qui distingue les deux niveaux. Tienam 1 g × 3/j passé à
    500 mg × 3/j à J4 reste le même épisode : le compteur affiche J4, pas J1,
    et la durée d'antibiothérapie court toujours depuis la première dose.
    Avant, il fallait choisir entre modifier la ligne — et perdre la posologie
    initiale — ou en ouvrir une seconde — et fausser la durée. Les deux
    donnaient un chiffre faux au comité des infections.

    Les champs non fournis sont repris de la posologie en cours : on change une
    dose, pas toute la prescription. Rend `None` si rien n'a bougé — une
    version « dose inchangée » n'apprendrait rien à personne et rendrait
    l'historique illisible.
    """
    inconnus = sorted(set(champs) - set(dom.CHAMPS_POSOLOGIE))
    if inconnus:
        # Sans ce refus, `dosee=500` passerait pour un changement de rien du
        # tout : la fonction rendrait None, l'écran dirait « posologie
        # inchangée », et la dose ne changerait jamais.
        raise ValueError(
            f"Champ de posologie inconnu : {', '.join(inconnus)}. "
            f"Attendus : {', '.join(dom.CHAMPS_POSOLOGIE)}."
        )
    with base.transaction():
        courante = dom.posologie_en_vigueur(posologies(base, ligne_id), a_partir_du)
        base_champs = {c: (courante or {}).get(c) for c in dom.CHAMPS_POSOLOGIE}
        nouveaux = {**base_champs, **champs}
        if courante is not None and not dom.posologie_differente(courante, nouveaux):
            return None
        # Une correction saisie le jour même remplace la version du jour au
        # lieu de s'empiler à côté d'elle : deux versions le même jour, c'est
        # une seule posologie appliquée et une ligne d'historique de trop.
        if courante is not None and courante["date_debut"] == a_partir_du:
            base.mettre_a_jour(
                "prescription_posologie", courante["id"],
                {**nouveaux, "motif_changement": motif},
                utilisateur_id=utilisateur_id,
            )
            return courante["id"]
        return _inserer_posologie(
            base, ligne_id, a_partir_du, nouveaux,
            motif=motif, utilisateur_id=utilisateur_id,
        )


def posologies(base: Base, ligne_id: str) -> list[dict]:
    """Toutes les versions d'un épisode, de la première à la dernière."""
    return base.requete(
        "SELECT * FROM prescription_posologie WHERE ligne_id = ? AND supprime = 0 "
        "ORDER BY date_debut, cree_le",
        (ligne_id,),
    )


def posologies_du_sejour(base: Base, sejour_id: str) -> dict[str, list[dict]]:
    """Les versions de tous les épisodes du séjour, par épisode.

    Une seule requête plutôt qu'une par ligne : la pancarte en affiche trente,
    et trente allers-retours à chaque affichage se sentent sur le poste du
    service.
    """
    lignes = base.requete(
        "SELECT p.* FROM prescription_posologie p "
        "JOIN prescription_ligne l ON l.id = p.ligne_id "
        "WHERE l.sejour_id = ? AND p.supprime = 0 AND l.supprime = 0 "
        "ORDER BY p.date_debut, p.cree_le",
        (sejour_id,),
    )
    par_ligne: dict[str, list[dict]] = {}
    for ligne in lignes:
        par_ligne.setdefault(ligne["ligne_id"], []).append(ligne)
    return par_ligne


def modifier_ligne(
    base: Base, ligne_id: str, valeurs: dict, *, utilisateur_id: str | None = None
) -> None:
    """Corrige l'identité d'un épisode : produit, voie, indication, durée
    prévue. Toute ligne — y compris issue d'un protocole — reste modifiable
    sans exception (SPEC §4.5, règle de sécurité 4).

    Refuse les champs de posologie, et c'est le point de la fonction. Écrire
    `{"dose": 500}` ici écraserait la dose initiale sans laisser de trace, et
    la pancarte des jours passés se mettrait à afficher une dose qui n'a jamais
    été donnée ces jours-là. Un changement de dose passe par
    `changer_posologie`, qui ouvre une version datée.
    """
    interdits = sorted(set(valeurs) & set(dom.CHAMPS_POSOLOGIE))
    if interdits:
        raise ValueError(
            f"Posologie modifiée sans version : {', '.join(interdits)}. "
            "Utiliser changer_posologie(a_partir_du=…) pour qu'un changement "
            "de dose reste daté et que la posologie initiale reste lisible."
        )
    base.mettre_a_jour("prescription_ligne", ligne_id, valeurs, utilisateur_id=utilisateur_id)


def arreter_ligne(
    base: Base,
    ligne_id: str,
    *,
    date_arret: str,
    motif_arret: str | None = None,
    utilisateur_id: str | None = None,
) -> None:
    """La ligne reste visible, barrée à l'affichage. Jamais supprimée
    (SPEC §5.1)."""
    base.mettre_a_jour(
        "prescription_ligne",
        ligne_id,
        {"statut": "arretee", "date_arret": date_arret, "motif_arret": motif_arret},
        utilisateur_id=utilisateur_id,
        action="arret",
    )


def horaires_ligne(
    base: Base, ligne_id: str, horaires: str, *,
    a_partir_du: str | None = None, utilisateur_id: str | None = None,
) -> str | None:
    """Horaires modifiables ligne par ligne (SPEC §5.3).

    L'heure de prise fait partie de la posologie : la déplacer ouvre une
    version, comme un changement de dose. Sans date, le changement vaut à
    partir d'aujourd'hui — pas rétroactivement sur des jours où le produit a
    été donné à l'ancienne heure.
    """
    return changer_posologie(
        base, ligne_id,
        a_partir_du=a_partir_du or date.today().isoformat(),
        horaires_override=horaires,
        utilisateur_id=utilisateur_id,
    )


# --------------------------------------------------------------------------
# Lecture de la pancarte à une date donnée
# --------------------------------------------------------------------------

def episodes(base: Base, sejour_id: str) -> list[dict]:
    """Les épisodes de traitement seuls, sans leur posologie.

    Un épisode par traitement, quel que soit le nombre de changements de dose :
    c'est la bonne unité pour compter une durée d'antibiothérapie.
    """
    return base.requete(
        "SELECT * FROM prescription_ligne WHERE sejour_id = ? AND supprime = 0 "
        "ORDER BY voie, cree_le",
        (sejour_id,),
    )


def toutes_les_lignes(
    base: Base, sejour_id: str, a_la_date: str | None = None
) -> list[dict]:
    """Les épisodes du séjour, chacun avec la posologie d'un jour donné.

    Sans date, c'est la dernière posologie connue qui est rendue — celle qui
    court aujourd'hui. Avec une date, c'est celle qui s'appliquait ce jour-là :
    relire la pancarte de J2 doit montrer ce qui a été donné à J2.
    """
    lignes = episodes(base, sejour_id)
    par_ligne = posologies_du_sejour(base, sejour_id)
    reference = a_la_date or date.today().isoformat()
    composees = []
    for ligne in lignes:
        versions = par_ligne.get(ligne["id"], [])
        # Sans date demandée, une ligne introduite demain (contredatée à
        # l'envers, ou pancarte préparée d'avance) n'a pas encore de version
        # « en vigueur » : c'est sa première qui la décrit.
        posologie = dom.posologie_en_vigueur(versions, reference)
        if posologie is None and a_la_date is None and versions:
            posologie = versions[0]
        composees.append(dom.appliquer_posologie(ligne, posologie))
    return composees


def lignes_actives_le(base: Base, sejour_id: str, a_la_date: str) -> list[dict]:
    """Lignes en vigueur ce jour-là, groupées par voie à l'affichage (SPEC
    §5.2) — l'ordre est laissé à l'appelant (UI).

    Chaque ligne porte la posologie de ce jour-là, pas celle d'aujourd'hui.
    """
    return [
        ligne
        for ligne in toutes_les_lignes(base, sejour_id, a_la_date)
        if dom.ligne_active_le(ligne, a_la_date)
    ]


def lignes_par_voie(lignes: list[dict]) -> dict[str, list[dict]]:
    from .. import listes

    groupes: dict[str, list[dict]] = {code: [] for code in listes.ORDRE_VOIES}
    for ligne in lignes:
        groupes.setdefault(ligne["voie"], []).append(ligne)
    return groupes


def pancarte_du_jour(base: Base, sejour_id: str, date_jour: str) -> dict:
    """Tout ce qu'il faut pour afficher/imprimer la pancarte d'un jour :
    lignes actives par voie, étiquettes J{n}, bilan hydrique, bilans
    demandés, allergies en tête."""
    lignes = lignes_actives_le(base, sejour_id, date_jour)
    bilan = dom.volume_entrees_24h(lignes)
    journee = base.une_ligne(
        "SELECT * FROM journee WHERE sejour_id = ? AND date_jour = ? AND supprime = 0",
        (sejour_id, date_jour),
    )
    bilans_demandes = []
    if journee:
        bilans_demandes = base.requete(
            "SELECT * FROM bilan_demande WHERE journee_id = ? AND supprime = 0 "
            "ORDER BY examen_code",
            (journee["id"],),
        )
    return {
        "date_jour": date_jour,
        "lignes": lignes,
        "lignes_par_voie": lignes_par_voie(lignes),
        "bilan_entrees": bilan,
        "journee": journee,
        "bilans_demandes": bilans_demandes,
    }


# --------------------------------------------------------------------------
# Bilans à demander pour le lendemain (SPEC §5.2 bis)
# --------------------------------------------------------------------------

def obtenir_ou_creer_journee(
    base: Base, sejour_id: str, date_jour: str, *, utilisateur_id: str | None = None
) -> dict:
    existante = base.une_ligne(
        "SELECT * FROM journee WHERE sejour_id = ? AND date_jour = ? AND supprime = 0",
        (sejour_id, date_jour),
    )
    if existante:
        return existante
    id_ = base.inserer(
        "journee", {"sejour_id": sejour_id, "date_jour": date_jour}, utilisateur_id=utilisateur_id
    )
    return base.une_ligne("SELECT * FROM journee WHERE id = ?", (id_,))


def definir_bilans_demandes(
    base: Base,
    sejour_id: str,
    date_jour: str,
    examens: list[tuple[str, str]],
    *,
    utilisateur_id: str | None = None,
) -> None:
    """`examens` : liste de (code_examen, heure_prelevement)."""
    with base.transaction():
        journee = obtenir_ou_creer_journee(base, sejour_id, date_jour, utilisateur_id=utilisateur_id)
        base.executer(
            "UPDATE bilan_demande SET supprime = 1 WHERE journee_id = ?", (journee["id"],)
        )
        for code, heure in examens:
            deja = base.une_ligne(
                "SELECT id FROM bilan_demande WHERE journee_id = ? AND examen_code = ?",
                (journee["id"], code),
            )
            if deja:
                base.mettre_a_jour(
                    "bilan_demande",
                    deja["id"],
                    {"supprime": 0, "heure_prelevement": heure},
                    utilisateur_id=utilisateur_id,
                )
            else:
                base.inserer(
                    "bilan_demande",
                    {"journee_id": journee["id"], "examen_code": code, "heure_prelevement": heure},
                    utilisateur_id=utilisateur_id,
                )


# --------------------------------------------------------------------------
# « Préparer la pancarte de demain » (SPEC §5.5) — la fonction la plus
# importante du logiciel.
# --------------------------------------------------------------------------

def etat_journee(base: Base, sejour_id: str, date_jour: str) -> dict | None:
    """L'état de préparation/validation d'une journée, sans recalculer toute
    la pancarte — sert à décider si un bouton d'impression doit être actif."""
    return base.une_ligne(
        "SELECT * FROM journee WHERE sejour_id = ? AND date_jour = ? AND supprime = 0",
        (sejour_id, date_jour),
    )


def preparer_pancarte_de_demain(
    base: Base, sejour_id: str, *, aujourdhui: str | None = None, utilisateur_id: str | None = None
) -> dict:
    """Ne duplique rien : crée simplement la `journee` du lendemain, prête à
    recevoir les bilans à demander. Les lignes actives, les compteurs
    avancés et les échéances signalées se calculent à l'affichage
    (`pancarte_du_jour`) — c'est ce qui garantit qu'il n'existe jamais deux
    versions divergentes d'une même ligne (règle de conception 5)."""
    demain = str(lendemain(aujourdhui))
    journee = obtenir_ou_creer_journee(base, sejour_id, demain, utilisateur_id=utilisateur_id)
    base.mettre_a_jour(
        "journee",
        journee["id"],
        {"preparee_le": base.__class__.__module__ and _maintenant()},
        utilisateur_id=utilisateur_id,
        action="preparation_pancarte",
    )
    return pancarte_du_jour(base, sejour_id, demain)


def valider_pancarte_de_demain(
    base: Base, sejour_id: str, *, aujourdhui: str | None = None, utilisateur_id: str | None = None
) -> dict:
    """Une relecture avant impression, distincte de la préparation.

    Préparer ne fait que reconduire les lignes actives — un geste mécanique.
    Valider dit que quelqu'un a relu le résultat avant que la feuille ne soit
    imprimable : sur demande du service, l'impression de la pancarte du
    lendemain reste bloquée tant que cette étape n'a pas eu lieu.
    """
    demain = str(lendemain(aujourdhui))
    journee = base.une_ligne(
        "SELECT * FROM journee WHERE sejour_id = ? AND date_jour = ? AND supprime = 0",
        (sejour_id, demain),
    )
    if journee is None:
        raise ValueError("La pancarte du lendemain n'a pas encore été préparée.")
    base.mettre_a_jour(
        "journee", journee["id"], {"validee_le": _maintenant(), "validee_par": utilisateur_id},
        utilisateur_id=utilisateur_id, action="validation_pancarte",
    )
    return pancarte_du_jour(base, sejour_id, demain)


def _maintenant() -> str:
    from ..db import maintenant

    return maintenant()


def lignes_echues(base: Base, sejour_id: str, a_la_date: str) -> list[dict]:
    """Lignes actives dont la durée prévue est dépassée — à signaler
    visuellement, jamais arrêtées automatiquement (SPEC §5.5)."""
    return [
        ligne
        for ligne in lignes_actives_le(base, sejour_id, a_la_date)
        if dom.etiquette_jour(ligne, a_la_date).echue
    ]


def pancarte_preparee(base: Base, sejour_id: str, date_jour: str) -> bool:
    """La pancarte de ce jour a-t-elle été préparée ?

    `etat_journee` rend la ligne entière ; cette question-ci n'en veut que la
    réponse, et c'est la seule dont le tableau des lits ait besoin pour dire
    quels lits restent à préparer.
    """
    journee = etat_journee(base, sejour_id, date_jour)
    return bool(journee and journee["preparee_le"])
