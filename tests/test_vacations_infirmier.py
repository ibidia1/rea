"""Les trois équipes, ce qu'elles donnent, et ce qu'elles cochent (SPEC §5.8).

Le piège central de ce fichier est la **vacation de nuit**. 19 h – 7 h n'est
pas un intervalle où le début est plus petit que la fin : tout calcul naïf
(`debut <= heure < fin`) la rend vide, et l'équipe de nuit ouvre un poste sans
aucun traitement à donner. Plusieurs tests ne sont là que pour ça.

Le second piège est le **jour de rattachement** : à 2 h du matin le 10,
l'équipe de nuit est celle qui a pris son poste à 19 h le 9. Se tromper, c'est
vider l'écran de l'infirmière au milieu de sa garde.
"""

from datetime import datetime

import pytest

from rea.domaine import vacations as dom
from rea.services import (administrations, affectations, constantes,
                          prescriptions, sejours, utilisateurs)


def _sejour(base, lit=1, nom="Patient"):
    pid = sejours.creer_patient(base, matricule=f"M{lit}", nom_affichage=nom,
                                date_naissance="1970-01-01")
    return sejours.creer_sejour(base, patient_id=pid,
                                date_admission="2026-09-08", lit_admission=lit)


# --- le découpage des vacations -------------------------------------------

def test_les_trois_vacations_couvrent_les_24_heures_sans_trou_ni_recouvrement():
    couvertes = []
    for code in dom.codes():
        couvertes.extend(dom.heures(code))
    assert sorted(couvertes) == list(range(24))


def test_la_nuit_franchit_minuit(base=None):
    """Le calcul naïf `debut <= heure < fin` rendrait cette vacation vide."""
    assert dom.heures("nuit") == (19, 20, 21, 22, 23, 0, 1, 2, 3, 4, 5, 6)
    assert dom.contient("nuit", 23)
    assert dom.contient("nuit", 2)
    assert not dom.contient("nuit", 8)


@pytest.mark.parametrize("heure, attendu", [
    (7, "matin"), (12, "matin"), (13, "apres_midi"), (18, "apres_midi"),
    (19, "nuit"), (23, "nuit"), (0, "nuit"), (6, "nuit"),
])
def test_chaque_heure_tombe_dans_la_bonne_vacation(heure, attendu):
    assert dom.vacation_de(heure) == attendu


def test_la_nuit_reste_datee_du_jour_de_prise_de_poste():
    """À 2 h le 10, l'équipe de nuit est celle entrée à 19 h le 9."""
    code, jour = dom.jour_de_vacation(datetime(2026, 9, 10, 2, 0))
    assert code == "nuit"
    assert jour.isoformat() == "2026-09-09"


def test_la_fenetre_de_nuit_se_termine_le_lendemain():
    debut, fin = dom.fenetre("nuit", "2026-09-09")
    assert debut == datetime(2026, 9, 9, 19, 0)
    assert fin == datetime(2026, 9, 10, 7, 0)


# --- ce que l'équipe a à donner -------------------------------------------

def _lignes():
    return [
        {"id": "a", "produit": "Tienam", "voie": "IV", "rythme": "x3/j"},
        {"id": "b", "produit": "Noradrénaline", "voie": "PSE", "rythme": "continu"},
        {"id": "c", "produit": "Paracétamol", "voie": "IV", "rythme": "conditionnel"},
        {"id": "d", "produit": "Enoxaparine", "voie": "SC", "rythme": "x1/j",
         "horaires_override": "20"},
    ]


def test_chaque_vacation_ne_voit_que_ses_prises():
    matin = dom.prises_de_la_vacation(_lignes(), "matin")
    assert ("Enoxaparine" not in [l["produit"] for _h, l in matin])
    nuit = dom.prises_de_la_vacation(_lignes(), "nuit")
    assert ("Enoxaparine", 20) in [(l["produit"], h) for h, l in nuit]


def test_une_seringue_apparait_une_fois_a_l_ouverture_du_poste():
    """Une perfusion continue n'a pas d'heure de prise : la faire apparaître
    à chaque heure donnerait douze cases pour une seringue qu'on ne touche
    pas."""
    for code in dom.codes():
        prises = dom.prises_de_la_vacation(_lignes(), code)
        noradre = [(h, l) for h, l in prises if l["produit"] == "Noradrénaline"]
        assert len(noradre) == 1
        assert noradre[0][0] == dom.heures(code)[0]


