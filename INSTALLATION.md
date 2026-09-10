# Installation — Logiciel de service, Réanimation polyvalente

Ce guide part d'un PC Windows neuf et va jusqu'aux infirmiers connectés
depuis leur téléphone. Il est écrit pour être suivi ligne par ligne, sans
rien deviner. Chaque étape se termine par une **vérification** : si elle
échoue, ne pas passer à la suivante.

Trois parties, dans l'ordre :

1. [Le PC serveur, seul](#1-le-pc-serveur) — tout fonctionne déjà à ce stade
2. [Le réseau du service](#2-le-réseau-du-service) — routeur, Wi-Fi, téléphones
3. [Les autres postes de l'hôpital](#3-les-autres-postes-de-lhôpital) — accès filaire

---

## Avant de commencer — ce qui protège quoi

Une phrase à lire deux fois : **le dossier des patients est un fichier sur le
disque du PC serveur**. Les codes d'accès de l'application empêchent un
collègue d'entrer sous le nom d'un autre ; ils n'empêchent personne de partir
avec le fichier.

Ce qui protège réellement, dans l'ordre d'efficacité :

| | Contre quoi |
|---|---|
| Session Windows verrouillée par mot de passe | quelqu'un qui s'assoit devant le PC |
| Disque chiffré (BitLocker) | quelqu'un qui repart avec le PC ou le disque |
| Base **hors** de OneDrive ou d'un dossier synchronisé | une copie qui part au cloud en permanence |
| Codes d'accès sur tous les comptes | un collègue qui entre sous le nom d'un autre |
| Réseau privé séparé de celui de l'hôpital | tout l'hôpital qui lit le dossier |

Les quatre premières sont de votre côté et ne coûtent rien. La cinquième est
la partie 2 de ce guide.

---

## 1. Le PC serveur

### 1.1 Choisir l'emplacement

**Ne pas installer dans OneDrive, ni dans un dossier synchronisé.** Deux
raisons : la synchronisation verrouille des fichiers pendant que la base
écrit, et une base de patients recopiée en permanence vers un cloud est une
question qu'il vaut mieux ne pas avoir à se poser.

Emplacement recommandé :

```
C:\rea
```

### 1.2 Installer Python

Télécharger Python 3.11 ou plus récent sur <https://www.python.org/downloads/>.

À l'écran d'installation, **cocher « Add python.exe to PATH »** avant de
cliquer sur Install. C'est la case que tout le monde oublie, et sans elle
rien de ce qui suit ne fonctionne.

**Vérification.** Ouvrir l'invite de commandes (touche Windows, taper `cmd`,
Entrée) et saisir :

```
python --version
```

Doit afficher `Python 3.11.x` ou plus. Si la commande n'est pas reconnue,
réinstaller en cochant la case.

### 1.3 Récupérer le logiciel

Installer Git depuis <https://git-scm.com/download/win> (toutes les options
par défaut conviennent), puis :

```
cd C:\
git clone https://github.com/ibidia1/rea.git
cd rea
```

**Vérification.** `dir` doit montrer `rea_app.py`, `SPEC.md`, `requirements.txt`.

### 1.4 Créer l'environnement et installer les dépendances

```
cd C:\rea
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

**Vérification.** L'invite doit commencer par `(.venv)`, et :

```
python -m pytest -q
```

doit afficher `998 passed` (ou davantage). Si des tests échouent, **arrêter
ici** et le signaler : l'installation n'est pas saine.

### 1.5 Premier démarrage

```
cd C:\rea
.venv\Scripts\activate
python -m streamlit run rea_app.py
```

Le navigateur s'ouvre sur `http://localhost:8501`. À la toute première
ouverture, le logiciel demande de créer le **compte administrateur** : c'est
lui qui créera ensuite tous les autres. Mettre un code d'accès dès
maintenant, six chiffres au minimum.

**Vérification.** Le tableau des douze lits s'affiche.

### 1.6 Créer les comptes du service

Barre latérale → **Administration** → **Comptes**.

Créer un compte par personne, avec son rôle et **son code d'accès**. Le
téléphone est facultatif mais utile : il s'affiche au médecin dans le
Prescrit, pour appeler directement l'infirmier du patient.

| Rôle | Ce qu'il peut faire |
|---|---|
| **Administrateur** | tout, plus la gestion des comptes |
| **Senior** | le dossier complet, **et signer les protocoles** |
| **Résident** / **Interne** | le dossier complet, pas les protocoles |
| **Surveillant** | le dossier, la supervision, tout **sauf** les protocoles |
| **Infirmier** | voir le prescrit sans le modifier, cocher les administrations, saisir la surveillance horaire |

Un compte ne se supprime pas, il se **désactive** — sinon des années de
prescriptions deviendraient anonymes.

**Garder au moins deux comptes administrateur.** Le logiciel refuse de retirer
le dernier, mais rien ne le protège d'un code oublié. Si cela arrive quand
même, l'annexe donne la porte de secours (`outils/administrateur.py`, à lancer
sur le PC serveur).

