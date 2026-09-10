"""Écrans 2 (Admission) et 7 (Sortie) — SPEC §4.1 à §4.7."""

from __future__ import annotations

from datetime import date

from .. import listes
from ..db import Base, maintenant


# --------------------------------------------------------------------------
# Identité et admission
# --------------------------------------------------------------------------

def creer_patient(
    base: Base,
    *,
    matricule: str,
    nom_affichage: str,
    date_naissance: str | None,
    sexe: str = "non_renseigne",
    groupe_sanguin: str | None = None,
    utilisateur_id: str | None = None,
    non_identifie: bool = False,
) -> str:
    # L'identifiant d'étude est cherché et écrit dans la même transaction :
    # sinon deux admissions simultanées reçoivent le même (deux onglets
    # suffisent, Streamlit sert chacun dans son propre fil).
    with base.transaction():
        if non_identifie:
            # Le matricule proposé à l'écran peut avoir été pris entre-temps.
            matricule = _suffixe_libre(
                base, "matricule", matricule.rsplit("-", 1)[0] + "-%d",
                int(matricule.rsplit("-", 1)[-1]) if matricule.rsplit("-", 1)[-1].isdigit() else 1,
            )
        return base.inserer(
            "patient",
            {
                "matricule": matricule,
                "nom_affichage": nom_affichage,
                "date_naissance": date_naissance,
                "sexe": sexe,
                "groupe_sanguin": None if groupe_sanguin in (None, "non_renseigne")
                                  else groupe_sanguin,
                "non_identifie": int(non_identifie),
                "identifiant_etude": _nouvel_identifiant_etude(base),
            },
            utilisateur_id=utilisateur_id,
        )


def modifier_identite(
    base: Base,
    patient_id: str,
    *,
    matricule: str,
    nom_affichage: str,
    date_naissance: str | None,
    sexe: str,
    groupe_sanguin: str | None,
    utilisateur_id: str | None = None,
) -> None:
    """Corrige une erreur de saisie à l'admission (matricule, nom, date de
    naissance, sexe, groupe).

    Ce n'est pas une nouvelle admission : la ligne existante est mise à jour,
    jamais recréée (règle de conception 2 — pas de suppression physique).
    Le journal garde qui a corrigé, quand, et vers quelles valeurs ; c'est ce
    qui distingue une correction tracée d'une donnée simplement écrasée.
    """
    base.mettre_a_jour(
        "patient",
        patient_id,
        {
            "matricule": matricule,
            "nom_affichage": nom_affichage,
            "date_naissance": date_naissance,
            "sexe": sexe,
            "groupe_sanguin": None if groupe_sanguin in (None, "non_renseigne")
                              else groupe_sanguin,
        },
        utilisateur_id=utilisateur_id,
        action="correction",
    )


