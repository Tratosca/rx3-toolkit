# Audit UX « fait par un DJ » — XDJ-RX3 Toolkit

## Top 10 des quick wins

Les formulations ci-dessous sont des propositions, pas des modifications effectuées. Les constats détaillés donnent les textes actuels EN/FR, les preuves et la lecture du persona.

| # | Changement directement applicable | Priorité · effort | Preuve et détail |
|---|---|---|---|
| 1 | Rendre visibles les introductions actuellement masquées ; placer la phrase utile sous le titre, sans bannière. | P1 · S | `app/ui/web/app.css:88` · O1 |
| 2 | Remplacer « Créer le mod » / « Build the mod » par **« Préparer la clé USB » / « Prepare USB drive »**, uniquement quand la destination est une clé USB ; employer « Préparer les fichiers » / « Prepare files » pour un autre dossier. | P1 · S | `app/ui/web/index.html:78`, `app/localization/fr.json:54` · M1 |
| 3 | Afficher **« Clé USB · {name} » / « USB drive · {name} »** en bas de la barre latérale, avec le chemin complet accessible. | P1 · S | `app/ui/web/app.js:198` · O2 |
| 4 | Remplacer le « Parcourir » de destination par **« Choisir la destination » / « Choose destination »** ; expliquer de sélectionner la clé elle-même. | P1 · S | `app/ui/web/index.html:115`, `app/ui/web/index.html:311` · O3 |
| 5 | Remplacer « Moteur de séparation et cache » / « Separation engine and cache » par **« Installation et stockage des stems » / « Stem setup and storage »**. Remonter l’installation en tête quand elle est nécessaire. | P1 · S | `app/ui/web/index.html:364`, `app/ui/web/stems.js:54` · S1 |
| 6 | Donner un accès direct **« Écouter les stems » / « Listen to stems »** depuis Préparation vers le panneau d’écoute existant. | P1 · S | `app/ui/web/index.html:348`, `app/ui/web/index.html:362` · S5 |
| 7 | Remplacer « À destination » / « At destination » par **« Stems enregistrés » / « Saved stems »**, et « Importés » / « Imported » par **« Fichiers choisis » / « Selected files »**. | P2 · S | `app/localization/fr.json:347`, `app/ui/web/stems-listen.js:127` · S6 |
| 8 | Remplacer l’astérisque de banque active par **« — utilisée sur la platine » / « — used on the deck »** dans le sélecteur. | P1 · S | `app/ui/web/samples.js:524` · A3 |
| 9 | Après récupération de la clé de chiffrement, afficher **« Clé de chiffrement prête. Vous pouvez préparer votre clé USB. » / « Encryption key ready. You can now prepare your USB drive. »** avec un bouton explicite vers Modules. | P1 · S | `app/ui/web/app.js:655`, `app/ui/web/app.js:752` · K7 |
| 10 | Dans le contrôle USB, remplacer « Retirer le mod » / « Remove the mod » par **« Retirer les modules de cette clé USB » / « Remove modules from this USB drive »**, et ajouter la procédure d’arrêt/redémarrage dans une aide dépliable. | P1 · S | `app/ui/web/index.html:65`, `README.md:308` · R1 |

## Les 3 changements structurants

1. **Faire de la clé USB le contexte visible du travail.** Conserver Modules comme écran initial et les cinq destinations. Dans Modules, présenter, dans cet ordre : destination, préparation initiale si nécessaire, choix des modules, action d’écriture. La barre latérale reste le point d’inspection USB. Chaque écran affiche sa destination réelle, même si elle diffère de celle des autres écrans. **P1 · M** — O2–O6, M1, K1–K8 ; `app/ui/web/app.js:192`, `app/ui/web/stems.js:470`.
2. **Organiser Stems autour de « préparer, écouter, utiliser sur la platine ».** Rendre l’installation nécessaire immédiatement accessible ; privilégier l’export rekordbox de la clé ; présenter playlist, stems à préparer, qualité, durée, destination ; donner ensuite accès à l’écoute et aux gestes sur la platine. L’import manuel et le stockage restent accessibles, avec les mêmes opérations. **P1 · M** — S1–S10 ; `app/ui/web/index.html:290`, `app/ui/web/index.html:348`.
3. **Employer les mêmes repères du choix jusqu’au résultat.** Nom de la clé, nom de banque, rôle des stems, couleurs et gestes stables ; distinguer sélection, enregistrement sur USB et activation sur la platine. Un résultat doit dire ce qui est prêt et quelle action suit. Conserver les libellés matériels et le contenu juridique. **P1 · M** — A3–A4, L2, K7, T1–T3, R1 ; `app/ui/web/app.js:741`, `app/ui/web/samples.js:491`.

## Cadre et niveau de preuve

Audit statique du checkout `/Users/fbrille/_Dev/rx3/rx3-toolbox`, le 27 septembre 2026, HEAD `256596c`, avec de nombreuses modifications préexistantes. Les lignes citées correspondent aux fichiers de travail lus, pas nécessairement au commit. Aucun code, réglage, fichier utilisateur ou périphérique n’a été modifié ; seul ce rapport est écrit. Aucun réseau, téléchargement, installation, commit ou test d’écriture.

Lecture préalable de `PRODUCT.md`, `.claude/STYLE.md` et `README.md`. Inspection de l’ensemble des fichiers HTML/CSS/JS nommés dans la demande, de `rx3-mock.js`, des quatre SVG Key Match et des deux catalogues. Les textes des modules viennent aussi de `mod/categories.json` et des manifestes : `app/localization/__init__.py:24` les ajoute au catalogue. Quelques lectures ciblées des producteurs de messages servent uniquement à identifier les textes effectivement présentables ; aucune recommandation de modification des services, du bridge ou de l’audio.

`make app` n’a pas été lancé. L’analyse statique suffit ici et évite les effets de l’application sur les fichiers ; même l’inspection USB peut effectuer un test d’écriture (`app/services/drive.py:73`). Aucun résultat ancien de validation visuelle n’est repris comme preuve actuelle. Les tailles, couleurs, ordres et règles de masquage sont **vérifiés dans le code** ; le ressenti du DJ et les risques de perte de repère sont des **inférences persona**. Aucun débordement, contraste perçu ou comportement sur matériel réel n’est déclaré testé.

**Persona unique :** DJ professionnel propriétaire d’un XDJ-RX3, habitué aux playlists, à l’export rekordbox et aux commandes de sa platine ; peu à l’aise avec les fichiers et l’installation de logiciels. Il ne doit pas traduire mentalement une opération informatique en résultat musical.

**Priorités :** P1 = perdu ou bloqué ; P2 = friction ou jargon ; P3 = finition. **Efforts relatifs de présentation :** S = texte, style ou déplacement local ; M = réorganisation de plusieurs états/composants ; L = chantier transversal. Ces efforts n’incluent aucune évolution de service. Lorsqu’un problème ne peut pas être résolu par la présentation, la limite est explicite.

Les propositions conservent les cinq destinations, les opérations existantes, le fonctionnement local et les libellés matériels (`PRODUCT.md:7`). Aucun nouvel écran de navigation principal, framework, build ou dépendance réseau. Aucune bannière ou disclaimer ajouté. Les aides proposées sont intégrées au contrôle concerné ou dans un dépliant. Les textes nouveaux sont signalés **« absent → »** ; les valeurs entre accolades proviennent de l’état déjà disponible ou d’un formatage de présentation, sans nouveau contrat de service.

## Parcours reconstitué : ce que le DJ rencontre

| Étape | Ce qui se passe dans l’interface actuelle | Ce que le DJ comprend et fait ; rupture probable |
|---|---|---|
| Première ouverture | Modules est initial ; langue du navigateur et thème système par défaut. Initialisation, puis conditions automatiques si aucune clé de chiffrement ni tâche affichée. `app/ui/web/index.html:72`, `app/ui/web/i18n.js:49`, `app/ui/web/components.js:4`, `app/ui/web/app.js:759`. | Il attend de choisir sa clé USB ; il doit d’abord comprendre un téléchargement et accepter des conditions. K1–K3. |
| Branchement USB | Aucune détection de branchement montrée dans le frontend : le contrôle inférieur ouvre l’inspection, puis un sélecteur de dossier. `app/ui/web/app.js:800`. | Brancher physiquement ne suffit pas ; il faut sélectionner le bon emplacement. O2–O3. |
| USB sélectionnée | Rapport, affectation initiale de la destination Modules ; ouverture de l’export dans Stems si présent et aucune bibliothèque ouverte ; affectation initiale de sa destination. `app/ui/web/app.js:192`, `app/ui/web/stems.js:470`. | Il pense avoir défini une clé commune ; un changement ultérieur peut laisser les destinations précédentes. O4. |
| Modules | Catégories, interrupteurs, sous-réglages harmoniques, résumé, clé de chiffrement et destination. `app/ui/web/app.js:317`, `app/ui/web/app.js:500`, `app/ui/web/index.html:87`. | Il choisit des usages DJ, mais « activé » et « Créer le mod » ne disent pas ce qui est déjà sur la clé. M1–M5. |
| Préparation Stems | Bibliothèque, playlist, destination, messages par morceau, waveforms, parties à séparer, qualité, installation/stockage. `app/ui/web/index.html:290`. | Il doit trouver les prérequis sous les réglages ; XML concurrence l’export USB connu. S1–S4. |
| Écoute Stems | Panneau sous « Import et écoute », après l’import manuel ; source enregistrée ou fichiers choisis ; Original et trois rôles possibles. `app/ui/web/index.html:348`, `app/ui/web/stems-listen.js:121`. | Il peut croire devoir importer ses résultats pour les écouter ; le sens des boutons actifs n’est pas expliqué. S5–S7. |
| Commandes Stems sur RX3 | Guide dépliable dans le module, modes Pads/Écran tactile, séquences animées. `app/ui/web/app.js:453`, `app/ui/web/rx3-mock.js:282`. | Il cherche comment jouer dans Stems, alors que l’aide est dans Modules. S10. |
| Logo | Choix d’image, aperçu, cadrage, thème d’aperçu et adaptation des gris ; activation Logo possible ; retour Modules pour écrire. `app/ui/web/logo.js:117`, `app/ui/web/index.html:273`. | L’aperçu paraît terminé, mais l’image n’est pas encore sur la clé. L1–L3. |
| Samples | Clé nécessaire ; banque, grille, inspecteur, test, volume et SHIFT ; enregistrement et activation distincts. `app/ui/web/samples.js:491`, `app/ui/web/samples.js:574`. | Il sait jouer des pads, mais pas distinguer banque enregistrée, banque utilisée et module présent sur USB. A1–A6. |
| Réglages | Apparence de l’app, langue, bref À propos. `app/ui/web/index.html:383`. | Il ne sait pas immédiatement si « Clair » modifie l’app, le RX3 ou l’aperçu. T1. |
| Téléchargement de la clé | Conditions → défilement → acceptation → tâche globale → résultat sous forme de chemin. Accessible à l’ouverture, par le bouton dédié, ou par création sans clé. `app/ui/web/app.js:621`, `app/ui/web/app.js:677`, `app/ui/web/app.js:772`. | Il attend de pouvoir préparer sa clé USB ; la sortie ne lui indique pas clairement où reprendre. K1–K8. |
| Retour à l’état d’origine | Retrait des fichiers depuis l’inspection USB ; procédure d’extinction/retrait/redémarrage dans le README, absente de ce contrôle. `app/ui/web/app.js:809`, `README.md:308`. | Il confond suppression de la clé de chiffrement, suppression des fichiers USB et arrêt des modifications en mémoire. R1. |

### Valeurs par défaut et points à conserver

| Élément vérifié | Lecture DJ et décision proposée |
|---|---|
| Langue issue du navigateur, thème système ; préférences mémorisées. `app/ui/web/i18n.js:43`, `app/ui/web/components.js:4`. | Conserver. L’app ne doit pas imposer un thème sombre parce qu’il s’agit de DJing. Corriger seulement les libellés de portée, T1. |
| Sélection reconstruite depuis les valeurs `default` à l’ouverture. `app/ui/web/app.js:586`. Beat Jump, Key Shift, Key Sync, Stems activés par leurs manifestes ; Key Match requis par Key Sync. | Conserver les décisions produit ; afficher « sélectionné pour la prochaine préparation », M1–M2. Ne pas présenter la sélection comme un relevé USB. |
| KEY SYNC harmonique, ±1 demi-ton ; règles additionnelles Key Match à zéro ; troisième colonne BPM. `app/ui/web/app.js:28`. | Conserver ; expliquer la portée des règles, M2. |
| Stems voix + instrumental, waveforms cochées sauf préférence précédente ; qualité par défaut Haute qualité, accélération auto. `app/ui/web/stems.js:21`, `app/ui/web/stems.js:407`, `app/stems/separation.py:476`. | Conserver les choix ; rendre le coût en temps lisible, S3–S4. Pas de nouvelle promesse de performance. |
| Banque nouvelle `bank1`, mode Une fois, SHIFT décoché ; valeurs de volume/niveau issues des limites. `app/ui/web/samples.js:33`, `app/ui/web/samples.js:606`, `app/ui/web/samples.js:709`. | Conserver les limites et le comportement ; mieux nommer la banque et expliciter l’activation, A3–A6. Huit emplacements visibles ne signifient pas huit lectures simultanées : la limite de voix vient de `limits.maxVoices`, `app/ui/web/samples.js:389`. |
| Logo ajusté dans sa zone, centré, aperçu sombre, inversion des gris activée ; restauration locale de l’image. `app/ui/web/logo.js:50`, `app/ui/web/logo.js:381`. | Conserver ; distinguer aperçu, préférence locale et présence sur USB, L2–L3. |
| Confirmation avant retrait, suppression de banque, suppression de clé et abandon de modifications ; focus initial sur Annuler. `app/ui/web/components.js:32`, `app/ui/web/samples.js:714`. | Conserver : le DJ garde ses sons et ne déclenche pas une suppression en tentant d’avancer. Préciser les objets concernés. |
| Export USB utilisable sans XML, samples déjà sur USB écoutables via `audioPath`, couleurs et aperçu existants. `app/ui/web/stems.js:228`, `app/ui/web/samples.js:51`, `app/ui/web/samples.js:452`. | Conserver. Ne pas reprendre comme défauts les anciennes chaînes inutilisées `samples.hearKept` ou les fonctions déjà réparées. |

## Constats — ouverture et clé USB

### O1 — Les phrases qui donnent le mode d’emploi sont invisibles

- **Où :** tous les écrans ; `app/ui/web/app.css:88`, `app/ui/web/index.html:76`, `app/ui/web/index.html:131`, `app/ui/web/index.html:207`, `app/ui/web/index.html:282`.
- **Ce que le DJ voit :** un titre et une action. Les phrases sur la durée des samples, la préparation avant le set, l’intégration du logo et les dépendances existent mais toutes les `.lede` d’en-tête sont masquées.
- **Où il décroche :** le titre « Stems » ne lui dit ni que les fichiers doivent être préparés avant le set, ni ce qui les rend disponibles sur la platine.
- **Proposition :** afficher une phrase sous chaque titre, avec hauteur d’en-tête adaptée au retour à la ligne. Conserver la phrase Stems actuelle. Pour Modules, donner le résultat visé ; déplacer l’explication des dépendances à côté des choix liés.
- **FR** (`app/localization/fr.json:46`, `modules.lede`) : « Les modules nécessaires s’activent automatiquement. » → « Choisissez les fonctions à ajouter à votre XDJ-RX3, puis préparez votre clé USB. ».
- **EN** (`app/localization/en.json:46`, `modules.lede`) : « Required modules turn on automatically. » → « Choose the features to add to your XDJ-RX3, then prepare your USB drive. ».
- **Priorité / effort : P1 · S.**

### O2 — La clé USB perd son identité dans la barre latérale

- **Où :** contrôle USB inférieur ; `app/ui/web/index.html:42`, `app/ui/web/app.js:198`, `app/ui/web/app.css:83`, `app/ui/web/app.css:288`.
- **Ce que le DJ voit :** « Clé USB sélectionnée ». Le chemin est seulement dans le survol ; pas de nom visible, ni de marque active lorsque l’inspection est ouverte (`app/ui/web/app.js:136`).
- **Où il décroche :** avec sa clé de set et sa clé de secours, il ne sait plus laquelle il prépare sans quitter son écran.
- **Proposition :** conserver ce contrôle en bas ; icône USB 16 px, nom sur la première ligne, « Voir le contenu » / « View contents » sur la seconde, fond sélectionné pendant l’inspection. Nom dérivé du chemin existant, chemin complet affichable au clavier. Ne pas afficher « prête » sur la seule preuve d’une sélection.
- **FR** (`app/localization/fr.json:421`, `ui.driveSelected`) : « Clé USB sélectionnée » → « Clé USB · {name} ».
- **EN** (`app/localization/en.json:421`, `ui.driveSelected`) : « USB drive selected » → « USB drive · {name} ».
- **Priorité / effort : P1 · S.**

### O3 — « Parcourir » ne dit pas où sélectionner la clé

- **Où :** Modules et Stems ; `app/ui/web/index.html:111`, `app/ui/web/index.html:308`, `app/ui/web/app.js:800`, `app/ui/web/app.js:833`, `app/ui/web/stems.js:443`.
- **Ce que le DJ voit :** « Destination », « aucun », puis « Parcourir », ouvrant un sélecteur de dossier. Le même mot sert aussi à choisir le fichier de chiffrement.
- **Où il décroche :** il peut sélectionner `Contents`, `PIONEER`, une playlist ou un dossier du Mac : il ne connaît pas « racine ».
- **Proposition :** libellé contextualisé de chaque bouton, sans changer globalement `common.browse`. Au-dessus du sélecteur, aide persistante **absent → FR « Pour préparer une clé USB, sélectionnez son nom, sans ouvrir de dossier à l’intérieur. » / EN « To prepare a USB drive, select the drive itself without opening a folder inside it. »**. Conserver le choix d’un dossier pour les usages existants.
- **FR** (`app/localization/fr.json:53`, `modules.output`) : « Destination » → « Clé USB ou dossier de destination ».
- **EN** (`app/localization/en.json:53`, `modules.output`) : « Write to » → « Destination USB drive or folder ».
- **FR** (`app/localization/fr.json:11`, `common.browse`) : « Parcourir » → « Choisir la destination ».
- **EN** (`app/localization/en.json:11`, `common.browse`) : « Browse » → « Choose destination ».
- **Priorité / effort : P1 · S.**

