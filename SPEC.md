# SPEC — Logiciel de service, Réanimation polyvalente

**Version 1.9 — 3 septembre 2026**

> **Document de référence du projet.** Complété par **FEUILLE_DE_ROUTE.md**,
> qui fixe l'ordre de construction et les règles d'isolation entre couches.
> À renvoyer au début de chaque session de
> travail, accompagné du code à jour. C'est la mémoire commune du projet.
>
> Toute décision prise en session doit être reportée ici avant la fin de la session.

---

# 1. CONTEXTE

## 1.1 Service

Service d'anesthésie-réanimation polyvalente.

- **12 lits**, répartis en 3 chambres de 4 lits (chambre 1 → lits 1-4, chambre 2
  → lits 5-8, chambre 3 → lits 9-12)
- Extension possible lors de l'inauguration d'un nouvel hôpital
- Durée de séjour : 2 à 60 jours
- Population : polytraumatisés, brûlés, complications postopératoires graves,
  décompensations de pathologies chirurgicales, défaillances hémodynamiques /
  neurologiques / respiratoires provenant des services chirurgicaux adjacents

## 1.2 Utilisateurs

| Groupe | Nombre | Droits v1 |
|---|---|---|
| Internes | 3 | Saisie complète |
| Résidents | 10 | Saisie complète |
| Seniors | variable | Saisie complète |

Pas de gestion de droits différenciés en v1. **Sélecteur d'utilisateur
obligatoire à l'ouverture**, enregistré sur chaque ligne créée ou modifiée.

## 1.3 Le problème à résoudre

> Aujourd'hui, un interne réécrit **à la main, chaque jour**, l'intégralité du
> prescrit de chaque patient, alors qu'il est presque identique à celui de la
> veille.

**C'est LA raison d'être du logiciel.** Le prescrit du lendemain doit apparaître
pré-rempli : les compteurs de jours ont avancé, les lignes actives sont
reconduites. L'interne vérifie, ajoute ce qui est nouveau, choisit les bilans du
lendemain, imprime, met dans la pancarte.

Tout le reste (statistiques, évolution, bilans) est secondaire par rapport à ça.

## 1.4 Continuité de service

Si le logiciel ne démarre pas un matin, le service utilise la pancarte imprimée
de la veille et continue normalement. **Le logiciel n'est jamais un point de
passage obligé.**

---

# 2. ENVIRONNEMENT TECHNIQUE

## 2.1 Matériel — validé

- **Un seul poste fixe**, Windows 10 ou 11, droits administrateur disponibles
- Ce poste héberge le **DMI** (l'EHR de l'hôpital) — c'est pour cela que
  l'application doit tourner dessus : le copier-coller ne traverse pas les
  machines
- Pas d'ordinateur portable en phase 1
- Pas d'antivirus bloquant, clé USB reconnue, exécution autorisée, écriture
  locale persistante après redémarrage, `localhost:8501` accessible
- **Imprimante : A4 uniquement pour le moment.** L'A3 n'est pas encore achetée

## 2.2 Architecture retenue

L'architecture « clé USB comme système » est **abandonnée** : elle n'avait de
sens qu'avec deux machines. Avec un poste unique :

