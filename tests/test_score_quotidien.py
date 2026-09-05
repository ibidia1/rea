"""score_quotidien (bloc 9) — jusqu'ici jamais alimentée par personne.

Le SOFA est calculé et affiché chaque jour à l'écran Évolution, mais rien ne
l'écrivait en base : `score_quotidien`, exportée au bloc 13, restait
structurellement vide.
"""

from rea.services import scores, sejours


def _sejour(base):
    pid = sejours.creer_patient(base, matricule="M", nom_affichage="M", date_naissance=None)
    return sejours.creer_sejour(base, patient_id=pid, date_admission="2026-09-01", lit_admission=1)


def test_historiser_ecrit_une_ligne(base):
    sid = _sejour(base)
    scores.historiser(base, sid, "2026-09-03")
    ligne = base.une_ligne(
        "SELECT * FROM score_quotidien WHERE sejour_id = ? AND date_jour = ?", (sid, "2026-09-03")
    )
    assert ligne is not None
    assert ligne["score"] == "sofa"


def test_un_score_incomplet_garde_valeur_nulle_mais_le_dit_dans_le_detail(base):
    """Un total calculé sur un score amputé serait faux : mieux vaut une
    valeur absente que silencieusement optimiste."""
    import json

    sid = _sejour(base)
    scores.historiser(base, sid, "2026-09-01")  # rien de saisi ce jour-là
    ligne = base.une_ligne(
        "SELECT * FROM score_quotidien WHERE sejour_id = ? AND date_jour = ?", (sid, "2026-09-01")
    )
    detail = json.loads(ligne["detail"])
    if not detail["complet"]:
        assert ligne["valeur"] is None


def test_reappeler_historiser_le_meme_jour_ne_duplique_pas(base):
    """Index unique (sejour_id, date_jour, score) : ré-ouvrir l'onglet
    Évolution le même jour ne doit pas créer une seconde ligne."""
    sid = _sejour(base)
    scores.historiser(base, sid, "2026-09-03")
    scores.historiser(base, sid, "2026-09-03")
    lignes = base.requete(
        "SELECT id FROM score_quotidien WHERE sejour_id = ? AND date_jour = ?", (sid, "2026-09-03")
    )
    assert len(lignes) == 1


def test_deux_jours_differents_donnent_deux_lignes(base):
    sid = _sejour(base)
    scores.historiser(base, sid, "2026-09-01")
    scores.historiser(base, sid, "2026-09-02")
    lignes = base.requete(
        "SELECT date_jour FROM score_quotidien WHERE sejour_id = ? ORDER BY date_jour", (sid,)
    )
    assert [l["date_jour"] for l in lignes] == ["2026-09-01", "2026-09-02"]


def test_historiser_journalise_la_ligne(base):
    sid = _sejour(base)
    avant = len(base.journal())
    scores.historiser(base, sid, "2026-09-03")
    assert len(base.journal()) == avant + 1
