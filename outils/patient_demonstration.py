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
    avis, bilans, dispositifs, evolution, explorations, microbiologie,
    prescriptions, sejours, vitesses,
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
    # (produit, dilution, vitesse de départ, changements [(heure, vitesse)])
    ("Noradrénaline", "0,5 mg/cc", 25, [(12, 18), (16, 15), (22, 8)]),
    ("Midazolam", "1 mg/cc", 6, [(14, 4)]),
    ("Sufentanil", "10 µg/cc", 4, [(14, 3)]),
    ("Insuline", "1 UI/cc", 2, [(10, 3), (18, 2)]),
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

    for produit, dilution, vitesse, changements in SERINGUES:
        ligne = prescriptions.ajouter_ligne(
            base, sejour_id=sid, voie="PSE", produit=produit, date_debut=J5,
            dilution=dilution, vitesse=vitesse, rythme="continu",
        )
        for heure, nouvelle in changements:
            vitesses.regler(base, cible=vitesses.LIGNE, cible_id=ligne,
                            date_heure=f"{AUJ}T{heure:02d}:00", vitesse=nouvelle)

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
    poser("sedation", J5, molecules="Midazolam + Sufentanil", vitesse=6)
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
            "plan_neurologique": "Fenêtre de sédation, RASS −2. TDM de contrôle stable.",
            "plan_respiratoire": "Réintubé à J4 après extubation accidentelle. "
                                 "VS-AI, FiO₂ 40 %. Sevrage en cours.",
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


if __name__ == "__main__":
    base = Base()
    sid = charger(base)
    lignes = prescriptions.toutes_les_lignes(base, sid)
    print(f"Patient de démonstration chargé — séjour {sid}")
    print(f"  {len(lignes)} lignes de prescription")
    print(f"  base : {base.chemin}")
    base.fermer()
