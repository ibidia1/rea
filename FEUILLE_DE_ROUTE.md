# FEUILLE DE ROUTE MODULAIRE
## Logiciel de service — Réanimation polyvalente

**Version 1.0 — 3 septembre 2026**
Annexe à SPEC.md. À lire avec lui, pas à sa place.

Ce document fixe **l'ordre de construction** et **les règles d'isolation entre
couches**. Le SPEC dit *quoi*. Celui-ci dit *dans quel ordre* et *sans casser
quoi*.

> **État d'application au 27 septembre 2026** — voir §10 : audit complet du
> code, ce qui a été corrigé pendant l'audit, et ce qui reste à faire.

---

## 1. PRINCIPE DE CLASSEMENT

Chaque bloc reçoit deux notes de 1 à 5.

**Utilité** — ce que le service perd si le bloc n'existe pas.

| Note | Signification |
|---|---|
| 5 | Le logiciel n'a pas de raison d'être sans ça |
| 4 | Gain de temps quotidien mesurable, ou valeur scientifique décisive |
| 3 | Confort réel, réclamé par les utilisateurs |
| 2 | Utile un jour, pas maintenant |
| 1 | Élégant, sans conséquence |

**Complexité** — heures, risque de régression, dépendances extérieures.

| Note | Signification |
|---|---|
| 1 | Quelques heures, aucune dépendance |
| 2 | Une session, périmètre fermé |
| 3 | Deux à trois sessions, touche plusieurs écrans |
| 4 | Dépend d'une décision extérieure ou d'un référentiel à valider |
| 5 | Chantier, à ne lancer qu'une fois le reste stable |

**Ordre de construction = utilité décroissante, complexité croissante à utilité
égale.**

Une exception assumée, détaillée en §5 : certaines choses coûtent **zéro** si
elles sont câblées dès le premier jour et **très cher** si elles sont ajoutées
après. Elles montent dans l'ordre même si leur bénéfice est lointain.

---

## 2. RÈGLES DE MODULARITÉ

L'objectif : que le bloc 11 puisse être écrit sans rouvrir le bloc 2.

### 2.1 Les six couches

```
  ┌──────────────────────────────────────────────┐
  │  C5  AIDES        règles déclaratives        │  ← lit, ne modifie rien
  ├──────────────────────────────────────────────┤
  │  C4  ANALYSE      export, stats, cohortes    │  ← lecture seule
  ├──────────────────────────────────────────────┤
  │  C3  RENDU        pancarte, évolution, CR    │  ← lecture seule
  ├──────────────────────────────────────────────┤
  │  C2  MÉTIER       prescription, bilans...    │  ← seule couche qui écrit
  ├──────────────────────────────────────────────┤
  │  C1  RÉFÉRENTIELS listes, codes, protocoles  │  ← données, pas du code
  ├──────────────────────────────────────────────┤
  │  C0  NOYAU        schéma, audit, sauvegarde  │  ← ne change presque jamais
  └──────────────────────────────────────────────┘
```

**Les dépendances vont vers le bas, jamais vers le haut.** Une couche ne connaît
que celles en dessous d'elle. Le rendu ne sait pas que les statistiques
existent. Les statistiques ne savent pas que la pancarte existe.

### 2.2 Les cinq règles qui rendent ça vrai

**R1 — Une seule couche écrit.**
C2 est la seule à créer ou modifier des lignes cliniques. C3, C4 et C5 lisent.
Un bug d'affichage ne peut donc jamais corrompre une donnée.

**R2 — Les référentiels sont des fichiers, pas du code.**
Listes de motifs, gestes chirurgicaux, examens de bilan, correspondances
CIM-10 / LOINC / ATC, protocoles de pré-remplissage : tout vit dans des fichiers
versionnés et datés, chargés au démarrage. Ajouter un antibiotique à la liste ne
doit jamais demander de toucher un `.py`.

