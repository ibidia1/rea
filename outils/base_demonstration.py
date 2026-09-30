"""La base de démonstration : un service entier, séparé de la vraie base.

Lancée par l'icône « Réanimation - Démonstration » (lancer_reanimation_
demonstration.bat), avant l'application. Elle écrit dans son propre dossier
— C:\\ReaService\\demonstration par défaut, jamais dans les données du
service : un patient fictif dans la vraie base fausserait les statistiques
de la Recherche, et se confondrait un jour avec un vrai malade.

Ce qu'elle contient :

* un compte par rôle, tous avec le code « demo2026 » — pour voir chaque
  écran avec les yeux de celui qui s'en sert ;
* deux patients hospitalisés qui, à eux deux, font passer par toutes les
  fonctionnalités (voir patient_demonstration.py) : le polytraumatisé du
  lit 1 et la patiente du lit 2, avec les relevés et les prises de
  l'infirmière, et qui les soigne aujourd'hui ;
* une quarantaine de séjours clos sur les neuf derniers mois, pour que la
  Recherche — tableaux, mortalité, ventilation, antibiotiques, qualité des
  données, relances J28 — ait de quoi montrer.

La base est refaite chaque jour : les dates d'un patient de démonstration
sont relatives à aujourd'hui (J1, J2…), et une démonstration ouverte une
semaine plus tard montrerait sinon un patient sans bilan depuis sept jours.
Ce qu'on y a essayé dans la journée est gardé jusqu'au lendemain.

    python outils\\base_demonstration.py            (REA_DIR = dossier de démo)
"""

from __future__ import annotations

import os
import random
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

#: Le code de tous les comptes de démonstration. Public, et c'est voulu :
#: cette base ne contient aucun patient réel.
CODE_DEMONSTRATION = "demo2026"

COMPTES = (
    ("Démo — Administrateur", "admin"),
    ("Démo — Senior", "senior"),
    ("Démo — Résident", "resident"),
    ("Démo — Interne", "interne"),
    ("Démo — Surveillant", "surveillant"),
    ("Démo — Infirmière de jour", "infirmier"),
    ("Démo — Infirmier de nuit", "infirmier"),
)

#: Fichier témoin : la date du jour où la base a été construite.
TEMOIN = "demonstration.txt"


def _dossier() -> Path:
    from rea import config

    return config.RACINE


def a_refaire(dossier: Path, aujourdhui: date | None = None) -> bool:
    temoin = dossier / TEMOIN
    if not temoin.exists():
        return True
    return temoin.read_text(encoding="utf-8").strip() != (aujourdhui or date.today()).isoformat()


def effacer(dossier: Path) -> None:
    """Retire la base et ses sauvegardes — uniquement dans un dossier de
    démonstration, reconnu à son fichier témoin ou vide de toute base."""
    donnees = dossier / "donnees"
    if (donnees / "rea.db").exists() and not (dossier / TEMOIN).exists():
        raise RuntimeError(
            f"{dossier} contient une base qui n'est pas une base de démonstration : "
            "rien n'est effacé.")
    for sous in ("donnees", "sauvegardes"):
        if (dossier / sous).exists():
            shutil.rmtree(dossier / sous)


def comptes(base) -> dict[str, str]:
    from rea.services import utilisateurs

    return {nom: utilisateurs.creer(base, nom, role, code=CODE_DEMONSTRATION)
            for nom, role in COMPTES}