def modifier_admission(
    base: Base,
    sejour_id: str,
    *,
    date_admission: str,
    provenance_type: str | None,
    provenance_detail: str | None,
    poids_kg: float | None,
    taille_cm: float | None,
    creatinine_base: float | None,
    type_admission: str | None,
    maladie_chronique_igs2: str | None,
    traumatique: bool,
    glasgow_initial: int | None = None,
    regions_traumatiques_choisies: list[str] | None = None,
    regions_traumatiques_precisions: dict[str, str] | None = None,
    mecanisme: str | None = None,
    mecanisme_detail: str | None = None,
    motif_principal: str | None = None,
    motifs_associes: list[str] | None = None,
    utilisateur_id: str | None = None,
) -> None:
    """Corrige les circonstances de l'admission.

    Couvre aussi le cas où le motif a été coché du mauvais côté (traumatique
    / non traumatique) à l'admission : les régions de l'autre catégorie sont
    effacées, pas laissées à traîner en double. `motifs_associes` reste pris
    en compte même quand `traumatique` est vrai : un traumatisme thoracique
    peut être associé à une embolie pulmonaire, un SDRA, une acidocétose
    diabétique — ce sont des motifs non traumatiques associés, pas le motif
    principal, que la région traumatique tient déjà.

    Le lit n'est volontairement pas modifiable ici — changer de lit est un
    transfert (`changer_de_lit`), pas une correction d'erreur de saisie ; les
    deux n'ont ni la même trace attendue ni les mêmes contrôles.
    """
    # Trois écritures pour une seule correction : le séjour, ses régions, ses
    # motifs. À moitié appliquée, elle laisserait un séjour dont la catégorie
    # ne correspond plus aux motifs qui y sont accrochés.
    with base.transaction():
        base.mettre_a_jour(
            "sejour",
            sejour_id,
            {
                "date_admission": date_admission,
                "provenance_type": provenance_type,
                "provenance_detail": provenance_detail,
                "poids_kg": poids_kg,
                "taille_cm": taille_cm,
                "creatinine_base": creatinine_base,
                "type_admission": type_admission,
                "maladie_chronique_igs2": maladie_chronique_igs2,
                "glasgow_initial": glasgow_initial,
                "traumatique": int(traumatique),
                "mecanisme": mecanisme if traumatique else None,
                "mecanisme_detail": mecanisme_detail if traumatique else None,
            },
            utilisateur_id=utilisateur_id,
            action="correction",
        )
        if traumatique:
            definir_regions_traumatiques(
                base, sejour_id, regions_traumatiques_choisies or [],
                precisions=regions_traumatiques_precisions, utilisateur_id=utilisateur_id,
            )
            # Pas de motif non traumatique "principal" — la région tient ce
            # rôle — mais les motifs associés (complications) restent posés.
            definir_motifs(
                base, sejour_id, motif_principal=None,
                motifs_associes=motifs_associes, utilisateur_id=utilisateur_id,
            )
        else:
            definir_regions_traumatiques(base, sejour_id, [], utilisateur_id=utilisateur_id)
            definir_motifs(
                base, sejour_id, motif_principal=motif_principal,
                motifs_associes=motifs_associes, utilisateur_id=utilisateur_id,
            )


def _suffixe_libre(base: Base, colonne: str, gabarit: str, depart: int) -> str:
    """Premier `gabarit % n` (à partir de `depart`) que `patient.colonne` ne
    porte pas encore.

    À n'appeler que dans une transaction : c'est elle qui garantit qu'aucune
    autre écriture ne prend la valeur entre le moment où on la trouve libre et
    celui où on l'écrit.
    """
    n = max(depart, 1)
    while base.une_ligne(
        f"SELECT 1 AS x FROM patient WHERE {colonne} = ?", (gabarit % n,)
    ):
        n += 1
    return gabarit % n


def _nouvel_identifiant_etude(base: Base) -> str:
    """Identifiant stable, sans lien direct avec le matricule (règle de
    conception 8 — export recherche pseudonymisé automatiquement).

    Se déduit du plus grand déjà attribué, puis du premier libre à partir de
    là. Un comptage des lignes donnait le bon résultat tant que rien n'est
    jamais effacé pour de bon — ce qui est le cas aujourd'hui (règle de
    conception 2) — mais ne le dit pas, et redevient faux le jour où une ligne
    est écrite ou reprise autrement. La recherche du premier libre, elle, tient
    la contrainte d'unicité du schéma quoi qu'il arrive.
    """
    dernier = base.une_ligne(
        "SELECT MAX(CAST(SUBSTR(identifiant_etude, 5) AS INTEGER)) AS n FROM patient "
        "WHERE identifiant_etude LIKE 'ETU-%'"
    )
    return _suffixe_libre(base, "identifiant_etude", "ETU-%05d", ((dernier or {}).get("n") or 0) + 1)