def test_les_conditionnels_sont_a_part():
    """« Si douleur » ne se prépare pas — mais doit se connaître."""
    for code in dom.codes():
        prises = dom.prises_de_la_vacation(_lignes(), code)
        assert "Paracétamol" not in [l["produit"] for _h, l in prises]
    assert [l["produit"] for l in dom.prises_conditionnelles(_lignes())] == ["Paracétamol"]


def test_les_prises_de_nuit_sont_dans_l_ordre_du_poste():
    """23 h vient avant 2 h — c'est l'ordre du poste, pas celui des nombres."""
    lignes = [
        {"id": "x", "produit": "A", "voie": "IV", "rythme": "x1/j",
         "horaires_override": "2"},
        {"id": "y", "produit": "B", "voie": "IV", "rythme": "x1/j",
         "horaires_override": "23"},
    ]
    prises = dom.prises_de_la_vacation(lignes, "nuit")
    assert [l["produit"] for _h, l in prises] == ["B", "A"]


# --- cocher une prise ------------------------------------------------------

def test_noter_une_prise_puis_la_corriger(base):
    sid = _sejour(base)
    ligne = prescriptions.ajouter_ligne(base, sejour_id=sid, voie="IV",
                                        produit="Tienam", date_debut="2026-09-09")
    administrations.noter(base, sejour_id=sid, ligne_id=ligne,
                          date_jour="2026-09-09", heure_prevue=8,
                          statut=administrations.DONNE)
    administrations.noter(base, sejour_id=sid, ligne_id=ligne,
                          date_jour="2026-09-09", heure_prevue=8,
                          statut=administrations.NON_DONNE, motif="au bloc")

    notees = administrations.du_jour(base, sid, "2026-09-09")
    assert len(notees) == 1, "corriger ne crée pas une seconde administration"
    assert notees[(ligne, 8)]["statut"] == administrations.NON_DONNE
    assert notees[(ligne, 8)]["motif"] == "au bloc"


def test_une_prise_non_donnee_n_est_pas_une_prise_absente(base):
    """Une case vide dit « pas encore », une ligne « non donné » dit
    « décidé ». Les confondre perd la seule trace d'un traitement
    volontairement sauté."""
    sid = _sejour(base)
    ligne = prescriptions.ajouter_ligne(base, sejour_id=sid, voie="IV",
                                        produit="Tienam", date_debut="2026-09-09")
    prises = [(8, {"id": ligne, "produit": "Tienam"})]
    assert administrations.manquantes(base, sid, "2026-09-09", prises) == prises

    administrations.noter(base, sejour_id=sid, ligne_id=ligne,
                          date_jour="2026-09-09", heure_prevue=8,
                          statut=administrations.NON_DONNE, motif="au bloc")
    assert administrations.manquantes(base, sid, "2026-09-09", prises) == []


def test_decocher_remet_la_prise_en_attente(base):
    sid = _sejour(base)
    ligne = prescriptions.ajouter_ligne(base, sejour_id=sid, voie="IV",
                                        produit="Tienam", date_debut="2026-09-09")
    administrations.noter(base, sejour_id=sid, ligne_id=ligne,
                          date_jour="2026-09-09", heure_prevue=8,
                          statut=administrations.DONNE)
    administrations.effacer(base, ligne_id=ligne, date_jour="2026-09-09",
                            heure_prevue=8)
    assert administrations.du_jour(base, sid, "2026-09-09") == {}


def test_un_statut_inconnu_est_refuse(base):
    sid = _sejour(base)
    ligne = prescriptions.ajouter_ligne(base, sejour_id=sid, voie="IV",
                                        produit="Tienam", date_debut="2026-09-09")
    with pytest.raises(ValueError, match="Statut inconnu"):
        administrations.noter(base, sejour_id=sid, ligne_id=ligne,
                              date_jour="2026-09-09", heure_prevue=8,
                              statut="peut_etre")


# --- la surveillance horaire ----------------------------------------------

