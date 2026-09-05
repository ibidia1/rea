"""Atomicité des écritures et allocation des compteurs.

Deux garanties, toutes deux invérifiables à l'œil nu sur un écran :

1. une écriture et sa trace au journal partent ensemble, ou pas du tout ;
2. deux admissions simultanées ne reçoivent jamais le même identifiant.

Le service tourne sur un poste unique, mais Streamlit sert chaque onglet dans
son propre fil : deux onglets ouverts suffisent à déclencher la course.
"""

import sqlite3
import threading

import pytest

from rea.services import sejours


# -- atomicité ------------------------------------------------------------

def test_une_ecriture_ratee_ne_laisse_rien_derriere(base):
    """Une transaction interrompue ne doit laisser ni la ligne, ni le journal."""
    avant_patients = base.une_ligne("SELECT COUNT(*) AS n FROM patient")["n"]
    avant_journal = base.une_ligne("SELECT COUNT(*) AS n FROM journal")["n"]

    with pytest.raises(RuntimeError):
        with base.transaction():
            sejours.creer_patient(
                base, matricule="M-ANNULE", nom_affichage="X", date_naissance=None
            )
            raise RuntimeError("écriture interrompue")

    assert base.une_ligne("SELECT COUNT(*) AS n FROM patient")["n"] == avant_patients
    assert base.une_ligne("SELECT COUNT(*) AS n FROM journal")["n"] == avant_journal
    assert base.une_ligne(
        "SELECT 1 AS x FROM patient WHERE matricule = 'M-ANNULE'"
    ) is None


def test_admission_incomplete_ne_laisse_pas_de_patient_orphelin(base):
    """Créer le patient puis le séjour : si le séjour échoue, le patient part
    avec — sinon le tableau des lits affiche un patient qu'on ne peut ouvrir."""
    avant = base.une_ligne("SELECT COUNT(*) AS n FROM patient")["n"]

    with pytest.raises(sqlite3.IntegrityError):
        with base.transaction():
            pid = sejours.creer_patient(
                base, matricule="M-ORPHELIN", nom_affichage="Y", date_naissance=None
            )
            # Séjour rattaché à un patient inexistant : la clé étrangère refuse.
            sejours.creer_sejour(
                base, patient_id="patient-qui-n-existe-pas",
                date_admission="2026-09-01", lit_admission=1,
            )
            assert pid

    assert base.une_ligne("SELECT COUNT(*) AS n FROM patient")["n"] == avant


def test_la_ligne_et_sa_trace_au_journal_arrivent_ensemble(base):
    pid = sejours.creer_patient(
        base, matricule="M-TRACE", nom_affichage="Z", date_naissance=None
    )
    trace = base.une_ligne(
        "SELECT * FROM journal WHERE ligne_id = ? AND table_cible = 'patient'", (pid,)
    )
    assert trace is not None
    assert trace["action"] == "creation"


def test_transaction_imbriquee_ne_valide_pas_avant_la_transaction_englobante(base):
    avant = base.une_ligne("SELECT COUNT(*) AS n FROM patient")["n"]
    with pytest.raises(RuntimeError):
        with base.transaction():
            with base.transaction():
                sejours.creer_patient(
                    base, matricule="M-IMBRIQUE", nom_affichage="W", date_naissance=None
                )
            raise RuntimeError("la transaction du dessus échoue")
    assert base.une_ligne("SELECT COUNT(*) AS n FROM patient")["n"] == avant


# -- compteurs ------------------------------------------------------------

def test_identifiants_uniques_sous_admissions_simultanees(base):
    """Le cas qui motive tout : deux fils admettent en même temps."""
    erreurs: list = []

    def admettre(n: int) -> None:
        try:
            sejours.creer_patient(
                base, matricule=f"M-{n}", nom_affichage=f"P{n}", date_naissance=None
            )
        except Exception as e:  # remonté après la jonction des fils
            erreurs.append(e)

    fils = [threading.Thread(target=admettre, args=(i,)) for i in range(12)]
    for f in fils:
        f.start()
    for f in fils:
        f.join()

    assert not erreurs, erreurs
    identifiants = [
        l["identifiant_etude"] for l in base.requete("SELECT identifiant_etude FROM patient")
    ]
    assert len(identifiants) == len(set(identifiants)), "identifiant d'étude attribué deux fois"