def prochain_matricule_non_identifie(base: Base) -> str:
    """SPEC §4.1 : `XXX-{date}-{n}`.

    Proposé à l'écran, puis réattribué au moment de l'écriture (voir
    `creer_patient`) : entre l'affichage et la validation du formulaire, un
    autre poste a pu prendre le numéro.
    """
    aujourdhui = date.today().strftime("%Y%m%d")
    prefixe = f"XXX-{aujourdhui}-"
    dernier = base.une_ligne(
        "SELECT MAX(CAST(SUBSTR(matricule, ?) AS INTEGER)) AS n FROM patient "
        "WHERE matricule LIKE ?",
        (len(prefixe) + 1, f"{prefixe}%"),
    )
    return _suffixe_libre(
        base, "matricule", f"{prefixe}%d", ((dernier or {}).get("n") or 0) + 1
    )


def creer_sejour(
    base: Base,
    *,
    patient_id: str,
    date_admission: str,
    lit_admission: int,
    provenance_type: str | None = None,
    provenance_detail: str | None = None,
    est_readmission: bool = False,
    motif_readmission: str | None = None,
    traumatique: bool | None = None,
    mecanisme: str | None = None,
    mecanisme_detail: str | None = None,
    creatinine_base: float | None = None,
    poids_kg: float | None = None,
    taille_cm: float | None = None,
    type_admission: str | None = None,
    maladie_chronique_igs2: str | None = None,
    glasgow_initial: int | None = None,
    utilisateur_id: str | None = None,
) -> str:
    with base.transaction():
        # Le plus grand numéro déjà donné, pas le nombre de séjours : c'est ce
        # que « deuxième séjour de ce patient » veut dire, et ça reste juste si
        # un séjour est un jour repris ou importé hors de cette fonction.
        numero = (base.une_ligne(
            "SELECT MAX(numero_sejour) AS n FROM sejour WHERE patient_id = ?", (patient_id,)
        ) or {}).get("n") or 0
        numero += 1
        return base.inserer(
            "sejour",
            {
                "patient_id": patient_id,
                "numero_sejour": numero,
                "date_admission": date_admission,
                "lit_admission": lit_admission,
                "provenance_type": provenance_type,
                "provenance_detail": provenance_detail,
                "type_admission": type_admission,
                "maladie_chronique_igs2": maladie_chronique_igs2,
                "est_readmission": int(est_readmission),
                "motif_readmission": motif_readmission,
                "traumatique": None if traumatique is None else int(traumatique),
                "mecanisme": mecanisme,
                "mecanisme_detail": mecanisme_detail,
                # Poids : sans lui, pas de clairance de la créatinine.
                "poids_kg": poids_kg,
                "taille_cm": taille_cm,
                # Créatinine antérieure : sans elle KDIGO est incalculable (§5).
                "creatinine_base": creatinine_base,
                # Glasgow d'arrivée : à J3 sous midazolam, personne ne sait
                # plus s'il est arrivé à 15 ou à 6.
                "glasgow_initial": glasgow_initial,
                "complication_statut": "non_renseigne",
            },
            utilisateur_id=utilisateur_id,
        )


def sejour_avec_patient(base: Base, sejour_id: str) -> dict | None:
    return base.une_ligne(
        """
        SELECT s.*, p.nom_affichage, p.date_naissance, p.matricule, p.sexe,
               p.traitement_habituel, p.sans_antecedent_connu,
               p.groupe_sanguin
        FROM sejour s JOIN patient p ON p.id = s.patient_id
        WHERE s.id = ?
        """,
        (sejour_id,),
    )


# --------------------------------------------------------------------------
# Motif traumatique — régions et statut polytraumatisé (SPEC §4.3)
# --------------------------------------------------------------------------

