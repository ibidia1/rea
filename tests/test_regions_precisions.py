"""Une précision libre par région traumatique — la région seule ne dit rien
de la lésion réelle (« Trauma crânien » ne dit pas s'il y a un hématome
extra-dural ou une simple plaie du scalp)."""

from rea.services import sejours


def _sejour(base, traumatique=True):
    pid = sejours.creer_patient(base, matricule="M", nom_affichage="M", date_naissance=None)
    return sejours.creer_sejour(
        base, patient_id=pid, date_admission="2026-09-01", lit_admission=1,
        traumatique=traumatique,
    )


def test_precision_posee_avec_la_region(base):
    sid = _sejour(base)
    sejours.definir_regions_traumatiques(
        base, sid, ["cranien"], precisions={"cranien": "Hématome extra-dural droit"},
    )
    detail = sejours.regions_traumatiques_detail(base, sid)
    assert detail == [{"region": "cranien", "precision": "Hématome extra-dural droit"}]


def test_region_sans_precision_reste_none(base):
    sid = _sejour(base)
    sejours.definir_regions_traumatiques(base, sid, ["thoracique"])
    detail = sejours.regions_traumatiques_detail(base, sid)
    assert detail[0]["precision"] is None


def test_reposer_une_region_met_a_jour_sa_precision(base):
    sid = _sejour(base)
    sejours.definir_regions_traumatiques(
        base, sid, ["cranien"], precisions={"cranien": "Première hypothèse"},
    )
    sejours.definir_regions_traumatiques(
        base, sid, ["cranien"], precisions={"cranien": "Embarrure pariétale confirmée au TDM"},
    )
    detail = sejours.regions_traumatiques_detail(base, sid)
    assert len(detail) == 1
    assert detail[0]["precision"] == "Embarrure pariétale confirmée au TDM"


def test_regions_traumatiques_simple_reste_une_liste_de_codes(base):
    """`regions_traumatiques()` sert au calcul du polytraumatisme : elle ne
    doit pas changer de forme quand une précision est posée."""
    sid = _sejour(base)
    sejours.definir_regions_traumatiques(
        base, sid, ["cranien", "thoracique"],
        precisions={"cranien": "Hématome extra-dural"},
    )
    assert set(sejours.regions_traumatiques(base, sid)) == {"cranien", "thoracique"}