Chaque fichier porte un **numéro de version affiché sur la pancarte imprimée**
(déjà exigé au SPEC §4.5).

**R3 — Le rendu ne calcule rien.**
Le compteur de jours, le rapport P/F, le volume des entrées, l'âge : tout est
calculé dans C2 et exposé sous forme de valeur. La pancarte, l'évolution et le
compte rendu affichent une valeur déjà faite. Trois consommateurs, un seul
calcul, donc un seul endroit à corriger et un seul endroit à tester.

**R4 — Les aides sont déclaratives.**
Une règle d'alerte est une ligne de fichier, pas une fonction :

```yaml
- id: reeval_atb_72h
  quand: ligne_prescription.categorie == "antibiotique" && jour == 3
  message: "Réévaluation de l'antibiothérapie — J3"
  action: signaler          # jamais "appliquer"
  source: "Protocole ATB service, v2026-09, signé Pr X"
```

Ajouter une alerte = ajouter une ligne. Zéro risque de régression sur la
prescription.

**R5 — L'export ne lit que le schéma, jamais l'écran.**
Aucune fonction d'export ne doit dépendre de la manière dont une donnée est
affichée. Cette règle est ce qui permettra d'écrire FHIR ou OMOP plus tard sans
toucher au reste.

### 2.3 Test de modularité

Avant de clore un bloc, poser la question : **« si je supprime ce module, est-ce
que le reste démarre encore ? »**
Si la réponse est non pour un module au-dessus de C2, la séparation est ratée.

---

## 3. TABLEAU DE PRIORISATION

| # | Bloc | Couche | Utilité | Complexité | Heures | Statut |
|---|---|---|---|---|---|---|
| 0 | Noyau : schéma, UUID, audit, sauvegarde | C0 | 5 | 3 | 5-7 | Prérequis |
| 1 | Référentiels + chargeur de listes | C1 | 5 | 2 | 3-4 | Prérequis |
| 2 | Lits, admission, identité, sélecteur d'utilisateur | C2 | 5 | 2 | 6-8 | Prérequis |
| 3 | **Prescription + compteurs + pancarte J+1 + impression A4** | C2/C3 | **5** | 3 | 16-20 | **Cœur** |
| 4 | Contrôles de cohérence à la saisie | C2 | 4 | 1 | 2-3 | Ratio max |
| 5 | Évolution quotidienne générée + copier | C3 | 4 | 2 | 5-7 | |
| 6 | Bilans : intégration du HTML existant + gaz du sang | C2/C3 | 4 | 2 | 6-8 | |
| 7 | Rappels temporels + FAST HUG (moteur de règles) | C5 | 4 | 2 | 4-5 | |
| 8 | Sortie + compte rendu généré | C2/C3 | 4 | 2 | 4-6 | |
| 9 | Socle recherche : IGS II, SOFA, ventilation, devenir | C2 | 4 | 3 | 6-8 | |
| 10 | Courbes de cinétique + bornes de normalité | C3 | 3 | 2 | 4-5 | |
| 11 | Explorations (DTC, TDM, ETT) | C2/C3 | 3 | 3 | 6-8 | |
| 12 | Antécédents + recherche CIM-10 + protocoles | C1/C2 | 3 | 3 | 8-10 | |
| 13 | Export recherche + dictionnaire de données + gel | C4 | 4 | 2 | 4-6 | |
| 14 | Microbiologie + écologie bactérienne + DDD | C2/C4 | 4 | 3 | 6-8 | |
| 15 | Définitions calculées : Berlin, KDIGO, Sepsis-3 | C5 | 3 | 3 | 5-6 | |
| 16 | Surveillance ECDC : PAVM / ILC pour 1000 jours | C4/C5 | 4 | 4 | 6-8 | |
| 17 | Tableau de bord + constructeur de cohorte | C4 | 3 | 3 | 8-10 | |
| 18 | STROBE + Table 1 auto-générée | C4 | 3 | 2 | 3-4 | |
| 19 | Export FHIR | C4 | 2 | 3 | 5-7 | v2 |
| 20 | Export OMOP CDM | C4 | 2 | 5 | 15+ | v2+ |