### 1.7 L'icône de bureau

Le dépôt fournit `installer.bat` : double-cliquer dessus crée un raccourci
« Réanimation » sur le bureau, qui lance l'application sans passer par
l'invite de commandes.

### 1.8 Les sauvegardes

Le logiciel sauvegarde tout seul toutes les 15 minutes, à l'ouverture et à la
fermeture, dans `C:\rea\sauvegardes`. **Ces sauvegardes sont sur le même
disque que la base : elles ne protègent pas d'un disque en panne.**

Une fois par semaine, faire un vrai export : Administration → Sauvegardes →
**Préparer le fichier à exporter** → **Télécharger**, et copier le fichier
obtenu sur une clé USB rangée ailleurs.

**Vérification qui vaut la peine d'être faite une fois** : sur un autre PC,
installer le logiciel, importer ce fichier (Administration → Sauvegardes →
Installer une base venue d'ailleurs), et retrouver les patients. Une
sauvegarde jamais restaurée n'existe pas.

---

## 2. Le réseau du service

À la fin de cette partie, les infirmiers ouvriront le logiciel depuis leur
téléphone.

### 2.1 Le principe, et pourquoi ce montage

L'hôpital n'a pas de Wi-Fi. On crée donc **un réseau privé au service**,
séparé de celui de l'hôpital :

```
Réseau de l'hôpital ─── Ethernet 1 ─┐
                                    ├─ PC serveur REA
Routeur Wi-Fi ────────── Ethernet 2 ─┘
      )))
       │
  Téléphones, tablettes, PC portable
```

**Le PC serveur a deux cartes réseau** : l'une vers l'hôpital, l'autre vers
le routeur du service. Si le PC n'a pas besoin du réseau de l'hôpital,
**débrancher ce câble** : c'est plus simple et plus sûr, et toute la
section 2.5 devient inutile.

### 2.2 Matériel

- un petit routeur Wi-Fi (un « routeur de voyage » suffit) ;
- un câble Ethernet ;
- une prise de courant près du PC serveur.

**À faire avant d'acheter** : poser un téléphone en partage de connexion à
l'emplacement prévu du routeur et vérifier depuis la chambre la plus
éloignée que le signal passe. Les murs d'une réanimation sont en béton.

### 2.3 Configurer le routeur

Brancher le routeur sur le courant, s'y connecter (l'adresse et le mot de
passe d'usine sont sous l'appareil), puis :

