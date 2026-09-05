"""Câblage des protocoles à l'admission (bloc 12) — jusqu'ici, aucun écran
ne les proposait : on pouvait écrire un protocole signé qui ne servait
jamais à rien.

La règle de sécurité 1 (SPEC §4.5) reste tenue par le service, pas par
l'écran : seul un protocole validé et signé est proposé, et il ne pose que
des lignes de prescription ordinaires — sans dose, modifiables, supprimables.
"""

from rea import protocoles
from rea.services import prescriptions, sejours
from rea.ui import admission


def _protocole_motif(tmp_path_factory, monkeypatch, code="choc_sept_proto", valide=True):
    dossier = tmp_path_factory.mktemp("protocoles")
    monkeypatch.setattr(protocoles.config, "DOSSIER_PROTOCOLES", dossier)
    protocoles._tous.cache_clear()
    protocoles.enregistrer(code, {
        "titre": "Choc septique — protocole initial",
        "version": "v1", "signe_par": "Pr. Test" if valide else None, "valide": valide,
        "declencheur": {"type": "motif", "valeur": "choc_septique"},
        "lignes_prescription": [
            {"voie": "IV", "produit": "Céfotaxime", "rythme": "x3/j"},
            {"voie": "PSE", "produit": "Noradrénaline"},
        ],
        "explorations_proposees": [], "consignes": ["Réévaluer à 48h"],
    })
    return protocoles.codes()


def test_un_protocole_signe_est_propose_pour_son_motif(tmp_path_factory, monkeypatch):
    _protocole_motif(tmp_path_factory, monkeypatch)
    proposes = admission._protocoles_proposes(
        traumatique=False, regions_choisies=[], motif_principal="choc_septique", motifs_associes=[],
    )
    assert [p.code for p in proposes] == ["choc_sept_proto"]


def test_un_brouillon_non_signe_n_est_jamais_propose(tmp_path_factory, monkeypatch):
    _protocole_motif(tmp_path_factory, monkeypatch, valide=False)
    proposes = admission._protocoles_proposes(
        traumatique=False, regions_choisies=[], motif_principal="choc_septique", motifs_associes=[],
    )
    assert proposes == []


def test_un_protocole_associe_est_aussi_propose_sur_un_sejour_traumatique(tmp_path_factory, monkeypatch):
    """Traumatisme thoracique associé à un choc septique : le protocole du
    motif associé doit être proposé même si le séjour est traumatique."""
    _protocole_motif(tmp_path_factory, monkeypatch)
    proposes = admission._protocoles_proposes(
        traumatique=True, regions_choisies=["thorax"],
        motif_principal=None, motifs_associes=["choc_septique"],
    )
    assert [p.code for p in proposes] == ["choc_sept_proto"]


def test_appliquer_protocole_pose_des_lignes_de_prescription_sans_dose(base, tmp_path_factory, monkeypatch):
    _protocole_motif(tmp_path_factory, monkeypatch)
    pid = sejours.creer_patient(base, matricule="M", nom_affichage="M", date_naissance=None)
    sid = sejours.creer_sejour(base, patient_id=pid, date_admission="2026-09-01", lit_admission=1)

    proto = protocoles.protocoles_pour_motif("choc_septique")[0]
    admission.appliquer_protocoles(
        base, sid, [proto], date_debut="2026-09-01", utilisateur_id=None,
    )
    lignes = prescriptions.lignes_actives(base, sid, "2026-09-01") if hasattr(prescriptions, "lignes_actives") \
        else base.requete("SELECT * FROM prescription_ligne WHERE sejour_id = ?", (sid,))
    produits = {l["produit"] for l in lignes}
    assert produits == {"Céfotaxime", "Noradrénaline"}
    assert all(l["dose"] is None for l in lignes), "un protocole ne pose jamais de dose (SPEC §3.1)"
    assert all(l["protocole_code"] == "choc_sept_proto" for l in lignes)


def test_les_lignes_posees_par_un_protocole_restent_modifiables(base, tmp_path_factory, monkeypatch):
    """Règle de sécurité 1 : toute ligne issue d'un protocole reste
    modifiable et supprimable comme une ligne ordinaire."""
    _protocole_motif(tmp_path_factory, monkeypatch)
    pid = sejours.creer_patient(base, matricule="M2", nom_affichage="M2", date_naissance=None)
    sid = sejours.creer_sejour(base, patient_id=pid, date_admission="2026-09-01", lit_admission=1)
    proto = protocoles.protocoles_pour_motif("choc_septique")[0]
    admission.appliquer_protocoles(base, sid, [proto], date_debut="2026-09-01", utilisateur_id=None)

    ligne = base.une_ligne("SELECT id FROM prescription_ligne WHERE sejour_id = ?", (sid,))
    prescriptions.arreter_ligne(base, ligne["id"], date_arret="2026-09-02")
    arretee = base.une_ligne("SELECT statut FROM prescription_ligne WHERE id = ?", (ligne["id"],))
    assert arretee["statut"] == "arretee"