def test_les_constantes_se_notent_heure_par_heure(base):
    sid = _sejour(base)
    constantes.enregistrer(base, sid, "2026-09-09", 8, {"fc": 92, "temperature": 38.4})
    constantes.enregistrer(base, sid, "2026-09-09", 9, {"fc": 88})

    grille = constantes.du_jour(base, sid, "2026-09-09")
    assert grille[8]["fc"] == 92
    assert grille[8]["temperature"] == 38.4
    assert grille[9]["fc"] == 88
    assert constantes.serie(base, sid, "2026-09-09", "fc") == [(8, 92.0), (9, 88.0)]


def test_reecrire_une_heure_corrige_au_lieu_de_dupliquer(base):
    sid = _sejour(base)
    constantes.enregistrer(base, sid, "2026-09-09", 8, {"fc": 92})
    constantes.enregistrer(base, sid, "2026-09-09", 8, {"fc": 110})
    assert constantes.serie(base, sid, "2026-09-09", "fc") == [(8, 110.0)]


def test_une_valeur_videe_est_effacee_pas_mise_a_zero(base):
    """Une FC à 0 est un arrêt cardiaque, pas une case qu'on a vidée."""
    sid = _sejour(base)
    constantes.enregistrer(base, sid, "2026-09-09", 8, {"fc": 92})
    constantes.enregistrer(base, sid, "2026-09-09", 8, {"fc": None})
    assert constantes.du_jour(base, sid, "2026-09-09").get(8, {}) == {}


# --- qui s'occupe de qui ---------------------------------------------------

def test_un_infirmier_prend_ses_malades_et_le_surveillant_les_voit(base):
    sid = _sejour(base, lit=3, nom="Ben Ali")
    uid = utilisateurs.creer(base, "Inf. Amel", "infirmier")
    affectations.affecter(base, sejour_id=sid, soignant_id=uid,
                          date_jour="2026-09-09", vacation="matin")

    miens = affectations.du_soignant(base, uid, "2026-09-09", "matin")
    assert [p["lit_admission"] for p in miens] == [3]

    vue_surveillant = affectations.du_jour(base, "2026-09-09", "matin")
    assert vue_surveillant[0]["soignant"] == "Inf. Amel"
    assert vue_surveillant[0]["nom_affichage"] == "Ben Ali"


def test_affecter_deux_fois_ne_cree_qu_une_affectation(base):
    sid = _sejour(base)
    uid = utilisateurs.creer(base, "Inf. Amel", "infirmier")
    a = affectations.affecter(base, sejour_id=sid, soignant_id=uid,
                              date_jour="2026-09-09", vacation="matin")
    b = affectations.affecter(base, sejour_id=sid, soignant_id=uid,
                              date_jour="2026-09-09", vacation="matin")
    assert a == b
    assert len(affectations.du_jour(base, "2026-09-09", "matin")) == 1


def test_une_vacation_inconnue_est_refusee(base):
    sid = _sejour(base)
    uid = utilisateurs.creer(base, "Inf. Amel", "infirmier")
    with pytest.raises(ValueError, match="Vacation inconnue"):
        affectations.affecter(base, sejour_id=sid, soignant_id=uid,
                              date_jour="2026-09-09", vacation="apres_minuit")


def test_les_deux_pressions_tombent_sur_la_meme_rangee():
    """L'écran affiche les constantes deux par rangée. Une systolique en haut
    d'une rangée et la diastolique en bas de la suivante, c'est une inversion
    par garde."""
    from rea.services import constantes as cst

    cles = [c for c, _l, _u in cst.CLES]
    rangees = [cles[i:i + 2] for i in range(0, len(cles), 2)]
    assert ["pas", "pad"] in rangees


# --- pourquoi une prise n'a pas été donnée ---------------------------------
#
# « Il arrive qu'il manque le médicament, ou qu'on ne puisse pas le donner —
# pas encore de sonde pour le per os » (demande du service, 10 septembre).
#
# Le point qui compte : ces motifs-là ne sont pas des cases cochées, ce sont
# des choses à faire. Un antibiotique qui manque à 8 h manquera à 16 h si
# personne ne le commande.

