<!-- SPDX-License-Identifier: MPL-2.0 -->
# XDJ-RX3 Toolkit 0.6.0 — hardware acceptance booklet

This booklet contains the complete campaign plan, cases and session sheet moved from `REFERENCES.md`. It is a **plan, not a record of passing RX3 hardware tests**. The editable [CSV](cases.csv), [JSON](cases.json), [read-only collector](collect-readonly.sh) and [fixture generator](prepare-fixtures.py) remain alongside it. Keep build hashes and observed results with each session.

## Contents

- [Campaign plan](#doc-acceptance-0-6-0-readme)
- [Detailed cases](#doc-acceptance-0-6-0-cas-de-test)
- [Session and defect sheet](#doc-acceptance-0-6-0-session)

<a id="doc-acceptance-0-6-0-readme"></a>
## Recette matérielle XDJ-RX3 Toolkit 0.6.0



**Proposition de recette, pas un résultat de validation.** Aucun essai de ce cahier n’a encore été exécuté sur le RX3. Le périmètre contient les 17 modules actuellement déclarés, les améliorations de la 0.6.0 et leurs interactions critiques. Les correctifs locaux non commités font partie du candidat seulement après gel de ses fichiers et de ses hashes.

- [149 cas détaillés](#doc-acceptance-0-6-0-cas-de-test), avec préparation, geste, résultat attendu et preuve.
- [Registre CSV](cases.csv), directement importable dans un tableur; [version JSON](cases.json).
- [Fiche de session et fiche d’anomalie](#doc-acceptance-0-6-0-session).
- [Générateur du corpus synthétique](prepare-fixtures.py), sans accès au RX3 ou à une clé USB.
- [Collecteur Telnet en lecture seule](collect-readonly.sh), à exécuter par l’assistant après identification du lecteur.

<a id="doc-acceptance-0-6-0-readme--1-rpartition-du-travail"></a>
#### 1. Répartition du travail

<a id="doc-acceptance-0-6-0-readme--ce-que-fait-lassistant"></a>
##### Ce que fait l’assistant

1. Identifier l’application à publier et le RX3, figer la génération, construire les profils de modules et préparer les ressources. Conserver les clés, identifiants, bibliothèques et enregistrements privés hors du dépôt public.
2. Générer les signaux étalons et les banques, choisir les morceaux musicaux avec François, préparer les stems, vérifier les paquets et leur association aux fichiers exportés, produire la playlist de recette et l’ordre des essais.
3. Réaliser la préparation dans **l’application empaquetée candidate** pour les tests bout en bout. Un export fait uniquement par les scripts internes ne valide pas le parcours de l’app.
4. Mettre à disposition pour chaque étape le bon build, les morceaux, leurs cues, la banque et les réglages. Naviguer dans l’app/rekordbox depuis l’ordinateur lorsque les outils disponibles le permettent. Si une opération physique ou un dialogue système est inaccessible, annoncer uniquement le geste manquant.
5. Par Telnet : relever processus, readiness, mappings, fichiers installés, logs, mémoire, charge, sockets et générations. Déclencher seulement les actions natives qualifiées pour ce firmware. Rapatrier les preuves sur l’ordinateur.
6. Collecter audio et vidéo, écouter et analyser les captures, contrôler les résultats numériques, consigner le verdict. Un log propre ne remplace jamais l’écoute ou la réponse à un bouton.
7. Préparer le cas suivant, remettre l’état initial et guider François **un test à la fois**.

<a id="doc-acceptance-0-6-0-readme--ce-que-fait-franois"></a>
##### Ce que fait François

- Brancher/débrancher physiquement les supports et l’audio, démarrer/arrêter le lecteur, éjecter les clés selon les instructions.
- Appuyer sur les commandes physiques et tactiles demandées; confirmer ce qui est visible et audible. Une capture écran ne valide ni le tactile ni les LEDs des pads.
- Juger la qualité musicale sur les vrais morceaux : artefacts de séparation, transposition, continuité, ergonomie et lisibilité.
- Signaler immédiatement coupure, gel, mauvaise piste, niveau anormal ou comportement imprévu; ne pas poursuivre machinalement la séquence.

<a id="doc-acceptance-0-6-0-readme--chargement-des-morceaux--capacit--qualifier"></a>
##### Chargement des morceaux : capacité à qualifier

Le dépôt inspecté ne fournit pas de télécommande matérielle validée pour charger arbitrairement un track sur le RX3. **Telnet ne signifie donc pas automatiquement contrôle du transport.** Q-06 qualifie cette possibilité : voie native identifiée, firmware et symboles vérifiés, deux decks arrêtés, trois chargements corrects par deck, vérification de l’ID réellement chargé.

Si cette qualification passe, l’assistant charge/prépositionne les morceaux hors cas testant justement LOAD/BROWSE. Sinon, l’assistant prépare la playlist et indique « BROWSE → RECETTE / 01_TRANSPORT → Q01, puis LOAD 1 ». François effectue ce geste; aucune injection d’adresse supposée, aucun protocole d’émulateur présenté comme disponible sur le RX3.

Même règle pour les captures : photo/vidéo externe par défaut. Une capture d’écran distante n’est ajoutée qu’après qualification d’une méthode en lecture seule, avec format/stride connus; aucune écriture du framebuffer et aucun lecteur concurrent du périphérique d’événements des pads.

<a id="doc-acceptance-0-6-0-readme--2-contrat--figer-avant-les-essais"></a>
#### 2. Contrat à figer avant les essais

Q-07 est un contrôle produit, pas une formalité. Les README anciens ne constituent pas tous le contrat actuel.

| Point | Attente de recette et source actuelle |
|---|---|
| Préparation Stems | VOCAL + DRUMS systématiques; INST reconstruit. Aucun choix qualité/modèle. `app/services/stems.py`, `app/ui/web/stems.js`. Les anciens paquets vocal seul restent une compatibilité de lecture, pas un mode de préparation proposé. |
| Réglage des niveaux Stems | Bouton combiné : tap pour activer/couper; maintien 350 ms puis glissement pour niveau. Vérifier cette interaction, pas d’anciennes vues ON/OFF et LEVEL décrites dans des notes antérieures. `rx3_stems_panel.h` et services de panneaux. |
| Key Match | Le moteur actuel applique **+2, +7, +4 dirigés**, à lettre identique, avec priorité aux correspondances natives vertes. Le brouillon de release contient « +/- ». Décider/corriger cette divergence avant de valider KM-03; ce n’est pas une différence rédactionnelle anodine. `core/api/rx3_harmony.h`. |
| MASTER / Key Sync | Référence locale MASTER, jamais « l’autre deck » supposé. En l’absence d’un snapshot natif actuel, le code récent utilise un fallback classique lorsque la référence est connue; un snapshot natif valide prévaut. Clé ou MASTER inconnus : pas d’action. Contrôler avant/après BROWSE et changement de MASTER. |
| Panneau vs mode physique | Le README Samples récent annonce que changer de mode physique modifie le routage sans fermer le panneau et conserve les sons; l’ancienne matrice d’onglets annonce un retour d’affichage natif. Fixer le contrat exact du candidat, puis UI-04/SA-05 le vérifient. |
| Retrait du Core | Le plan de réinsertion signale une migration de retrait encore à établir. USB-08 doit démontrer le retour stock réel, ou une obligation explicite de redémarrage complet; pas de succès d’interface laissant l’ancien mod actif. |
| Decoder wait | Recevoir une réponse UDP n’atteste pas que 100 µs sont appliquées. Relecture de valeur uniquement si disponible et identifiée. Sinon distinguer transport validé, valeur non vérifiée et mesure audio comparative. |
| Éjection et verbose | Des textes anciens exigent l’arrêt du lecteur, d’autres l’éjection. Vérifier l’état des handles et le retrait propre; documenter la procédure réellement sûre pour chaque mode. Aucun arrachage à chaud pour le tester. |
| Gains/performance | Ni « zéro latence », ni « audio identique » par défaut. Conserver des mesures et des seuils arrêtés avant verdict, en comparant la même source, le même trajet audio et le même firmware. |

Une divergence produit non résolue reste **BLOQUÉE**, même si le code fonctionne exactement comme il a été écrit.

<a id="doc-acceptance-0-6-0-readme--3-banc-et-prrequis"></a>
#### 3. Banc et prérequis

L’assistant remplit Q-01 avec les éléments disponibles avant le premier test matériel :

- RX3 identifié, version réelle 1.19 ou 1.20. Si les deux sont revendiquées pour la release, conserver des résultats séparés. Aucun flash/changement de firmware implicite dans ce cahier.
- Ordinateur et application candidate identifiés par OS, architecture, version, hash et date. Une réussite sur macOS ne valide pas Windows/Linux ni les autres binaires distribués.
- USB-B direct pour Telnet/Now Playing; adresse découverte à chaque session. Accès Telnet fourni par le propriétaire, non inscrit dans les preuves publiques. Aucun réseau de salle partagé.
- U1 : clé dédiée au candidat et aux médias de recette. U2 : clé musicale de test pour continuité et double montage. U0 : secours sans `autoexec.bin`, dont la lecture stock a été vérifiée. Copie de sauvegarde des trois états côté ordinateur.
- Casque et écoute à niveau modéré; enregistrement stéréo indépendant de préférence par sortie du RX3 vers une interface audio. Si capture USB utilisée, vérifier qu’elle ne change pas le mode du lecteur et qu’elle coexiste avec le lien diagnostic. La fonction d’enregistrement interne sur U1 n’est pas utilisée pendant les essais d’éjection.
- Vidéo cadrant écran, boutons et LEDs, avec un son/repère commun à la capture audio. Sans entrée audio de capture disponible : verdict audio perceptif possible, **mesures audio BLOQUÉES**, jamais inventées.
- Marge libre sur ordinateur et clés. Les gros jeux de limites sont dimensionnés à partir du code courant; l’assistant affiche leurs tailles avant création. Pas d’allocation volontaire épuisant la RAM du lecteur.

<a id="doc-acceptance-0-6-0-readme--4-corpus-prpar-par-lassistant"></a>
#### 4. Corpus préparé par l’assistant

Le générateur fourni crée des WAV déterministes, leurs hashes, un CSV de métadonnées et les consignes de banque. Il n’écrit **ni base rekordbox ni clé USB**. Une source audio seule ne devient pas une piste analysée/exportée par magie.

| Jeu | Contenu / usage | Préparation complète avant test |
|---|---|---|
| Q01 | 120 BPM, 64 s, impulsions repérant les temps, marqueur chaque 32 temps, référence tonale | Importer/analyser dans bibliothèque de recette; grille vérifiée à 0, cues à 0/16/32/48 s. Tempo initial 0. |
| KEY24 | 24 accords synthétiques A/B, 8 s chacun; clés Camelot attendues enregistrées | Renseigner/vérifier les clés exportées, sans confondre résultat d’auto-analyse et oracle. Playlist dédiée et piste sans clé. |
| SYN3 / IM | Mix connu = composante « vocal » tonale + transitoires « drums » + basse INST; fichiers séparés strictement alignés | Import manuel des rôles via l’app, export du paquet et preview; oracle mathématique connu. Ce jeu teste routage/gain/synchro, **pas la qualité d’une IA sur de la musique**. |
| M01/M02/M03 | Morceaux musicaux possédés par François : voix exposée, percussions/transitoires, basses/pads stéréo; 44,1 et 48 kHz, formats réellement utilisés | Sélectionner avec François, préparer via la politique fixe de l’app, écouter la séparation; noter track ID, durée, BPM, clé, gain et chemins exacts. Aucun nom de bibliothèque personnelle inventé. |
| SORT | Au moins 100 entrées sur plusieurs pages : BPM 80/100/128/140, durées différentes, titres/artistes longs, doublons, accents et champs vides | Générer l’oracle de tri depuis les métadonnées réellement exportées; préserver l’ID par ligne. Utiliser le comparateur natif comme référence pour collation/nulls/key plutôt qu’un tri lexical arbitraire. |
| SEARCH | NIÑO, CORAZÓN, Bébé, Straße, Ð/Þ, casse et témoins sans accents | Exporter et vérifier leur indexation stock, puis test du module. ß est replié vers un S; ne pas promettre SS ou translittération universelle. |
| B1/B2 | 8 sons identifiables, modes once/hold/loop/latch, couleurs distinctes, gains 0/50/100/200, volume défaut 50; SHIFT silence ON/OFF | Créer/sauver/activer depuis l’app; relire settings et WAV exportés. Son long 9 s destiné au test de troncature à 8 s. |
| VIS | Logo transparent avec bordures, variante claire, image sombre, pochettes colorées et gradients | Préparer par l’éditeur Logo et comparer preview/fichier; variantes invalide/missing uniquement sur copie dédiée. |
| LIMIT | Paquets valides près des limites calculées, paire dépassant ensemble 512 MiB; versions tronquée/CRC invalide/legacy | Générer après lecture des limites exactes de la génération; ne jamais altérer les originaux. L’app doit refuser les cas hors limites; les fixtures négatives ont un chemin séparé clairement marqué. |

Playlists ordonnées : `RECETTE/01_TRANSPORT`, `02_KEY24`, `03_STEMS`, `04_SORT`, `05_SEARCH`, `06_LIMITES`. Noms et ordres figés dans le manifeste. L’assistant garde une fiche par piste : ID dans l’export, chemin réel, SHA-256 audio/paquet, durée exacte, cues, grille et résultat attendu.

Pour chaque clé : vérifier `PIONEER`/base exportée, audio, paquets associés et banques sous `RX3_RUNTIME/samples/banks` selon le format effectivement écrit par l’app. La vérification porte sur les chemins réels; ne pas deviner l’association par le seul basename.

<a id="doc-acceptance-0-6-0-readme--utilisation-du-gnrateur"></a>
##### Utilisation du générateur

```sh
python3 docs/acceptance/0.6.0/prepare-fixtures.py --output local/acceptance/0.6.0/fixtures
```

Il refuse d’écraser un dossier existant. Les médias synthétiques générés restent sous `local/`, ignoré par Git. L’export rekordbox, les stems et les banques demeurent **À PRÉPARER** jusqu’à vérification sur la clé; leur génération source seule ne valide pas Q-08.

<a id="doc-acceptance-0-6-0-readme--5-profils-dinstallation"></a>
#### 5. Profils d’installation

Chaque profil possède son manifest et ses hashes. Ajouter les dépendances du manifest courant, sans se fier aux anciennes descriptions. Les deux modules Beat Jump dépendent actuellement de `decoder-sleep`; ils ne dépendent pas l’un de l’autre.

- **STOCK** : démarrage sans mod, référence audio/UI.
- **DIAG** : Telnet + logging, puis Core si nécessaire à l’inspection. Logging verbose seulement dans les tests qui le demandent.
- **MIN-module** : chaque module isolé avec ses seules dépendances, plus diagnostics temporaires. Inclut Logo seul et Theme seul avec Core, Key Match seul, Key Shift sans Key Sync, decoder seul, chaque Beat Jump seul.
- **COMPLET** : toutes les fonctions DJ, Telnet et logging simple pour les mesures; verbose dans un sous-test séparé.
- **FINAL** : exactement le profil qui sera utilisé/publié, sans Telnet ni logs non demandés. Les checksums du core doivent être reliés au même candidat; si des options de compilation le changent, c’est un artefact distinct à identifier.
- **ERREUR** : copies de test invalides, uniquement pendant fenêtre idle et avec secours vérifié. Ce n’est pas un profil à livrer.

Les huit variantes ci-dessous sont toutes obligatoires dans UI-01, avec Key Sync non sélectionné sauf test dédié afin de ne pas réintroduire Key Shift par dépendance :

| Variante | KEY | STEMS | SAMPLES | Attente principale |
|---|---|---|---|---|
| TAB-000 | non | non | non | ZOOM/GRID natifs, STATUS et BEAT FX |
| TAB-001 | non | non | oui | ZOOM/GRID natifs et SAMPLES |
| TAB-100 | oui | non | non | KEY pleine largeur, STATUS accessible |
| TAB-101 | oui | non | oui | KEY pleine largeur et SAMPLES |
| TAB-010 | non | oui | non | STEMS pleine largeur, STATUS accessible |
| TAB-011 | non | oui | oui | STEMS pleine largeur et SAMPLES |
| TAB-110 | oui | oui | non | KEY/STEMS séparés, STATUS accessible |
| TAB-111 | oui | oui | oui | KEY/STEMS séparés et SAMPLES |

Pour chaque variante : capture avant/après touche, retouche de l’actif, bords, bande inférieure et contrôle BEAT FX. Une case CSV parent ne suffit pas : créer les résultats `UI-01/TAB-000` à `UI-01/TAB-111`.

Autres combinaisons obligatoires : Browse seul / Key Match seul / ensemble; Key Shift seul / trio Sync; Stems + Key Shift ± + MT; Stems + Samples quatre voix; Theme + Logo + chaque mode waveform; tous modules + double deck + tri. Ce périmètre couvre les interactions identifiées, pas les 2^17 sous-ensembles possibles.

<a id="doc-acceptance-0-6-0-readme--6-ce-qui-est-mesur-par-telnet"></a>
#### 6. Ce qui est mesuré par Telnet

Le collecteur fourni imprime uniquement l’état; l’assistant sauvegarde sa sortie **sur l’ordinateur**. Il ne lit pas l’audio ni la mémoire du processus et n’écrit aucun fichier système. Les lectures peuvent échouer selon le firmware : signaler le manque, ne pas installer d’outil sur le lecteur pour le masquer.

- État initial/final de chaque cas : uptime, PID et starttime, exécutable réel, maps, ready, hash du core, mémoire, nombre de threads/FD, sockets utiles, extraits de logs identifiés.
- Pendant performance/endurance : relever seulement CPU/mémoire/threads/FD à 10 s d’intervalle depuis l’ordinateur; ne pas relancer le collecteur complet (hashes, maps, logs) à cette cadence; CPU calculé à partir des deltas `/proc/stat` et `/proc/PID/stat`, pas d’un seul instantané.
- Température uniquement si une source présente et son unité sont identifiées; aucune adresse ou conversion devinée.
- `ready` + log ne prouvent pas un écran correct : maintenir vidéo et entrée physique utile dans le même cas.
- `readlink` et SHA du fichier disque ne prouvent pas le contenu d’une mapping déjà supprimée : enregistrer device/inode et `(deleted)` dans maps. Une incohérence bloque le verdict de génération.
- Les tests d’échec `mprotect`, hooks détachés avec callbacks en vol, pénurie de RAM artificielle et patch de gardes sont d’abord des tests hôte. **Pas d’injection de faute mémoire dans un RX3 en lecture.** Le matériel vérifie les cycles réels, le refus de ressources invalides et le rétablissement.
- Le test de double lancement USB-11 reste bloqué tant que sa voie d’exécution n’est pas qualifiée. Le shell Telnet n’autorise pas à relancer aveuglément `autoexec.sh` sur un lecteur chargé.

<a id="doc-acceptance-0-6-0-readme--7-critres-dacceptation"></a>
#### 7. Critères d’acceptation

Les seuils ci-dessous sont des **objectifs de recette proposés**, pas des performances déjà mesurées. Q-03 établit le stock; les budgets dépendant de la taille et du support sont figés avant le test concerné. Toute révision ultérieure est motivée et tracée, pas ajustée silencieusement pour faire passer un défaut.

| Domaine | Critère |
|---|---|
| Critique | Zéro crash, OOM, restart non demandé, mauvaise piste, stems du mauvais morceau, corruption USB, audio perdu durablement ou action dangereuse sur le mauvais deck. Un seul événement entraîne NOK/P0. |
| Audio | Zéro dropout/clic nouveau inexpliqué dans les fenêtres étalons et le stress. Capturer le signal, distinguer les silences du média des trous de sortie. Qualité musicale séparément évaluée par François; un son médiocre ne passe pas parce que son buffer est valide. |
| Pitch | À tempo nul, ratio de fréquence attendu `2^(n/12)`; tolérance proposée ±5 cents sur la partie stable, après calibration. Vérifier aussi durée, canaux, transitoires et reset. Les valeurs extrêmes ont une écoute dédiée. |
| Stems | Sur SYN3, composantes attendues seules présentes; alignement avec la référence après compensation d’un délai fixe de capture. Toutes les activées reproduisent le mix à gain nominal dans la tolérance de répétabilité mesurée stock; pas de null test numérique imposé à une sortie analogique. |
| UI | Action simple visible en moins de 250 ms visés, hors chargement documenté; aucun blocage >1 s. Première conversion d’images mesurée séparément; différence visible durable après 5 s au repos = NOK à analyser. Mesurer sur vidéo, pas au ressenti seulement. |
| Chargement | Mesurer 10 charges par famille/taille/support, médiane et pire cas. Fixer le budget après baseline et taille des paquets; ne pas imposer 1 s à un paquet de centaines de MiB. Annulation obsolète observée après fin du read en cours; un read noyau bloqué n’est pas interruptible par ce mécanisme. |
| Mémoire | Après échauffement, fin de 20 cycles retour à un plateau expliqué; pente de RSS positive persistante, threads/FD jamais libérés ou hausse non expliquée >10 MiB = anomalie à analyser. Arène Theme résidente attendue, pas une fuite à elle seule. |
| CPU/thermique | Comparer stock et mod à scénarios identiques; relever moyenne, pics et éventuel throttling. Toute saturation corrélée à un défaut audio/UI bloque. Pas de température universelle arbitraire en l’absence de capteur qualifié. |
| Réinsertion no-op | PID ET starttime inchangés, mêmes ressources actives et continuité audio depuis U2. Une disparition/recréation de PID ne se masque pas derrière un nouveau marqueur ready. |
| Échec | Refus clairement annoncé, ressources cohérentes, prochaine charge saine utilisable. Pas de faux « succès » ou de fallback silencieux à un autre morceau. |

Priorités : **P0** = intégrité, audio, transport ou fonction essentielle; **P1** = autre fonction publiée/qualité d’usage. Tous les cas applicables sont exécutés. Un P1 ne devient pas automatiquement dispensable : défaut affectant le set ou promesse de release = correction, retrait de fonction ou réserve explicitement acceptée. Une fonction expérimentale demeure étiquetée telle quelle.

Statuts : `NON_EXECUTE`, `EN_COURS`, `OK`, `NOK`, `BLOQUE`, `NA_JUSTIFIE`. Ni BLOQUE ni NON_EXECUTE ne comptent comme succès. `NA_JUSTIFIE` exige une raison et ne permet pas d’écarter une fonction annoncée. Dupliquer les lignes par firmware, build, OS ou variante; conserver les anciens résultats.

<a id="doc-acceptance-0-6-0-readme--8-droul-de-la-campagne-et-guidage"></a>
#### 8. Déroulé de la campagne et guidage

Ordre proposé pour limiter les manipulations et isoler les régressions :

1. **Préparation ordinateur** : APP, corpus, manifests, profils, sauvegardes et garde des preuves. Pas de besoin de présence continue de François.
2. **Session banc / secours** : Q, STOCK, DIAG, T, vérification des gestes de secours. Puis smoke module par module avant charge complète.
3. **Session navigation** : huit onglets, BROWSE/tri, Search, Key Match, Key Sync et logo/thème. Réglages/profils préparés à l’avance, aucune recompilation improvisée entre gestes.
4. **Session audio** : Beat Jump, Key Shift, Stems, waveforms, Samples; d’abord signaux étalons puis musique; D1 et D2.
5. **Session lifecycle** : USB et copies invalides, après sauvegarde des preuves et avec decks arrêtés quand le cas implique restart. Continuité sur U2 uniquement dans les cas qui la prévoient.
6. **Session endurance** : stress actif 30 min, cycle de 2 h, puis 30 min en FINAL sans diagnostics. L’endurance n’est pas substituée par deux heures de silence.
7. **Compatibilité et verdict** : firmware(s), app(s) réellement distribuée(s), OverCue séparé; réconciliation des notes de version et décision GO/NO-GO.

Prévoir plusieurs séances, pas une seule longue liste à exécuter sans pause. Ordre de grandeur de planification : 1/2 à 1 journée de préparation, 6–10 h d’essais actifs répartis, plus endurance et variantes de plateforme/firmware. À recalibrer après Q; ce n’est pas un engagement de durée.

<a id="doc-acceptance-0-6-0-readme--exemple-de-guidage-effectivement-utilis-en-session"></a>
##### Exemple de guidage effectivement utilisé en session

> **ST-03 — pads Stems / deck 1**<br>
> Préparation : profil COMPLET hash …, SYN3 chargé sur D1, D2 arrêté, niveaux 100 %, capture audio et logs démarrés.<br>
> **À faire :** appuyez sur SLIP LOOP jusqu’à voir INST / VOCAL / DRUMS. Lancez PLAY. Appuyez une fois sur pad 6, attendez deux secondes, puis rappuyez.<br>
> **À constater :** seule la composante VOCAL disparaît puis revient; le bouton et la LED suivent.<br>
> **Votre retour :** « OK » ou le premier écart entendu/vu. Je récupère la capture, mesure, note le verdict et prépare la suite. Je ne vous demande pas de chercher le fichier suivant.

Les ordres de changement de média mentionnent toujours le deck, le nom/ID, la clé concernée, la nécessité de stopper/éjecter et l’état attendu. Si l’état réel ne correspond pas, on remet le cas à zéro avant l’action suivante.

<a id="doc-acceptance-0-6-0-readme--arrt-et-reprise-sur-anomalie"></a>
##### Arrêt et reprise sur anomalie

1. François signale STOP; réduit le master si le défaut est sonore. Aucun nouveau geste de stress.
2. L’assistant sauvegarde capture et instantanés si le lecteur répond. Ne pas tuer `rbp` pour « essayer » avant la collecte et la procédure de récupération.
3. Si nécessaire : arrêter proprement le lecteur, retirer le support candidat hors tension, redémarrer avec U0. Ne jamais forcer un retrait de la clé en cours d’écriture.
4. Refaire Q-03/smoke stock. Créer l’anomalie avec la dernière action et le build exact; aucune preuve antérieure effacée.
5. Après correction : nouveau hash, reproduction du cas échoué, voisins concernés, smoke global, et nouveau stress/endurance si audio, core, lifecycle ou mémoire ont changé.

<a id="doc-acceptance-0-6-0-readme--9-dcision-de-release"></a>
#### 9. Décision de release

Le bilan contient : versions d’app/firmware réellement testées, hashes de chaque candidat, résultats par variante, anomalies et réserves, comparaison stock, qualité musicale validée par François, absence de régression du dernier artefact FINAL.

**GO** seulement si tous les P0 applicables sont OK, tous les P1 sont traités ou explicitement acceptés avec une portée de release adaptée, les preuves sont consultables et la génération livrée correspond à celle testée. Pas de substitution après coup d’un binaire « presque identique ».

Une seule version de firmware testée ne permet pas d’écrire « validé matériellement sur 1.19 et 1.20 ». Un export OverCue relu sur ordinateur ne valide pas un CDJ-3000. Un test RX3 ne valide pas le packaging Windows. Ces limites sont reportées dans la release note, même si la suite hôte est verte.

<a id="doc-acceptance-0-6-0-readme--10-sources-locales-de-la-recette"></a>
#### 10. Sources locales de la recette

Inventaire : les 17 `mod/modules/*/manifest.json`. Contrats : les sections [disposition des contrôles](../../../REFERENCES.md#doc-performance-tab-matrix), [réinsertion USB](../../../REFERENCES.md#doc-runtime-reinsertion-plan), [transposition](../../../REFERENCES.md#doc-transposition), [services communs](../../../REFERENCES.md#doc-runtime-framework) et [format des stems](../../../REFERENCES.md#doc-stem-package) dans `REFERENCES.md`, ainsi que les README des modules, confrontés au code pour les écarts de la section 2. Derniers correctifs : `tests/test_audit_regressions.py`, `tests/test_bounded_runtime.py`, `tests/test_runtime_transitions.py`.

Les 418 tests précédemment passés, la compilation ARM et le préflight sont des preuves de travail local antérieur. Ils devront être rejoués sur le candidat figé; ils ne préremplissent aucune case matérielle de ce cahier.

<a id="doc-acceptance-0-6-0-readme--11-traabilit-modules-et-preuves"></a>
#### 11. Traçabilité modules et preuves

| Module du manifest | Cas principaux |
|---|---|
| core | Q, T, UI, USB, END |
| decoder-sleep | T-09/T-10, BJ-05/BJ-07 |
| beatjump-32bars | BJ-01/BJ-02/BJ-06/BJ-07 |
| beatjump-no-quantize | BJ-03/BJ-04/BJ-06/BJ-07 |
| browse-columns | BR-01 à BR-09, UI-01, USB-05 |
| keyshift | KEY-01 à KEY-06, KEY-10, KEY-13, ST-14 |
| key-match | KM-01 à KM-05, BR-05/BR-09, KEY-07 à KEY-13 |
| key-sync | KEY-07 à KEY-13 |
| stems | APP-03 à APP-09, ST, WF, USB-02/USB-14 |
| samples | APP-11/APP-14, SA, UI, USB-06 |
| theme-white | VIS-01 à VIS-06, VIS-08/VIS-10, WF-06 |
| logo | APP-14, VIS-07 à VIS-10, USB-03/USB-04 |
| search-latin | KM-06/KM-07 |
| now-playing | NP-01 à NP-06 |
| logging | T-06 à T-08, USB-01/USB-13 |
| logging-verbose | T-07/T-08, USB-13 |
| telnet | Q-04, T, NP-05, T-08 |

Les nouveautés transversales sont également couvertes : nouvelle app et acquisition automatique (APP-01/APP-13), choix de clé et dépendances (APP-02/UI-01/KEY-13), préparation fixe et cache (APP-03/APP-05), import/preview (APP-07/APP-14), annulation (APP-06), safe mode (USB-09/USB-10), messages localisés (UI-07), export OverCue (DIST-03/DIST-04), artefacts par OS et firmware (DIST-01/DIST-02). Le prototype lecteur OverCue éventuel est séparé (DIST-05).

Codes de preuve :

- `ENV` : version, processus et topologie; `HASH` : SHA-256 + manifest des fichiers; `LOG` : événements runtime/noyau horodatés.
- `VIDEO` / `PHOTO` : écran réel et gestes/LEDs concernés; `AUDIO` : capture stéréo avec référence et réglages de gain; `NETWORK` : datagrammes bruts et horodatage.
- `METRICS` : données brutes, unité, fréquence de collecte, calcul et graphiques de comparaison; `ORACLE` : valeurs attendues fixées indépendamment de l’observation (signaux générés, métadonnées exportées, référence native ou calcul tonal).
- `DOC` : décision motivée, contrat ou limitation identifiée. Un texte déclaratif n’est pas une preuve de comportement audio.

Arborescence privée proposée : `local/acceptance/0.6.0/runs/<session>/<firmware>/<build>/<ID>/<variante>/`. Chaque répertoire conserve `before.txt`, `after.txt`, événements, preuves et verdict selon disponibilité. Les résultats du CSV citent ces chemins relatifs. Les médias personnels, logs de titres et numéros de série ne sont pas joints automatiquement à une publication.

Le CSV est le registre de campagne éditable; le JSON décrit le catalogue initial. Conserver un exemplaire vierge et un exemplaire de résultats par candidat. Ne pas réécrire une ancienne ligne OK pour lui attribuer le hash d’un nouveau build.

<a id="doc-acceptance-0-6-0-readme--ajout-aprs-le-gel-du-catalogue--asshole-mode"></a>
#### Ajout après le gel du catalogue : Asshole mode

Le nouveau module ajoute les cas **AH-01 à AH-11**, tous **NON EXÉCUTÉS**,
dans [la recette du masquage des titres](../../../REFERENCES.md#doc-title-visibility--additional-hardware-acceptance-all-not-run).
Ils complètent le catalogue initial de 149 cas ; ils ne sont pas encore inclus
dans ses exports CSV/JSON. Les exécuter avant de déclarer ce module accepté.

---

<a id="doc-acceptance-0-6-0-cas-de-test"></a>
## Cas de recette RX3 0.6.0



Statut initial de tous les cas : **NON EXÉCUTÉ**. Lire [le protocole](#doc-acceptance-0-6-0-readme) avant utilisation. A = assistant, F = François. Chaque variante demandée reçoit sa propre ligne de résultat; un cas parent reste non validé tant qu’une variante manque. Les étapes de chargement sont préparées par A, mais ne sont automatisées que si Q-06 a réussi.

<a id="doc-acceptance-0-6-0-cas-de-test--identification-et-qualification-du-banc"></a>
#### Identification et qualification du banc

| ID | Priorité / acteur | Préparation par A | Action à exécuter | Résultat attendu | Preuve |
|---|---|---|---|---|---|
| Q-01 | P0 / A+F | RX3 arrêté; clé de secours stock; volume de sortie réduit | F relie le banc et lit la version dans Utility; A relève firmware, numéro de série privé et topologie USB | Version et appareil identifiés; secours accessible; aucune clé musicale personnelle utilisée comme cible | PHOTO+ENV |
| Q-02 | P0 / A | Source et application candidate disponibles | Figer commit ET diff local, manifests, dépendances et SHA-256 de l’app, autoexec.bin, core et ressources | Une génération unique identifie tous les résultats; toute modification produit un nouveau build de recette | HASH |
| Q-03 | P0 / A+F | Profil STOCK sans mod; médias étalons exportés | F charge D1 puis D2 et lance 5 min; A enregistre écran, audio et temps de chargement | Référence native saine avant comparaison; audio et commandes fonctionnent sur les deux decks | AUDIO+VIDEO+METRICS |
| Q-04 | P0 / A+F | Profil DIAG; connexion USB-B directe | F insère puis attend; A découvre l’adresse actuelle, ouvre Telnet et relève les outils présents | Connexion sur le bon RX3; accès et outils identifiés sans réutiliser une ancienne IP à l’aveugle | ENV+LOG |
| Q-05 | P0 / A | Répertoire de preuves sur ordinateur | Calibrer horodatage, capture audio stéréo et vidéo; enregistrer un marqueur simultané | Preuves corrélables; canaux L/R identifiés; la capture ne sature pas | AUDIO+VIDEO |
| Q-06 | P0 / A+F | Deux decks arrêtés; piste Q01 en première position | Qualifier une éventuelle commande de chargement native documentée; vérifier ID, deck et écran après chaque action | Automatisation admise seulement après 3 charges correctes par deck; sinon F utilise les boutons physiques LOAD | LOG+VIDEO |
| Q-07 | P0 / A | Tous les modules et notes candidat | Résoudre les écarts listés dans le cahier et figer les attentes avant les essais | Contrat produit connu; pas de verdict OK attribué à deux comportements contradictoires | DOC |
| Q-08 | P0 / A | Médias étalons et bibliothèque dédiée | Relire les fichiers, calculer les hashes, vérifier chemins exportés, BPM, clés et cues sur le RX3 | Corpus réellement chargeable; aucune hypothèse fondée sur le seul nom du fichier | HASH+PHOTO |

<a id="doc-acceptance-0-6-0-cas-de-test--application-livre-et-prparation-usb"></a>
#### Application livrée et préparation USB

| ID | Priorité / acteur | Préparation par A | Action à exécuter | Résultat attendu | Preuve |
|---|---|---|---|---|---|
| APP-01 | P0 / A+F | Application empaquetée candidate, compte de test et clé U1 | A démarre l’app, choisit U1, prépare l’installation; F ne confirme que les dialogues système inaccessibles à A | Parcours livré utilisable sans lancer le code source; manifest et fichiers correspondent à la sélection | VIDEO+HASH |
| APP-02 | P0 / A | U1 et U2 avec installations différentes | Changer de clé sélectionnée, relancer l’app puis relire les choix | Cases dérivées du manifest de la bonne clé; aucun module inventé d’après les logs | VIDEO+HASH |
| APP-03 | P0 / A | Profil neuf puis anciennes préférences de qualité/modèle | Préparer la même piste par les deux profils | Aucun sélecteur qualité/modèle; VOCAL et DRUMS préparés; INST reconstruit; ancienne préférence sans effet sur cette politique | VIDEO+LOG+HASH |
| APP-04 | P0 / A | Source musicale M01 avec voix et batterie; cache vide | Installer le moteur si nécessaire, préparer et écouter chaque combinaison | Installation effective, progression et fin explicites; sortie valide; modèle choisi automatiquement; voix et batterie musicalement exploitables | LOG+AUDIO |
| APP-05 | P1 / A | Cache de M01 puis variante source/paramètres effectifs | Repréparer à l’identique, puis changer une entrée invalidante et essayer après éviction du cache | Réutilisation vérifiée à l’identique; recalcul justifié après invalidation; aucun engagement de réutilisation après suppression | LOG+HASH |
| APP-06 | P0 / A | Préparation longue sur une copie | Annuler pendant séparation, décodage et export; refaire chaque étape; fermer l’app pendant un job | Processus enfants terminés; pas de paquet partiel publié; ancien résultat conservé; reprise possible | LOG+HASH |
| APP-07 | P0 / A | Jeu IM de stems connus puis décalés/trop courts/niveau incompatible | Importer le jeu sain; tenter séparément les variantes invalides | Import sain accepté et conservé; refus ou ajustements explicitement annoncés; aucune correction silencieuse du niveau | LOG+HASH+AUDIO |
| APP-08 | P0 / A | U1 avec espace insuffisant simulé sur support de test, puis source dépassant la limite calculée | Lancer une préparation/importation refusée | Refus explicite avant travail inutile; aucune bibliothèque existante détériorée | LOG+HASH |
| APP-09 | P1 / A | Bibliothèque de test ouverte dans rekordbox | Demander lecture/préparation; fermer rekordbox puis Check again | Accès bloqué puis reprise propre, sans opérations concurrentes sur la bibliothèque | VIDEO |
| APP-10 | P1 / A | FR puis EN, fenêtre étroite et normale | Parcourir Modules, Stems, Samples, Logo; inspecter erreurs et sélection clavier | Libellés lisibles; pas de clé de traduction brute; avertissement ZOOM/GRID présent; phrase STATUS retirée | VIDEO |
| APP-11 | P0 / A | Banque B1 existante; banque B2 à sauvegarder | Annuler une édition; sauver B2; injecter un échec de conversion sur une copie avant remplacement | Annulation sans écriture; banque saine entièrement préparée; échec de conversion ne mélange pas anciens et nouveaux pads | HASH+LOG |
| APP-12 | P1 / A | U1 de recette; sauvegarde préalable des fichiers de musique | Tester suppression du mod et suppression d’une banque avec annulation puis confirmation | Confirmations utiles; seule la cible est supprimée; musique et autres banques inchangées | HASH+VIDEO |
| APP-13 | P0 / A | Clé fraîche, acquisition du matériel de construction non en cache | Construire via l’app, puis recommencer hors réseau avec les éléments déjà disponibles | Acquisition automatique explicite; archive vérifiée; erreur réseau compréhensible; pas d’installation prétendue réussie en cas d’échec | LOG+HASH |
| APP-14 | P1 / A | Logo de test, prévisualisation Samples et écoute Stems | Comparer les préparations de l’app aux fichiers effectivement exportés | Cadrage, noms, couleurs, modes, gains et audio correspondent aux paramètres enregistrés | HASH+VIDEO |

<a id="doc-acceptance-0-6-0-cas-de-test--contrles-telnet-et-core"></a>
#### Contrôles Telnet et core

| ID | Priorité / acteur | Préparation par A | Action à exécuter | Résultat attendu | Preuve |
|---|---|---|---|---|---|
| T-01 | P0 / A | Profil COMPLET au repos | Lire PID/starttime de rbp, chemin exécutable, maps, marqueur ready et hash du core installé | Un seul lecteur actif; ready lié au bon PID; bon core réellement mappé; pas de faux succès fondé sur un fichier isolé | ENV+HASH |
| T-02 | P0 / A | Même profil après chargement et lecture | Collecter logs runtime, noyau, sorties joueur et statut de processus | Aucun crash, OOM, segfault, boucle de relance ni échec ignoré d’un module sélectionné | LOG+METRICS |
| T-03 | P0 / A | Firmware identifié; outils statiques hors lecteur | Vérifier les signatures contre le firmware exact et les preuves live disponibles | Toutes les gardes requises correspondent; distinction explicite entre binaire disque et hooks réellement actifs | HASH+LOG |
| T-04 | P1 / A | 5 min stock puis 5 min COMPLET idle | Relever CPU, mémoire, threads et descripteurs toutes les 10 s depuis l’ordinateur | Mesure comparative complète; pas de croissance sans plateau; collecte elle-même légère | METRICS |
| T-05 | P0 / A | rbp prêt et utilities usuels disponibles | Lancer uniquement des lectures bénignes dans une session enfant; recontrôler readiness | Les outils enfants ne réinitialisent pas l’état du lecteur et ne cherchent pas à installer ses hooks | LOG+ENV |
| T-06 | P1 / A | Profil DIAG puis même profil réinséré | Vérifier session.txt, session-previous.txt et motifs restart/no-op | Rotation exploitable; génération identifiable; absence de succès trompeur après erreur | LOG |
| T-07 | P1 / A+F | Logging simple puis verbose, essais séparés | F lit 2 min; A compare flux, occupation, handles et coût | Simple et verbose distingués; verbose écrit les logs attendus sans perturbation; avertissement cohérent avec la politique d’éjection | LOG+METRICS+AUDIO |
| T-08 | P0 / A+F | Profil FINAL sans diagnostics, redémarrage complet | F joue 5 min; A vérifie absence d’écoute Telnet depuis l’ordinateur et inspecte la clé après éjection | Diagnostic absent par défaut; pas de journal USB non demandé; même comportement audio/UI | NETWORK+HASH+AUDIO |
| T-09 | P1 / A | Decoder wait actif; console interne disponible | Capturer les réponses aux deux réglages sans boucler les commandes | Réponses non vides pour D1 et D2; valeur appliquée marquée NON_VERIFIEE si aucune lecture fiable n’existe | LOG |
| T-10 | P1 / A | Copie de test du helper, cible UDP sans répondant; aucun lecteur en lecture | Exécuter le cas timeout isolé puis relever ses enfants/fichiers temporaires | Échec borné; ni faux succès ni enfant de réception orphelin; aucune panne imposée au service natif | LOG+METRICS |

<a id="doc-acceptance-0-6-0-cas-de-test--beat-jump-et-conservation-des-commandes-natives"></a>
#### Beat Jump et conservation des commandes natives

| ID | Priorité / acteur | Préparation par A | Action à exécuter | Résultat attendu | Preuve |
|---|---|---|---|---|---|
| BJ-01 | P0 / A+F | Q01 à 120 BPM avec grille et repères 32 temps; profil BJ32 | F ouvre BEAT JUMP, presse pad 8 puis pad 7 sur D1; refaire D2 | Déplacement de +32 puis -32 temps, soit 16 s à tempo nul; pads concernés corrects; retour au repère | VIDEO+AUDIO |
| BJ-02 | P0 / A+F | Q01 près du début puis de la fin | F essaie les sauts hors limites et les autres tailles de saut | Refus/limites natives conservés; aucun wrap ni position impossible; autres pads inchangés | VIDEO |
| BJ-03 | P0 / A+F | Profil immédiat seul puis combiné BJ32 | F presse quatre fois rapidement le saut choisi pendant lecture | Quatre actions prises en compte sans attente ajoutée de demi-mesure; position finale attendue et audio continu | VIDEO+AUDIO |
| BJ-04 | P0 / A+F | Q01, Quantize ON puis OFF | F teste Beat Jump, Hot Cue, boucle et Beat FX dans chaque état | Seul le comportement Beat Jump demandé change; cues, boucles et FX gardent leurs règles natives | VIDEO+AUDIO |
| BJ-05 | P1 / A+F | Profil decoder seul et STOCK; même média/position | F répète 20 sauts identiques par deck; A mesure reprise et charge | Distributions comparables et aucune régression sonore; ne pas conclure à un gain sur la seule réponse UDP | METRICS+AUDIO |
| BJ-06 | P0 / A+F | COMPLET, deux decks en lecture, stems et Key Shift actifs | F alterne sauts, cue, jog et reverse | Aucun blocage, morceau précédent ou canal perdu; resets audio corrects | AUDIO+VIDEO+LOG |
| BJ-07 | P1 / A+F | Retrait des modules puis arrêt/marche stock | F refait un saut pad 7/8 et une séquence rapide | Distances et cadence natives retrouvées; réglage volatile non présenté comme persistant | VIDEO+ENV |

<a id="doc-acceptance-0-6-0-cas-de-test--onglets-routage-des-pads-et-gestes-communs"></a>
#### Onglets, routage des pads et gestes communs

| ID | Priorité / acteur | Préparation par A | Action à exécuter | Résultat attendu | Preuve |
|---|---|---|---|---|---|
| UI-01 | P0 / A+F | Huit profils KEY/STEMS/SAMPLES définis dans le cahier | A prépare chaque profil; F touche chaque onglet et ses bords | Les huit combinaisons respectent la matrice; aucune zone fantôme; ZOOM/GRID disponibles seulement sans KEY et STEMS | VIDEO+HASH |
| UI-02 | P0 / A+F | COMPLET; pistes et banque chargées | F touche KEY, STEMS, SAMPLES, BEAT FX, puis retouche l’onglet actif | Changement direct entre panneaux; second appui retourne à STATUS; BEAT FX reste utilisable | VIDEO |
| UI-03 | P0 / A+F | Profil KEY ou STEMS sans Samples | F ouvre le panneau puis touche STATUS | Retour natif possible même sans Samples; aucune interaction forcée avec le panneau précédent | VIDEO |
| UI-04 | P0 / A+F | SAMPLES ouvert, loop sample en cours | F presse HOT CUE, BEAT LOOP, SLIP LOOP, BEAT JUMP puis revient SAMPLES | Routage suit le mode physique; aucun Hot Cue perdu; panneau et audio suivent le contrat figé; pas de déclenchement croisé | VIDEO+AUDIO |
| UI-05 | P0 / A+F | Deux decks; sliders STEMS et Samples | F touche sans déplacer, glisse, sort de la cible puis relâche; répéter de l’autre côté | Pas de saut de gain au contact; pas de clic parasite après drag; deck opposé inchangé | VIDEO+AUDIO |
| UI-06 | P1 / A+F | Dark puis Light, états idle/actif/indisponible | F parcourt tous les panneaux et appuie sur leurs commandes | Texte, couleurs, état pressé et état désactivé lisibles; absence de chevauchement ou de scintillement persistant | PHOTO+VIDEO |
| UI-07 | P0 / A+F | FR puis EN sur le RX3; profil messages ON puis OFF; aucun média en lecture au restart | F observe le message de démarrage et sa disparition; A vérifie readiness et désactivation explicite | Message dans la langue du lecteur, sans masquage persistant des contrôles; pas de fin annoncée avant readiness; désactivation respectée | VIDEO+LOG |

<a id="doc-acceptance-0-6-0-cas-de-test--browse--colonnes-et-tri"></a>
#### BROWSE : colonnes et tri

| ID | Priorité / acteur | Préparation par A | Action à exécuter | Résultat attendu | Preuve |
|---|---|---|---|---|---|
| BR-01 | P0 / A+F | Playlist SORT de 100 entrées, BPM en 3e colonne | F ouvre BROWSE et parcourt début/milieu/fin | Deux colonnes natives conservées; 3e correcte pour chaque ID; sélection lisible | VIDEO+ORACLE |
| BR-02 | P0 / A+F | Playlist SORT mélangée; titre, artiste, BPM | F touche chaque en-tête deux fois, dans les deux directions | Tri de toute la liste et pas seulement de la page; flèche correcte; ordre comparé à l’oracle exporté | VIDEO+ORACLE |
| BR-03 | P0 / A+F | Troisième colonne successivement Key puis Duration puis Artist | F trie ascendant/descendant et charge le morceau sélectionné | Champ de tri valide; temps triés par durée et BPM numériquement; convention de clés/nulls figée; valeurs des colonnes inchangées | VIDEO+ORACLE |
| BR-04 | P0 / A+F | Une piste repère sélectionnée avant tri | F trie, fait défiler puis appuie LOAD 1; recommence LOAD 2 | Même track ID retenu et réellement chargé; pas simplement le même numéro de ligne | VIDEO+LOG |
| BR-05 | P0 / A+F | Filtre natif actif, lignes vertes et couleurs Key Match | F trie plusieurs champs puis inverse | Filtre, en-tête, marqueurs verts et catégories conservés; aucune ligne perdue/dupliquée ni champ invalide | VIDEO+ORACLE |
| BR-06 | P1 / A+F | Titres/artistes longs, doublons, accents et champs vides | F sélectionne puis laisse défiler; change de ligne pendant le défilement | Pas de débordement; nouveau texte propre; pause et défilement cohérents; 3e valeur visible | VIDEO |
| BR-07 | P0 / A+F | BROWSE avec colonnes actives | F touche les anciennes zones LOAD écran puis les boutons LOAD physiques | Zones masquées inertes; LOAD physique charge le bon deck; boutons des autres écrans restent natifs | VIDEO |
| BR-08 | P1 / A+F | Catégories/dossiers, menu ouvert et en-tête de liste | F fait un drag depuis l’en-tête puis navigue hors liste | Drag annulé sans tri; catégories et menus ne capturent pas le tri de pistes | VIDEO |
| BR-09 | P0 / A+F | Deux decks lisent; playlist longue; module seul puis avec Key Match | F trie et scrolle rapidement pendant 5 min | Aucune coupure audio; pas de lag persistant ni fuite de mémoire après retour idle | AUDIO+VIDEO+METRICS |

<a id="doc-acceptance-0-6-0-cas-de-test--key-shift-et-key-sync"></a>
#### Key Shift et Key Sync

| ID | Priorité / acteur | Préparation par A | Action à exécuter | Résultat attendu | Preuve |
|---|---|---|---|---|---|
| KEY-01 | P0 / A+F | D1 vide, K01 chargé uniquement sur D2 | F ouvre KEY; A vérifie ID et tonalité | Tonalité D2 connue et correcte même sans chargement D1; inverse également valable | VIDEO+ORACLE |
| KEY-02 | P0 / A+F | K01 et K02, tons mesurables, tempo nul | F applique +1, -1 et reset centre sur chaque deck | Décalage réel de ±1 demi-ton et libellé correct; deck opposé inchangé; durée/tempo conservés | AUDIO+VIDEO |
| KEY-03 | P0 / A+F | K01 | F va à +12 puis -12; essaie un pas au-delà et revient à zéro | Bornes ±12 respectées; commande indisponible visible; aucun overflow ni octave involontaire au reset | AUDIO+VIDEO |
| KEY-04 | P0 / A+F | Décalage non nul sur D1; autre piste et piste sans clé préparées | F charge les deux successivement puis recharge une piste connue | Reset à zéro; nouvelle clé conservée; ancienne clé effacée si absente; aucune information du mauvais deck | VIDEO+LOG |
| KEY-05 | P0 / A+F | Key Shift actif ±3, Master Tempo ON/OFF, tempo -6/0/+6 % | F change tempo et MT pendant lecture des deux decks | Comportement comparé au stock et à l’oracle tonal; pas de double transposition inattendue ni décrochage | AUDIO+VIDEO |
| KEY-06 | P0 / A+F | Musique M01 et signal Q01 transposés | F pause/reprend, cue, hot cue, loop, Beat Jump, scratch et reverse | Aucun ancien fragment après repositionnement; pas de clic soutenu, gel ou décalage croissant | AUDIO+VIDEO |
| KEY-07 | P0 / A+F | K8A MASTER D1, K2A D2; mode compatible; limite 1; extensions OFF | F ouvre KEY et demande la correction proposée sur D2 | Proposition conforme au jeu natif/fallback documenté; dans le jeu classique 2A vers 9A à +1; MASTER D1 non transposable par Sync | VIDEO+ORACLE+AUDIO |
| KEY-08 | P0 / A+F | Même couple, mode même tonalité, limites 1 puis 6 | F tente KEY SYNC dans les deux configurations | Pas de proposition hors limite; à 6 la correction atteint 8A; cible majeure/mineure préservée | VIDEO+ORACLE |
| KEY-09 | P0 / A+F | Les deux decks connus; KEY affiché | F change MASTER puis charge un nouveau morceau MASTER sans ouvrir BROWSE | Référence actualisée; aucune ancienne cible applicable; délai éventuel documenté; puis concordance après ouverture BROWSE | VIDEO+LOG |
| KEY-10 | P0 / A+F | MASTER connu, BROWSE puis KEY ouverts | F transpose MASTER, revient sur D2 et rouvre BROWSE | Référence et suggestions suivent la clé effective; snapshot périmé non réutilisé comme actuel | VIDEO+ORACLE |
| KEY-11 | P0 / A+F | Référence absente/inconnue et candidat inconnu; source USB1 puis USB2 | F tente KEY SYNC, puis restaure des clés connues | Pas d’action sans référence fiable; stockage et numéro de deck jamais confondus | VIDEO |
| KEY-12 | P0 / A+F | Candidat déjà compatible, identique, puis prétransposé | F demande Sync; teste égalité de distance et limite absolue | Déjà accepté reste inchangé; choix du plus petit déplacement supplémentaire conforme à l’oracle; bornes respectées | VIDEO+ORACLE+AUDIO |
| KEY-13 | P0 / A+F | Profil Key Shift seul puis Key Match seul puis trio | F ouvre KEY/BROWSE et tente les fonctions disponibles | Manuel utilisable seul; Key Match sans transposition; Sync seulement quand ses dépendances sont actives | VIDEO+HASH |

<a id="doc-acceptance-0-6-0-cas-de-test--key-match-et-recherche"></a>
#### Key Match et recherche

| ID | Priorité / acteur | Préparation par A | Action à exécuter | Résultat attendu | Preuve |
|---|---|---|---|---|---|
| KM-01 | P0 / A+F | Playlist KEY24; MASTER 8A; extensions OFF | F ouvre BROWSE; A compare aux classifications natives stock | Verts natifs préservés; aucune couleur supplémentaire non demandée | VIDEO+ORACLE |
| KM-02 | P0 / A+F | KEY24; activer +2, +7, +4 séparément puis ensemble | F observe 10A, 3A et 12A face à MASTER 8A | Jaune/orange/rouge selon règles dirigées du contrat; vert natif prioritaire; +4 clairement expérimental | VIDEO+ORACLE |
| KM-03 | P0 / A+F | Même liste; contre-exemples 6A, 1A, 4A et clés B | F observe les relations inverses et change MASTER | Ne pas accepter une promesse ± si seul + est implémenté; aucun faux match entre modes non prévu | VIDEO+ORACLE |
| KM-04 | P0 / A+F | BROWSE ouvert puis trié; MASTER remplacé/transposé | F change référence et filtre sans quitter la liste | Marqueurs et troisième colonne actualisés ensemble; aucun résidu de la piste précédente | VIDEO+ORACLE |
| KM-05 | P1 / A+F | Traffic Light natif ON puis OFF; piste sans clé | F observe les mêmes lignes | Respect du réglage natif et du contrat; piste inconnue sans suggestion inventée | VIDEO |
| KM-06 | P0 / A+F | SEARCH contient NIÑO, CORAZÓN, Bébé, Straße, Eth/Thorn et titres témoins | F saisit NINO, CORAZON, BEBE puis les formes de recherche préparées | Résultats trouvés sur la vraie base exportée; métadonnées affichées inchangées; ß vers un S testé comme tel | VIDEO+ORACLE |
| KM-07 | P1 / A+F | Même recherche sans module, puis activée; chaînes longues/vides | F efface, recherche sans résultat et sélectionne un résultat | Différence utile démontrée; aucun blocage ou corruption du champ; bonne piste chargée | VIDEO |

<a id="doc-acceptance-0-6-0-cas-de-test--stems--son-contrles-limites-et-chargement"></a>
#### Stems : son, contrôles, limites et chargement

| ID | Priorité / acteur | Préparation par A | Action à exécuter | Résultat attendu | Preuve |
|---|---|---|---|---|---|
| ST-01 | P0 / A+F | Paquet SYN3 et piste M01 préparés; D1 puis D2 | F charge et ouvre STEMS; attend la fin de chargement | Trois rôles disponibles, états lisibles; aucun rôle de l’ancienne piste durant le chargement | VIDEO+LOG |
| ST-02 | P0 / A+F | SYN3 dont chaque composante est connue | F écoute les 7 combinaisons non vides puis tout coupe; A enregistre | Chaque combinaison correspond au mix attendu; INST conserve la basse; tout activé retrouve le mix; silence quand tout est coupé | AUDIO+ORACLE |
| ST-03 | P0 / A+F | SYN3, écran STEMS et mode SLIP LOOP | F alterne pads 5 INST, 6 VOCAL, 7 DRUMS et commandes tactiles; essaie pad 8 | Audio, LED et écran cohérents; pad 8 garde sa boucle native | VIDEO+AUDIO |
| ST-04 | P0 / A+F | STEMS 100 %; panneau combiné boutons/sliders | F fait un tap, puis maintien >350 ms et glisse vers 50/0/100 % | Tap mute/active; drag règle sans saut initial ni toggle final; 0 éteint; à 100 slider se masque après environ 2 s | VIDEO+AUDIO |
| ST-05 | P0 / A+F | Deux pistes différentes simultanées | F modifie tous les niveaux sur D1 puis D2 et recharge un deck | Indépendance des decks; niveaux réinitialisés au nouveau morceau; pas de contamination croisée | VIDEO+AUDIO |
| ST-06 | P0 / A+F | M01 en lecture; stems tous actifs puis isolés | F fait 30 toggles rapides, tempo, MT, loops, Beat Jump et scratch | Pas de désynchronisation, clic anormal récurrent ou fragment ancien; transition cohérente avec le transport | AUDIO+VIDEO |
| ST-07 | P0 / A+F | Trois paquets distincts A gros, B petit, C petit; autre deck joue | F charge A puis B/C avant la fin du premier chargement, 20 fois | Seul le dernier morceau publie ses stems; lectures obsolètes abandonnées; autre deck continu; mémoire récupérée | LOG+AUDIO+METRICS |
| ST-08 | P0 / A+F | Piste sans paquet puis paquet sain | F charge chaque piste et touche les anciennes zones stems | Piste ordinaire joue normalement; message NO STEMS/inactivité; chargement sain suivant opérationnel | VIDEO+AUDIO |
| ST-09 | P0 / A+F | Copies tronquée, mauvais CRC et header invalide d’un paquet | F charge chaque piste dédiée puis une saine | Paquet rejeté en totalité; pas de mélange partiel ni crash; son natif et recovery vérifiés | LOG+VIDEO+AUDIO |
| ST-10 | P1 / A+F | Corpus legacy vocal seul, vocal+drums, ancien bass, optional invalide | F charge chaque variante et joue tous les contrôles visibles | Compatibilité conservée; bass ancien suit INST; seul préfixe contigu valide legacy admis; pas de relecture inutile observable | LOG+AUDIO |
| ST-11 | P0 / A+F | Deux paquets sous plafond individuel mais dépassant ensemble 512 MiB | F charge le premier puis le second; A observe sans allouer de mémoire artificielle | Refus du second set lorsque le budget est insuffisant; premier deck intact; message explicite; pas d’OOM | LOG+METRICS+AUDIO |
| ST-12 | P0 / A+F | Tailles calculées juste avant/après limites; jeu dédié préparé hors app si test négatif | F charge seulement les fixtures bornées prévues; A contrôle mémoire disponible | Limites de taille/durée et réserve de 300 MiB appliquées; refus sûr; aucun test ne force l’épuisement mémoire | LOG+METRICS |
| ST-13 | P0 / A+F | Même basename sur chemins distincts, nom long, accents, USB1/USB2 | F charge chaque piste; A compare signature audio au manifeste | Aucun paquet attribué au mauvais morceau; ambiguïté éventuelle refuse ou reste native, jamais stems étrangers | AUDIO+HASH+LOG |
| ST-14 | P0 / A+F | M01 avec stems, Key Shift et Samples actifs | F transpose ±, joue quatre samples et change les rôles | Mix cohérent, pas de saturation interne inattendue à niveaux de test, aucun décrochage | AUDIO+VIDEO+METRICS |

<a id="doc-acceptance-0-6-0-cas-de-test--waveforms-stems"></a>
#### Waveforms Stems

| ID | Priorité / acteur | Préparation par A | Action à exécuter | Résultat attendu | Preuve |
|---|---|---|---|---|---|
| WF-01 | P0 / A+F | SYN3 et M01; Blue, RGB et 3 Band disponibles | F parcourt les 7 combinaisons pour chaque mode et chaque deck | Waveform principale et overview cohérentes avec rôles actifs; retour full mix restitue l’original; temps/cues inchangés | VIDEO+ORACLE |
| WF-02 | P0 / A+F | Stems actifs avec niveaux intermédiaires puis zéro | F ajuste et réactive chaque rôle | Règle de waveform liée aux rôles actifs explicitée; aucun dessin périmé; absence de promesse de niveau continu si dessin binaire | VIDEO |
| WF-03 | P0 / A+F | Waveform filtrée, pistes avec/sans préparation alternées | F charge nouveau morceau puis revient au précédent | Aucune colonne/overview de la piste ancienne; retour natif si données absentes | VIDEO |
| WF-04 | P0 / A+F | Paquet legacy audio-only compatible | F active/coupe les rôles dans chaque mode visuel | Audio stems fonctionnel et waveform native conservée; pas de données inventées | VIDEO+AUDIO |
| WF-05 | P1 / A+F | Sources 44,1/48 kHz; transitoires et silences; analyse à sections cues répétées | F charge, zoome si disponible, saute début/fin et observe | Lecture d’analyse acceptée; bandes RGB sans débordement; fin et padding propres; comparaison visuelle documentée | VIDEO+ORACLE |
| WF-06 | P0 / A+F | Deux waveforms actives; toggles stems et thème | F change rapidement thème et rôles, 20 cycles | Aucun gel de transport, damier, reste d’ancienne palette ou perte d’overview | VIDEO+AUDIO+METRICS |

<a id="doc-acceptance-0-6-0-cas-de-test--samples"></a>
#### Samples

| ID | Priorité / acteur | Préparation par A | Action à exécuter | Résultat attendu | Preuve |
|---|---|---|---|---|---|
| SA-01 | P0 / A+F | Banque B1 avec 8 signatures sonores et couleurs distinctes | F touche SAMPLES puis chaque pad D1 et D2 | Bons son, nom, couleur et gain; pas de son d’un autre pad; touches natives restaurables | VIDEO+AUDIO |
| SA-02 | P0 / A+F | Pad1 one-shot et pad2 hold | F relâche immédiatement pad1; maintient puis relâche pad2 | One-shot va à son terme; hold s’arrête au relâchement avec comportement de bord attendu | AUDIO+VIDEO |
| SA-03 | P0 / A+F | Pad3 loop et pad4 latch | F appuie deux fois chacun puis laisse chaque mode aller à sa fin | Loop boucle jusqu’au second appui; latch s’arrête au second appui ou à sa fin et ne boucle pas | AUDIO+VIDEO |
| SA-04 | P0 / A+F | Pad2 hold sur les deux decks | F maintient le même pad sur D1 et D2, relâche D1 puis D2 | Son maintenu tant qu’un deck le tient; dernier relâchement arrête | AUDIO+VIDEO |
| SA-05 | P0 / A+F | Pad2 tenu; pad3 loop actif | F change de panneau puis de mode physique et relâche hold; revient SAMPLES | Pas de perte de ownership; hold cesse au dernier relâchement; loop conservée puis arrêtable | AUDIO+VIDEO |
| SA-06 | P0 / A+F | Quatre pads distincts en lecture, répartis entre decks | F tente un cinquième pad, libère une voix puis retente | Plafond global 4; cinquième refusé sans couper les autres; slot libéré réutilisable | AUDIO+VIDEO |
| SA-07 | P0 / A+F | Pad1 en lecture, quatre voix occupées | F retrigge pad1 rapidement 30 fois, y compris juste après son départ | Retrigger repart sans voix supplémentaire; aucune commande perdue au curseur zéro | AUDIO+VIDEO |
| SA-08 | P0 / A+F | B1 SHIFT silence ON puis B2 OFF | F joue plusieurs sons puis presse SHIFT seul sur chaque deck | ON stoppe tous les samples; OFF ne les stoppe pas; fonctions SHIFT natives conservées | AUDIO+VIDEO |
| SA-09 | P0 / A+F | B1 volume défaut 50, gains par pad 0/50/100/200 testés à faible master | F glisse volume banque, touche sa valeur pour reset et compare les pads | Niveau et reset cohérents; 0 muet; gains enregistrés appliqués sans dépassement non annoncé | AUDIO+VIDEO |
| SA-10 | P1 / A+F | Pads vides, son très court, son 8 s et source 9 s préparée par l’app | F déclenche chaque pad; A compare durée et fin | Vide sans effet; durée exportée limitée aux 8 premières secondes; boucle courte sans trou répété anormal | AUDIO+HASH |
| SA-11 | P0 / A+F | Samples joués, piste en pause puis en lecture; master et talkover disponibles | F ajuste master, active talkover puis coupe celui-ci | Samples intégrés au chemin de sortie prévu; niveaux restaurés; pas de disparition/duplication imprévue | AUDIO+VIDEO |
| SA-12 | P0 / A+F | Banque absente puis fichier WAV/settings corrompu sur copie | F ouvre et déclenche les pads puis recharge B1 saine | Refus explicite/borné; pas de lecture hors limites ni crash; banque saine de nouveau utilisable | LOG+VIDEO |
| SA-13 | P0 / A+F | B1 puis B2 même nom avec audio modifié; autre deck arrêté | A prépare changement; F effectue l’éjection/insertion demandée | Génération détectée; redémarrage encadré si nécessaire; aucun ancien son annoncé comme nouveau | HASH+LOG+AUDIO |

<a id="doc-acceptance-0-6-0-cas-de-test--thme-et-logo"></a>
#### Thème et logo

| ID | Priorité / acteur | Préparation par A | Action à exécuter | Résultat attendu | Preuve |
|---|---|---|---|---|---|
| VIS-01 | P0 / A+F | Profils startup dark/light/wait/switch, démarrage froid chacun | F observe du premier écran à la disponibilité; A filme | Mode demandé réellement obtenu; pas de moitié d’écran incohérente; mode wait attend la première peinture | VIDEO+LOG |
| VIS-02 | P0 / A+F | Deux decks chargés en lecture, profils switch | F alterne SHIFT+SHORTCUT 20 fois | Fond, header, cellules Hot Cue et panneaux cohérents sans quitter/revenir à l’écran; audio continu | VIDEO+AUDIO |
| VIS-03 | P0 / A+F | Même charge, menu Utility | F choisit DISPLAY MODE DARK puis LIGHT, 10 cycles | Même résultat que le raccourci; navigation et fermeture menu correctes | VIDEO+AUDIO |
| VIS-04 | P0 / A+F | Light actif; collection de pochettes et écrans encore non visités | F parcourt BROWSE, SEARCH, menus, pads et waveforms | Conversion progressive puis stable; pas de blocage long lors d’une première image; transparence et couleurs utiles conservées | VIDEO+METRICS |
| VIS-05 | P0 / A+F | Changement de mode pendant conversion de nouvelles images | F bascule plusieurs fois avant stabilisation | Aucune image partiellement convertie publiée; pas de mélange persistant de modes; cache cohérent | VIDEO+LOG |
| VIS-06 | P1 / A+F | Beaucoup de pochettes différentes; limites naturelles de l’arène | F navigue une collection représentative pendant 15 min | Mémoire bornée; fallback stock lisible à saturation; aucun forçage artificiel de pénurie sur lecteur | VIDEO+METRICS |
| VIS-07 | P0 / A+F | Profil LOGO seul, image avec repères de bord et transparence | F démarre puis compare au cadrage app | Logo centré aux bonnes dimensions; zones transparentes propres; readiness vraie; pas besoin de Stems/Key Shift | PHOTO+HASH |
| VIS-08 | P1 / A+F | Logo dark/light distinct puis une seule image fournie | F bascule thème et inspecte | Bonne variante utilisée; fallback à l’image fournie cohérent; gris préservés selon option | PHOTO |
| VIS-09 | P0 / A+F | Nouveau logo sur clé, puis fichier invalide sur copie dédiée | F réinsère selon U; A suit génération et readiness | Nouveau logo après restart prévu; invalide rejeté et pas de succès trompeur; restauration de la version saine | LOG+PHOTO+HASH |
| VIS-10 | P0 / A+F | Thème et logo retirés par nouvelle sélection puis démarrage stock | F inspecte les mêmes écrans | Placement et images natives rétablis; aucun hook résiduel ni zone d’image invalide | PHOTO+ENV |

<a id="doc-acceptance-0-6-0-cas-de-test--now-playing"></a>
#### Now Playing

| ID | Priorité / acteur | Préparation par A | Action à exécuter | Résultat attendu | Preuve |
|---|---|---|---|---|---|
| NP-01 | P0 / A+F | Récepteur UDP 50123 sur ordinateur, connexion USB-B | F charge D1 puis D2; A capture les datagrammes | JSON valide, deux decks corrects, titres/BPM/IDs cohérents; rien attribué au mauvais deck | NETWORK+VIDEO |
| NP-02 | P1 / A+F | Deux pistes Unicode et titres longs | F remplace un morceau pendant lecture de l’autre | Texte encodé/échappé correctement; snapshot des deux decks cohérent | NETWORK |
| NP-03 | P0 / A+F | Pistes connues; capture réseau prête | F exécute play/pause/cue, tempo puis fader/on-air; A corrèle les événements | Table observée des valeurs brutes et unités; aucune traduction play mode/tempo annoncée sans preuve | NETWORK+VIDEO |
| NP-04 | P1 / A | Récepteur lancé après démarrage du module | Attendre puis arrêter/relancer le récepteur | Heartbeats environ toutes les 2 s; état complet récupéré sans recharger de piste | NETWORK |
| NP-05 | P0 / A+F | Récepteur absent puis câble déconnecté, audio continu | F poursuit le mix; A restaure le récepteur ensuite | Télémétrie sans blocage audio; reprise automatique; absence de destinataire tolérée | AUDIO+NETWORK |
| NP-06 | P0 / A+F | Module retiré puis redémarrage du profil FINAL | A observe UDP; F charge et joue deux pistes | Plus de datagrammes du module; aucun thread fantôme; lecteur normal | NETWORK+ENV |

<a id="doc-acceptance-0-6-0-cas-de-test--insertion-usb-redmarrage-retrait-et-rcupration"></a>
#### Insertion USB, redémarrage, retrait et récupération

| ID | Priorité / acteur | Préparation par A | Action à exécuter | Résultat attendu | Preuve |
|---|---|---|---|---|---|
| USB-01 | P0 / A+F | U1 inchangée; pistes arrêtées/déchargées de U1 | F éjecte proprement puis réinsère 5 fois; A compare PID/starttime, core et inodes | Pas de restart sans changement; liens remis à jour si montage change; pas de modification inutile d’actifs | ENV+HASH+LOG |
| USB-02 | P0 / A+F | Musique depuis U2, U1 mod identique sans piste chargée depuis U1 | F éjecte/réinsère U1 pendant lecture U2 | PID et audio inchangés; pas de reset des états des decks | AUDIO+ENV+LOG |
| USB-03 | P0 / A+F | U2 en lecture; U1 contient nouvelle génération core/logo/config | F insère U1; A observe puis attend une fenêtre sûre | Modification différée par garde média; pas de remplacement des fichiers live ni interruption U2; motif explicite | AUDIO+HASH+LOG |
| USB-04 | P0 / A+F | Aucun autre média actif; nouvelle génération prête | F insère U1 et attend le message de fin | Un restart planifié; core et ressources de même génération; base USB redevient visible; aucun double autoexec | ENV+VIDEO+LOG |
| USB-05 | P0 / A+F | Config Key Match/BROWSE inchangée puis réellement modifiée | F réinsère les deux builds successivement en période sûre | No-op accepté; vrai changement appliqué au bon moment; absence d’échec shell sur code sans changement | LOG+VIDEO |
| USB-06 | P0 / A+F | Banque identique déplacée, puis même nom/audio changé, puis banque désactivée | F suit les trois insertions proposées | Identique repointe sans reset inutile; changé/désactivé applique la bonne génération via restart; aucun ancien contenu | HASH+AUDIO+ENV |
| USB-07 | P0 / A+F | COMPLET puis retrait d’un module en conservant Core | F réinsère hors lecture; A inspecte la sélection et le processus | Fonction retirée réellement absente après restart; autres modules opérationnels; pas de résidu de hook | LOG+VIDEO+ENV |
| USB-08 | P0 / A+F | COMPLET puis suppression de Core et de ses dépendants via l’app | F suit la procédure de retrait puis démarre sans mod | Retour stock complet et vérifié; si retrait à chaud non supporté, app/documentation imposent le cycle nécessaire; aucun faux succès | LOG+VIDEO+ENV |
| USB-09 | P0 / A+F | Démarrage froid, mod non encore actif | F tient SHIFT gauche avant insertion jusqu’à reconnaissance; recommence SHIFT droite | Chaque bouton déclenche le bypass; pas de patch/module/log USB appliqué pour cette insertion; lecteur stock | VIDEO+ENV |
| USB-10 | P0 / A+F | Mod déjà actif; insertion avec SHIFT tenu | F réinsère en SHIFT puis compare | Insertion ignorée mais mod actif non prétendu désinstallé; retour stock seulement via procédure prévue | VIDEO+ENV |
| USB-11 | P0 / A | Lecteur idle, plan de secours validé; double lancement contrôlé du même orchestrateur | Déclencher uniquement via voie qualifiée, puis vérifier le verrou; sinon rester BLOQUE | Une seule application; concurrent refuse sans supprimer le workspace du premier; pas de stale lock non expliqué | LOG+ENV |
| USB-12 | P0 / A+F | Installation délibérément invalide sur clé de test, aucune lecture | F insère; A observe refus/rollback puis propose la clé saine | État précédent restauré si transition commencée; refus avant changement sinon; retour à la lecture native démontré | LOG+HASH+VIDEO |
| USB-13 | P0 / A+F | Logging simple/verbose puis OFF, U1/U2 | F éjecte uniquement par procédure native ou arrête complètement si nécessaire | Retrait sans corruption ni handle bloquant inexpliqué; procédure exacte documentée par mode; hashes musique inchangés | HASH+LOG |
| USB-14 | P1 / A+F | USB1 puis USB2, supports FAT compatibles distincts; chemins longs | F répète chargement et réinsertion | Pas de dépendance au nom sda/sdb ni au port; bonne bibliothèque et bons stems | LOG+VIDEO+HASH |

<a id="doc-acceptance-0-6-0-cas-de-test--combinaisons-endurance-et-validation-finale"></a>
#### Combinaisons, endurance et validation finale

| ID | Priorité / acteur | Préparation par A | Action à exécuter | Résultat attendu | Preuve |
|---|---|---|---|---|---|
| END-01 | P0 / A+F | Chaque module seul avec ses dépendances minimales, puis COMPLET | A prépare les profils; F fait le smoke de chaque fonction | 17 modules couverts; dépendances exactes; absence de couplage caché à un module non sélectionné | HASH+VIDEO+LOG |
| END-02 | P0 / A+F | COMPLET, M01/M02, 4 samples et capture audio | F joue 30 min: stems, Key Shift, Beat Jump, tri BROWSE et thème selon séquence imposée | Zéro crash/restart/coupure inexpliquée; commandes utiles malgré concurrence; défauts audio caractérisés | AUDIO+VIDEO+METRICS |
| END-03 | P0 / A+F | Même génération; cycle de 10 min répété 12 fois | A pilote observations et changements préparés; F assure gestes requis ou lecture continue définie | Endurance 2 h; mémoire/threads/FD stabilisés; aucun état coincé; stress actif distingué du simple idle | AUDIO+METRICS+LOG |
| END-04 | P0 / A+F | Profil FINAL sans Telnet/logs et même artefact candidat | F mixe 30 min; A capture depuis ordinateur sans instrumentation lecteur | Comportement confirmé hors profil diagnostic; audio et UI ne dépendent pas des sondes | AUDIO+VIDEO+HASH |
| END-05 | P0 / A+F | 5 démarrages à froid dont un avec deux clés, sans retrait brutal | F démarre/arrête selon consigne; A compare chaque session | Pas de course aléatoire au boot; readiness et médias corrects à chaque fois | VIDEO+LOG |
| END-06 | P0 / A | Résultats complets pour chaque firmware revendiqué | Relire preuves, anomalies, hashes et cas BLOQUE/NON_EXECUTE | Aucun P0 non résolu ni P1 affectant le set; couverture firmware explicitement limitée si un seul appareil/version testé | DOC |

<a id="doc-acceptance-0-6-0-cas-de-test--compatibilit-de-distribution-et-options-exprimentales"></a>
#### Compatibilité de distribution et options expérimentales

| ID | Priorité / acteur | Préparation par A | Action à exécuter | Résultat attendu | Preuve |
|---|---|---|---|---|---|
| DIST-01 | P0 / A+F | Chaque OS et architecture réellement publié; application empaquetée | A répète installation, ouverture, sélection USB, build et préparation M01; F aide seulement pour permissions système | Chaque binaire publié testé; Linux/WebKit, macOS signature et Windows chemins contrôlés selon cible | LOG+HASH+VIDEO |
| DIST-02 | P0 / A+F | Firmware 1.19 puis 1.20 sur banc disponible distinct ou changement planifié séparément | Rejouer P0 et smoke de chaque module avec mêmes médias | Résultats propres à chaque firmware; les trois octets de différence ne remplacent pas une recette réelle | DOC+HASH |
| DIST-03 | P1 / A | OverCue OFF puis ON, source lossless et source lossy | Exporter, relire les fichiers, tester refus et manque de place sur copie | Option OFF inchangée; ON produit sortie vérifiée avec estimation; restriction lossless explicite; échec ne détruit pas les paquets RX3 | HASH+LOG |
| DIST-04 | P1 / A+F | CDJ-3000 et environnement OverCue disponibles séparément | F teste reconnaissance, rôles, seek et deux decks sur la cible; sinon noter NON_EXECUTE | Aucune compatibilité CDJ déclarée validée à partir des seuls tests RX3; option reste expérimentale sans cette preuve | VIDEO+AUDIO+DOC |
| DIST-05 | P1 / A+F | Seulement si le binaire livré active RX3_OVERCUE_PROTOTYPE; fichiers 96 kHz de test vérifiés | A identifie le flag réel; si activé, F teste lecture, rôles, seek, chargements rapides et 2 decks sur RX3 | Cache/conversion sans sous-alimentation ni désynchronisation; sinon NA_JUSTIFIE flag absent, distinct de l’export desktop OverCue | HASH+AUDIO+METRICS |


---

<a id="doc-acceptance-0-6-0-session"></a>
## Fiche de session RX3 0.6.0



<a id="doc-acceptance-0-6-0-session--identification"></a>
#### Identification

- Session / début / fin / opérateurs :
- RX3 / firmware / hash du rbp stock identifié :
- Application / OS / architecture / SHA-256 :
- Commit / patch local archivé / manifest / profil :
- SHA-256 autoexec / core / ressources / corpus :
- USB U0/U1/U2 : identité, format, port, espace libre :
- Connexion diagnostic / interface réseau (pas de mot de passe) :
- Capture audio, fréquence, canaux, gains, référence et vidéo :
- État initial D1/D2, MASTER, tempo/MT/Quantize, gains, thème :
- Tests hôte / compilation / preflight du candidat :
- Q-06 chargement distant : QUALIFIE / NON QUALIFIE, preuve :
- Écarts de contrat Q-07 résolus / restants :

<a id="doc-acceptance-0-6-0-session--rsultat-dun-cas-ou-dune-variante"></a>
#### Résultat d’un cas ou d’une variante

- ID parent / variante / répétition :
- Préparation terminée et vérifiée par :
- Horodatage et marqueur de capture :
- Geste demandé / geste réellement réalisé :
- Résultat attendu :
- Observation de François :
- Mesure de l’assistant, unité et méthode :
- PID/starttime avant/après, erreur noyau/runtime éventuelle :
- Preuves relatives (audio, vidéo, log, hash, oracle) :
- Statut : NON_EXECUTE / EN_COURS / OK / NOK / BLOQUE / NA_JUSTIFIE
- Anomalie associée / motif si bloqué ou non applicable :
- État final et remise à zéro :

<a id="doc-acceptance-0-6-0-session--anomalie"></a>
#### Anomalie

- BUG-ID / sévérité P0-P1 / module(s) :
- Première occurrence, candidat et cas :
- Symptôme exact, fréquence (n/N), impact sur le set :
- Dernière action; conditions préalables; reproduction minimale :
- Attendu vs observé, chacun séparé :
- Preuves, sans secret ni chemin privé publié :
- Cause confirmée / hypothèses / vérifications restantes :
- Récupération effectuée et état stock vérifié :
- Correctif / nouveau candidat :
- Cas rejoué / voisins / régression / endurance :
- Décision : OUVERT / CORRIGE_A_RETESTER / FERME_AVEC_PREUVE / RESERVE_ACCEPTEE

<a id="doc-acceptance-0-6-0-session--dcision-de-session-et-release"></a>
#### Décision de session et release

- Nombre de variantes : prévues / OK / NOK / BLOQUE / NON_EXECUTE / NA_JUSTIFIE :
- Firmware et plateformes couverts :
- P0 ouverts; P1 ouverts et impact :
- Avis audio/ergonomie de François :
- Réserves à reprendre dans la release note :
- Artefact FINAL et hash validés :
- Décision motivée : GO / NO-GO / CAMPAGNE_INCOMPLETE
- Prochaine étape concrète :

---

---