**Total blocs 0 à 18 : environ 100 à 130 heures.**
**Seuil d'utilisation quotidienne : fin du bloc 3, soit 30 à 39 heures.**
Inchangé par rapport au SPEC.

---

## 4. DÉTAIL PAR BLOC

Chaque bloc porte quatre informations : ce qu'il contient, ce dont il dépend,
**ce qu'il n'a pas le droit de toucher**, et son critère de fin.

### PHASE I — SOCLE (blocs 0 à 3)

Rien d'utilisable avant la fin du bloc 3. C'est la seule phase où l'on ne peut
pas s'arrêter en route.

#### Bloc 0 — Noyau
*Utilité 5 · Complexité 3 · 5-7 h · Couche C0*

Schéma complet, UUID partout, `cree_le` / `modifie_le` / `modifie_par` sur toute
table, champ `supprime` sans suppression physique, trois états explicites
partout, sauvegarde automatique (ouverture, fermeture, toutes les 15 min),
migrations de schéma versionnées, journal d'audit consultable.

**Dépend de :** rien.
**Ne touche pas :** rien n'existe encore.
**Fin quand :** on peut créer une donnée, la modifier, retrouver qui l'a
modifiée et quand, arrêter le programme, le redémarrer, et **restaurer une
sauvegarde avec succès**. La restauration doit être testée, pas supposée.

> Une sauvegarde jamais restaurée n'existe pas. À retester tous les mois, en
> cochant une case dans un carnet.

#### Bloc 1 — Référentiels
*Utilité 5 · Complexité 2 · 3-4 h · Couche C1*

Chargeur de fichiers de listes. Toutes les listes codées du SPEC §4 sortent du
code : provenances, mécanismes, régions traumatiques, motifs non traumatiques,
gestes chirurgicaux, examens de bilan, modes de sortie. Chaque fichier porte un
nom, une version et une date.

**Dépend de :** bloc 0.
**Ne touche pas :** rien.
**Fin quand :** on ajoute un motif d'admission en éditant un fichier, sans
redémarrer, sans toucher au code, et la version s'affiche quelque part.

> C'est trois heures qui économisent trente sollicitations du développeur sur
> deux ans.

#### Bloc 2 — Lits, admission, identité
*Utilité 5 · Complexité 2 · 6-8 h · Couche C2*

Tableau des 12 lits, création de séjour, identité, provenance, motif
d'admission, sélecteur d'utilisateur à l'ouverture, historique des lits, sortie
technique (libération du lit — le compte rendu vient plus tard au bloc 8).

**Fin quand :** on admet un patient dans le lit 7, on le voit sur le tableau, on
le sort, le lit se libère.

#### Bloc 3 — PRESCRIPTION ⭐
*Utilité 5 · Complexité 3 · 16-20 h · Couches C2 et C3*

**La raison d'être du logiciel.** Rien ne passe devant.

Lignes de prescription par voie d'administration, avec formulaire à champs
variables selon la voie. Calcul des horaires selon le rythme. Compteurs de jours
J2 → J3 et J7/7. Bouton **« Préparer la pancarte de demain »**. Volume des
entrées sur 24 h. Section « Bilans à demander pour le lendemain ». Zones
manuscrites réservées pour les infirmiers. Impression HTML/CSS en A4, avec la
bascule A3 prête sur une seule ligne. Snapshot immuable de chaque pancarte
imprimée.

**Ne touche pas :** rien au-dessus. En particulier, le module d'impression **ne
calcule aucun compteur** — il reçoit `"J7/7"` déjà formé (règle R3).

**Fin quand :** un interne prépare la pancarte du lendemain en moins de trois
minutes, l'imprime, et elle est utilisable telle quelle dans la pancarte
physique.