def historique(base, n: int = 40, graine: int = 2026) -> int:
    """Des séjours clos sur les neuf derniers mois — de quoi remplir la
    Recherche. Tirés au hasard, mais toujours les mêmes (graine fixe) : une
    démonstration qui change de chiffres à chaque ouverture ne se commente
    pas deux fois."""
    from rea.services import (dispositifs, evolution, microbiologie, prescriptions,
                              sejours, bilans)

    alea = random.Random(graine)
    aujourdhui = date.today()
    antibiotiques = ("Imipénème", "Céfotaxime", "Amikacine", "Vancomycine",
                     "Pipéracilline-tazobactam", "Métronidazole")
    for i in range(n):
        admission = aujourdhui - timedelta(days=270 - i * 6 - alea.randint(0, 4))
        duree = max(1, int(alea.expovariate(1 / 7)))
        sortie = admission + timedelta(days=duree)
        if sortie >= aujourdhui - timedelta(days=1):
            continue
        trauma = alea.random() < 0.4
        sexe = alea.choice("MMF")
        pid = sejours.creer_patient(
            base, matricule=f"DEMO-H{i + 1:03d}", nom_affichage=f"Séjour clos {i + 1}",
            date_naissance=f"{alea.randint(1940, 2004)}-{alea.randint(1, 12):02d}-15",
            sexe=sexe)
        sid = sejours.creer_sejour(
            base, patient_id=pid, date_admission=admission.isoformat(),
            heure_admission=f"{alea.randint(0, 23):02d}:{alea.choice((0, 15, 30, 45)):02d}",
            lit_admission=3 + i % 10, poids_kg=alea.randint(52, 105),
            taille_cm=alea.randint(155, 185),
            provenance_type=alea.choice(("urgences", "urgences", "bloc", "service",
                                         "autre_hopital")),
            traumatique=trauma, mecanisme=alea.choice(("avp_deux_roues", "avp_quatre_roues",
                                                       "chute_hauteur")) if trauma else None,
            type_admission=alea.choice(("medicale", "chirurgie_non_programmee",
                                        "chirurgie_programmee")),
            glasgow_initial=alea.randint(5, 15), creatinine_base=alea.randint(55, 110),
            maladie_chronique_igs2="aucune")
        if trauma:
            sejours.definir_regions_traumatiques(
                base, sid, alea.sample(["cranien", "thoracique", "abdominal", "peripherique"],
                                       alea.randint(1, 3)))
        else:
            sejours.definir_motifs(base, sid, motif_principal=alea.choice(
                ("choc_septique", "pneumopathie_grave", "decompensation_bpco", "avc_hemorragique",
                 "etat_de_mal", "acidocetose", "intox_medicamenteuse", "post_arret_cardiaque",
                 "envenimation_scorpionique", "hemorragie_post_partum")))
        # Ventilation : la moitié des patients, quelques extubations
        # accidentelles, quelques réintubations.
        if alea.random() < 0.55 and duree >= 2:
            fin = admission + timedelta(days=alea.randint(1, duree))
            motif = "accidentelle" if alea.random() < 0.12 else "programmee"
            tube = dispositifs.poser(base, sejour_id=sid, type_="intubation",
                                     date_pose=admission.isoformat())
            dispositifs.retirer(base, tube, date_retrait=fin.isoformat(), motif_retrait=motif)
            if (fin - admission).days >= 2 and alea.random() < 0.3:
                pneumo = microbiologie.enregistrer(
                    base, sejour_id=sid, date_prelevement=fin.isoformat(),
                    type_prelevement="pdp")
                microbiologie.completer(base, pneumo, {
                    "resultat": "positif",
                    "germe": alea.choice(("Klebsiella pneumoniae BLSE",
                                          "Acinetobacter baumannii", "Pseudomonas aeruginosa"))})
                microbiologie.declarer_infection_nosocomiale(
                    base, sejour_id=sid, type_="pavm", date_diagnostic=fin.isoformat())
        kt = dispositifs.poser(base, sejour_id=sid, type_="kt_central",
                               date_pose=admission.isoformat(), site="Jugulaire interne droite")
        dispositifs.retirer(base, kt, date_retrait=sortie.isoformat())
        # Antibiothérapie : de quoi calculer des jours de traitement.
        for produit in alea.sample(antibiotiques, alea.randint(0, 2)):
            ligne = prescriptions.ajouter_ligne(
                base, sejour_id=sid, voie="IV", produit=produit,
                date_debut=admission.isoformat(), dose=1, unite="g", rythme="x3/j")
            prescriptions.arreter_ligne(
                base, ligne, date_arret=min(sortie, admission + timedelta(
                    days=alea.randint(3, 10))).isoformat())
        # La fièvre qui cède — c'est elle que suit la courbe d'apyrexie.
        for jour in range(min(duree, 4)):
            evolution.enregistrer_elements(
                base, sid, (admission + timedelta(days=jour)).isoformat(),
                {"temperature": round(max(36.8, 39.2 - jour * alea.uniform(0.3, 0.9)), 1)})
        bilans.enregistrer_resultats(
            base, sejour_id=sid, date_heure=f"{admission.isoformat()}T08:00",
            valeurs={"creat": alea.randint(60, 320), "crp": alea.randint(5, 320),
                     "hb": round(alea.uniform(7, 14), 1), "plq": alea.randint(40, 400)})
        deces = alea.random() < 0.22
        sejours.cloturer_sejour(
            base, sid, date_heure_sortie=f"{sortie.isoformat()}T{alea.randint(9, 17):02d}:00",
            mode_sortie="deces" if deces else alea.choice(
                ("transfert_service", "transfert_service", "domicile", "reeducation")),
            complication_statut=alea.choice(("aucune", "non_renseigne")))
        # J28 : vérifié pour une partie, laissé à relancer pour l'autre.
        if not deces and duree < 28 and alea.random() < 0.6:
            sejours.noter_statut_j28(base, sid, statut=alea.choice(
                ("vivant", "vivant", "vivant", "decede", "perdu_de_vue")))
    return n