### O4 — Changer de clé n’actualise pas forcément les destinations

- **Où :** contexte partagé et Stems ; `app/ui/web/app.js:206`, `app/ui/web/app.js:671`, `app/ui/web/stems.js:470`, `app/ui/web/stems.js:218`.
- **Ce que le DJ voit :** une clé sélectionnée dans la barre latérale ; Modules et Stems conservent leurs destinations non vides. La bibliothèque Stems déjà ouverte reste aussi la précédente.
- **Où il décroche :** il sélectionne sa clé B et suppose que ses prochaines préparations iront dessus, alors que la destination peut rester A. Fait établi dans le frontend ; aucune écriture réelle testée.
- **Proposition :** ne pas écraser ses choix. Afficher près de chaque action sa **destination effective**, avec son nom en premier, chemin en détails. Quand elle diffère du contexte USB : aide locale **absent → FR « Destination : {destination}. La clé sélectionnée dans la barre latérale est {drive}. » / EN « Destination: {destination}. The USB drive selected in the sidebar is {drive}. »** et bouton existant de choix. Distinguer également **« Musique lue depuis » / « Music read from »** de **« Stems enregistrés dans » / « Stems saved to »**.
- **Priorité / effort : P1 · M.**


### O5 — L’ouverture parle de connexion à une application locale

- **Où :** initialisation ; `app/ui/web/index.html:426`, `app/ui/web/app.js:897`, `app/ui/web/app.js:921`, `app/ui/web/i18n.js:23`.
- **Ce que le DJ voit :** « Connexion au Toolkit… », puis éventuellement « Reconnecter ». Avant chargement du catalogue, l’HTML est anglais ; une erreur précoce peut même afficher un identifiant de traduction.
- **Où il décroche :** il cherche un câble RX3 ou une connexion Internet, alors que l’interface locale démarre. L’échec d’un chargement d’image utilise aussi `ui.unavailable` (`app/ui/web/logo.js:298`) et accuse toute l’application.
- **Proposition :** placer le démarrage dans un état initial stable du contenu ; pas de bandeau flottant de chargement courant. Fournir un texte de secours local FR/EN et conserver une erreur actionnable. Pour l’image : **absent → FR « Impossible d’afficher cette image. Choisissez une autre image. » / EN « Cannot display this image. Choose another image. »**.
- **FR** (`app/localization/fr.json:381`, `ui.connecting`) : « Connexion au Toolkit… » → « Ouverture de l’application… ».
- **EN** (`app/localization/en.json:381`, `ui.connecting`) : « Connecting to the toolkit... » → « Opening the app… ».
- **FR** (`app/localization/fr.json:383`, `ui.retry`) : « Reconnecter » → « Réessayer ».
- **EN** (`app/localization/en.json:383`, `ui.retry`) : « Reconnect » → « Try again ».
- **FR** (`app/localization/fr.json:382`, `ui.unavailable`) : « Le Toolkit ne répond pas. Cliquez sur Reconnecter. » → « L’application n’a pas pu terminer le chargement. Cliquez sur Réessayer. ».
- **EN** (`app/localization/en.json:382`, `ui.unavailable`) : « The Toolkit is not responding. Click Reconnect. » → « The app could not finish loading. Click Try again. ».
- **Priorité / effort : P2 · M.**

### O6 — Le rapport USB mélange fichiers présents et dernier passage sur la platine

- **Où :** inspection USB ; `app/ui/web/app.js:156`, `app/ui/web/app.js:162`, `app/ui/web/app.js:168`, `app/ui/bridge.py:344`.
- **Ce que le DJ voit :** « Mod », « Firmware », des identifiants de modules joints tels quels, puis les éléments chargés ou désactivés au dernier démarrage. Le compte de musique dépend de `music.present`, sans présentation dédiée de `music.unreadable`, pourtant disponible.
- **Où il décroche :** il peut lire les informations historiques comme un contrôle de la platine en cours ; un export illisible présenté avec des compteurs ne lui dit pas de le refaire dans rekordbox. Une liste telle que `beatjump-no-quantize` ne correspond pas aux noms qu’il a choisis.
- **Proposition :** ordre : musique et playlists → modules présents sur cette clé → banque utilisée → détails du dernier démarrage enregistré. Employer les noms localisés connus pour les modules, garder l’identifiant seulement en détail ou si inconnu. Si l’export est illisible, afficher **absent → FR « L’export rekordbox de cette clé USB ne peut pas être lu. Réexportez vos playlists depuis rekordbox, puis actualisez la clé. » / EN « The rekordbox export on this USB drive cannot be read. Export your playlists again from rekordbox, then refresh the drive. »** ; conserver les détails d’erreur. S’il est absent, conserver le message existant et indiquer le même geste d’export, sans fausse bibliothèque vide. Garder l’état lecture seule visible avec son action, vocabulaire T5.
- **FR** (`app/localization/fr.json:25`, `drive.mod`) : « Mod » → « Modules sur cette clé USB ».
- **EN** (`app/localization/en.json:25`, `drive.mod`) : « Mod » → « Modules on this USB drive ».
- **FR** (`app/localization/fr.json:30`, `drive.lastRun`) : « Chargés au dernier démarrage » → « Chargés au dernier démarrage enregistré ».
- **EN** (`app/localization/en.json:30`, `drive.lastRun`) : « Loaded at last startup » → « Loaded at the last recorded startup ».
- **FR** (`app/localization/fr.json:31`, `drive.refused`) : « Désactivés au dernier démarrage » → « Non chargés au dernier démarrage enregistré ».
- **EN** (`app/localization/en.json:31`, `drive.refused`) : « Disabled at last startup » → « Not loaded at the last recorded startup ».
- **Priorité / effort : P1 · M.**

## Constats — Modules

### M1 — Les interrupteurs ressemblent à une activation immédiate

- **Où :** liste, résumé et action principale ; `app/ui/web/app.js:317`, `app/ui/web/app.js:557`, `app/ui/web/app.js:677`, `app/ui/web/index.html:78`.
- **Ce que le DJ voit :** des interrupteurs bleus, « modules activés », puis « Créer le mod ». Les changements ne sont écrits qu’à l’action de préparation.
- **Où il décroche :** il ferme l’app en pensant avoir activé les fonctions ; ou il n’ose pas « créer un mod » sur sa platine.
- **Proposition :** conserver les interrupteurs, mais titrer le résumé **« À enregistrer sur votre clé USB » / « To save to your USB drive »** quand cette destination est choisie. Afficher la destination et la prochaine action auprès du bouton fixe. Sans destination, donner un bouton visible de choix et son motif ; ne pas laisser le seul diagnostic tout en bas du résumé. Succès : résultat contextualisé, pas seulement un nombre d’octets.
- **FR** (`app/localization/fr.json:54`, `modules.build`) : « Créer le mod » → « Préparer la clé USB ».
- **EN** (`app/localization/en.json:54`, `modules.build`) : « Build the mod » → « Prepare USB drive ».
- **FR** (`app/localization/fr.json:360`, `modules.selectedCount`) : one : « {count} module activé » ; other : « {count} modules activés » → one : « {count} module sélectionné » ; other : « {count} modules sélectionnés ».
- **EN** (`app/localization/en.json:360`, `modules.selectedCount`) : one : « {count} module on » ; other : « {count} modules on » → one : « {count} module selected » ; other : « {count} modules selected ».
- **FR** (`app/localization/fr.json:56`, `modules.built`) : « {bytes} écrits dans {path} » → « Préparation terminée dans {path}. ».
- **EN** (`app/localization/en.json:56`, `modules.built`) : « {bytes} written to {path} » → « Preparation completed in {path}. ».
- **Variante dossier :** « Préparer les fichiers » / « Prepare files ». Ne pas dire « clé USB prête » si seule une destination quelconque est connue. Le nombre d’octets reste dans les détails du résultat.
- **Priorité / effort : P1 · M.**

### M2 — Le mixage harmonique demande de lire un arbre de dépendances

- **Où :** Key Shift/Key Match/Key Sync ; `app/ui/web/app.js:331`, `app/ui/web/app.js:364`, `app/ui/web/app.js:412`, `mod/modules/key-sync/manifest.json:20`, `mod/modules/key-match/manifest.json:39`, `mod/modules/core/api/rx3_harmony.h:33` (sens des valeurs Camelot uniquement).
- **Ce que le DJ voit :** « Requis par », « Nécessite », plusieurs sous-réglages, une case verte désactivée et des règles +2/+7/+4. Key Match peut être sélectionné par Key Sync sans règle additionnelle cochée.
- **Où il décroche :** il ne sait pas s’il a activé une transposition, une indication dans BROWSE ou les deux. « Adapter la tonalité » ne dit pas à quelle référence.
- **Proposition :** montrer une phrase de fonction par module ; sous-réglages visibles seulement quand sélectionné, détails relationnels dépliables. Conserver les dépendances. Préciser le MASTER et qualifier les nombres en pas Camelot ; garder les noms Energy Boost et l’aide musicale existante. Aperçu accessible par **« Voir dans BROWSE » / « Preview in BROWSE »**, au lieu du seul « i » (`app/ui/web/app.js:254`).
- **Textes exacts :** FR « Adapter la tonalité » → « Même tonalité que le MASTER » ; EN « Match the other deck’s key » → « Match the MASTER key ». FR « Utiliser la tonalité compatible KEY MATCH la plus proche » → « Tonalité compatible la plus proche » ; EN « Use the nearest KEY MATCH key » → « Nearest compatible key ». FR/EN « Energy Boost +2 » → « Energy Boost · +2 Camelot » ; idem +7. Ne pas présenter ces nombres comme des demi-tons.
- **Priorité / effort : P2 · M.**

### M3 — « Morceau en cours » promet une utilisation inaccessible à ce persona

- **Où :** catégorie Diffusion ; `mod/modules/now-playing/manifest.json:8`, `mod/modules/now-playing/manifest.json:38`, `app/ui/web/app.js:485`, `mod/categories.json:55`.
- **Ce que le DJ voit :** un usage séduisant pour son stream, suivi d’instructions **ouvertes par défaut** : Python 3, terminal, commande, UDP, JSON, outil externe.
- **Où il décroche :** il pensait envoyer le titre à son logiciel de stream ; il doit maintenant réaliser une intégration informatique.
- **Proposition :** conserver le module et ses instructions, replier le guide technique. Mettre la limite de l’usage avant le choix dans la description, sans bannière. FR « Recevoir les informations des morceaux sur l’ordinateur » → « Configuration technique pour votre logiciel de diffusion » ; EN « Receive track information on your computer » → « Technical setup for your streaming software ».
- **Description actuelle exacte :** FR « Transmettez les titres, BPM et états ON AIR à votre ordinateur pour un overlay de stream, un écran VJ ou votre liste de morceaux. Le RX3 continue de lire votre clé USB, sans rekordbox ni PRO DJ LINK. » ; EN « Send track titles, BPM and ON AIR status to your computer for a stream overlay, VJ display or set list. The RX3 keeps playing from your USB drive, without rekordbox or PRO DJ LINK. ».
- **Description exacte proposée :** FR « Transmet les titres et BPM à un logiciel de diffusion compatible, à configurer séparément. L’affichage des titres n’est pas inclus. » / EN « Sends titles and BPM to compatible streaming software, which you configure separately. Title display is not included. » Elle remplace la description de `mod/modules/now-playing/manifest.json:8` ; conserver les précisions ON AIR, USB-B et PRO DJ LINK dans le guide. L’UI seule ne rend pas cette fonction utilisable sans compétences techniques ; ne pas inventer de bouton d’intégration.
- **Priorité / effort : P1 · S.**

### M4 — Les contrôles internes prennent le nom de composants

- **Où :** Avancé et Diagnostic ; `app/ui/web/app.js:540`, `mod/modules/core/manifest.json:4`, `mod/modules/decoder-sleep/manifest.json:4`, `mod/modules/telnet/manifest.json:4`, `mod/modules/logging/manifest.json:4`, `mod/modules/logging-verbose/manifest.json:4`.
- **Ce que le DJ voit :** Core, decoder-sleep, réveils CPU, Telnet et mot de passe root. Core non sélectionnable est néanmoins présenté dans les contrôles avancés.
- **Où il décroche :** il pense devoir choisir une pièce indispensable sans savoir à quoi elle sert.
- **Proposition :** garder Diagnostic replié ; renommer Avancé **« Composants inclus » / « Included components »** si le groupe ne contient que les composants automatiques actuels. Présenter leur inclusion comme un état, pas un choix inaccessible. Conserver les explications techniques dépliées et toutes les précautions Telnet.
- **Textes exacts :** FR/EN « Core » → « Composants communs » / « Shared components » ; FR « Attente du décodeur (decoder-sleep) » → « Reprise audio après un Beat Jump » ; EN « Decoder wait (decoder-sleep) » → « Audio recovery after a Beat Jump ». FR « Journal de session » → « Rapport de dépannage » ; EN « Session logging » → « Troubleshooting report ». Le bénéfice du décodeur reste **possible**, pas garanti ; chiffres techniques dans les détails.
- **Priorité / effort : P2 · S.**

### M5 — La compatibilité ne dit pas comment lire la version de sa platine

- **Où :** résumé Modules ; `app/ui/web/index.html:90`, `app/ui/web/app.js:759`, `README.md:102`.
- **Ce que le DJ voit :** « Compatibilité RX3 » puis « 1.19 / 1.20 ». Ce sont les versions proposées par le logiciel, pas une détection de son RX3.
- **Où il décroche :** il ignore sa version ou croit la platine déjà vérifiée par l’app.
- **Proposition :** conserver la liste actuelle, ajouter une aide dépliable locale **absent → FR « Voir la version sur la platine » / EN « Find the version on your deck »**. Reprendre le geste du README : clé USB retirée, platine allumée, maintien de **MENU (UTILITY)** une seconde, version en bas du menu. Ne pas ajouter un faux indicateur de détection matérielle.
- **FR** (`app/localization/fr.json:48`, `modules.firmware`) : « Compatibilité RX3 » → « Versions compatibles du XDJ-RX3 ».
- **EN** (`app/localization/en.json:48`, `modules.firmware`) : « RX3 compatibility » → « Compatible XDJ-RX3 versions ».
- **Priorité / effort : P1 · S.**

## Constats — Stems, préparation et panneau d’écoute

### S1 — L’installation nécessaire se trouve après les réglages

- **Où :** bas de Stems ; `app/ui/web/index.html:364`, `app/ui/web/stems.js:52`, `app/ui/web/stems.js:203`, `app/stems/provisioning.py:342`.
- **Ce que le DJ voit :** « Préparer les stems » désactivé, puis « Moteur de séparation et cache » plus bas. Le dépliant s’ouvre automatiquement si nécessaire : il n’est donc pas fermé, mais reste après tout le contenu précédent. Le résumé peut être l’anglais brut « Missing: audio-separator and FFmpeg. Install the separation runtime to continue. ».
- **Où il décroche :** il ne sait pas quelle installation débloque son bouton ni où la trouver.
- **Proposition :** remonter le groupe existant avant Musique lorsque non prêt ; garder en bas les réglages techniques et le stockage une fois prêt. Présenter un texte local d’état et conserver le message brut dans les détails.
- **FR** (`app/localization/fr.json:405`, `ui.runtimeSettings`) : « Moteur de séparation et cache » → « Installation et stockage des stems ».
- **EN** (`app/localization/en.json:405`, `ui.runtimeSettings`) : « Separation engine and cache » → « Stem setup and storage ».
- **FR** (`app/localization/fr.json:150`, `stems.install`) : « Installer le moteur » → « Installer les outils de préparation ».
- **EN** (`app/localization/en.json:148`, `stems.install`) : « Install engine » → « Install stem preparation tools ».
- **FR** (`app/localization/fr.json:168`, `stems.needRuntime`) : « Ouvrez Moteur de séparation et cache, puis cliquez sur Installer le moteur. » → « Installez les outils de préparation pour créer vos stems sur cet ordinateur. ».
- **EN** (`app/localization/en.json:166`, `stems.needRuntime`) : « Open Separation engine and cache, then click Install engine. » → « Install the preparation tools to create stems on this computer. ».
- **Limite :** l’absence de Python peut réellement bloquer l’installation (`app/stems/provisioning.py:550`). Présenter la nécessité de Python et l’action existante, sans prétendre l’installer automatiquement. FR brut identique à EN « No Python … interpreter with the venv module was found. … » → FR « Python {versions} est nécessaire pour installer les outils de préparation. Installez cette version de Python, puis réessayez. » / EN « Python {versions} is required to install the preparation tools. Install this Python version, then try again. » Détails d’origine conservés ; pas d’évolution d’installation proposée.
- **Priorité / effort : P1 · M.**

### S2 — XML concurrence le parcours USB que le DJ connaît

- **Où :** Musique ; `app/ui/web/index.html:290`, `app/ui/web/stems.js:228`, `app/ui/web/stems.js:434`.
- **Ce que le DJ voit :** une aide qui commence par XML, deux boutons de même poids, un chemin et un compte de morceaux.
- **Où il décroche :** il retourne dans rekordbox chercher un nouvel export alors que sa clé contient déjà ce qu’il faut.
- **Proposition :** mettre « Ouvrir une clé USB » en premier visuellement et dans le texte ; placer XML dans un dépliant **« Autre source musicale » / « Other music source »**. Conserver l’opération. Afficher nom de la source, nombre de morceaux et playlist avant le chemin technique.
- **FR** (`app/localization/fr.json:153`, `stems.musicHint`) : « Ouvrez un export XML rekordbox ou une clé USB contenant un export rekordbox. » → « Ouvrez la clé USB sur laquelle vous avez exporté vos playlists rekordbox. ».
- **EN** (`app/localization/en.json:151`, `stems.musicHint`) : « Open a rekordbox XML export or a USB drive containing a rekordbox export. » → « Open the USB drive you exported your rekordbox playlists to. ».
- **FR** (`app/localization/fr.json:155`, `stems.fromExport`) : « Ouvrir un export XML » → « Choisir un export XML rekordbox ».
- **EN** (`app/localization/en.json:153`, `stems.fromExport`) : « Open XML export » → « Choose a rekordbox XML export ».
- **Priorité / effort : P2 · S.**

### S3 — Les détails par morceau repoussent les choix de préparation