**Tests obligatoires avant de clore :** compteur qui passe minuit, ligne arrêtée
qui disparaît, ligne à échéance signalée, dernier jour d'antibiotique, horaires
pour chaque rythme, volume total des entrées.

> **À la fin de ce bloc, le logiciel résout le problème et peut entrer en usage
> solo.** Deux semaines complètes d'usage par une seule personne avant d'ouvrir
> aux treize utilisateurs.

### PHASE II — GAIN QUOTIDIEN (blocs 4 à 9)

Chaque bloc est indépendant. On peut s'arrêter après n'importe lequel sans
laisser de chantier.

#### Bloc 4 — Contrôles de cohérence 🎯
*Utilité 4 · Complexité 1 · 2-3 h · Couche C2*

**Le meilleur ratio de toute la feuille de route.**

Valeur hors bornes physiologiques, unité improbable, date de sortie avant
l'admission, poids à 700 kg, kaliémie à 45, date d'extubation avant
l'intubation. Le message est un avertissement, jamais un blocage : le médecin
peut toujours forcer, la valeur forcée est marquée comme telle.

**Fin quand :** dix erreurs de frappe volontaires sur dix sont signalées.

> Deux heures ici valent plus, pour la qualité de la base, que vingt heures de
> statistiques plus tard. On ne rattrape pas une donnée fausse saisie il y a
> huit mois.

#### Bloc 5 — Évolution quotidienne
*Utilité 4 · Complexité 2 · 5-7 h · Couche C3*

Format validé au SPEC §8.1. En-tête et jour d'hospitalisation générés, quatre
plans en saisie libre, rubrique traitement générée depuis les lignes actives,
conduite laissée vide. Bouton copier.

> ⚠️ **À tester le premier jour** : accents, `HCO₃⁻`, `PaO₂`, retours à la
> ligne. Si le DMI abîme les indices Unicode, bascule sur `HCO3-` et `PaO2` —
> un paramètre, pas une réécriture.

#### Bloc 6 — Bilans
*Utilité 4 · Complexité 2 · 6-8 h · Couches C2 et C3*

