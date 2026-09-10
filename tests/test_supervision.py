"""L'écran du surveillant : ce qui a changé, et ce qu'il faut commander
(SPEC §5.9).

Le problème que ce module résout : aujourd'hui le surveillant relit chaque
pancarte pour repérer les nouveautés de la garde. Il en manque, et un
antibiotique commencé à 4 h du matin n'est commandé qu'à midi.

Ce que les tests protègent : la phrase doit se lire sans décoder — produit,
posologie, durée, patient, matricule — et **les arrêts comptent autant que les
ajouts**, parce qu'un antibiotique arrêté est une commande à ne pas passer.
"""

from rea.services import prescriptions, sejours, supervision


def _patient(base, nom="Ben Ali", matricule="123456", lit=3):
    pid = sejours.creer_patient(base, matricule=matricule, nom_affichage=nom,
                                date_naissance="1970-01-01")
    return sejours.creer_sejour(base, patient_id=pid,
                                date_admission="2026-09-08", lit_admission=lit)


def test_un_ajout_se_lit_en_une_phrase_avec_le_matricule(base):
    sid = _patient(base)
    prescriptions.ajouter_ligne(
        base, sejour_id=sid, voie="IV", produit="Tienam", dose=1, unite="g",
        rythme="x3/j", duree_prevue_jours=7, date_debut="2026-09-09",
    )
    evenements = supervision.nouveautes(base)
    assert len(evenements) == 1
    texte = evenements[0]["texte"]
    assert texte.startswith("Ajout de Tienam 1g x3/j pendant 7 jours")
    assert "Ben Ali" in texte
    assert "matricule 123456" in texte
    assert "lit 3" in texte


def test_un_arret_apparait_aussi(base):
    """Un antibiotique arrêté est une commande à ne pas passer."""
    sid = _patient(base)
    ligne = prescriptions.ajouter_ligne(
        base, sejour_id=sid, voie="IV", produit="Tienam", dose=1, unite="g",
        rythme="x3/j", date_debut="2026-09-09",
    )
    prescriptions.arreter_ligne(base, ligne, date_arret="2026-09-10")

    genres = [e["genre"] for e in supervision.nouveautes(base)]
    assert "ajout" in genres and "arret" in genres
    arret = next(e for e in supervision.nouveautes(base) if e["genre"] == "arret")
    assert arret["texte"].startswith("Arrêt de Tienam")


def test_les_nouveautes_sont_du_plus_recent_au_plus_ancien(base):
    sid = _patient(base)
    for produit in ("Premier", "Deuxieme"):
        prescriptions.ajouter_ligne(base, sejour_id=sid, voie="IV",
                                    produit=produit, date_debut="2026-09-09")
    quand = [e["quand"] for e in supervision.nouveautes(base)]
    assert quand == sorted(quand, reverse=True)


def test_la_fenetre_de_jours_est_respectee(base):
    """Une ligne posée il y a longtemps n'est pas une nouveauté."""
    sid = _patient(base)
    ligne = prescriptions.ajouter_ligne(base, sejour_id=sid, voie="IV",
                                        produit="Ancien", date_debut="2026-08-01")
    base.mettre_a_jour("prescription_ligne", ligne, {})
    base.requete("UPDATE prescription_ligne SET cree_le = ? WHERE id = ?",
                 ("2026-08-01T08:00:00", ligne))
    assert supervision.nouveautes(base, depuis_jours=2) == []


def test_les_medicaments_a_commander_excluent_les_soins(base):
    """Soins, kiné et surveillance ne se commandent pas : les faire figurer
    noierait ce qu'il faut vraiment aller chercher."""
    sid = _patient(base)
    prescriptions.ajouter_ligne(base, sejour_id=sid, voie="IV", produit="Tienam",
                                date_debut="2026-09-09")
    prescriptions.ajouter_ligne(base, sejour_id=sid, voie="SOINS",
                                produit="Pansement", date_debut="2026-09-09")

    patients = supervision.medicaments_par_patient(base, "2026-09-09")
    assert len(patients) == 1
    produits = [l["produit"] for l in patients[0]["lignes"]]
    assert produits == ["Tienam"]
    assert patients[0]["matricule"] == "123456"
    assert patients[0]["lit"] == 3


def test_un_patient_sans_traitement_n_apparait_pas(base):
    _patient(base)
    assert supervision.medicaments_par_patient(base, "2026-09-09") == []


def test_un_patient_sorti_n_est_plus_dans_la_liste(base):
    """On ne commande pas pour un lit vide."""
    sid = _patient(base)
    prescriptions.ajouter_ligne(base, sejour_id=sid, voie="IV", produit="Tienam",
                                date_debut="2026-09-09")
    sejours.cloturer_sejour(base, sid, date_heure_sortie="2026-09-09",
                            mode_sortie="domicile")
    assert supervision.medicaments_par_patient(base, "2026-09-09") == []
    assert supervision.sejours_ouverts(base) == []