- **Où :** bibliothèque et zone de préparation ; `app/ui/web/stems.js:163`, `app/ui/web/stems.js:287`, `app/ui/web/index.html:313`, `app/ui/web/index.html:321`, `app/ui/web/index.html:327`.
- **Ce que le DJ voit :** une ligne de capacité par morceau, puis les états de waveforms par morceau, avant les parties et la qualité. Les listes ne sont pas bornées dans le frontend.
- **Où il décroche :** avec une longue playlist, il parcourt une succession de « le RX3 peut les charger » pour atteindre le choix voix/batterie. Risque déduit de l’ordre DOM, pas mesure de défilement réelle.
- **Proposition :** ordre : source/playlist → parties → qualité → option de forme d’onde → durée et destination. Présenter en premier le nombre de morceaux concernés par un refus ou une limite ; replier les détails des morceaux compatibles dans **« Voir les détails des morceaux » / « Show track details »**. Garder les refus et leurs actions visibles ; ne pas changer les limites ni la sélection.
- **FR** (`app/localization/fr.json:463`, `stems.waveOption`) : « Calculer les waveforms des stems » → « Préparer aussi les formes d’onde des stems ».
- **EN** (`app/localization/en.json:463`, `stems.waveOption`) : « Calculate stem waveforms » → « Also prepare stem waveforms ».
- **FR** (`app/localization/fr.json:464`, `stems.waveOptionHelp`) : « La waveform s’adapte aux stems activés. Rallonge le délai de préparation des stems. Les waveforms peuvent être calculées plus tard. » → « Sur la platine, la forme d’onde suivra les stems activés. Cette option ajoute du temps de préparation ; vous pouvez la lancer plus tard. ».
- **EN** (`app/localization/en.json:464`, `stems.waveOptionHelp`) : « Show waveforms for the active stems. Adds preparation time. You can calculate the waveforms later. » → « On the deck, the waveform will follow the active stems. This adds preparation time; you can run it later. ».
- **Priorité / effort : P2 · M.**

### S4 — La qualité est expliquée avec la méthode de calcul

- **Où :** Qualité et vitesse, installation ; `app/ui/web/stems.js:73`, `app/ui/web/stems.js:63`, `app/localization/fr.json:458`, `app/localization/en.json:458`, `app/localization/fr.json:229`, `app/localization/en.json:227`.
- **Ce que le DJ voit :** « quatre passes décalées », modèle spécialisé, 17,6 kHz ; dans l’installation, CPU, Metal, CUDA, ROCm, DirectML.
- **Où il décroche :** il sait juger une voix propre mais pas choisir une bibliothèque de calcul. Le nom « Normale » ne lui dit pas si cette qualité convient à un set.
- **Proposition :** conserver les presets, leurs valeurs et Haute qualité par défaut. Afficher le compromis musical en première phrase, conserver les restrictions de bande passante et détails du modèle dans un dépliant. Montrer Automatique comme choix normal ; conserver les accélérateurs dans les réglages avancés, renommés selon le matériel.
- **FR** (`app/localization/fr.json:230`, `quality.normal.name`) : « Normale » → « Équilibrée ».
- **EN** (`app/localization/en.json:228`, `quality.normal.name`) : « Normal » → « Balanced ».
- **FR** (`app/localization/fr.json:458`, `quality.quality.drums`) : « Voix et batterie : modèle spécialisé lorsqu’il est disponible, avec quatre passes décalées. Traitement plus long. » → « Voix et batterie : préparation plus longue, avec davantage de traitement. Écoutez le résultat avant votre set. ».
- **EN** (`app/localization/en.json:458`, `quality.quality.drums`) : « Vocals and drums: fine-tuned model when available, with four shifted passes. Takes longer. » → « Vocals and drums: longer preparation with more processing. Listen to the result before your set. ».
- **FR** (`app/localization/fr.json:459`, `quality.normal.drums`) : « Voix et batterie : deux passes décalées. » → « Voix et batterie : compromis entre temps de préparation et traitement. ».
- **EN** (`app/localization/en.json:459`, `quality.normal.drums`) : « Vocals and drums: two shifted passes. » → « Vocals and drums: a balance between preparation time and processing. ».
- **FR** (`app/localization/fr.json:460`, `quality.quick.drums`) : « Voix et batterie : une seule passe. » → « Voix et batterie : préparation avec le moins de traitement. ».
- **EN** (`app/localization/en.json:460`, `quality.quick.drums`) : « Vocals and drums: one pass. » → « Vocals and drums: preparation with the least processing. ».
- **Priorité / effort : P2 · S.**

### S5 — Écouter les stems préparés ressemble à une opération d’import

- **Où :** sous-vues et écoute ; `app/ui/web/index.html:317`, `app/ui/web/index.html:348`, `app/ui/web/index.html:362`, `app/ui/web/stems.js:42`, `app/ui/web/stems.js:234`, `app/ui/web/stems.js:404`.
- **Ce que le DJ voit :** Préparation et Import et écoute. Le panneau d’écoute est enfant de la deuxième vue, sous deux emplacements de fichiers d’import. Après préparation, seule la liste des formes d’onde est actualisée par ce gestionnaire.
- **Où il décroche :** « je les ai déjà préparés, pourquoi faudrait-il les importer ? » Il risque de choisir des fichiers inutiles pour simplement vérifier une voix.
- **Proposition :** donner au panneau d’écoute une place commune après les résultats, avec morceau associé au-dessus. L’import garde son bloc distinct. Ajouter un lien « Écouter les stems » / « Listen to stems » depuis le résultat ; utiliser les opérations d’écoute et de rafraîchissement existantes.
- **FR** (`app/localization/fr.json:407`, `ui.importView`) : « Import et écoute » → « Importer des stems existants ».
- **EN** (`app/localization/en.json:407`, `ui.importView`) : « Import & listen » → « Import existing stems ».
- **FR** (`app/localization/fr.json:314`, `stems.importTitle`) : « Import manuel de stems » → « Associer vos fichiers de stems ».
- **EN** (`app/localization/en.json:314`, `stems.importTitle`) : « Manual stem import » → « Match your stem files ».
- **Priorité / effort : P1 · M.**

### S6 — Le panneau d’écoute ne reprend pas les repères de jeu

- **Où :** transport d’écoute ; `app/ui/web/stems-listen.js:10`, `app/ui/web/stems-listen.js:43`, `app/ui/web/stems-listen.js:147`, `app/ui/web/app.css:138`, `app/ui/web/app.css:279`.
- **Ce que le DJ voit :** À destination/Importés, Original/INST/VOCAL/DRUMS dans des groupes visuellement semblables ; Original et les rôles peuvent paraître pressés simultanément. Temps en secondes décimales. Les rôles n’ont pas leurs couleurs de platine.
- **Où il décroche :** il ne sait pas si toucher VOCAL isole ou coupe la voix ; 245,32 secondes demande une conversion mentale en durée musicale.
- **Proposition :** séparer le choix de source des commandes de stems et du bouton Original. Ajouter une phrase **absent → FR « Les stems allumés sont audibles. Touchez un stem pour le couper ou le réactiver. » / EN « Lit stems are audible. Tap a stem to mute or enable it. »** ; rouge INST, vert VOCAL, bleu DRUMS, texte conservé et état éteint lisible. Afficher le temps en `mm:ss`, sans changer la précision du lecteur. Nom du morceau au-dessus du transport.
- **FR** (`app/localization/fr.json:347`, `stems.listenDrive`) : « À destination » → « Stems enregistrés ».
- **EN** (`app/localization/en.json:347`, `stems.listenDrive`) : « At destination » → « Saved stems ».
- **FR** (`app/localization/fr.json:348`, `stems.listenImported`) : « Importés » → « Fichiers choisis ».
- **EN** (`app/localization/en.json:348`, `stems.listenImported`) : « Imported » → « Selected files ».
- **Priorité / effort : P2 · M.**

### S7 — L’import demande au DJ de comprendre un compte rendu DSP

- **Où :** import manuel ; `app/ui/web/stems.js:356`, `app/ui/web/stems.js:388`, `app/localization/fr.json:320`, `app/localization/fr.json:324`, `app/localization/fr.json:326`, `app/localization/fr.json:333`, `app/localization/fr.json:334` ; clés identiques dans EN aux mêmes lignes.
- **Ce que le DJ voit :** gain estimé avant même d’avoir importé, trames retirées, corrélation, énergie résiduelle et décalage d’encodeur.
- **Où il décroche :** il veut savoir si sa voix est au bon endroit dans le morceau ; il n’a aucun seuil métier pour interpréter ces nombres.
- **Proposition :** garder voix obligatoire et batterie facultative explicites dans les emplacements. Premier résultat : disponibilité de l’écoute et éventuelle action corrective ; détails techniques dépliables conservés tels quels, sans revendiquer de certification. Ne pas convertir un avertissement en réussite.
- **FR** (`app/localization/fr.json:320`, `stems.importHeuristic`) : « Le gain est une estimation. Aucune correction de gain n'est appliquée. Écoutez l'instrumental reconstitué avant de l'utiliser. » → « Écoutez l’instrumental pour vérifier le résultat. Le volume de vos fichiers n’est pas corrigé. ».
- **EN** (`app/localization/en.json:320`, `stems.importHeuristic`) : « The gain is an estimate. No gain correction is applied. Listen to the rebuilt instrumental before using it. » → « Listen to the instrumental to check the result. Your file levels are not corrected. ».
- **FR** (`app/localization/fr.json:324`, `stems.importShort`) : « Le stem est plus court que le mix non tronqué. Réexportez le morceau complet, décalage de l'encodeur compris. » → « Le stem ne couvre pas tout le morceau. Réexportez-le avec le même début et la même fin que le morceau original. ».
- **EN** (`app/localization/en.json:324`, `stems.importShort`) : « Stem is shorter than the untrimmed mix. Re-export the complete track including encoder padding. » → « The stem does not cover the whole track. Export it again with the same start and end as the original track. ».
- **FR** (`app/localization/fr.json:326`, `stems.importAlignment`) : « Calage audio incertain. Corrélation : {correlation}. Réexportez le stem avec les points de début et de fin du morceau original, sans traitement supplémentaire. » → « Le calage de ce stem avec le morceau est incertain. Réexportez-le avec le même début et la même fin, sans traitement supplémentaire. ».
- **EN** (`app/localization/en.json:326`, `stems.importAlignment`) : « Audio alignment is uncertain. Correlation: {correlation}. Export the stem with the original track's start and end points, without additional processing. » → « This stem may not line up with the track. Export it again with the same start and end, without additional processing. ».
- **Détails conservés :** valeur `{correlation}`, particularité de l’encodeur, mesures de `{ms}`, `{head}`, `{tail}`, `{gain}` et `{ratio}` restent accessibles ; la proposition sépare le message lisible des données, elle ne les retire pas.
- **Priorité / effort : P2 · M.**

### S8 — Certaines instructions désignent des contrôles qui n’existent plus

- **Où :** avertissements Stems et KEY SYNC ; `app/ui/web/stems.js:109`, `app/localization/fr.json:434`, `app/localization/fr.json:377`, `app/localization/en.json:434`, `app/localization/en.json:377`, `mod/modules/key-sync/manifest.json:49`.
- **Ce que le DJ voit :** « Décochez Batterie » alors que l’interface propose deux boutons Voix + instrumental / Voix + batterie + instrumental. L’erreur KEY SYNC cite « Trouve… » et deux intitulés absents du sélecteur.
- **Où il décroche :** il cherche une case inexistante et relit inutilement l’écran.
- **Proposition :** aligner tous les renvois sur les intitulés visibles finaux, y compris après S1 et S5. Aucun changement de capacité.
- **FR** (`app/localization/fr.json:434`, `stems.drumsModelImport`) : « Aucune qualité disponible sur cet ordinateur ne sépare la batterie. Décochez Batterie, ou importez une piste de batterie dans Import et écoute. » → « Cet ordinateur ne peut pas préparer la batterie avec les qualités disponibles. Choisissez Voix + instrumental, ou importez un fichier de batterie. ».
- **EN** (`app/localization/en.json:434`, `stems.drumsModelImport`) : « No quality on this computer separates drums. Uncheck Drums, or import a drums stem in Import & listen. » → « This computer cannot prepare drums with the available quality settings. Choose Vocals + instrumental, or import a drums file. ».
- **FR** (`app/localization/fr.json:377`, `error.keySyncMode`) : « Choisissez « Aligner sur le morceau en cours » ou « Trouve la tonalité compatible la plus proche ». » → « Choisissez « Même tonalité que le MASTER » ou « Tonalité compatible la plus proche ». ».
- **EN** (`app/localization/en.json:377`, `error.keySyncMode`) : « Choose Match the playing track or Find the nearest compatible key. » → « Choose Match the MASTER key or Nearest compatible key. ».
- **Priorité / effort : P1 · S.**

### S9 — La fin d’une préparation ne distingue pas assez résultat global et exceptions

- **Où :** barre de tâche ; `app/ui/web/app.js:698`, `app/ui/web/app.js:741`, `app/ui/web/app.css:238`, `app/ui/web/app.css:240`, `app/localization/fr.json:450`.
- **Ce que le DJ voit :** « Terminé », une barre remplie et éventuellement une longue liste d’erreurs dans une zone de 96 px de hauteur maximale. Les messages par morceau et les notices partagent cette zone.
- **Où il décroche :** il comprend « tout est prêt » avant de découvrir qu’un morceau important a échoué. Annulé reçoit aussi une barre à 100 % (`app/ui/web/app.js:729`).
- **Proposition :** titre composé à partir des comptes déjà fournis : **absent → FR « {ready} morceaux prêts · {failed} à vérifier » / EN « {ready} tracks ready · {failed} to check »**, avec variantes singulières. Détails repliables sous ce bilan ; action d’écoute adjacente. Annulation : remplacer la barre pleine par le libellé de fin d’opération, sans inventer de pourcentage de préparation. Pour les longues tâches, conserver la progression globale et le morceau courant ; ne pas afficher une durée restante non calculée.
- **Priorité / effort : P1 · M.**

### S10 — Apprendre les gestes demande de quitter Stems et les consignes se contredisent

- **Où :** guide Modules, aperçus, README ; `app/ui/web/app.js:453`, `app/ui/web/rx3-mock.js:301`, `app/ui/web/rx3-mock.js:330`, `app/ui/web/rx3-mock.js:392`, `mod/modules/stems/manifest.json:70`, `README.md:298`, `.claude/STYLE.md:42`.
- **Ce que le DJ voit :** guide accessible dans Modules, animation cyclique ; README : batterie 5, basse 6, instrumental 7, voix 8 ; guide actuel : instrumental 5, voix 6, batterie 7. Le glossaire comporte encore une mention stems 7/8 avec TODO.
- **Où il décroche :** il apprend deux gestes incompatibles pour couper la voix. Aucune validation matérielle dans cet audit ne tranche lequel reflète la platine actuelle.
- **Proposition :** réutiliser le guide dans Stems sous **« Sur votre XDJ-RX3 » / « On your XDJ-RX3 »**. À côté de l’animation, afficher en permanence le geste tactile déjà décrit : FR « Touchez un stem pour le couper ou le réactiver. Maintenez puis glissez pour régler son volume. » / EN « Tap a stem to mute or enable it. Hold, then drag to adjust its volume. ». Ces textes restent inchangés ; déplacer leur visibilité, actuellement essentiellement portée par l’accessibilité. Ajouter des étapes manuelles précédent/suivant ou une image fixe légendée pour éviter d’attendre une boucle.
- **Limite de preuve :** avant de publier une instruction numérotée unique, aligner README, glossaire et guide sur la référence matérielle validée. Ne pas ajouter la basse ni choisir arbitrairement un numéro de pad. L’unification documentaire est recommandée, pas effectuée.
- **Priorité / effort : P1 · M.**


## Constats — Logo

### L1 — L’état vide invite déjà à régler une image absente

- **Où :** Logo ; `app/ui/web/index.html:214`, `app/ui/web/index.html:229`, `app/ui/web/logo.js:117`, `app/ui/web/logo.js:381`.
- **Ce que le DJ voit :** un aperçu DJ LOGO et les réglages de zone, zoom et cadrage, alors qu’aucune image n’a encore été choisie.
- **Où il décroche :** il manipule le zoom sans résultat et ne sait pas s’il règle le logo de démonstration ou son futur logo.
- **Proposition :** avant choix, conserver l’aperçu et « Choisir une image » ; présenter le groupe de cadrage désactivé avec son motif, ou ne le révéler qu’après choix. Garder les choix utiles de zone accessibles après sélection. Texte actuel conservé : FR « Choisissez une image pour cadrer votre logo. » / EN « Choose an image to frame your logo. ». Aucun disclaimer d’aperçu.
- **Priorité / effort : P2 · S.**

### L2 — Le bouton dominant reste « Remplacer l’image » quand le travail est fini

- **Où :** Logo, notes et liaison Modules ; `app/ui/web/index.html:209`, `app/ui/web/index.html:273`, `app/ui/web/logo.js:133`, `app/ui/web/logo.js:295`, `app/ui/web/logo.js:205`.
- **Ce que le DJ voit :** son logo cadré, « Remplacer l’image » en haut ; l’action Activer Logo est dans les notes et le lien Modules en bas. L’image est mémorisée sur l’ordinateur, pas écrite sur USB par le cadrage.
- **Où il décroche :** il estime le travail terminé et retire sa clé sans avoir préparé les fichiers.
- **Proposition :** après sélection, conserver Remplacer l’image comme action secondaire. En tête, afficher l’action de navigation **« Continuer dans Modules » / « Continue in Modules »**, puis l’état de sélection du module. Cette action ne déclenche aucune écriture. Garder Activer Logo adjacent si nécessaire.
- **FR** (`app/localization/fr.json:141`, `logo.buildHint`) : « Dans Modules, activez Logo, puis cliquez sur Créer le mod. » → « Votre logo est prêt à être intégré. Dans Modules, sélectionnez Logo, puis préparez votre clé USB. ».
- **EN** (`app/localization/en.json:139`, `logo.buildHint`) : « In Modules, enable Logo, then click Build the mod. » → « Your logo is ready to include. In Modules, select Logo, then prepare your USB drive. ».
- **FR** (`app/localization/fr.json:375`, `logo.tick`) : « Activer Logo » → « Sélectionner Logo ».
- **EN** (`app/localization/en.json:375`, `logo.tick`) : « Enable Logo » → « Select Logo ».
- **Priorité / effort : P1 · S.**