Intégration du fichier HTML existant, tel quel, plus les deux champs manquants :
**albumine et glycémie** (exigés par l'alignement ANZICS). Tableau par date. Gaz
du sang groupés avec les paramètres ventilatoires, rapport P/F calculé.

#### Bloc 7 — Rappels et FAST HUG
*Utilité 4 · Complexité 2 · 4-5 h · Couche C5*

Moteur de règles déclaratif (R4) et premières règles : réévaluation antibiotique
à 48-72 h · J7/7 · ablation de cathéter · TDM de contrôle H48 · dépistage BMR
hebdomadaire · **checklist FAST HUG quotidienne**.

**Ne touche pas :** aucune donnée. La couche C5 **signale et ne décide jamais.**
**Fin quand :** une nouvelle alerte s'ajoute en éditant un fichier, sans toucher
au code.

#### Bloc 8 — Sortie et compte rendu
*Utilité 4 · Complexité 2 · 4-6 h · Couches C2 et C3*

#### Bloc 9 — Socle recherche
*Utilité 4 · Complexité 3 · 6-8 h · Couche C2*

IGS II à l'admission, SOFA quotidien, dates d'intubation et d'extubation,
épuration extrarénale, mortalité en réanimation et à J28, jours vivants sans
ventilateur. Chaque score est **calculé, avec ses composantes stockées** —
jamais un total saisi à la main.

> **Tests automatisés obligatoires sur chaque score.** Un IGS II faux découvert
> après soumission d'un article invalide deux ans de recueil. C'est le seul
> endroit du projet où l'erreur est irrattrapable.

### PHASE III — VALEUR SCIENTIFIQUE (blocs 10 à 18)

#### Bloc 10 — Courbes de cinétique
*Utilité 3 · Complexité 2 · 4-5 h · Couche C3*

#### Bloc 11 — Explorations
*Utilité 3 · Complexité 3 · 6-8 h · Couches C2 et C3*

**Valeurs chiffrées, pas de compte rendu textuel.**

#### Bloc 12 — Antécédents et protocoles
*Utilité 3 · Complexité 3 · 8-10 h · Couches C1 et C2*

**Règle non négociable :** le pré-remplissage est **proposé, jamais appliqué**.

#### Bloc 13 — Export recherche
*Utilité 4 · Complexité 2 · 4-6 h · Couche C4*

Trois éléments qui font la différence entre un export et un recueil défendable :

1. **Dictionnaire de données exporté avec chaque CSV** — nom de variable, type,
   unité, code LOINC ou ATC, modalités possibles, définition et sa référence.
2. **Gel de base daté et numéroté.**
3. **Trois types de manquant distingués** — non applicable / non fait / fait
   mais non renseigné.

#### Bloc 14 — Microbiologie et écologie bactérienne
*Utilité 4 · Complexité 3 · 6-8 h · Couches C2 et C4*

Consommation antibiotique en **DDD pour 1000 jours-patients** (standard OMS).
**Prérequis :** le code ATC doit avoir été câblé dès le bloc 3 (voir §5).

#### Bloc 15 — Définitions calculées
*Utilité 3 · Complexité 3 · 5-6 h · Couche C5*

| Concept | Référence |
|---|---|
| Sepsis, choc septique | Sepsis-3 |
| SDRA | Définition de Berlin |
| Insuffisance rénale aiguë | KDIGO |
| SOFA | Vincent 1996 |
| IGS II | Le Gall 1993 |

#### Bloc 16 — Surveillance ECDC
*Utilité 4 · Complexité 4 · 6-8 h · Couches C4 et C5*

PAVM et ILC, définitions **ECDC HAI-Net ICU**, dénominateurs en jours de
ventilation et jours de cathéter.

#### Bloc 17 — Tableau de bord et cohortes
*Utilité 3 · Complexité 3 · 8-10 h · Couche C4*

#### Bloc 18 — STROBE et Table 1
*Utilité 3 · Complexité 2 · 3-4 h · Couche C4*

### PHASE IV — PÉRENNITÉ (blocs 19 et 20, v2)

**Bloc 19 — Export FHIR** *(2 · 3 · 5-7 h)* — exporter vers FHIR, ne pas
construire sur FHIR.
**Bloc 20 — Export OMOP CDM** *(2 · 5 · 15 h+)*

---

## 5. À CÂBLER TÔT, EXPLOITER TARD

Ces éléments coûtent **quelques minutes** s'ils sont posés dès le bloc 3, et
**des semaines de reprise rétroactive** s'ils sont ajoutés plus tard.

| Élément | À poser au bloc | Exploité au bloc | Coût si oublié |
|---|---|---|---|
| Colonne code **ATC** sur chaque médicament | 3 | 14 | Recodage manuel de milliers de lignes |
| Colonne code **LOINC** sur chaque analyte | 6 | 13 | Table de correspondance a posteriori |
| Colonne code **CIM-10** sur diagnostics et antécédents | 12 | 17 | Relecture de tous les dossiers |
| **Unités UCUM** normalisées | 6 | 13 | Confusion µmol/L vs mg/L, données inutilisables |
| Dates de **pose et retrait** de chaque dispositif | 3 | 16 | Pas de dénominateur, pas de taux de PAVM |
| **Créatinine de base** avant admission | 2 | 15 | KDIGO incalculable |
| **Journal d'audit** consultable | 0 | permanent | Non reconstituable |

> Règle simple : **un identifiant standard ne coûte rien à stocker et vaut tout
> à l'analyse.** Dans le doute, la colonne existe et reste vide.

---

## 6. CE QUI FAIT « PRODUIT » ET PAS BRICOLAGE

**Statut réglementaire.** La règle « aucun calcul de dose, protocole proposé
jamais appliqué » est ce qui maintient l'outil du côté de la documentation
clinique. À écrire dans le SPEC comme un **choix de conception assumé et
justifié**, pas comme une limitation technique.

**Protection des données.** Base légale, durée de conservation, registre de
traitement, autorisation de l'autorité nationale et avis du comité d'éthique —
**à lancer maintenant**, les délais sont longs.

**Intégrité, principes ALCOA+.** Attribuable, lisible, contemporain, original,
exact.

**Tests automatisés sur tous les calculs.** Un test par calcul, écrit **dans le
bloc qui crée le calcul**, jamais reporté.

**Restauration testée mensuellement**, avec une trace écrite.

**Versionnement.** Git, versions sémantiques, migrations de schéma numérotées.

**Continuité humaine.** Question ouverte n°11 du SPEC. La modularité y répond en
partie ; elle n'y répond pas entièrement — il faut un nom.

---

## 7. HORS PÉRIMÈTRE, ET POURQUOI

| Écarté | Raison |
|---|---|
| Base d'interactions médicamenteuses | Engagement de maintenance disproportionné, responsabilité qui change de nature |
| SNOMED CT | Licence et lourdeur. CIM-10 + ATC + LOINC suffisent |
| Codage diagnostique APACHE III | Plusieurs centaines de catégories |
| Score ANZROD | Calibré sur la population australienne |
| Tout LLM sur données patient | Tant que ça sort de la machine, non |
| Saisie infirmière numérique | Décision SPEC §5.7 |
| Reprise d'un EHR open source | Aucun ne fait la reconduction du prescrit |

---

## 8. RÈGLE DE DÉPLOIEMENT

**Usage en solo pendant deux semaines complètes après le bloc 3, avant ouverture
aux treize utilisateurs.**

Ensuite, un bloc à la fois, avec la question posée à chaque fois :
**est-ce que le service réclame ce bloc, ou est-ce que c'est moi qui ai envie de
le coder ?**

---

## 9. QUESTIONS QUE CETTE FEUILLE DE ROUTE OUVRE

| # | Question | Bloque | État |
|---|---|---|---|
| A | Le socle de variables de recherche est-il validé par le chef ? | Bloc 9 | ouverte |
| B | Source des fichiers CIM-10, LOINC et ATC ? | §5, blocs 6 et 12 | ouverte — mapping LOINC provisoire ; code ATC jamais renseigné ; la saisie CIM-10 a été retirée de l'écran Identité à la demande du service (la colonne reste) |
| C | Heure de départ pour un rythme ×4/j | Bloc 3 | tranchée — 6-12-18-24 |
| D | Bornes de normalité pour signaler les valeurs anormales | Blocs 4 et 10 | ouverte — bornes usuelles provisoires |
| E | Poste du chef de service : copie lecture seule ou rien ? | Bloc 0 | ouverte |
| F | Qui maintient le programme en l'absence de l'auteur ? | Tout | ouverte |
| G | Démarches auprès de l'autorité de protection des données | Blocs 13 et suivants | ouverte |
| H | Règles et protocoles modifiés sur place : où les ranger ? | Blocs 7 et 0 | **ouverte** — l'éditeur écrit dans le dossier du programme : une mise à jour écrase ces modifications, et aucune sauvegarde ne les emporte (voir §10) |

---

## 10. ÉTAT D'APPLICATION AU 27 SEPTEMBRE 2026

Audit complet, refait sur le code tel qu'il est — pas sur ce que disaient les
versions précédentes de ce paragraphe (4 septembre), dont plusieurs lignes
étaient devenues fausses (check-list FAST HUG retirée, `rea/db.py` devenu
`rea/database/`, feuille du service fournie).

### Comment l'audit a été fait

- **Tests** : 1 407, tous verts — dont 28 nouveaux qui lancent l'application
  entière. Couverture par couche : impression 95 %, métier 94 %, services
  92 %, base 91 % — **écrans 15 % avant l'audit, 53 % après** (total 61 → 77 %).
- **Analyse statique** : pyflakes sans remarque ; ruff (règles bugs et
  sécurité) — les SQL construits par chaîne sont tous sur des noms de table ou
  de colonne en liste blanche, aucune injection possible.
- **Charge** : une base synthétique de **trois ans** (1 500 séjours, 210 000
  résultats de bilan) : 252 Mo, dont la moitié pour le journal d'audit.
- **L'application entière lancée**, pour chaque rôle et chaque écran — ce
  qu'aucun test ne faisait jusqu'ici.

### Corrigé pendant l'audit

| Gravité | Défaut | Correction |
|---|---|---|
| **Bloquant** | `rea_app.py` importait `rea.domaine`, renommé `rea.models` : **l'application plantait juste après la connexion** sur un poste installé de neuf (masqué ailleurs par l'ancien dossier resté en place) | import corrigé ; `tests/test_ecrans.py` lance désormais l'application entière (5 rôles, 7 onglets de fiche, 10 vues de recherche, admission, administration, supervision, poste infirmier) et vérifie que chaque `import rea.…` désigne un module qui existe |
| **Élevée** | L'installateur (`robocopy /E`) laissait sur le poste les modules supprimés : c'est ce qui masquait l'erreur ci-dessus | le dossier `rea/` est désormais remis à l'identique (`/PURGE`) ; `regles/` et `protocoles/` ne sont pas purgés (question H) |
| **Élevée** | La compression des sauvegardes se faisait sous le verrou de la base : sur une base de trois ans, **tous les écrans figés ~7 s toutes les 15 min** | seule la copie SQLite (0,6 s mesurée) tient le verrou ; la copie en cours porte `.tmp` et n'apparaît jamais dans la liste des restaurations |
| **Élevée** | Le **statut à J28** n'avait aucun écran de saisie : la mortalité à J28 ne comptait que les décès en réanimation | devenir déduit quand on le sait (décès en réanimation avant J28, patient encore hospitalisé à J28) ; seuls les patients sortis vivants avant J28 sont à vérifier — saisie dans l'onglet Sortie et en liste dans Recherche → Qualité des données |
| **Élevée** | Un décès après la sortie, une fois saisi en J28, aurait été compté comme **décès en réanimation** (mortalité, rapport O/A, carte de contrôle) | « décès en réanimation » et « décès avant J28 » séparés ; les jours sans ventilation suivent la définition de Schoenfeld (décès **avant J28** = 0) |
| Moyenne | Date/heure de sortie tapées au format `AAAA-MM-JJTHH:MM` : une faute de frappe faisait planter l'écran | sélecteurs de date et d'heure |
| Moyenne | La Recherche (ajout du 27 septembre) utilisait Altair, écarté le 6 septembre après un plantage sur le poste du service | cartes en SVG, comme le reste du logiciel |
| Faible | Libellés de tranches des croisements (noms de germes, produits, antécédents tapés à la main) insérés en HTML sans échappement | échappés |
| Faible | Rapport O/A : l'IGS II prédit la mortalité hospitalière, l'observé est la mortalité en réanimation | écrit à l'écran : le rapport est un peu sous-estimé |

