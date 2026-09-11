"""Configuration du poste.

Tout ce qui peut changer d'un poste à l'autre ou d'une décision de service à
l'autre est ici, et nulle part ailleurs.
"""

from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------
# Emplacement des données (SPEC §2.2)
# --------------------------------------------------------------------------
# Sur le poste du service (Windows) : C:\ReaService
# Ailleurs (poste de développement) : ~/ReaService
# Surchargeable par la variable d'environnement REA_DIR, ce dont se servent
# les tests.

def _racine_par_defaut() -> Path:
    if os.name == "nt":
        return Path("C:/ReaService")
    return Path.home() / "ReaService"


RACINE = Path(os.environ.get("REA_DIR") or _racine_par_defaut())
DOSSIER_DONNEES = RACINE / "donnees"
DOSSIER_SAUVEGARDES = RACINE / "sauvegardes"
DOSSIER_EXPORTS = RACINE / "exports"
DOSSIER_PANCARTES = RACINE / "pancartes"
FICHIER_BASE = DOSSIER_DONNEES / "rea.db"

# Dossier des protocoles, livré avec le code (versionné, signé — SPEC §4.5)
DOSSIER_PROTOCOLES = Path(__file__).resolve().parent.parent / "protocoles"

# Le logo de l'hôpital sur la feuille imprimée. On dépose l'image sur le poste
# à cet emplacement — `C:\ReaService\logo.png` — et elle apparaît en haut à
# gauche de la pancarte, à la place du cadre pointillé « LOGO HÔPITAL ». PNG ou
# JPEG ; hors du dossier du code, donc conservée d'une réinstallation à
# l'autre. Tant qu'aucune image n'est déposée, le cadre pointillé montre où
# elle ira (demande du service, 11 septembre).
NOMS_LOGO = ("logo.png", "logo.jpg", "logo.jpeg")


# --------------------------------------------------------------------------
# Version livrée
# --------------------------------------------------------------------------
# Affichée sur l'écran d'ouverture et dans la barre latérale. Ce n'est pas un
# ornement : « je ne vois pas la barre latérale » n'a pas de réponse tant
# qu'on ignore quelle version tourne sur le poste. Le service a signalé le
# 11 septembre une barre absente, corrigée le matin même — le poste tournait
# une version d'avant, et rien à l'écran ne permettait de le dire.
#
# Un fichier et non une constante dans le code : l'installateur recopie le
# dossier tel quel, sans git, et le numéro doit survivre à la copie.

def _version() -> str:
    fichier = Path(__file__).resolve().parent.parent / "VERSION"
    try:
        return fichier.read_text(encoding="utf-8").strip() or "inconnue"
    except OSError:
        return "inconnue"


VERSION = _version()

# --------------------------------------------------------------------------
# Réseau et authentification (§2.4 — contraintes d'architecture)
# --------------------------------------------------------------------------
# Le logiciel a d'abord tourné sur un poste unique, sans réseau : la boucle
# locale suffisait, et rien du dossier n'était joignable d'ailleurs.
#
# Les infirmiers ouvrant désormais leur poste depuis leur téléphone sur le
# Wi-Fi du service, l'application doit écouter sur le réseau. C'est un
# basculement, pas un réglage : dès que l'adresse n'est plus la boucle
# locale, **le code d'accès devient obligatoire sur tous les comptes**. Les
# deux ensemble, jamais l'un sans l'autre — la règle était écrite ici depuis
# le début, et `AUTH_EXIGEE` la fait tenir toute seule.
#
# L'adresse se règle sans toucher au code, par la variable d'environnement
# `REA_HOTE` : « 127.0.0.1 » pour un poste isolé, « 0.0.0.0 » pour écouter sur
# le réseau, ou l'IP privée du serveur pour n'écouter que sur celle-là — c'est
# le réglage à préférer quand le poste a deux cartes réseau, parce qu'il rend
# le dossier invisible depuis le réseau de l'hôpital.
HOTE = os.environ.get("REA_HOTE", "127.0.0.1").strip() or "127.0.0.1"
PORT = int(os.environ.get("REA_PORT", "8501"))

#: Adresses qui ne sortent pas de la machine.
ADRESSES_LOCALES = ("127.0.0.1", "localhost", "::1")

#: Le code d'accès est-il exigé de tous ? Vrai dès que l'application est
#: joignable depuis une autre machine. Ce n'est pas un réglage indépendant :
#: c'est une conséquence, et c'est voulu — un réglage se laisse oublier.
AUTH_EXIGEE = HOTE not in ADRESSES_LOCALES