### L3 — Cadrer son logo demande de lire des dimensions et de maîtriser la molette

- **Où :** zones, notes, zoom ; `app/ui/web/logo.js:124`, `app/ui/web/logo.js:303`, `app/ui/web/logo.js:260`, `app/ui/web/index.html:245`, `app/ui/web/app.css:294`.
- **Ce que le DJ voit :** « Classique », « Pleine largeur », des tailles en pixels, un multiplicateur de zoom à deux décimales ; la molette change le cadrage dans l’aperçu. À 1180 px, la règle CSS limite l’aperçu à 440 px et place les réglages dessous.
- **Où il décroche :** il veut voir si son nom de DJ tient dans la zone ; les nombres ne l’aident pas. En défilant vers les réglages, il peut zoomer par inadvertance.
- **Proposition :** deux petites silhouettes de zone centrale sous les choix ; dimensions dans un dépliant, pas dans les boutons. Conserver le curseur Zoom et le déplacement direct ; réserver la molette au défilement tant que l’aperçu n’a pas explicitement le focus. Garder Recentrer visible près du curseur. Sous l’inversion, conserver l’explication sur les blancs/gris ; ne pas promettre d’inverser toutes les couleurs.
- **FR** (`app/localization/fr.json:372`, `logo.pane.classic`) : « Classique » → « Zone centrale ».
- **EN** (`app/localization/en.json:372`, `logo.pane.classic`) : « Classic » → « Centre area ».
- **FR** (`app/localization/fr.json:133`, `logo.fit`) : « Ajuster l’image » → « Afficher l’image entière ».
- **EN** (`app/localization/en.json:131`, `logo.fit`) : « Fit image » → « Show the whole image ».
- **FR** (`app/localization/fr.json:134`, `logo.fill`) : « Remplir la zone » → « Remplir la zone, en recadrant ».
- **EN** (`app/localization/en.json:132`, `logo.fill`) : « Fill area » → « Fill the area and crop ».
- **FR** (`app/localization/fr.json:129`, `logo.frameHint`) : « Faites glisser le logo pour le déplacer. Faites défiler sur l’aperçu pour zoomer. » → « Faites glisser le logo pour le déplacer. Réglez sa taille avec Zoom. ».
- **EN** (`app/localization/en.json:127`, `logo.frameHint`) : « Drag the logo to move it. Scroll over the preview to zoom. » → « Drag the logo to move it. Use Zoom to adjust its size. ».
- **Priorité / effort : P2 · M.**

## Constats — Samples

### A1 — Le clic sur un pad peut modifier un inspecteur hors écran

- **Où :** grille et inspecteur ; `app/ui/web/index.html:165`, `app/ui/web/index.html:190`, `app/ui/web/app.css:265`, `app/ui/web/samples.js:138`.
- **Ce que le DJ voit :** grille puis réglages globaux, avec l’inspecteur en dessous dès 1190 px ; la fenêtre par défaut fait 1180 px. Un clic sélectionne un pad sans amener l’inspecteur en vue.
- **Où il décroche :** il clique « Ajouter un sample » dans une case vide, mais ce clic sélectionne seulement le pad ; le vrai bouton est plus bas.
- **Proposition :** dans la disposition empilée, rapprocher l’inspecteur directement de la grille et le rendre visible après sélection d’un pad vide. Garder le titre « Pad {index} » et sa couleur pendant l’édition. Déplacer volume de banque et SHIFT après l’éditeur, avec le reste des réglages de banque. À largeur suffisante, garder la disposition côte à côte.
- **FR** (`app/localization/fr.json:65`, `samples.addSound`) : « Ajouter un sample » → « Ajouter un sample ».
- **EN** (`app/localization/en.json:65`, `samples.addSound`) : « Add a sample » → « Add a sample ».
- **Texte inchangé, action clarifiée :** le lien visuel de la case doit mener directement au contrôle d’ajout correspondant ; le clic d’un pad rempli conserve sa fonction de sélection. Aucune modification audio.
- **Priorité / effort : P1 · M.**

### A2 — Après ajout, la sélection passe au pad suivant

- **Où :** ajout d’un ou plusieurs samples ; `app/ui/web/samples.js:534`, `app/ui/web/samples.js:560`.
- **Ce que le DJ voit :** il ajoute un son au pad 1, puis l’inspecteur montre le pad 2 lorsque celui-ci existe. Le code avance après chaque fichier et sélectionne l’emplacement suivant.
- **Où il décroche :** il pense que l’import a échoué, ou règle la couleur du mauvais pad.
- **Proposition :** après ajout simple, garder sélectionné le pad rempli ; après ajout multiple, sélectionner le premier pad rempli et signaler la plage dans l’éditeur. Texte nouveau **absent → FR « Samples ajoutés aux pads {first} à {last}. » / EN « Samples added to pads {first}–{last}. »** ; variante singulière. Garder le nombre d’emplacements fourni par les limites.
- **Priorité / effort : P1 · S.**

### A3 — « Enregistrée » ne signifie pas « utilisée sur la platine »

- **Où :** banque, sélecteur et activation ; `app/ui/web/samples.js:491`, `app/ui/web/samples.js:518`, `app/ui/web/samples.js:574`, `app/ui/web/index.html:153`.
- **Ce que le DJ voit :** badge Enregistrée, un astérisque dans le sélecteur et Activer la banque parfois désactivé. Une nouvelle banque n’est pas activée automatiquement si une autre est déjà active.
- **Où il décroche :** il prépare sa banque de set, la sauvegarde, puis retrouve l’ancienne sur la platine.
- **Proposition :** deux informations distinctes : sauvegarde et banque utilisée. Remplacer ` *` par **« — utilisée sur la platine » / « — used on the deck »** dans le sélecteur, et montrer cette banque près du bouton d’enregistrement. Si une autre banque est active, dire son nom ; garder l’activation explicite existante. Si des modifications empêchent l’activation, en donner la raison adjacente.
- **FR** (`app/localization/fr.json:113`, `samples.makeActive`) : « Activer la banque » → « Utiliser cette banque sur la platine ».
- **EN** (`app/localization/en.json:111`, `samples.makeActive`) : « Activate bank » → « Use this bank on the deck ».
- **FR** (`app/localization/fr.json:115`, `samples.clean`) : « Enregistrée » → « Enregistrée sur la clé USB ».
- **EN** (`app/localization/en.json:113`, `samples.clean`) : « Saved » → « Saved to USB drive ».
- **FR** (`app/localization/fr.json:106`, `samples.bankHint`) : « Une clé USB peut contenir plusieurs banques de samples. Le RX3 charge la banque de samples active. » → « Vous pouvez enregistrer plusieurs banques sur la clé USB. La platine utilise une seule banque à la fois. ».
- **EN** (`app/localization/en.json:104`, `samples.bankHint`) : « A USB drive can hold several sample banks. The RX3 loads the active sample bank. » → « You can save several banks to the USB drive. The deck uses one bank at a time. ».
- **Priorité / effort : P1 · S.**

### A4 — Enregistrer des samples n’explique pas comment les rendre jouables

- **Où :** Samples et module Samples ; `app/ui/web/samples.js:574`, `app/ui/web/samples.js:694`, `app/ui/web/app.js:453`, `mod/modules/samples/manifest.json:15`, `app/ui/web/index.html:187`.
- **Ce que le DJ voit :** enregistrement réussi et instruction SLIP LOOP. Le module Samples est désactivé par défaut ; cet écran ne propose pas l’équivalent du bouton Activer Logo.
- **Où il décroche :** il a bien enregistré sa banque, mais peut n’avoir jamais préparé le module correspondant sur la clé.
- **Proposition :** sous l’état de banque, montrer séparément la présence du module rapportée par la clé et la sélection pour la prochaine préparation. Si nécessaire, fournir un lien vers le module dans Modules, puis laisser l’écriture à son action explicite. Texte nouveau **absent → FR « Banque enregistrée. Pour jouer vos samples, sélectionnez Samples dans Modules, puis préparez cette clé USB. » / EN « Bank saved. To play your samples, select Samples in Modules, then prepare this USB drive. »** uniquement lorsque l’étape manque ou reste inconnue. Ne pas affirmer qu’un module sélectionné est déjà installé. Conserver SLIP LOOP et la protection des hot cues dans l’aide existante.
- **Priorité / effort : P1 · S.**

### A5 — Une case à cocher change le sens du clic sur toute la grille

- **Où :** test des pads ; `app/ui/web/index.html:172`, `app/ui/web/samples.js:138`, `app/ui/web/samples.js:626`, `app/ui/web/app.css:187`.
- **Ce que le DJ voit :** « Tester les pads » ; selon cette case, le même pad sélectionne un son ou le joue. Les couleurs choisies ne sont indiquées que par une petite pastille ; la sélection et la lecture emploient l’accent bleu générique.
- **Où il décroche :** il veut régler un pad, mais déclenche un son, ou clique pour écouter et ouvre l’éditeur. La petite pastille n’évoque pas ses pads éclairés.
- **Proposition :** présenter les deux modes existants comme deux choix exclusifs **absent → FR « Modifier les pads » / « Jouer les pads » ; EN « Edit pads » / « Play pads »**. Utiliser la couleur du sample pour le liseré et l’état joué, avec une indication textuelle de lecture ; garder la sélection d’édition distincte. Afficher Tout arrêter près de la grille. Conserver la limite de voix et les modes de lecture existants.
- **FR** (`app/localization/fr.json:92`, `samples.simulateHint`) : « Activez pour jouer à la souris ou avec les touches 1 à 8. Échap arrête tous les samples. Désactivez pour modifier les pads. L’écoute reprend vos réglages sur cet ordinateur, sans simuler le traitement audio du RX3. » → « Jouez avec la souris ou les touches 1 à 8. Échap arrête tous les samples. Revenez à Modifier les pads pour changer vos sons. ».
- **EN** (`app/localization/en.json:91`, `samples.simulateHint`) : « Enable to play with the mouse or keys 1–8. Esc stops all samples. Disable to edit. Uses your playback settings on this computer, without simulating RX3 audio processing. » → « Play with the mouse or keys 1–8. Esc stops all samples. Return to Edit pads to change your sounds. ».
- **Priorité / effort : P2 · M.**

### A6 — Les réglages simples sont encombrés par les réglages secondaires

- **Où :** inspecteur, nom de banque, volume ; `app/ui/web/samples.js:181`, `app/ui/web/samples.js:310`, `app/ui/web/samples.js:606`, `app/ui/web/index.html:178`.
- **Ce que le DJ voit :** nom et couleur avant l’extrait et l’écoute ; deux niveaux de volume ; `bank1` comme nom initial ; champs Début/Durée précis au centième de seconde.
- **Où il décroche :** pour choisir huit secondes d’un jingle, il doit d’abord comprendre tout l’inspecteur ; « initial » n’indique pas quand ce volume sera utilisé.
- **Proposition :** ordre inspecteur : son → extrait et écoute côte à côte → mode de lecture → nom/couleur → niveau. Conserver les champs numériques et leurs limites ; pas de nouvelle analyse audio ni de waveform à produire. Ajouter une aide **absent → FR « Début de l’extrait dans le fichier » / EN « Excerpt start in the file »**. Nom nouveau `bank1` → `Banque-1` en FR / `Bank-1` en EN, respectant les restrictions actuelles ; ne pas renommer les banques existantes. Unité % visible pour le volume global comme pour le niveau du pad.
- **FR** (`app/localization/fr.json:110`, `samples.volume`) : « Volume initial de la banque » → « Volume au chargement de la banque ».
- **EN** (`app/localization/en.json:108`, `samples.volume`) : « Initial bank volume » → « Volume when the bank loads ».
- **FR** (`app/localization/fr.json:76`, `samples.modeHold`) : « Maintenu » → « Pendant l’appui ».
- **EN** (`app/localization/en.json:76`, `samples.modeHold`) : « While held » → « While held ».
- **Priorité / effort : P2 · S.**

## Parcours critique — obtenir la clé de chiffrement de la platine

Le besoin utilisateur est bien celui nommé « clé de déchiffrement » dans le brief. Le vocabulaire officiel de l’application reste **encryption key / clé de chiffrement**, conformément à `.claude/STYLE.md:19`. Ce fichier n’est pas une clé USB et ce parcours ne lit pas un secret directement depuis une platine branchée. Le code prévoit des archives publiées par le constructeur (`app/firmware/key_source.json:2`) ; leur disponibilité réseau n’a pas été vérifiée et aucun téléchargement n’a été lancé.

### Chemin complet et embranchements

| Situation | État et action actuels vérifiés | Point à rendre évident pour le DJ |
|---|---|---|
| Aucune clé au démarrage | `boot()` appelle `openTerms()` si la zone de tâche est cachée. `app/ui/web/app.js:767`. | Pourquoi ce téléchargement précède son travail ; possibilité de le faire plus tard. K1. |
| Clé absente dans Modules | Chemin « aucun », Obtenir la clé de chiffrement, Parcourir ; note de taille. `app/ui/web/app.js:604`. | Une seule action courante ; ce n’est pas un choix de clé USB. K2, K8. |
| Préparer avec une destination mais sans clé | Le bouton peut être actif ; `startBuild()` ouvre les conditions et s’arrête là. `app/ui/web/app.js:574`, `app/ui/web/app.js:678`. | Le bouton ne prépare pas encore les fichiers ; première préparation à expliquer. K1, K7. |
| Clé déjà trouvée | Chemin rempli, téléchargement masqué. Suppression proposée seulement pour la clé conservée par l’application. `app/ui/web/app.js:604`. | État prêt, aucune nouvelle récupération nécessaire. K8. |
| Fichier choisi manuellement | Choix d’un fichier existant ; `setKey()` met son chemin à l’écran. `app/ui/web/app.js:819`. | Fichier choisi n’est pas synonyme de vérification réussie. K8. |
| Conditions ouvertes | Sept paragraphes, zone défilante ; case bloquée jusqu’au bas ; bouton bloqué jusqu’à acceptation. `app/ui/web/index.html:441`, `app/ui/web/app.js:621`. | Lire dans la bonne langue, voir où défiler, comprendre le poids du téléchargement. K3–K4. |
| Annuler / fermer avant accord | Ferme les conditions ; aucun téléchargement n’est demandé par ce bouton. `app/ui/web/app.js:829`. | Revenir à la tâche et retrouver plus tard la même étape. K1. |
| Accord donné | Fermeture de la modale, demande explicite de récupération ; suivi global. `app/ui/web/app.js:648`. | Voir une progression stable et l’objet téléchargé. K5. |
| Une autre tâche occupe l’app | L’opération peut renvoyer l’erreur de tâche en cours ; la modale s’est déjà fermée. `app/ui/web/app.js:650`, `app/localization/fr.json:182`. | Attendre la tâche nommée et disposer d’un accès clair au nouvel essai. K6, T2. |
| Transfert | Deux parties configurées ; taille totale 252 802 747 octets, environ 253 Mo décimaux. `app/firmware/key_source.json:7`, `app/firmware/key_source.json:14`, `app/ui/bridge.py:431`. | Taille et avancement compréhensibles ; ne pas chercher deux fichiers à ouvrir. K5. |
| Vérification / lecture | Contrôles des archives, puis message de lecture avec progression indéterminée. `app/firmware/key_source.py:204`, `app/ui/bridge.py:435`. | Le transfert n’est pas toute l’opération ; attendre le résultat. K5. |
| Arrêt demandé | Annuler appelle l’annulation existante ; retour « demandé » puis état annulé. `app/ui/web/app.js:838`, `app/ui/bridge.py:445`. | Un arrêt demandé n’est pas encore un arrêt effectif. K6. |
| Réseau interrompu | Erreur avec nom d’archive et raison ; données déjà reçues annoncées conservées. `app/localization/en.json:300`, `app/localization/fr.json:300`. | Connexion puis nouvel essai, sans manipuler l’archive. K6. |
| Vérification refusée | Invite à mettre l’app à jour ou choisir manuellement un fichier. `app/localization/en.json:301`, `app/localization/fr.json:301`. | Ne pas contourner la vérification ; proposition manuelle réservée à qui possède déjà le fichier. K6. |
| Réessai | Réouvre les conditions ; archives valides réutilisables, transfert partiel repris si le serveur le permet. `app/ui/web/app.js:621`, `app/firmware/key_source.py:170`, `app/firmware/key_source.py:189`, `app/firmware/key_source.py:361`. | Ne pas promettre une reprise octet pour octet dans tous les cas. K6. |
| Réussite | Message avec chemin ; relecture de la clé ; aucune reprise automatique de `startBuild()`. `app/ui/web/app.js:655`, `app/ui/web/app.js:752`. | La préparation USB reste à demander explicitement. K7. |
| Suppression ultérieure | Confirmation ; suppression de la clé conservée et des téléchargements partiels ; actualisation. `app/ui/web/app.js:658`. | Ne supprime pas les modules déjà préparés sur USB ; ne restaure pas la platine. K8, R1. |

### K1 — Le téléchargement arrive avant son explication

- **Où :** première ouverture et bouton Préparer ; `app/ui/web/app.js:770`, `app/ui/web/app.js:678`, `app/ui/web/index.html:441`.
- **Ce que le DJ voit :** « Avant de télécharger la clé de chiffrement », immédiatement, avec l’écran Modules en arrière-plan.
- **Où il décroche :** il ne comprend ni pourquoi sa platine aurait besoin d’une clé informatique, ni s’il doit la brancher à l’ordinateur.
- **Proposition :** conserver l’étape et le consentement ; donner en haut de la modale une phrase d’usage, distincte du texte légal : **absent → FR « Cette préparation initiale permet de créer les fichiers que votre XDJ-RX3 chargera depuis la clé USB. » / EN « This initial setup lets you create the files your XDJ-RX3 will load from the USB drive. »**. Remplacer le bouton de fermeture par Plus tard, sans changer son action. Si la modale est différée, le résumé Modules conserve le lien de récupération.
- **FR** (`app/localization/fr.json:303`, `terms.title`) : « Avant de télécharger la clé de chiffrement » → « Préparation initiale : clé de chiffrement ».
- **EN** (`app/localization/en.json:303`, `terms.title`) : « Before downloading the encryption key » → « Initial setup: encryption key ».
- **FR** (`app/localization/fr.json:14`, `common.cancel`) : « Annuler » → « Plus tard ».
- **EN** (`app/localization/en.json:14`, `common.cancel`) : « Cancel » → « Later ».
- **Portée :** remplacement de `common.cancel` pour cette modale uniquement. Maintenir Annuler ailleurs et l’accord avant chaque téléchargement. Aucune récupération silencieuse.
- **Priorité / effort : P1 · S.**

