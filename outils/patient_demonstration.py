"""Charge un patient de démonstration saturé, pour éprouver la feuille imprimée.

À lancer avant le premier patient réel, sur une base d'essai :

    REA_DIR=C:\\ReaEssai python outils\\patient_demonstration.py

Puis ouvrir le logiciel sur cette même base, aller dans Prescrit, cliquer
« Imprimer la pancarte de ce jour », ouvrir le fichier téléchargé et imprimer :
A3, paysage, marges nulles, sans mise à l'échelle.

Ce que ce patient a de particulier : il déborde volontairement. Quarante lignes
de prescription pour trente emplacements sur la feuille, des allergies, des
seringues électriques avec changements de vitesse, des bilans cochés pour
demain, un antibiogramme, des drains. C'est là que les surprises d'impression
apparaissent — jamais sur un patient à trois lignes.

Ce fichier ne fait pas partie du logiciel : il n'est jamais importé par
l'application, seulement lancé à la main.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rea.db import Base  # noqa: E402
from rea.domaine import prescription as dom_prescription  # noqa: E402
from rea.services import (  # noqa: E402
    bilans, dispositifs, evolution, microbiologie, prescriptions, sejours, vitesses,
)

AUJ = date.today().isoformat()
J1 = (date.today() - timedelta(days=1)).isoformat()
J2 = (date.today() - timedelta(days=2)).isoformat()
DEMAIN = (date.today() + timedelta(days=1)).isoformat()

# Quarante lignes pour trente emplacements : le débordement est voulu.
PRESCRIPTIONS = [
    # (voie, produit, dose, unité, rythme, durée prévue)
    ("IV", "Imipénème", 1, "g", "x3/j", 7),
    ("IV", "Amikacine", 1500, "mg", "x1/j", 3),
    ("IV", "Vancomycine", 1, "g", "x2/j", 10),
    ("IV", "Métronidazole", 500, "mg", "x3/j", 7),
    ("IV", "Paracétamol", 1, "g", "x4/j", None),
    ("IV", "Néfopam", 20, "mg", "x4/j", None),
    ("IV", "Oméprazole", 40, "mg", "x1/j", None),
    ("IV", "Furosémide", 40, "mg", "x3/j", None),
    ("PO", "Kardégic", 75, "mg", "x1/j", None),
    ("PO", "Atorvastatine", 40, "mg", "x1/j", None),
    ("PO", "Lévétiracétam", 500, "mg", "x2/j", None),
    ("PO", "Bisoprolol", 2.5, "mg", "x1/j", None),
    ("PO", "Amlodipine", 5, "mg", "x1/j", None),
    ("PO", "Metformine", 850, "mg", "x2/j", None),
    ("PO", "Vitamine D", 100000, "UI", "1j/2", None),
    ("SC", "Enoxaparine 4000 UI", None, None, "x1/j", None),
    ("SC", "Insuline rapide", 6, "UI", "x3/j", None),
    ("SC", "Insuline lente", 18, "UI", "x1/j", None),
    ("AEROSOL", "Salbutamol", 5, "mg", "x4/j", None),
    ("AEROSOL", "Ipratropium", 0.5, "mg", "x3/j", None),
    ("AEROSOL", "Sérum salé hypertonique", None, None, "x3/j", None),
    ("SOINS", "Pansement du drain thoracique", None, None, "x1/j", None),
    ("SOINS", "Soins de trachéotomie", None, None, "x2/j", None),
    ("SOINS", "Soins de bouche", None, None, "x6/j", None),
    ("SOINS", "Prévention d'escarre — changement de position", None, None, "x6/j", None),
    ("KINE", "Kinésithérapie respiratoire", None, None, "x2/j", None),
    ("KINE", "Mobilisation passive des quatre membres", None, None, "x2/j", None),
    ("KINE", "Verticalisation au fauteuil", None, None, "x1/j", None),
]

# Le produit, son indication : les deux tiers de l'identité d'un épisode.
INDICATIONS = {
    "Imipénème": "pneumopathie acquise sous ventilation",
    "Amikacine": "pneumopathie acquise sous ventilation",
    "Vancomycine": "couverture probabiliste du cathéter",
    "Métronidazole": "péritonite post-opératoire",
    "Enoxaparine 4000 UI": "prophylaxie thrombo-embolique",
    "Lévétiracétam": "prophylaxie des crises, traumatisme crânien",
    "Oméprazole": "prophylaxie de l'ulcère de stress",
}

# Une posologie adaptée en cours de route, pour éprouver les deux niveaux.
CHANGEMENTS_DE_DOSE = {
    "Amikacine": (1000, "mg", "adaptation à la fonction rénale"),
    "Vancomycine": (750, "mg", "taux résiduel à 28 mg/L"),
}

SERINGUES = [
    # (produit, dilution, vitesse de départ, changements [(heure, vitesse)])
    ("Noradrénaline", "0,5 mg/cc", 25, [(12, 18), (16, 15), (22, 8)]),
    ("Midazolam", "1 mg/cc", 6, [(14, 4)]),
    ("Sufentanil", "10 µg/cc", 4, [(14, 3)]),
    ("Insuline", "1 UI/cc", 2, [(10, 3), (18, 2)]),
    ("Amiodarone", "15 mg/cc", 1, []),
]

ENTREES = [
    ("perfusion", "Ringer Lactate", 60, None, "+ 3 KCl"),
    ("perfusion", "Sérum glucosé 5 %", 40, None, "+ 2 NaCl"),
    ("nutrition_enterale", "Nutrition entérale", None, 1500, None),
]


def charger(base: Base) -> str:
    pid = sejours.creer_patient(
        base, matricule="DEMO-2026-001", nom_affichage="Patient DÉMONSTRATION",
        date_naissance="1961-04-12", sexe="M",
    )
    sid = sejours.creer_sejour(
        base, patient_id=pid, date_admission=J2, lit_admission=1,
        poids_kg=82, taille_cm=174, provenance_type="urgences",
        traumatique=True, mecanisme="avp_deux_roues",
        mecanisme_detail="motocycliste heurté par une voiture",
        creatinine_base=88, type_admission="medicale",
        maladie_chronique_igs2="aucune",
    )
    sejours.definir_regions_traumatiques(
        base, sid, ["cranien", "thoracique", "abdominal", "membres"],
        precisions={
            "cranien": "hématome sous-dural aigu, Glasgow 7 à l'arrivée",
            "thoracique": "volet costal droit, contusion pulmonaire bilatérale",
            "abdominal": "fracture de rate grade III, laparotomie d'hémostase",
            "membres": "fracture ouverte du fémur gauche",
        },
    )
    sejours.definir_motifs(base, sid, motif_principal=None,
                           motifs_associes=["sdra", "choc_septique"])

    # Allergies et antécédents — la ligne rouge en tête de feuille.
    for categorie, libelle in [
        ("allergie", "Pénicilline (œdème de Quincke)"),
        ("allergie", "Produits de contraste iodés"),
        ("personnel", "Diabète type 2"),
        ("personnel", "HTA"),
        ("personnel", "BPCO stade II"),
        ("chirurgical", "Cholécystectomie 2019"),
    ]:
        sejours.ajouter_antecedent(base, patient_id=pid, categorie=categorie,
                                   libelle=libelle)
    sejours.ajouter_antecedent(base, patient_id=pid, categorie="habitude",
                               libelle="Tabagisme", code="tabagisme",
                               quantification_valeur=40,
                               quantification_unite="paquets-année")

    for voie, produit, dose, unite, rythme, duree in PRESCRIPTIONS:
        ligne = prescriptions.ajouter_ligne(
            base, sejour_id=sid, voie=voie, produit=produit, date_debut=J1,
            dose=dose, unite=unite, rythme=rythme, duree_prevue_jours=duree,
            indication=INDICATIONS.get(produit),
            horaires_override=",".join(
                str(h) for h in dom_prescription.horaires_par_defaut(produit, rythme)
            ) or None,
        )
        # Un changement de dose n'ouvre pas un nouveau traitement : le compteur
        # doit toujours afficher J2, et la durée d'antibiothérapie courir
        # depuis la première dose (SPEC §5.1).
        if produit in CHANGEMENTS_DE_DOSE:
            nouvelle, unite_nouvelle, motif = CHANGEMENTS_DE_DOSE[produit]
            prescriptions.changer_posologie(
                base, ligne, a_partir_du=AUJ,
                dose=nouvelle, unite=unite_nouvelle, motif=motif,
            )

    for produit, dilution, vitesse, changements in SERINGUES:
        ligne = prescriptions.ajouter_ligne(
            base, sejour_id=sid, voie="PSE", produit=produit, date_debut=J1,
            dilution=dilution, vitesse=vitesse, rythme="continu",
        )
        for heure, nouvelle in changements:
            vitesses.regler(base, cible=vitesses.LIGNE, cible_id=ligne,
                            date_heure=f"{AUJ}T{heure:02d}:00", vitesse=nouvelle)

    for sous_type, produit, vitesse, volume, additifs in ENTREES:
        prescriptions.ajouter_ligne(
            base, sejour_id=sid, voie="ENTREES", produit=produit, date_debut=J1,
            sous_type=sous_type, vitesse=vitesse, volume_24h=volume,
            additifs=additifs, rythme="continu",
        )

    # Dispositifs : abords, drains, sédation.
    for type_, site, details in [
        ("intubation", None, {"taille_sonde": 7.5, "reperage_cm": 22}),
        ("sedation", None, {"molecules": "Midazolam + Sufentanil", "vitesse": 6}),
        ("kt_central", "Jugulaire interne droite", {"nb_voies": 3}),
        ("kta", "Radiale gauche", {}),
        ("sonde_urinaire", None, {"taille_sonde": 16}),
        ("sng", "Narine droite", {"fixation_cm": 55}),
        ("drain_thoracique", "Droit", {}),
        ("redon", "Abdomen", {}),
    ]:
        dispositifs.poser(base, sejour_id=sid, type_=type_, date_pose=J2,
                          site=site, details=details)

    # Bilans des deux jours précédents, plusieurs prélèvements par jour.
    bilans.enregistrer_resultats(base, sejour_id=sid, date_heure=f"{J2}T06:00", valeurs={
        "hb": 8.4, "hte": 26, "plq": 96, "gb": 18.2, "tp": 58, "inr": 1.6, "tca": 42,
        "na": 148, "k": 3.1, "cl": 112, "ca": 2.05, "mg": 0.62, "phosphore": 0.71,
        "creat": 184, "uree": 18.4, "crp": 280, "glycemie": 12.4, "albumine": 22,
        "asat": 122, "alat": 96, "bili": 34,
    })
    bilans.enregistrer_resultats(base, sejour_id=sid, date_heure=f"{J2}T18:00", valeurs={
        "hb": 7.9, "k": 3.4, "creat": 196, "crp": 310,
    })
    bilans.enregistrer_resultats(base, sejour_id=sid, date_heure=f"{J1}T06:00", valeurs={
        "hb": 9.6, "hte": 30, "plq": 88, "gb": 14.6, "na": 144, "k": 4.2,
        "creat": 152, "uree": 14.2, "crp": 210, "glycemie": 9.1,
    })
    for heure, gaz in [
        (f"{J2}T06:00", dict(ph=7.28, pao2=64, paco2=52, hco3=19, lactate=4.2,
                             fio2=80, pep=10, fr=22, spo2=91, sao2=90, vt=420, ai=14)),
        (f"{J2}T14:00", dict(ph=7.31, pao2=72, paco2=48, hco3=21, lactate=3.1,
                             fio2=70, pep=10, fr=20, spo2=93)),
        (f"{J1}T06:00", dict(ph=7.38, pao2=88, paco2=42, hco3=24, lactate=1.8,
                             fio2=50, pep=8, fr=18, spo2=96, sao2=96, vt=440, ai=12)),
    ]:
        bilans.enregistrer_gaz_du_sang(base, sid, heure, mode_ventilatoire="VAC", **gaz)

    # Microbiologie : un résultat rendu avec antibiogramme, un en attente.
    mid = microbiologie.enregistrer(base, sejour_id=sid, date_prelevement=J2,
                                    type_prelevement="hemoculture")
    microbiologie.completer(base, mid, {
        "resultat": "positif", "germe": "Klebsiella pneumoniae BLSE",
        "antibiogramme": microbiologie.texte_antibiogramme(
            sensibles=["imipeneme", "amikacine", "colistine"],
            intermediaires=["ciprofloxacine"],
            resistants=["ceftriaxone", "amox_clav", "pip_tazo"],
        ),
    })
    microbiologie.enregistrer(base, sejour_id=sid, date_prelevement=J1,
                              type_prelevement="pdp")
    microbiologie.declarer_infection_nosocomiale(
        base, sejour_id=sid, type_="pavm", date_diagnostic=J1,
        germe="Klebsiella pneumoniae BLSE",
    )

    # Bilans cochés pour aujourd'hui et pour demain.
    prescriptions.definir_bilans_demandes(
        base, sid, AUJ, [("nfs", "08:00"), ("ionogramme", "08:00")])
    prescriptions.definir_bilans_demandes(
        base, sid, DEMAIN,
        [("nfs", "08:00"), ("ionogramme", "08:00"), ("crp", "08:00"),
         ("gaz_du_sang", "08:00"), ("hemoculture", "08:00")])

    # Évolution du jour, avec les sorties qui font le bilan hydrique.
    drains = evolution.drains_du_jour(base, sid, AUJ)
    mesures = {
        "rass": -4, "glasgow": 6, "pupilles": "egales_reactives",
        "fr_clinique": 20, "spo2_clinique": 94, "tete_de_lit": "oui",
        "fc": 112, "pas": 92, "pad": 48, "pam": 63,
        "diurese_24h": 850, "diurese_conservee": "non",
        "temperature": 38.9, "frissons": "present",
    }
    for drain, volume in zip(drains, (320, 180)):
        mesures[drain["cle"]] = volume
    evolution.enregistrer_journee(
        base, sid, AUJ, elements=mesures,
        textes={
            "plan_neurologique": "Sédation profonde, RASS −4. TDM de contrôle demandée.",
            "plan_respiratoire": "SDRA modéré. Décubitus ventral discuté.",
            "plan_hemodynamique": "Choc septique sous noradrénaline, en décroissance.",
            "plan_infectieux": "PAVM à Klebsiella BLSE, J2 d'imipénème.",
            "conduite": "Poursuite de l'antibiothérapie. Sevrage progressif des amines.",
        },
        version_attendue=evolution.obtenir_ou_creer(base, sid, AUJ)["version"],
    )
    evolution.ajouter_escarre(base, sejour_id=sid, localisation="Sacrum",
                              grade=2, date_constat=J1)
    return sid


if __name__ == "__main__":
    base = Base()
    sid = charger(base)
    lignes = prescriptions.toutes_les_lignes(base, sid)
    print(f"Patient de démonstration chargé — séjour {sid}")
    print(f"  {len(lignes)} lignes de prescription")
    print(f"  base : {base.chemin}")
    base.fermer()