def test_un_motif_de_rupture_demande_une_action_de_la_pharmacie():
    assert administrations.action_du_motif("rupture_stock") == "pharmacie"
    assert administrations.action_du_motif("pas_de_sng") == "abord"
    assert administrations.action_du_motif("etat_clinique") == "medical"


def test_un_motif_qui_se_regle_seul_ne_remonte_a_personne():
    """Patient au bloc, à jeun : rien à faire, et une liste qui contient tout
    ne se lit plus."""
    assert administrations.action_du_motif("patient_absent") is None
    assert administrations.action_du_motif("a_jeun") is None
    assert administrations.action_du_motif(None) is None
    assert administrations.action_du_motif("motif_inconnu") is None


def test_les_non_donnes_a_traiter_remontent_au_surveillant(base):
    sid = _sejour(base, lit=4, nom="Ben Ali")
    manquant = prescriptions.ajouter_ligne(base, sejour_id=sid, voie="IV",
                                           produit="Tienam",
                                           date_debut="2026-09-09")
    au_bloc = prescriptions.ajouter_ligne(base, sejour_id=sid, voie="PO",
                                          produit="Amlodipine",
                                          date_debut="2026-09-09")
    administrations.noter(base, sejour_id=sid, ligne_id=manquant,
                          date_jour="2026-09-09", heure_prevue=8,
                          statut=administrations.NON_DONNE,
                          motif_code="rupture_stock")
    administrations.noter(base, sejour_id=sid, ligne_id=au_bloc,
                          date_jour="2026-09-09", heure_prevue=8,
                          statut=administrations.NON_DONNE,
                          motif_code="patient_absent")

    a_traiter = administrations.a_traiter(base, "2026-09-09")
    assert [l["produit"] for l in a_traiter] == ["Tienam"], (
        "seul ce qui demande une action remonte"
    )
    assert a_traiter[0]["action"] == "pharmacie"
    assert a_traiter[0]["matricule"] == "M4"
    assert a_traiter[0]["lit_admission"] == 4
    assert "rupture" in a_traiter[0]["libelle_motif"].lower()


def test_le_medecin_voit_tous_les_non_donnes_de_son_patient(base):
    """Y compris ceux qui ne demandent aucune action : prescrire à nouveau
    sans savoir que la dose n'est pas passée, c'est croire à un échec du
    traitement."""
    sid = _sejour(base)
    ligne = prescriptions.ajouter_ligne(base, sejour_id=sid, voie="PO",
                                        produit="Amlodipine",
                                        date_debut="2026-09-09")
    administrations.noter(base, sejour_id=sid, ligne_id=ligne,
                          date_jour="2026-09-09", heure_prevue=8,
                          statut=administrations.NON_DONNE,
                          motif_code="pas_de_sng",
                          motif="SNG posée à 11 h")

    vues = administrations.non_donnees_du_sejour(base, sid, "2026-09-09")
    assert len(vues) == 1
    assert vues[0]["libelle_motif"] == "Pas de sonde nasogastrique en place"
    assert vues[0]["motif"] == "SNG posée à 11 h"
    assert vues[0]["action"] == "abord"


def test_le_texte_libre_ne_remplace_pas_le_motif(base):
    """« Rupture » tapé à la main ne se compte pas et ne remonte à personne."""
    sid = _sejour(base)
    ligne = prescriptions.ajouter_ligne(base, sejour_id=sid, voie="IV",
                                        produit="Tienam",
                                        date_debut="2026-09-09")
    administrations.noter(base, sejour_id=sid, ligne_id=ligne,
                          date_jour="2026-09-09", heure_prevue=8,
                          statut=administrations.NON_DONNE,
                          motif="rupture de stock")
    assert administrations.a_traiter(base, "2026-09-09") == []


def test_tous_les_motifs_du_referentiel_ont_une_action_lisible():
    """Une action mal orthographiée dans le fichier ferait disparaître le
    motif de la vue du surveillant, sans erreur nulle part."""
    from rea import listes

    for entree in listes.MOTIFS_NON_ADMINISTRATION:
        action = entree[2] if len(entree) > 2 else "aucune"
        assert action in set(administrations.ACTIONS) | {"aucune"}, (
            f"« {entree[0] } » porte l'action inconnue « {action} »"
        )