### K2 — Deux objets différents s’appellent « clé »

- **Où :** résumé Modules, choix manuel et acquisition ; `app/ui/web/index.html:100`, `app/ui/web/app.js:604`, `app/localization/fr.json:51`, `app/localization/fr.json:295`.
- **Ce que le DJ voit :** Clé de chiffrement / aucun / Obtenir / Parcourir, à proximité de la destination USB. La phrase `modules.keyLede` existe mais n’est pas insérée ici.
- **Où il décroche :** il pense devoir chercher un fichier sur sa clé USB ou dans rekordbox.
- **Proposition :** conserver le terme du glossaire et l’accompagner une fois : **absent → FR « La clé de chiffrement est un fichier nécessaire à la préparation. L’application peut le récupérer et le conserver sur cet ordinateur. » / EN « The encryption key is a file needed for preparation. The app can retrieve it and keep it on this computer. »**. Présenter l’état et le bouton de récupération avant le chemin ; pictogramme de clé pour ce fichier, pictogramme USB pour le support.
- **FR** (`app/localization/fr.json:366`, `modules.needKey`) : « Ajoutez une clé de chiffrement pour créer le mod. » → « Récupérez la clé de chiffrement pour préparer votre clé USB. ».
- **EN** (`app/localization/en.json:366`, `modules.needKey`) : « Add an encryption key to build the mod. » → « Get the encryption key to prepare your USB drive. ».
- **FR** (`app/localization/fr.json:295`, `modules.keyFetchNote`) : « Archive source Pioneer : {bytes}. Seule la clé de chiffrement est conservée. » → « Téléchargement initial : {bytes}, depuis l’archive source Pioneer DJ. Seule la clé de chiffrement est conservée à la fin. ».
- **EN** (`app/localization/en.json:295`, `modules.keyFetchNote`) : « Pioneer source archive: {bytes}. Only the encryption key is kept. » → « Initial download: {bytes}, from the Pioneer DJ source archive. Only the encryption key is kept when complete. ».
- **Priorité / effort : P1 · S.**

### K3 — Le consentement est lisible seulement dans une petite fenêtre défilante

- **Où :** conditions ; `app/ui/web/index.html:443`, `app/ui/web/index.html:452`, `app/ui/web/app.css:256`, `app/ui/web/app.js:639`, `app/ui/web/i18n.js:49`.
- **Ce que le DJ voit :** environ 40 % de la hauteur de fenêtre au maximum pour le texte, soit 224 px à 560 px ; une case désactivée et le sélecteur de langue uniquement dans Réglages, derrière la modale.
- **Où il décroche :** il tente de cocher avant d’avoir atteint le bas, ou ne peut pas facilement changer une langue mémorisée qu’il ne comprend pas.
- **Proposition :** garder tout le texte et la condition de défilement. Afficher FR/EN dans la modale, au-dessus du texte ; conserver le bas de la modale visible avec la case et les actions. Donner au corps l’espace restant plutôt qu’une limite arbitraire de 40vh quand de la place est disponible. Afficher la taille du téléchargement près du bouton. Ne pas cocher à sa place et ne pas abréger le texte légal.
- **FR** (`app/localization/fr.json:311`, `terms.scroll`) : « Lisez les conditions jusqu’en bas pour pouvoir cocher la case d’acceptation. » → « Faites défiler les conditions jusqu’en bas pour activer la case « J’ai lu et j’accepte ces conditions ». ».
- **EN** (`app/localization/en.json:311`, `terms.scroll`) : « Read and scroll to the end to enable acceptance. » → « Scroll to the end of the terms to enable the “I have read and accept these terms” checkbox. ».
- **Priorité / effort : P2 · M.**

### K4 — Le changement de langue change aussi des informations de fond

- **Où :** conditions et règle éditoriale ; `app/localization/en.json:304`, `app/localization/fr.json:304`, `app/localization/en.json:306`, `app/localization/fr.json:306`, `app/localization/en.json:309`, `app/localization/fr.json:309`, `app/localization/en.json:310`, `app/localization/fr.json:310`, `.claude/STYLE.md:46`.
- **Ce que le DJ voit :** EN explique vérification, conservation locale et suppression du reste ; FR parle de clé USB « moddable » et de « déverrouiller » un mode. FR interdit aussi la commercialisation d’un mod basé sur la clé ; cette formulation n’apparaît pas dans le paragraphe EN correspondant. EN nomme MPL 2.0, FR non. EN explique où supprimer ; FR explique la conséquence sur les futurs mods.
- **Où il décroche :** en cherchant une précision dans l’autre langue, il obtient une autre explication et d’autres formulations de responsabilité. Ce sont des écarts textuels vérifiés, **pas une conclusion juridique**.
- **Proposition concrète de présentation :** ajouter des intertitres identiques de portée, sans retirer une phrase : **absent → FR « Téléchargement et conservation » / EN « Download and storage »**, **FR « Usage et responsabilité » / EN « Use and responsibility »**, **FR « Supprimer la clé de chiffrement » / EN « Delete the encryption key »**. Maintenir la totalité des conditions avant acceptation. Ne pas substituer les versions l’une à l’autre dans une simple passe UX.
- **À résoudre avant publication de nouveaux textes juridiques :** réconciliation éditoriale EN/FR avec README et la référence NOTICE demandée par STYLE ; aucun fichier `NOTICE` n’a été trouvé dans ce checkout. La formulation juridique exacte reste hors proposition de réécriture ici pour ne pas choisir arbitrairement quelles obligations supprimer ou ajouter. Le mot « moddable » n’est pas recommandé ailleurs ; son remplacement dans les conditions doit faire partie de cette réconciliation explicite.
- **Priorité / effort : P1 · M** pour la présentation et la cohérence ; validation du fond non estimée.

### K5 — La progression raconte l’archive, pas l’avancement utile

- **Où :** téléchargement et barre globale ; `app/ui/web/app.js:709`, `app/ui/web/app.js:717`, `app/ui/bridge.py:431`, `app/localization/fr.json:298`, `app/ui/web/i18n.js:38`.
- **Ce que le DJ voit :** « archive source Pioneer, partie 1 sur 2 », une barre ; puis « Lecture de la clé… » et une barre indéterminée. Les octets reçus/total existent dans les données de progression, mais le frontend ne les affiche pas pour la clé.
- **Où il décroche :** il ne sait pas s’il doit patienter, ouvrir une archive, ni pourquoi la barre change d’aspect après le transfert.
- **Proposition :** deux phases stables : téléchargement puis récupération/vérification, sans inventer de pourcentage pendant la phase indéterminée. Afficher les octets déjà fournis en Mo/MB et le pourcentage réel. Laisser les noms d’archives dans les détails. Taille totale calculée depuis les métadonnées, pas une constante UI de 250.
- **FR** (`app/localization/fr.json:298`, `job.keyDownload`) : « Téléchargement de l’archive source Pioneer, partie {part} sur {count} » → « Téléchargement des fichiers Pioneer DJ · {part}/{count} ».
- **EN** (`app/localization/en.json:298`, `job.keyDownload`) : « Downloading Pioneer's source archive, part {part} of {count} » → « Downloading Pioneer DJ files · {part}/{count} ».
- **FR** (`app/localization/fr.json:299`, `job.keyRead`) : « Lecture de la clé de chiffrement dans l’archive » → « Récupération de la clé de chiffrement… ».
- **EN** (`app/localization/en.json:299`, `job.keyRead`) : « Reading the encryption key from the archive » → « Retrieving the encryption key… ».
- **Unités :** pour une présentation Mo/MB, convertir réellement les octets en base 10 ; ne pas renommer Mio/MiB sans conversion. Les conditions existantes peuvent conserver leur approximation d’environ 250 Mo.
- **Priorité / effort : P2 · S.**

### K6 — Réessayer ou annuler exige de retrouver soi-même l’entrée du parcours

- **Où :** échec et interruption ; `app/ui/web/app.js:648`, `app/ui/web/app.js:722`, `app/ui/web/app.js:838`, `app/localization/fr.json:300`, `app/localization/fr.json:301`, `app/firmware/key_source.py:170`, `app/firmware/key_source.py:189`.
- **Ce que le DJ voit :** nom ZIP opaque et raison technique ; Annuler disparaît en fin de tâche, sans bouton de reprise dans le résultat. Le bouton de récupération existe toujours dans Modules.
- **Où il décroche :** il pense devoir chercher le ZIP, supprimer un téléchargement ou réinstaller la platine ; après annulation il ignore ce qui reste.
- **Proposition :** résultat avec action explicite **« Réessayer le téléchargement » / « Retry download »** qui réouvre les conditions existantes. Séparer les détails d’erreur, sans les perdre. Annulation : **absent → FR « Téléchargement arrêté. Vous pouvez le relancer depuis Modules. » / EN « Download stopped. You can restart it from Modules. »** ; afficher cet état uniquement après arrêt confirmé. Si une tâche occupe l’app, donner un lien vers sa progression, sans annuler cette tâche automatiquement.
- **FR** (`app/localization/fr.json:300`, `error.keyNetwork`) : « Impossible de télécharger {name} : {reason}. Vérifiez la connexion, puis réessayez. Les données déjà reçues sont conservées. » → « Le téléchargement a été interrompu. Vérifiez votre connexion Internet, puis réessayez. Les données déjà reçues sont conservées. ».
- **EN** (`app/localization/en.json:300`, `error.keyNetwork`) : « Couldn't download {name}: {reason}. Check the connection, then try again. Data already downloaded is kept. » → « The download was interrupted. Check your internet connection, then try again. Data already downloaded is kept. ».
- **FR** (`app/localization/fr.json:301`, `error.keyPackage`) : « La vérification de {name} a échoué. Mettez le Toolkit à jour ou sélectionnez un fichier de clé de chiffrement avec Parcourir. » → « Les fichiers téléchargés n’ont pas passé la vérification. Mettez le Toolkit à jour avant de réessayer. ».
- **EN** (`app/localization/en.json:301`, `error.keyPackage`) : « Verification failed for {name}. Update the Toolkit or select an encryption key file with Browse. » → « The downloaded files did not pass verification. Update the Toolkit before trying again. ».
- **Détails :** `{name}` et `{reason}` restent consultables ; l’alternative d’un fichier de clé déjà détenu reste dans les options manuelles K8. Pas de contournement de vérification et pas de promesse de reprise exacte lorsque le serveur ignore la reprise partielle.
- **Priorité / effort : P1 · M.**

### K7 — Réussite : un chemin de fichier remplace la prochaine action

- **Où :** fin de téléchargement ; `app/ui/web/app.js:655`, `app/ui/web/app.js:666`, `app/ui/web/app.js:752`, `app/ui/web/app.js:677`.
- **Ce que le DJ voit :** « Terminé » puis « Clé de chiffrement enregistrée dans {path} » ; la sélection se met à jour. Le clic initial sur Créer le mod n’est pas relancé.
- **Où il décroche :** il cherche s’il doit déplacer ce fichier sur sa clé USB, ou croit que toute la préparation est terminée.
- **Proposition :** état prêt dans le résumé, chemin conservé dans les détails, bouton **« Continuer dans Modules » / « Continue in Modules »**. Si déjà dans Modules, mettre en évidence le bouton de préparation et sa destination. L’écriture reste explicitement demandée par le DJ, pas déclenchée au retour du téléchargement.
- **FR** (`app/localization/fr.json:297`, `modules.keyFetched`) : « Clé de chiffrement enregistrée dans {path} » → « Clé de chiffrement prête. Vous pouvez préparer votre clé USB. ».
- **EN** (`app/localization/en.json:297`, `modules.keyFetched`) : « Encryption key saved to {path} » → « Encryption key ready. You can now prepare your USB drive. ».
- **Détail conservé :** `{path}` reste disponible sous l’état ; ce chemin ne doit pas être présenté comme une consigne de copie. Si aucune destination n’est choisie, le prochain contrôle mis en évidence est son choix.
- **Priorité / effort : P1 · S.**

### K8 — Chemin, import manuel et suppression ont trop de poids

- **Où :** clé présente ou absente ; `app/ui/web/app.js:604`, `app/ui/web/app.js:658`, `app/ui/web/app.js:819`, `app/ui/web/index.html:104`.
- **Ce que le DJ voit :** un chemin long, Parcourir et Supprimer la clé de chiffrement côte à côte. Une clé choisie manuellement remplit l’état sans preuve de validation ; le téléchargement est alors masqué.
- **Où il décroche :** il prend un fichier au hasard pour débloquer le bouton, ou supprime la clé en pensant désactiver les modules.
- **Proposition :** état principal « Clé de chiffrement disponible » / « Encryption key available » uniquement pour la clé retenue reconnue ; pour choix manuel « Fichier choisi » / « File selected ». Grouper chemin, sélection manuelle et suppression dans **« Gérer la clé de chiffrement » / « Manage encryption key »**. Garder une issue visible après fichier introuvable : choisir un autre fichier ou revenir au parcours de récupération avec accord.
- **FR** (`app/localization/fr.json:11`, `common.browse`) : « Parcourir » → « Choisir un fichier de clé de chiffrement ».
- **EN** (`app/localization/en.json:11`, `common.browse`) : « Browse » → « Choose an encryption key file ».
- **FR** (`app/localization/fr.json:388`, `ui.forgetKeyBody`) : « La clé de chiffrement enregistrée et le téléchargement partiel seront supprimés. Vous devrez récupérer la clé de chiffrement pour créer un nouveau mod. » → « La clé de chiffrement et les téléchargements partiels seront supprimés de cet ordinateur. Les fichiers déjà préparés sur votre clé USB resteront en place. Vous devrez récupérer la clé de chiffrement pour une prochaine préparation. ».
- **EN** (`app/localization/en.json:388`, `ui.forgetKeyBody`) : « This deletes the saved encryption key and any partial download. You will need the encryption key again to build another mod. » → « The encryption key and partial downloads will be deleted from this computer. Files already prepared on your USB drive will remain. You will need to retrieve the encryption key for a future preparation. ».
- **Portée :** nouveau libellé de Parcourir propre au choix de clé ; ne pas remplacer le bouton des autres écrans. Conserver les règles actuelles protégeant un fichier manuel et la confirmation de suppression.
- **Priorité / effort : P2 · S.**

## Constats transversaux — Réglages, graphismes, cohérence et états

### T1 — Trois thèmes concernent trois choses différentes

- **Où :** Réglages, module Thème clair, Logo ; `app/ui/web/index.html:392`, `app/ui/web/index.html:253`, `mod/modules/theme-white/manifest.json:4`, `app/localization/fr.json:412`.
- **Ce que le DJ voit :** Apparence, Thème clair et Thème de l’aperçu. L’aide Réglages renvoie vers Logo, alors que l’apparence réelle de la platine dépend du module Thème clair.
- **Où il décroche :** il choisit Clair dans Réglages et s’attend à retrouver ce thème sur le RX3 ; l’aperçu clair n’est pas non plus une activation du module.
- **Proposition :** nommer les trois portées, conserver leurs choix et leur indépendance. Dans Réglages, mettre langue et apparence dans deux groupes compacts ; À propos peut rester bref. Ne pas ajouter de réglage technique stems dans cette destination générale.
- **FR** (`app/localization/fr.json:411`, `ui.appearance`) : « Apparence » → « Apparence de l’application ».
- **EN** (`app/localization/en.json:411`, `ui.appearance`) : « Appearance » → « App appearance ».
- **FR** (`app/localization/fr.json:412`, `ui.appearanceHint`) : « Ce réglage change le thème du Toolkit. Réglez séparément l’aperçu du RX3 dans Logo. » → « Pour l’écran de la platine, sélectionnez Thème clair dans Modules. ».
- **EN** (`app/localization/en.json:412`, `ui.appearanceHint`) : « This changes the Toolkit theme. Adjust the RX3 preview separately in Logo. » → « For the deck’s screen, select Light theme in Modules. ».
- **FR** (`app/localization/fr.json:368`, `logo.screenTheme`) : « Thème de l’aperçu » → « Aperçu sur fond clair ou sombre ».
- **EN** (`app/localization/en.json:368`, `logo.screenTheme`) : « Preview theme » → « Preview on a light or dark screen ».
- **FR** (`app/localization/fr.json:416`, `ui.immediateSettings`) : « Les modifications s’appliquent immédiatement. » → « La langue et l’apparence de l’application s’appliquent immédiatement. ».
- **EN** (`app/localization/en.json:416`, `ui.immediateSettings`) : « Changes apply immediately. » → « App language and appearance changes apply immediately. ».
- **Priorité / effort : P2 · S.**

### T2 — Les erreurs se répètent et les réussites courantes déplacent le contenu

- **Où :** messages communs ; `app/ui/web/app.js:64`, `app/ui/web/app.js:97`, `app/ui/web/components.js:55`, `app/ui/web/components.js:70`, `app/ui/web/app.js:208`, `app/ui/web/app.css:247`.
- **Ce que le DJ voit :** une erreur peut apparaître à la fois dans le toast global et dans l’état de l’écran. Un simple relevé USB affiche aussi un état de succès au-dessus de la carte. Le toast fixé en bas à droite peut occuper le même espace que la progression.
- **Où il décroche :** il peut compter deux pannes au lieu d’une ou chercher un nouveau problème à chaque actualisation. Le résultat se déplace pendant qu’il lit.
- **Proposition :** une erreur liée à un champ ou écran reste au bon endroit avec son action ; erreur de tâche dans sa zone de résultat ; un seul affichage principal, détails techniques dépliables. Réserver les annonces de succès aux états du contenu, sans bannière de lecture/rafraîchissement. Prévoir une place stable pour la progression longue. Conserver les confirmations destructives.
- **FR** (`app/localization/fr.json:181`, `error.detail`) : « Échec de l'opération : {detail} » → « L’opération n’a pas abouti. Consultez les détails ci-dessous. ».
- **EN** (`app/localization/en.json:179`, `error.detail`) : « Operation failed: {detail} » → « The operation did not complete. See the details below. ».
- **Détails :** `{detail}` est déplacé sous « Détails techniques » / « Technical details », jamais supprimé. Les erreurs connues doivent garder leur correction précise ; le texte générique n’est qu’un repli. Pas de « Réessayer » universel déclenchant une écriture non contextualisée.
- **Priorité / effort : P2 · M.**

