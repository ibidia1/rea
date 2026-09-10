"""Seize soignants qui écrivent en même temps (SPEC §2.4).

Le service prévoit une soixantaine de comptes et une quinzaine de terminaux
actifs. La question posée était : est-ce que SQLite tient ? La réponse mesurée
est oui, et très largement — mais la mesure a trouvé autre chose, qui n'avait
rien à voir avec SQLite.

**Lire puis écrire n'est pas atomique hors transaction.** Les services notaient
« s'il existe une ligne, la mettre à jour, sinon l'insérer » sans transaction :
deux fils lisent tous les deux « rien de noté » et insèrent tous les deux, le
second heurte l'index unique, et **la note est perdue** — une administration
non enregistrée alors que l'infirmière a vu le bouton devenir vert.

Ce n'est pas une hypothèse de laboratoire : le cas le plus probable n'est pas
deux infirmières sur le même patient, c'est **un seul doigt qui appuie deux
fois** sur un téléphone quand le réseau traîne.

Mesuré le 10 septembre 2026 : onze échecs sur 36 587 écritures en 45 secondes,
tous de cette forme. Après correction : zéro sur 55 409.

Ces tests-ci sont la version courte, faite pour tourner en une seconde. Le test
de charge complet est dans le journal de `SPEC.md`.
"""

import importlib
import threading


def _services(nom):
    return importlib.import_module(f"rea.services.{nom}")


def _sejour(base, lit=1):
    sejours = _services("sejours")
    pid = sejours.creer_patient(base, matricule=f"M{lit}", nom_affichage=f"P{lit}",
                                date_naissance="1970-01-01")
    return sejours.creer_sejour(base, patient_id=pid, date_admission="2026-09-01",
                                lit_admission=lit)


def _en_parallele(action, fois=24):
    """Lance `action` sur autant de fils, et rend les exceptions levées."""
    erreurs: list[BaseException] = []
    depart = threading.Barrier(fois)

    def tourner():
        depart.wait()          # tous partent au même instant, pour se heurter
        try:
            action()
        except BaseException as e:      # noqa: BLE001
            erreurs.append(e)

    fils = [threading.Thread(target=tourner) for _ in range(fois)]
    for f in fils:
        f.start()
    for f in fils:
        f.join(timeout=30)
    return erreurs


# -- la même note, écrite par plusieurs mains au même instant --------------

def test_deux_doigts_sur_la_meme_administration(base):
    """Le doigt qui appuie deux fois sur un réseau lent. Sans transaction, la
    seconde écriture heurtait l'index unique et la note était perdue."""
    administrations = _services("administrations")
    prescriptions = _services("prescriptions")
    sid = _sejour(base)
    ligne = prescriptions.ajouter_ligne(base, sejour_id=sid, voie="IV",
                                        produit="Imipénème", date_debut="2026-09-01")

    erreurs = _en_parallele(lambda: administrations.noter(
        base, sejour_id=sid, ligne_id=ligne, date_jour="2026-09-09",
        heure_prevue=8, statut=administrations.DONNE))

    assert erreurs == [], erreurs
    lignes = base.requete(
        "SELECT id FROM administration WHERE ligne_id = ? AND supprime = 0", (ligne,))
    assert len(lignes) == 1          # une prise, une ligne


def test_deux_mains_sur_la_meme_constante(base):
    constantes = _services("constantes")
    sid = _sejour(base)
    erreurs = _en_parallele(lambda: constantes.enregistrer(
        base, sid, "2026-09-09", 8, {"fc": 90.0, "pas": 120.0, "diurese": 250.0}))
    assert erreurs == [], erreurs
    lignes = base.requete(
        "SELECT cle FROM constante_horaire WHERE sejour_id = ? AND heure = 8 "
        "AND supprime = 0", (sid,))
    assert len(lignes) == 3          # fc, pas, diurèse — une chacune


def test_deux_mains_sur_le_meme_prelevement(base):
    prelevements = _services("prelevements")
    sid = _sejour(base)
    erreurs = _en_parallele(lambda: prelevements.noter(
        base, sejour_id=sid, date_jour="2026-09-09", examen_code="nfs",
        heure_prevue=8, statut=prelevements.FAIT))
    assert erreurs == [], erreurs
    lignes = base.requete(
        "SELECT id FROM prelevement WHERE sejour_id = ? AND supprime = 0", (sid,))
    assert len(lignes) == 1


def test_deux_infirmiers_prennent_le_meme_malade(base):
    """Deux téléphones qui touchent « Prendre » au même instant ne doivent pas
    créer deux affectations : le surveillant lirait deux soignants pour un
    lit."""
    affectations = _services("affectations")
    utilisateurs = _services("utilisateurs")
    sid = _sejour(base)
    uid = utilisateurs.creer(base, "Inf. Amel", "infirmier")
    erreurs = _en_parallele(lambda: affectations.affecter(
        base, sejour_id=sid, soignant_id=uid, date_jour="2026-09-09",
        vacation="matin"))
    assert erreurs == [], erreurs
    assert len(affectations.du_sejour(base, sid, "2026-09-09")) == 1


def test_la_meme_molecule_apprise_par_deux_prescripteurs(base):
    """Deux médecins prescrivent « Tienam 500 » au même instant : une seule
    entrée au catalogue, sinon la molécule ne se compterait jamais avec
    elle-même."""
    medicaments = _services("medicaments")
    erreurs = _en_parallele(lambda: medicaments.apprendre(base, "Tienam 500"))
    assert erreurs == [], erreurs
    assert len(medicaments.locales(base)) == 1


# -- la configuration qui rend tout cela possible --------------------------

def test_la_base_est_en_wal_avec_un_delai_d_attente(base):
    """WAL laisse lire pendant qu'on écrit — c'est ce qui permet à quinze
    téléphones de consulter la pancarte pendant qu'un seizième la coche. Et le
    délai d'attente évite qu'une écriture abandonne parce qu'une autre tenait
    le verrou un instant."""
    assert list(base.une_ligne("PRAGMA journal_mode").values())[0] == "wal"
    assert list(base.une_ligne("PRAGMA busy_timeout").values())[0] >= 5000


def test_une_transaction_bloque_aussi_les_lecteurs(base):
    """La nuance que le mode WAL seul ne dit pas.

    SQLite en WAL laisse lire pendant qu'on écrit. Mais cette application pose
    un verrou Python autour de **tous** ses accès — lectures comprises — pour
    tenir le « lire puis écrire » des services. Pendant une transaction, un
    autre fil ne lit donc pas : il attend.

    Ce n'est pas un défaut tant que les transactions durent onze millisecondes.
    C'en devient un dès qu'on met un calcul, une impression ou une attente
    réseau dans un `with base.transaction()` — ce qui bloquerait alors tout le
    service, et pas seulement les autres écrivains. C'est la règle que ce test
    grave.
    """
    sid = _sejour(base)
    constantes = _services("constantes")
    lecture_faite = threading.Event()

    def lire():
        constantes.du_jour(base, sid, "2026-09-09")
        lecture_faite.set()

    fil = threading.Thread(target=lire, daemon=True)
    with base.transaction():
        constantes.enregistrer(base, sid, "2026-09-09", 8, {"fc": 90.0})
        fil.start()
        # Le lecteur attend la fin de la transaction : il n'a pas fini.
        assert not lecture_faite.wait(timeout=0.4)

    # Sitôt la transaction refermée, il passe.
    assert lecture_faite.wait(timeout=5), "le lecteur n'a jamais été libéré"
    fil.join(timeout=5)
    assert len(constantes.du_jour(base, sid, "2026-09-09")) == 1