- **Nom du réseau (SSID)** : quelque chose de neutre, par exemple `REA-SERVICE` ;
- **Sécurité** : WPA2 ou WPA3, avec un mot de passe **long** (une phrase de
  quatre mots vaut mieux qu'un code de huit caractères) ;
- **Ne rien brancher sur le port WAN** du routeur : ce réseau n'a pas besoin
  d'internet, et lui en donner ouvre une porte sans contrepartie ;
- **Plage d'adresses** : laisser le routeur distribuer les adresses (DHCP),
  par exemple `192.168.50.x`.

Brancher ensuite le câble Ethernet entre un port **LAN** du routeur et la
deuxième carte réseau du PC serveur.

### 2.4 Donner une adresse fixe au PC serveur

Le serveur doit garder la même adresse, sinon le raccourci des téléphones ne
fonctionne plus après un redémarrage.

Windows → Paramètres → Réseau et Internet → Ethernet (la carte reliée au
routeur) → Modifier les paramètres IP → **Manuel**, activer IPv4 :

| Champ | Valeur |
|---|---|
| Adresse IP | `192.168.50.2` |
| Longueur du préfixe / Masque | `24` (soit `255.255.255.0`) |
| **Passerelle** | **laisser vide** |
| DNS | laisser vide |

> **La passerelle vide n'est pas un oubli.** C'est l'erreur la plus fréquente
> de ce montage : avec deux passerelles, Windows en choisit une au hasard et
> l'accès au réseau de l'hôpital tombe par intermittence, sans message.

**Vérification.** Dans l'invite de commandes :

```
ipconfig
```

La carte du routeur doit montrer `192.168.50.2` et **aucune** passerelle par
défaut.

### 2.5 Empêcher les deux réseaux de communiquer

*(à ignorer si le câble de l'hôpital est débranché)*

- ne **pas** créer de pont réseau (« Connexions par pont ») ;
- ne **pas** activer le « Partage de connexion Internet » ;
- dans les propriétés de la carte reliée au routeur, décocher tout ce qui
  n'est pas nécessaire, et laisser le profil réseau sur **Privé**.

### 2.6 Lancer l'application sur le réseau du service

C'est ici que tout se joue. On donne au logiciel **l'adresse privée du
serveur** — et non `0.0.0.0`.

Créer un fichier `C:\rea\lancer_service.bat` contenant :

```bat
@echo off
cd /d C:\rea
call .venv\Scripts\activate
set REA_HOTE=192.168.50.2
python -m streamlit run rea_app.py
```

Double-cliquer dessus pour démarrer le service.

> **Pourquoi `192.168.50.2` et pas `0.0.0.0` ?** `0.0.0.0` veut dire « écoute
> sur toutes les cartes », donc **aussi sur celle de l'hôpital**. N'importe
> quel poste de l'hôpital ouvrirait alors le dossier. L'adresse privée limite
> l'écoute au réseau du service.

**Ce qui change automatiquement** : dès que l'adresse n'est plus locale, le
logiciel **exige un code d'accès sur tous les comptes**. Un compte sans code
se voit refuser l'entrée, et l'écran d'ouverture le signale. C'est voulu :
un dossier joignable depuis un téléphone sans mot de passe n'est pas un
dossier protégé.

Deux verrous s'activent également : **blocage de dix minutes après cinq
essais ratés**, et **six caractères minimum** pour les codes.

**Vérification.** Sur le PC serveur, ouvrir `http://192.168.50.2:8501` — la
page doit s'afficher.

### 2.7 Connecter les téléphones et le PC portable

Sur chaque appareil :

1. se connecter au Wi-Fi `REA-SERVICE` ;
2. ouvrir le navigateur sur **`http://192.168.50.2:8501`** ;
3. entrer son nom et son code.

**Créer un raccourci sur l'écran d'accueil** — l'application s'ouvre alors
comme une application ordinaire :

- **Android (Chrome)** : menu ⋮ → *Ajouter à l'écran d'accueil* ;
- **iPhone (Safari)** : bouton Partager → *Sur l'écran d'accueil*.

**Vérification.** Depuis un téléphone, entrer avec un compte infirmier :
l'écran « Mon poste » doit s'afficher avec la vacation en cours.

---

## 3. Les autres postes de l'hôpital

Les médecins qui travaillent depuis un bureau, sur le réseau filaire de
l'hôpital, ont besoin que le serveur écoute **aussi** de ce côté. C'est un
choix qui se pèse.

### Ce que ça implique

Faire écouter le logiciel sur le réseau de l'hôpital signifie que **tout
poste de l'hôpital peut atteindre la page d'ouverture**. Les codes d'accès
deviennent alors la seule barrière — d'où l'obligation absolue d'un code de
six chiffres sur chaque compte, sans exception.

### Comment faire

Deux façons, par ordre de préférence :

**A. Le poste du bureau rejoint le réseau du service.** Si le bureau est
proche, tirer un câble depuis le routeur du service, ou lui ajouter un
adaptateur Wi-Fi et le connecter à `REA-SERVICE`. Le dossier ne sort pas du
service. **C'est la solution à privilégier.**

**B. Écouter sur les deux réseaux.** Remplacer dans `lancer_service.bat` :

```bat
set REA_HOTE=0.0.0.0
```

Les postes de l'hôpital ouvrent alors `http://172.21.8.228:8501` (l'adresse
du serveur côté hôpital — la remplacer par la vôtre, `ipconfig` la donne).

Si vous choisissez B, faites-le **après** avoir posé un code sur tous les
comptes, et prévenez le service que la page est visible de tout l'hôpital.

---

## Annexe — Que faire quand

**L'application ne démarre pas.** Vérifier que l'invite affiche `(.venv)`.
Sinon : `cd C:\rea` puis `.venv\Scripts\activate`.

**Un téléphone n'atteint pas le serveur.** Dans l'ordre : le téléphone est-il
sur `REA-SERVICE` et non sur un autre réseau ? `ipconfig` sur le serveur
donne-t-il bien `192.168.50.2` ? Le pare-feu Windows autorise-t-il le
port 8501 sur le profil Privé ?

**Un compte est bloqué après des essais ratés.** Attendre dix minutes, ou
redémarrer l'application (les compteurs sont en mémoire).

**Un code d'accès est perdu.** Un administrateur en pose un nouveau :
Administration → Comptes → Modifier.

**Aucun compte n'a accès à Administration → Comptes.** L'écran des comptes
demande le droit `comptes`, que seul le rôle **Administrateur** possède. Trois
cas mènent à l'impasse : une base qui porte des comptes mais aucun
administrateur, le seul administrateur désactivé, ou son code perdu. Le
logiciel refuse bien de *retirer* le dernier administrateur — mais cela ne
couvre pas ces trois cas-là.

La porte de secours se lance **sur le PC serveur**, jamais depuis un
téléphone :

```
cd C:\rea
.venv\Scripts\activate
python outils\administrateur.py --lister
python outils\administrateur.py --promouvoir "Dr Karaa"
```

`--lister` montre chaque compte, son rôle, s'il est actif et s'il a un code —
et dit s'il n'y a aucun administrateur. Les autres gestes : `--creer "Nom"`
pour un nouvel administrateur, `--code "Nom"` pour poser un code, `--reactiver
"Nom"` pour un compte désactivé. Le code se tape sans s'afficher : ne jamais
le passer en argument, il resterait dans l'historique du terminal.

Si c'est un programme à part et non un bouton dans l'application, c'est
voulu : un bouton « devenir administrateur » serait atteignable depuis
n'importe quel téléphone du service. Ici il faut un accès aux fichiers du PC
serveur — celui qui permettrait de toute façon de modifier la base
directement. Chaque geste est enregistré dans le journal d'audit.

**Mettre à jour le logiciel.** Fermer l'application, puis :

```
cd C:\rea
git pull origin main
.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m pytest -q
```

Les tests doivent passer avant de relancer. La base n'est jamais touchée par
une mise à jour : les colonnes manquantes sont ajoutées automatiquement au
démarrage.
