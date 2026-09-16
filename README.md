# Logiciel de service — Réanimation polyvalente

| Document | Pour qui |
|---|---|
| **[INSTALLATION.md](INSTALLATION.md)** | installer le poste serveur, le routeur du service, l'accès depuis les téléphones et les autres postes |
| **[GUIDE_UTILISATION.md](GUIDE_UTILISATION.md)** | se servir du logiciel, un guide par métier |
| **[SPEC.md](SPEC.md)** | la référence du projet et son journal des versions |

## État actuel

**v2.5** — tous les blocs codables de la feuille de route sont faits, et la
feuille imprimée est celle du service (maquette A3 de Kairouan, dans
`modeles/` : c'est un fichier, il se remplace sans reprogrammer).

### Organisation du code

Le code est rangé **par couches**, chacune dans son paquet sous `rea/` :

- `rea/models/` — tout le calcul médical (scores, cohérence, prescription,
  règles). Ne connaît ni la base ni les écrans : c'est ce qui le rend
  vérifiable.
- `rea/services/` — la seule couche qui écrit, toujours dans une transaction
  et toujours avec une trace au journal.
- `rea/database/` — la couche SQLite (une connexion, un fichier `rea.db`) et le
  schéma (`schema.sql`).
- `rea/printing/` — remplit la maquette imprimée avec un dossier qu'on lui
  donne ; ne lit rien par lui-même.
- `rea/ui/` — un module par écran ; `rea_app.py` ne fait plus que le montage.

Ces séparations sont vérifiées par `tests/test_architecture.py`, pas seulement
écrites ici.

*Soin quotidien* : Lits, Admission, Prescrit (toutes voies, bilan hydrique,
impression), Explorations et actes (dispositifs invasifs avec compteurs de
jours calculés ; transfusion à étapes réserve → prête → transfusé), Bilans
(saisie, cinétique, microbiologie, texte généré), Évolution (rappels, scores,
quatre plans), Visite (la pancarte à l'écran, sans papier), Sortie.

*Feuille imprimée* : personnalisable sans reprogrammer — déposer un `logo.png`
(racine du programme, ou `C:\ReaService\` pour le remplacer sur un poste) et
régler `NOM_RESPONSABLE` dans `rea/config.py` (imprimé sous le logo).

*Analyse* : écran **Recherche** — cohortes, tableau descriptif STROBE, taux
d'infections liées aux dispositifs, consommation d'antibiotiques, export
pseudonymisé avec dictionnaire des données, gel de base.

*Administration* : sauvegardes et **restauration**, journal d'audit
consultable, version de chaque référentiel, de chaque protocole et de chaque
jeu de règles, **éditeur** pour ajouter ou modifier une règle d'aide ou un
protocole pré-rempli depuis un formulaire (sans toucher au JSON).

Les listes codées (`referentiels/`), les règles d'aide et les barèmes de score
(`regles/`) sont des **fichiers JSON versionnés** : les modifier ne demande pas
de reprogrammer le logiciel.

### Ce qui reste, et qui ne dépend pas du développement

- **à faire valider par un senior** : bornes de normalité des bilans, barème
  IGS II, seuils des rappels, correspondances LOINC — tout est marqué non
  validé à l'écran ;
- **à compléter depuis leur source officielle** : la CIM-10 (58 codes de
  démarrage seulement) et la table des DDD de l'OMS ;
- le dossier de protection des données et le test sur patients réels.

Le détail exact figure dans le journal des versions de SPEC.md et dans
l'audit §10 de FEUILLE_DE_ROUTE.md.

## Installation sur le poste du service (Windows)

Pas de commande à taper : **un double-clic sur `installer.bat`**, une seule
fois. Il fait quatre choses, dans l'ordre, en affichant ce qu'il fait :

1. il cherche Python — et **l'installe** s'il manque, par winget ou par
   téléchargement direct ;
2. il copie le programme dans **`C:\ReaService\programme`**, hors de
   OneDrive : une base SQLite dans un dossier synchronisé se corrompt en
   silence ;
3. il installe les composants du logiciel (il faut Internet à cette étape) ;
4. il pose **deux icônes** sur le Bureau, puis ouvre le logiciel :
   - **Réanimation - Local** — le poste pour lui seul (`127.0.0.1`), sans code
     d'accès ;
   - **Réanimation - Serveur** — ce poste sert la réanimation au réseau du
     service : il **détecte tout seul** son adresse, l'affiche pour les
     téléphones et les autres postes, et **exige alors un code** sur tous les
     comptes (voir INSTALLATION.md §2).

Ensuite, au quotidien : **l'icône du Bureau** (Local le plus souvent). Elle
ouvre le navigateur toute seule. **Ne pas fermer la fenêtre noire** pendant
l'usage : la fermer arrête le logiciel.

Si quelque chose manque — pas d'Internet, pas le droit d'installer un
programme — l'installateur le dit en clair et s'arrête sans rien abîmer. On
corrige, on relance le même fichier, et ce qui est déjà fait n'est pas
refait.

Le logiciel tourne alors **entièrement en local** : aucune donnée ne sort du
poste (voir *Emplacement des données* ci-dessous et SPEC §2.2).

## Installation (poste de développement)

```bash
python -m venv .venv
source .venv/bin/activate   # ou .venv\Scripts\activate sous Windows
pip install -r requirements.txt
```

## Lancer l'application

```bash
streamlit run rea_app.py
```

Ouvre `http://localhost:8501`. Choisir ou créer un utilisateur, puis
cliquer sur un lit libre pour admettre un patient.

## Lancer les tests

```bash
python -m pytest
```

## Emplacement des données

Par défaut : `~/ReaService` (Linux/Mac) ou `C:\ReaService` (Windows), voir
`rea/config.py`. Surchargeable avec la variable d'environnement `REA_DIR`
(utilisée par les tests pour ne jamais toucher aux données réelles).