def definir_regions_traumatiques(
    base: Base,
    sejour_id: str,
    regions: list[str],
    *,
    precisions: dict[str, str] | None = None,
    utilisateur_id: str | None = None,
) -> None:
    precisions = precisions or {}
    with base.transaction():
        base.executer(
            "UPDATE sejour_region_trauma SET supprime = 1 WHERE sejour_id = ?", (sejour_id,)
        )
        for region in regions:
            precision = precisions.get(region)
            existe = base.une_ligne(
                "SELECT id FROM sejour_region_trauma WHERE sejour_id = ? AND region = ?",
                (sejour_id, region),
            )
            if existe:
                base.mettre_a_jour(
                    "sejour_region_trauma", existe["id"],
                    {"supprime": 0, "precision": precision},
                    utilisateur_id=utilisateur_id,
                )
            else:
                base.inserer(
                    "sejour_region_trauma",
                    {"sejour_id": sejour_id, "region": region, "precision": precision},
                    utilisateur_id=utilisateur_id,
                )


def regions_traumatiques(base: Base, sejour_id: str) -> list[str]:
    lignes = base.requete(
        "SELECT region FROM sejour_region_trauma WHERE sejour_id = ? AND supprime = 0",
        (sejour_id,),
    )
    return [l["region"] for l in lignes]


def regions_traumatiques_detail(base: Base, sejour_id: str) -> list[dict]:
    """Région et précision, pour l'affichage et la fiche imprimée — contrairement
    à `regions_traumatiques()`, qui ne sert qu'au calcul du polytraumatisme."""
    return base.requete(
        "SELECT region, precision FROM sejour_region_trauma "
        "WHERE sejour_id = ? AND supprime = 0 ORDER BY cree_le",
        (sejour_id,),
    )


def est_polytraumatise(base: Base, sejour_id: str) -> bool:
    """Calculé automatiquement, jamais saisi (SPEC §4.3) : >= 2 régions."""
    return len(regions_traumatiques(base, sejour_id)) >= 2


# --------------------------------------------------------------------------
# Motif non traumatique (SPEC §4.4)
# --------------------------------------------------------------------------

def definir_motifs(
    base: Base,
    sejour_id: str,
    *,
    motif_principal: str | None,
    motifs_associes: list[str] | None = None,
    precisions: dict[str, dict] | None = None,
    utilisateur_id: str | None = None,
) -> None:
    """`motif_principal=None` efface les motifs principaux sans en reposer —
    c'est ce dont un séjour traumatique a besoin : la région atteinte tient
    lieu de motif principal, mais un motif non traumatique peut s'y associer
    (un traumatisme thoracique associé à une embolie pulmonaire, un SDRA, une
    acidocétose diabétique). `motifs_associes` reste donc pris en compte même
    sans motif principal — seul `motif_principal=None` et
    `motifs_associes` vide efface tout sans rien reposer.
    """
    import json

    with base.transaction():
        base.executer("UPDATE sejour_motif SET supprime = 1 WHERE sejour_id = ?", (sejour_id,))
        if motif_principal is None and not motifs_associes:
            return
        precisions = precisions or {}
        tous = (
            ([(motif_principal, True)] if motif_principal else [])
            + [(m, False) for m in (motifs_associes or [])]
        )
        for code, principal in tous:
            base.inserer(
                "sejour_motif",
                {
                    "sejour_id": sejour_id,
                    "code": code,
                    "principal": int(principal),
                    "donnees": json.dumps(precisions.get(code, {}), ensure_ascii=False),
                },
                utilisateur_id=utilisateur_id,
            )


def motifs_du_sejour(base: Base, sejour_id: str) -> list[dict]:
    return base.requete(
        "SELECT * FROM sejour_motif WHERE sejour_id = ? AND supprime = 0 ORDER BY principal DESC",
        (sejour_id,),
    )


# --------------------------------------------------------------------------
# Antécédents (SPEC §4.2) — attachés au patient
# --------------------------------------------------------------------------

