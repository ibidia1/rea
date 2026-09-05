"""Trace du franchissement d'un garde-fou de cohérence (bloc 4).

Un avertissement « impossible » se franchit à un second clic — c'est voulu, le
médecin garde le dernier mot. Ce qui ne l'était pas : que rien dans le dossier
n'en garde la trace. Seul `bilan_resultat` avait une colonne `saisie_forcee` ;
les cinq autres écrans qui laissent forcer n'en ont aucune.
"""


import pytest

from rea.domaine import coherence
from rea.services import sejours
from rea.ui import contexte


def _avertissements_impossibles():
    """Un vrai avertissement « impossible » : sortie avant l'admission."""
    a = coherence.verifier_sejour(
        date_admission="2026-09-10", date_sortie="2026-09-01"
    )
    assert any(x.gravite == "impossible" for x in a), "le cas de test doit être bloquant"
    return a


# -- la trace elle-même ---------------------------------------------------

def test_le_forcage_laisse_une_trace_au_journal(base):
    base.journaliser_forcage(
        cible="sejour",
        avertissements=_avertissements_impossibles(),
        utilisateur_id=None,
        ligne_id="sej-1",
    )
    trace = base.une_ligne(
        "SELECT * FROM journal WHERE action = 'forcage_coherence'"
    )
    assert trace is not None
    assert trace["table_cible"] == "sejour"
    assert trace["ligne_id"] == "sej-1"


def test_la_trace_dit_quel_avertissement_a_ete_franchi(base):
    """Sans le message, la trace dirait qu'on a forcé, pas ce qu'on a forcé."""
    avertissements = _avertissements_impossibles()
    base.journaliser_forcage(cible="sejour", avertissements=avertissements)
    trace = base.une_ligne("SELECT details FROM journal WHERE action = 'forcage_coherence'")
    assert avertissements[0].message in trace["details"]
    assert "impossible" in trace["details"]


def test_le_forcage_apparait_dans_le_journal_consultable(base):
    """L'écran Administration lit le journal — le forçage doit y remonter."""
    base.journaliser_forcage(cible="dispositif", avertissements=_avertissements_impossibles())
    actions = [
        l["action"] for l in base.requete("SELECT action FROM journal ORDER BY date_heure DESC")
    ]
    assert "forcage_coherence" in actions


# -- le garde-fou de l'écran ----------------------------------------------

class _FauxStreamlit:
    """Le strict nécessaire pour faire tourner `contexte.controle` hors
    Streamlit : l'état de session et les quatre façons d'afficher."""

    def __init__(self):
        self.session_state = {}
        self.messages = []

    def error(self, message, icon=None):
        self.messages.append(("error", message))

    def warning(self, message, icon=None):
        self.messages.append(("warning", message))

    def info(self, message, icon=None):
        self.messages.append(("info", message))


@pytest.fixture
def ecran(base, monkeypatch):
    faux = _FauxStreamlit()
    monkeypatch.setattr(contexte, "st", faux)
    monkeypatch.setattr(contexte, "base", lambda: base)
    monkeypatch.setattr(contexte, "utilisateur_id", lambda: None)
    return faux


def _forcages(base) -> int:
    return base.une_ligne(
        "SELECT COUNT(*) AS n FROM journal WHERE action = 'forcage_coherence'"
    )["n"]


def test_sans_avertissement_on_enregistre_sans_rien_tracer(base, ecran):
    assert contexte.controle("cle", [], cible="sejour") is True
    assert _forcages(base) == 0


def test_un_avertissement_improbable_passe_sans_second_clic(base, ecran):
    improbables = coherence.verifier_sejour(
        date_admission="2026-09-01", date_naissance="1890-01-01"
    )
    assert improbables and not any(a.gravite == "impossible" for a in improbables)
    assert contexte.controle("cle", improbables, cible="sejour") is True
    assert _forcages(base) == 0, "un improbable n'est pas un forçage"


def test_un_impossible_demande_un_second_clic_puis_se_trace(base, ecran):
    avertissements = _avertissements_impossibles()

    # premier clic : refusé, rien d'écrit
    assert contexte.controle("sortie", avertissements, cible="sejour") is False
    assert _forcages(base) == 0
    assert ("info", "Cliquer à nouveau sur le bouton pour enregistrer malgré tout.") in [
        (n, m) for n, m in ecran.messages
    ]

    # second clic : accepté, et tracé
    assert contexte.controle("sortie", avertissements, cible="sejour") is True
    assert _forcages(base) == 1


def test_deux_ecrans_qui_forcent_laissent_deux_traces_distinctes(base, ecran):
    avertissements = _avertissements_impossibles()
    for cle, cible in (("sortie", "sejour"), ("retrait_x", "dispositif")):
        contexte.controle(cle, avertissements, cible=cible)
        contexte.controle(cle, avertissements, cible=cible)
    cibles = [
        l["table_cible"]
        for l in base.requete(
            "SELECT table_cible FROM journal WHERE action = 'forcage_coherence'"
        )
    ]
    assert sorted(cibles) == ["dispositif", "sejour"]


def test_le_bilan_garde_en_plus_sa_colonne_saisie_forcee(base):
    """La colonne existante ne disparaît pas : elle sert aux statistiques,
    là où relire le journal serait absurde."""
    pid = sejours.creer_patient(base, matricule="B", nom_affichage="B", date_naissance=None)
    sid = sejours.creer_sejour(
        base, patient_id=pid, date_admission="2026-09-01", lit_admission=1
    )
    base.inserer(
        "bilan_resultat",
        {
            "sejour_id": sid, "date_heure": "2026-09-02T06:00",
            "analyte": "k", "valeur_num": 99.0, "saisie_forcee": 1,
        },
    )
    ligne = base.une_ligne(
        "SELECT saisie_forcee FROM bilan_resultat WHERE sejour_id = ?", (sid,)
    )
    assert ligne["saisie_forcee"] == 1