### Blocs

| Bloc | État réel |
|---|---|
| 0 Noyau | ✅ — restauration testée, journal consultable ; sauvegardes compressées, rétention étagée (1 an), gels jamais effacés |
| 1 Référentiels | ✅ |
| 2-3 Lits, admission, prescription | ✅ — feuille du service (maquette Kairouan) ; heure d'admission et bande « ADMISSION » |
| 4 Cohérence | ✅ |
| 5-8 Évolution, bilans, rappels, sortie | ✅ — check-list FAST HUG retirée à la demande du service ; suppression logique d'un bilan erroné |
| 9 Socle recherche | ✅ — **devenir à J28 désormais recueilli** |
| 10-11 Courbes, explorations | ✅ |
| 12 Antécédents, CIM-10 | ◐ antécédents faits ; CIM-10 : 58 codes, saisie retirée de l'écran |
| 13 Export | ✅ |
| 14 Microbiologie | ◐ consommation en DOT ; table DDD de l'OMS à saisir |
| 15-18 Définitions, taux ECDC, cohortes, STROBE | ✅ — intervalles de confiance, carte de contrôle, calibration IGS II, Kaplan-Meier, qualité des données |
| 19-20 | ❌ v2 (multi-postes, reprise après incident) |

### Règles de modularité