def ajouter_antecedent(
    base: Base,
    *,
    patient_id: str,
    categorie: str,
    libelle: str,
    code: str | None = None,
    code_icd10: str | None = None,
    precision: str | None = None,
    quantification_valeur: float | None = None,
    quantification_unite: str | None = None,
    statut: str = "present",
    utilisateur_id: str | None = None,
) -> str:
    return base.inserer(
        "antecedent",
        {
            "patient_id": patient_id,
            "categorie": categorie,
            "code": code,
            "libelle": libelle,
            "code_icd10": code_icd10,
            "precision": precision,
            "quantification_valeur": quantification_valeur,
            "quantification_unite": quantification_unite,
            "statut": statut,
        },
        utilisateur_id=utilisateur_id,
    )


def supprimer_antecedent(
    base: Base, antecedent_id: str, *, utilisateur_id: str | None = None
) -> None:
    """Retire un antécédent saisi par erreur (demande du service, 8 septembre).

    Suppression logique, jamais physique (règle de conception 2) : la ligne
    reste en base avec `supprime = 1`, et le journal garde qui l'a retirée et
    quand. Un antécédent faux doit pouvoir disparaître de la feuille imprimée
    — sans quoi il se recopie de garde en garde.
    """
    base.supprimer_logiquement("antecedent", antecedent_id, utilisateur_id=utilisateur_id)


def antecedents_du_patient(base: Base, patient_id: str) -> list[dict]:
    """N'inclut jamais la catégorie `evaluation` (§4.2 bis) : c'est une note
    interne sur l'état de l'interrogatoire, pas un antécédent à afficher."""
    return base.requete(
        "SELECT * FROM antecedent WHERE patient_id = ? AND categorie != 'evaluation' "
        "AND supprime = 0 ORDER BY cree_le",
        (patient_id,),
    )


# --------------------------------------------------------------------------
# « Le patient a-t-il des antécédents ? » Oui / Non / Inconnu (SPEC §4.2 bis)
# --------------------------------------------------------------------------
#
# Case « Sans antécédent connu » de la SPEC : distincte de « jamais demandé »
# (trois états, comme partout ailleurs dans ce logiciel). Dès qu'un antécédent
# réel est ajouté, cette note devient caduque et est retirée — elle ne doit
# jamais contredire une entrée réelle.

def definir_etat_antecedents(
    base: Base, patient_id: str, etat: str, *, utilisateur_id: str | None = None
) -> None:
    if etat not in ("absent", "non_renseigne"):
        raise ValueError("etat doit être 'absent' ou 'non_renseigne'")
    # Get-or-create dans une transaction, sinon deux fils créent tous les deux :
    # là où un index unique existe, le second échoue et l'écriture est perdue ;
    # là où il n'y en a pas, le doublon passe **en silence**, ce qui est pire.
    # `antecedent` ne porte **aucun** index unique sur (patient, evaluation) :
    # deux évaluations créées en même temps se seraient rangées côte à côte
    # sans que rien ne le signale.
    with base.transaction():
        existante = base.une_ligne(
            "SELECT id FROM antecedent WHERE patient_id = ? AND categorie = 'evaluation' "
            "AND supprime = 0",
            (patient_id,),
        )
        if existante:
            base.mettre_a_jour(
                "antecedent", existante["id"], {"statut": etat},
                utilisateur_id=utilisateur_id,
            )
        else:
            base.inserer(
                "antecedent",
                {
                    "patient_id": patient_id,
                    "categorie": "evaluation",
                    "libelle": "Interrogatoire des antécédents",
                    "statut": etat,
                },
                utilisateur_id=utilisateur_id,
            )


def etat_antecedents(base: Base, patient_id: str) -> str:
    """'oui' dès qu'un antécédent réel existe ; sinon la réponse déclarée
    ('absent' / 'non_renseigne') ; 'non_renseigne' si jamais demandé."""
    if antecedents_du_patient(base, patient_id):
        return "oui"
    evaluation = base.une_ligne(
        "SELECT statut FROM antecedent WHERE patient_id = ? AND categorie = 'evaluation' "
        "AND supprime = 0",
        (patient_id,),
    )
    return evaluation["statut"] if evaluation else "non_renseigne"


