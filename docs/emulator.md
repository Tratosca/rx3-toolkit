# Émulateur minimal RX3 1.19 avec écran tactile virtuel

Cet outil exécute le véritable binaire ARM `rbp` et les bibliothèques du
firmware 1.19 dans Docker/QEMU. Un shim remplace `fbdev` et les périphériques
indispensables au démarrage, puis exporte le framebuffer DirectFB en PNG. La
commande principale ouvre aussi une fenêtre 1280×720 : un clic y est routé
vers les onglets et les contrôles du broker KEY/STEMS.

Deux niveaux complémentaires sont disponibles :

- `make emulate` exécute `rbp`, affiche son framebuffer et fournit le tactile
  virtuel utile à la validation rapide des mods ;
- `make emulate-system` exécute le vrai U-Boot et le vrai noyau RX3 sur le
  modèle i.MX6Q de QEMU ;
- `make emulate-system-fast` poursuit avec le rootfs 1.19, `/sbin/init`,
  `rcS`, `apl_start`, `rbp` et vérifie que DirectFB crée son framebuffer.

Les deux chemins sont volontairement séparés :

```text
validation visuelle : Docker/QEMU-user -> rbp -> fbdev virtuel -> fenêtre tactile
validation système  : QEMU i.MX6Q -> noyau -> init -> apl_start -> rbp -> fbdev virtuel invité
```

Le framebuffer du second chemin est actuellement prouvé dans la VM mais pas
encore transporté vers la fenêtre macOS. Pour voir et piloter l'écran, utilisez
donc `make emulate`. Un succès graphique n'est pas présenté comme une preuve
du boot système, et réciproquement.

Le premier niveau ne simule pas un RX3 complet. Il valide le chargement ELF,
les gardes des hooks, le démarrage de `rbp`, le chemin de rendu natif et le
routage tactile des mods. Il ne valide pas le DSP audio, les LEDs, les accès
USB réels ni la stabilité sur appareil.

`UiObjectManager::init()` va désormais jusqu'au bout et `startUp()` s'exécute :
`/dev/subucom_spi1.0`, `/dev/subucom_spi2.0` et `/dev/tsc2007_2-0048` sont
ouverts, treize périphériques au lieu de huit. Voir « Le verrou, trouvé et
levé ». Rien n'écrit encore dans ces nœuds, donc les clics passent toujours par
la FIFO privée du mod et non par le `solveCoordToKey` de `rbp` ; c'est
maintenant réalisable, et non plus bloqué.

Les hypothèses que ce niveau fait sur le matériel, et la façon de les vérifier
sur un vrai RX3, sont rassemblées dans
[hardware-questions.md](hardware-questions.md) — à lire avant de toucher au
`/dev/gpiodrv` d'un appareil sous tension.

## Prérequis

- Docker Desktop démarré avec l'émulation `linux/arm/v7` ;
- le sysroot 1.19 privé dans `local/research/rx3-lab/sysroot` ;
- `clang` et `lld` pour compiler le hook ARM lorsque des mods sont activés.

Le firmware, `rbp` et les ressources propriétaires restent dans `local/` et ne
sont jamais ajoutés au dépôt. Le sysroot est monté en lecture seule. Le runner
copie seulement `/root/pdj` dans le conteneur avant d'appliquer le patch requis.

## Utilisation

```sh
make emulate
```

La commande teste le profil `all` pendant 300 secondes. Les résultats sont dans
`outputs/rx3-emulator/<date>/`. Cliquez dans l'écran pour piloter KEY/STEMS ;
Échap ou `q` ferme la session. `--duration 0` supprime la limite et laisse la
fenêtre ouverte jusqu'à sa fermeture ; ce mode exige `--window`, faute de quoi
rien ne pourrait interrompre la session sans perdre le rapport. Les artefacts
comprennent :

- `framebuffer.png` : dernière image 1280×720 ;
- `rbp.log` et `hook.log` : journaux séparés ;
- `report.json` : empreintes des binaires, assertions et périmètre de preuve.

Pour isoler une régression :

```sh
python3 -m tools.rx3_emulator.cli --profile stock --duration 45
python3 -m tools.rx3_emulator.cli --profile keyshift --duration 60
python3 -m tools.rx3_emulator.cli --profile stems --duration 60
python3 -m tools.rx3_emulator.cli --profile all --duration 60
```

Un succès du profil modifié exige un framebuffer non vide, le fichier de
readiness du hook, le message d'activation, la table d'images privée, des
compteurs de rendu non nuls et le canal tactile virtuel.

## La fenêtre

La conversion du framebuffer emprunte deux chemins. Celui de la bibliothèque
standard n'a aucune dépendance et écrit le `framebuffer.png` que cite
`report.json` ; c'est une boucle Python par pixel sur 921 600 pixels, soit
environ 220 ms par image, incapable d'animer quoi que ce soit. Quand Pillow est
importable, le même dépaquetage se fait en C — mesuré à 3,5 ms, soit 64 fois
plus vite — et la fenêtre est alimentée en mémoire par un PPM remis directement
à `PhotoImage`, sans zlib, sans fichier temporaire et sans second décodage.

