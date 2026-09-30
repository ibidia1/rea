"""Charge un patient de démonstration saturé, pour éprouver la feuille imprimée.

À lancer avant le premier patient réel, sur une base d'essai :

    REA_DIR=C:\\ReaEssai python outils\\patient_demonstration.py

Puis ouvrir le logiciel sur cette même base, aller dans Prescrit, cliquer
« Imprimer la pancarte de ce jour », ouvrir le fichier téléchargé et imprimer :
A3, paysage, marges nulles, sans mise à l'échelle.

Ce que ce patient a de particulier : il remplit tout. Un polytraumatisé à son
sixième jour — trente lignes de prescription, chacune dans son bloc, des seringues dont la vitesse
change, neuf bilans et neuf gaz du sang sur six jours, des transfusions
encadrées par leurs hémoglobines, huit avis spécialisés, des dispositifs posés,
retirés et reposés (une extubation accidentelle, une épuration extra-rénale),
une vingtaine d'actes et d'explorations, des prélèvements positifs avec
antibiogramme. C'est là que les surprises d'impression apparaissent — jamais
sur un patient à trois lignes.

Ce fichier ne fait pas partie du logiciel : il n'est jamais importé par
l'application, seulement lancé à la main.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rea.database import Base  # noqa: E402
from rea.models import prescription as dom_prescription  # noqa: E402
from rea.services import (  # noqa: E402
    administrations, avis, bilans, constantes, dispositifs, evolution,
    explorations, microbiologie, prescriptions, sejours, vitesses,
)

AUJ = date.today().isoformat()
J1 = (date.today() - timedelta(days=1)).isoformat()
J2 = (date.today() - timedelta(days=2)).isoformat()
J3 = (date.today() - timedelta(days=3)).isoformat()
J4 = (date.today() - timedelta(days=4)).isoformat()
J5 = (date.today() - timedelta(days=5)).isoformat()   # jour de l'admission
DEMAIN = (date.today() + timedelta(days=1)).isoformat()

# Trente lignes pour trente emplacements, chacune dans son bloc : huit IV pour
# huit lignes, cinq PO pour cinq, deux aérosols, deux soins locaux, deux kinés.
# Aucune ligne n'emprunte la place d'un autre bloc — la feuille se lit comme
# le service la remplit. (Le partage des lignes entre blocs, quand un bloc
# déborde, est éprouvé par tests/test_feuille.py.)
PRESCRIPTIONS = [
    # (voie, produit, dose, unité, rythme, durée prévue)
    ("IV", "Imipénème", 1, "g", "x3/j", 7),
    ("IV", "Amikacine", 1500, "mg", "x1/j", 3),
    ("IV", "Vancomycine", 1, "g", "x2/j", 10),
    ("IV", "Métronidazole", 500, "mg", "x3/j", 7),
    ("IV", "Paracétamol", 1, "g", "x4/j", None),
    ("IV", "Néfopam", 20, "mg", "x4/j", None),
    ("IV", "Oméprazole", 40, "mg", "x1/j", None),
    ("IV", "Hydrocortisone", 50, "mg", "x4/j", 5),
    ("PO", "Kardégic", 75, "mg", "x1/j", None),
    ("PO", "Atorvastatine", 40, "mg", "x1/j", None),
    ("PO", "Lévétiracétam", 500, "mg", "x2/j", None),
    ("PO", "Bisoprolol", 2.5, "mg", "x1/j", None),
    ("PO", "Amlodipine", 5, "mg", "x1/j", None),
    ("SC", "Enoxaparine 4000 UI", None, None, "x1/j", None),
    ("SC", "Insuline rapide", 6, "UI", "x3/j", None),
    ("AEROSOL", "Salbutamol", 5, "mg", "x4/j", None),
    ("AEROSOL", "Ipratropium", 0.5, "mg", "x4/j", None),
    ("SOINS", "Pansement du drain thoracique", None, None, "x1/j", None),
    ("SOINS", "Pansement de l'escarre sacrée", None, None, "x1/j", None),
    ("KINE", "Kinésithérapie respiratoire", None, None, "x2/j", None),
    ("KINE", "Kinésithérapie motrice", None, None, "x1/j", None),
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

# Le jour où chaque traitement a commencé — les compteurs J de la feuille
# en dépendent. Par défaut le lendemain de l'admission.
DEBUTS = {
    "Imipénème": J3, "Amikacine": J3, "Vancomycine": J4, "Métronidazole": J5,
    "Hydrocortisone": J3, "Lévétiracétam": J5, "Salbutamol": J2, "Ipratropium": J2,
    "Insuline rapide": J1, "Pansement de l'escarre sacrée": J2,
}

# Une posologie adaptée en cours de route, pour éprouver les deux niveaux.
CHANGEMENTS_DE_DOSE = {
    "Amikacine": (1000, "mg", "adaptation à la fonction rénale"),
    "Vancomycine": (750, "mg", "taux résiduel à 28 mg/L"),
}

SERINGUES = [
    # (produit, dilution, vitesse de départ, changements [(heure, vitesse)],
    #  date d'arrêt) — la sédation est arrêtée hier : « J1 d'AS » sur la feuille.
    ("Noradrénaline", "0,5 mg/cc", 25, [(12, 18), (16, 15), (22, 8)], None),
    ("Midazolam", "1 mg/cc", 6, [], J1),
    ("Sufentanil", "10 µg/cc", 4, [], J1),
    ("Insuline", "1 UI/cc", 2, [(10, 3), (18, 2)], None),
]

ENTREES = [
    # Les produits viennent du catalogue, les additifs de leur liste : c'est
    # la forme « + (1 NaCl + 2 KCl) » qui s'imprime sur la feuille.
    ("perfusion", "Ringer Lactate", 60, None, [("KCl", 3)]),
    ("perfusion", "Sérum glucosé 5 %", 40, None, [("NaCl", 1), ("KCl", 2)]),
    ("nutrition_parenterale", "SmofKabiven", None, 1500, [("Cernevit", 1)]),
]


def charger(base: Base) -> str:
    pid = sejours.creer_patient(
        base, matricule="DEMO-2026-001", nom_affichage="Patient DÉMONSTRATION",
        date_naissance="1961-04-12", sexe="M", groupe_sanguin="A+",
    )
    sid = sejours.creer_sejour(
        base, patient_id=pid, date_admission=J5, heure_admission="15:40",
        lit_admission=1,
        poids_kg=82, taille_cm=174, provenance_type="urgences",
        traumatique=True, mecanisme="avp_deux_roues",
        mecanisme_detail="motocycliste heurté par une voiture",
        creatinine_base=88, type_admission="medicale", glasgow_initial=7,
        maladie_chronique_igs2="aucune",
    )
    sejours.definir_regions_traumatiques(
        base, sid, ["cranien", "thoracique", "abdominal", "peripherique"],
        precisions={
            "cranien": "hématome sous-dural aigu, Glasgow 7 à l'arrivée",
            "thoracique": "volet costal droit, contusion pulmonaire bilatérale",
            "abdominal": "fracture de rate grade III, laparotomie d'hémostase",
            "peripherique": "fracture ouverte du fémur gauche",
        },
    )
    sejours.definir_motifs(base, sid, motif_principal=None,
                           motifs_associes=["sdra", "choc_septique"])

    # Allergies et antécédents — la ligne rouge en tête de feuille.
    for categorie, libelle, precision in [
        ("allergie", "Pénicilline (œdème de Quincke)", None),
        ("allergie", "Produits de contraste iodés", None),
        ("personnel", "Diabète type 2", "sous insuline"),
        ("personnel", "HTA", "sous trithérapie"),
        ("personnel", "BPCO stade II", None),
        ("chirurgical", "Cholécystectomie 2019", None),
    ]:
        sejours.ajouter_antecedent(base, patient_id=pid, categorie=categorie,
                                   libelle=libelle, precision=precision)
    sejours.ajouter_antecedent(base, patient_id=pid, categorie="habitude",
                               libelle="Tabagisme", code="tabagisme",
                               quantification_valeur=40,
                               quantification_unite="paquets-année")

    for voie, produit, dose, unite, rythme, duree in PRESCRIPTIONS:
        ligne = prescriptions.ajouter_ligne(
            base, sejour_id=sid, voie=voie, produit=produit,
            date_debut=DEBUTS.get(produit, J4), dose=dose, unite=unite, rythme=rythme, duree_prevue_jours=duree,
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

    # Des cures déjà terminées : l'antibioprophylaxie de la fracture ouverte
    # (clindamycine + gentamicine, le patient est allergique à la pénicilline),
    # relayée à J3 par imipénème + amikacine sur la Klebsiella BLSE. Arrêtées,
    # elles quittent la grille et s'écrivent « 3 J Clindamycine » dans la case
    # « Cures terminées », au-dessus des transfusions.
    for produit, dose, unite, rythme in (("Clindamycine", 600, "mg", "x3/j"),
                                         ("Gentamicine", 400, "mg", "x1/j")):
        ligne = prescriptions.ajouter_ligne(
            base, sejour_id=sid, voie="IV", produit=produit, date_debut=J5,
            dose=dose, unite=unite, rythme=rythme,
            indication="antibioprophylaxie, fracture ouverte du fémur",
        )
        prescriptions.arreter_ligne(base, ligne, date_arret=J3,
                                    motif_arret="relais par imipénème + amikacine")

    for produit, dilution, vitesse, changements, arret in SERINGUES:
        ligne = prescriptions.ajouter_ligne(
            base, sejour_id=sid, voie="PSE", produit=produit, date_debut=J5,
            dilution=dilution, vitesse=vitesse, rythme="continu",
        )
        for heure, nouvelle in changements:
            vitesses.regler(base, cible=vitesses.LIGNE, cible_id=ligne,
                            date_heure=f"{AUJ}T{heure:02d}:00", vitesse=nouvelle)
        if arret:
            prescriptions.arreter_ligne(base, ligne, date_arret=arret,
                                        motif_arret="arrêt de la sédation")

    for sous_type, produit, vitesse, volume, additifs in ENTREES:
        prescriptions.ajouter_ligne(
            base, sejour_id=sid, voie="ENTREES", produit=produit, date_debut=J4,
            sous_type=sous_type, vitesse=vitesse, volume_24h=volume,
            additifs=dom_prescription.texte_additifs(additifs or []),
            rythme="continu",
        )

    # Dispositifs : posés à l'admission, certains retirés ou reposés depuis.
    # La feuille coche ce qui est en place ; ce qui a été retiré reste lisible
    # (« Extubé », « Redon retiré »), et une extubation accidentelle suivie
    # d'une réintubation s'écrit « Réintubé » avec son propre compteur.
    def poser(type_, jour, site=None, **details):
        return dispositifs.poser(base, sejour_id=sid, type_=type_, date_pose=jour,
                                 site=site, details=details)

    tube = poser("intubation", J5, taille_sonde=7.5, reperage_cm=22)
    sedation = poser("sedation", J5, molecules="Midazolam + Sufentanil", vitesse=6)
    poser("kt_central", J5, "Jugulaire interne droite", nb_voies=3)
    kta = poser("kta", J5, "Radiale gauche")
    poser("sonde_urinaire", J5, taille_sonde=16)
    poser("sng", J5, "Narine droite", fixation_cm=55)
    poser("drain_thoracique", J5, "Droit")
    poser("drain_abdominal", J5, "Loge de splénectomie", nature_drain="Loge splénique")
    redon = poser("redon", J5, "Membre inférieur")
    vvp = poser("voie_peripherique", J5, "Membre supérieur gauche")
    dispositifs.retirer(base, vvp, date_retrait=J4)
    dispositifs.retirer(base, redon, date_retrait=J3)
    # Insuffisance rénale aiguë à J3 : cathéter de dialyse, hémodiafiltration.
    poser("eer", J3, "Fémorale droite", technique="CVVHDF")
    # Bloc serratus pour le volet costal : une ALR sans péridurale, le patient
    # étant coagulopathe à l'admission.
    poser("catheter_alr", J3, "Bloc serratus", molecules="Ropivacaïne 0,2 %", vitesse=8)
    # Extubation accidentelle au nursing, réintubé dans l'heure.
    dispositifs.retirer(base, tube, date_retrait=J2, motif_retrait="accidentelle")
    poser("intubation", J2, taille_sonde=7.5, reperage_cm=23)
    # Sédation arrêtée hier : la feuille écrit « J1 d'AS ».
    dispositifs.retirer(base, sedation, date_retrait=J1)
    # Trachéotomie percutanée ce matin — et l'intubation laissée ouverte, pour
    # montrer le rappel : « Intubé … ⚠ à retirer (trachéo) » sur la feuille,
    # un bandeau rouge et un bouton de correction à l'écran.
    poser("tracheotomie", AUJ, taille_sonde=8)
    # Le KTA radial ne donnait plus de courbe : retiré, reposé de l'autre côté.
    dispositifs.retirer(base, kta, date_retrait=J1)
    poser("kta", J1, "Radiale droite")

    # Neuf bilans en six jours : l'admission, le contrôle post-opératoire, puis
    # un bilan chaque matin et un contrôle le soir quand ça bouge. La créatinine
    # monte jusqu'à l'EER puis redescend ; la CRP et la PCT suivent le sepsis.
    for date_heure, valeurs in [
        (f"{J5}T16:00", {"hb": 6.8, "hte": 21, "plq": 74, "gb": 16.4, "tp": 48, "inr": 1.9,
                         "tca": 48, "na": 139, "k": 4.8, "cl": 108, "ca": 1.92, "mg": 0.66,
                         "phosphore": 1.4, "creat": 118, "uree": 8.1, "glycemie": 13.2,
                         "albumine": 24, "asat": 186, "alat": 142, "bili": 18, "crp": 12}),
        (f"{J5}T22:00", {"hb": 8.9, "hte": 27, "plq": 58, "tp": 61, "inr": 1.5, "k": 4.4}),
        (f"{J4}T06:00", {"hb": 8.6, "hte": 26, "plq": 66, "gb": 18.2, "tp": 66, "inr": 1.4,
                         "tca": 40, "na": 144, "k": 4.6, "cl": 110, "creat": 176, "uree": 12.9,
                         "crp": 96, "pct": 4.8, "glycemie": 11.8, "asat": 122, "alat": 96,
                         "bili": 34, "albumine": 22}),
        (f"{J3}T06:00", {"hb": 8.2, "hte": 25, "plq": 92, "gb": 21.3, "na": 147, "k": 5.9,
                         "cl": 112, "creat": 298, "uree": 21.6, "crp": 280, "pct": 18.6,
                         "ca": 2.01, "mg": 0.61, "phosphore": 2.1}),
        (f"{J3}T18:00", {"k": 5.1, "creat": 241, "uree": 17.2}),
        (f"{J2}T06:00", {"hb": 8.1, "hte": 24, "plq": 104, "gb": 17.9, "tp": 70, "inr": 1.3,
                         "na": 145, "k": 4.3, "cl": 108, "creat": 196, "uree": 14.8,
                         "crp": 310, "pct": 12.2, "glycemie": 9.4}),
        (f"{J2}T18:00", {"hb": 7.2, "hte": 22, "k": 4.1}),
        (f"{J1}T06:00", {"hb": 9.6, "hte": 30, "plq": 128, "gb": 14.6, "na": 142, "k": 4.0,
                         "cl": 106, "creat": 152, "uree": 11.2, "crp": 210, "pct": 6.1,
                         "glycemie": 8.6, "asat": 64, "alat": 71, "bili": 22,
                         "albumine": 25}),
        (f"{AUJ}T06:00", {"hb": 9.4, "hte": 29, "plq": 146, "gb": 12.8, "tp": 76, "inr": 1.2,
                          "tca": 34, "na": 141, "k": 3.9, "cl": 105, "creat": 131,
                          "uree": 9.6, "crp": 150, "pct": 2.4, "mg": 0.74, "glycemie": 8.1}),
    ]:
        bilans.enregistrer_resultats(base, sejour_id=sid, date_heure=date_heure,
                                     valeurs=valeurs)

    # Neuf gaz du sang : VAC jusqu'à la réintubation, puis VS-AI au sevrage.
    # Chaque mode n'imprime que ses paramètres, et la FiO₂ du rapport
    # PaO₂/FiO₂ est toujours écrite juste au-dessus.
    for heure, mode, gaz in [
        (f"{J5}T16:00", "vac", dict(ph=7.21, pao2=78, paco2=49, hco3=17, lactate=5.8,
                                    fio2=100, pep=8, fr=18, spo2=94, sao2=93, vt=460)),
        (f"{J5}T22:00", "vac", dict(ph=7.29, pao2=84, paco2=44, hco3=20, lactate=3.9,
                                    fio2=70, pep=10, fr=20, spo2=95, sao2=95, vt=440)),
        (f"{J4}T06:00", "vac", dict(ph=7.31, pao2=66, paco2=47, hco3=22, lactate=2.6,
                                    fio2=80, pep=12, fr=22, spo2=91, sao2=90, vt=420)),
        (f"{J3}T06:00", "vac", dict(ph=7.24, pao2=64, paco2=52, hco3=19, lactate=4.2,
                                    fio2=80, pep=12, fr=24, spo2=91, sao2=90, vt=400)),
        (f"{J3}T14:00", "vac", dict(ph=7.30, pao2=72, paco2=48, hco3=21, lactate=3.1,
                                    fio2=70, pep=12, fr=24, spo2=93, sao2=93, vt=400)),
        (f"{J2}T06:00", "vac", dict(ph=7.36, pao2=86, paco2=44, hco3=23, lactate=2.2,
                                    fio2=60, pep=10, fr=20, spo2=95, sao2=95, vt=420)),
        (f"{J2}T11:00", "vac", dict(ph=7.33, pao2=74, paco2=47, hco3=23, lactate=2.4,
                                    fio2=70, pep=10, fr=20, spo2=93, sao2=93, vt=420)),
        (f"{J1}T06:00", "vs_ai", dict(ph=7.38, pao2=88, paco2=42, hco3=24, lactate=1.8,
                                      fio2=50, pep=8, spo2=96, sao2=96, vt=440, ai=12)),
        (f"{J1}T18:00", "vs_ai", dict(ph=7.41, pao2=92, paco2=40, hco3=25, lactate=1.4,
                                      fio2=40, pep=6, spo2=97, sao2=97, vt=460, ai=10)),
    ]:
        bilans.enregistrer_gaz_du_sang(base, sid, heure, mode_ventilatoire=mode, **gaz)

    # Microbiologie : des prélèvements rendus avec antibiogramme, un stérile,
    # d'autres en attente. Chaque type a sa ligne sur la feuille.
    klebsiella = microbiologie.texte_antibiogramme(
        sensibles=["imipeneme", "amikacine", "colistine"],
        intermediaires=["ciprofloxacine"],
        resistants=["ceftriaxone", "amox_clav", "pip_tazo"],
    )
    for jour, type_, resultat, germe, antibiogramme in [
        (J4, "hemoculture", "positif", "Klebsiella pneumoniae BLSE", klebsiella),
        (J4, "ecbu", "sterile", None, None),
        (J3, "hemoculture", "positif", "Klebsiella pneumoniae BLSE", klebsiella),
        (J3, "pdp", "positif", "Klebsiella pneumoniae BLSE", klebsiella),
        (J2, "catheter", "sterile", None, None),
        (J1, "hemoculture", "sterile", None, None),
        (J1, "pdp", "en_cours", None, None),
        (AUJ, "ecbu", "en_cours", None, None),
    ]:
        mid = microbiologie.enregistrer(base, sejour_id=sid, date_prelevement=jour,
                                        type_prelevement=type_)
        if resultat != "en_cours":
            microbiologie.completer(base, mid, {
                "resultat": resultat, "germe": germe, "antibiogramme": antibiogramme,
            })
    microbiologie.declarer_infection_nosocomiale(
        base, sejour_id=sid, type_="pavm", date_diagnostic=J3,
        germe="Klebsiella pneumoniae BLSE",
    )

    # Bilans cochés pour aujourd'hui et pour demain.
    # Aujourd'hui : le bilan de 8 h, et des examens à d'autres heures — ils
    # s'écrivent à leur heure sur la bande « Bilans & examens à faire ».
    prescriptions.definir_bilans_demandes(
        base, sid, AUJ,
        [("nfs", "08:00"), ("ionogramme", "08:00"), ("rx_thorax", "10:00"),
         ("gds", "14:00"), ("crp", "20:00"), ("hemoculture", "02:00")])
    prescriptions.definir_bilans_demandes(
        base, sid, DEMAIN,
        [("nfs", "08:00"), ("ionogramme", "08:00"), ("crp", "08:00"),
         ("gaz_du_sang", "08:00"), ("hemoculture", "08:00")])

    # Évolution du jour, avec les sorties qui font le bilan hydrique.
    drains = evolution.drains_du_jour(base, sid, AUJ)
    mesures = {
        "rass": -2, "glasgow": 9, "pupilles": "egales_reactives",
        "fr_clinique": 20, "spo2_clinique": 96, "tete_de_lit": "oui",
        "fc": 104, "pas": 108, "pad": 56, "pam": 73,
        "diurese_24h": 850, "diurese_conservee": "non",
        "temperature": 38.2, "frissons": "absent",
    }
    for drain, volume in zip(drains, (320, 180, 90)):
        mesures[drain["cle"]] = volume
    evolution.enregistrer_journee(
        base, sid, AUJ, elements=mesures,
        textes={
            "plan_neurologique": "Sédation arrêtée hier (J1 d'AS), RASS −2, réveil en "
                                 "cours. TDM de contrôle stable.",
            "plan_respiratoire": "Réintubé à J4 après extubation accidentelle. "
                                 "Trachéotomie percutanée ce jour (canule n° 8) pour "
                                 "sevrage prolongé. VS-AI, FiO₂ 40 %.",
            "plan_hemodynamique": "Choc septique en régression, noradrénaline à 8 cc/h. "
                                  "IRA KDIGO 3 sous CVVHDF depuis J3, créatinine en baisse.",
            "plan_infectieux": "PAVM et bactériémie à Klebsiella BLSE, "
                               "J4 d'imipénème + amikacine.",
            "conduite": "Poursuite de l'antibiothérapie. Sevrage progressif des amines "
                        "et de la ventilation.",
        },
        version_attendue=evolution.obtenir_ou_creer(base, sid, AUJ)["version"],
    )
    evolution.ajouter_escarre(base, sejour_id=sid, localisation="Sacrum",
                              grade=2, date_constat=J2)
    evolution.ajouter_escarre(base, sejour_id=sid, localisation="Talon droit",
                              grade=1, date_constat=J1)

    # Avis spécialisés — huit en six jours, dont deux fois la neurochirurgie et
    # l'orthopédie : un avis n'efface jamais le précédent. La feuille imprime
    # les six plus récents ; l'écran les garde tous.
    for jour, specialite, nom, grade, texte in (
        (J5, "neurochirurgie", "Ben Salah", "senior",
         "HSD aigu 6 mm sans effet de masse : abstention, TDM de contrôle à 48 h"),
        (J5, "chirurgie_viscerale", "Gharbi", "senior",
         "Laparotomie d'hémostase, splénectomie. Drain dans la loge"),
        (J5, "orthopedie", "Mansour", "resident",
         "Fixateur externe du fémur gauche, ostéosynthèse différée"),
        (J4, "ccvt", "Trabelsi", "resident",
         "Pas d'indication chirurgicale du volet, drain à laisser en place"),
        (J3, "nephrologie", "Hamdi", "senior",
         "IRA anurique avec hyperkaliémie : indication d'EER continue"),
        (J2, "infectiologie", "Jaziri", "senior",
         "Klebsiella BLSE : imipénème 1 g × 3 + amikacine, durée 7 jours"),
        (J1, "orthopedie", "Mansour", "senior",
         "Enclouage centromédullaire programmé dès stabilisation"),
        (AUJ, "neurochirurgie", "Ben Salah", "senior",
         "TDM stable, pas de contre-indication neurochirurgicale au bloc"),
    ):
        avis.demander(base, sejour_id=sid, specialite=specialite, date_avis=jour,
                      nom=nom, grade=grade, texte=texte)

    # Transfusions : le choc hémorragique de l'admission, les plaquettes du
    # lendemain, puis deux CGR à J4 au soir. Ceux-là tombent entre l'Hb de
    # 18 h (7,2) et celle du lendemain matin (9,6) : c'est là que la feuille
    # pose sa flèche « 2 CGR ➜ ». La réserve de ce jour n'est pas encore
    # passée : elle ne s'imprime pas.
    for date_heure, produit, poches, statut in [
        (f"{J5}T17:00", "CGR (culot globulaire)", 4, "Transfusé"),
        (f"{J5}T17:00", "PFC (plasma frais congelé)", 4, "Transfusé"),
        (f"{J5}T18:00", "CUP (concentré plaquettaire)", 1, "Transfusé"),
        (f"{J4}T10:00", "CUP (concentré plaquettaire)", 1, "Transfusé"),
        (f"{J2}T22:00", "CGR (culot globulaire)", 2, "Transfusé"),
        (f"{J2}T22:00", "PFC (plasma frais congelé)", 2, "Transfusé"),
        (f"{AUJ}T07:00", "CGR (culot globulaire)", 2, "Réserve prête"),
    ]:
        explorations.enregistrer(
            base, sejour_id=sid, date_heure=date_heure, type_="transfusion",
            valeurs={"produit": produit, "nb_poches": poches, "statut": statut,
                     "complication": "Absent" if statut == "Transfusé" else None},
            operateur="Garde",
        )

    # Actes et explorations : l'imagerie de surveillance du traumatisé
    # crânien, l'échographie cardiaque du choc, la radiographie quotidienne,
    # la fibroscopie de la PAVM, l'ALR du volet costal.
    for date_heure, type_, valeurs, conclusion in [
        (f"{J5}T15:00", "tdm_cerebrale", {"lesion": "Présent",
                                          "type_lesion": "HSD aigu fronto-pariétal droit 6 mm"},
         "Pas d'effet de masse, pas d'engagement"),
        (f"{J5}T16:30", "ecg", {"rythme": "Sinusal", "fc": 128, "pr": 150, "qrs": 90,
                                "qtc": 440, "trouble_repolarisation": "Absent"},
         "Tachycardie sinusale"),
        (f"{J5}T17:30", "ett", {"fevg": 60, "itv_sa": 13, "vci": 9,
                                "vci_compliance": "Présent", "epanchement": "Absent"},
         "Hypovolémie, cœur hyperkinétique"),
        (f"{J5}T19:00", "dtc", {"ip_droit": 1.4, "ip_gauche": 1.3, "vm_droite": 38,
                                "vm_gauche": 41}, "IP limites"),
        (f"{J5}T20:00", "radio_thorax", {"syndrome": "Syndrome alvéolaire",
                                         "localisation": "Droit", "foyer": "Absent"},
         "Contusion pulmonaire droite, drain en place"),
        (f"{J4}T09:00", "dtc", {"ip_droit": 1.2, "ip_gauche": 1.1, "vm_droite": 46,
                                "vm_gauche": 48}, "Amélioration des vélocités"),
        (f"{J4}T11:00", "echo_pleuro_pulmonaire", {"epanchement_droit": "Absent",
                                                   "epanchement_gauche": "Présent",
                                                   "condensation": "Présent",
                                                   "lignes_b": "Présent"},
         "Condensation des bases, petit épanchement gauche"),
        (f"{J3}T08:00", "radio_thorax", {"syndrome": "Syndrome alvéolaire",
                                         "localisation": "Bilatéral", "foyer": "Présent",
                                         "siege_foyer": "Bases"},
         "Foyer bilatéral des bases"),
        (f"{J3}T10:00", "alr", {"technique": "Bloc serratus", "cote": "Droit",
                                "anesthesique": "Ropivacaïne 0,2 %", "volume": 20,
                                "catheter": "Présent", "vitesse": 8},
         "Cathéter laissé en place pour le volet costal"),
        (f"{J3}T12:00", "ett", {"fevg": 45, "itv_sa": 16, "debit_cardiaque": 5.8,
                                "vci": 18, "vci_compliance": "Absent", "paps": 38,
                                "tapse": 17, "rapport_vd_vg": 0.7, "epanchement": "Absent"},
         "Dysfonction VG septique modérée"),
        (f"{J3}T16:00", "dtc", {"ip_droit": 1.0, "ip_gauche": 1.0, "vm_droite": 52,
                                "vm_gauche": 55}, "Normalisé"),
        (f"{J3}T18:00", "tdm_cerebrale", {"lesion": "Présent",
                                          "type_lesion": "HSD stable 6 mm"},
         "Stable, pas de nouvelle lésion"),
        (f"{J2}T10:30", "fibroscopie", {"indication": "PAVM, contrôle après réintubation",
                                        "prelevement": "PDP + aspiration bronchique"},
         "Sécrétions purulentes des bases"),
        (f"{J1}T08:00", "radio_thorax", {"syndrome": "Syndrome alvéolaire",
                                         "localisation": "Bilatéral", "foyer": "Présent",
                                         "siege_foyer": "Bases, en régression"},
         "Amélioration"),
        (f"{J1}T11:00", "ett", {"fevg": 55, "itv_sa": 19, "debit_cardiaque": 6.2,
                                "vci": 16, "vci_compliance": "Absent", "paps": 32,
                                "tapse": 21, "epanchement": "Absent"},
         "Récupération de la fonction VG"),
        (f"{AUJ}T09:00", "ecg", {"rythme": "Sinusal", "fc": 102, "qtc": 452,
                                 "trouble_repolarisation": "Absent"},
         "Sinusal, QTc limite : à recontrôler"),
    ]:
        explorations.enregistrer(base, sejour_id=sid, date_heure=date_heure, type_=type_,
                                 valeurs=valeurs, conclusion=conclusion)
    return sid


# ===========================================================================
# La patiente : ce que le polytraumatisé ne montre pas
# ===========================================================================
#
# Une femme de 32 ans, HELLP syndrome : césarienne en urgence, hémorragie du
# post-partum, hystérectomie d'hémostase. Elle arrive du bloc à 2 h 30, est
# extubée à J2, puis fait une pyélonéphrite sur sonde. Sur elle se lisent :
# une admission chirurgicale non programmée venue du bloc, avec ses
# interventions ; une extubation programmée (« Extubé ») et l'arrêt de la
# sédation (« J2 d'AS ») ; l'oxygène à haut débit puis au masque et aux
# lunettes — des gaz sans PaO₂/FiO₂ ; une réaction transfusionnelle ; une
# infection urinaire nosocomiale ; une cure de sulfate de magnésium terminée ;
# un bloc TAP ; les relevés heure par heure et les prises de l'infirmière.

PRESCRIPTIONS_PATIENTE = [
    # (voie, produit, dose, unité, rythme, durée prévue, début)
    ("IV", "Céfotaxime", 1, "g", "x3/j", 10, J1),
    ("IV", "Paracétamol", 1, "g", "x4/j", None, J3),
    ("IV", "Néfopam", 20, "mg", "x4/j", None, J3),
    ("IV", "Oméprazole", 40, "mg", "x1/j", None, J3),
    ("IV", "Furosémide", 20, "mg", "x2/j", None, J2),
    ("IV", "Fer injectable", 200, "mg", "x1/j", 3, J1),
    ("PO", "Labétalol", 200, "mg", "x2/j", None, J2),
    ("PO", "Nifédipine", 20, "mg", "x2/j", None, J1),
    ("SC", "Enoxaparine 4000 UI", None, None, "x1/j", None, J2),
    ("AEROSOL", "Salbutamol", 5, "mg", "x3/j", None, J3),
    ("KINE", "Kinésithérapie respiratoire", None, None, "x2/j", None, J2),
    ("SOINS", "Pansement de la cicatrice", None, None, "x1/j", None, J3),
    ("SOINS", "Soins de sonde urinaire", None, None, "x2/j", None, J3),
]


def charger_patiente(base: Base, lit: int = 2) -> str:
    pid = sejours.creer_patient(
        base, matricule="DEMO-2026-002", nom_affichage="Patiente DÉMONSTRATION",
        date_naissance="1994-06-03", sexe="F", groupe_sanguin="O-",
    )
    sid = sejours.creer_sejour(
        base, patient_id=pid, date_admission=J3, heure_admission="02:30",
        lit_admission=lit, poids_kg=68, taille_cm=162, provenance_type="bloc",
        provenance_detail="Maternité — césarienne en urgence",
        traumatique=False, type_admission="chirurgie_non_programmee",
        creatinine_base=60, glasgow_initial=15, maladie_chronique_igs2="aucune",
    )
    sejours.definir_motifs(base, sid, motif_principal="hemorragie_post_partum",
                           motifs_associes=["hellp", "choc_hemorragique"])
    sejours.ajouter_intervention(base, sejour_id=sid, date_acte=J4, geste="cesarienne",
                                 geste_detail="césarienne en urgence à 34 SA, HELLP")
    sejours.ajouter_intervention(base, sejour_id=sid, date_acte=J3,
                                 geste="hysterectomie_hemostase", est_reprise=True,
                                 geste_detail="atonie utérine rebelle aux utérotoniques")
    for categorie, libelle, precision in [
        ("allergie", "Latex", "urticaire géante"),
        ("personnel", "Asthme", "sous salbutamol à la demande"),
        ("personnel", "Prééclampsie", "grossesse précédente, 2021"),
        ("chirurgical", "Appendicectomie 2010", None),
    ]:
        sejours.ajouter_antecedent(base, patient_id=pid, categorie=categorie,
                                   libelle=libelle, precision=precision)

    lignes = {}
    for voie, produit, dose, unite, rythme, duree, debut in PRESCRIPTIONS_PATIENTE:
        lignes[produit] = prescriptions.ajouter_ligne(
            base, sejour_id=sid, voie=voie, produit=produit, date_debut=debut,
            dose=dose, unite=unite, rythme=rythme, duree_prevue_jours=duree,
            indication="pyélonéphrite sur sonde à E. coli" if produit == "Céfotaxime" else None,
            horaires_override=",".join(
                str(h) for h in dom_prescription.horaires_par_defaut(produit, rythme)
            ) or None,
        )
    # Cures terminées : l'antibioprophylaxie de l'hystérectomie, et le sulfate
    # de magnésium des 24 premières heures du HELLP.
    ligne = prescriptions.ajouter_ligne(
        base, sejour_id=sid, voie="IV", produit="Amoxicilline-acide clavulanique",
        date_debut=J3, dose=1, unite="g", rythme="x3/j",
        indication="antibioprophylaxie, hystérectomie")
    prescriptions.arreter_ligne(base, ligne, date_arret=J2, motif_arret="fin de prophylaxie")
    ligne = prescriptions.ajouter_ligne(
        base, sejour_id=sid, voie="PSE", produit="Sulfate de magnésium",
        date_debut=J3, dilution="1 g/10 cc", vitesse=10, rythme="continu",
        duree_prevue_jours=2, indication="prévention de l'éclampsie")
    prescriptions.arreter_ligne(base, ligne, date_arret=J2, motif_arret="24 h révolues")
    # L'HTA du HELLP, à la seringue : la vitesse suit la pression.
    nicardipine = prescriptions.ajouter_ligne(
        base, sejour_id=sid, voie="PSE", produit="Nicardipine", date_debut=J3,
        dilution="1 mg/cc", vitesse=3, rythme="continu")
    for heure, vitesse in ((12, 2), (18, 1)):
        vitesses.regler(base, cible=vitesses.LIGNE, cible_id=nicardipine,
                        date_heure=f"{AUJ}T{heure:02d}:00", vitesse=vitesse)
    for produit, vitesse, additifs in (("Ringer Lactate", 40, []),
                                       ("Sérum glucosé 5 %", 20, [("KCl", 2)])):
        prescriptions.ajouter_ligne(
            base, sejour_id=sid, voie="ENTREES", produit=produit, date_debut=J3,
            sous_type="perfusion", vitesse=vitesse, rythme="continu",
            additifs=dom_prescription.texte_additifs(additifs))

    # Dispositifs : extubée à J2 (programmée), sédation arrêtée le même jour.
    def poser(type_, jour, site=None, **details):
        return dispositifs.poser(base, sejour_id=sid, type_=type_, date_pose=jour,
                                 site=site, details=details)
    tube = poser("intubation", J3, taille_sonde=7, reperage_cm=21)
    sedation = poser("sedation", J3, molecules="Propofol + Rémifentanil", vitesse=8)
    dispositifs.retirer(base, tube, date_retrait=J2, motif_retrait="programmee")
    dispositifs.retirer(base, sedation, date_retrait=J2)
    poser("kt_central", J3, "Sous-clavière droite", nb_voies=3)
    poser("kta", J3, "Radiale droite")
    poser("sonde_urinaire", J3, taille_sonde=14)
    poser("drain_abdominal", J3, "Pelvis", nature_drain="Douglas")
    poser("redon", J3, "Site opératoire", nature_drain="Pariétal (sous-cutané)")
    poser("voie_peripherique", J3, "Membre supérieur gauche")

    # Bilans du HELLP : plaquettes et transaminases qui remontent, une IRA
    # fonctionnelle qui se corrige, la CRP de la pyélonéphrite, la magnésémie
    # du sulfate de magnésium.
    for date_heure, valeurs in [
        (f"{J3}T02:45", {"hb": 6.2, "hte": 19, "plq": 42, "gb": 18.6, "tp": 45, "inr": 1.8,
                         "tca": 52, "na": 136, "k": 5.1, "cl": 109, "creat": 110, "uree": 7.2,
                         "asat": 420, "alat": 310, "bili": 42, "albumine": 21,
                         "glycemie": 7.8, "mg": 2.4}),
        (f"{J3}T10:00", {"hb": 8.8, "hte": 27, "plq": 68, "tp": 62, "inr": 1.4, "k": 4.6}),
        (f"{J2}T06:00", {"hb": 8.4, "hte": 26, "plq": 71, "gb": 15.2, "na": 138, "k": 4.2,
                         "cl": 106, "creat": 145, "uree": 10.8, "asat": 280, "alat": 240,
                         "bili": 30, "mg": 2.1}),
        (f"{J1}T06:00", {"hb": 8.9, "hte": 27, "plq": 96, "gb": 14.1, "na": 139, "k": 3.8,
                         "creat": 132, "uree": 9.4, "crp": 180, "pct": 3.2,
                         "asat": 150, "alat": 170}),
        (f"{AUJ}T06:00", {"hb": 9.2, "hte": 28, "plq": 134, "gb": 11.3, "tp": 82, "inr": 1.1,
                          "na": 140, "k": 3.9, "cl": 104, "creat": 98, "uree": 7.1,
                          "crp": 120, "pct": 1.4, "asat": 72, "alat": 95, "bili": 18}),
    ]:
        bilans.enregistrer_resultats(base, sejour_id=sid, date_heure=date_heure, valeurs=valeurs)
    # VAC au bloc, Optiflow après l'extubation, puis masque et lunettes : les
    # deux derniers n'ont ni FiO₂ ni rapport PaO₂/FiO₂ — la feuille le respecte.
    for heure, mode, gaz in [
        (f"{J3}T03:00", "vac", dict(ph=7.26, pao2=182, paco2=38, hco3=17, lactate=4.8,
                                    fio2=60, pep=6, fr=16, vt=420, sao2=99)),
        (f"{J2}T08:00", "optiflow", dict(ph=7.38, pao2=74, paco2=36, hco3=21, lactate=1.9,
                                         fio2=50, debit_o2=50, sao2=94)),
        (f"{J1}T07:00", "masque", dict(ph=7.41, pao2=81, paco2=37, hco3=23, lactate=1.2,
                                       debit_o2=6, sao2=96)),
        (f"{AUJ}T06:30", "lunette", dict(ph=7.42, pao2=86, paco2=38, hco3=24, lactate=0.9,
                                         debit_o2=2, sao2=97)),
    ]:
        bilans.enregistrer_gaz_du_sang(base, sid, heure, mode_ventilatoire=mode, **gaz)

    # Microbiologie : ECBU positif sur sonde, hémocultures stériles.
    ecbu = microbiologie.enregistrer(base, sejour_id=sid, date_prelevement=J1,
                                     type_prelevement="ecbu")
    microbiologie.completer(base, ecbu, {
        "resultat": "positif", "germe": "Escherichia coli",
        "antibiogramme": microbiologie.texte_antibiogramme(
            sensibles=["cefotaxime", "ceftriaxone", "amikacine", "imipeneme"],
            intermediaires=[], resistants=["amox_clav", "cotrimoxazole"],
        ),
    })
    hemoc = microbiologie.enregistrer(base, sejour_id=sid, date_prelevement=J1,
                                      type_prelevement="hemoculture")
    microbiologie.completer(base, hemoc, {"resultat": "sterile"})
    microbiologie.enregistrer(base, sejour_id=sid, date_prelevement=AUJ,
                              type_prelevement="ecbu")
    microbiologie.declarer_infection_nosocomiale(
        base, sejour_id=sid, type_="iu", date_diagnostic=J1, germe="Escherichia coli")

    # Transfusions : massive au bloc, puis un culot à J2 avec une réaction
    # fébrile — la complication se note, avec ce qu'elle a été.
    for date_heure, produit, poches, statut, complication, detail in [
        (f"{J3}T03:00", "CGR (culot globulaire)", 4, "Transfusé", "Absent", None),
        (f"{J3}T03:00", "PFC (plasma frais congelé)", 4, "Transfusé", "Absent", None),
        (f"{J3}T04:00", "CUP (concentré plaquettaire)", 2, "Transfusé", "Absent", None),
        (f"{J2}T14:00", "CGR (culot globulaire)", 1, "Transfusé", "Présent",
         "frissons et fièvre à 38,6 °C — réaction fébrile non hémolytique"),
        (f"{AUJ}T09:00", "CGR (culot globulaire)", 1, "Réserve envoyée", None, None),
    ]:
        explorations.enregistrer(
            base, sejour_id=sid, date_heure=date_heure, type_="transfusion",
            valeurs={"produit": produit, "nb_poches": poches, "statut": statut,
                     "complication": complication, "complication_detail": detail},
            operateur="Garde")

    for date_heure, type_, valeurs, conclusion in [
        (f"{J3}T03:15", "ecg", {"rythme": "Sinusal", "fc": 124, "qtc": 430,
                                "trouble_repolarisation": "Absent"}, "Tachycardie sinusale"),
        (f"{J3}T03:30", "ett", {"fevg": 65, "itv_sa": 14, "vci": 8, "vci_compliance": "Présent",
                                "epanchement": "Absent"}, "Hypovolémie, cœur normal"),
        (f"{J3}T05:00", "alr", {"technique": "Bloc TAP", "cote": "Bilatéral",
                                "anesthesique": "Ropivacaïne 0,375 %", "volume": 40,
                                "catheter": "Absent"}, "Analgésie pariétale"),
        (f"{J2}T09:00", "echo_pleuro_pulmonaire", {"epanchement_droit": "Présent",
                                                    "epanchement_gauche": "Présent",
                                                    "lignes_b": "Présent",
                                                    "condensation": "Absent"},
         "Surcharge : lignes B diffuses, épanchements bilatéraux"),
        (f"{J2}T10:00", "radio_thorax", {"syndrome": "Syndrome interstitiel",
                                         "localisation": "Bilatéral", "foyer": "Absent"},
         "Œdème pulmonaire de surcharge"),
        (f"{AUJ}T08:30", "radio_thorax", {"syndrome": "Normale", "foyer": "Absent"},
         "Régression de la surcharge"),
    ]:
        explorations.enregistrer(base, sejour_id=sid, date_heure=date_heure, type_=type_,
                                 valeurs=valeurs, conclusion=conclusion)

    for jour, specialite, nom, grade, texte in (
        (J3, "gyneco_obstetrique", "Kallel", "senior",
         "Hystérectomie d'hémostase, surveillance du drain pelvien, pas de reprise prévue"),
        (J2, "hematologie", "Mahjoub", "senior",
         "HELLP sans CIVD : surveillance des plaquettes, pas de plasmaphérèse"),
        (J1, "nephrologie", "Hamdi", "resident",
         "IRA fonctionnelle post-hémorragique, pas d'indication d'épuration"),
        (AUJ, "urologie", "Zouari", "senior",
         "Échographie rénale sans dilatation : pyélonéphrite simple, sonde à changer"),
    ):
        avis.demander(base, sejour_id=sid, specialite=specialite, date_avis=jour,
                      nom=nom, grade=grade, texte=texte)

    prescriptions.definir_bilans_demandes(
        base, sid, AUJ, [("nfs", "08:00"), ("ionogramme", "08:00"), ("crp", "20:00")])
    prescriptions.definir_bilans_demandes(
        base, sid, DEMAIN, [("nfs", "08:00"), ("ionogramme", "08:00"), ("ecbu", "08:00")])

    drains = evolution.drains_du_jour(base, sid, AUJ)
    mesures = {
        "rass": 0, "glasgow": 15, "pupilles": "egales_reactives",
        "fr_clinique": 18, "spo2_clinique": 97, "tete_de_lit": "oui",
        "fc": 96, "pas": 138, "pad": 84, "pam": 102,
        "diurese_24h": 2100, "diurese_conservee": "oui",
        "temperature": 38.3, "frissons": "absent",
    }
    for drain, volume in zip(drains, (60, 20)):
        mesures[drain["cle"]] = volume
    evolution.enregistrer_journee(
        base, sid, AUJ, elements=mesures,
        textes={
            "plan_neurologique": "Consciente, orientée, EVA 3. Pas de signe d'éclampsie.",
            "plan_respiratoire": "Extubée à J2. Lunettes 2 L/min, surcharge en régression.",
            "plan_hemodynamique": "HTA contrôlée, nicardipine en décroissance. "
                                  "Créatinine revenue à 98.",
            "plan_infectieux": "Pyélonéphrite sur sonde à E. coli, J2 de céfotaxime.",
            "conduite": "Changer la sonde urinaire. Relais oral de l'antihypertenseur.",
        },
        version_attendue=evolution.obtenir_ou_creer(base, sid, AUJ)["version"],
    )
    return sid


# --------------------------------------------------------------------------
# Ce que l'infirmière relève : constantes heure par heure, et les prises
# --------------------------------------------------------------------------

def _heures_du_jour(date_jour: str) -> list[int]:
    """Les heures déjà passées de ce jour de service (8 h → 8 h)."""
    from datetime import datetime

    heures = list(range(8, 24)) + list(range(0, 8))
    if date_jour != AUJ:
        return heures
    maintenant = datetime.now().hour
    return [h for h in range(8, 24) if h <= maintenant] if maintenant >= 8 else []


def surveillance_infirmiere(base: Base, sid: str, *, profil: dict) -> None:
    """Deux jours de relevés horaires — la veille entière et ce jour jusqu'à
    l'heure qu'il est : constantes, niveau du sac de diurèse (vidé à 6 h),
    drains, pupilles, état du drain thoracique."""
    import math

    drains_ids = [d["id"] for d in dispositifs.du_sejour(base, sid)
                  if not d["date_retrait"]
                  and d["type"] in ("drain_thoracique", "drain_abdominal", "redon")]
    thoracique = next((d["id"] for d in dispositifs.du_sejour(base, sid)
                       if d["type"] == "drain_thoracique" and not d["date_retrait"]), None)
    for jour in (J1, AUJ):
        sac = 0
        for rang, heure in enumerate(_heures_du_jour(jour)):
            onde = math.sin(rang / 3)
            valeurs = {
                "fc": round(profil["fc"] + 6 * onde),
                "pas": round(profil["pas"] + 8 * onde),
                "pad": round(profil["pad"] + 5 * onde),
                "fr": profil["fr"],
                "spo2": profil["spo2"],
                "temperature": round(profil["temperature"] + 0.4 * math.sin(rang / 5), 1),
            }
            if heure % 4 == 0:
                valeurs["glasgow"] = profil["glasgow"]
                valeurs["dextro"] = profil["dextro"]
            sac += profil["diurese_h"]
            valeurs["diurese"] = sac
            for i, drain in enumerate(drains_ids):
                valeurs[constantes.cle_drain(drain)] = (rang + 1) * (8 - 2 * i)
            textes = {
                f"{constantes.PREFIXE_PUPILLE}d": constantes.etat_pupille(*profil["pupilles"]),
                f"{constantes.PREFIXE_PUPILLE}g": constantes.etat_pupille(*profil["pupilles"]),
            }
            if thoracique:
                textes[constantes.cle_etat_drain(thoracique)] = constantes.etat_drain(
                    "siphonnage" if heure != 14 else "aspiration", heure == 14)
            jete = {"diurese"} if heure == 6 else set()
            if jete:
                sac = 0
            constantes.enregistrer(base, sid, jour, heure, valeurs, textes=textes,
                                   sacs_jetes=jete)


def prises_de_la_veille(base: Base, sid: str, *, non_donnees: dict) -> None:
    """Chaque prise de la veille notée « donné », sauf celles de
    `non_donnees` — {(produit, heure): motif} — notées « non donné » avec
    leur motif : ce sont elles qui remontent au surveillant."""
    for ligne in prescriptions.lignes_actives_le(base, sid, J1):
        if ligne["voie"] in ("PSE", "ENTREES"):
            continue
        for heure in dom_prescription.horaires_pour_rythme(
                ligne.get("rythme"), ligne.get("horaires_override")):
            motif = non_donnees.get((ligne["produit"], heure % 24))
            administrations.noter(
                base, sejour_id=sid, ligne_id=ligne["id"], date_jour=J1,
                heure_prevue=heure % 24,
                statut=administrations.NON_DONNE if motif else administrations.DONNE,
                motif_code=motif)


if __name__ == "__main__":
    base = Base()
    sid = charger(base)
    lignes = prescriptions.toutes_les_lignes(base, sid)
    print(f"Patient de démonstration chargé — séjour {sid}")
    print(f"  {len(lignes)} lignes de prescription")
    print(f"  base : {base.chemin}")
    base.fermer()