### T3 — Les codes DJ existent, mais changent entre les représentations

- **Où :** couleurs, icônes, aperçus ; `app/ui/web/app.css:17`, `app/ui/web/app.css:172`, `app/ui/web/app.css:187`, `app/ui/web/index.html:22`, `app/ui/web/rx3-mock.js:292`, `app/ui/web/rx3-mock.js:392`, `app/ui/web/rx3-mock.js:210`, `app/ui/web/rx3-mock.js:422`, `app/ui/web/key-match-green.svg:1` et les trois SVG correspondants.
- **Ce que le DJ voit :** accent applicatif bleu, pads représentés par une grille d’icône de six cases alors que l’éditeur en présente huit, DRUMS bleu clair dans l’aide pads et bleu pur dans l’aide tactile, rôles d’écoute neutres. Les aperçus affichent un temps impossible « 0:67 ».
- **Où il décroche :** il cherche les mêmes repères qu’en jouant ; un bouton DRUMS doit être reconnaissable sans relire, et un temps impossible diminue la crédibilité de l’aperçu.
- **Proposition graphique précise :** conserver les SVG Key Match à leur dessin natif 28 × 26 et leurs couleurs, avec une légende textuelle ; ne pas les remplacer par des pastilles génériques. Uniformiser l’icône Samples en 2 × 4 cases. Définir les couleurs sémantiques des rôles dans l’UI et les réutiliser pour guides, écoute et légendes : INST rouge, VOCAL vert, DRUMS bleu ; le détail de luminance doit correspondre à la représentation matérielle concernée, pas être remplacé arbitrairement sur le RX3. Corriger dans les deux langues la donnée fictive « 0:67 » → « 1:07 ».
- **À conserver :** accent bleu réservé aux actions de l’app, vert de réussite réservé aux résultats ; ne pas recolorer toute l’app en orange au motif que rekordbox en utilise. Les libellés matériels BROWSE, MASTER, KEY, STEMS, SLIP LOOP, RELEASE FX et VOL restent tels quels. Les codes de rekordbox sont ici appréciés depuis les actifs et représentations du dépôt, sans comparaison live à une version externe.
- **Priorité / effort : P2 · M.**

### T4 — Les détails de 12 px occupent la place des décisions

- **Où :** typographie et espacements ; `app/ui/web/app.css:6`, `app/ui/web/app.css:66`, `app/ui/web/app.css:91`, `app/ui/web/app.css:147`, `app/ui/web/app.css:265`, `app/ui/web/app.css:270`.
- **Ce que le DJ voit :** corps 13 px, aides et chemins 12 px, nombreuses cartes séparées par 24 px ; résumé Modules placé avant la liste sous 1040 px, inspecteur Samples et contrôles Logo empilés sous 1190 px.
- **Où il décroche :** à petite fenêtre, son attention va aux chemins, aux réglages techniques et aux cartes avant le geste musical. À la taille par défaut, l’éditeur de pad n’est déjà plus voisin de la grille.
- **Proposition :** instructions nécessaires à la décision en 14 px, secondaires en 12 px ; nom de clé et action en 14 px semi-gras. Garder les espacements existants de 8/16/24 px mais utiliser 8 px entre une instruction et son contrôle, 16 px entre choix liés, 24 px entre tâches. À 880 × 560, résumer destination/étape en une ligne avant les modules, puis développer le reste à la demande ; ne pas réserver d’abord une grande carte de réglages techniques. Tester le retour à la ligne FR avant de changer les seuils de colonnes. Pas de réduction des libellés par troncature pour faire tenir la fenêtre.
- **Priorité / effort : P2 · M.**

### T5 — Les unités et les messages de dépannage demandent une traduction informatique

- **Où :** tailles, import et messages relayés ; `app/ui/web/i18n.js:38`, `app/localization/fr.json:274`, `app/localization/fr.json:278`, `app/localization/fr.json:288`, `app/localization/fr.json:443`, `app/localization/fr.json:436`, `app/ui/web/stems.js:55`.
- **Ce que le DJ voit :** Gio/Mio/Kio, nombre brut d’octets, « Rétablissez la détection des processus », code de séparation, paquet de stems, trames et cache. Quelques messages sont anglais même avec l’interface française.
- **Où il décroche :** aucune action concrète ne correspond à « rétablir la détection » ; supprimer un fichier dans RX3_STEMS ou comprendre un code de processus dépasse son usage DJ.
- **Proposition :** d’abord l’objet musical, la conséquence et l’action réellement disponible ; chiffres techniques en détails. Tailles en Mo/Go avec conversion correcte, durées en minutes/secondes. Présenter les textes bruts comme détails conservés, sans parser une erreur arbitraire en fausse cause certaine. Les lignes de diagnostic ne doivent pas devenir des prescriptions techniques invérifiables.
- **FR** (`app/localization/fr.json:278`, `stems.processUnknown`) : « Impossible de vérifier si le logiciel de bibliothèque musicale est ouvert. Rétablissez la détection des processus avant de continuer. » → « Impossible de vérifier que rekordbox est fermé. Fermez rekordbox, puis cliquez sur Vérifier de nouveau. Si le blocage persiste, conservez les détails de l’erreur pour le dépannage. ».
- **EN** (`app/localization/en.json:278`, `stems.processUnknown`) : « Cannot check whether the library application is running. Restore process detection before continuing. » → « Cannot check that rekordbox is closed. Close rekordbox, then click Check again. If this remains blocked, keep the error details for troubleshooting. ».
- **FR** (`app/localization/fr.json:443`, `stems.separatorFailed`) : « Le moteur de séparation s’est arrêté avec le code {code}. Détails : {detail} » → « La préparation des stems s’est arrêtée. Consultez les détails de l’erreur avant de réessayer. ».
- **EN** (`app/localization/en.json:443`, `stems.separatorFailed`) : « The separation engine stopped with code {code}. Details: {detail} » → « Stem preparation stopped. Check the error details before trying again. ».
- **FR** (`app/localization/fr.json:470`, `stems.waveInvalid`) : « Paquet de stems illisible. Préparez à nouveau ce morceau. » → « Impossible de lire les fichiers de stems. Préparez de nouveau ce morceau. ».
- **EN** (`app/localization/en.json:470`, `stems.waveInvalid`) : « Cannot read the stems package. Prepare this track again. » → « Cannot read the stem files. Prepare this track again. ».
- **Détails et limite :** `{code}` et `{detail}` restent disponibles. Relancer ne garantit pas de réparer une détection de processus. Le remplacement de stems importés qui requiert aujourd’hui une manipulation de fichiers reste une limite produit : ne pas inventer un bouton « Remplacer » sans opération existante.
- **Priorité / effort : P1 · M.**

## Constat — retour à l’état d’origine

### R1 — Retirer les fichiers et retrouver la platine d’origine sont confondus

- **Où :** inspection USB, confirmation, résultat ; `app/ui/web/index.html:65`, `app/ui/web/app.js:809`, `app/localization/fr.json:385`, `app/localization/fr.json:386`, `README.md:308`, `app/services/mod.py:78`.
- **Ce que le DJ voit :** « Retirer le mod », puis un nombre de fichiers supprimés. La procédure d’arrêt, extinction, retrait de la clé et redémarrage n’est pas dans l’app. Supprimer la clé de chiffrement est une autre action visible.
- **Où il décroche :** il peut croire devoir désinstaller quelque chose dans la platine ou pense que supprimer la clé de chiffrement désactive immédiatement ses fonctions.
- **Proposition :** garder le retrait de fichiers explicite et confirmé, avec le nom de la clé. Séparer dans une aide dépliable « Utiliser la platine sans modules » / « Use the deck without modules » de l’action qui nettoie l’USB. Reprendre exactement la séquence du README sous forme de gestes : **absent → FR « Arrêtez la lecture. Éteignez la platine. Retirez la clé USB préparée. Rallumez la platine. » / EN « Stop playback. Turn off the deck. Remove the prepared USB drive. Turn the deck on again. »**. Ne pas laisser entendre qu’un retrait de clé en lecture suffit.
- **FR** (`app/localization/fr.json:39`, `drive.removeMod`) : « Retirer le mod » → « Retirer les modules de cette clé USB ».
- **EN** (`app/localization/en.json:39`, `drive.removeMod`) : « Remove the mod » → « Remove modules from this USB drive ».
- **FR** (`app/localization/fr.json:385`, `ui.removeDriveTitle`) : « Retirer le mod de cette clé USB ? » → « Retirer les modules de cette clé USB ? ».
- **EN** (`app/localization/en.json:385`, `ui.removeDriveTitle`) : « Remove the mod from this USB drive? » → « Remove modules from this USB drive? ».
- **FR** (`app/localization/fr.json:386`, `ui.removeDriveBody`) : « Clé USB : {path}<br>Les fichiers du mod seront supprimés. » → « Clé USB : {path}<br>Les fichiers des modules et leurs journaux seront supprimés. Votre musique, vos stems et vos banques de samples seront conservés. ».
- **EN** (`app/localization/en.json:386`, `ui.removeDriveBody`) : « USB drive: {path}<br>The mod files will be removed. » → « USB drive: {path}<br>Module files and their logs will be removed. Your music, stems and sample banks will be kept. ».
- **Résultat proposé :** FR « Modules retirés de cette clé USB. Votre musique, vos stems et vos banques de samples sont conservés. » / EN « Modules removed from this USB drive. Your music, stems and sample banks have been kept. » remplace les deux formes de `drive.removed` (`app/localization/en.json:41`, `app/localization/fr.json:41`) ; nombre de fichiers dans les détails. Ne pas déclarer la platine déjà revenue à l’état d’origine depuis le seul résultat sur USB.
- **Priorité / effort : P1 · S.**


## Vocabulaire

Ce tableau couvre les termes techniques fixes repérés dans les écrans, leurs aides, les conditions et les messages susceptibles d’être relayés. Les valeurs libres d’une erreur externe peuvent contenir d’autres termes : leur totalité ne peut pas être recensée statiquement. Les libellés matériels et les termes DJ connus ne sont pas à « simplifier » arbitrairement.

**Convention éditoriale proposée :** garder les termes techniques nécessaires dans un détail consultable ; employer dans le parcours principal un objet ou un geste compréhensible. Le remplacement d’un intitulé ne promet jamais une nouvelle capacité. Les constats associés portent priorité et effort ; ce tableau constitue leur inventaire lexical, pas un second catalogue de défauts sans preuve.