Pillow n'est qu'un accélérateur : il ne doit jamais changer un pixel. Or son
mode `BGR;16` élargit les canaux de 5 et 6 bits avec son propre arrondi, qui
diffère de la réplication des bits de poids fort sur 15 des 32 niveaux rouges
et bleus et 30 des 64 niveaux verts. Une table d'inversion, **mesurée** à
l'import plutôt qu'écrite en dur, rétablit l'égalité ; `tests/test_rx3_emulator`
la vérifie sur les 65 536 mots RGB565 possibles.

Sous l'écran, une façade de boutons vise les mêmes pixels qu'un doigt, puisque
le seul canal d'entrée actuel reste la FIFO tactile que scrute le hook. Les
colonnes des contrôles diffèrent d'un panneau à l'autre — trois pour KEY, deux
pour STEMS — donc la rangée est reconstruite à chaque changement d'onglet. La
géométrie est une seconde copie de celle d'`emulator_apply_touch` ; un test la
relit dans le C et échoue si les deux divergent.

## Les touches physiques au-dessus de l'écran

`InitUiBrowseKey` enregistre chaque touche dans une table de 230 entrées de
16 octets — état en `+8`, gestionnaire en `+12` — et `BrowseKeyProcessing()`
la parcourt en appelant le gestionnaire de toute entrée marquée. Marquer une
entrée via `UiKey_KeyPush(index, 0, 0, 1)` constitue donc *tout* l'appui : ni
microcontrôleur de façade, ni dépendance à `startUp()`.

Les index, relevés dans `InitUiBrowseKey` :

| Touche | Index | Touche | Index |
|---|---:|---|---:|
| SOURCE | 4 | MENU | 10 |
| BROWSE | 5 | Encodeur (appui) | 11 |
| TAG LIST | 6 | LOAD deck 1 | 12 |
| PLAYLIST | 7 | LOAD deck 2 | 13 |
| SEARCH | 8 | BACK | 17 |

MENU est un appui long — trois secondes — et la durée est mesurée par le
gestionnaire pendant que l'entrée reste marquée : la maintenir fait partie du
geste, l'écourter en fait un autre. Le protocole de la FIFO accepte donc
`<seq> k <index> [hold_ms]` à côté de `<seq> <x> <y>`.

**Le pompage ne tourne pas de lui-même.** Mesuré : une touche marquée puis
laissée reste marquée, et l'appui suivant est refusé, `UiKey_KeyPush` n'accep­tant
un appui que sur une entrée libre. Le hook appelle donc `BrowseKeyProcessing()`
directement — elle ne prend aucun argument et retrouve la table seule ; les
appuis successifs sont alors tous acceptés.

**Mais l'écran ne change pas.** Comparaison image par image avant/après SOURCE,
BROWSE et un MENU de trois secondes : **zéro pixel modifié**. Les gestionnaires
s'exécutent et rendent la main, mais n'ont pas d'interface à piloter — ce qui
est exactement la forme attendue si `BrowseUiIfDpl` et `UsbBrowser` n'ont jamais
été construits. C'est le même verrou que ci-dessous.

## Le verrou, trouvé et levé

`main` n'appelle `IReceptionForMAIN::startUp()` que si `r0` est non nul après
`initialize_()`, qui est `void` : le `cmp` lit donc le résultat de
`UiObjectManager::init()`. Cette fonction ne rendait jamais la main.

`--trace-init` pose des hooks gardés à l'entrée et à la sortie des constructeurs
qu'appelle `init()`. Le flux est diffusé en direct dans la console, `hook.log`
n'étant recopié qu'à l'arrêt du conteneur. Le décompte a désigné le coupable :
`PcController` entrait et sortait, `UsbStorageManager` entrait sans ressortir,
et un niveau plus bas `GpioManager` entrait 16 fois pour 15 sorties.

`common::GpioManager::GpioManager` (`0x00028cd8`) ouvre `/dev/gpiodrv`, se
positionne par `lseek` sur le numéro de GPIO, lit un octet, puis le transmet à
un `GpioCallback` **par un emplacement de vtable** — précisément l'arc qu'aucun
graphe d'appels statique ne suit, et la raison pour laquelle un parcours inverse
depuis toutes les primitives bloquantes ne trouvait aucun chemin.

Pour `UsbStorageManager`, ce rappel est `handleGpioMessage`, qui filtre les
GPIO `0x7e` et `0xcc` — les entrées de **surintensité USB** — et les passe à
`notify_over_current`. Ces lignes sont **actives à l'état bas** :

```c
if (param_1) return;                  /* 1 : rien à signaler */
(**(code **)(... + 0xc))(...);        /* 0 : défaut -> appel virtuel */
request_usb_stop(this);               /*      puis arrêt de la pile USB */
```