def allergies_du_patient(base: Base, patient_id: str) -> list[dict]:
    """Affichées en alerte rouge en haut de la pancarte (SPEC §4.2)."""
    return [
        a
        for a in antecedents_du_patient(base, patient_id)
        if a["categorie"] == "allergie" and a["statut"] == "present"
    ]


# --------------------------------------------------------------------------
# Interventions chirurgicales (SPEC §4.6)
# --------------------------------------------------------------------------

def ajouter_intervention(
    base: Base,
    *,
    sejour_id: str,
    date_acte: str,
    geste: str,
    geste_detail: str | None = None,
    est_reprise: bool = False,
    utilisateur_id: str | None = None,
) -> str:
    return base.inserer(
        "intervention",
        {
            "sejour_id": sejour_id,
            "date_acte": date_acte,
            "geste": geste,
            "geste_detail": geste_detail,
            "est_reprise": int(est_reprise),
            "complication_statut": "non_renseigne",  # jamais "aucune" par défaut — SPEC §4.6
        },
        utilisateur_id=utilisateur_id,
    )


def interventions_du_sejour(base: Base, sejour_id: str) -> list[dict]:
    return base.requete(
        "SELECT * FROM intervention WHERE sejour_id = ? AND supprime = 0 ORDER BY date_acte",
        (sejour_id,),
    )


# --------------------------------------------------------------------------
# Changement de lit
# --------------------------------------------------------------------------

def changer_de_lit(
    base: Base, sejour_id: str, nouveau_lit: int, *, utilisateur_id: str | None = None
) -> None:
    """Transfère un séjour vers un autre lit.

    Met à jour `sejour.lit_admission` — c'est ce champ que
    `lits.etat_des_lits()` lit pour savoir qui occupe quel lit, malgré son nom.
    Sans cette mise à jour, un transfert restait invisible : le patient
    continuait d'apparaître dans son ancien lit, et le nouveau restait affiché
    comme libre. `sejour_lit` garde l'historique (durée passée dans chaque
    lit), il ne sert pas à l'affichage courant.
    """
    with base.transaction():
        occupe = base.une_ligne(
            "SELECT id FROM sejour WHERE lit_admission = ? AND date_sortie IS NULL "
            "AND supprime = 0 AND id != ?",
            (nouveau_lit, sejour_id),
        )
        if occupe:
            raise ValueError(f"Le lit {nouveau_lit} est déjà occupé.")
        en_cours = base.une_ligne(
            "SELECT id FROM sejour_lit WHERE sejour_id = ? AND date_fin IS NULL", (sejour_id,)
        )
        if en_cours:
            base.mettre_a_jour(
                "sejour_lit", en_cours["id"], {"date_fin": maintenant()}, utilisateur_id=utilisateur_id
            )
        base.inserer(
            "sejour_lit",
            {"sejour_id": sejour_id, "lit": nouveau_lit, "date_debut": maintenant()},
            utilisateur_id=utilisateur_id,
        )
        base.mettre_a_jour(
            "sejour", sejour_id, {"lit_admission": nouveau_lit},
            utilisateur_id=utilisateur_id, action="transfert",
        )


# --------------------------------------------------------------------------
# Sortie (SPEC §4.7) — clôture le séjour et libère le lit
# --------------------------------------------------------------------------

def cloturer_sejour(
    base: Base,
    sejour_id: str,
    *,
    date_heure_sortie: str,
    mode_sortie: str,
    destination: str | None = None,
    meme_etablissement: bool | None = None,
    complication_statut: str = "non_renseigne",
    complication_texte: str | None = None,
    ordonnance_sortie: str | None = None,
    consultation_externe: str | None = None,
    deces_reanimation: bool | None = None,
    utilisateur_id: str | None = None,
) -> None:
    if mode_sortie == "deces" and deces_reanimation is None:
        deces_reanimation = True
    base.mettre_a_jour(
        "sejour",
        sejour_id,
        {
            "date_sortie": date_heure_sortie,
            "mode_sortie": mode_sortie,
            "destination": destination,
            "meme_etablissement": None if meme_etablissement is None else int(meme_etablissement),
            "complication_statut": complication_statut,
            "complication_texte": complication_texte,
            "ordonnance_sortie": ordonnance_sortie,
            "consultation_externe": consultation_externe,
            "deces_reanimation": None if deces_reanimation is None else int(deces_reanimation),
        },
        utilisateur_id=utilisateur_id,
        action="sortie",
    )