def test_matricule_non_identifie_unique_sous_charge(base):
    """SPEC §4.1 : l'afflux de blessés non identifiés est justement le moment
    où plusieurs personnes admettent en parallèle."""
    def admettre() -> None:
        propose = sejours.prochain_matricule_non_identifie(base)
        sejours.creer_patient(
            base, matricule=propose, nom_affichage="Inconnu",
            date_naissance=None, non_identifie=True,
        )

    fils = [threading.Thread(target=admettre) for _ in range(10)]
    for f in fils:
        f.start()
    for f in fils:
        f.join()

    matricules = [
        l["matricule"] for l in base.requete("SELECT matricule FROM patient")
    ]
    assert len(matricules) == len(set(matricules)), "matricule XXX attribué deux fois"


def test_identifiant_etude_reste_unique_apres_une_suppression(base):
    """La suppression est logique : la ligne reste, donc son identifiant aussi.
    Un nouveau patient ne doit pas le reprendre."""
    p1 = sejours.creer_patient(base, matricule="A", nom_affichage="A", date_naissance=None)
    sejours.creer_patient(base, matricule="B", nom_affichage="B", date_naissance=None)
    base.supprimer_logiquement("patient", p1)

    p3 = sejours.creer_patient(base, matricule="C", nom_affichage="C", date_naissance=None)
    identifiants = {
        l["id"]: l["identifiant_etude"]
        for l in base.requete("SELECT id, identifiant_etude FROM patient")
    }
    assert identifiants[p3] not in {v for k, v in identifiants.items() if k != p3}


def test_une_correction_de_motifs_interrompue_ne_les_efface_pas(base):
    """`definir_motifs` marque tout supprimé puis repose la nouvelle liste.
    Interrompue au milieu, elle laissait le séjour sans aucun motif."""
    pid = sejours.creer_patient(base, matricule="MM", nom_affichage="MM", date_naissance=None)
    sid = sejours.creer_sejour(
        base, patient_id=pid, date_admission="2026-09-01", lit_admission=1
    )
    sejours.definir_motifs(base, sid, motif_principal="choc_septique")
    avant = base.requete(
        "SELECT code FROM sejour_motif WHERE sejour_id = ? AND supprime = 0", (sid,)
    )
    assert avant

    with pytest.raises(RuntimeError):
        with base.transaction():
            sejours.definir_motifs(base, sid, motif_principal="sdra")
            raise RuntimeError("interrompu avant la fin")

    apres = base.requete(
        "SELECT code FROM sejour_motif WHERE sejour_id = ? AND supprime = 0", (sid,)
    )
    assert apres == avant, "les motifs d'origine doivent être intacts"


def test_numero_sejour_suit_le_maximum_pas_le_compte(base):
    pid = sejours.creer_patient(base, matricule="M", nom_affichage="M", date_naissance=None)
    s1 = sejours.creer_sejour(base, patient_id=pid, date_admission="2026-09-01", lit_admission=1)
    s2 = sejours.creer_sejour(base, patient_id=pid, date_admission="2026-09-05", lit_admission=2)
    base.supprimer_logiquement("sejour", s1)
    s3 = sejours.creer_sejour(base, patient_id=pid, date_admission="2026-09-09", lit_admission=3)

    numeros = {
        l["id"]: l["numero_sejour"]
        for l in base.requete("SELECT id, numero_sejour FROM sejour WHERE patient_id = ?", (pid,))
    }
    assert numeros[s2] == 2
    assert numeros[s3] == 3, "le numéro doit suivre le plus grand déjà donné"
