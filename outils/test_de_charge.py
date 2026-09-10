"""Seize soignants qui écrivent en même temps, pour de vrai (SPEC §2.4).

À lancer **avant la mise en service**, et après toute reprise de la couche
d'écriture. Passe par les services — pas par du SQL brut — pour mesurer ce que
l'application fait réellement : constantes horaires, administrations,
prélèvements.

    REA_DIR=/tmp/essai DUREE=60 ECRIVAINS=16 python outils/test_de_charge.py

Ce qu'il faut regarder, dans l'ordre :

* **erreurs = 0.** Une seule suffit à condamner la version : une écriture qui
  échoue est une administration non enregistrée alors que l'infirmière a vu le
  bouton devenir vert. C'est ainsi qu'a été trouvée, le 10 septembre 2026, une
  course entre lecture et écriture dans les services — onze pertes sur 36 587
  écritures.
* **la latence p99**, qui dit ce que ressent le plus malchanceux.
* **integrity_check**, qui doit rendre « ok ».

Le débit, lui, n'est pas la question : la limite du service n'est pas SQLite
mais le temps de rendu de Streamlit. Ce test dit seulement que la base n'est
pas le goulot.

Utilise sa propre base (REA_DIR) — ne jamais le lancer sur celle du service.
"""
import os, random, statistics, sys, threading, time
sys.path.insert(0, "/home/user/rea")

from rea.db import obtenir_base
from rea.services import (administrations, constantes, prelevements,
                          prescriptions, sejours)

DUREE = float(os.environ.get("DUREE", "60"))
ECRIVAINS = int(os.environ.get("ECRIVAINS", "16"))

base = obtenir_base()
base.arreter_sauvegardes_periodiques() if hasattr(base, "arreter_sauvegardes_periodiques") else None

# 12 lits, comme le service.
lits = []
for i in range(1, 13):
    pid = sejours.creer_patient(base, matricule=f"CH-{i:03d}",
                                nom_affichage=f"Patient {i}",
                                date_naissance="1970-01-01")
    sid = sejours.creer_sejour(base, patient_id=pid,
                               date_admission="2026-09-01", lit_admission=i)
    ligne = prescriptions.ajouter_ligne(base, sejour_id=sid, voie="IV",
                                        produit="Imipénème", date_debut="2026-09-01",
                                        rythme="x3", dose=1, unite="g")
    prescriptions.definir_bilans_demandes(base, sid, "2026-09-09",
                                          [("nfs", "08:00"), ("crp", "08:00")])
    lits.append((sid, ligne))

latences, erreurs, ecrites = [], [], [0]
verrou_mesure = threading.Lock()
stop = threading.Event()


def soignant(numero: int) -> None:
    alea = random.Random(numero)
    tour = 0
    while not stop.is_set():
        sid, ligne = alea.choice(lits)
        tour += 1
        debut = time.perf_counter()
        try:
            geste = tour % 3
            if geste == 0:
                constantes.enregistrer(
                    base, sid, "2026-09-09", alea.randrange(24),
                    {"fc": float(alea.randrange(60, 130)),
                     "pas": float(alea.randrange(90, 150)),
                     "diurese": float(alea.randrange(50, 900))})
            elif geste == 1:
                administrations.noter(
                    base, sejour_id=sid, ligne_id=ligne, date_jour="2026-09-09",
                    heure_prevue=alea.choice([8, 16, 24]),
                    statut=administrations.DONNE)
            else:
                prelevements.noter(
                    base, sejour_id=sid, date_jour="2026-09-09",
                    examen_code=alea.choice(["nfs", "crp"]),
                    heure_prevue=8, statut=prelevements.FAIT)
            duree = (time.perf_counter() - debut) * 1000
            with verrou_mesure:
                latences.append(duree)
                ecrites[0] += 1
        except Exception as e:                      # noqa: BLE001
            with verrou_mesure:
                erreurs.append(f"{type(e).__name__}: {e}")
        time.sleep(0.001)


fils = [threading.Thread(target=soignant, args=(i,), daemon=True)
        for i in range(ECRIVAINS)]
depart = time.perf_counter()
for f in fils:
    f.start()
time.sleep(DUREE)
stop.set()
for f in fils:
    f.join(timeout=10)
ecoule = time.perf_counter() - depart

latences.sort()
def pct(p):
    return latences[int(len(latences) * p)] if latences else 0.0

print(f"\n{ECRIVAINS} écrivains simultanés, {ecoule:.0f} s")
print(f"  écritures réussies : {ecrites[0]}  ({ecrites[0]/ecoule:.0f}/s)")
print(f"  erreurs            : {len(erreurs)}")
for e in sorted(set(erreurs))[:5]:
    print("     ", e)
print(f"  latence médiane    : {statistics.median(latences):.1f} ms")
print(f"  latence p95        : {pct(0.95):.1f} ms")
print(f"  latence p99        : {pct(0.99):.1f} ms")
print(f"  latence maximale   : {latences[-1]:.1f} ms")

# Intégrité : ce qui est en base doit correspondre à ce qu'on a écrit.
n_const = base.une_ligne("SELECT COUNT(*) n FROM constante_horaire WHERE supprime=0")["n"]
n_adm = base.une_ligne("SELECT COUNT(*) n FROM administration WHERE supprime=0")["n"]
n_prel = base.une_ligne("SELECT COUNT(*) n FROM prelevement WHERE supprime=0")["n"]
print(f"  lignes en base     : {n_const} constantes · {n_adm} administrations · {n_prel} prélèvements")
integre = base.une_ligne("PRAGMA integrity_check")
print(f"  integrity_check    : {list(integre.values())[0]}")
print(f"  journal_mode       : {list(base.une_ligne('PRAGMA journal_mode').values())[0]}")
print(f"  busy_timeout       : {list(base.une_ligne('PRAGMA busy_timeout').values())[0]} ms")
print(f"  synchronous        : {list(base.une_ligne('PRAGMA synchronous').values())[0]}")