# --------------------------------------------------------------------------
# Compte rendu de sortie (SPEC §4.7) — généré, bouton « copier »
# --------------------------------------------------------------------------

def compte_rendu_sortie(base: Base, sejour_id: str) -> str:
    from ..domaine.dates import duree_sejour_jours, format_date_fr

    sejour = sejour_avec_patient(base, sejour_id)
    duree = duree_sejour_jours(sejour["date_admission"], sejour.get("date_sortie"))

    lignes = [f"{sejour['nom_affichage']} — matricule {sejour['matricule']}"]

    date_admission_fr = format_date_fr(sejour["date_admission"])
    date_sortie_fr = format_date_fr(sejour.get("date_sortie")) if sejour.get("date_sortie") else "en cours"
    lignes.append(f"Séjour du {date_admission_fr} au {date_sortie_fr} — {duree} jours")

    provenance = listes.libelle(listes.PROVENANCES, sejour["provenance_type"], "non renseignée")
    if sejour["provenance_detail"]:
        provenance += f" ({sejour['provenance_detail']})"
    lignes.append(f"Admis de {provenance}")

    if sejour["traumatique"]:
        regions = regions_traumatiques(base, sejour_id)
        libelles_regions = [listes.libelle(listes.REGIONS_TRAUMATIQUES, r) for r in regions]
        mecanisme = listes.libelle(listes.MECANISMES, sejour["mecanisme"], "")
        motif = f"polytraumatisme ({mecanisme})" if est_polytraumatise(base, sejour_id) else " / ".join(libelles_regions)
        lignes.append(f"Motif : {motif or 'traumatique — région non précisée'}")
    else:
        motifs = motifs_du_sejour(base, sejour_id)
        principal = next((m for m in motifs if m["principal"]), None)
        if principal:
            lignes.append(f"Motif : {listes.libelle_motif(principal['code'])}")

    from . import dispositifs as dispositifs_service

    intubations = [
        d for d in dispositifs_service.du_sejour(base, sejour_id) if d["type"] == "intubation"
    ]
    for v in reversed(intubations):
        fin = format_date_fr(v["date_retrait"]) if v["date_retrait"] else "en cours"
        lignes.append(f"Ventilation du {format_date_fr(v['date_pose'])} au {fin}")
    if intubations:
        total = dispositifs_service.duree_ventilation_jours(base, sejour_id)
        lignes.append(f"Durée totale de ventilation : {total} jours")

    if sejour["complication_statut"] == "presente" and sejour["complication_texte"]:
        lignes.append(f"Compliqué de : {sejour['complication_texte']}")
    elif sejour["complication_statut"] == "aucune":
        lignes.append("Sans complication rapportée")

    mode = listes.libelle(listes.MODES_SORTIE, sejour.get("mode_sortie"), "")
    destination = sejour["destination"] or ""
    meme_etab = " (même établissement)" if sejour["meme_etablissement"] else ""
    if sejour.get("mode_sortie") == "deces":
        lignes.append("Décès en réanimation")
    elif destination:
        lignes.append(f"Sortie vers {destination}{meme_etab} le {date_sortie_fr}")
    else:
        lignes.append(f"Sortie — {mode} le {date_sortie_fr}")

    if sejour["ordonnance_sortie"]:
        lignes.append(f"Traitement : {sejour['ordonnance_sortie']}")
    if sejour["consultation_externe"]:
        lignes.append(f"Consultation : {sejour['consultation_externe']}")

    return "\n".join(lignes)