| Règle | État |
|---|---|
| R1 une seule couche écrit | ✅ vérifiée par `tests/test_architecture.py` |
| R2 référentiels en fichiers | ✅ |
| R3 le rendu ne calcule rien | ✅ — la feuille reçoit un `DossierFeuille` préparé par `services/feuille_dossier.py`, vérifié par test |
| R4 aides déclaratives | ✅ |
| R5 export lit le schéma | ✅ |

### Mesures sur trois ans de données

| | Mesure | Lecture |
|---|---|---|
| Taille de la base | 252 Mo (journal d'audit : ~160 Mo avec ses index) | normal pour SQLite ; le journal est le prix de la traçabilité |
| Sauvegarde compressée | 57 Mo, 7 s de compression (hors verrou) | ~110 fichiers conservés ≈ 6 Go au bout de trois ans : réduire les paliers `RETENTION_*` si le disque est petit |
| Écran de la fiche, feuille imprimée | < 0,1 s | — |
| Recherche : tableau descriptif, mortalité, calibration, qualité | ~2,5 s chacun | l'IGS II est recalculé pour chaque séjour à chaque affichage ; à mettre en cache si l'attente gêne |

### Ce qui reste à faire, par priorité

**À faire avant l'usage réel**
1. **Recette sur le poste du service** après réinstallation (`installer.bat`,
   qui purge maintenant le code périmé) : ouvrir chaque écran avec un compte
   de chaque rôle, imprimer une feuille, restaurer une sauvegarde.
2. **Question H** : ranger les règles et protocoles modifiés sur place dans
   `C:\ReaService` (à côté des données) plutôt que dans le programme, pour
   qu'une mise à jour ne les écrase plus et qu'ils soient sauvegardés.
3. **Déconnexion après inactivité** en mode réseau : aujourd'hui une session
   ouverte sur un téléphone ou un poste partagé le reste indéfiniment, et
   tout ce qui s'y écrit est signé du nom de celui qui l'a ouverte.

**Souhaitable**
4. **HTTPS sur le Wi-Fi** : les codes d'accès circulent en clair sur le réseau
   du service (Streamlit sait servir en HTTPS avec un certificat local).
5. **Annuler une sortie faite par erreur** (senior), comme on supprime une
   admission : aujourd'hui, seule une restauration de sauvegarde le permet.
6. **Mettre en cache l'IGS II** dans la Recherche (2,5 s par vue à trois ans).
7. Remplacer `use_container_width` (54 appels, obsolète) **avant** toute
   montée de version de Streamlit — la version épinglée l'accepte encore.

**Ne dépend pas du développement**
8. Validation par un senior : bornes des bilans, barème IGS II, seuils des
   rappels, correspondances LOINC.
9. CIM-10 complète, table des DDD et codes ATC depuis leur source officielle.
10. Dossier de protection des données (question G) et avis du comité
    d'éthique avant toute exploitation scientifique.
11. Désigner qui maintient le logiciel (question F) : le code est documenté,
    testé et découpé en couches, mais personne ne le connaît encore à part
    son auteur.

---

*Fin du document — Feuille de route v1.0, audit du 27 septembre 2026*
*Toute décision prise en session est reportée ici et dans le SPEC avant la fin
de la session.*
