"""Un motif non traumatique peut s'associer à un séjour traumatique.

Exemple donné par le service : traumatisme thoracique + embolie pulmonaire +
SDRA + acidocétose diabétique — la région tient lieu de motif principal, mais
les complications non traumatiques doivent rester posées à côté, pas
effacées parce que `traumatique=True`.
"""

from rea.services import sejours


def _sejour_traumatique(base):
    pid = sejours.creer_patient(base, matricule="M", nom_affichage="M", date_naissance=None)
    return sejours.creer_sejour(
        base, patient_id=pid, date_admission="2026-09-01", lit_admission=1, traumatique=True,
    )


def test_definir_motifs_garde_les_associes_meme_sans_principal(base):
    sid = _sejour_traumatique(base)
    sejours.definir_motifs(
        base, sid, motif_principal=None,
        motifs_associes=["embolie_pulmonaire", "sdra", "acidocetose"],
    )
    motifs = {m["code"] for m in sejours.motifs_du_sejour(base, sid)}
    assert motifs == {"embolie_pulmonaire", "sdra", "acidocetose"}
    assert all(not m["principal"] for m in sejours.motifs_du_sejour(base, sid))


def test_motif_principal_none_et_associes_vides_efface_tout(base):
    sid = _sejour_traumatique(base)
    sejours.definir_motifs(base, sid, motif_principal="sdra", motifs_associes=[])
    sejours.definir_motifs(base, sid, motif_principal=None, motifs_associes=[])
    assert sejours.motifs_du_sejour(base, sid) == []


def test_modifier_admission_traumatique_garde_les_motifs_associes(base):
    sid = _sejour_traumatique(base)
    sejours.modifier_admission(
        base, sid,
        date_admission="2026-09-01", provenance_type=None, provenance_detail=None,
        poids_kg=None, taille_cm=None, creatinine_base=None, type_admission=None,
        maladie_chronique_igs2=None, traumatique=True,
        regions_traumatiques_choisies=["thorax"],
        motifs_associes=["embolie_pulmonaire", "sdra"],
    )
    motifs = {m["code"] for m in sejours.motifs_du_sejour(base, sid)}
    assert motifs == {"embolie_pulmonaire", "sdra"}
    regions = sejours.regions_traumatiques(base, sid)
    assert "thorax" in regions


def test_modifier_admission_bascule_traumatique_efface_le_principal_pas_les_associes(base):
    """Le séjour passe de non-traumatique à traumatique : le motif principal
    non traumatique n'a plus de sens (la région le remplace), mais un motif
    associé fourni au même moment doit être posé."""
    pid = sejours.creer_patient(base, matricule="M2", nom_affichage="M2", date_naissance=None)
    sid = sejours.creer_sejour(
        base, patient_id=pid, date_admission="2026-09-01", lit_admission=2, traumatique=False,
    )
    sejours.definir_motifs(base, sid, motif_principal="choc_septique")

    sejours.modifier_admission(
        base, sid,
        date_admission="2026-09-01", provenance_type=None, provenance_detail=None,
        poids_kg=None, taille_cm=None, creatinine_base=None, type_admission=None,
        maladie_chronique_igs2=None, traumatique=True,
        regions_traumatiques_choisies=["cranien"],
        motifs_associes=["sdra"],
    )
    motifs = {m["code"] for m in sejours.motifs_du_sejour(base, sid)}
    assert motifs == {"sdra"}, "le motif principal d'origine doit disparaître, mais pas l'associé"