- Application **installée localement** sur le poste fixe
- Python 3.11+ installé normalement (droits admin disponibles)
- Interface **Streamlit**, ouverte dans le navigateur du poste
- Base **SQLite**, fichier unique dans `C:\ReaService\data\rea.db`
- **Sauvegarde automatique** : à l'ouverture, à la fermeture, et toutes les
  15 minutes. Destination `C:\ReaService\backups\` avec horodatage dans le nom
- **Clé USB = support de sauvegarde uniquement** (copie manuelle hebdomadaire,
  clé chiffrée BitLocker To Go)
- Chiffrement du disque du poste (BitLocker) recommandé
- Dossier de travail **jamais** synchronisé avec un cloud

**Impression :** génération HTML + CSS d'impression. `@page { size: A4 }`
aujourd'hui, basculement vers `A3 landscape` par changement d'une seule ligne
quand l'imprimante arrivera. La mise en page est conçue dès maintenant pour
supporter les deux.

## 2.3 Point à trancher

Le poste du chef de service ne doit **pas** recevoir une base modifiable.
Deux options, à décider : soit copie en lecture seule pour consultation, soit
rien du tout et consultation sur le poste du service. Une base modifiable en
deux endroits produit deux vérités.

## 2.4 Contraintes d'architecture

Cette section voyage avec le code, pas seulement avec la SPEC. Sans elle, on
proposera dans trois mois une architecture client-serveur déjà écartée — ou on
oubliera que le multi-postes reste possible.

**État actuel — ne pas dépasser.** Un seul poste Windows, celui du DMI. Un
seul utilisateur à la fois. Écoute sur 127.0.0.1. SQLite local. Pas de réseau,
pas d'internet sur cette machine.

**Évolutions possibles, non décidées, à ne pas développer.** Postes du service
via LAN de l'hôpital, portable de visite, tablettes, mini-PC serveur dédié,
PIN par utilisateur.

> **Règle** : ne rien coder pour ces cas, mais ne jamais les rendre coûteux.

### Invariants — à respecter dans tout code produit

1. **Aucune hypothèse « un seul utilisateur ».** Toute table modifiable porte
   `version` (int, défaut 1), `cree_par`, `modifie_par`, `cree_le`,
   `modifie_le`. `version` est incrémentée à chaque écriture. Personne ne la
   lit encore.
2. **Aucune hypothèse « un seul écran ouvert ».** Toute écriture se fait ligne
   par ligne, au moment de la validation de la ligne. Jamais un formulaire
   entier enregistré en bloc.
3. **Un seul endroit contient du SQL.** Les vues et le rendu appellent des
   fonctions métier, jamais une requête.
4. **Les calculs sont des fonctions pures**, sans accès base : compteurs de
   jours, volume des entrées, âge, polytraumatisé, P/F. Testables sans base.
5. **Aucune valeur en dur hors `config.py`** — `HOTE`, `AUTH_REQUISE`,
   `FORMAT_PAGE`, `PORT`.
6. **Les référentiels** (protocoles, listes, seuils, médicaments) sont des
   fichiers versionnés dans `referentiels/`, jamais du code.
7. **Le rendu ne calcule jamais.** Il reçoit des valeurs déjà calculées.

**Interdits** : couche d'abstraction générique de base, système de plugins,
API REST, gestion de rôles, mode hors ligne, cache local. Ces éléments coûtent
aujourd'hui pour un besoin hypothétique.

### Où ces invariants vivent dans ce dépôt

Trois écarts de nommage avec l'énoncé d'origine, assumés — renommer coûterait
sans rien apporter :

| Énoncé      | Ici                | Pourquoi                                     |
|-------------|--------------------|----------------------------------------------|
| `donnees.py`| `rea/db.py`        | même rôle, nom déjà en place partout          |
| `metier/`   | `rea/domaine/`     | idem                                          |
| YAML        | JSON               | pas de dépendance à installer sur un poste hors ligne ; même versionnement, même lisibilité |

Un quatrième écart n'est pas assumé mais **connu** : le SQL est réparti dans
les services plutôt que réuni dans un seul fichier (invariant 3). Ce qui est
tenu aujourd'hui, et vérifié par `tests/test_architecture.py`, c'est qu'aucun
écran ni aucun rendu n'en contient — c'est là que la règle protège vraiment.
Réunir les quinze services en un fichier reste à faire, sans urgence.

L'invariant 2 est tenu pour les prescriptions (une ligne, une écriture) mais
pas pour l'évolution ni la saisie d'un bilan, enregistrés d'un bouton. Un
bilan est un événement unique — un prélèvement, trente analytes — et son
enregistrement en bloc correspond à la réalité. L'évolution, elle, est un
vrai écart : deux internes sur le même patient le même jour s'écrasent.

Les invariants vérifiables sont tenus par des tests plutôt que par la
discipline (`tests/test_architecture.py`) : traçabilité de chaque table,
incrémentation de `version`, `pin` présent, aucun `DELETE`, aucun SQL dans un
écran, adresse d'écoute limitée à la boucle locale, et `AUTH_REQUISE` exigé
dès que `HOTE` s'ouvre.

---

# 3. RÈGLES DE CONCEPTION

1. **UUID** comme identifiants, jamais de numéros séquentiels
2. **Aucune suppression physique** — champ `supprime` marqué à vrai
3. **Horodatage systématique** — `cree_le`, `modifie_le`, `modifie_par`
4. **Séries temporelles en format long** — une ligne par mesure, jamais une
   colonne par jour
5. **Le texte est calculé, pas stocké** — sauf exception ci-dessous
6. **Table d'identité séparée** des données cliniques
7. **Trois états explicites** partout où l'absence d'information est possible :
   *présent* / *absent* / *non renseigné* (jamais de valeur par défaut
   silencieuse)
8. **Export recherche pseudonymisé automatiquement**, sans option

**Exception à la règle 5 :** chaque pancarte imprimée est enregistrée comme
*snapshot immuable* (contenu HTML + date/heure + numéro de version +
utilisateur). Une pancarte imprimée est un document physique qui a circulé dans
le service ; il faut pouvoir la reconstituer à l'identique.

## 3.1 Ce que le logiciel calcule et ne calcule pas

| Calcul | v1 |
|---|---|
| Compteur de jours (J2 → J3) | ✅ automatique |
| Dernier jour d'antibiothérapie (J7/7) | ✅ automatique |
| Horaires d'administration selon le rythme | ✅ automatique |
| Volume des **entrées** sur 24 h | ✅ automatique |
| Âge à partir de la date de naissance | ✅ automatique |
| Statut « polytraumatisé » | ✅ automatique |
| **Dose en mg/kg ou en γ/kg/min** | ❌ jamais en v1 |
| **Adaptation de posologie à la fonction rénale** | ❌ jamais en v1 |

La règle est simple : le logiciel calcule des **dates, des horaires et des
volumes**. Il ne calcule jamais une **dose**.

---

# 4. MODÈLE DE DONNÉES

## 4.1 Identité et séjour

### `patient`

| Champ | Type | Notes |
|---|---|---|
| id | UUID | |
| matricule | texte | Identifiant hospitalier, stable |
| nom_affichage | texte | Format `K. Abdelaziz` (initiale du nom + prénom) |
| date_naissance | date | Complète — permet l'âge et l'analyse par tranche |
| sexe | liste | M / F / non renseigné |

### `sejour`

| Champ | Type | Notes |
|---|---|---|
| id | UUID | |
| patient_id | UUID | |
| numero_sejour | entier | 1er, 2e… séjour de ce patient |
| date_admission | datetime | |
| lit_admission | entier | 1-12, figé |
| provenance_type | liste | Urgences / Service (préciser) / Bloc opératoire / Consultation externe A-R / Autre hôpital / Domicile |
| provenance_detail | texte | Nom du service si applicable |
| est_readmission | booléen | |
| motif_readmission | texte | Si réadmission |
| traumatique | booléen | **Question filtre — conditionne toute la suite** |
| mecanisme | liste | Voir §4.3 |
| date_sortie | datetime | |
| mode_sortie | liste | Voir §4.7 |

### `sejour_lit` — historique des changements de lit

`sejour_id`, `lit`, `date_debut`, `date_fin`

Le lit d'admission reste dans `sejour`. L'historique est secondaire mais coûte
peu à enregistrer.

### Patient non identifié

Génération d'un matricule provisoire `XXX-{date}-{n}`, `nom_affichage` =
« Non identifié 1 ». Fonction de fusion avec le vrai dossier quand l'identité
est connue. **À détailler ultérieurement.**

## 4.2 Antécédents

Attachés au **patient** (persistants d'un séjour à l'autre), avec horodatage de
mise à jour.

### `antecedent`

| Champ | Type | Notes |
|---|---|---|
| patient_id | UUID | |
| categorie | liste | Personnel / Familial / Chirurgical / Allergie / Habitude de vie |
| libelle | texte | |
| code_icd10 | texte | Optionnel |
| precision | texte | Ex. « stenté en 2019 », « type 2 sous insuline » |
| quantification | nombre + unité | Ex. 30 paquets-années |
| statut | liste | Présent / Absent / Non renseigné |

**Saisie :** liste courte des 10 pathologies les plus fréquentes en accès
direct, plus un champ de recherche ICD-10 (par nom ou par code) pour tout le
reste. Case **« Sans antécédent connu »** disponible.

### 4.2 bis — Le patient a-t-il des antécédents ? (implémenté v2.6)

Question d'entrée, avant toute saisie : **Oui / Non / Inconnu**. Inconnu
s'affiche comme « aucun antécédent enregistré », mais reste distingué de
Non en base — ce logiciel ne confond jamais « répondu non » et « jamais
demandé ». Si Oui, la saisie se scinde par catégorie : **Familiaux** /
**Personnels** (chirurgical, médical, allergies) / **Habitudes de vie**,
ces dernières avec trois habitudes prêtes par défaut — tabagisme (quantifié
en paquets-années), éthylisme, toxicomanie (substance ou substances
précisées) — modifiable après l'admission, à tout moment, depuis l'onglet
Identité.

**Allergies :** catégorie à part, affichée en **alerte rouge en haut de la
pancarte et de toutes les fiches**.

**Traitement habituel :** texte libre, un seul champ.

### Liste courte de départ (à valider par un senior)

HTA · Diabète type 2 · Diabète type 1 · Cardiopathie ischémique · Insuffisance
cardiaque · BPCO · Asthme · Insuffisance rénale chronique · Cirrhose · AVC ·
Tabagisme · Éthylisme · Anticoagulant au long cours · Antiagrégant

## 4.3 Motif d'admission — traumatique

**Multi-sélection** des régions atteintes (`traumatisme_region`) :

- Traumatisme crânien
- Traumatisme thoracique
- Traumatisme abdominal
- Traumatisme pelvien
- Traumatisme périphérique *(englobe massif facial, membres, rachis)*

> **Statut « polytraumatisé » calculé automatiquement** si ≥ 2 régions cochées.

L'objectif n'est pas la description exhaustive de la lésion, mais la
**catégorisation** : pouvoir extraire plus tard la cohorte complète des
traumatismes crâniens.

### Mécanisme (liste unique)

AVP deux-roues · AVP quatre-roues · AVP piéton · Chute de sa hauteur · Chute
d'un lieu élevé (préciser hauteur) · Agression par arme blanche · Agression par
arme à feu · Agression contondante · Accident de travail · Accident domestique ·
Sport · Écrasement / ensevelissement · Blast / explosion · Autre · Non renseigné

## 4.4 Motif d'admission — non traumatique

Un **motif principal** obligatoire + motifs associés en multi-sélection.

**Défaillance circulatoire** — Choc septique *(+ porte d'entrée : pulmonaire /
digestive / urinaire / cutanée-parties molles / cathéter / méningée /
indéterminée)* · Choc hémorragique non traumatique · Choc cardiogénique ·
Choc anaphylactique · Choc obstructif

**Défaillance respiratoire** — SDRA · Pneumopathie grave · Décompensation de
BPCO · OAP cardiogénique · Embolie pulmonaire · Inhalation · Obstruction des
voies aériennes

**Défaillance neurologique** — AVC ischémique · AVC hémorragique · Hémorragie
méningée · État de mal épileptique · Méningo-encéphalite · Coma métabolique ·
Coma toxique

**Postopératoire** — Surveillance postopératoire lourde programmée ·
Complication postopératoire non programmée *(préciser)*

**Brûlures** — *(+ surface cutanée brûlée en %, profondeur, agent thermique /
électrique / chimique, lésion d'inhalation associée oui/non)*

**Métabolique et rénal** — Acidocétose diabétique · Coma hyperosmolaire ·
Dysnatrémie sévère · Dyskaliémie sévère · Insuffisance rénale aiguë avec
indication d'épuration

**Intoxications et envenimations** — Médicamenteuse · Organophosphorés ·
Monoxyde de carbone · Caustique · Envenimation scorpionique · Envenimation
ophidienne

**Obstétrical** — Prééclampsie sévère · Éclampsie · HELLP syndrome · Hémorragie
du post-partum · Embolie amniotique

**Autre** — Post-arrêt cardiaque · Tétanos · Autre *(préciser)*

## 4.5 Protocoles de pré-remplissage

Le diagnostic déclenche une **proposition** de lignes de prescription et de
surveillance. Exemple validé :

> **Traumatisme crânien** → TDM cérébrale de contrôle à H48 · Surveillance des
> ACSOS toutes les 6 h pendant 48 h · Pas de Ringer Lactate pendant 48 h

### Règles de sécurité — non négociables

1. Chaque protocole est **écrit et signé par le chef de service**, pas par
   l'auteur du logiciel
2. Le fichier des protocoles porte une **date de version**, affichée sur la
   pancarte imprimée
3. Le pré-remplissage est **proposé, jamais appliqué** — une liste de cases
   s'affiche, le médecin coche ce qu'il retient
4. Toute ligne issue d'un protocole reste **modifiable et supprimable** sans
   exception

## 4.6 Interventions chirurgicales

`sejour_id` · `date_acte` · `geste` (liste) · `est_reprise` (booléen) ·
`complication_statut` (**Aucune / Présente / Non renseigné** — défaut : *Non
renseigné*) · `complication_texte`

> ⚠️ La demande initiale était « sans complication par défaut ». **Refusé** :
> impossible de distinguer ensuite un patient réellement sans complication d'un
> patient dont personne n'a rempli la case. Les taux calculés seraient faux et
> un relecteur le verrait. Trois états explicites, défaut *Non renseigné*.

## 4.7 Sortie — écran dédié

L'écran de sortie clôture le séjour et libère le lit sur l'écran d'accueil.

| Champ | Valeurs |
|---|---|
| `mode_sortie` | Domicile · Transfert vers un service *(préciser)* · Transfert vers un autre hôpital · Rééducation · Sortie contre avis médical · **Décès** |
| `destination` | Nom du service et de l'établissement, avec mention « même établissement » ou non |
| `date_heure_sortie` | |
| `complication_statut` | **Aucune / Présente / Non renseigné** — défaut : *Non renseigné* |
| `complication_texte` | Ex. « PAVM à J5 — *Pseudomonas aeruginosa* » |
| `ordonnance_sortie` | Texte libre — ex. « Enoxaparine 0,4 mL/j pendant 15 jours » |
| `consultation_externe` | Délai, service, examens à apporter |

**Compte rendu de sortie généré** à partir des données du séjour : identité,
dates et durée, provenance, motif d'admission, durée de ventilation,
complications, destination, traitement de sortie et rendez-vous de suivi.
Bouton « copier » pour collage dans le DMI.

# 5. PRESCRIPTION — cœur du logiciel

## 5.1 Structure d'une ligne — deux niveaux

Une ligne de prescription porte deux choses de nature différente : **quel
traitement** (le produit, pourquoi il a été introduit, depuis quand) et **à
quelle dose** (dose, rythme, dilution, vitesse). Les confondre coûte cher.

Tienam 1 g × 3/j introduit à J1 passe à 500 mg × 3/j à J4 pour une
insuffisance rénale. Avec un seul niveau, il faut choisir entre deux erreurs :

- modifier la ligne — et la posologie initiale disparaît, la pancarte de J2 se
  met à afficher une dose qui n'y a jamais été donnée ;
- ouvrir une seconde ligne — et le compteur repart à J1, alors que
  l'antibiothérapie court depuis la première dose.

**La durée d'antibiothérapie est fausse dans les deux cas**, et c'est un
chiffre qui sort du service, vers le comité des infections. D'où deux niveaux.

### L'épisode de traitement

Ce qu'on traite, et depuis quand. Porte le compteur J{n} et la durée.

| Champ | Notes |
|---|---|
| categorie | Voir §5.2 |
| produit | Nom du médicament |
| **indication** | Le même produit redonné pour autre chose est un autre épisode |
| date_debut | **Début de l'épisode : détermine le compteur de jours** |
| duree_prevue_jours | **Nécessaire pour afficher « J7/7 »** |
| date_arret | Si arrêtée |
| statut | Active / Arrêtée |
| prescripteur | Utilisateur ayant créé la ligne |
| code_atc | Posé même vide — voir §5 (consommation en DDD) |

### La version de posologie

Combien on donne, et à partir de quand. Un épisode en a au moins une.

| Champ | Notes |
|---|---|
| date_debut | Premier jour où cette posologie s'applique |
| dose + unite | Ex. 1 g |
| rythme | Ex. ×3/j, ×4/j, continu, conditionnel |
| horaires | **Calculés** à partir du rythme — voir §5.3 |
| condition | Ex. « si T ≥ 38,5 °C » |
| dilution | PSE — ex. 0,5 mg/cc |
| vitesse | PSE et perfusions — cc/h, vitesse de départ (§5.5) |
| nb_ampoules | Affiché entre parenthèses pour les infirmiers |
| additifs | Ex. « + 3 KCl + 2 NaCl » |
| motif_changement | Ex. « adaptation à la fonction rénale » |

**Pas de date de fin.** Une version vaut jusqu'à ce que la suivante commence.
Une date de fin stockée à côté de la date de début de la suivante, ce sont deux
façons de dire la même chose — donc tôt ou tard deux réponses différentes à la
même question.

**Règles qui en découlent :**

- Changer une dose crée une version, jamais un épisode. Le compteur affiche
  J4, pas J1.
- La pancarte d'un jour donné montre la posologie **de ce jour-là**. Relire
  J2 doit montrer ce qui a été donné à J2.
- Une posologie ne s'applique jamais rétroactivement.
- Réenregistrer la même dose ne crée pas de version ; une correction saisie le
  jour même remplace la version du jour au lieu de s'empiler à côté d'elle.
- La durée d'antibiothérapie et le DOT se comptent **par épisode**. Compter les
  versions doublerait la durée de tout patient dont la dose a été adaptée.

**Arrêt d'un traitement :** l'épisode reste visible, **barré**. Jamais
supprimé. L'arrêt porte sur l'épisode, pas sur une version.

## 5.2 Composition par voie d'administration

La pancarte est **organisée par voie**, et le formulaire de saisie change de
champs selon la voie choisie. C'est ce qui permet de ne demander que ce qui a
un sens.

| Voie | Champs spécifiques demandés |
|---|---|
| `PO` | dose, unité, rythme |
| `IV` | dose, unité, rythme, condition éventuelle |
| `PSE` | produit, **dilution** (mg/cc), **nombre d'ampoules**, **vitesse** (cc/h) |
| `S/C` | dose, rythme |
| `Aérosol` | produit, dose, rythme |
| `Soins locaux` | libellé, rythme *(ex. soins oculaires x4/j)* |
| `Kinésithérapie` | libellé, rythme |
| `Entrées` | soluté, vitesse (cc/h), additifs *(ex. + 3 KCl + 2 NaCl)*, ou volume/24 h pour la nutrition |

Le **nombre d'ampoules** est affiché entre parenthèses sur la pancarte
imprimée, à destination des infirmiers.

## 5.2 bis Bilans à demander pour le lendemain

Section à part entière de la pancarte, remplie chaque soir par l'interne :
liste d'examens à cocher, avec l'heure de prélèvement *(par défaut 8 h,
tranché en FEUILLE_DE_ROUTE.md §9 — après les soins d'hygiène, avant les
prises de 8 h)*.

Liste de départ à valider : NFS · Ionogramme · Créatinine · Urée · CRP ·
Procalcitonine · Gaz du sang · TP/INR · Bilan hépatique · Hémoculture · ECBU ·
PDP. Un examen coché apparaît sur la pancarte imprimée pour que les infirmiers
le voient.

## 5.3 Calcul automatique des horaires

| Rythme | Horaires générés |
|---|---|
| ×1/j | 8 h |
| ×2/j | 8 h — 20 h |
| ×3/j | 8 h — 16 h — 24 h |
| ×4/j | toutes les 6 h |
| ×6/j | toutes les 4 h |
| Continu | pas d'horaire, débit affiché |
| Conditionnel | pas d'horaire, condition affichée |

Horaires modifiables ligne par ligne.

✅ *Tranché en v1.3 : ×4/j → 6 h — 12 h — 18 h — 24 h, ×6/j → 4 h — 8 h — 12 h —
16 h — 20 h — 24 h. Valeur par défaut modifiable dans `rea/config.py`
(`HORAIRES_PAR_RYTHME`) et ligne par ligne dans l'écran Prescrit. À
contre-valider par un senior.*

## 5.4 Compteurs de jours

Comportement attendu, tel que décrit :

```
Jour d'introduction :  Introduction de Targocid 400 mg ×2/j
Lendemain :            J2 Targocid 400 mg ×2/j
Antibiotique en cours : J2 Tienam 1 g ×3/j
Dernier jour prévu :   J7/7 Tazobactam 1 g ×4/j
```

L'affichage `J{n}/{durée}` n'apparaît que si une durée prévue a été saisie.

## 5.5 Génération de la fiche du lendemain

**La fonction la plus importante du logiciel.**

Un bouton « Préparer la pancarte de demain » produit une copie où :

- tous les compteurs de jours ont avancé d'un cran
- les lignes actives sont reconduites à l'identique
- les lignes arrivées à échéance sont signalées visuellement
- les lignes arrêtées disparaissent
- une zone vide attend les bilans à demander pour le lendemain

L'interne vérifie, modifie, ajoute, imprime.

## 5.6 Bilan hydrique — entrées

Calcul automatique du **volume total des entrées sur 24 h** :

```
Σ (perfusions : vitesse cc/h × 24)
+ Σ (PSE : vitesse cc/h × 24)
+ Σ (médicaments IV : volume de dilution × nombre de prises)
+ nutrition entérale (volume/j)
+ nutrition parentérale (volume/j)
```

Les **sorties** restent manuscrites sur la pancarte par les infirmiers. Le
logiciel fournit donc les entrées, pas le bilan complet. C'est déjà l'essentiel
du travail de calcul évité.

## 5.7 Surveillance infirmière

**Pas de saisie numérique.** Les infirmiers écrivent à la main sur la pancarte
imprimée. La pancarte doit donc réserver des zones manuscrites suffisantes :
constantes horaires, diurèse, drains, observations.

Cette décision simplifie considérablement le projet et supprime toute la
phase 3 initialement prévue.

---

# 6. EXPLORATIONS ET ACTES

Écran dédié, distinct des bilans biologiques. Il enregistre les explorations
**avec leurs valeurs chiffrées**, pas seulement un compte rendu textuel, et
depuis la v1.6 **tous les dispositifs invasifs** du patient.

## 6.0.0 Dispositifs et actes (v1.6)

Une seule table `dispositif` couvre tout ce qui se pose et se retire :
intubation, sédation, trachéotomie, sonde nasogastrique (avec sa fixation en
cm), gastrostomie, sonde urinaire, cathéter sus-pubien, cathéter veineux
central (avec son site), PICC, cathéter artériel, voie périphérique, drains,
DVE, épuration extra-rénale.

**Rien n'est saisi deux fois et aucune durée n'est stockée.** Chaque ligne
porte `date_pose` et `date_retrait` ; tous les compteurs se calculent :

| Situation | Affichage | Convention |
|---|---|---|
| Dispositif en place | « Intubé J3 », « KT central J5 » | J1 = jour de la pose |
| Dispositif retiré | « Extubé J2 », « Arrêt sédation J1 » | J0 = jour de l'événement |
| Durée de ventilation | somme des épisodes d'intubation | calculée |

C'est la même règle que les compteurs de prescription (§5.4) : le logiciel
calcule des dates, jamais une dose.

Ces compteurs alimentent automatiquement le bandeau d'état du patient, le
tableau des lits, l'évolution du jour et le compte rendu de sortie. Ils
donnent aussi le dénominateur des taux d'infection nosocomiale — PAVM pour
1 000 jours de ventilation, ILC pour 1 000 jours de cathéter (§9.4), sans
aucune saisie supplémentaire.

## 6.0.1 Table `exploration`

`sejour_id` · `date_heure` · `type` · `valeurs` *(paires clé-valeur selon le
type)* · `conclusion` *(texte court)* · `operateur`

## 6.0.2 Types et valeurs à saisir

| Exploration | Valeurs chiffrées |
|---|---|
| **DTC** (Doppler transcrânien) | IP droit, IP gauche, Vm droite, Vm gauche, conclusion |
| **TDM cérébrale** | date, conclusion, présence de lésion(s) codée |
| **ETT** | FEVG, diamètre de la VCI, PAPS, épanchement |
| **Échographie pleuro-pulmonaire** | épanchement D/G, condensation, lignes B |
| **Radiographie thoracique** | conclusion, foyer codé |
| **EEG** | conclusion |
| **Fibroscopie bronchique** | indication, résultat, prélèvement associé |

Liste à compléter et valider avec un senior.

## 6.0.3 Deux principes

Les explorations sont **proposées par le protocole du diagnostic** — un
traumatisme crânien programme la TDM de contrôle à H48 et le DTC quotidien.

Les valeurs saisies sont **reprises automatiquement dans l'évolution du jour**
sous une rubrique « Explorations », sans aucune ressaisie, et restent
exploitables en recherche (cinétique de l'IP, évolution de la FEVG).

# 7. BILANS

## 7.1 Import

L'utilisateur dispose déjà d'un **fichier HTML de saisie des bilans** produisant
un format de sortie spécifique — à intégrer directement dans l'application.

✅ **Fichier reçu le 2 septembre 2026** (`bilan_rea.html`) et intégré : mêmes
analytes, mêmes groupes, même texte généré (`rea/analytes.py`,
`rea/services/bilans.py`). Contrairement au fichier d'origine (autonome,
JS pur, valeurs non conservées), les valeurs saisies sont maintenant
**stockées en base** — nécessaire pour les courbes de cinétique (§7.2) et
l'export recherche, qui étaient hors de portée du fichier HTML seul.

⚠️ **Aperçu, appelé à évoluer** (indiqué par l'utilisateur à la remise du
fichier) : calcul automatique de la clairance de la créatinine à ajouter,
au moins un champ à retirer — à préciser en session. Le socle de bilans
ci-dessous est bâti pour absorber ces changements sans refonte : un
analyte s'ajoute ou se retire par une ligne dans `rea/analytes.py`.

## 7.2 Affichage

- Tableau par date
- **Courbes de cinétique** par analyte — c'est ce qui manque le plus dans un
  EHR classique
- Signalement des valeurs hors bornes *(bornes à définir)*

## 7.3 Gaz du sang

Structure particulière, toujours groupée avec les paramètres ventilatoires :
`pH` · `PaO₂` · `PaCO₂` · `HCO₃⁻` · `mode ventilatoire` · `FiO₂` · `PEP` · `FR`
· **rapport P/F** *(calculé automatiquement : PaO₂ / FiO₂)*

## 7.4 Microbiologie

Table séparée. Prélèvements : hémoculture · ECBU · ponction lombaire · PDP ·
prélèvement de cathéter · autre.

Champs : date, type de prélèvement, résultat *(stérile / positif / en cours)*,
germe identifié, antibiogramme *(texte libre en v1, structuré plus tard)*.

---

# 8. ÉVOLUTION QUOTIDIENNE

## 8.1 Format cible — validé

```
01/09/2026, J{n} d'hospitalisation :
Sur le plan Neurologique :
Sur le plan respiratoire :
Sur le plan hémodynamique :
Sur le plan Infectieux :
Explorations :
- DTC (08h) : IP 1.35 D / 1.28 G ; Vm 42 D / 45 G
Bilan du jour :
Hématologie :
Biochimie :
Gaz du sang : pH = 7.4 ; PaO₂ = 80 mmHg ; PaCO₂ = 40 mmHg ; HCO₃⁻ = 24 mmol/L ;
sous le mode VAC ; FiO2 = 50% ; PEP = 6 ; FR = 18 ; Rapport = 160
Sous le traitement :
J2 Tienam 1g*3/j
J2 Coli 3MUI*3/j
Introduction de Targocid 400mg*2/j
J7/7 Tazobactam 1g*4/j
Conduite :
==>
==>
==>
```

## 8.2 Répartition génération / saisie

| Section | Origine |
|---|---|
| En-tête, date, jour d'hospitalisation | **Généré** |
| Les quatre plans | **Saisie manuelle** |
| Explorations du jour | **Généré** depuis l'écran Explorations |
| Bilan du jour, gaz du sang | **Généré** depuis les bilans du jour |
| Sous le traitement | **Généré** depuis les lignes de prescription actives |
| Conduite | **Vide**, à compléter par l'interne |

Bouton « Copier » qui place le texte dans le presse-papier pour collage dans le
DMI.

⚠️ **Test à faire tôt :** coller un texte avec accents, symboles (`HCO₃⁻`,
`PaO₂`) et retours à la ligne dans le DMI et vérifier qu'il n'est pas déformé.
Si le DMI abîme les indices Unicode, il faudra basculer sur `HCO3-` et `PaO2`.

*v1.3 : le basculement est prêt — `rea/config.py`, drapeau `SYMBOLES_UNICODE`.
Mis à `False`, tout le texte généré sort en `HCO3-`, `PaO2`, `PaCO2`. Le test
dans le DMI reste à faire.*

---

# 9. STATISTIQUES ET RECHERCHE

## 9.1 Demande exprimée

Pas de question de recherche précise pour le moment. Objectif : une interface
d'exploration permettant de visualiser l'activité du service, de chercher des
relations, et surtout de **faciliter le recueil de données**.

## 9.2 Le problème à signaler

Un recueil sans variables de jugement ne produit rien de publiable. En
réanimation, presque toute publication repose sur un socle standard. Sans lui,
la base sera volumineuse et inexploitable.

### Socle minimal proposé — ❓ à valider

| Variable | Pourquoi |
|---|---|
| **IGS II à l'admission** | Score de gravité, exigé par tout relecteur pour comparer des groupes |
| **SOFA quotidien** | Évolution des défaillances, critère de jugement fréquent |
| **Dates d'intubation et d'extubation** | Durée de ventilation, jours vivants sans ventilateur |
| **Épuration extra-rénale** oui/non + durée | Défaillance rénale |
| **Mortalité en réanimation** | Critère de jugement principal quasi universel |
| **Mortalité à J28** | Standard international |
| **Durée de séjour** | Calculée automatiquement |
| **Infections nosocomiales** (PAVM, ILC) | Axe de publication très accessible dans ce service |
| **Durée d'antibiothérapie, désescalade** | Idem — déjà à moitié capturé par le prescrit |

Ces variables coûtent quelques secondes de saisie par jour et déterminent la
totalité de la valeur scientifique du projet.

*v1.3 : le schéma SQL porte déjà ces variables (tables `ventilation_episode`,
`epuration_episode`, `infection_nosocomiale`, `score_quotidien`,
`evaluation_admission`, champs `deces_reanimation` et `statut_j28` du séjour).
Tant que la validation n'est pas faite, aucun de ces écrans de saisie n'est
imposé : les tables existent, vides, et ne coûtent rien.*

## 9.3 Fonctions de l'interface statistique

- Tableau de bord d'activité : occupation, durées de séjour, répartition des
  motifs, mortalité
- Constructeur de cohorte : filtres croisés *(ex. « tous les traumatismes
  crâniens de 2026 avec IGS II > 40 »)*
- Export CSV **pseudonymisé automatiquement** — identifiant d'étude stable,
  ni nom, ni matricule, ni date de naissance complète (âge uniquement)
- Diagramme de flux type STROBE

## 9.4 Quatre usages au-delà de la cohorte

1. **Écologie bactérienne du service** — germes, résistances, prélèvements,
   durée moyenne d'antibiothérapie, taux de désescalade. Les données viennent
   du prescrit et de la microbiologie, déjà saisis : c'est le sujet le plus
   accessible pour une première publication.
2. **Indicateurs de qualité et de sécurité** — PAVM pour 1 000 jours de
   ventilation, délai admission-bloc, durée de séjour, taux d'occupation,
   mortalité, suivis mois par mois.
3. **Comparaison de deux périodes ou de deux pratiques** — un avant-après
   devient possible dès qu'on dispose de deux années comparables.
4. **Préparation d'une publication** — export anonymisé pour R ou SPSS,
   diagramme de flux STROBE, tableau descriptif de la population.

## 9.5 Alignement sur le standard ANZICS

Le registre australo-néo-zélandais publie un dictionnaire de 109 variables, en
usage depuis 1992, ainsi qu'un dictionnaire pour programmeurs et un guide de
validation destiné aux systèmes développés hors de leur logiciel.

**Principe retenu : on adopte leurs définitions, on ne rejoint pas leur
registre.** L'alignement des définitions rend les chiffres comparables à la
littérature internationale, sans démarche ni coût.

### Ce qui est repris

| Bloc | Origine dans le logiciel | Coût de saisie |
|---|---|---|
| Identité, dates, provenance, destination, devenir | Écrans Admission et Sortie | nul |
| Conditions chroniques — respiratoire, cardiovasculaire, rénale, hépatique, immunosuppression, cancer, diabète, + « aucune » | Écran Admission, listes à aligner | nul |
| Biologie des premières 24 h — Na, K, bicarbonates, créatinine, urée, hématocrite, leucocytes, bilirubine, pH, PaO₂, PaCO₂, FiO₂ | Fichier de bilans existant | nul |
| **Albumine et glycémie** | **Deux champs à ajouter au fichier de bilans** | nul |
| Ventilation invasive à J1, dates d'intubation et d'extubation | Écran Explorations | 10 s |
| Insuffisance rénale aiguë | **Calculée** : créatinine > 133 µmol/L + diurèse 24 h < 410 mL + absence d'IRC | nul |
| Score de gravité | **Calculé** à partir des variables ci-dessus | nul |
| Constantes extrêmes 24 h — T°, FC, PAS, PAM, FR | Recopiées une fois depuis la pancarte manuscrite | 3 min |
| Diurèse des 24 h | Recopiée depuis la pancarte | 10 s |
| Glasgow (œil, verbal, moteur) et score de fragilité | Jugement clinique à l'admission | 30 s |

**Total : environ 4 minutes par patient, une seule fois à l'admission.**

### Simplification retenue

Les valeurs **d'admission** sont saisies plutôt que les pires valeurs des
24 heures. Une étude sur 11 107 admissions montre une capacité de
discrimination équivalente pour APACHE II entre les deux méthodes. À mentionner
explicitement dans toute publication.

### Ce qui est écarté

- **Codage diagnostique APACHE III** — plusieurs centaines de catégories avec
  règles de hiérarchie. Trop lourd pour démarrer ; on garde la liste maison,
  le rapprochement se fera plus tard si nécessaire.
- **Score ANZROD** — calibré sur la population australienne. On utilise
  **l'IGS II**, standard francophone, qui partage l'essentiel des variables.
- Clé de liaison statistique SLK-581 et statut indigène — hors contexte.

### Champs qui pèsent le plus

ANZICS signale explicitement les champs déterminants pour l'ajustement au
risque : **diagnostic, physiologie, devenir hospitalier, Glasgow, objectifs
thérapeutiques et conditions chroniques**. Ce sont ceux à saisir avec le plus
de soin.

---

# 10. QUESTIONS OUVERTES

| # | Question | Bloque | État |
|---|---|---|---|
| 1 | Le socle de variables de recherche (§9.2) est-il validé ? | Modèle de données | ouverte — tables créées, saisie non imposée |
| 2 | Scores IGS II et SOFA : saisis systématiquement ou optionnels ? | Modèle de données | ouverte |
| 3 | Ventilation : suivi des dates d'intubation/extubation ? | Modèle de données | **résolue v1.6** — saisi dans l'écran Explorations et actes, durée calculée |
| 4 | Infections nosocomiales : à tracer ? | Modèle de données | ouverte — table prête |
| 5 | Mortalité : réanimation seule, ou aussi J28 ? | Modèle de données | ouverte — les deux champs existent |
| 6 | Heure de départ pour un rythme ×4/j | Prescription | **tranchée v1.3** — 6-12-18-24, modifiable |
| 7 | Format exact de copier-coller du DMI pour les bilans | Import bilans | **résolue v1.5** — fichier HTML reçu et intégré |
| 8 | Bornes de normalité pour signaler les valeurs anormales | Import bilans | ouverte — bornes usuelles posées (affichage) et bornes physiologiques posées (contrôles de saisie, v1.7), **les deux à valider par un senior** |
| 13 | Source officielle des référentiels CIM-10, LOINC et ATC | Export recherche | **ouverte** — correspondances LOINC provisoires en v1.7, `LOINC_VALIDE = False` |
| 9 | Poste du chef de service : copie lecture seule ou rien ? | Architecture | ouverte |
| 10 | Liste des gestes chirurgicaux les plus fréquents | Interventions | ouverte — liste provisoire dans `listes.py` |
| 11 | Qui maintient le programme en cas d'absence de l'auteur | Continuité | ouverte |
| 12 | Les protocoles de pré-remplissage doivent être **signés** avant usage | Protocoles | ouverte — le brouillon TC est marqué non validé |

## Documents attendus

- 📎 **PDF du prescrit (version bêta)** — conditionne toute la partie 5
- ✅ **Fichier HTML de saisie des bilans** — reçu et intégré (v1.5). Une
  version plus détaillée est annoncée (clairance automatique, un champ en
  moins) : à recevoir et à répercuter dans `rea/analytes.py`

---

# 11. FEUILLE DE ROUTE

Estimation en **heures de travail effectif** (session de travail commune :
je code, tu testes et tu décides). Hors délais d'attente extérieurs.

| Bloc | Contenu | Heures | État |
|---|---|---|---|
| **0** | Modèle de données complet, listes codées, schéma SQL | 4-6 | ✅ fait (v1.3) |
| **1** | Socle : base, sauvegardes, sélecteur d'utilisateur, tableau des 12 lits, création/sortie de séjour, identité | 8-10 | ✅ fait (v1.4) |
| **2** | **Prescription** : lignes, catégories, horaires, compteurs de jours, duplication J+1, bilan hydrique des entrées, impression A4 | 18-22 | ✅ fait (v1.4) — impression en mise en page provisoire, à reprendre sur le PDF réel |
| **3** | Évolution quotidienne générée + bouton copier | 6-8 | ◐ en cours — génération et écran faits ; ne reprend pas encore Explorations ni Bilan du jour (blocs 4/6 non commencés) |
| **4** | Bilans : import, tableau, courbes, gaz du sang, microbiologie | 12-16 | ◐ en cours (v1.6) — saisie, stockage structuré, texte généré, tableau par date, variations, bornes usuelles et courbes faits ; microbiologie non faite |
| **5** | Motifs, régions traumatiques, antécédents + recherche ICD-10, protocoles de pré-remplissage, sortie | 12-15 | ◐ en cours — motifs, régions, antécédents (liste courte), interventions, sortie et compte rendu généré faits, écrans Admission/Sortie construits ; recherche ICD-10, interventions en UI et application effective des protocoles non faites |
| **6** | Statistiques, constructeur de cohorte, export pseudonymisé | 8-10 | ○ à faire |
| **7** | Robustesse, journal des modifications, finitions, documentation | 6-8 | ◐ partiel — journal et sauvegardes faits |
| | **Total** | **75-95 h** | |

## Ordre d'exécution

Blocs **0 → 1 → 2** en priorité absolue. À la fin du bloc 2, le logiciel résout
déjà le problème principal du service et peut être utilisé quotidiennement.

Ce sous-ensemble représente **environ 30 heures**. C'est le seuil qui compte :
au-delà, chaque bloc est une amélioration facultative, et une interruption du
projet ne laisse jamais un chantier inutilisable.

## Règle de déploiement

Usage en solo pendant **au moins deux semaines complètes** avant ouverture aux
13 utilisateurs. Une première impression ratée dans un service ne se rattrape
pas.

---

# 12. PROTOCOLE DE SESSION

Au début de chaque session de travail :

1. Renvoyer **ce document** (version à jour)
2. Renvoyer le **code actuel** (dossier compressé ou fichiers)
3. Indiquer le **bloc en cours** et ce qui a été testé depuis la dernière fois

En fin de session :

4. Reporter dans ce document les **décisions prises** et les questions résolues
5. Incrémenter le numéro de version en en-tête
6. Conserver la version précédente du code — jamais d'écrasement

---

# JOURNAL DES VERSIONS

**v3.28 — 10 septembre 2026 — un catalogue de molécules qui apprend**

Le produit d'une ligne de prescription se tapait à la main. On retapait
« Imipénème » vingt fois par semaine ; on l'écrivait de vingt façons —
« imipeneme », « Tienam », « TIENAM 1g » ; et surtout **« quelle molécule sur
quel type d'infection » n'avait plus de réponse calculable**, puisque le
logiciel ne savait pas que ces graphies désignaient le même produit (demande
du service, 10 septembre).

*Deux sources, une seule liste.* `referentiels/medicaments.json` livre
98 molécules courantes de réanimation polyvalente, chacune avec son unité
usuelle et ses **noms commerciaux en synonymes** : on tape « tie » et
Imipénème sort, parce que « Tienam » est ce qu'on a en tête au lit du malade.
On cherche aussi par famille — « curare », « aminoside », « C3G ». Et la table
`medicament_local` se remplit **sans que personne la remplisse** : la première
prescription d'une molécule absente l'y inscrit, et elle est proposée dès la
suivante. Personne n'a de catalogue à préparer avant de pouvoir travailler.

*Ce qui est écrit reste la dénomination commune*, pas la marque : c'est elle
qui permet de compter une molécule à travers ses noms commerciaux. Les marques
servent à la chercher, pas à la nommer.

*Aucune posologie n'est proposée*, et c'est la règle du service tenue ici
comme ailleurs. Le catalogue porte l'unité usuelle — « g » plutôt que « mg »
pour l'imipénème — ce qui est une unité et non une dose. La dose part vide.
Une dose pré-remplie est une dose validée sans être lue.

*Le classement compte plus que le filtre.* « tie » trouve Tienam par le début
d'un mot, mais aussi « antiepileptique » en plein milieu : trois molécules
justes noyées sous quatre qui n'ont rien à voir, c'est une liste qu'on cesse
d'utiliser. `chercher` classe donc début de nom, puis début de mot, puis
milieu — et abandonne le milieu de mot dès qu'il a mieux.

*Un catalogue qui apprend finit par contenir les fautes qu'on a prescrites.*
D'où **Administration → Molécules** : chercher, corriger, retirer. Aucun de
ces gestes ne touche aux prescriptions déjà écrites — une ligne porte le nom
écrit ce jour-là, et le réécrire changerait une prescription signée.

**Limite connue.** Le classement de `chercher` ne pilote pas la liste
déroulante du prescrit : Streamlit filtre lui-même sur l'étiquette affichée,
par simple sous-chaîne. La bonne molécule sort en tête, mais quelques lignes
sans rapport peuvent l'accompagner. Le classement sert l'écran d'administration
et restera là si la liste du prescrit est un jour pilotée côté serveur.

**Vérifications.** 1 068 tests passent (17 ajoutés), pyflakes propre. Recette
navigateur rejouée sur les cinq rôles, section « Molécules » comprise : aucun
écran en erreur. Vérifié à l'écran : « tie » → Imipénème · Tienam en tête,
« curare » → les quatre curares.

**v3.27 — 10 septembre 2026 — une porte de secours pour les comptes**

Le service s'est retrouvé enfermé dehors en testant l'application : plus
d'accès administrateur, et rien dans le logiciel pour en refaire un.

L'écran des comptes demande le droit `comptes`, que seul le rôle
**Administrateur** possède. Le logiciel refusait déjà de *retirer* le dernier
administrateur — mais cette garde ne couvre pas les trois cas qui enferment
réellement : une base qui porte des comptes sans qu'aucun ne soit
administrateur (l'écran de première ouverture ne s'affiche plus, et personne
ne peut en créer), le seul administrateur désactivé, ou son code perdu. Le
seul recours restant était d'ouvrir la base SQLite à la main.

`outils/administrateur.py` lit et répare : `--lister`, `--promouvoir`,
`--creer`, `--code`, `--reactiver`.

**Pourquoi un programme à part et non un bouton.** Un bouton « devenir
administrateur » serait atteignable depuis n'importe quel téléphone du
service, et rendrait inutile tout le reste. L'outil demande un accès aux
fichiers du PC serveur — c'est-à-dire l'accès qui permettrait de toute façon
de modifier la base directement. La barrière reste au bon endroit : la session
Windows du poste serveur. Et chaque geste passe par les services habituels,
donc le **journal d'audit** l'enregistre.

Deux pièges rencontrés en l'écrivant, tous deux dans les tests désormais.
`utilisateurs.par_nom` ne regarde que les comptes **actifs** — juste pour
l'écran d'ouverture, faux ici, puisque le compte qu'on vient réactiver n'est
par définition pas actif. Et l'état d'un compte se lit sur `actif`, pas sur
`supprime` : un compte désactivé se serait affiché comme actif.

Le code se tape sans s'afficher et ne se passe jamais en argument — il
resterait dans l'historique du terminal et dans la liste des processus.

**Vérifications.** 1 045 tests passent (7 ajoutés, dont l'outil lancé pour de
vrai dans son propre processus). Essayé de bout en bout sur une base à deux
comptes sans administrateur : `--lister` le signale, `--promouvoir` rend la
main, le journal d'audit trace.

**v3.26 — 10 septembre 2026 — trois jours côte à côte à la visite, et un tableau des constantes daté à part**

*Trois jours de biologie et de gaz.* Une valeur seule ne dit pas si le rein
décroche ; deux ne disent pas s'il décroche ou s'il remonte. Une créatinine à
152 après 196 rassure — après 196 puis 120, elle inquiète, et la conduite du
jour n'est pas la même (demande du service, 10 septembre). Les gaz et la
biologie sont donc rendus en trois colonnes, la plus récente à droite et en
gras, et **seule celle-là porte les alertes en rouge** : colorer les trois
ferait lire trois anomalies là où il n'y en a qu'une.

Trois jours **renseignés**, pas trois jours de calendrier : on ne prélève pas
tous les jours en réanimation, et deux colonnes vides n'apprennent rien.
Chaque colonne est datée, parce que deux colonnes voisines séparées de quatre
jours ne se lisent pas comme une cinétique. Pour les gaz, un par jour — le
dernier — avec son heure : un patient qui en a quatre dans la journée
remplirait sinon la colonne de sa seule matinée, et un gaz de 6 h ne se
compare pas à un gaz de 22 h.

*Le tableau des constantes, en bas et daté à part.* Vingt-quatre colonnes
serrées dans la demi-largeur de droite obligeaient à faire défiler le tableau
pour lire la nuit ; en bas et sur toute la largeur, la journée se lit d'un
seul regard. Et il a **sa propre date** : les deux questions ne tombent pas
le même jour — on regarde le prescrit d'aujourd'hui en se demandant comment
s'est passée la nuit d'avant-hier, et changer la date du haut de l'écran
changerait aussi les traitements affichés.

**Vérifications.** 1 038 tests passent (10 ajoutés), pyflakes propre. Recette
navigateur rejouée sur les cinq rôles : aucun écran en erreur.

*Un bug trouvé par la recette, et pas par les tests.* L'écran lisait `v.id`
sur une `Variation`, qui porte `analyte` : la Visite tombait entièrement —
biologie, infectieux et plans avec elle — alors que les tests de service
passaient tous, parce qu'aucun ne touchait ce chemin. Corrigé, et figé par un
test qui lit le code source. C'est la troisième fois qu'ouvrir réellement les
écrans trouve ce que la suite ne voit pas.

**v3.25 — 10 septembre 2026 — la diurèse se calcule, elle ne s'additionne plus**

*L'erreur, d'abord.* La version du matin additionnait les cases horaires de la
diurèse. Ce n'est juste que si chaque case contient ce qui est sorti pendant
l'heure. Or l'infirmier y note **ce qu'il lit sur le sac** : un patient qui
fait 100 mL/h pendant douze heures produit 1 200 mL, et la somme des niveaux
lus en annonce **7 800**. L'erreur grandissait avec le nombre d'heures
relevées, pas avec ce que le patient produit — l'équipe la plus
consciencieuse aurait faussé le plus le bilan.

*La deuxième erreur.* La ligne « Jetés », livrée le matin même comme une
perte supplémentaire, se trompait de sens : jeter un sac est un **geste de
comptage**, et ce qu'il contient est déjà la diurèse. L'ajouter au total des
pertes doublait l'urine du patient. La ligne est retirée du bilan, de la
feuille imprimée et du plan hémodynamique.

*Ce qui la remplace.* La case horaire porte le **niveau lu**, et une case à
cocher dit « j'ai jeté le sac après ce relevé ». `domaine/recueil.py` fait la
soustraction que personne ne doit faire au lit du malade :

    sortie(h) = niveau(h) − niveau du relevé précédent dans le même sac

et, après un sac jeté, le relevé suivant se compte à partir de zéro. Jeter un
sac ne change alors pas d'un millilitre le total du jour — c'est le test qui
tient cette propriété.

*Le piège de 8 h.* « À 8 h on jette celui de la nuit. » Attribuer le sac
entier au jour du changement donnerait au 10 l'urine du 9, et un bilan faux
les deux jours. En comptant les différences heure par heure, chaque heure
reste dans sa journée. C'est aussi pourquoi le calcul ne se coupe pas à 7 h :
le premier relevé d'un jour se compare à celui de la veille au soir, sinon
une heure sur vingt-quatre serait perdue tous les jours. Les relevés sont
donc datés en horodatage réel — un relevé de 3 h rangé sous le 9 a eu lieu le
10 — sans quoi 23 h et 1 h se compareraient à l'envers et la diurèse de la
nuit serait négative.

*Deux règles de sûreté.* Le **premier relevé d'un séjour n'est pas une
sortie** : le sac contenait déjà quelque chose, l'attribuer à l'heure où on a
commencé à regarder inventerait une diurèse. Et un **niveau qui baisse sans
sac déclaré jeté** n'est jamais compté en négatif : quelqu'un a vidé le sac
sans le dire, on compte le niveau lu — le minimum certain — et on le signale
sous le tableau. Un total amputé qui se présente comme complet est pire qu'un
total absent : le médecin le recopie.

*À l'écran.* L'infirmier voit deux lignes dans sa grille : les niveaux qu'il a
écrits, en gris, avec un ↺ à chaque sac jeté ; et en dessous les volumes que
le logiciel en déduit, avec le total du poste. Le médecin voit la même chose
dans Visite et Évolution. Personne n'a de soustraction à faire, et tout le
monde peut vérifier celle du logiciel.

**Vérifications.** 1 028 tests passent, pyflakes propre. Recette navigateur
rejouée sur les cinq rôles : aucun écran en erreur. Vérifié à l'écran sur un
sac qui court d'un jour sur l'autre : niveaux 873 puis 943 à 8 h, sac jeté,
85 à 9 h — le logiciel compte 70 puis 85, et 1 956 mL sur les 24 h.

**v3.24 — 10 septembre 2026 — les seuils de fièvre du service, les jetés, et le relevé infirmier ouvert au médecin**

*Trois états thermiques, aux seuils du service.* Les bornes provisoires
(37,5 et 38,3 °C) sont remplacées par celles que le service a arrêtées :
apyrétique en dessous de 38, subfébrile de 38 à **38,5 inclus**, fébrile
**au-dessus** de 38,5. Les deux bornes ne se comparent pas de la même façon
et c'est voulu ; les clés du référentiel le disent (`subfebrile_a_partir_de_c`,
`febrile_au_dessus_de_c`) pour qu'on n'ait pas à relire le code. Un `<` à la
place du `<=` rendrait fébrile un patient à 38,5 — et ferait décrocher, dans
l'analyse du délai d'apyrexie, toute une colonne de patients qui n'ont pas
décroché.

*Les jetés.* Ce qui est recueilli puis jeté au lieu d'être réinjecté — le
liquide gastrique aspiré, avant tout. L'infirmier les relève heure par heure,
dans un groupe **Sorties de l'heure** distinct des constantes vitales, et le
cumul du poste s'affiche au bout de sa grille. Ils entrent dans le **total des
pertes** du bilan hydrique, ont leur ligne sur la feuille imprimée et leur
case dans le plan hémodynamique. Sans eux, un patient qui perd huit cents
millilitres par la sonde gastrique a une diurèse correcte, des drains qui ne
donnent pas, et un bilan qui le déclare en excès de deux litres pendant qu'il
se déshydrate.

Une asymétrie assumée entre les deux sorties : des jetés absents comptent
pour zéro, une diurèse absente prive de bilan. La diurèse est mesurée chez
tout le monde ; la plupart des patients n'ont rien à jeter, et exiger la case
priverait de bilan les trois quarts du service.

*Le relevé infirmier ouvert au médecin.* Vingt-quatre lignes par jour étaient
saisies et personne d'autre ne les voyait. Elles s'affichent désormais dans
la **Visite** et dans l'**Évolution**, en lecture seule — la saisie appartient
à celui qui est au lit du malade.

Trois précautions portées par le rendu lui-même. Les heures sont dans l'ordre
du poste (7 → 6) et non de minuit à minuit : les relevés d'une nuit sont
rangés sous le jour de la prise de poste, et une grille partant de minuit
afficherait la fin de la nuit **avant** le matin qui l'a précédée — la courbe
se lirait à l'envers. La colonne de synthèse est placée **avant** les heures,
parce que vingt-quatre colonnes ne tiennent pas dans la moitié d'un écran et
que ce qui dépasse à droite est justement ce qu'on vient lire. Et on ne
résume que ce qui se résume : extrêmes pour les constantes, somme pour les
sorties — la somme des températures d'une journée n'est pas une température.

Sous la diurèse et les jetés des 24 h, le total infirmier est **proposé** au
médecin, jamais écrit à sa place : un relevé à trous n'est pas une mesure des
24 h, et c'est ce chiffre-là qui entre ensuite dans le bilan.

**Vérifications.** 1 019 tests passent (20 ajoutés), pyflakes propre. Recette
navigateur rejouée sur les cinq rôles : aucun écran en erreur. Chaîne complète
vérifiée à l'écran — 700 mL de jetés saisis font passer le total des pertes de
2 646 à 3 346 mL et le bilan de +2 862 à +2 162 mL.

**v3.23 — 10 septembre 2026 — recette complète, deux bugs trouvés, et les guides**

*Recette.* Chaque écran de chaque rôle ouvert dans un navigateur, pour de
vrai : cinq rôles, sept écrans de fiche, six vues de recherche, sept sections
d'administration, quatre vues de surveillance. Deux bugs en sont sortis, que
la suite de tests ne pouvait pas voir.

**L'accueil du rôle était une prison.** Le point d'entrée reposait l'écran
d'accueil « chaque fois que l'écran courant est absent ». Or ouvrir un
dossier retire l'écran courant pour laisser passer la fiche — l'accueil était
donc reposé aussitôt. Conséquence : le surveillant et l'infirmier ne
pouvaient **jamais** ouvrir un dossier patient, renvoyés chez eux à chaque
tentative. Toute la différence tenait entre « une fois par session » et
« chaque fois qu'il manque ».

**Une unité d'une seule lettre emportait l'écran des protocoles.** `UNITES`
est une liste plate de chaînes — « mg », « g » — et non des paires
code/libellé. `libelle()` y lisait `entree[1]`, c'est-à-dire la deuxième
lettre : `IndexError` sur « g », et l'écran entier tombait. Corrigé à
l'appel, et `libelle()` tolère désormais une liste plate — c'est la même
famille que le bilan disparu du référentiel, en v3.21.

Les deux sont figés par des tests qui lisent le code source : ils tiennent
sans navigateur.

*Deux guides, dans le dépôt.*

**INSTALLATION.md** part d'un PC Windows neuf et va jusqu'aux infirmiers
connectés depuis leur téléphone : Python, dépendances, premier compte,
comptes du service, sauvegardes, puis le routeur du service, l'adresse fixe
du serveur, le lancement sur le réseau privé, et enfin l'accès filaire des
autres postes de l'hôpital — avec ce que ce dernier choix implique. Chaque
étape se termine par une vérification ; les pièges du double réseau
(passerelle à laisser vide, pas de pont, `REA_HOTE` sur l'IP privée et non
sur `0.0.0.0`) y sont expliqués plutôt que mentionnés.

**GUIDE_UTILISATION.md** donne quatre guides indépendants — infirmier,
surveillant, résident, senior — qui suivent la journée réelle du poste. Ils
disent aussi ce que le logiciel **refuse** de faire et pourquoi : pas de
posologie proposée d'elle-même, pas de chiffre incalculable affiché, pas de
pourcentage sous cinq patients.

**v3.22 — 10 septembre 2026 — un « non donné » qui dit pourquoi, et qui arrive à qui doit agir**

« Il arrive qu'il manque le médicament, ou qu'on ne puisse pas le donner —
pas encore de sonde pour le per os » (remarque du service). Le motif était un
champ de texte libre : il rendait service à qui relisait la garde, et à
personne d'autre.

Or ces motifs-là ne sont pas des cases cochées, ce sont des **choses à
faire**. Un antibiotique qui manque à 8 h manquera à 16 h si personne ne le
commande, et la sonde absente à midi le sera encore le soir. « Rupture » tapé
à la main ne se compte pas et ne remonte nulle part.

Douze motifs dans `referentiels/motifs_non_administration.json`, chacun
portant **qui doit agir** : la pharmacie (rupture, dotation épuisée), l'abord
(pas de SNG, pas de voie, voie obstruée), le médecin (contre-indication,
refus, intolérance), ou personne (à jeun, au bloc, suspendu). Déplacer un
motif d'une catégorie à l'autre est une décision de service, pas une
modification de programme.

Ce que ça change, et c'est tout l'intérêt :

* **l'infirmier** choisit dans une liste, et l'écran lui dit tout de suite si
  son motif va remonter. Le texte libre reste **à côté** et non à la place :
  il précise quelle voie était obstruée, il ne remplace pas le motif ;
* **le surveillant** ouvre sur « Non donnés à traiter », groupés par action,
  avec le patient et son matricule — c'est la vue qui a une heure de
  validité, les nouveautés et les affectations peuvent attendre midi. Ce qui
  n'appelle aucune action n'y figure pas : une liste qui contient tout ne se
  lit plus ;
* **le médecin** voit sur le prescrit de son patient ce qui n'est pas passé
  aujourd'hui, motif compris. Sans cela, on relit une courbe qui ne baisse
  pas et on conclut à un échec du traitement, alors que la dose n'a
  simplement pas été donnée.

« Refusé » cesse d'être un statut pour devenir un motif : deux états
suffisent — donné, non donné — et c'est le motif qui dit pourquoi. Un statut
de plus se serait ajouté à chaque cas particulier.

**v3.21 — 10 septembre 2026 — le poste dans la poche, et le réseau qui va avec**

Les infirmiers ouvriront leur poste depuis leur téléphone, sur le Wi-Fi du
service. Ce n'est pas un réglage : c'est ce qui décide de la forme de l'écran
et de la sécurité du dossier, et les deux changent ensemble.

*L'écran infirmier sur un téléphone.* Mesuré avant de corriger, à 390 px :
**86 cibles sous 40 pixels** et trois lignes par médicament. La disposition en
trois colonnes — case, produit, bouton — se dépliait sous 640 px : une
pancarte de trente prises devenait quatre-vingt-dix lignes à faire défiler au
pouce, avec des cases de seize pixels qu'on rate une fois sur trois.

Une prise tient désormais sur **une ligne** : un bouton pleine largeur qu'on
touche, dont le libellé porte l'état — « Donné — Tienam 1 g » se lit en plein
soleil et par quelqu'un qui distingue mal le rouge du gris. Le cas rare — non
donné, refusé — descend dans un volet replié sous chaque heure, au lieu
d'occuper une place fixe sur toutes les lignes. Traitements et surveillance ne
s'affichent plus côte à côte mais l'un ou l'autre : empilés sur un téléphone,
il aurait fallu faire défiler trente traitements pour atteindre la case de la
température. Après : **0 cible sous 40 px**.

Deux détails qui n'en sont pas. Les champs de saisie passent à 16 px, sinon
iOS zoome de lui-même à chaque case touchée et la page reste zoomée. Et les
constantes se remplissent **rangée par rangée** : deux colonnes remplies
verticalement, une fois empilées sur un téléphone, donnaient « FC, PA diast.,
FR, Glasgow, Dextro, PA syst. » — les deux pressions séparées par quatre
champs, c'est-à-dire une inversion par garde. L'ordre du catalogue les met
maintenant côte à côte, et un test le vérifie.

*Le réseau.* Le logiciel n'écoutait que la boucle locale, et c'était la seule
chose qui protégeait le dossier. Il écoute désormais l'adresse donnée par
`REA_HOTE` — et **dès que cette adresse n'est plus locale, le code d'accès
devient obligatoire sur tous les comptes**. Ce n'est plus un commentaire dans
un fichier de configuration, c'est une conséquence calculée (`AUTH_EXIGEE`)
que deux tests vérifient sur les deux branches. Un compte sans code se voit
refuser l'entrée, et l'écran d'ouverture dit pourquoi.

Deux serrures de plus, parce que l'ouverture au réseau les rend nécessaires :
**blocage après cinq essais ratés** pendant dix minutes — mesuré, un essai
coûte 47 ms, donc un code à quatre chiffres tombait en huit minutes d'essais
automatiques, et depuis le Wi-Fi c'est n'importe quel téléphone du couloir qui
peut les enchaîner — et **six caractères minimum** quand l'authentification
est exigée, les codes les plus évidents refusés.

*Le médecin voit qui soigne son patient.* L'écran Prescrit affiche, sous la
date, l'infirmier de la vacation en cours et son numéro, cliquable. L'ancienne
façon de le savoir était de faire le tour des chambres. L'information existait
déjà — l'infirmier la crée en prenant son poste — elle manquait à l'endroit où
l'on prescrit.

*Un écran qui tombait pour un référentiel qui change.* Trouvé en vérifiant le
reste : un bilan enregistré sous le code `gaz_du_sang`, code disparu depuis du
référentiel des examens, rendait **tout l'écran Prescrit inaccessible** pour
ce patient — Streamlit refuse une valeur par défaut absente des options, et
l'exception emporte l'écran entier. Le dossier était intact ; on ne pouvait
plus prescrire.

La correction est générale et non ponctuelle, parce qu'un référentiel *va*
changer : `champs.index_ou_zero` et `champs.valeurs_connues` ignorent ce qui
a disparu, `champs.valeurs_oubliees` le dit à l'écran plutôt que de le taire —
une case qui se décoche toute seule entre deux ouvertures est pire qu'un
message qui explique pourquoi. Quatre endroits corrigés.

**v3.20 — 10 septembre 2026 — des comptes, des rôles, et le travail infirmier**

Le logiciel avait un sélecteur d'ouverture qui ne servait qu'à signer les
écritures : tout le monde saisissait tout. Le service s'organisant, trois
choses arrivent ensemble — les comptes, l'écran de l'infirmier, celui du
surveillant.

*Les rôles.* Administrateur, senior, résident, interne, surveillant,
infirmier. Leurs droits sont dans `referentiels/roles.json`, pas dans le
code : déplacer un droit d'un rôle à l'autre est une décision de service.
Le senior signe les protocoles, le surveillant change tout **sauf** les
protocoles, l'infirmier voit le prescrit sans le modifier. L'écran d'accueil
suit le rôle : un infirmier ouvre son poste, un surveillant sa supervision.

**Ce qu'il faut savoir, et que le logiciel dit à l'écran plutôt que de le
taire : un rôle organise l'application, il ne la protège pas.** Tant qu'un
compte n'a pas de code d'accès, son nom reste sélectionnable par n'importe
qui, et son rôle avec. La serrure, c'est le code — facultatif compte par
compte, pour qu'un service qui démarre ne se bloque pas un matin de garde,
et exigé dès qu'il est posé. Il n'est jamais gardé en clair : empreinte
PBKDF2 salée, parce qu'une base copiée sur une clé rendrait sinon tous les
codes du service.

Un compte ne se supprime pas, il se **désactive** : l'effacer rendrait
anonymes des années de prescriptions. Et l'on refuse de retirer le dernier
compte capable de gérer les comptes — on ne se ferme pas la porte de
l'extérieur.

*L'écran de l'infirmier.* Trois vacations : 7 h – 13 h, 13 h – 19 h,
19 h – 7 h. L'infirmier choisit ses malades en prenant son poste, et voit
**ce qu'il va donner sur ces heures-là** — pas la pancarte des vingt-quatre
heures où il faudrait retrouver ses prises. Une case à cocher par prise, un
« non donné » avec son motif, et la surveillance horaire du verso de la
feuille — FC, PA, T°, SpO₂, Glasgow, diurèse — saisie heure par heure et
relue en tableau.

Deux points où le calcul naïf se trompe, et qu'un test protège chacun. La
vacation de nuit **franchit minuit** : `debut <= heure < fin` la rendrait
vide, et l'équipe de nuit ouvrirait un poste sans rien à donner. Et elle
reste **datée du jour de prise de poste** : à 2 h du matin le 10, l'équipe
de nuit est celle entrée à 19 h le 9 — sinon l'écran se vide au milieu de la
garde.

Ce qui coule en continu apparaît **une fois**, à l'ouverture du poste : une
seringue qu'on ne touche pas ne mérite pas douze cases à cocher. Les
conditionnels sont à part — ils se connaissent, ils ne se préparent pas.

Une prise non donnée **se note**, elle ne s'omet pas. Une case vide dit
« pas encore », une ligne « non donné » dit « décidé, à telle heure, et
voici pourquoi ». Les confondre, c'est perdre la seule trace d'un traitement
volontairement sauté — exactement ce qu'on cherche en relisant une nuit qui
s'est mal passée.

*L'écran du surveillant.* Trois questions, aucune ne demande de chercher :
qui s'occupe de qui, vacation par vacation ; ce qu'il faut commander,
patient par patient ; et surtout **ce qui a changé** dans les prescriptions,
en phrases — « Ajout de Tienam 1 g x3/j pendant 7 jours — M. X, matricule
123456, lit 3 ». Aujourd'hui le surveillant relit chaque pancarte pour
repérer les nouveautés de la garde ; il en manque, et un antibiotique
commencé à 4 h du matin n'est commandé qu'à midi. Les arrêts y figurent
autant que les ajouts : un antibiotique arrêté est une commande à ne pas
passer.

**v3.19 — 9 septembre 2026 — croiser ses données, pas six variables prévues ; le total des pertes**

*Les exemples étaient des exemples.* « Mortalité et E/e' », « mortalité et
PaO₂/FiO₂ » illustraient une idée — pouvoir se servir de ce que le dossier
contient — et non un catalogue à implémenter. Les facteurs croisables ne sont
donc plus une liste écrite dans le code : ils sont **dérivés des données**.

* les champs du séjour — provenance, type d'admission, mécanisme, Glasgow
  d'arrivée, mode de sortie, statut J28, poids, taille, IMC ;
* **tous** les analytes, y compris ceux que le service a ajoutés lui-même,
  chacun en quatre lectures : première valeur, la plus basse, la plus haute,
  dernière ;
* **tous** les champs des gaz du sang — pH, PaO₂, PaCO₂, HCO₃⁻, lactates,
  FiO₂, PEP, Vt, SpO₂ ;
* **toutes** les mesures des quatre plans effectivement saisies — FC, PA,
  RASS, Glasgow, diurèse, température… ;
* les produits réellement prescrits (exposition *et* durée), les dispositifs
  réellement posés (exposition *et* durée), les germes réellement isolés, les
  antécédents réellement saisis.

Sur la base de démonstration, un seul patient : **227 facteurs en 13
familles**. Une donnée nouvelle dans le dossier devient un facteur sans que
personne touche au code. Les résultats s'élargissent de la même façon :
mortalité en réanimation et à J28, durée de séjour, de ventilation, jours sans
ventilation, survenue d'une infection nosocomiale, réadmission.

Deux règles de lecture, tenues par des tests. Un séjour dont le facteur n'est
pas renseigné reste hors du tableau — sauf pour « a reçu / a eu / a isolé »,
où l'absence de ligne *est* un non, et dire « inconnu » viderait le croisement
de sa moitié utile. Une colonne booléenne se lit « Oui / Non » : « traumatique
= 1 » n'apprend rien à personne dans un tableau. Et un patient perdu de vue à
J28 n'est pas un survivant.

*Le total des pertes.* Devant un redon qui donne, la question est « combien
a-t-il perdu ? » — elle demandait d'additionner de tête diurèse, drains et
pertes insensibles. Le bilan affiche maintenant **entrées − total pertes** en
grand, le détail en dessous, et chaque drain nommé avant son total : « drain
thoracique 320 + redon 180 = 500 mL ». Deux redons à 90 et 410 ne se lisent
pas comme deux à 250, et c'est le genre de chiffre qui fait rappeler le
chirurgien. La feuille imprimée gagne une ligne « Total des pertes (ml) » sous
les drains, et le texte généré porte le total lui aussi.

**v3.18 — 9 septembre 2026 — l'évolution se documente après coup, une posologie dans les protocoles, décrocher c'est ne plus être fébrile**

*Le bilan des 24 h se calculait sur une journée qui n'avait que deux heures.*
L'écran Évolution s'ouvrait sur aujourd'hui ; l'intégration exacte des vitesses
(v3.17) additionnait alors la fenêtre entière — 8 h → 8 h le lendemain —
d'une journée à peine commencée. Le chiffre n'était ni celui d'aujourd'hui ni
celui d'hier, dans la case qui décide d'une déplétion ou d'un remplissage.

Une évolution se documente **après coup**, et c'est vrai de tout ce qui est
« /24 h » : diurèse, drains, pertes insensibles se relèvent sur une journée
révolue. L'écran s'ouvre donc sur la **dernière journée close** — le 8 quand
on est le 9 au matin, puisque la journée du 8 s'est terminée à 8 h. Sur une
journée en cours, le bilan ne s'affiche pas et dit pourquoi, en distinguant
deux situations qui n'ont rien à voir : « journée en cours, le bilan se
calcule dans 17 h » n'est pas « il manque la diurèse ».

Trois fonctions du domaine portent la notion : `jour_de_service`,
`dernier_jour_clos`, `journee_close`.

*Un protocole signé a le droit de porter une posologie* (décision du service).
Le §3.1 ne bouge pas — *le logiciel* ne calcule ni ne propose de dose — mais
ce qui arrive dans la ligne n'est pas un calcul : c'est le texte qu'un senior
a écrit et signé. Un protocole de correction de kaliémie sans dose ne sert à
rien : la dose *est* le protocole. L'éditeur gagne donc les colonnes dose,
unité et vitesse ; un champ laissé vide reste vide, et une dose illisible
(« selon kaliémie ») devient absente plutôt que zéro — un zéro dans une
prescription se lit comme une décision.

*Apyrétique, subfébrile, fébrile.* « Fébrile » n'est pas « a de la
température » : en réanimation on distingue trois états, et la différence
décide d'une conduite. Les seuils sont dans `referentiels/temperature.json`
(apyrétique en dessous de 38 ; subfébrile de 38 à 38,5 inclus ; fébrile
au-dessus de 38,5 — arrêtés par le service le 10 septembre 2026), le domaine dans
`domaine/temperature.py`, et la catégorie s'affiche à côté de la température
dans l'écran Visite — « 38,4 °C » demande un instant de conversion, « fébrile »
se lit d'un coup d'œil.

*Le délai d'apyrexie.* « À partir de combien de jours un patient décroche sous
telle molécule ? » — décrocher, c'est ne plus être fébrile. Pour chaque
traitement commencé **chez un patient fébrile**, le nombre de jours jusqu'au
premier jour apyrétique, le jour de début comptant pour J1.

Trois refus, un test chacun, parce que chacun ferait paraître une molécule
plus efficace qu'elle n'est :

* un patient **subfébrile** n'a pas décroché ;
* une température **non mesurée** n'est jamais lue comme une apyrexie — sinon
  tout patient qu'on cesse de mesurer décroche ;
* ceux qui **ne décrochent jamais** sont comptés et affichés à côté de la
  médiane. Ne rapporter que ceux qui ont décroché est le piège classique de ce
  calcul, et il fait paraître efficace une molécule sous laquelle personne ne
  décroche.

**v3.17 — 9 septembre 2026 — les entrées comptées pour de vrai, l'administration lisible, les protocoles déclenchés, les croisements**

*Le bilan hydrique comptait les seringues à leur vitesse de départ.* Une
noradrénaline montée à 30 cc/h dans la nuit puis redescendue à 8 le matin
valait sa vitesse d'ouverture pendant 24 h. Le volume est maintenant intégré
**réglage par réglage**, à la minute, sur la journée de service (8 h → 8 h) :
25 cc/h passés à 10 à midi valent 300 mL, pas 600. La pancarte imprimée et le
plan hémodynamique lisent le même calcul — deux chiffres différents pour la
même journée, et plus personne ne sait lequel croire.

Reste une imprécision, nommée plutôt que masquée : une ligne porte une date de
début, pas une heure. Le premier jour d'une seringue posée à 14 h est donc
compté depuis 8 h. Y remédier demande une heure de pose sur la ligne — décision
du service, pas invention du logiciel.

*L'écran Administration.* Il présentait quinze noms de fichiers horodatés à la
seconde et une liste déroulante de toutes les sauvegardes. Personne ne choisit
une base sur un horodatage : ce qu'on veut, c'est emporter le service sur une
clé, ou remettre celle d'hier soir. Quatre gestes nommés par ce qu'ils font,
chacun expliqué sous son bouton : **exporter** (une copie complète à
télécharger), **importer** (installer une base venue d'ailleurs),
**sauvegarder**, **revenir à la dernière sauvegarde**. La liste complète
descend sous un dépliant.

Un fichier importé est **inspecté avant d'être installé** : est-ce du SQLite,
porte-t-il les tables du logiciel, et combien de patients contient-il. Ce
dernier chiffre est affiché à côté de celui de la base actuelle — c'est lui qui
arrête quelqu'un qui s'est trompé de fichier.

*Les protocoles se déclenchent enfin sur autre chose que l'admission.* Motif
d'entrée et région traumatique décrivent le patient qui arrive ; la plupart des
protocoles d'un service répondent pourtant à ce qui *survient*. Un troisième
déclencheur attache un protocole au **code d'une règle d'aide** : quand la
règle « hypokaliémie » se déclenche, le protocole de correction s'ouvre sous le
rappel qui vient de le déclencher, dans l'écran Évolution.

Les quatre règles de sécurité du §4.5 ne bougent pas : seul un protocole
**signé** est proposé, il est proposé et non appliqué, les lignes posées sont
des lignes ordinaires, et elles partent **sans dose** (§3.1). Le dépôt livre
`protocoles/correction_hypokaliemie.json` en **brouillon** : il montre le
mécanisme, il ne prescrit rien tant qu'un senior ne l'a pas relu et signé.

*Croisements (bloc 19).* Les indicateurs répondent à « comment va le
service ? ». Il manquait la famille de questions qu'on se pose en staff : la
mortalité change-t-elle avec le PaO₂/FiO₂ ? avec le E/e' ? combien de temps
reste-t-on ventilé sous telle molécule ? On choisit un résultat et un facteur,
la cohorte est découpée en tranches, le résultat s'affiche tranche par tranche
avec son effectif.

Le catalogue de biologie étant ouvert, **un analyte ajouté par le service
devient un facteur sans reprogrammer** : « mortalité selon le E/e' » ne demande
que d'avoir saisi des E/e' dans l'écran Bilans.

Trois refus tiennent ce module :

* une tranche de moins de cinq séjours garde son effectif mais n'affiche pas de
  pourcentage — dans douze lits, « 100 % de mortalité » sur deux patients est
  le cas le plus fréquent, et ce n'est pas un résultat ;
* un séjour dont le facteur n'est pas renseigné n'entre dans aucune tranche, et
  ce nombre est affiché : une donnée manquante ne devient jamais un « non » ;
* aucun test statistique n'est calculé, délibérément. Un p affiché à côté d'un
  tableau descriptif univarié, monocentrique et non ajusté serait lu comme une
  preuve. Chaque tableau porte la phrase : il fabrique une hypothèse, il ne
  démontre rien.

**v3.16 — 9 septembre 2026 — le bouton Copier ne suppose plus la dernière version de Streamlit**

L'écran Évolution plantait sur le poste du service : `AttributeError: module
'streamlit' has no attribute 'iframe'`. Le bouton Copier venait d'être écrit
avec `st.iframe`, parce que la version de développement signalait
`st.components.v1.html` comme déprécié. Suivre l'avertissement était juste sur
la machine qui le donnait, et faux sur celle qui fait tourner le service : elle
est plus ancienne, `st.iframe` n'y existe pas encore.

Le logiciel prend maintenant celui des deux noms qui est là, le récent d'abord.
Le poste du service n'est pas mis à jour d'un clic — il est hors ligne, et on
ne touche pas à son environnement pendant qu'il porte des patients.

Au passage, `requirements.txt` annonçait `streamlit>=1.36` alors que deux écrans
appellent `st.segmented_control`, arrivé en 1.40 : un plancher faux ne se voit
qu'à l'installation sur un poste neuf, écran blanc à l'appui. Il passe à 1.40,
et un test le compare aux appels réellement utilisés.

Vérifié en relançant l'application avec `st.iframe` retiré de Streamlit : la
page se rend, et le bouton copie.

**v3.15 — 9 septembre 2026 — l'Évolution rend sa moitié droite, les avis sortent des plans**

*Le texte à recopier s'en va.* Il tenait la moitié droite de l'écran — 640
pixels de haut — pour n'être lu par personne : on le relit dans le DMI après
l'avoir collé, pas dans le logiciel qui vient de l'écrire. Pendant ce temps les
quatre plans se saisissaient dans ce qu'il restait. Il ne reste qu'un bouton
**Copier le compte rendu du jour**, en bas de page, et la largeur entière
revient à la saisie.

Deux chemins vers le presse-papiers, parce qu'un seul ne suffit pas :
`navigator.clipboard` quand le navigateur l'accorde, `execCommand('copy')`
sinon — l'iframe d'un composant n'a pas toujours la permission
`clipboard-write`. Si les deux échouent, le bouton le dit ; et il ne s'affiche
pas du tout tant que la journée est vide. Un bouton qui copie le vide en
silence ne se remarque qu'au moment où on colle, dans le DMI, c'est-à-dire trop
tard.

*Les avis spécialisés quittent le plan infectieux.* Ils y avaient été rangés
parce que c'est là qu'on décide de rappeler un chirurgien. À l'usage c'était
faux : on demande un avis de cardiologie sur un trouble du rythme, de
néphrologie sur une épuration — la moitié des avis n'a rien d'infectieux. Ils
forment leur propre section, sous les quatre plans : la liste chronologique à
gauche, la saisie à droite (demande du service, 9 septembre).

**v3.14 — 9 septembre 2026 — un seul écran construit à la fois**

L'application était lente sur une base presque vide : neuf secondes pour ouvrir
une fiche, près d'une seconde pour le moindre clic dans le prescrit. Une base
vide qui rame, c'est le signe que ce n'est pas la base — et la mesure l'a
confirmé : les 110 requêtes SQL d'une exécution complète tiennent en **20 ms**,
et les référentiels sont déjà en cache.

Le coût était ailleurs. `st.tabs` n'est pas un aiguillage : Streamlit exécute le
corps des sept onglets à chaque exécution du script, qu'on les regarde ou non,
et garde tout dans la page. Une fiche chargée, c'était **2 785 widgets** et
**5 404 éléments de page** reconstruits à chaque clic — y compris les six écrans
qu'on ne regardait pas.

Les onglets deviennent un sélecteur (`st.segmented_control`) et un seul écran
est construit :

| | avant | après |
|---|---|---|
| ouverture d'une fiche | 9 300 ms | **121 ms** |
| widgets | 2 785 | **342** |
| éléments de page | 5 404 | **754** |
| clic dans le prescrit | 700–1 100 ms | 65–550 ms |

La contrepartie est assumée : changer d'écran coûte désormais un aller-retour au
serveur (190 à 740 ms, les Bilans étant le plus lourd) au lieu d'être instantané.
On change d'écran quelques fois par patient ; on clique dedans des dizaines de
fois. L'échange est largement favorable.

*Effet de bord réglé au passage :* les panneaux d'onglets restant tous dans la
page, une sonde de test pouvait lire un champ appartenant à un autre écran —
c'est ce qui avait fait croire à un faux « FR affichée dans tous les modes
ventilatoires ». Un seul écran présent, la page dit désormais ce qu'elle montre.

**v3.13 — 9 septembre 2026 — un mode Visite, et la pancarte enfin lisible**

Le reste de l'application est fait pour être lu assis, à cinquante centimètres,
en train de saisir. La visite, c'est l'inverse : on ne tape rien, on lit un
portable posé sur le chariot, debout, et ce qu'on cherche est toujours la même
chose — quel traitement, à quel jour, à quelle dose, et comment la biologie a
bougé depuis hier. D'où un onglet **Visite**, en tête parce que c'est celui
qu'on ouvre au pied du lit.

À gauche, les traitements par voie. À droite, l'état du jour (constantes, bilan
hydrique, dernier gaz du sang — celui d'hier s'il n'y en a pas eu aujourd'hui,
et daté pour qu'on le sache), les abords, la biologie avec sa valeur
précédente, le bilan infectieux avec les avis, et les plans de la journée.

**Cet écran n'écrit rien**, et c'est vérifié par un test qui lit son code :
aucun appel de service dont le nom dit qu'il écrit. À la visite on lit et on
discute, on ne prescrit pas d'une main en tenant un chariot de l'autre — un
bouton d'arrêt de traitement à portée de manche est un traitement arrêté par
erreur. Corollaire : `services.evolution.journee()` lit une journée sans la
créer. `obtenir_ou_creer` semait une ligne vide pour chaque jour que quelqu'un
avait seulement regardé, et « cette journée existe » cessait de vouloir dire
« quelqu'un l'a remplie ».

*La ligne de pancarte.* Elle était en 0,82 rem — la taille d'une légende — pour
la ligne la plus lue du logiciel. Elle passe à 0,95 rem, et surtout se range en
trois colonnes : le compteur J, le produit, la dose. L'œil descend la colonne
des compteurs pour trouver un dernier jour d'antibiotique, celle des doses pour
vérifier une posologie ; une phrase d'un seul tenant l'oblige à relire chaque
ligne en entier.

Le découpage est fait par le domaine (`prescription.parties_ligne`) et non à
l'écran. La première version retranchait la dose de la phrase déjà composée :
ça marche jusqu'au jour où un horaire se glisse derrière elle — et alors la
dose s'affiche deux fois, ce qui est exactement ce qui s'est produit.

Les vitesses horaires d'une seringue passent sous la ligne, en petit : en
ligne, elles repoussaient la dose et cassaient l'alignement de la colonne qu'on
descend pour la vérifier.

**v3.12 — 9 septembre 2026 — les bilans : modes ventilatoires, ordre, catalogue ouvert**

*Chaque mode ventilatoire a ses paramètres.* Tous les champs étaient proposés
quel que soit le mode : une PEP sous air ambiant, une AI en VAC. Des cases qui
n'existent pas cliniquement, et qu'un interne de garde finit par remplir avec le
paramètre d'à côté — après quoi la valeur est en base, indiscernable d'une
mesure. Chaque mode déclare maintenant ce qui a un sens pour lui, dans
`referentiels/modes_ventilatoires.json` :

| Mode | Paramètres |
|---|---|
| Air ambiant | aucun |
| Lunettes, masque | débit |
| Optiflow *(nouveau)* | débit, FiO₂ |
| VS-AI | FiO₂, PEP, AI, Vt |
| VAC | FiO₂, PEP, FR, Vt |
| VACI *(nouveau)* | FiO₂, PEP, FR, Vt, AI |

Le gaz du sang lui-même — pH, PaO₂, PaCO₂, HCO₃⁻, lactates, SaO₂ — ne dépend
d'aucun mode : c'est une seringue de sang artériel, qu'on soit ventilé ou non.

Les modes sont désormais des **codes** et non des libellés. Un libellé se
réécrit, un code non, et c'est le code qui décide des paramètres. Les gaz du
sang écrits par la version précédente sont traduits à l'ouverture de la base.

*Le bicarbonate quitte l'ionogramme.* Il figure déjà avec le gaz du sang : deux
lignes pour le même chiffre, c'était deux cinétiques à lire pour un paramètre.

*L'ordre des bilans* est celui de la visite : gaz et ventilation, ionogramme,
fonction rénale, métabolique, NFS et hémostase, puis l'inflammation — la CRP et
la PCT se lisent avec le bilan infectieux, qui n'est pas demandé tous les jours.
L'observation générée suit maintenant cet ordre au lieu d'une liste recopiée à
côté, qui divergeait de l'écran à la première réorganisation.

*Un catalogue qu'on peut compléter.* Le catalogue de biologie est du code : y
ajouter la troponine demandait une nouvelle version du logiciel. Un service qui
se met à doser quelque chose ne peut pas attendre ça — il le noterait dans un
commentaire libre, où le résultat ne se compare pas d'un jour à l'autre, ne
trace aucune courbe et ne sort dans aucune statistique. La table
`analyte_local` porte les analytes du service, avec leur unité et leurs bornes ;
ils rejoignent les bilans non systématiques et portent leur libellé partout,
saisie comme observation générée.

Ils sont dans la **base** et non dans `referentiels/` : ce sont des données du
service, pas du logiciel. Ils sont donc sauvegardés et restaurés avec elle,
alors qu'un fichier de référentiel réécrit à l'exécution cesserait d'être
versionné. Retirer un analyte de la liste ne touche pas aux valeurs déjà
mesurées : ce qui a été mesuré a été mesuré.

**v3.11 — 9 septembre 2026 — les colonnes de biologie, pour de bon**

Deux défauts restaient, visibles dès la première feuille imprimée.

*Une colonne vide au milieu d'un jour.* Le nombre de colonnes d'un jour était
compté sur **tous** ses prélèvements, bilans et gaz du sang confondus, alors que
chaque tableau ne remplit que les siens. Un jour à deux bilans et deux gaz
recevait quatre colonnes dans le récapitulatif de chimie, qui n'en remplissait
que deux : la troisième restait vide au milieu du jour, pendant qu'un autre
jour, faute de place, n'était pas montré du tout. Chaque tableau compte
désormais sa propre source, et a son propre en-tête de jours (`days` pour la
chimie, `daysGaz` pour les gaz).

*Un bloc sans date entre deux jours.* Les colonnes sans emploi — séjour trop
court pour remplir les huit — formaient un groupe anonyme entre le dernier jour
passé et le jour en cours, ce qui se lisait comme un jour manquant. Elles
reviennent maintenant au jour en cours, seul à avoir de vraies raisons d'avoir
des cases libres : la garde y écrit ses bilans de la nuit. Il n'y a plus aucune
colonne anonyme sur la feuille, et toute colonne appartient à un jour daté.

**v3.10 — 8 septembre 2026 — actes de réanimation, avis spécialisés, Glasgow d'arrivée**

*Correction de la v3.9.* Le tableau de biologie se remplit de gauche à droite.
Les colonnes libres — quand le séjour est trop court pour remplir les huit — se
placent **après** les jours datés, jamais avant : une zone vide en tête donnait
à croire qu'un jour manquait.

*Glasgow initial.* Case fixe sur la feuille, sous le transport, parce que c'est
le même moment : ce que valait le patient en arrivant. C'est la seule valeur
neurologique qu'on ne peut plus reconstituer — à J3 sous midazolam, personne ne
sait plus s'il est arrivé à 15 ou à 6 — et c'est un facteur pronostique majeur
du traumatisme crânien. Rien n'est imprimé quand elle n'a pas été saisie : une
ligne « Glasgow initial : » vide se lirait comme un 3.

*Antidater un acte.* La date et l'heure d'une exploration se choisissent, comme
pour un bilan ou un traitement. C'était une chaîne de caractères pré-remplie à
« maintenant » : modifiable en théorie, mais il fallait réécrire un horodatage
ISO à la main, et personne ne le faisait. Un acte fait à 3 h et saisi à la
relève appartient à la nuit, pas au jour de la frappe.

*Transfusion, radiographie, ALR.* Trois actes qui n'existaient pas. La
transfusion note son produit (liste fermée : un produit sanguin écrit à la main
ne se retrouve pas dans une revue de morbidité), son nombre de poches, son heure
et sa complication éventuelle. La radiographie thoracique note son syndrome —
alvéolaire, interstitiel, opacité, clarté — et sa localisation. L'anesthésie
locorégionale se sépare en deux : un bloc en une fois est un **acte** avec sa
dose ; une péridurale ou un cathéter périnerveux sont des **dispositifs** qui
coulent, et l'anesthésique local apparaît désormais dans le bloc P.S.E. de la
feuille avec son débit.

Ce dernier point a demandé de généraliser : la sédation était le seul dispositif
reporté au bloc P.S.E., par une fonction qui ne connaissait qu'elle. C'est le
fichier des types qui le déclare maintenant (`pse`), et une péridurale y arrive
sans qu'on rouvre le rendu. Le site n'y est pas répété — il est déjà sur le
bandeau des abords, et l'écrire deux fois cassait la grille des seringues.

*Avis spécialisés.* Nouvelle table, saisie sous le plan infectieux, report à
gauche de la feuille : « Avis CCVT (09/09) : Rsdt X : Pas d'indication
chirurgicale ». Un avis de neurochirurgie ne se résume pas — « refaire la TDM à
48 h » est une consigne datée et signée, et c'est sur elle qu'on décide trois
jours plus tard. Écrits dans le texte libre du plan infectieux, ces avis
disparaissaient à sa première réécriture. Un avis n'annule jamais le précédent,
même de la même spécialité : c'est la suite des avis qui raconte l'évolution
d'une décision chirurgicale, et le second ne se comprend souvent qu'à la lumière
du premier. Le grade est imprimé parce qu'un avis de senior et un avis de
résident n'engagent pas la même chose.

*Garde-fou R2 renforcé.* Le test qui protège `listes.py` comptait ses lignes :
il refusait autant une liste recopiée dans le code qu'une fonction d'accès
légitime, et quiconque en ajoutait une était tenté de relever le seuil — c'est
comme ça qu'un garde-fou perd ses dents. Il vérifie maintenant la règle
elle-même, par l'AST : aucune donnée écrite en dur au niveau du module.

**v3.9 — 8 septembre 2026 — six retours du service sur le prescrit et la feuille**

*Additifs.* Le champ était libre : « KCl 2 », « 2 amp KCl » et « +2K »
désignaient la même ampoule sans jamais se relire d'une feuille à l'autre.
Chaque additif se coche maintenant dans une liste
(`referentiels/additifs_perfusion.json`) avec son nombre d'ampoules, et
s'imprime « + (1 NaCl + 2 KCl) ». La quantité reste un nombre d'ampoules et
jamais des millimoles : c'est l'unité dans laquelle l'infirmière prépare, et
convertir ferait écrire une chose et préparer l'autre. Le texte se relit
(`analyser_additifs`) pour repeupler le formulaire — sans ce chemin de retour,
un additif oublié à la ressaisie disparaîtrait de la prescription sans que
personne ne l'ait décidé ; les anciennes écritures libres restent lisibles.

Au passage : les additifs n'étaient imprimés **nulle part** sur la feuille.
L'infirmière préparait d'après la pancarte, et la pancarte ne les disait pas.
Ils suivent maintenant leur produit sur la même ligne.

*Produits d'entrée.* Kabiven, SmofKabiven, Fresubin, G5 %, sérum salé
isotonique, Ringer Lactate… au catalogue (`referentiels/produits_entrees.json`),
qui sait aussi si le produit est une perfusion ou une nutrition et pré-remplit
la case. La liste reste ouverte : un produit absent s'écrit à la main.

*Colonnes de biologie.* Chaque jour prenait quatre colonnes qu'il ait eu un
bilan ou quatre : deux jours suffisaient à remplir la page, et un patient
prélevé une fois par jour perdait six colonnes sur huit en cases vides. Les
douze colonnes ne bougent pas — la page est imprimée — mais les huit qui ne
sont pas au jour en cours vont désormais aux jours passés **à proportion de
leurs prélèvements réels**, en remontant jusqu'à les remplir. Un jour sans
prélèvement ne prend aucune colonne. La feuille montre une semaine de cinétique
au lieu de deux jours, et une cinétique de créatinine sur une semaine, c'est ce
qui fait voir une insuffisance rénale qui s'installe. Conséquence technique :
les filets ne pouvaient plus être un dégradé de fond régulier — ce sont les
cases qui les portent.

*Créatinine.* Suivie de sa clairance de Cockcroft-Gault entre parenthèses —
« 184 (41) ». Une créatinine à 184 ne veut pas dire la même chose chez un homme
de 40 ans de 90 kg et chez une femme de 80 ans de 45. Calculée, jamais saisie,
et rien affiché quand il manque le poids, l'âge ou le sexe. Elle reste une
grandeur physiologique : aucune adaptation de dose n'en est déduite (§3.1).

*Bilan infectieux.* Une ligne par type — CRP, PCT, ECBU, PDP, Hémocultures, PL
— chacune montrant la suite datée de ses résultats
(« 07/09 : 210 → 08/09 : 185 → 10/09 : 56 »). Le bloc listait les six derniers
résultats tous types confondus : deux hémocultures et une CRP suffisaient à
faire disparaître l'ECBU de la veille, et la cinétique d'une CRP ne se lisait
nulle part alors que c'est elle, plus que sa valeur du jour, qui dit si
l'antibiothérapie marche. Une ligne vide reste imprimée : « PL » sans rien en
face se lit « pas de ponction lombaire », ce qui est une information ; une ligne
absente ne se lit pas du tout. La colonne du prélèvement passe de 166 à 78 px,
la place gagnée va à la cinétique. La PCT était demandable sans être
saisissable — elle entre au catalogue d'analytes.

*CRP.* Retirée du récapitulatif de chimie : l'écrire aux deux endroits donnait
deux cinétiques à lire pour un seul paramètre.

**v3.8 — 8 septembre 2026 — un changement de dose n'est pas un nouveau traitement**

Lacune du §5.1, remontée par le service : la ligne de prescription portait à la
fois l'identité du traitement et sa posologie. Tienam 1 g × 3/j passé à
500 mg × 3/j à J4 laissait le choix entre modifier la ligne — et perdre la
posologie initiale — ou en ouvrir une seconde — et faire repartir le compteur à
J1, alors que l'antibiothérapie court depuis la première dose. La durée de
traitement rendue au comité des infections était fausse dans les deux cas.

Deux niveaux, décrits au §5.1 réécrit. L'**épisode** (`prescription_ligne`) :
produit, indication, date de début ; il porte le compteur J{n} et la durée.
La **version de posologie** (`prescription_posologie`) : dose, rythme,
dilution, vitesse, à partir de quel jour. Pas de date de fin — une version vaut
jusqu'à ce que la suivante commence, sinon deux façons de dire la même chose
finissent par se contredire.

Ce qui en découle et qui est vérifié : la pancarte d'un jour donné montre la
posologie de ce jour-là, une nouvelle dose ne s'applique pas rétroactivement,
réenregistrer la même dose ne crée pas de version, une correction saisie le jour
même remplace celle du jour, et le DOT se compte par épisode — compter les
versions doublerait la durée de tout patient dont la dose a été adaptée une
fois.

`modifier_ligne` refuse désormais les champs de posologie. C'est le point de la
fonction : écrire `{"dose": 500}` directement écraserait la dose initiale sans
laisser de trace, et la pancarte des jours passés se mettrait à afficher une
dose qui n'y a jamais été donnée. L'écran Prescrit a un panneau « Changer la
dose d'un traitement en cours », qui montre l'historique des versions avec leur
motif.

Une base existante se migre à l'ouverture : chaque ligne reçoit sa première
version, recopiée de la posologie d'introduction restée sur la ligne. Éprouvé
sur la base du patient de démonstration — trente-six épisodes, trente-six
versions, deux ouvertures sans rien dupliquer.

**PAM calculée, case supprimée.** (PAS + 2 × PAD) / 3, écrite `105/58 (74)` dans
le texte du plan hémodynamique. Trois cases dont une déductible des deux autres,
c'était une incohérence qui attendait son tour. Le SOFA continue de lire une
PAM : celle déjà enregistrée si elle existe — elle a pu être relevée sur un
cathéter artériel, ce que l'estimation au brassard ne remplace pas — et sinon
celle du calcul.

**v3.7 — 8 septembre 2026 — deux internes sur le même jour, et les deux répétitions avant le premier patient**

L'évolution quotidienne était le dernier écran enregistré en bloc : la visite
passe, un interne remplit le lit 3, un autre ouvre le même lit pour ajouter une
ligne, et le second enregistrement écrasait le premier sans que personne ne
voie jamais que quelque chose avait été perdu. C'est la seule catégorie de bug
qui détruit des données sans laisser de trace.

La colonne `version` posée en v3.6 servait à ça. À l'enregistrement, si la
version en base a changé depuis l'ouverture de l'écran, on refuse et on le dit.
Pas de fusion, pas de résolution de conflit : refuser, expliquer, et laisser
relire ce qui est en base. `db.ConflitDeVersion`, `Base.verifier_version()`,
`services.evolution.enregistrer_journee()` — mesures et textes dans une seule
transaction, derrière la vérification : refuser à moitié serait pire que tout.

Deux répétitions ont été faites, parce qu'un logiciel de service se juge sur ce
qu'il fait le jour où quelque chose tourne mal :

*Restaurer une sauvegarde pour de vrai.* Une sauvegarde jamais restaurée n'est
pas une sauvegarde. Sauvegarde écrite par le logiciel, fichier recopié dans un
autre dossier, application lancée sur cette copie : elle démarre, elle n'écoute
que sur 127.0.0.1, et le patient, ses trente-six lignes, ses drains et son bilan
hydrique sont tous là. Le bouton « Restaurer » de l'écran Administration a été
éprouvé de bout en bout : une saisie erronée commise après la sauvegarde
disparaît, le filet de sécurité est écrit avant, et le journal garde la trace de
la restauration.

*Imprimer une pancarte chargée à fond.* `outils/patient_demonstration.py` charge
un patient qui déborde volontairement — trente-six lignes pour trente
emplacements, allergies, cinq seringues avec changements de vitesse dans la
journée, antibiogramme, drains, bilans cochés pour demain. La feuille tient : le
débordement est annoncé en pied de page voie par voie, les vitesses de PSE
s'écrivent bien heure par heure (25 à 8 h, 18 à 12 h, 15 à 16 h, 8 à 22 h), et
rien n'est affirmé qui n'ait été mesuré.

Une surprise, trouvée là où ces répétitions servent à en trouver : les trois
emplacements de drain de la feuille s'appelaient « Redon 1 / 2 / 3 » quel que
soit le patient. Sur du papier rempli à la main toutes les heures, rien ne dit
lequel est le drain thoracique et lequel est le redon de l'abdomen — et deux
volumes intervertis, c'est une reprise chirurgicale décidée sur le chiffre de
l'autre drain. Les lignes portent maintenant le nom du drain réellement en
place ; les emplacements libres gardent un libellé générique, pour un drain posé
après l'impression. Les valeurs, elles, restent manuscrites : le volume relevé
dans l'évolution est celui des 24 h, pas celui de chaque heure.

Reste hors de portée d'ici : l'impression physique sur l'imprimante du service.
Le fichier est prêt ; le passage papier — A3, paysage, marges nulles, sans mise
à l'échelle — doit être fait sur place.

**v3.6 — 8 septembre 2026 — §2.4, contraintes d'architecture : audit et mise en conformité**

Le §2.4 entre dans la SPEC (état actuel, évolutions écartées, sept invariants,
interdits). Audit du code existant contre ses huit points, avant le premier
patient — c'est le dernier moment où le schéma est bon marché.

*Le plus grave, et le plus court à corriger.* Aucune adresse d'écoute n'était
configurée : Streamlit écoutait sur toutes les interfaces. Le bandeau de
démarrage annonçait lui-même « Network URL » et « External URL ». Sur le
réseau de l'hôpital, le dossier de tous les patients était lisible depuis
n'importe quelle machine, sans mot de passe. Le poste n'a pas de réseau
aujourd'hui, et c'est la seule raison pour laquelle rien n'est arrivé.
`config.HOTE = "127.0.0.1"`, repris par le lanceur et par la configuration
Streamlit ; un test vérifie que les deux ne divergent pas, un autre exige que
`AUTH_REQUISE` passe à True le jour où `HOTE` s'ouvrira.

*Schéma (points 1 et 2 de l'audit).* `version` manquait sur les 29 tables. Elle
est ajoutée aux 26 tables modifiables, part à 1 et s'incrémente à chaque
écriture, en SQL — personne ne la lit encore. `pin` est ajouté à
`utilisateur`, vide. Quinze tables gagnent au passage les `modifie_le` /
`modifie_par` qui leur manquaient. Quatre tables restent hors du dispositif,
chacune pour sa raison, écrite dans l'en-tête du schéma — dont
`pancarte_snapshot`, dont la colonne `version` désignait déjà le numéro
d'impression : l'incrémenter aurait renuméroté des feuilles déjà sorties de
l'imprimante. Une base existante se met à jour toute seule à l'ouverture,
sans perte : vérifié sur une base de quatre patients.

*Points déjà tenus.* Aucune suppression physique (point 3), trois états
explicites (point 4), calculs en fonctions pures et rendu qui ne calcule pas
(points 4 et 7) — ces deux derniers étaient déjà tenus par des tests.

*Point 6, partiellement.* Quatre requêtes SQL vivaient dans deux écrans ; elles
rejoignent les services. Le SQL reste réparti entre les quinze services plutôt
que réuni en un fichier : l'écart est décrit au §2.4 plutôt que corrigé dans
l'urgence, ce qui protège vraiment étant qu'aucun écran n'en contienne.

Ce qui est vérifiable est désormais tenu par des tests plutôt que par la
discipline : 178 nouvelles vérifications d'architecture.

**v3.5 — 8 septembre 2026 — le bilan hydrique se calcule tout seul**

Demande du service : quantifier les sorties dans le plan hémodynamique et en
tirer le bilan des 24 h, au lieu de le refaire de tête à chaque visite.

*Les sorties.* La diurèse était déjà là. S'y ajoute le recueil des drains, un
champ par drain effectivement en place — et rien du tout s'il n'y en a pas.
« Drainé » se déclare dans `types_dispositif.json` (clé `draine`) : drain
thoracique, drain abdominal, DVE, et le Redon, qui manquait au référentiel
alors que la feuille lui réserve trois lignes. La sonde urinaire ne le porte
pas : son volume, c'est la diurèse, et l'ajouter la compterait deux fois.

*Le calcul*, arrêté par le service :

    entrées − (diurèse + drains + pertes insensibles)

Pertes insensibles : 0,5 mL/kg/h × 24 h à 37 °C, majorées de 2 mL/kg/24 h par
degré au-dessus — ou d'un forfait par degré, au choix. Ces quatre nombres sont
dans `referentiels/bilan_hydrique.json`, pas dans le code : un senior peut les
revoir sans reprogrammer, et basculer du mode « par kilo » au mode « forfait »
tient en une ligne de fichier.

Le bilan s'affiche sous la carte hémodynamique, se recalcule pendant qu'on
tape, et rejoint le texte prêt à coller dans le DMI. Il ne s'affiche pas tant
qu'il manque la diurèse ou le poids : il dit alors ce qui manque. Un chiffre
inventé dans un bilan hydrique est pire que pas de chiffre du tout.

L'eau endogène (oxydation, ~300 mL/24 h) est nommée dans la demande mais
absente de l'équation qu'elle donne : elle n'est donc pas comptée, en attendant
que le service tranche. Le total des entrées reste celui du prescrit
(SPEC §5.6) : il ne suit pas encore les changements de vitesse de la journée,
et les boissons per os ne sont pas saisies.

Corrigé au passage : les valeurs relues d'un jour précédent s'affichaient
« 96,0 » et se réenregistraient avec leur zéro décimal.

*Le lien entre les deux écrans.* Les quatre types drainés se posent depuis
« Explorations et actes » comme n'importe quel dispositif, et apparaissent
aussitôt dans le recueil de l'évolution — le Redon compris, désormais. À la
pose, l'écran le dit : « son recueil des 24 h se relève dans l'évolution, plan
hémodynamique ». Sans cette phrase, on cherche sur l'écran des actes un champ
« volume » qui n'y est pas et n'a pas à y être : un drain se pose une fois,
son recueil se relève tous les jours.

Défaut corrigé du même coup : un drain posé aujourd'hui apparaissait dans
l'évolution des jours précédents, où il n'avait rien pu recueillir — le bilan
hydrique d'un jour passé changeait donc chaque fois qu'on posait un drain.

**v3.4 — 8 septembre 2026 — antidater la garde, et la vitesse heure par heure**

*Antidater ce qui a été fait pendant la garde.* C'était déjà possible en base
— le compteur de jours se calcule depuis `date_debut`, jamais depuis la date
de frappe — mais la saisie ne s'y prêtait pas. Le bilan se datait sur une
ligne à l'anglaise (« 2026-09-08T06:30 ») à corriger caractère par caractère :
elle laisse place à un jour et une heure séparés, et un bilan daté d'hier
l'annonce. La date de début d'un traitement sort du formulaire, où elle ne
pouvait rien dire, et affiche tout de suite le compteur qu'elle produira :
« Introduit le 07/09 — la pancarte du 08/09 l'affichera J2 ». Trois tests
tiennent le calcul, un quatrième vérifie qu'un bilan antidaté tombe bien dans
la colonne de sa nuit.

*La vitesse d'une seringue, heure par heure.* Une vitesse n'est pas une donnée
figée : on part à 25 cc/h et on descend à 15 à 16 h. La feuille n'imprimait
que la vitesse de départ, dans la colonne dose — la suite se réécrivait à la
main tous les jours, alors même que la maquette du service annonce déjà
« débit ml/h dans les cases ». Une table `vitesse_reglage` porte les réglages
horodatés, et la grille horaire les écrit : la vitesse en vigueur à
l'ouverture de la journée, puis chaque changement à son heure.

La journée du service va de 8 h à 8 h (`config.HEURE_DEBUT_JOURNEE`), comme la
grille imprimée : un réglage noté à 2 h appartient à la nuit de cette
feuille-là, pas à la suivante. Deux choses coulent et se règlent pareil — une
ligne prescrite (noradrénaline) et un dispositif (la sédation, posée dans
l'écran des actes) ; `cible` dit seulement d'où vient ce qui coule.

Deux défauts trouvés en chemin, et corrigés : la vitesse courante d'un
dispositif (celle de sa carte et de la pastille du bandeau) servait aussi de
vitesse d'origine — descendre une sédation aujourd'hui aurait réécrit les
feuilles des jours passés à la nouvelle valeur ; la pose ouvre donc désormais
l'historique des vitesses, et c'est la dernière vitesse *dans le temps* qui
devient la courante, pas la dernière saisie. Et ces vitesses s'affichaient
« 4.0 cc/h » : un zéro décimal de plus sur une pompe n'apprend rien à personne.

Reste en l'état, faute d'avoir été demandé : le bilan des entrées sur 24 h
compte toujours `vitesse × 24` (SPEC §5.6), c'est-à-dire la vitesse de départ,
sans tenir compte des changements de la journée.

**v3.3 — 8 septembre 2026 — quatorze retours du service, écran par écran**

*Identité.* « Modifier l'admission » descend sous « Transférer vers un autre
lit », dans un tiroir de même forme : deux gestes occasionnels, au même
endroit, plutôt qu'un bouton en permanence dans la rangée de tête. Les trois
blocs de tête (identité, motif, antécédents) reprennent la largeur libérée et
passent en grand — ce sont les seules lignes de l'écran qu'on relit debout, à
distance. Chaque antécédent porte enfin sa croix : un antécédent se saisit
vite et se trompe vite, et sans moyen de le retirer il se recopiait sur
chaque feuille imprimée. La suppression reste logique, tracée au journal
(règle de conception 2).

*Prescrit.* Vérification demandée : imprimer la pancarte d'un jour choisi
imprime bien **ce jour-là**, pas le jour courant — c'était déjà le cas, trois
tests le tiennent désormais. L'heure de prise se choisit à la ligne ; laissée
vide, elle suit l'horaire habituel du produit et du rythme, et l'enoxaparine
en une prise part à 20 h (`referentiels/horaires_par_produit.json`, une règle
en données, pas en code). La sédation, posée comme dispositif, se lit
maintenant dans le bloc P.S.E. de l'écran comme elle se lisait déjà sur la
feuille — et sa vitesse se règle en cours de route, ce qui manquait
complètement : une sédation se conduit surtout en descendant. Enfin la
colonne dose de la feuille porte le nombre de prises, « 1 g × 3 » : la dose
d'une prise ne dit pas la dose de la journée.

*Feuille imprimée.* Un jour passé qui ne porte qu'un seul bilan n'a plus ses
quatre créneaux numérotés : la valeur tient dans le premier, les trois
suivants redeviennent du papier réglé. Le bloc « Bilans infectieux » perd sa
colonne Date, qui suit désormais le libellé entre parenthèses —
« Hémoculture (06/09) » : 62 px pour cinq caractères prenaient la place du
résultat, seul texte du bloc dont la longueur soit imprévisible.

*Explorations et actes.* Une deuxième intubation s'appelle une réintubation,
et le logiciel le dit avant la saisie comme après (`libelle_repete` /
`en_cours_repete` dans le référentiel des dispositifs, rang d'épisode calculé
sur l'ensemble du séjour). Le retrait peut porter un motif : « extubation
programmée » ou « extubation accidentelle » ne se lisent pas pareil, et seule
la seconde est un événement à compter.

*Bilans.* La microbiologie rejoint le mode « Saisir » : c'est une saisie, pas
une relecture. L'antibiogramme se coche au lieu de se taper — trois listes
S / I / R puisées dans une liste fermée de molécules
(`referentiels/antibiotiques_antibiogramme.json`) ; en texte libre, la même
molécule s'écrivait de six façons et aucun profil de résistance du service ne
se comptait. L'ordre de saisie suit enfin celui de la visite : gaz du sang
d'abord — le seul bilan refait plusieurs fois par jour —, puis la chimie,
puis l'hémato, le bilan hépatique et le bilan lipidique repliés derrière.

*Évolution.* La check-list FAST HUG est retirée de l'écran : elle occupait la
moitié de la page pour redire ce que l'interne relit dans les quatre plans
juste en dessous. Le moteur de règles qui la calculait reste en place — ce
sont les mêmes règles qui produisent les rappels — et elle se rebranche en
une ligne si le service la redemande.

**v3.2 — 6 septembre 2026 — arrêter un traitement d'un geste sur sa ligne**

Consigne du service : arrêter un traitement se faisait dans un encart
séparé (« Arrêter une ligne »), à rouvrir et où retrouver la bonne ligne
dans une liste à part — un détour pour un geste courant. Retiré, remplacé
par une croix devant chaque traitement actif de la pancarte : un clic dessus
l'arrête, exactement comme avant (le traitement reste visible, barré, rien
n'est supprimé physiquement).

**v3.1 — 6 septembre 2026 — courbes sans altair, escarres rattachées au plan infectieux**

Signalé par le service : l'onglet Évolution plantait entièrement sur les
postes Windows du service (`TypeError: ... got an unexpected keyword
argument 'closed'`). Cause : `st.line_chart` importe `altair` à la volée,
qui entre en conflit de version avec `typing_extensions` sur certaines
installations — un risque qu'on ne maîtrise pas sur un poste d'hôpital.
Corrigé en supprimant la dépendance plutôt qu'en figeant une version
fragile : `theme.courbe()`, un traceur SVG sans dépendance, remplace
`st.line_chart` aux trois endroits où il était utilisé (SOFA dans
Évolution, tendance d'un analyte dans Bilans, cinétique d'une exploration
dans Explorations et actes).

Par la même occasion : les escarres, jusque-là dans un encart séparé et
sans lien avec le reste, sont désormais saisies à l'intérieur même de la
carte "Sur le plan Infectieux", où elles ont leur place clinique.

**v3.0 — 6 septembre 2026 — retrait des emojis décoratifs de l'interface**

Consigne du service : une interface sobre, fonctionnelle, peu décorative.
Les emojis en préfixe de bouton, d'expander et de titre (🖨, 📅, ➕, 🧪,
✏️, 🛏, la barre latérale 🛏/📈/⚙…) étaient purement décoratifs — retirés
de tous les écrans (`rea/ui/*.py`, `rea_app.py`). Conservés, parce que
fonctionnels : les cases à cocher ☑/☐ de la fiche imprimée (ce sont de
vraies cases de formulaire papier), les icônes d'alerte natives Streamlit
(`icon="⚠️"`, déjà couplées à une couleur sémantique rouge/orange), les
flèches de tendance ↑/↓ sur les valeurs de bilan, et le favicon de l'onglet
navigateur. Corrigé au passage : les puces ✅/⬜ de la check-list FAST HUG
ne respectaient pas la couleur d'état qui leur était assignée (un emoji
porte sa propre couleur, insensible au CSS) — remplacées par des puces
pleines/vides (● ○) qui l'affichent correctement.

**v2.9 — 6 septembre 2026 — récapitulatif biologique aligné sur la maquette de référence**

Comparé à `Feuille_Reanimation_Kairouan_A3fin.html`, envoyé par le service :
plusieurs paramètres, toujours lus ensemble, tenaient sur des lignes
séparées, et trois paramètres n'étaient pas suivis du tout.

1. **Lignes combinées** (`_valeurs_biologie` accepte désormais plusieurs
   codes par ligne, affichés séparés par « / ») : TP / INR, Cl⁻ / HCO₃⁻,
   ASAT / ALAT, Bili / Albumine, Ca²⁺ / Mg²⁺ / Phosphore, FR / AI. Rien
   n'est retiré de la saisie — seule la ligne imprimée change.
2. **Trois nouveaux analytes** (`rea/analytes.py`, groupe Ionogramme) :
   Magnésium, Phosphore, HCO₃⁻ veineux (distinct du HCO₃⁻ artériel posé
   avec chaque gaz du sang).
3. **Trois nouvelles colonnes sur `gaz_du_sang`** : SaO₂ (remplace le SpO₂
   continu — déjà suivi heure par heure sur le verso — dans ce tableau de
   gaz du sang), Vt, AI (aide inspiratoire).
4. Gaz du sang : FiO₂ rejoint le tableau des gaz (retiré de la ventilation,
   où il faisait doublon) ; Débit O₂ reste saisissable mais ne figure plus
   dans ce récapitulatif imprimé.

**v2.8 — 6 septembre 2026 — correction des constantes de la feuille de surveillance**

Remarque du service : la liste des constantes de la feuille imprimée
(verso) était fausse — EVA-BPS, RASS et Dextro manquaient, et la diurèse
avec les drains étaient rangés sous « Constantes vitales » au lieu de
« Sorties & drains ». Corrigé dans `referentiels/feuille_lignes.json`
(fichier, pas de code à toucher pour la prochaine correction) :

- **Constantes vitales** : T°, FC, PA (PAS/PAD), FR, SpO₂, Glasgow, Pupilles
  (D/G), EVA — BPS, RASS, Dextro.
- **Sorties & drains** : Diurèse, Bandelette urinaire, Redon 1/2/3 (au lieu
  de deux « Drain » génériques).

**v2.7 — 5 septembre 2026 — retrait du CIM-10, précision par région, motif/ATCD imprimés automatiquement**

1. **Codage CIM-10 retiré** de l'écran Identité : outil interne redondant
   avec le motif d'admission, déjà précis, que l'interne choisit à la
   création du séjour.
2. **« Corriger l'admission » → « Modifier l'admission »**, en bouton
   compact (`st.popover`) en haut à droite de l'onglet, plutôt qu'un bandeau
   permanent — modifier une admission est un geste occasionnel.
3. **Précision libre par région traumatique** (§4.3) : chaque région choisie
   porte désormais un commentaire libre, affiché « Région : commentaire »
   (ex. « Traumatisme crânien : Hématome extra dural droit avec engagement
   temporal / Embarrure pariétale »).
4. **Motif, type de traumatisme et antécédents imprimés automatiquement**
   sur la fiche de réanimation, dans l'encart « Motif — Transport — ATCD —
   Ttt habituel » (jusque-là entièrement manuscrit) : l'interne n'a plus à
   retranscrire à la main ce qu'il a déjà saisi sur l'onglet Identité. Le
   traitement habituel reste manuscrit tant qu'aucun écran ne le saisit.
5. **Antécédents : liste courte portée à 20 pathologies fréquentes**, et
   saisie repensée — un seul champ de recherche par mot-clé partiel (« dia »
   retrouve Diabète), plusieurs antécédents empilés avant une validation
   unique, texte libre accepté au même endroit si l'antécédent n'est pas
   dans la liste courte.

**v2.6 — 5 septembre 2026 — protocoles et définitions câblés, antécédents en trois états, pancarte relue avant impression**

Suite directe de la reprise d'architecture v2.5 : plusieurs briques posées mais
jamais reliées à un écran, et deux bugs réels trouvés en les câblant.

1. **Heure de prélèvement par défaut : 08:00** (était 06:00 — décision
   FEUILLE_DE_ROUTE.md non reportée dans le code).
2. **Protocoles câblés à l'admission** (§4.5) : les protocoles pertinents
   pour la région traumatique ou le motif sont proposés à la création du
   séjour et appliqués sans jamais poser de dose.
3. **Définitions cliniques câblées** (Berlin/KDIGO/qSOFA/Sepsis-3, §8) à
   l'onglet Évolution — `rea/domaine/definitions.py` était pur et testé mais
   inatteignable depuis l'interface.
4. **`score_quotidien` historisé** à chaque calcul de SOFA.
5. **Bug réel — transfert de lit invisible** : `changer_de_lit` écrivait
   l'historique (`sejour_lit`) mais jamais `sejour.lit_admission`, le champ
   que le tableau des lits lit réellement. Un transfert ne changeait donc
   rien à l'écran. Corrigé, avec contrôle d'occupation du lit cible.
6. **Bug réel — motifs associés perdus** : `definir_motifs` sortait sans
   rien écrire dès que `motif_principal` était `None`, ce qui empêchait
   d'associer un motif non traumatique à un séjour traumatique (ex.
   traumatisme thoracique + embolie pulmonaire + SDRA + acidocétose
   diabétique — cas explicitement demandé par le service).
7. **`st.form()` retiré des écrans d'admission et de correction.** Un
   formulaire Streamlit ne redéclenche pas de script tant qu'il n'est pas
   soumis : la bascule traumatique/non traumatique, la révélation du
   mécanisme, de la provenance détaillée, ne s'affichaient jamais. Toute
   logique conditionnelle dans ce logiciel doit désormais éviter `st.form`.
8. **Antécédents en trois états** (§4.2 bis) : la case « Sans antécédent
   connu » de la SPEC devient un vrai « Le patient a-t-il des
   antécédents ? » Oui / Non / Inconnu — Inconnu s'affiche comme Non mais
   reste distingué en base (`antecedent` catégorie `evaluation`, retirée
   dès qu'un antécédent réel est ajouté). Si Oui : Familiaux / Personnels
   (chirurgical, médical, allergies) / Habitudes de vie, ces dernières avec
   trois habitudes prêtes — tabagisme quantifié en paquets-années,
   éthylisme, toxicomanie avec la ou les substances précisées.
9. **Écran Bilans** : bascule Saisir/Visualiser pour espacer la saisie de la
   relecture, sur demande du service.
10. **Pancarte de demain relue avant impression** (§5.5) : entre préparer
    (reconduction mécanique) et imprimer, une étape valider explicite
    (`journee.validee_le`/`validee_par`) — l'impression d'une reconduction
    jamais relue est désormais impossible depuis l'écran.
11. Placeholders français sur les listes déroulantes à choix multiple, et
    correction du double-journal dans `export.exporter()`/`geler()`.
12. **Écran Prescrit réorganisé** : le panneau « Ajouter une ligne » reste en
    permanence à côté de la pancarte, au lieu d'un tiroir à rouvrir à chaque
    ligne. La voie se choisit d'un clic sur un bouton coloré (même couleur
    qu'à l'affichage de la pancarte), plutôt que dans une liste déroulante —
    c'est le geste le plus répété de l'écran.

**v2.5 — 5 septembre 2026 — reprise d'architecture : atomicité, traçabilité, découpe**

Quatre corrections issues d'une évaluation structurelle du dépôt. Aucune ne
change ce que le service voit à l'écran ; toutes changent ce sur quoi on peut
s'appuyer.

1. **Les écritures sont atomiques.** La connexion était en validation
   automatique, sans un seul `BEGIN`/`COMMIT` dans tout le dépôt. Une
   admission — créer le patient, puis le séjour — pouvait laisser un patient
   sans séjour ; une correction de motifs, qui efface tout avant de reposer la
   nouvelle liste, pouvait laisser un séjour **sans aucun motif**. `Base` a
   maintenant un gestionnaire de transaction (`base.transaction()`), le verrou
   est réentrant, et une ligne part désormais avec sa trace au journal, ou pas
   du tout.
2. **Les compteurs ne courent plus.** `identifiant_etude`, matricule `XXX-` et
   `numero_sejour` se calculaient par `COUNT(*) + 1`, lu puis écrit hors
   transaction. Deux admissions simultanées prenaient le même identifiant — et
   comme le schéma porte une contrainte d'unicité, la seconde **plantait**.
   Deux onglets ouverts suffisaient : Streamlit sert chacun dans son propre
   fil. L'allocation se fait maintenant dans la transaction, sur le premier
   numéro libre. Vérifié par des tests qui lancent douze admissions en
   parallèle, et qui échouent bien sur l'ancien code.
3. **Tout forçage d'un garde-fou laisse une trace.** Un avertissement
   « impossible » se franchit à un second clic — c'est voulu. Mais seul
   `bilan_resultat` avait une colonne `saisie_forcee` : sur les cinq autres
   écrans qui laissent forcer (admission, correction, prescription, sortie,
   dispositifs), rien dans le dossier ne disait qu'un garde-fou avait été
   franchi. Le journal enregistre désormais l'écran, l'utilisateur et le texte
   exact des avertissements passés outre.
4. **`rea_app.py` n'est plus un monolithe.** 2 040 lignes, 33 fonctions dont 8
   de plus de cent lignes, et surtout **zéro test** : le fichier n'était pas
   importable sans exécuter l'application entière. Les écrans vivent maintenant
   dans `rea/ui/` (lits, admission, identite, prescrit, bilans, evolution,
   actes, sortie, fiche, champs), et `rea_app.py` se réduit à 70 lignes de
   montage. `rea/ui/contexte.py` porte ce que les écrans partagent (base,
   utilisateur courant, garde-fou de cohérence) à la place des variables
   globales qui les retenaient prisonniers du même fichier.
5. **Règle R3 tenue.** `rea/rendu/feuille.py` importait `db.Base` et six
   services : le rendu décidait quoi lire, et `services/pancarte.py` devait un
   import différé pour éviter le cycle. Un `services/feuille_dossier.py`
   rassemble maintenant toutes les lectures, et le rendu reçoit ce dossier —
   il ne connaît plus ni la base ni les services. Au passage, `ui/utilisateur.py`
   écrivait lui aussi directement en base (règle R1) : c'est un service
   désormais.

Les règles d'isolation sont **vérifiées par des tests** (`test_architecture.py`)
et non plus seulement écrites : le domaine reste pur, aucun écran n'écrit en
base, le rendu ne lit rien, et le paquet n'a aucun cycle d'import. Une règle
qu'aucun test ne tient finit par ne plus être vraie — les cinq l'avaient été
au moins une fois.

- 370 tests (pytest, +63), dépôt propre sous pyflakes, et parcours complet des
  treize écrans plus une impression réelle vérifiés au navigateur.
- La couverture affichée passe de 90 % à 69 %, ce qui est une **amélioration
  de la mesure, pas une régression** : `rea/ui/` (1 025 instructions) était
  jusqu'ici totalement absent du rapport, faute d'être importable. Le cœur
  métier reste au-dessus de 90 %.

**v2.4 — 4 septembre 2026 — éditeur de règles et de protocoles, sans JSON**

Jusqu'ici, ajouter un rappel ou un protocole pré-rempli demandait d'éditer un
fichier JSON à la main dans `regles/` ou `protocoles/` — en pratique un frein
pour le service, qui n'a pas à ouvrir un éditeur de texte pour ça.
Administration → **Règles d'aide** et **Protocoles** portent maintenant un
formulaire complet ; le fichier reste la vérité, ces écrans ne font que le
lire et le réécrire exactement comme une main l'aurait fait.

- **Règles d'aide** : choisir un fichier existant ou en créer un nouveau,
  lister/modifier/supprimer ses règles, composer une condition (jusqu'à 4
  clauses, et/ou) sur la liste des faits que le moteur sait déjà calculer
  (`FAITS_CONNUS` dans `rea/domaine/regles.py`), et **tester la règle avec des
  valeurs d'exemple avant de l'enregistrer** — un aller-retour sans quitter
  l'écran. Le garde-fou SPEC §3.1 (aucune règle ne peut porter un mot de
  posologie — mg/kg, administrer, injecter…) est vérifié au moment de la
  frappe du message, avec le même code que celui qui protège les fichiers
  livrés.
- **Protocoles** : mêmes principes pour les protocoles de pré-remplissage —
  déclencheur (région traumatique ou motif), jusqu'à 6 lignes de prescription
  et 4 explorations proposées, consignes. La règle de sécurité 1 (SPEC §4.5)
  reste tenue par le code, pas par l'écran : tant que « Validé » n'est pas
  coché et « Signé par » renseigné, `protocoles_valides()` — et donc tout
  écran de proposition — ignore le protocole, qui reste un brouillon visible
  mais inerte.
- Chaque enregistrement incrémente la version du fichier
  (`AAAA-MM-JJ.N`, `regles.prochaine_version()`), comme une modification
  manuelle l'aurait fait.
- En corrigeant ce chantier : un bug d'isolation dans les tests de cet
  éditeur écrivait, lors d'une exécution complète de la suite, dans les
  vrais dossiers `regles/` et `protocoles/` du dépôt au lieu d'un dossier
  temporaire — `conftest.base` vide `sys.modules["rea.*"]` pour forcer une
  relecture de `REA_DIR`, ce qui pouvait faire pointer un module `rea.config`
  fraîchement importé vers un objet différent de celui déjà capturé par
  `rea.protocoles`. Le correctif patche `protocoles.config` directement
  plutôt qu'un `rea.config` réimporté à part.
- 290 tests (pytest, +10) ; vérifié aussi dans l'application réelle
  (Playwright) : créer/tester/modifier/supprimer une règle, créer un
  protocole brouillon et vérifier qu'aucun écran ne le proposerait, le
  valider et signer, vérifier qu'il devient proposable, le supprimer.

**v2.3 — 5 septembre 2026 — neuf remarques du service sur la feuille imprimée**

Toutes issues d'une relecture de la feuille par le service.

1. **La grille horaire commence à 8 h**, pas à minuit — c'est l'heure où la
   relève ouvre la feuille. `ORDRE_HEURES = (8..23, 0..7)` commande à la fois
   l'en-tête et le placement des ronds, recto comme verso.
2. **La colonne « Voie » a disparu** : chaque bloc est déjà organisé par voie,
   elle ne disait rien de plus. Ce qu'elle portait d'utile pour les entrées
   (perfusion / nutrition) est reporté entre parenthèses à côté du produit.
   La largeur libérée agrandit Dose.
3. **La dose affiche le nombre de comprimés ou d'ampoules** à côté du dosage
   — « 40 mg · 1 cp », « 4000 UI · 1 amp » — sauf en seringue électrique, où
   la vitesse (le seul nombre qu'un infirmier règle) prime sur tout le reste.
   `nb_ampoules` est désormais saisissable en PO (comprimés) et SC
   (ampoules), en plus de PSE ; toujours une valeur saisie, jamais déduite du
   dosage (SPEC §3.1).
4. **Le rond à cocher est plus grand** (11px → 15px, gras) : visible depuis
   le pied du lit.
5. **Le nom du médicament s'imprime en bleu**, plus gras — la seule couleur
   du tableau qui ne soit ni le noir du texte ni le vert d'en-tête du service.
6. **Les abords et dispositifs sont abrégés** : KTVC (sous-C G, 3 voies),
   KTA (radiale G), SNG (ND, 55cm), SV (sans le calibre — ça ne change pas
   grand-chose), Trachéo, Drain thx… Un nouveau référentiel
   (`feuille_abreviations.json`) porte ces raccourcis : le service peut en
   changer sans toucher au code. Les écrans du logiciel gardent le libellé
   complet, seule la feuille imprimée est compressée.
7. **La sédation apparaît aussi en P.S.E., vitesse comprise** — en plus des
   abords, où son compteur de jours reste affiché. C'est à la fois une
   lecture neurologique et une consigne infirmière ; elle partage le quota de
   lignes du bloc P.S.E., elle ne s'ajoute pas par-dessus.
8. **Le texte grossit dans un bloc largement vide** : moins d'un tiers de
   lignes utilisées → 13,5 px, moins de 60 % → 11,5 px, sinon la taille
   normale. Un style calculé par patient est injecté au début de la feuille ;
   la maquette elle-même ne change pas.
9. **Rappel si les plaquettes sont basses sous énoxaparine ou IPP** — deux
   règles ajoutées à `regles/rappels_biologie.json`, sur signalement du
   service : risque hémorragique et TIH pour l'héparine de bas poids
   moléculaire, cause médicamenteuse à évoquer pour un inhibiteur de la
   pompe à protons. Comme toute règle tout juste ajoutée, marquées non
   validées tant qu'un senior ne les a pas confirmées.

- 280 tests (pytest, +15), vérifiés aussi sur un dossier réaliste couvrant les
  neuf remarques, dans l'application réelle


**v2.2 — 5 septembre 2026 — corriger une admission, revoir les fiches imprimées**

Deux manques signalés à l'usage : aucune façon de corriger une erreur de
saisie à l'admission sans recréer le patient, et aucune façon de retrouver
une fiche déjà imprimée un autre jour.

*Corriger l'admission*

Un encadré « ✏️ Corriger l'admission » dans l'onglet Identité, fermé par
défaut, pré-rempli avec les valeurs actuelles. Ce n'est pas une nouvelle
admission : la même ligne est mise à jour (règle de conception 2 — jamais de
suppression physique), avec trace de qui a corrigé et quand dans le journal.

Couvre aussi le cas où le motif a été coché du mauvais côté à l'admission
(traumatique / non traumatique) : basculer d'un côté à l'autre efface
proprement les régions ou les motifs de l'ancienne catégorie, sans les laisser
traîner en double.

Le **lit n'est volontairement pas modifiable** ici : changer de lit est un
transfert (`changer_de_lit`, déjà écrit côté service mais pas encore relié à
un écran), pas une correction d'erreur de saisie — les deux n'ont ni la même
trace attendue ni les mêmes contrôles.

*Revoir les fiches imprimées*

Chaque impression était déjà conservée telle quelle en base
(`pancarte_snapshot`, une des rares tables où le texte est stocké et non
recalculé — règle de conception 6), mais rien ne permettait de la relire :
seule la toute dernière impression restait visible, et seulement jusqu'au
prochain rafraîchissement du navigateur.

- **Par patient** (onglet Prescrit) : « 📜 Anciennes fiches imprimées »,
  sélecteur par jour et version, aperçu et téléchargement.
- **Par jour, tout le service** (Administration → Fiches imprimées) : choisir
  une date, voir tout ce qui a été imprimé ce jour-là, tous lits confondus —
  la relecture qu'une visite ou une revue médico-légale demande.

La fiche relue est **l'instantané exact du jour d'impression**, pas une
version recalculée avec les données d'aujourd'hui : un test vérifie que
modifier le dossier après coup ne change pas une fiche déjà imprimée.

- 265 tests (pytest, +9), vérifiés aussi dans l'application réelle : correction
  d'une admission, historique par patient, historique par jour tout le service


**v2.1 — 5 septembre 2026 — la feuille du service**

Le document attendu depuis le début est arrivé : la maquette A3 de la feuille
de réanimation du service (Hôpital Ibn El Jazzar, Kairouan). La mise en page
imprimée n'est donc plus provisoire.

*La maquette reste un fichier, pas du code*

`modeles/feuille_reanimation_kairouan.html` est la maquette du service, reprise
sans retouche de dessin. Le programme n'y injecte que des valeurs, par trois
constructions et pas une de plus (`{{ valeur }}`, `{{ valeur.champ }}`,
`<sc-for>`). Le jour où le service change sa feuille, il remplace ce fichier —
il n'y a rien à reprogrammer. C'est la règle R3 tenue jusqu'au bout : la couche
de rendu met en forme, elle ne calcule rien.

L'ancienne mise en page A4 écrite en Python est supprimée.

*Ce que la feuille apporte, et qu'une feuille vierge n'apporte pas*

- Les **bilans des deux jours précédents** sont reportés, colonne par jour.
- La **colonne du jour reste vide** : les bilans de la garde s'y écrivent à la
  main pendant la nuit et sont ressaisis le lendemain matin. Le logiciel ne
  prend jamais cette place, même s'il connaît déjà une valeur du jour.
- Les **examens demandés la veille** sont inscrits à leur ligne, avec une case
  à l'heure de réalisation.
- Un **rond par prise** est posé sur la ligne du médicament, à l'heure calculée
  d'après le rythme. Le rond est vide : c'est l'infirmier qui le coche. Le
  logiciel dit *quand*, il ne dit jamais que c'est fait.
- Les **dispositifs sont cochés avec leur compteur de jours**, calculé.
- Les cases **« à demander pour demain »** sont pré-cochées d'après la saisie ;
  trois d'entre elles couvrent deux examens (Urée/Créat, CRP/PCT, ECBU/PDP) et
  se cochent dès que l'un des deux est demandé.

*Ce que la feuille laisse délibérément vide*

Les constantes horaires, les sorties et drains, les zones de texte : elles se
relèvent au lit du malade, sur le papier. Le logiciel étiquette ces lignes, il
ne les remplit pas.

*Ce qui a été corrigé en chemin*

- Le service note « 24 h » pour minuit et la grille imprimée va de 0 à 23 : la
  prise de minuit d'un ×4/j n'apparaissait nulle part. Repliée sur 0.
- Une ligne **arrêtée ce jour-là** reste imprimée, **barrée** et marquée
  « ARRÊTÉ ». Une ligne qui disparaît sans trace, c'est soit une
  administration poursuivie par habitude, soit un arrêt que personne ne
  remarque.
- Les boucles imbriquées du gabarit (créneaux dans les jours) étaient mal
  appariées : la moitié du tableau de biologie aurait disparu sans erreur.
- Un **débordement** est signalé en pied de page : la feuille a un nombre de
  lignes fixe, et une ligne prescrite qui n'y tient pas doit se voir.

*Impression*

Deux pages A3 paysage, sans script ni police téléchargée : le poste du service
peut être hors ligne. Un bouton télécharge la feuille, qui s'imprime depuis le
navigateur (A3, paysage, marges nulles, sans mise à l'échelle).

- 251 tests (pytest, +19), et vérification de la feuille remplie sur un dossier
  complet ainsi que de l'impression depuis l'application

*Groupe sanguin et rapport PaO₂/FiO₂ (ajoutés le 5 septembre)*

- Le **groupe sanguin** est demandé dès l'admission, à côté du sexe : il figure
  en tête de la feuille imprimée, et quatre heures du matin n'est pas un moment
  pour le chercher. Il est porté par le **patient**, pas par le séjour — il ne
  change pas d'une admission à l'autre et n'a pas à être resaisi. « Non
  renseigné » reste une valeur à part entière : un groupe inconnu n'est jamais
  deviné ni affiché comme connu.
- Le **rapport PaO₂/FiO₂** est calculé pour chaque gaz du sang et porté à sa
  ligne sur la feuille. C'est le seul chiffre de la feuille qui n'est ni saisi
  ni recopié : le recalculer à la main à chaque gaz du sang est exactement le
  genre d'arithmétique qu'on finit par ne plus faire. Une case reste vide
  quand la FiO₂ manque — elle dit « pas de gaz du sang », jamais « rapport
  normal ».

- 256 tests (pytest, +24)



**v2.0 — 4 septembre 2026 — tous les blocs codables de la feuille de route**

Cette version termine les blocs 0 à 18. Ce qui reste ne dépend plus du
développement : un document attendu, des validations à signer, deux fichiers
officiels à recopier.

*Fondations remises d'aplomb (règles R2 et R4, violées jusqu'ici)*

- **Les référentiels sont des fichiers** (`referentiels/`, 32 fichiers JSON
  versionnés). `rea/listes.py` n'est plus qu'un module d'accès. Les 37 noms
  qu'il exporte ont exactement les mêmes valeurs qu'avant — vérifié par
  comparaison automatique — et les 146 tests d'alors passent inchangés.
  **Ajouter un motif d'admission ne demande plus de reprogrammer le logiciel.**
- **Les règles d'aide sont déclaratives** (`regles/`). Le moteur ne connaît
  aucune règle : il lit des conditions et les évalue sur des faits. Changer un
  seuil ne demande plus d'informaticien.
- La **version de chaque référentiel et de chaque jeu de règles est affichée**
  dans l'écran Administration (§4.5) : deux extractions faites à six mois
  d'écart ne sont pas comparables sans le savoir.

*Bloc 0 terminé*

- **Restauration de sauvegarde** — écrite, testée, et accessible à l'écran.
  Une sauvegarde jamais restaurée n'existe pas. L'état courant est sauvegardé
  avant tout remplacement : restaurer par erreur reste réversible.
- **Journal d'audit consultable** et filtrable. Il était rempli mais illisible,
  donc inutilisable pour retracer qui a modifié quoi.
- Deux sauvegardes prises dans la même seconde s'écrasaient — ce qui arrivait
  systématiquement au filet posé avant une restauration. Corrigé.
- Les **colonnes ajoutées au schéma sont rattrapées à l'ouverture** d'une base
  ancienne. Sans cela, la première mise à jour après mise en service aurait
  planté à la première écriture.

*Bloc 4 — cohérence câblée partout*

Les contrôles n'étaient branchés que sur les bilans ; ils le sont maintenant
sur les six écritures qui portent des dates. Un avertissement « improbable »
s'affiche et laisse passer ; un « impossible » — extubation avant
l'intubation, sortie avant l'admission — demande un second clic. Rien n'est
bloqué : le médecin garde le dernier mot, mais pas par inadvertance.

*Bloc 7 — check-list quotidienne*

FAST HUG (Vincent, *Crit Care Med* 2005), cochée à partir de ce qui est déjà
saisi, avec trois états : fait, à vérifier, **non renseigné** — un point non
renseigné n'est pas un point raté. Seize rappels livrés (durée des dispositifs,
sédation prolongée, intubé sans SNG, escarres, valeurs biologiques critiques).
Un test vérifie qu'**aucune règle ne parle de posologie** : la limite du §3.1
devient exécutable, pas seulement écrite.

*Bloc 9 — scores*

SOFA quotidien avec sa courbe, IGS II et mortalité prédite, jours sans
ventilation à J28. Trois précautions :

- une variable manquante vaut zéro point **mais rend le score explicitement
  incomplet**, avec la liste de ce qui manque ;
- la mortalité prédite n'est calculée que sur un IGS II complet ;
- le **barème IGS II est marqué non validé** : il a été saisi de mémoire et
  doit être relu contre la publication d'origine avant tout usage statistique.

La composante circulatoire du SOFA est limitée à la PAM : ses paliers
supérieurs dépendent de la dose de vasopresseur, que le logiciel ne saisit pas
et ne calcule pas (§3.1). C'est écrit à l'écran plutôt que masqué.

Deux variables de l'IGS II qu'aucune autre donnée ne permettait de retrouver
après coup sont désormais saisies à l'admission : **type d'admission** et
**maladie chronique au sens du score**.

*Blocs 12 à 18 — la couche recherche*

- **Export pseudonymisé** : ni matricule, ni nom, ni date de naissance ;
  identifiant d'étude et âge à la place. Le texte libre est retiré par défaut
  — un commentaire peut contenir un nom, un lieu, un numéro de chambre — et
  l'inclure inscrit un avertissement dans l'export lui-même. La politique de
  pseudonymisation est **volontairement dans le code** et non dans un fichier :
  tout le reste est paramétrable, pas ceci, car un fichier se modifie sans
  trace. L'export emporte son **dictionnaire des données**, la version de
  chaque référentiel, et trois codes de valeur manquante distincts (`.NR` non
  renseigné, `.NA` non applicable, `.NF` non fait).
- **Gel de base** avant analyse : une étude qui tourne pendant que les données
  bougent n'est pas reproductible.
- **Microbiologie** : prélèvements, résultats en attente affichés en premier
  (c'est ce qu'on oublie), infections acquises. Consommation d'antibiotiques
  en **jours de traitement pour 1000 journées** : la table des DDD de l'OMS
  n'est pas recopiée de mémoire, le fichier l'attend.
- **Définitions standard** : Berlin, KDIGO, qSOFA, Sepsis-3, avec référence.
  Une définition qu'on ne peut pas appliquer rend **« non applicable » et
  jamais « négatif »** : sans gaz du sang, on ne peut pas dire qu'il n'y a pas
  de SDRA.
- **Taux d'infections liées aux dispositifs** au dénominateur ECDC
  (jours-dispositif). Sans jours enregistrés le taux est *incalculable*, pas
  zéro. Une infection diagnostiquée avant 48 h n'est pas comptée comme acquise.
- **Cohortes** et **Table 1 de STROBE** : chaque ligne déclare sur combien de
  dossiers elle est calculée. Mortalité observée et rapport observé/attendu,
  ce dernier seulement quand tous les séjours clos ont un IGS II complet.
- **Codage CIM-10** avec recherche insensible aux accents, sur un
  sous-ensemble de démarrage **explicitement partiel** (58 codes à vérifier).

*Ce qu'un test de garde a rattrapé*

Quatre tables déclaraient leurs colonnes de texte libre sous un nom
inexistant : le texte continuait donc d'être exporté. Une faute de frappe
invisible à la relecture, et une fuite réelle. Le test vérifie désormais que
chaque colonne déclarée existe.

*Ce qui ne dépend plus du développement*

1. le **PDF réel du prescrit** — la mise en page imprimée reste provisoire ;
2. les **validations d'un senior** : bornes des bilans, barème IGS II, seuils
   des rappels, correspondances LOINC (tout est marqué non validé à l'écran) ;
3. la **CIM-10 complète** et la **table des DDD** — deux fichiers à remplir
   depuis leur source officielle, sans toucher au code ;
4. le **dossier de protection des données** et le test sur patients réels.

- 231 tests (pytest, +85), et vérification de bout en bout dans l'application
  réelle : admission, codage CIM-10, prélèvement, cohorte, export


**v1.9 — 3 septembre 2026**

- **Poids idéal théorique** ajouté aux valeurs dérivées, formule de Devine
  adaptée aux centimètres, telle que fournie par le service :

      Homme : 50   + 0,91 × (taille − 152,4)
      Femme : 45,5 + 0,91 × (taille − 152,4)

  Référence : Devine BJ, *Drug Intell Clin Pharm* 1974;8:650-5
- Le poids idéal **ne remplace jamais le poids réel** : les deux sont affichés
  côte à côte dans la fiche d'identité. C'est le **poids réel** qui entre dans
  la clairance de la créatinine
- La formule sort de son domaine de validité chez les patients de moins de
  1,20 m : dans ce cas rien n'est affiché plutôt qu'un poids absurde
- Le sexe est indispensable — sans lui, la formule n'a pas de constante de
  départ et la valeur reste vide
- 146 tests (pytest, +8)

**v1.8 — 3 septembre 2026**

- **Saisie pensée pour le demi-écran.** L'application est utilisée avec le DMI
  ouvert à côté, fenêtre en demi-largeur : la saisie des bilans passe en tête
  d'onglet et tient sur deux colonnes à 960 px
- **Champs vides à l'ouverture.** Plus de « 0.00 » à effacer avant de taper :
  le champ est vide, la **plage normale s'affiche en gris dedans**, et la
  valeur est **signalée en rouge** dès qu'elle sort de la plage. Deux niveaux
  distincts, comme au bloc 4 : « hors plage usuelle » (anormal) et « hors
  bornes physiologiques » (impossible)
- La **virgule décimale française** est acceptée partout : on tape « 9,2 »
- **Poids et taille à l'admission**, plus la créatinine antérieure connue.
  Le poids est ce qui rend la **clairance de la créatinine** calculable
- **Valeurs dérivées** (`rea/domaine/calculs.py`), chacune avec sa formule et
  sa référence bibliographique dans le code :
  - Clairance de la créatinine — Cockcroft & Gault 1976
  - Natrémie corrigée à la glycémie — Katz 1973
  - Calcémie corrigée à l'albuminémie — Payne 1973
  - Trou anionique, rapport PaO₂/FiO₂
  Une valeur dérivée rend `None` dès qu'il lui manque un ingrédient : elle
  n'invente jamais de valeur par défaut. **Aucune n'est une dose** et le
  logiciel n'en déduit aucune adaptation de posologie (§3.1)
- **Albumine et glycémie** ajoutées au catalogue — le manque signalé par la
  feuille de route (bloc 6, alignement ANZICS). Ce sont aussi les ingrédients
  des deux corrections ci-dessus
- **ECG** ajouté aux explorations (rythme, FC, PR, QRS, QTc, axe,
  repolarisation, territoire) et **ETT étendue** à douze paramètres
  (ITV sous-aortique, débit cardiaque, E/A, E/e′, TAPSE, VD/VG…)
- **Éléments fixes dans les quatre plans de l'évolution.** Ce que l'interne
  réécrivait chaque jour devient saisissable en un geste, et exploitable en
  cinétique :
  - *Neurologique* : RASS, Glasgow, pupilles, déficit focal — et
    automatiquement « Sédaté J4 » ou « Arrêt sédation J4 »
  - *Respiratoire* : FR, SpO₂, encombrement — et automatiquement « Intubé J6 »
    et le mode ventilatoire du dernier gaz du sang
  - *Hémodynamique* : FC, PA (écrite « 105/58 »), PAM, diurèse sur 24 h,
    diurèse conservée, signes périphériques de choc — et automatiquement les
    amines en cours avec leur débit
  - *Infectieux* : température, frissons — et automatiquement les
    antibiotiques avec leur J{n}/{durée} et les escarres
- **Escarres suivies dans le temps** (table `escarre`) : localisation, grade
  NPUAP/EPUAP, date de constat, date de guérison. Une escarre guérie sort de
  l'évolution mais reste dans l'historique du séjour
- Un dispositif n'est jamais écrit deux fois : l'intubation et la sédation
  sont reprises dans leur plan, pas dans la ligne de tête
- 138 tests (pytest, +30)

**❓ Question ouverte soulevée en séance** — « on corrige au pH les variables ».
Les deux corrections mises en place sont celles dont la formule fait consensus
(calcémie/albumine, natrémie/glycémie). Une correction **au pH** est ambiguë :
s'agit-il de la kaliémie estimée selon le pH, du calcium ionisé, ou d'autre
chose ? La formule à retenir doit être écrite avec sa référence avant d'être
codée — une définition non écrite change silencieusement.

**v1.7 — 3 septembre 2026**

- **Feuille de route modulaire reprise dans le dépôt** (`FEUILLE_DE_ROUTE.md`),
  avec en §10 un audit honnête du code existant contre ses règles. Deux
  violations constatées et non encore corrigées : les référentiels sont dans du
  code et non dans des fichiers (règle R2), et trois règles d'alerte sont
  codées en dur dans l'écran (règle R4)
- **Colonnes « à câbler tôt » posées** (§5 de la feuille de route) — elles
  coûtent quelques minutes maintenant et des semaines de reprise rétroactive
  plus tard :
  - `code_atc` sur chaque ligne de prescription — sans lui, la consommation
    antibiotique en DDD demanderait de recoder des milliers de lignes
  - `code_loinc` et `unite_ucum` sur chaque résultat de bilan, recopiés
    automatiquement depuis le catalogue d'analytes à l'enregistrement
  - `code_icd10` sur le motif d'admission
  - `creatinine_base` sur le séjour — sans elle, la définition KDIGO de
    l'insuffisance rénale aiguë est incalculable a posteriori
- Les 25 analytes portent une correspondance LOINC et UCUM. ⚠️ **Ces
  correspondances sont une proposition, pas une source validée** : le drapeau
  `analytes.LOINC_VALIDE` reste à `False` tant qu'un senior ou une source
  officielle ne les a pas relues ligne à ligne (question B de la feuille de
  route). L'export devra les marquer comme provisoires
- **Bloc 4 fait — contrôles de cohérence à la saisie**, le meilleur ratio de la
  feuille de route. Deux jeux de bornes bien distincts :
  - *bornes usuelles* (`rea/analytes.py`) : « anormal ». Une kaliémie à 6,2 est
    hors normes mais parfaitement réelle en réanimation
  - *bornes physiologiques* (`rea/domaine/coherence.py`) : « impossible chez un
    patient vivant ». Une kaliémie à 45 est une faute de frappe
  Sont également vérifiés : sortie avant admission, extubation avant
  intubation, naissance dans le futur, âge de plus de 120 ans, dose ou vitesse
  absurde, durée prévue déraisonnable
- **Un avertissement n'est jamais un blocage** : le médecin peut toujours
  forcer, et la valeur forcée est marquée `saisie_forcee` en base pour qu'un
  relecteur la retrouve
- Critère de fin du bloc 4 respecté et transformé en test : **dix erreurs de
  frappe volontaires sur dix sont signalées**, et aucune valeur anormale mais
  réelle ne déclenche de fausse alerte
- 108 tests (pytest, +15)

**v1.6 — 3 septembre 2026**

- **Écran « Explorations et actes »** (§6) : les explorations chiffrées
  (DTC, ETT, TDM…) et, nouveauté, **tous les dispositifs invasifs** —
  intubation, sédation, trachéotomie, SNG avec fixation en cm, gastrostomie,
  sonde urinaire, KTSP, KT central avec son site, PICC, KTA, VVP, drains,
  DVE, épuration. Les compteurs de jours sont **calculés** : « Intubé J3 »,
  « Extubé J2 », « Arrêt sédation J1 », « KT central J5 (jugulaire interne
  droite, 3 voies) »
- Décision de modèle : les tables `ventilation_episode` et
  `epuration_episode` de la v1.3 sont **supprimées** au profit de la table
  unique `dispositif`. Deux tables auraient donné deux endroits où lire la
  date d'intubation, donc deux vérités possibles — le même raisonnement que
  pour le poste du chef de service (§2.3). La durée de ventilation du socle
  de recherche se calcule désormais depuis les épisodes d'intubation
- Ces compteurs alimentent sans ressaisie le bandeau d'état du patient, le
  tableau des lits, l'évolution du jour et le compte rendu de sortie
- **Vue de cinétique des bilans repensée pour le lit du malade** : panneaux
  par organe (Infection, Rénal, Hématologie, Ionogramme), dernière valeur
  avec sa variation depuis le prélèvement précédent, tableau analytes ×
  dates, puis courbes. L'onglet s'ouvre désormais sur la lecture, la saisie
  est repliée — on consulte un bilan bien plus souvent qu'on n'en saisit
- Bornes usuelles de l'adulte ajoutées pour signaler une valeur hors norme
  (question 8) : elles **colorent seulement**, aucune décision clinique n'en
  dépend, et restent à valider par un senior
- **Refonte visuelle** : thème (`.streamlit/config.toml`), feuille de style
  commune (`rea/ui/theme.py`), tableau des lits en cartes avec métriques
  d'occupation et pastilles d'état, bandeau d'état en tête de chaque fiche
  patient. Code couleur constant : rouge = alerte, orange = attention,
  bleu = valeur calculée par le logiciel, vert = stable
- L'évolution du jour reprend maintenant les dispositifs et les explorations
  en plus des bilans et du prescrit — l'observation est quasi complète avant
  toute frappe
- 93 tests (pytest, +28)

**v1.5 — 2 septembre 2026**

- **Fichier HTML de saisie des bilans reçu** (`bilan_rea.html`) — débloque le
  bloc 4. Question ouverte 7 résolue
- **Écran Bilans construit**, intégrant directement ce fichier : mêmes
  analytes, mêmes groupes (NFS, Hémostase, Ionogramme & rénale, Gaz du sang
  & ventilation, Bilan hépatique, Bilan lipidique), même texte généré —
  seule différence volontaire : les valeurs sont **stockées en base**
  (format long, règle de conception 4) plutôt que perdues à la fermeture de
  la page, ce qui donne les courbes de cinétique (§7.2) sans travail
  supplémentaire
- Calculs automatiques repris à l'identique : rapport PaO₂/FiO₂, bilirubine
  indirecte, conversion mmol/L ↔ g/L pour le bilan lipidique
- Catalogue des analytes extrait dans `rea/analytes.py` — ajouter ou retirer
  un analyte est une ligne à changer, pas une refonte. Prévu : l'utilisateur
  a annoncé une version plus détaillée du fichier à venir (calcul de
  clairance de la créatinine automatique, au moins un champ à retirer)
- Table `gaz_du_sang` complétée avec `spo2` et `debit_o2` (débit d'oxygène
  pour masque/lunette), absents du schéma initial
- **Évolution quotidienne** : la section « Bilan du jour », vide depuis la
  v1.3, est maintenant remplie automatiquement depuis l'écran Bilans
- Testé de bout en bout en navigateur réel (Playwright) : saisie complète,
  bascule d'unité des lipides, enregistrement, texte généré, courbe de
  cinétique, reprise dans l'évolution — aucune anomalie, un seul ajustement
  cosmétique (hauteur de la zone de texte de l'évolution augmentée)
- 65 tests (pytest)

**v1.4 — 2 septembre 2026**

- **v1 utilisable de bout en bout.** Interface Streamlit (`rea_app.py`) avec
  les quatre écrans du seuil de la feuille de route : Lits (accueil),
  Admission (identité, motif traumatique/non traumatique, antécédents),
  Prescrit (ajout de ligne par voie, arrêt, bilan hydrique, bilans à
  demander, « préparer demain », impression), Sortie (clôture + compte
  rendu généré). Évolution quotidienne ajoutée en plus (bloc 3, en avance
  sur le seuil). Testé de bout en bout par un navigateur piloté
  automatiquement (Playwright) contre l'application réellement lancée —
  admission → prescription (10 lignes, toutes voies) → impression →
  évolution → sortie → lit libéré — captures d'écran envoyées à la session
- Deux bugs réels trouvés par ce test et corrigés : (1) `db.inserer()`
  tentait d'écrire `cree_le` même sur les tables qui n'ont pas cette colonne
  (`pancarte_snapshot`, `journal`, `sauvegarde`), (2) créer un utilisateur
  avec un nom déjà pris faisait planter l'application sur la contrainte
  UNIQUE au lieu de reconnecter la personne à son compte existant
- Pancarte imprimée : mise en page **provisoire**, clairement annoncée comme
  telle sur la pancarte elle-même (bandeau) et dans le code. Le PDF réel du
  prescrit du service n'a toujours pas été fourni (question ouverte 7/§7.1) ;
  cette mise en page sera reprise trait pour trait dessus
- 52 tests (pytest), domaine + base + schéma + services + pancarte/évolution
- Toujours pas commencé : Explorations (écran + reprise dans l'évolution),
  Bilans (bloc 4, bloqué), Statistiques (bloc 6), recherche ICD-10

**v1.3 — 2 septembre 2026**

- **Dépôt dédié créé** : `github.com/ibidia1/rea` — ce projet ne vit plus dans
  le dépôt `stat-serie` (sans rapport, application de révision du résidanat)
- **Première tranche de code, bloc 0 fait, bloc 1 en cours.** Schéma SQL
  complet (28 tables), listes codées, module de configuration du poste,
  couche base SQLite avec sauvegardes automatiques et journal des
  modifications, calculs de dates/âges/compteurs de jours, calcul des
  horaires par rythme et du bilan hydrique des entrées, chargement des
  protocoles JSON, services Admission/Sortie/Lits. **Pas encore fait à ce
  stade** : service de prescription (ajout de ligne, arrêt, reconduction
  J+1), génération de la pancarte imprimable, écran Explorations, évolution
  du jour, et surtout **l'interface Streamlit elle-même** — rien n'est encore
  utilisable par un interne. Suite de la session à venir
- Question 6 **tranchée** : ×4/j → 6-12-18-24, ×6/j → 4-8-12-16-20-24,
  modifiable dans la configuration et ligne par ligne
- Décision de modèle : **une ligne de prescription n'est jamais dupliquée** pour
  le lendemain. Elle porte `date_debut` / `date_arret` ; la pancarte d'un jour
  donné sera *calculée* par intersection avec cette période. C'est ce qui rend
  les compteurs de jours exacts sans aucune recopie, et ce qui empêche deux
  versions divergentes d'une même prescription (règle de conception 5)
- Décision : le **drapeau `SYMBOLES_UNICODE`** permettra de basculer tout le
  texte généré en ASCII (`HCO3-`, `PaO2`) le jour où le test de collage dans
  le DMI échoue
- Protocoles : format **JSON versionné et signé** dans `protocoles/`. Le
  protocole « traumatisme crânien » est livré en **brouillon non validé** et
  le chargeur (`rea/protocoles.py`) l'exclut tant qu'il n'est pas signé — donc
  tant que le chef de service ne l'a pas validé
- Bloc 4 (bilans) **explicitement non commencé** : le fichier HTML de saisie
  existant n'a pas été fourni, et le réécrire produirait un format incompatible
  avec celui déjà utilisé dans le service

**v1.2 — 1er septembre 2026**

- Alignement du socle de variables sur le **dictionnaire ANZICS** (§9.5)
- Deux champs à ajouter au fichier de bilans : **albumine et glycémie**
- Insuffisance rénale aiguë et score de gravité passent en **calcul automatique**
- Décision : valeurs **d'admission** plutôt que pires valeurs sur 24 h
- Score retenu : **IGS II**, pas ANZROD

**v1.1 — 1er septembre 2026**

- Ajout de l'écran **Explorations** (§6) : DTC, TDM, ETT et autres, avec valeurs
  chiffrées, proposées par protocole et reprises dans l'évolution
- Ajout de l'écran **Sortie** (§4.7) : destination codée, complications à trois
  états, ordonnance, consultation de suivi, compte rendu généré
- Prescription **par voie d'administration** (§5.2) : les champs de saisie
  changent selon PO / IV / PSE / S/C / Aérosol / Soins / Kiné / Entrées
- Ajout de la section **Bilans à demander pour le lendemain** (§5.2 bis)
- Ajout de **quatre usages** de la base au-delà de la cohorte (§9.4)
- Le programme compte désormais **8 écrans**

**v1.0 — août 2026**

- Version initiale du document de référence
