"""Listes codées (SPEC §4).

Chaque valeur a un **code stable** et un libellé affiché. Le code est ce qui
part en base et en export ; le libellé peut être réécrit sans casser les
statistiques déjà produites. Rien dans le programme ne doit stocker un libellé.
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# Utilisateurs (SPEC §1.2)
# --------------------------------------------------------------------------
ROLES = (
    ("interne", "Interne"),
    ("resident", "Résident"),
    ("senior", "Senior"),
)

# --------------------------------------------------------------------------
# Trois états explicites (règle de conception 7)
# --------------------------------------------------------------------------
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

# --------------------------------------------------------------------------
# Identité et séjour (SPEC §4.1)
# --------------------------------------------------------------------------
SEXES = (
    ("M", "Masculin"),
    ("F", "Féminin"),
    ("non_renseigne", "Non renseigné"),
)

PROVENANCES = (
    ("urgences", "Urgences"),
    ("service", "Service (préciser)"),
    ("bloc", "Bloc opératoire"),
    ("consultation_ar", "Consultation externe A-R"),
    ("autre_hopital", "Autre hôpital"),
    ("domicile", "Domicile"),
)
# Provenances qui appellent un détail écrit (nom du service, de l'hôpital).
PROVENANCES_AVEC_DETAIL = ("service", "autre_hopital")

MODES_SORTIE = (
    ("domicile", "Domicile"),
    ("transfert_service", "Transfert vers un service (préciser)"),
    ("transfert_hopital", "Transfert vers un autre hôpital"),
    ("reeducation", "Rééducation"),
    ("contre_avis", "Sortie contre avis médical"),
    ("deces", "Décès"),
)

# --------------------------------------------------------------------------
# Antécédents (SPEC §4.2)
# --------------------------------------------------------------------------
CATEGORIES_ANTECEDENT = (
    ("personnel", "Personnel"),
    ("familial", "Familial"),
    ("chirurgical", "Chirurgical"),
    ("allergie", "Allergie"),
    ("habitude", "Habitude de vie"),
)

# Liste courte en accès direct — à valider par un senior (SPEC §4.2).
ANTECEDENTS_COURTS = (
    ("hta", "HTA", "personnel"),
    ("diabete_2", "Diabète type 2", "personnel"),
    ("diabete_1", "Diabète type 1", "personnel"),
    ("cardiopathie_ischemique", "Cardiopathie ischémique", "personnel"),
    ("insuffisance_cardiaque", "Insuffisance cardiaque", "personnel"),
    ("bpco", "BPCO", "personnel"),
    ("asthme", "Asthme", "personnel"),
    ("irc", "Insuffisance rénale chronique", "personnel"),
    ("cirrhose", "Cirrhose", "personnel"),
    ("avc", "AVC", "personnel"),
    ("tabagisme", "Tabagisme", "habitude"),
    ("ethylisme", "Éthylisme", "habitude"),
    ("anticoagulant", "Anticoagulant au long cours", "personnel"),
    ("antiagregant", "Antiagrégant", "personnel"),
)

# Conditions chroniques alignées sur le dictionnaire ANZICS (SPEC §9.5).
# Elles ne remplacent pas les antécédents : elles les résument en sept
# catégories comparables à la littérature internationale.
CONDITIONS_CHRONIQUES = (
    ("respiratoire", "Insuffisance respiratoire chronique"),
    ("cardiovasculaire", "Insuffisance cardiovasculaire chronique"),
    ("renale", "Insuffisance rénale chronique"),
    ("hepatique", "Insuffisance hépatique chronique"),
    ("immunosuppression", "Immunosuppression"),
    ("cancer", "Cancer (dont hémopathie)"),
    ("diabete", "Diabète"),
    ("aucune", "Aucune de ces conditions"),
)

# --------------------------------------------------------------------------
# Motif traumatique (SPEC §4.3)
# --------------------------------------------------------------------------
REGIONS_TRAUMATIQUES = (
    ("cranien", "Traumatisme crânien"),
    ("thoracique", "Traumatisme thoracique"),
    ("abdominal", "Traumatisme abdominal"),
    ("pelvien", "Traumatisme pelvien"),
    ("peripherique", "Traumatisme périphérique (massif facial, membres, rachis)"),
)

MECANISMES = (
    ("avp_deux_roues", "AVP deux-roues"),
    ("avp_quatre_roues", "AVP quatre-roues"),
    ("avp_pieton", "AVP piéton"),
    ("chute_hauteur", "Chute de sa hauteur"),
    ("chute_lieu_eleve", "Chute d'un lieu élevé (préciser hauteur)"),
    ("arme_blanche", "Agression par arme blanche"),
    ("arme_a_feu", "Agression par arme à feu"),
    ("contondante", "Agression contondante"),
    ("accident_travail", "Accident de travail"),
    ("accident_domestique", "Accident domestique"),
    ("sport", "Sport"),
    ("ecrasement", "Écrasement / ensevelissement"),
    ("blast", "Blast / explosion"),
    ("autre", "Autre"),
    ("non_renseigne", "Non renseigné"),
)
MECANISMES_AVEC_DETAIL = ("chute_lieu_eleve", "autre")

# --------------------------------------------------------------------------
# Motif non traumatique (SPEC §4.4)
# --------------------------------------------------------------------------
# Structure : groupe → (code, libellé, champs de précision attendus).
MOTIFS_NON_TRAUMATIQUES: dict[str, tuple[tuple[str, str, tuple[str, ...]], ...]] = {
    "Défaillance circulatoire": (
        ("choc_septique", "Choc septique", ("porte_entree",)),
        ("choc_hemorragique", "Choc hémorragique non traumatique", ()),
        ("choc_cardiogenique", "Choc cardiogénique", ()),
        ("choc_anaphylactique", "Choc anaphylactique", ()),
        ("choc_obstructif", "Choc obstructif", ()),
    ),
    "Défaillance respiratoire": (
        ("sdra", "SDRA", ()),
        ("pneumopathie_grave", "Pneumopathie grave", ()),
        ("decompensation_bpco", "Décompensation de BPCO", ()),
        ("oap_cardiogenique", "OAP cardiogénique", ()),
        ("embolie_pulmonaire", "Embolie pulmonaire", ()),
        ("inhalation", "Inhalation", ()),
        ("obstruction_vas", "Obstruction des voies aériennes", ()),
    ),
    "Défaillance neurologique": (
        ("avc_ischemique", "AVC ischémique", ()),
        ("avc_hemorragique", "AVC hémorragique", ()),
        ("hemorragie_meningee", "Hémorragie méningée", ()),
        ("etat_de_mal", "État de mal épileptique", ()),
        ("meningo_encephalite", "Méningo-encéphalite", ()),
        ("coma_metabolique", "Coma métabolique", ()),
        ("coma_toxique", "Coma toxique", ()),
    ),
    "Postopératoire": (
        ("postop_programme", "Surveillance postopératoire lourde programmée", ()),
        ("postop_complication", "Complication postopératoire non programmée", ("texte",)),
    ),
    "Brûlures": (
        ("brulure", "Brûlure", ("brulure",)),
    ),
    "Métabolique et rénal": (
        ("acidocetose", "Acidocétose diabétique", ()),
        ("coma_hyperosmolaire", "Coma hyperosmolaire", ()),
        ("dysnatremie", "Dysnatrémie sévère", ()),
        ("dyskaliemie", "Dyskaliémie sévère", ()),
        ("ira_epuration", "Insuffisance rénale aiguë avec indication d'épuration", ()),
    ),
    "Intoxications et envenimations": (
        ("intox_medicamenteuse", "Intoxication médicamenteuse", ()),
        ("intox_organophosphores", "Organophosphorés", ()),
        ("intox_co", "Monoxyde de carbone", ()),
        ("intox_caustique", "Caustique", ()),
        ("envenimation_scorpionique", "Envenimation scorpionique", ()),
        ("envenimation_ophidienne", "Envenimation ophidienne", ()),
    ),
    "Obstétrical": (
        ("preeclampsie", "Prééclampsie sévère", ()),
        ("eclampsie", "Éclampsie", ()),
        ("hellp", "HELLP syndrome", ()),
        ("hemorragie_post_partum", "Hémorragie du post-partum", ()),
        ("embolie_amniotique", "Embolie amniotique", ()),
    ),
    "Autre": (
        ("post_arret_cardiaque", "Post-arrêt cardiaque", ()),
        ("tetanos", "Tétanos", ()),
        ("autre", "Autre", ("texte",)),
    ),
}

PORTES_ENTREE_SEPSIS = (
    ("pulmonaire", "Pulmonaire"),
    ("digestive", "Digestive"),
    ("urinaire", "Urinaire"),
    ("cutanee", "Cutanée — parties molles"),
    ("catheter", "Cathéter"),
    ("meningee", "Méningée"),
    ("indeterminee", "Indéterminée"),
)

PROFONDEURS_BRULURE = (
    ("second_degre_superficiel", "2e degré superficiel"),
    ("second_degre_profond", "2e degré profond"),
    ("troisieme_degre", "3e degré"),
    ("mixte", "Mixte"),
)
AGENTS_BRULURE = (
    ("thermique", "Thermique"),
    ("electrique", "Électrique"),
    ("chimique", "Chimique"),
)

# --------------------------------------------------------------------------
# Interventions (SPEC §4.6) — liste provisoire, question ouverte 10
# --------------------------------------------------------------------------
GESTES_CHIRURGICAUX = (
    ("laparotomie", "Laparotomie exploratrice"),
    ("splenectomie", "Splénectomie"),
    ("hepatique", "Chirurgie hépatique d'hémostase"),
    ("drainage_thoracique", "Drainage thoracique"),
    ("thoracotomie", "Thoracotomie"),
    ("craniectomie", "Craniectomie décompressive"),
    ("evacuation_hematome", "Évacuation d'hématome intracrânien"),
    ("dvE", "Dérivation ventriculaire externe"),
    ("fixateur_externe", "Fixateur externe"),
    ("osteosynthese", "Ostéosynthèse"),
    ("parage", "Parage de plaie / excision-greffe"),
    ("tracheotomie", "Trachéotomie"),
    ("cesarienne", "Césarienne"),
    ("hysterectomie_hemostase", "Hystérectomie d'hémostase"),
    ("autre", "Autre (préciser)"),
)

# --------------------------------------------------------------------------
# Prescription (SPEC §5.2)
# --------------------------------------------------------------------------
# Chaque voie déclare les champs que le formulaire doit demander — et donc
# aussi ceux qu'il ne doit pas demander.
VOIES: dict[str, dict] = {
    "PO": {
        "libelle": "PO",
        "titre": "Per os",
        "champs": ("produit", "dose", "unite", "rythme"),
    },
    "IV": {
        "libelle": "IV",
        "titre": "Intraveineux",
        "champs": ("produit", "dose", "unite", "rythme", "condition", "volume_dilution"),
    },
    "PSE": {
        "libelle": "PSE",
        "titre": "Seringue électrique",
        "champs": ("produit", "dilution", "nb_ampoules", "vitesse"),
    },
    "SC": {
        "libelle": "S/C",
        "titre": "Sous-cutané",
        "champs": ("produit", "dose", "unite", "rythme"),
    },
    "AEROSOL": {
        "libelle": "Aérosol",
        "titre": "Aérosols",
        "champs": ("produit", "dose", "unite", "rythme"),
    },
    "SOINS": {
        "libelle": "Soins",
        "titre": "Soins locaux",
        "champs": ("produit", "rythme"),
    },
    "KINE": {
        "libelle": "Kiné",
        "titre": "Kinésithérapie",
        "champs": ("produit", "rythme"),
    },
    "ENTREES": {
        "libelle": "Entrées",
        "titre": "Entrées",
        "champs": ("produit", "vitesse", "additifs", "volume_24h", "sous_type"),
    },
}
ORDRE_VOIES = ("PO", "IV", "PSE", "SC", "AEROSOL", "SOINS", "KINE", "ENTREES")

# Sous-types de la voie « Entrées » : une perfusion se prescrit en cc/h, une
# nutrition en volume sur 24 h. Les deux comptent dans le bilan des entrées.
SOUS_TYPES_ENTREES = (
    ("perfusion", "Perfusion (cc/h)"),
    ("nutrition_enterale", "Nutrition entérale (mL/24 h)"),
    ("nutrition_parenterale", "Nutrition parentérale (mL/24 h)"),
)

RYTHMES = (
    ("x1/j", "×1/j"),
    ("x2/j", "×2/j"),
    ("x3/j", "×3/j"),
    ("x4/j", "×4/j"),
    ("x6/j", "×6/j"),
    ("1j/2", "1 jour sur 2"),
    ("continu", "Continu"),
    ("conditionnel", "Conditionnel"),
)

UNITES = ("mg", "g", "µg", "UI", "MUI", "mL", "cc", "cp", "amp", "bouffée", "%")

STATUTS_LIGNE = (
    ("active", "Active"),
    ("arretee", "Arrêtée"),
)

# --------------------------------------------------------------------------
# Bilans à demander pour le lendemain (SPEC §5.2 bis) — à valider
# --------------------------------------------------------------------------
EXAMENS_A_DEMANDER = (
    ("nfs", "NFS"),
    ("ionogramme", "Ionogramme"),
    ("creatinine", "Créatinine"),
    ("uree", "Urée"),
    ("crp", "CRP"),
    ("procalcitonine", "Procalcitonine"),
    ("gds", "Gaz du sang"),
    ("tp_inr", "TP / INR"),
    ("bilan_hepatique", "Bilan hépatique"),
    ("hemoculture", "Hémoculture"),
    ("ecbu", "ECBU"),
    ("pdp", "PDP"),
)

# --------------------------------------------------------------------------
# Explorations (SPEC §6) — liste à compléter avec un senior
# --------------------------------------------------------------------------
# Chaque type déclare ses valeurs chiffrées : (clé, libellé, unité, type).
TYPES_EXPLORATION: dict[str, dict] = {
    "dtc": {
        "libelle": "DTC (Doppler transcrânien)",
        "valeurs": (
            ("ip_droit", "IP droit", "", "nombre"),
            ("ip_gauche", "IP gauche", "", "nombre"),
            ("vm_droite", "Vm droite", "cm/s", "nombre"),
            ("vm_gauche", "Vm gauche", "cm/s", "nombre"),
        ),
    },
    "tdm_cerebrale": {
        "libelle": "TDM cérébrale",
        "valeurs": (
            ("lesion", "Lésion", "", "trois_etats"),
            ("type_lesion", "Type de lésion", "", "texte"),
        ),
    },
    "ett": {
        "libelle": "ETT",
        "valeurs": (
            ("fevg", "FEVG", "%", "nombre"),
            ("vci", "Diamètre VCI", "mm", "nombre"),
            ("paps", "PAPS", "mmHg", "nombre"),
            ("epanchement", "Épanchement péricardique", "", "trois_etats"),
        ),
    },
    "echo_pleuro_pulmonaire": {
        "libelle": "Échographie pleuro-pulmonaire",
        "valeurs": (
            ("epanchement_droit", "Épanchement droit", "", "trois_etats"),
            ("epanchement_gauche", "Épanchement gauche", "", "trois_etats"),
            ("condensation", "Condensation", "", "trois_etats"),
            ("lignes_b", "Lignes B", "", "trois_etats"),
        ),
    },
    "radio_thorax": {
        "libelle": "Radiographie thoracique",
        "valeurs": (
            ("foyer", "Foyer", "", "trois_etats"),
            ("siege_foyer", "Siège du foyer", "", "texte"),
        ),
    },
    "eeg": {
        "libelle": "EEG",
        "valeurs": (),
    },
    "fibroscopie": {
        "libelle": "Fibroscopie bronchique",
        "valeurs": (
            ("indication", "Indication", "", "texte"),
            ("prelevement", "Prélèvement associé", "", "texte"),
        ),
    },
}

# --------------------------------------------------------------------------
# Microbiologie (SPEC §7.4)
# --------------------------------------------------------------------------
PRELEVEMENTS = (
    ("hemoculture", "Hémoculture"),
    ("ecbu", "ECBU"),
    ("lcr", "Ponction lombaire"),
    ("pdp", "PDP"),
    ("catheter", "Prélèvement de cathéter"),
    ("autre", "Autre"),
)
RESULTATS_MICROBIO = (
    ("en_cours", "En cours"),
    ("sterile", "Stérile"),
    ("positif", "Positif"),
)

# --------------------------------------------------------------------------
# Infections nosocomiales (SPEC §9.2)
# --------------------------------------------------------------------------
INFECTIONS_NOSOCOMIALES = (
    ("pavm", "PAVM"),
    ("ilc", "Infection liée au cathéter"),
    ("iu", "Infection urinaire"),
    ("iss", "Infection du site opératoire"),
    ("autre", "Autre"),
)

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
TYPES_DISPOSITIF: dict[str, dict] = {
    "intubation": {
        "libelle": "Intubation",
        "sites": (),
        "champs": ("taille_sonde", "reperage_cm"),
        "en_cours": "Intubé",
        "apres": "Extubé",
        "verbe_retrait": "Extubation",
    },
    "sedation": {
        "libelle": "Sédation",
        "sites": (),
        "champs": ("molecules",),
        "en_cours": "Sédaté",
        "apres": "Arrêt sédation",
        "verbe_retrait": "Arrêt de la sédation",
    },
    "tracheotomie": {
        "libelle": "Trachéotomie (canule)",
        "sites": (),
        "champs": ("taille_sonde",),
        "en_cours": "Canule de trachéotomie",
        "apres": "Décanulé",
        "verbe_retrait": "Décanulation",
    },
    "sng": {
        "libelle": "Sonde nasogastrique",
        "sites": ("Narine droite", "Narine gauche", "Bouche"),
        "champs": ("fixation_cm",),
        "en_cours": "SNG",
        "apres": "SNG retirée",
        "verbe_retrait": "Retrait",
    },
    "gastrostomie": {
        "libelle": "Gastrostomie",
        "sites": (),
        "champs": (),
        "en_cours": "Gastrostomie",
        "apres": "Gastrostomie retirée",
        "verbe_retrait": "Retrait",
    },
    "sonde_urinaire": {
        "libelle": "Sonde urinaire",
        "sites": (),
        "champs": ("taille_sonde",),
        "en_cours": "Sondé",
        "apres": "Sonde urinaire retirée",
        "verbe_retrait": "Ablation",
    },
    "ktsp": {
        "libelle": "Cathéter sus-pubien (KTSP)",
        "sites": (),
        "champs": (),
        "en_cours": "KTSP",
        "apres": "KTSP retiré",
        "verbe_retrait": "Ablation",
    },
    "kt_central": {
        "libelle": "Cathéter veineux central (KT)",
        "sites": (
            "Jugulaire interne droite", "Jugulaire interne gauche",
            "Sous-clavière droite", "Sous-clavière gauche",
            "Fémorale droite", "Fémorale gauche",
        ),
        "champs": ("nb_voies",),
        "en_cours": "KT central",
        "apres": "KT central retiré",
        "verbe_retrait": "Ablation",
    },
    "picc": {
        "libelle": "PICC line",
        "sites": ("Bras droit", "Bras gauche"),
        "champs": (),
        "en_cours": "PICC",
        "apres": "PICC retiré",
        "verbe_retrait": "Ablation",
    },
    "kta": {
        "libelle": "Cathéter artériel (KTA)",
        "sites": (
            "Radiale droite", "Radiale gauche",
            "Fémorale droite", "Fémorale gauche",
            "Humérale droite", "Humérale gauche",
        ),
        "champs": (),
        "en_cours": "KTA",
        "apres": "KTA retiré",
        "verbe_retrait": "Ablation",
    },
    "voie_peripherique": {
        "libelle": "Voie veineuse périphérique",
        "sites": ("Membre supérieur droit", "Membre supérieur gauche",
                  "Membre inférieur droit", "Membre inférieur gauche"),
        "champs": (),
        "en_cours": "VVP",
        "apres": "VVP retirée",
        "verbe_retrait": "Ablation",
    },
    "drain_thoracique": {
        "libelle": "Drain thoracique",
        "sites": ("Droit", "Gauche", "Bilatéral"),
        "champs": (),
        "en_cours": "Drain thoracique",
        "apres": "Drain thoracique retiré",
        "verbe_retrait": "Ablation",
    },
    "drain_abdominal": {
        "libelle": "Drain abdominal",
        "sites": (),
        "champs": (),
        "en_cours": "Drain abdominal",
        "apres": "Drain abdominal retiré",
        "verbe_retrait": "Ablation",
    },
    "dve": {
        "libelle": "Dérivation ventriculaire externe",
        "sites": ("Droite", "Gauche"),
        "champs": (),
        "en_cours": "DVE",
        "apres": "DVE retirée",
        "verbe_retrait": "Ablation",
    },
    "eer": {
        "libelle": "Épuration extra-rénale (cathéter de dialyse)",
        "sites": ("Jugulaire interne droite", "Jugulaire interne gauche",
                  "Fémorale droite", "Fémorale gauche"),
        "champs": ("technique",),
        "en_cours": "EER",
        "apres": "EER arrêtée",
        "verbe_retrait": "Arrêt",
    },
}

ORDRE_DISPOSITIFS = (
    "intubation", "sedation", "tracheotomie", "sng", "gastrostomie",
    "kt_central", "picc", "kta", "voie_peripherique",
    "sonde_urinaire", "ktsp", "drain_thoracique", "drain_abdominal", "dve", "eer",
)

# Champs supplémentaires : libellé du formulaire, puis préfixe et unité pour
# l'affichage compact (« repère 22 cm », « 3 voies »). Même logique que les
# voies de prescription : on ne demande que ce qui a un sens.
CHAMPS_DISPOSITIF: dict[str, tuple[str, str, str]] = {
    #   clé            libellé du formulaire          préfixe     unité
    "taille_sonde": ("Taille / calibre", "n°", ""),
    "reperage_cm": ("Repère à l'arcade dentaire", "repère", "cm"),
    "fixation_cm": ("Fixation", "fixée à", "cm"),
    "molecules": ("Molécules", "", ""),
    "nb_voies": ("Nombre de voies", "", "voies"),
    "technique": ("Technique", "", ""),
}


def libelle_dispositif(code: str | None) -> str:
    if not code:
        return ""
    return TYPES_DISPOSITIF.get(code, {}).get("libelle", code)