| Terme actuel EN / FR ou texte brut visible | Pourquoi le DJ s’arrête | Proposition EN | Proposition FR | Preuve / constat |
|---|---|---|---|---|
| Mod / mod ; build / créer le mod | Il ne sait pas ce qui sera installé ni où. | Prepare USB drive ; module files | Préparer la clé USB ; fichiers des modules | `app/localization/en.json:54`, `app/localization/fr.json:54` · M1 |
| Modules | Nom imposé des destinations ; peut évoquer des composants. | Keep **Modules**, explain “features for your XDJ-RX3” | Garder **Modules**, expliquer « fonctions pour votre XDJ-RX3 » | `PRODUCT.md:7`, `app/localization/en.json:45`, `app/localization/fr.json:45` · O1/M1 |
| Module on / module activé | Peut signifier déjà actif sur la platine. | Module selected | Module sélectionné | `app/localization/en.json:360`, `app/localization/fr.json:360` · M1 |
| Requires / Needed by ; Nécessite / Requis par | Relation informatique, pas action de mix. | Included with {feature} | Inclus avec {feature} | `app/localization/en.json:49`, `app/localization/fr.json:49`, `app/localization/en.json:365`, `app/localization/fr.json:365` · M2 |
| Firmware | Version logicielle peu familière ; pas une détection. | XDJ-RX3 software version | Version du logiciel du XDJ-RX3 | `app/localization/en.json:28`, `app/localization/fr.json:28` · M5 |
| Build settings / Réglages du mod | Préparation et état installé se confondent. | To save to your USB drive | À enregistrer sur votre clé USB | `app/localization/en.json:417`, `app/localization/fr.json:417` · M1 |
| Write to / Destination | Destination de quoi, et quel objet choisir ? | Destination USB drive or folder | Clé USB ou dossier de destination | `app/localization/en.json:53`, `app/localization/fr.json:53` · O3 |
| Browse / Parcourir | Même mot pour dossier et secret technique ; peut aussi rappeler BROWSE. | Choose destination / Choose encryption key file | Choisir la destination / Choisir un fichier de clé de chiffrement | `app/localization/en.json:11`, `app/localization/fr.json:11` · O3/K8 |
| Absolute path / chemin tel que `/Volumes/…` | Il reconnaît le nom de sa clé, pas sa notation système. | Drive/folder name ; full location in details | Nom de clé/dossier ; emplacement complet dans les détails | `app/ui/web/app.js:116` · O2/O4 |
| Encryption key / clé de chiffrement | Confusion avec clé USB. | Encryption key — file needed for preparation | Clé de chiffrement — fichier nécessaire à la préparation | `app/localization/en.json:51`, `app/localization/fr.json:51` · K2 ; **glossaire conservé** |
| Source archive / archive source | Il croit devoir extraire ou programmer quelque chose. | Initial download ; source archive in details | Téléchargement initial ; archive source dans les détails | `app/localization/en.json:295`, `app/localization/fr.json:295` · K2 ; **glossaire conservé** |
| Maintenance mode / mode maintenance | Il peut chercher une combinaison de boutons ou craindre une réparation. | Keep legal term ; explain initial preparation in the task heading | Garder le terme juridique ; expliquer la préparation initiale dans le titre du parcours | `app/localization/en.json:304`, `app/localization/fr.json:304` · K1/K4 ; **glossaire conservé** |
| “moddable”, “déverrouiller un mode spécial” | Donne une explication opaque et différente de l’EN. | Task heading: Initial setup | Titre de parcours : Préparation initiale | `app/localization/fr.json:304` · K4 ; **pas de substitution isolée dans les conditions** |
| GPL, fingerprint, licences, MPL 2.0 | Il ne s’en sert pas pour préparer sa musique. | Keep unchanged in the full terms, under a clear heading | Conserver dans les conditions intégrales, sous un intertitre clair | `app/localization/en.json:304`, `app/localization/en.json:307`, `app/localization/en.json:309` · K4 ; **sens légal intact** |
| Archive part / partie d’archive ; ZIP opaque | Il croit devoir ouvrir plusieurs fichiers. | Downloading Pioneer DJ files · {part}/{count} | Téléchargement des fichiers Pioneer DJ · {part}/{count} | `app/localization/en.json:298`, `app/localization/fr.json:298`, `app/firmware/key_source.json:6` · K5/K6 |
| Verification failed / vérification échouée | Pas de prochaine action évidente. | Downloaded files did not pass verification ; update Toolkit | Les fichiers téléchargés n’ont pas passé la vérification ; mettre le Toolkit à jour | `app/localization/en.json:301`, `app/localization/fr.json:301` · K6 |
| Retained key / clé conservée | Où est-elle conservée ? | Encryption key saved on this computer | Clé de chiffrement enregistrée sur cet ordinateur | `app/localization/en.json:387`, `app/localization/fr.json:387` · K8 |
| Separation engine / moteur de séparation | Il ne sait pas ce qu’il doit installer. | Stem preparation tools | Outils de préparation des stems | `app/localization/en.json:148`, `app/localization/fr.json:150` · S1 |
| Runtime / environment / environnement | Détail d’installation incompréhensible pour ce persona. | Preparation tools ; installation | Outils de préparation ; installation | `app/stems/provisioning.py:351`, `app/stems/provisioning.py:685` · S1/T5 |
| audio-separator, FFmpeg, PyTorch, pip | Noms de composants utilisés à la place d’un état utilisable. | Installing preparation tools ; component names in details | Installation des outils de préparation ; noms des composants dans les détails | `app/stems/provisioning.py:354`, `app/stems/provisioning.py:606` · S1/T5 |
| Python interpreter, venv | Vrai prérequis, pas un terme que l’on peut effacer en le renommant. | Python {versions} is required to install the preparation tools | Python {versions} est nécessaire pour installer les outils de préparation | `app/stems/provisioning.py:550` · S1 ; conserver la limite réelle |
| Run on / Calcul sur ; accelerator | Le DJ ne choisit pas une méthode de calcul. | Processing hardware · Automatic | Matériel utilisé · Automatique | `app/localization/en.json:147`, `app/localization/fr.json:149` · S4 |
| CPU only / CPU uniquement | Acronyme sans utilité pour son choix courant. | Computer processor | Processeur de l’ordinateur | `app/localization/en.json:235`, `app/localization/fr.json:237` · S4 |
| Apple Silicon (Metal), NVIDIA CUDA, AMD ROCm, DirectML | Mélange de matériel et de technologies. | Apple chip / NVIDIA graphics card / AMD graphics card / Windows graphics acceleration | Puce Apple / Carte graphique NVIDIA / Carte graphique AMD / Accélération graphique Windows | `app/localization/en.json:236`, `app/localization/fr.json:238` · S4 ; termes exacts conservés dans les détails |
| XML export / export XML ; library / bibliothèque | Il connaît son export USB et sa playlist. | USB rekordbox export first ; rekordbox XML export under Other music source | Export rekordbox sur clé en premier ; export XML rekordbox sous Autre source musicale | `app/localization/en.json:151`, `app/localization/fr.json:153` · S2 |
| Source / output / destination | Il doit distinguer ce qui est lu de ce qui est préparé. | Music read from / Stems saved to | Musique lue depuis / Stems enregistrés dans | `app/ui/web/index.html:300`, `app/ui/web/index.html:310` · O4 |
| Model / preset / passes / shifted passes | Le mécanisme n’indique pas le temps ni le résultat utile. | Quality setting ; longer/faster preparation | Réglage de qualité ; préparation plus longue/rapide | `app/localization/en.json:458`, `app/localization/fr.json:458` · S4 ; détail technique conservé |
| Frequencies above 17.6 kHz | Limite technique réelle mais encombrante au premier niveau. | Frequency-range limitation, in quality details | Limite de fréquences, dans les détails de qualité | `app/localization/en.json:227`, `app/localization/fr.json:229` · S4 ; ne pas la nier |
| Cache / local cache | Il peut croire supprimer les stems de sa clé USB. | Copies kept on this computer | Copies conservées sur cet ordinateur | `app/localization/en.json:290`, `app/localization/fr.json:290` · T5 |
| Clear cache / Vider le cache | Objet de la suppression mal identifié. | Delete saved copies on this computer | Supprimer les copies conservées sur cet ordinateur | `app/localization/en.json:291`, `app/localization/fr.json:291` · T5 ; garder la confirmation |
| GiB, MiB, KiB / Gio, Mio, Kio ; bytes / octets | Des chiffres et unités qu’il ne relie pas à l’espace libre habituel. | GB / MB, with decimal conversion | Go / Mo, avec conversion décimale | `app/ui/web/i18n.js:38`, `app/localization/en.json:215`, `app/localization/fr.json:217`, `app/localization/fr.json:274` · K5/T5 |
| Symbolic link / lien symbolique | Aucun objet reconnaissable sur l’écran. | Choose the actual music folder, not a shortcut | Choisissez le dossier qui contient la musique, pas un raccourci | `app/localization/en.json:273`, `app/localization/fr.json:273` · T5 ; terme exact dans les détails |
| Process detection / détection des processus | Il n’a aucune action portant ce nom. | Close rekordbox, then Check again ; if still blocked, keep the error details | Fermez rekordbox, puis Vérifier de nouveau ; si le blocage persiste, conserver les détails | `app/localization/en.json:278`, `app/localization/fr.json:278` · T5 |
| Read-only / lecture seule ; writable / accessible en écriture | Seul compte le fait de pouvoir enregistrer. | Cannot save to this USB drive. Choose another drive. | Impossible d’enregistrer sur cette clé USB. Choisissez une autre clé. | `app/localization/en.json:37`, `app/localization/fr.json:37` · O3/T5 |
| Package / paquet de stems | Le DJ cherche un morceau et ses stems, pas un conteneur. | Stem files | Fichiers de stems | `app/localization/en.json:470`, `app/localization/fr.json:470` · T5 |
| Encoding / encodage | Étape technique sans geste associé. | Preparing {role} | Préparation : {role} | `app/localization/en.json:286`, `app/localization/fr.json:286` · T5 |
| At destination / À destination ; Imported / Importés | Source d’écoute mal identifiée ; les fichiers choisis ne sont pas nécessairement écrits. | Saved stems / Selected files | Stems enregistrés / Fichiers choisis | `app/localization/en.json:347`, `app/localization/fr.json:347` · S6 |
| INST, VOCAL, DRUMS, INSTRUMENTAL | Libellés des commandes à reconnaître, même si anglais. | Keep control labels ; explain Instrumental, Vocal, Drums nearby | Garder les commandes ; expliquer Instrumental, Voix, Batterie à proximité | `app/ui/web/stems-listen.js:10`, `app/ui/web/rx3-mock.js:392` · S6/S10 ; **ne pas traduire la commande matérielle** |
| Alignment, correlation / calage, corrélation | Il doit savoir si le son commence au bon endroit. | Stem may not line up with the track | Le stem peut ne pas être calé avec le morceau | `app/localization/en.json:326`, `app/localization/fr.json:326` · S7 |
| Gain factor / facteur de gain ; normalization / normalisation | Rapport numérique sans seuil d’écoute. | Export again at the original level, without processing | Réexportez au niveau d’origine, sans traitement | `app/localization/en.json:328`, `app/localization/fr.json:328` · S7 ; chiffres en détails |
| Residual energy / énergie résiduelle | Aucune conclusion DJ fiable à tirer seul de la valeur. | Listen to the instrumental ; analysis details | Écouter l’instrumental ; détails de l’analyse | `app/localization/en.json:334`, `app/localization/fr.json:334` · S7 ; valeur conservée |
| Audio frames / trames ; encoder padding / décalage de l’encodeur | Détails de longueur/calage, pas un geste dans rekordbox. | Export the full track with the same start and end | Réexportez le morceau complet avec le même début et la même fin | `app/localization/en.json:324`, `app/localization/fr.json:324`, `app/localization/en.json:333`, `app/localization/fr.json:333` · S7 |
| Lossless / sans perte ; subtraction / soustraction | Le DJ doit choisir un format d’export, pas comprendre le calcul. | Export as WAV, AIFF or FLAC without lossy compression | Exportez en WAV, AIFF ou FLAC, sans compression avec perte | `app/localization/en.json:322`, `app/localization/fr.json:322` · S7 ; formats et contrainte conservés |
| Time stretching / étirement temporel | Terme à relier à une action musicale. | Export again without changing track length or tempo | Réexportez sans modifier la durée ni le tempo du morceau | `app/localization/en.json:327`, `app/localization/fr.json:327` · S7 |
| Clipped to 16 bits / écrêtés en 16 bits | Il a besoin de savoir quoi écouter, pas compter les échantillons. | Clipping detected ; listen for distortion | Écrêtage détecté ; vérifiez à l’écoute l’absence de saturation | `app/localization/en.json:288`, `app/localization/fr.json:288` · T5 ; nombre/format dans les détails, terme « échantillon » technique conservé |
| Error code / code du moteur | Ne dit pas quoi faire. | Stem preparation stopped ; error details | La préparation des stems s’est arrêtée ; détails de l’erreur | `app/localization/en.json:443`, `app/localization/fr.json:443` · T5 |
| RX3_STEMS, original/source file, collision | Renommer des fichiers à la main sort du parcours DJ. | Track name ; “Two tracks use the same exported name” | Nom du morceau ; « Deux morceaux ont le même nom dans l’export » | `app/localization/en.json:436`, `app/localization/fr.json:436`, `app/localization/en.json:446`, `app/localization/fr.json:446` · T5 ; ne pas inventer une résolution automatique |
| Bank / banque ; active bank / banque active | Banque comprise après explication ; active doit désigner ce qui jouera. | Bank used on the deck | Banque utilisée sur la platine | `app/localization/en.json:104`, `app/localization/fr.json:106`, `app/ui/web/samples.js:524` · A3 |
| Initial volume / volume initial | Initial à quel moment ? | Volume when the bank loads | Volume au chargement de la banque | `app/localization/en.json:108`, `app/localization/fr.json:110` · A6 |
| RGB, #RRGGBB ; ASCII, underscore | Contraintes informatiques de saisie. | Choose a colour ; name example “Set-1” | Choisissez une couleur ; exemple de nom « Set-1 » | `app/localization/en.json:191`, `app/localization/fr.json:193`, `app/localization/en.json:189`, `app/localization/fr.json:191`, `app/samples/bank.py:341` · T5 ; préserver la validation existante |
| Classic / Classique ; canvas dimensions | Le DJ voit une zone, pas une toile de pixels. | Centre area / Full width | Zone centrale / Pleine largeur | `app/localization/en.json:372`, `app/localization/fr.json:372`, `app/ui/web/logo.js:311` · L3 |
| Invert greys / inverser les gris | Peu parlant sans résultat montré. | Adapt whites and greys for a light screen | Adapter les blancs et gris à l’écran clair | `app/localization/en.json:369`, `app/localization/fr.json:369` · L3 ; garder l’explication exacte et l’aperçu |
| Core / decoder-sleep / decoder wait / CPU wakeups | Noms de mécanismes sans choix musical à faire. | Shared components / Audio recovery after a Beat Jump | Composants communs / Reprise audio après un Beat Jump | `mod/modules/core/manifest.json:4`, `mod/modules/decoder-sleep/manifest.json:8` · M4 |
| Logging / journal / verbose / diagnostics | Dépannage présenté comme fonction de mix. | Troubleshooting report / Detailed troubleshooting report | Rapport de dépannage / Rapport de dépannage détaillé | `mod/modules/logging/manifest.json:4`, `mod/modules/logging-verbose/manifest.json:4` · M4 |
| Telnet, root password / mot de passe root | Manipulation technique réelle ; aucun synonyme ne la rend simple. | Technical troubleshooting access (Telnet) | Accès technique de dépannage (Telnet) | `mod/modules/telnet/manifest.json:8` · M4 ; détails et conditions d’usage conservés |
| Terminal, source folder, command / terminal, dossier source, commande | Le persona ne sait pas les utiliser. | Technical setup for streaming software | Configuration technique du logiciel de diffusion | `mod/modules/now-playing/manifest.json:40`, `mod/modules/now-playing/manifest.json:47`, `app/ui/web/app.js:490` · M3 ; commandes conservées dans les détails |
| UDP port, firewall, JSON / port UDP, pare-feu, JSON | L’intégration suppose des compétences hors persona. | Connection details for the streaming software | Détails de connexion du logiciel de diffusion | `mod/modules/now-playing/manifest.json:41`, `mod/modules/now-playing/manifest.json:48` · M3 ; valeurs techniques conservées |
| Overlay | Le résultat utile est le titre affiché dans le stream. | Track-title display in your stream | Affichage des titres dans votre stream | `mod/modules/now-playing/manifest.json:8` · M3 ; ne pas promettre que l’app le produit |
| Energy Boost +2/+7, Experimental +4 | Peut être confondu avec un nombre de demi-tons. | Energy Boost · +2/+7 Camelot ; Experimental · +4 Camelot | Energy Boost · +2/+7 Camelot ; Expérimental · +4 Camelot | `mod/modules/key-match/manifest.json:39` · M2 ; conserver l’avertissement musical existant |
| Transposition maximale | Terme musical possiblement connu ; le nombre doit garder sa référence. | Maximum key shift (semitones) | Transposition maximale (demi-tons) | `mod/modules/key-sync/manifest.json:34`, `mod/modules/key-sync/manifest.json:44` · M2 |
| Reconnect / Reconnecter | Il cherche une connexion physique inexistante. | Try again | Réessayer | `app/localization/en.json:383`, `app/localization/fr.json:383` · O5 |
| Stock / uninstall / restore / reflash | Le DJ veut retrouver ses fonctions d’origine. | Use the deck without modules | Utiliser la platine sans modules | `README.md:308` et absence d’aide dans `app/ui/web/index.html:63` · R1 |

### Termes du brief qui ne doivent pas devenir de faux constats

- **Sidecar / fichier sidecar (`.rx3stem`)** est dans `.claude/STYLE.md:25`, mais aucun libellé principal actuel des catalogues ou du frontend inspecté n’emploie « sidecar ». Ne pas prétendre qu’un écran le demande. **Évolution explicite du glossaire proposée pour la prose grand public :** EN **stem file** / FR **fichier de stems**, avec extension exacte seulement dans les détails. Conserver « fichier sidecar » comme terme technique lorsque nécessaire. Ne pas en déduire qu’un format unique est encore utilisé partout.
- **exFAT / FAT32** figurent dans les prérequis du README (`README.md:74`), pas dans un sélecteur de formatage des cinq écrans inspectés. Ne pas inventer ce sélecteur ni ajouter un formatage. Si ces termes doivent être montrés : EN **USB drive format supported by the XDJ-RX3 (FAT32 or exFAT)** / FR **Format de clé USB accepté par le XDJ-RX3 (FAT32 ou exFAT)**, en conservant les noms exacts et sans promettre une compatibilité externe nouvellement vérifiée.
- **Déchiffrement** décrit le besoin dans le brief ; le remplacement officiel n’est pas proposé. Garder **encryption key / clé de chiffrement** dans les textes, accompagnés de l’explication K2. Ne pas employer « clé d’activation » : cela inventerait un mécanisme de licence.
- **BPM, tonalité, hot cue, pad, sample, stems, export rekordbox** sont le vocabulaire du persona : conserver. « Sample » reste le son du pad ; « échantillon » reste l’unité audio technique (`.claude/STYLE.md:22`). Pour **deck**, conserver DECK 1/DECK 2 comme libellés d’écran ; « platine » désigne l’appareil complet. Compléter le TODO du glossaire devra préserver cette distinction.
- **Power cycle**, encore TODO (`.claude/STYLE.md:28`) : **évolution explicite proposée du glossaire**, EN **turn the deck off and on again** / FR **éteignez puis rallumez la platine**. La procédure de retour à l’origine inclut aussi l’arrêt de lecture et le retrait de la clé, R1.

## Cohérence FR/EN et chaîne documentaire

Les phrases proposées au DJ sont au vouvoiement ; les boutons emploient l’infinitif. **rekordbox**, **XDJ-RX3**, noms de formats et libellés matériels restent exacts. Les autres capitales conservées dans les aperçus sont des repères d’écran, pas des chaînes oubliées à traduire. La coquille visible « Share informations… » de `mod/categories.json:64` peut devenir EN **« Share track information with your computer. »** ; FR actuel **« Partagez des informations sur le contenu en cours de lecture avec un ordinateur. »** → **« Transmettez les informations du morceau à votre ordinateur. »**. Ce correctif P3 · S relève de M3 et ne change pas la capacité annoncée.

Les libellés changés doivent être reportés dans leurs renvois : `modules.needOutput`, `stems.needOutput`, `stems.needRuntime`, `logo.buildHint`, `stems.drumsModelPreset`, `stems.drumsModelImport`, `stems.drumsModelUnknown`, `stems.cpuFallback`, `error.key`, `error.keySyncMode`. Exemple de renvoi final : **FR « Sélectionnez la clé USB ou le dossier où enregistrer les fichiers. » / EN « Select the USB drive or folder where you want to save the files. »**, suivi du lien direct **« Choisir la destination » / « Choose destination »** ; pour l’installation, lien direct vers **« Installation et stockage des stems » / « Stem setup and storage »**. Ne pas faire chercher au DJ un ancien nom de bouton.

Le README promet une préparation simple sur USB et un retour à l’origine par extinction/retrait/redémarrage (`README.md:8`, `README.md:308`), mais cite encore des onglets « Stems preparation » et « Modules installation », un choix manuel du firmware et des rôles/pads différents (`README.md:150`, `README.md:217`, `README.md:298`). Cette divergence documentaire ne justifie pas de rajouter ces anciennes étapes à l’UI. **Recommandation éditoriale associée à S10, P1 · M :** nommer les destinations actuelles, décrire la compatibilité affichée plutôt qu’un sélecteur absent et publier une seule consigne matérielle validée. Le présent audit ne réécrit aucun de ces fichiers.

## Vérifications de lecture à effectuer après une éventuelle implémentation

Ces critères sont des objectifs de validation, **pas des tests effectués**. Ils restent dans les opérations existantes et peuvent d’abord être vérifiés avec des données locales de présentation, sans écrire sur une clé réelle.

| Situation présentée au DJ | Réussite attendue en moins de 30 secondes | Constats concernés |
|---|---|---|
| Première ouverture sans clé de chiffrement | Il explique pourquoi une préparation initiale est demandée, trouve sa langue et sait la différer ou lire les conditions. | O1, K1–K4 |
| Deux clés USB, puis changement de sélection | Il nomme la source musicale et la destination réelle de chaque écran, sans deviner à partir d’un chemin seul. | O2–O4 |
| Modules choisis, aucun fichier encore préparé | Il distingue sélection et présence sur USB, et trouve l’action suivante. | M1–M5 |
| Installation Stems absente | Il voit l’installation avant les réglages et comprend la limite si Python manque. | S1 |
| Playlist longue, un morceau refusé | Il voit le nombre de morceaux concernés, règle voix/batterie et qualité, et identifie le morceau à corriger. | S2–S4, S8–S9 |
| Préparation Stems terminée | Il écoute un morceau sans importer un fichier, comprend les stems audibles et le bouton Original. | S5–S7 |
| Aperçu tactile/pads | Il retrouve les mêmes rôles et comprend toucher versus maintenir/glisser sans attendre plusieurs boucles. | S10, T3 |
| Logo cadré | Il sait que le logo est préparé localement et où demander son écriture sur la clé. | L1–L3 |
| Sample ajouté au pad 1 | Il retrouve ce pad sélectionné, peut l’écouter, voit la banque utilisée et le statut du module Samples. | A1–A6 |
| Téléchargement interrompu puis réussi | Il retrouve l’action de réessai, lit les conditions, comprend le résultat et reprend volontairement Modules. | K5–K8 |
| Retour à l’origine | Il distingue retrait des modules de l’USB, suppression de la clé de chiffrement et extinction/redémarrage de la platine. | R1 |
| FR/EN, clair/sombre, 880 × 560 et 1180 × 820 | Il retrouve action, motif de blocage et destination sans texte coupé ni déplacement dû à un rafraîchissement ordinaire. | O5, T1–T5 |

L’état actuel dispose déjà des bons objets DJ — export USB, playlists, pads, stems et aperçu RX3. La priorité est de rendre leur enchaînement évident, de montrer ce qui a réellement été enregistré et de réserver les détails informatiques aux endroits où ils aident à résoudre un problème.


## Mise en œuvre autorisée — 27 septembre 2026

L’instruction « applique toutes ces recommandations » autorise la mise en œuvre après l’audit. Les références de lignes ci-dessus décrivent l’état audité ; elles ne sont pas renumérotées après les modifications. Cette section décrit le résultat. Aucune dépendance, aucun framework, aucun service audio ni contrat Python↔JS n’a été ajouté ou modifié. Aucun commit, téléchargement de clé, accès réseau ou essai sur clé USB réelle.

### Correspondance avec les constats