Notre `/dev/gpiodrv` factice était un fichier vide : toute lecture renvoyait
EOF, puis, une fois le fichier complété, l'octet `0`. Autrement dit une
surintensité USB permanente, signalée pendant la construction. `init()` n'en
revenait pas.

**Le correctif tient dans un octet** : remplir `/dev/gpiodrv` de `1` plutôt que
de `0`. Tous les compteurs s'équilibrent, `init()` rend la main, `startUp()`
s'exécute, et `rbp` ouvre 13 périphériques au lieu de 8 — dont
`/dev/subucom_spi1.0`, `/dev/subucom_spi2.0` et `/dev/tsc2007_2-0048`, soit les
ouvertures n° 62 à 64 de la trace de référence relevée sur l'appareil.

Deux pistes voisines ont été essayées et mesurées avant celle-ci, toutes deux
négatives, et sont consignées dans `fbshim.c` pour ne pas être refaites : passer
`/proc/udev_usb*` en tubes, et y annoncer une clé présente.

Deux ELF sont compilés. `librx3_core.so` reste le livrable de production.
`librx3_core_emulator.so` ajoute uniquement, sous `RX3_EMULATOR_BUILD`, le
panneau initial et le canal de clics nécessaires faute de façade physique. Les
deux empreintes sont consignées dans `report.json`. L'acceptation finale d'un
mod audio ou matériel reste un test sur RX3 réel. Les périphériques ne se
laissent pas convaincre par un PNG, ce qui est d'une mesquinerie assez
constante chez eux.

## Émulation système i.MX6Q

```sh
make emulate-system
```

Cette commande utilise directement les artefacts privés 1.19 :
`u-boot.bin.nand`, `uImage` et `rootfs.cramfs`. Leurs SHA-256 sont contrôlés
avant exécution. Deux journaux et un rapport JSON sont écrits dans
`outputs/rx3-system-emulator/<date>/`.

Le U-Boot Pioneer est chargé à son adresse de link `0x17800000`. Le noyau
Linux 3.0.101 est inchangé ; un petit stub fournit uniquement le
protocole ATAG historique, l'identifiant machine Sabre-SD `3980` et l'adresse
d'entrée `0x10008000`. Cette adaptation est requise parce que la machine QEMU
`sabrelite` démarre normalement avec un device tree, alors que le noyau RX3 a
`CONFIG_USE_OF` désactivé.

La sonde validée atteint actuellement :

- U-Boot 2009.08, i.MX6Q, 1 Gio de RAM, I²C et quatre contrôleurs USDHC ;
- Linux `3.0.101-2790-gc248ed7-svn3098` ;
- les pilotes RX3 `subucom`, `gpiodrv`, `TSC2007` et `mxc_sdc_fb`.

Pour démarrer également l'environnement utilisateur réel :

```sh
make emulate-system-fast
```

Ce profil extrait l'`Image` ARM du `uImage`, superpose le sysroot privé dans un
initramfs externe et adapte seulement les interfaces matérielles absentes. Les
ELF remplacés par un wrapper restent présents avec le suffixe `.real`. La
chaîne vérifiée est :

```text
Linux 3.0.101 -> /init -> BusyBox init -> rcS -> rc.local
              -> apl_start -> rbp.real -r -a -> framebuffer 1280x720x32
```

Une seule instruction noyau est neutralisée : l'entrée `gpu_init` retourne
zéro, car QEMU ne fournit aucun modèle Vivante Galcore. La garde vérifie les
8 octets d'origine avant le patch et le rapport consigne avant/après, offset,
empreintes du firmware, de l'initramfs et du shim. Les variables U-Boot,
`bootmod`, `boardrev`, GPIO et registres sont simulés uniquement dans
l'initramfs temporaire ; le sysroot privé sur disque n'est pas modifié.

Ce profil ne fait pas passer le noyau à travers U-Boot : les deux binaires
Pioneer sont exécutés et vérifiés par des sondes distinctes. Les contrôleurs
de stockage attendus par le script de boot original ne sont pas suffisamment
modélisés par la machine `sabrelite` pour former une chaîne U-Boot → SD/NAND
fidèle.

Le boot système complet exige encore des modèles QEMU pour GPMI NAND/APBH
DMA, IPU/LDB, le tactile I²C/IRQ et les coprocesseurs Pioneer SPI. Le modèle
i.MX6Q amont fournit le CPU, les UART, timers, GPIO, I²C, USDHC, USB, SPI et
Ethernet, mais pas la NAND ni le pipeline graphique utilisés par ce firmware.
En conséquence, l'écran tactile exploitable reste pour l'instant fourni par
`make emulate`; les modes système prouvent séparément le bootloader, le SoC,
le noyau et le démarrage de l'espace utilisateur sans prétendre simuler les
périphériques manquants.
