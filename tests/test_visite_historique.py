"""Trois jours côte à côte à la visite (SPEC §6).

Une valeur seule ne dit pas si le rein décroche ; deux ne disent pas s'il
décroche ou s'il remonte. Une créatinine à 152 après 196 rassure — après 196
puis 120, elle inquiète, et la conduite du jour n'est pas la même (demande du
service, 10 septembre).

Et le tableau des constantes horaires descend en bas de l'écran avec **sa
propre date** : on relit la nuit d'avant-hier sans perdre le prescrit qu'on
est en train de lire.
"""

import importlib
import pathlib


def _services(nom):
    return importlib.import_module(f"rea.services.{nom}")


def _source(module: str) -> str:
    chemin = pathlib.Path(__file__).resolve().parent.parent / "rea" / "ui" / f"{module}.py"
    return chemin.read_text(encoding="utf-8")


def _sejour(base):
    sejours = _services("sejours")
    pid = sejours.creer_patient(base, matricule="M1", nom_affichage="P1",
                                date_naissance="1970-01-01")
    return sejours.creer_sejour(base, patient_id=pid, date_admission="2026-09-01",
                                lit_admission=1)


# -- la biologie sur trois jours -------------------------------------------

def test_les_trois_derniers_jours_renseignes_pas_du_calendrier(base):
    """On ne prélève pas tous les jours en réanimation. Trois colonnes dont
    deux vides n'apprendraient rien : on rend les trois derniers jours qui
    portent vraiment un prélèvement."""
    bilans = _services("bilans")
    sid = _sejour(base)
    for jour, creat in (("2026-09-02", 196.0), ("2026-09-05", 170.0),
                        ("2026-09-08", 152.0), ("2026-09-09", 140.0)):
        bilans.enregistrer_resultats(base, sid, f"{jour}T08:00", {"creat": creat})
    jours, matrice = bilans.tableau_derniers_jours(base, sid, ["creat"], "2026-09-09")
    assert jours == ["2026-09-05", "2026-09-08", "2026-09-09"]
    assert matrice["creat"]["2026-09-09"] == 140.0


def test_l_historique_ne_depasse_pas_le_jour_regarde(base):
    """À la visite on peut relire une journée passée. Y faire apparaître un
    bilan postérieur montrerait l'avenir du patient."""
    bilans = _services("bilans")
    sid = _sejour(base)
    bilans.enregistrer_resultats(base, sid, "2026-09-05T08:00", {"creat": 170.0})
    bilans.enregistrer_resultats(base, sid, "2026-09-09T08:00", {"creat": 140.0})
    jours, _m = bilans.tableau_derniers_jours(base, sid, ["creat"], "2026-09-06")
    assert jours == ["2026-09-05"]


def test_une_seule_valeur_par_jour_la_derniere(base):
    """Deux prélèvements le même jour ne font pas deux colonnes : à la visite
    on commente celui du matin qui a décidé de la journée, et le détail
    heure par heure reste dans l'écran Bilans."""
    bilans = _services("bilans")
    sid = _sejour(base)
    bilans.enregistrer_resultats(base, sid, "2026-09-09T06:00", {"k": 2.6})
    bilans.enregistrer_resultats(base, sid, "2026-09-09T18:00", {"k": 3.4})
    jours, matrice = bilans.tableau_derniers_jours(base, sid, ["k"], "2026-09-09")
    assert jours == ["2026-09-09"]
    assert matrice["k"]["2026-09-09"] == 3.4


def test_sans_aucun_bilan_l_historique_est_vide_pas_en_erreur(base):
    bilans = _services("bilans")
    sid = _sejour(base)
    jours, matrice = bilans.tableau_derniers_jours(base, sid, ["creat"], "2026-09-09")
    assert jours == [] and matrice == {}


# -- les gaz du sang --------------------------------------------------------