def construire(base) -> dict:
    """Remplit une base vide : comptes, deux patients, un service, un passé."""
    import patient_demonstration as demo
    from rea.services import affectations

    ids = comptes(base)
    historique(base)
    polytrauma = demo.charger(base)
    patiente = demo.charger_patiente(base, lit=2)
    demo.surveillance_infirmiere(base, polytrauma, profil=dict(
        fc=104, pas=112, pad=58, fr=20, spo2=96, temperature=38.1, glasgow=9,
        dextro=1.4, diurese_h=35, pupilles=("intermediaire", "reactive")))
    demo.surveillance_infirmiere(base, patiente, profil=dict(
        fc=96, pas=138, pad=84, fr=18, spo2=97, temperature=37.9, glasgow=15,
        dextro=1.1, diurese_h=90, pupilles=("intermediaire", "reactive")))
    demo.prises_de_la_veille(base, polytrauma,
                             non_donnees={("Lévétiracétam", 20): "pas_de_sng"})
    demo.prises_de_la_veille(base, patiente,
                             non_donnees={("Fer injectable", 8): "rupture_stock",
                                           ("Paracétamol", 14): "patient_absent"})
    jour, nuit = ids["Démo — Infirmière de jour"], ids["Démo — Infirmier de nuit"]
    for sid in (polytrauma, patiente):
        for soignant, vacation in ((jour, "matin"), (jour, "apres_midi"), (nuit, "nuit")):
            affectations.affecter(base, sejour_id=sid, soignant_id=soignant,
                                  date_jour=demo.AUJ, vacation=vacation)
    return {"polytrauma": polytrauma, "patiente": patiente, "comptes": ids}


def principal() -> int:
    dossier = _dossier()
    if not a_refaire(dossier):
        print(f"Base de démonstration du jour déjà prête : {dossier}")
        return 0
    try:
        effacer(dossier)
    except PermissionError:
        # La démonstration est déjà ouverte (fichier verrouillé) : on garde
        # celle-là plutôt que d'échouer.
        print("La démonstration est déjà ouverte : elle est gardée telle quelle.")
        return 0
    except RuntimeError as refus:
        print(refus)
        return 1
    from rea.database import Base

    # Le témoin d'abord : une construction interrompue laisse un dossier
    # reconnu comme dossier de démonstration, que le lancement suivant pourra
    # nettoyer — sans lui, il y trouverait une base inconnue et refuserait.
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / TEMOIN).write_text("en construction", encoding="utf-8")
    base = Base()
    construire(base)
    base.fermer()
    (dossier / TEMOIN).write_text(date.today().isoformat(), encoding="utf-8")
    print(f"Base de démonstration prête : {dossier}")
    print(f"Comptes : {', '.join(nom for nom, _r in COMPTES)} — code {CODE_DEMONSTRATION}")
    return 0


if __name__ == "__main__":
    if not os.environ.get("REA_DIR"):
        print("REA_DIR n'est pas défini : la démonstration n'écrit jamais dans la "
              "base du service. Lancer lancer_reanimation_demonstration.bat.")
        sys.exit(1)
    sys.exit(principal())