| Constat | Mise en œuvre dans l’interface |
|---|---|
| O1 | Phrases d’usage affichées sous les titres ; instructions de décision en 14 px. |
| O2 | Nom de la clé, pictogramme USB, accès au contenu et état actif dans la barre latérale ; emplacement complet dans l’inspection. |
| O3 | Choix de destination contextualisé et aide expliquant de sélectionner le nom de la clé, sans entrer dans ses dossiers. |
| O4 | Destination effective auprès de la préparation Modules ; divergences avec la clé du contexte signalées dans Modules et Stems. Les choix existants restent conservés. Source musicale et destination des stems distinctes. |
| O5 | Vocabulaire de démarrage local, secours FR/EN avant chargement des catalogues et message propre aux images. État initial couvrant la zone de travail, sans bandeau de connexion courant. |
| O6 | Musique en premier, export illisible explicite, noms localisés des modules et historique du dernier démarrage replié. |
| M1 | Modules « sélectionnés », destination visible, préparation USB ou fichiers selon la destination connue ; sélection et présence sur USB restent distinctes. |
| M2 | Réglages affichés pour les modules sélectionnés, relations repliées, référence MASTER et pas Camelot explicites, bouton Voir dans BROWSE. |
| M3 | Limite de l’intégration de diffusion explicite ; commande et configuration conservées dans un guide replié. |
| M4 | Noms métier pour composants et dépannage ; inclusion automatique indiquée pour Core. Le groupe reste « Composants et réglages techniques », car decoder-sleep demeure sélectionnable : le renommer entièrement « Composants inclus » aurait été trompeur. Détails et accès technique conservés. |
| M5 | Aide locale MENU (UTILITY), sans indicateur fictif de détection de la platine. |
| S1 | Installation nécessaire remontée avant la musique ; état traduit et détail brut conservé. Retour en bas quand les outils sont prêts. |
| S2 | Export USB au premier niveau ; XML sous Autre source musicale. |
| S3 | Parties et qualité avant les formes d’onde ; détails des morceaux compatibles et formes d’onde déjà prêtes repliés. Refus et actions restent visibles. |
| S4 | Compromis de qualité en première phrase, modèle et restrictions dans les détails. Choix matériel explicites et repliés ; valeurs et défauts conservés. |
| S5 | Choix du morceau et écoute communs aux deux vues, indépendants de l’import ; accès depuis le résultat de préparation. |
| S6 | Source distincte des commandes, couleurs INST/VOCAL/DRUMS, indication du geste et temps mm:ss. Original ne fait plus apparaître les rôles comme simultanément sélectionnés. Le masque audio envoyé reste inchangé. |
| S7 | Voix obligatoire, batterie facultative ; conseil d’écoute après import, mesures techniques conservées dans un dépliant. |
| S8 | Renvois vers les intitulés réels, notamment modes de stems, KEY SYNC et installation. |
| S9 | Bilan des morceaux préparés et à vérifier ; import compté comme un résultat ; détails séparés. Barre masquée après annulation ou échec. |
| S10 | Guides tactiles également disponibles dans Stems et Samples, légende permanente et étapes manuelles. Ancienne cartographie contradictoire à quatre stems retirée du README et mention 7/8 non établie retirée du glossaire. Réserve matérielle détaillée ci-dessous. |
| L1 | Cadrage désactivé tant qu’aucune image n’a été choisie ; explication visible. |
| L2 | Continuer dans Modules devient l’action principale après choix ; remplacement secondaire, aucune écriture automatique. |
| L3 | Silhouettes de zones, dimensions en détails, libellés explicites, zoom à une décimale ; molette réservée au cadrage lorsque l’aperçu a le focus. |
| A1 | Inspecteur voisin de la grille à la taille par défaut ; sélection d’un pad vide amène le contrôle d’ajout en vue. Volume de banque et SHIFT après l’éditeur. |
| A2 | Après ajout, sélection conservée sur le premier pad rempli ; message du pad ou de la plage ajoutée. |
| A3 | Banque utilisée nommée, état d’enregistrement distinct, suffixe lisible dans le sélecteur, motif de sauvegarde avant activation. Activation existante conservée. |
| A4 | Présence du module Samples sur la clé distinguée de sa sélection pour la prochaine préparation ; accès à Modules si nécessaire. |
| A5 | Modes Modifier/Jouer explicites ; couleur du pad et état de lecture distincts, nom accessible de lecture, Tout arrêter conservé. |
| A6 | Son puis extrait/écoute, mode, nom/couleur et niveau ; groupe extrait/écoute côte à côte dans l’inspecteur large. Nouvelles banques localisées, volumes en %. |
| K1 | But de la préparation initiale avant les conditions ; Plus tard ferme sans récupérer la clé. |
| K2 | Distinction fichier de chiffrement / support USB, explication et pictogrammes différents ; taille du téléchargement initial affichée. |
| K3 | Langue accessible dans la modale, corps utilisant la hauteur disponible, actions conservées en bas. Changement de langue réinitialise lecture et consentement. |
| K4 | Trois intertitres ajoutés ; les sept paragraphes juridiques et le libellé d’acceptation restent strictement identiques à l’état avant intervention. Réconciliation du fond laissée à une validation explicite. |
| K5 | Compteurs de transfert existants affichés en Mo/MB décimaux ; phase de récupération indéterminée conservée, sans pourcentage inventé. |
| K6 | Réessai explicite réouvrant les conditions ; annulation confirmée distinguée de la demande ; erreurs lisibles avec archive et raison conservées dans les détails. Accès à la tâche en cours en cas d’occupation. |
| K7 | Clé prête puis Continuer dans Modules ; aucun enchaînement automatique vers une écriture USB. |
| K8 | État disponible distingué du fichier manuel ; gestion avancée repliée, choix manuel et récupération toujours accessibles. Suppression limitée à la clé conservée, avec confirmation expliquant sa portée. |
| T1 | Apparence de l’application, module Thème clair et fond de l’aperçu nommés séparément. |
| T2 | Une erreur d’opération rattachée à son écran ; détails consultables ; disparition des annonces de lecture USB et sauvegarde de banque qui doublaient les états du contenu. Progression à sa place, messages globaux hors de sa zone. |
| T3 | Icône Samples 2 × 4 ; couleurs des rôles harmonisées ; SVG Key Match conservés ; temps 1:07 corrigé. |
| T4 | Corps et instructions utiles en 14 px ; inspecteurs côte à côte à 1180 px. À largeur minimale, Modules commence par les choix, avec destination et action dans l’en-tête. |
| T5 | Présentation décimale correcte des tailles et du stockage ; vocabulaire des copies locales, fichiers de stems, raccourcis et récupération après erreur. Les clés de traduction diagnostiques conservent leurs paramètres pour ne pas perdre les données remontées par Python. |
| R1 | Retrait des modules nommé et confirmé ; conservation musique/stems/banques expliquée ; nombre de fichiers en détail et gestes de retour à la platine sans modules dans une aide distincte. |

### Vérifications réalisées

- **41 tests réussis** : `tests.test_localization`, `tests.test_key_sync_settings`, `tests.test_stems_screen`, `tests.test_module_consistency`, `tests.test_docs_hygiene`. Les scénarios Node `sample_preview.cjs` et `stems_preview.cjs` se terminent également sans erreur.
- **84 configurations de rendu natif pywebview** : FR/EN, clair/sombre, fenêtres demandées 880 × 560, 1180 × 820 et 1440 × 900, six surfaces et seconde vue Stems. La zone web réelle mesure 32 px de moins en hauteur, à cause du titre natif. Aucun débordement horizontal, cible inférieure à 28 px, contrôle de formulaire sans nom ou clé de traduction non résolue détecté dans cette matrice.
- **43 contrôles de parcours réussis** : installation préalable simulée, destination divergente, ajout de sample, fichier de clé manuel, consentement et changement de langue, transfert/échec/annulation/succès, préservation des brouillons, confirmations destructives, contrats de préparation et d’import. Aucun appel d’écriture automatique après succès de récupération de clé.
- Contrastes des couples de texte/surface testés au seuil 4,5:1. Le détecteur Impeccable a signalé une animation de largeur sur la barre de progression ; cette transition a été retirée.
- Comparaison exacte des sept paragraphes légaux et de l’acceptation EN/FR avec la copie de travail avant intervention : identiques.
- Les changements de traductions des modules restent dans leurs manifests. Aucun changement aux fichiers de services, au bridge ou au traitement audio.

Preuve reproductible : [banc natif hors ligne](../app/ui/web/design-audit/verify_ui.py), [résultats de la validation](../app/ui/web/design-audit/dj-verification.json). Le banc utilise exclusivement des réponses simulées, hormis les métadonnées locales autorisées par sa liste blanche. La première passe a détecté le champ de stockage trop étroit ; la confirmation a rendu les 84 configurations sans anomalie. Une correction du scénario de test (sauvegarder son sample avant de changer de clé) a ensuite permis de terminer les contrôles fonctionnels avec `--flows-only`, en conservant la matrice de rendu de confirmation. Les empreintes des sources finales sont enregistrées avec les résultats.

### Limites maintenues volontairement

**K4 — fond juridique.** L’audit ne propose pas de version juridique réconciliée. Les écarts EN/FR et l’absence de NOTICE restent à résoudre avant une publication de nouvelles conditions. L’intervention porte sur la lecture et l’accès au consentement, pas sur les obligations.

**S10 — référence matérielle.** Aucune validation sur XDJ-RX3 n’a été réalisée. Les numéros présents dans le guide existant ne constituent donc pas une nouvelle référence matérielle validée. L’aide ajoutée dans Stems reprend le geste tactile établi dans les textes du dépôt, sans ajouter une cartographie numérotée. README et glossaire n’affirment plus la cartographie ancienne contradictoire.

Les essais natifs automatisés ne valident ni Windows/WebView2, ni une acquisition réseau réelle, ni une clé USB réelle, ni l’audio ou le comportement matériel. La capture d’écran par l’outil de contrôle natif n’a pas été disponible ; les constats de rendu reposent sur les mesures du DOM effectivement peint dans pywebview, pas sur une certification visuelle humaine.


### Corrections après retour visuel

- Modules : deux colonnes défilant indépendamment, y compris à 880 px ; l’aide de désactivation est dans le panneau de droite.
- État USB vide : texte sur toute la largeur ; la colonne d’icône n’est utilisée qu’en présence de l’icône.
- Destination Modules/Stems : suppression du renvoi au bouton inexistant « Parcourir ».
- Aide renommée **Désactiver le mod** : « Éteignez le RX3, connectez la clé USB à l’ordinateur et supprimez le fichier autoexec.bin de la clé USB. Les prochaines utilisations de la clé n’activeront pas le mod. » Version EN correspondante. Cette consigne remplace la précédente aide R1 ; l’opération de retrait des fichiers reste distincte.
- Installation et stockage des stems : section ouverte, matériel et stockage directement accessibles ; seul le diagnostic technique reste repliable. La source musicale n’affiche plus une légende sans source choisie.
- « Sur votre XDJ-RX3 » renommé **Tutoriel**, et **Tutorial** en anglais.

Validation de cette correction : **13 tests ciblés réussis**, puis nouvelle matrice native complète de **84 configurations sans anomalie** et **56 contrôles de parcours réussis**, dont le défilement indépendant dans les 12 combinaisons taille/langue/thème. Les résultats et empreintes des sources sont actualisés dans `app/ui/web/design-audit/dj-verification.json`. Aucun réseau, téléchargement ou support USB réel utilisé.


### Régression de hauteur des catégories Modules

La capture utilisateur a révélé une lacune dans la validation précédente : l’absence de débordement horizontal ne garantissait pas que les options restaient visibles. Dans la nouvelle colonne à hauteur contrainte, les lignes automatiques de la grille se comprimaient ; les catégories masquaient alors leurs options avec `overflow: hidden`.

Correction : `#modules .categories { grid-auto-rows: max-content; }`. Chaque catégorie conserve la hauteur de son contenu ; le défilement appartient toujours à la colonne, indépendamment du panneau droit. Le banc vérifie désormais la hauteur intérieure de chaque catégorie ouverte et les limites de ses interrupteurs, dans les 12 combinaisons taille/langue/thème. Résultat : **84 rendus et 80 contrôles réussis**. Les affirmations de validation antérieures ne couvraient pas ce défaut de rognage vertical.


### Tutoriel du logiciel

Ajout demandé d’une destination **Tutoriel / Tutorial** avant Modules dans la barre latérale. Le guide FR/EN explique le choix de la clé, la sélection des modules, la récupération de la clé de chiffrement et l’installation du mod, puis les parcours facultatifs Stems (préparation, import, écoute), Samples et Logo, les réglages et la désactivation. Les raccourcis ouvrent les écrans existants sans déclencher d’opération. Modules reste l’écran initial. Les instructions produit et de disposition sont mises à jour pour cette nouvelle destination.

Validation : six tests de localisation réussis, **96 configurations natives sans anomalie et 95 contrôles réussis**, dont l’ouverture du tutoriel, son raccourci vers Modules et la présence de tous les boutons latéraux dans la fenêtre minimale. Données simulées uniquement ; aucune acquisition de clé ou opération USB réelle.


### Installation intégrée, sans panneau droit

À la demande de l’utilisateur, Modules présente désormais une liste sur toute la largeur. **Installer le mod** ouvre le parcours de destination et de confirmation. Sans fichier de clé disponible, **Continuer** ouvre les conditions existantes ; aucun téléchargement sans accord explicite. Après acquisition, retour à la confirmation d’installation, sans écriture automatique. Le téléchargement reste suivi dans la barre de tâche. Aucun consentement demandé au démarrage. Compatibilité, choix manuel, récupération et suppression de la clé restent accessibles sous Options d’installation. Le tutoriel suit ce parcours ; les retouches utilisateur du texte français hors de ce parcours sont conservées.

Validation : **13 tests ciblés réussis**, **120 configurations natives sans anomalie**, **101 contrôles réussis**. La matrice inclut la fenêtre d’installation avec options fermées et ouvertes aux trois tailles, dans les deux langues et les deux thèmes. Contrôles explicites : absence de demande de clé au démarrage, ouverture de la destination sans clé, consentement depuis l’installation, retour à sa confirmation après acquisition et absence d’installation déclenchée par la seule acquisition. Les essais restent entièrement simulés, sans téléchargement ni support USB réel.


### Menu Installer le mod et simplification USB — 27 septembre 2026

- Entrée permanente « Installer le mod » après Stems : récapitulatif de tous les modules cochés, du logo choisi, des banques de samples et de leur état d’enregistrement, de la source et de la destination des stems, puis destination de l’installation. Le bouton a été retiré de Modules. Les fichiers de stems et les banques restent préparés dans leurs écrans respectifs.
- Suppression complète de l’affichage du dernier démarrage enregistré et des détails techniques dans l’écran USB. Le support sélectionné apparaît sous son nom, sans préfixe « Clé USB ».
- Aide renommée « Désactiver le mod en cas d’urgence » ; procédure de suppression de `autoexec.bin` conservée.
- Validation : 13 tests ciblés ; 120 configurations pywebview simulées (FR/EN, clair/sombre, trois tailles), 105 contrôles de parcours réussis, aucun défaut de rendu détecté par les contrôles. Aucune opération sur une clé USB réelle, aucun téléchargement. Preuve : `app/ui/web/design-audit/dj-verification.json`.


### Logo automatique, Stems simplifié et prévisualisation locale — 27 septembre 2026

- Le choix d’une image active Logo via les règles normales de sélection des modules. Les avertissements d’activation et les renvois vers Modules ont été supprimés. Le canvas Logo reste un outil de cadrage.
- Dans Stems, Ouvrir le XML apparaît à côté d’Ouvrir une clé USB. Suppression du libellé Musique lue depuis, de l’estimation de préparation, du choix de destination, des détails ordinaires des morceaux et du choix de générer les waveforms. Les avertissements de refus ou de capacité restent exploitables ; la préparation cible la clé USB sélectionnée et inclut systématiquement les waveforms.
- Prévisualisation contient le sélecteur Morceau, la waveform entière, les commandes de stems et Lecture/Pause. Suppression des boutons de source, de la barre de seeking séparée et d’Actualiser. Le clic sur la waveform et les touches fléchées/Home/End déplacent la lecture.
- La préécoute charge une fois le morceau et ses pistes, par transferts de dix secondes. Les bascules de gains, la pause et le seeking restent ensuite dans Web Audio, sans reconstruction ni appel Python. Une transition anti-clic de 256 frames accompagne les gains, sans arrêt du transport. La forme d’onde représente le morceau original entier. Les anciennes opérations de préécoute restent disponibles ; trois opérations de session ont été ajoutées pour ce parcours explicitement demandé. Les données temporaires sont locales, libérées après transfert ; le budget de buffers est borné à 1 Gio. Un morceau dépassant ce budget n’est pas prévisualisé.
- Les waveforms de la platine sont déjà calculées sur CPU après finalisation des stems du morceau. Aucun parallélisme entre la séparation d’un morceau et les waveforms du précédent n’a été ajouté ; il demanderait une gestion séparée de la mémoire, des annulations et de la publication.
- Tous les guides matériels existants et leurs mocks ont été déplacés dans Tutoriel. Installation et stockage des stems devient Paramètres avancés, sans volet Détails techniques.
- Validation : 27 tests ciblés distincts réussis (localisation, sélection, écran Stems, préécoute Python/bridge et interactions Web Audio), puis 120 configurations pywebview simulées et 109 contrôles réussis, sans défaut détecté. Les tests audio utilisent uniquement des fichiers temporaires synthétiques ; aucune clé USB réelle, aucun téléchargement ni validation matérielle RX3. Preuve de rendu et de parcours : `app/ui/web/design-audit/dj-verification.json`.


### Correction de la vue Tutoriel — 27 septembre 2026

La vue précédente empilait une notice et des démonstrations séparées, avec une rubrique Samples en double. L’aperçu harmonique avait conservé son comportement de fenêtre flottante. De plus, le rendu des modules reconstruisait les guides et réinitialisait leur progression.

La vue présente désormais un sujet à la fois : Première installation, Samples, Stems, Mixage harmonique, Logo, Diffusion, Réglages ou En cas d’urgence. Chaque sujet réunit ses étapes et ses mocks. L’aperçu harmonique reste dans la page. Le rendu des guides est indépendant des interrupteurs de Modules ; les démonstrations masquées sont arrêtées. Les textes FR/EN correspondent aux parcours actuels, notamment l’activation automatique du logo et les waveforms systématiques.

Vérification : 13 tests ciblés réussis et matrice de rendu étendue à 204 configurations couvrant chaque sujet, les deux langues, les deux thèmes et trois tailles. La fenêtre utilisateur observée conservait une ancienne UI en mémoire ; elle n’a pas été rechargée afin de conserver son état.


### Retour aux tutoriels contextuels — 27 septembre 2026

À la demande de l’utilisateur, l’entrée Tutoriel et sa vue par sujets sont supprimées. Les guides matériels et leurs mocks sont replacés auprès de chaque module ; les écrans Samples, Stems et Logo contiennent leur aide de préparation. Première installation est déplacé dans Installer le mod. La rubrique Modules associés disparaît de l’interface, sans modifier les règles de dépendance qui déterminent la sélection.

Désactiver le mod en cas d’urgence est un titre et un texte permanents dans l’écran USB. La procédure propose, RX3 éteint et clé connectée à l’ordinateur, de renommer autoexec.bin en autoexec.bin.disabled ou de supprimer autoexec.bin. Elle indique comment rétablir le nom d’origine après un renommage.

Validation : 13 tests ciblés réussis ; 156 configurations de rendu simulées couvrant aussi les guides ouverts, sans défaut détecté. Aucun fichier de clé USB n’a été renommé ou supprimé.