def test_un_gaz_par_jour_le_dernier(base):
    """Un patient qui a quatre gaz dans la journée remplirait sinon la
    colonne de sa seule matinée, et on perdrait comment il a bougé depuis
    avant-hier."""
    bilans = _services("bilans")
    sid = _sejour(base)
    for date_heure, pao2 in (("2026-09-08T06:00", 70.0), ("2026-09-09T06:00", 80.0),
                             ("2026-09-09T14:00", 88.0), ("2026-09-09T22:00", 95.0)):
        bilans.enregistrer_gaz_du_sang(base, sid, date_heure, pao2=pao2)
    gaz = bilans.derniers_gaz_du_sang(base, sid, "2026-09-09")
    assert [g["date_heure"] for g in gaz] == ["2026-09-08T06:00", "2026-09-09T22:00"]


def test_les_gaz_s_arretent_au_jour_regarde(base):
    bilans = _services("bilans")
    sid = _sejour(base)
    bilans.enregistrer_gaz_du_sang(base, sid, "2026-09-08T06:00", pao2=70.0)
    bilans.enregistrer_gaz_du_sang(base, sid, "2026-09-10T06:00", pao2=95.0)
    gaz = bilans.derniers_gaz_du_sang(base, sid, "2026-09-08")
    assert len(gaz) == 1 and gaz[0]["date_heure"] == "2026-09-08T06:00"


def test_au_plus_trois_colonnes(base):
    """Debout, sur un portable posé sur un chariot : au-delà de trois
    colonnes le tableau ne se lit plus, il se déchiffre."""
    bilans = _services("bilans")
    sid = _sejour(base)
    for jour in ("05", "06", "07", "08", "09"):
        bilans.enregistrer_gaz_du_sang(base, sid, f"2026-09-{jour}T06:00", pao2=80.0)
        bilans.enregistrer_resultats(base, sid, f"2026-09-{jour}T06:00", {"creat": 150.0})
    assert len(bilans.derniers_gaz_du_sang(base, sid, "2026-09-09")) == 3
    jours, _m = bilans.tableau_derniers_jours(base, sid, ["creat"], "2026-09-09")
    assert len(jours) == 3


# -- le tableau des constantes, daté à part --------------------------------

def test_les_constantes_ont_leur_propre_date_a_la_visite():
    """Les deux questions ne tombent pas le même jour : on regarde le prescrit
    d'aujourd'hui en se demandant comment s'est passée la nuit d'avant-hier.
    Une seule date en haut de l'écran obligerait à perdre l'un pour lire
    l'autre.
    """
    source = _source("visite")
    assert "visite_jour_constantes_" in source
    # Distincte de la clé du sélecteur principal, sinon les deux bougeraient
    # ensemble et l'écart n'existerait pas.
    assert 'key="visite_jour"' in source


def test_le_tableau_des_constantes_est_en_bas_et_pleine_largeur():
    """Vingt-quatre colonnes serrées dans la demi-largeur de droite
    obligeaient à faire défiler le tableau pour lire la nuit."""
    source = _source("visite")
    position_colonnes = source.index("gauche, droite = st.columns")
    position_tableau = source.index("surveillance.bloc_du_jour(")
    assert position_tableau > position_colonnes
    # Rendu hors du `with droite:` — donc sur toute la largeur de la page.
    assert "st.divider()\n    _surveillance(sejour, date_jour_str)" in source


def test_l_alerte_se_lit_sur_un_champ_qui_existe_vraiment():
    """Le bug que la recette navigateur a trouvé et que la suite ne voyait pas.

    L'écran lisait `v.id` sur une `Variation`, qui porte `analyte`. Rien dans
    les tests ne touchait ce chemin : l'écran entier tombait — biologie,
    infectieux et plans avec elle — et seule l'ouverture réelle de la Visite
    le montrait.
    """
    from dataclasses import fields

    bilans = _services("bilans")
    noms = {f.name for f in fields(bilans.Variation)}
    assert {"analyte", "alerte"} <= noms
    source = _source("visite")
    assert "v.analyte: v.alerte" in source
    assert "v.id" not in source