#: Conservé pour compatibilité : du code ancien lit encore ce nom.
AUTH_REQUISE = AUTH_EXIGEE

#: Essais de code ratés tolérés avant blocage temporaire du compte, et durée
#: du blocage. Sans cela, un code à quatre chiffres tombe en huit minutes
#: d'essais automatiques — mesuré, pas supposé.
ESSAIS_AVANT_BLOCAGE = 5
BLOCAGE_MINUTES = 10

#: Longueur minimale d'un code quand l'authentification est exigée.
LONGUEUR_CODE_MINIMALE = 6

#: Le compte administrateur de départ, pour qu'un service qui installe le
#: logiciel un matin ne reste pas devant un écran sans porte : sans
#: administrateur, personne ne peut créer de compte — et le bouton qui le
#: permettrait est justement celui qui manque.
#:
#: Le code est provisoire au sens strict : il est écrit ici, donc public, donc
#: il ne protège rien. Le logiciel le sait — il marque le compte
#: `code_provisoire`, réclame un vrai code à la première entrée et n'ouvre
#: aucun écran avant qu'il soit posé. Et il ne crée ce compte que sur une base
#: où **aucun compte n'a de code** : là, rien n'était protégé de toute façon.
#: Sur une base déjà protégée, la porte reste celle qui demande un code connu.
COMPTE_INITIAL_NOM = "Slah"
CODE_INITIAL = "rea123"

# --------------------------------------------------------------------------
# Sauvegardes (SPEC §2.2)
# --------------------------------------------------------------------------
INTERVALLE_SAUVEGARDE_MINUTES = 15
# Nombre de sauvegardes conservées avant rotation. Une base de service pèse
# quelques mégaoctets : garder large ne coûte rien.
SAUVEGARDES_CONSERVEES = 200

# --------------------------------------------------------------------------
# Service (SPEC §1.1)
# --------------------------------------------------------------------------
NB_LITS = 12
# Chambre 1 → lits 1-4, chambre 2 → lits 5-8, chambre 3 → lits 9-12.
LITS_PAR_CHAMBRE = 4


def chambre_du_lit(lit: int) -> int:
    """Numéro de chambre d'un lit. Reste juste si le service s'agrandit."""
    return (lit - 1) // LITS_PAR_CHAMBRE + 1


# --------------------------------------------------------------------------
# Impression (SPEC §2.2)
# --------------------------------------------------------------------------
# « A4 portrait » aujourd'hui. Le jour où l'imprimante A3 arrive, une seule
# ligne change ici — la mise en page de la pancarte suit toute seule.
FORMAT_PAGE = "A4 portrait"
FORMATS_PAGE_POSSIBLES = ("A4 portrait", "A4 landscape", "A3 landscape")

# --------------------------------------------------------------------------
# Horaires d'administration (SPEC §5.3 — question 6, tranchée en v1.3)
# --------------------------------------------------------------------------
# La journée du service commence à 8 h, pas à minuit : la relève du matin
# ouvre la feuille, et la grille horaire imprimée suit cet ordre (8 h → 7 h le
# lendemain). C'est aussi la fenêtre dans laquelle se rangent les changements
# de vitesse d'une seringue : un réglage à 2 h du matin appartient à la
# journée ouverte la veille à 8 h, pas à celle qui commence six heures plus
# tard.
HEURE_DEBUT_JOURNEE = 8

# Les horaires proposés par rythme ne sont plus ici : ils sont partis dans
# `referentiels/rythmes.json` (10 septembre 2026). L'heure d'une prise est une
# habitude de service — 8 h parce que c'est l'heure de la visite — pas une
# règle de programme, et le service doit pouvoir la revoir sans reprogrammer.
# `domaine/prescription.horaires_pour_rythme` les y lit, et elles restent
# modifiables ligne par ligne dans l'écran Prescrit.

# --------------------------------------------------------------------------
# Texte généré (SPEC §8.2 — test de collage dans le DMI à faire)
# --------------------------------------------------------------------------
# Passer à False si le DMI abîme les indices Unicode : tout le texte généré
# sort alors en PaO2, PaCO2, HCO3-.
SYMBOLES_UNICODE = True

# --------------------------------------------------------------------------
# Bilans à demander pour le lendemain (SPEC §5.2 bis)
# --------------------------------------------------------------------------
HEURE_PRELEVEMENT_DEFAUT = "08:00"
