<!-- SPDX-License-Identifier: MPL-2.0 -->
# Questions à poser au RX3

Ce que l'émulateur suppose du matériel sans pouvoir le vérifier, et comment le
vérifier sur l'appareil. Chaque entrée dit ce dont on doute, la mesure qui
tranche, et ce que chaque résultat signifierait — de sorte qu'une mesure qui
contredit l'hypothèse soit aussi utile qu'une qui la confirme.

L'accès est un shell root par `busybox telnetd` (`ANALYSE.md` §20.8), sans
écriture persistante. Rien ici ne modifie la NAND.

## Avertissement : lire un GPIO le reconfigure

`chardev_read` de `gpiodrv` ne se contente pas de lire :

```c
gpio = (unsigned)(*offset);
if (gpio_request(gpio, "gpiodrv") < 0) return -EFAULT;
gpio_direction_input(gpio);       /* <-- la broche devient une entrée */
rc = gpio_get_value(gpio);
```

Lire une broche qui est normalement une **sortie** la bascule en entrée haute
impédance. Sur un appareil sous tension cela peut relâcher un reset, couper une
alimentation, démuter un ampli ou éteindre un rétroéclairage. **Ne pas balayer
`/dev/gpiodrv` de 0 à 255.** Les seules broches sûres sont celles que `rbp` lit
lui-même déjà comme entrées, listées ci-dessous : les relire ne fait rien de
nouveau.

---

## 1. Les entrées de surintensité USB — priorité haute

**Le doute.** Le blocage de l'émulateur a été levé en faisant lire `1` au lieu
de `0` sur `/dev/gpiodrv`, au motif que ces lignes sont actives à l'état bas.
Le raisonnement colle au code (`notify_over_current` rend la main sur 1 et
démonte la pile USB sur 0) et le résultat est net, mais **personne n'a vérifié
ce que l'appareil lit réellement**. Un correctif qui marche n'est pas un
correctif qui est juste.

Les deux broches, tirées du constructeur `UsbStorageManager` (`this[0x84]`
sélectionne l'une ou l'autre) :

| GPIO | Décimal | i.MX6 | Canal |
|---|---:|---|---|
| `0x7e` | 126 | GPIO4_30 | 1 |
| `0xcc` | 204 | GPIO7_12 | 2 |

**La mesure**, `rbp` tournant normalement, sans clé USB puis avec :

```sh
dd if=/dev/gpiodrv bs=1 skip=126 count=1 2>/dev/null | od -An -tu1
dd if=/dev/gpiodrv bs=1 skip=204 count=1 2>/dev/null | od -An -tu1
```

**RÉPONDU — mesuré sur l'appareil, clé USB insérée et montée :**

```
GPIO 126 (GPIO4_30, canal 1) -> 001
GPIO 204 (GPIO7_12, canal 2) -> 001
```

Les deux lignes reposent à **1**. L'hypothèse est confirmée : elles sont bien
actives à l'état bas, l'émulateur rapporte ce que rapporte le matériel, et le
correctif `gpiodrv` est juste et non simplement efficace.

## 2. Le contenu de la trame façade — priorité haute

**Le doute.** L'enveloppe est connue par `subucom_jogtest.c` : 100 octets,
charge utile 0..95, CRC-16/CCITT réfléchi (poly `0x8408`, init `0xFFFF`, xor
final) dans la moitié haute du mot 32 bits à l'offset 96, **chaque groupe de
4 octets inversé** car l'ECSPI travaille en mots de 32 bits. Ce qui manque est
la seule chose qui compte pour piloter la façade : **quel bit est quelle
touche**. La source GPL ne le dit pas et `rbp` ne le dit pas non plus.

**La mesure.** Capturer des trames au repos, puis en maintenant une touche, et
comparer :

```sh
dd if=/dev/subucom_spi1.0 bs=100 count=20 2>/dev/null | od -An -tx1 > /tmp/idle.hex
# puis en maintenant PLAY du deck 1
dd if=/dev/subucom_spi1.0 bs=100 count=20 2>/dev/null | od -An -tx1 > /tmp/play.hex
```

Une touche à la fois, en notant laquelle. Les octets qui changent donnent la
carte.

**Réserve honnête.** Avec le timer actif, `read()` est une simple copie d'un
instantané noyau, donc la lecture ne consomme pas la trame — mais elle remet
`rx_detected` à zéro, et `rbp` détecte les appuis sur ce drapeau. Capturer
pendant que `rbp` tourne peut donc lui faire manquer des appuis. Ce n'est pas
dangereux, c'est simplement à savoir : si l'appareil rate des touches pendant la
capture, c'est la capture qui en est la cause.

### RÉPONDU en partie — mesuré sur l'appareil

**Les touches ne sont pas sur le nœud qu'on croyait.** `/dev/subucom_spi1.0`
(ECSPI2, µCOM « ERP », celui qu'utilise `subucom_jogtest.c`) ne bouge pas d'un
octet quand on appuie. Les touches sont sur **`/dev/subucom_spi2.0`**, le µCOM
« SUB » d'ECSPI3.

**Géométrie de la trame SUB, vérifiée par CRC** — 28 octets, charge utile
`0..23`, CRC-16 dans la moitié haute du mot 32 bits à l'offset **24**. Même
algorithme que la trame jog (poly `0x8408`, init `0xFFFF`, xor final, sur la
charge utile inversée par mots de 4 octets). Vérifié au repos *et* touche
enfoncée :

```
repos      CRC_POS=24: stocké=0x0e3d calculé=0x0e3d  OK
PLAY tenu  CRC_POS=24: stocké=0x68eb calculé=0x68eb  OK
```

La trame jog de `spi1.0` reste, elle, de 100 octets avec son CRC à l'offset 96 —
également vérifié sur trame réelle (`0xc262`). Les deux µCOM ont donc la même
enveloppe et des longueurs différentes.

**Carte des touches, début :**

| Touche | Octet | Bit | Masque |
|---|---:|---:|---|
| PLAY deck 1 | 7 | 6 | `0x40` |
| CUE deck 1 | 7 | 7 | `0x80` |

L'octet 7 est donc le registre de transport du deck 1, et la disposition est un
champ de bits groupé par deck plutôt que par fonction — ce qui indique où
chercher le reste : les bits 0 à 5 du même octet, puis l'octet symétrique du
deck 2.

Les octets 26–27 changent à chaque appui : c'est le CRC qui suit la charge
utile, pas une donnée de touche.

**L'octet 22 : deux hypothèses posées, deux réfutées.** Il a d'abord semblé
dériver seul — faux : trois captures espacées de trois secondes sans aucune
action sont identiques au bit près. Il a ensuite semblé porter le mode de pad,
puisqu'il avait changé pendant qu'une touche de mode était pressée — faux
également : sélectionner BEAT LOOP, LED passée à l'orange et HOT CUE éteinte,
ne change **aucun octet** de la trame. Il a changé une fois de `0xEC` à `0xEB`
et n'a plus bougé. Sa signification reste inconnue ; ce n'est ni du bruit ni le
mode.

**Ce que la trame porte, et ce qu'elle ne porte pas.** Cette trame va du µCOM
vers l'hôte et transporte l'**état brut des touches**. Le mode de pad est un
état logiciel de `rbp`, et la couleur des LED est la direction **inverse**
(hôte vers µCOM, via `SubMiconTx::setFullColorLed`). Ni l'un ni l'autre
n'apparaît ici.

Conséquence : les quatre sélecteurs de mode sont des touches **momentanées**
comme les autres. Leur bit n'existe que pendant l'appui, donc elles exigent le
même protocole « maintenir puis signaler » que PLAY, CUE et les huit pads. Une
capture après relâchement ne montre rien — c'est exactement ce qui a été mesuré.

Méthode qui marche : demander de **maintenir** la touche et de le signaler
pendant qu'elle est tenue, puis capturer. Une capture programmée à l'avance rate
la fenêtre — soixante secondes d'échantillonnage pendant une séquence d'appuis
n'ont rien donné, faute de synchronisation.

### Ce que l'analyse statique a rendu inutile

La carte des touches n'a pas besoin de l'appareil. `keyCodeAsText()` contient la
table complète des codes, et `docs/rx3-key-codes.md` la donne : 146 entrées
nommées, obtenues hors ligne. Cartographier la façade à la main aurait demandé
un appui par touche, un opérateur devant la machine et une fenêtre de
synchronisation qui se rate — ce qui s'est produit deux fois.

Reste propre à la capture matérielle : **quel bit de quelle trame** porte quelle
touche. Utile pour lire la façade, inutile pour l'injecter — `onKey_*` prend un
`IKeyInput` dont la disposition est connue, et les codes le sont maintenant
aussi.

## 3. Le format de pixel des couches pads — priorité moyenne

**Le doute.** Les contrôles KEY/STEMS n'ont ni graduation de couleur ni retour
d'appui parce que `NS_PALRender_DrawText` décode son champ couleur de trois
façons selon le format de pixel de la fenêtre, qu'il lit dans
`DS_GR_GetWindowInfo` et non dans le glyphe. RGB888 a donné du magenta sur du
vert, RGB565 du vert, et un balayage des 256 valeurs basses n'a jamais fait
sortir le rouge ni le bleu de zéro.

**La mesure.** Un `autoexec.bin` qui appelle `DS_GR_GetWindowInfo` pour les
couches `0x1701` et `0x1801` et journalise le format retourné. C'est le seul
chiffre manquant ; il débloque d'un coup la couleur, l'état sélectionné et le
retour d'appui.

## 4. Les étiquettes stock de la rangée de pads — priorité moyenne

**Le doute.** Les contrôles portent la police de l'en-tête, deux fois trop
grande, parce que le modèle cloné vient de l'en-tête. La capture d'une vraie
étiquette de pad est écrite et en place, mais n'a jamais été déclenchée : aucun
tracé de texte n'a été observé dans le sous-arbre `0x17xx` / `0x18xx` sous
émulation.

**La question.** Sur l'appareil, la rangée de pads affiche-t-elle du texte que
`rbp` dessine (et non une image) ? Si oui, la capture se déclenchera d'elle-même
et la police se corrigera sans autre travail. Si la rangée est faite d'images,
l'approche du clonage est à revoir entièrement.

## 5. Fidélité de l'émulateur — priorité basse, mais gratuit

**La ligne de commande — CONFIRMÉ.** Relevé sur l'appareil dans
`/proc/<pid>/cmdline` : `/root/pdj/rbp`, **sans `-a`**. L'émulateur lance
`rbp -a`. La divergence est réelle et sans effet observé, mais elle n'a jamais
été justifiée : autant aligner l'émulateur.

**Le jeu de périphériques réel — RELEVÉ.** `rbp` tient 65 descripteurs ouverts,
dont :

| Chemin | Nombre |
|---|---:|
| `/dev/gpiodrv` | 17 |
| `/dev/snd/seq`, `/dev/hidg0` | 2 chacun |
| `/dev/subucom_spi{1,2}.0`, `/dev/subucom_spi_rdy{3,4}.0` | 1 chacun |
| `/dev/tsc2007_2-0048`, `/dev/fb0`, `/dev/mem`, `/dev/galcore` | 1 chacun |
| `/dev/paudiog0`, `/dev/snd/pcmC{0,1}D*{p,c}` | 1 chacun |
| `/proc/udev_usb{1,2}`, `/proc/udev_usbctn{1,2}` | 1 chacun |

L'émulateur en ouvre treize à quatorze. Manquent notamment `/dev/mem`,
`/dev/galcore`, `/dev/paudiog0`, les nœuds PCM ALSA et les deux
`subucom_spi_rdy` — ces derniers étant les CPU d'afficheur de jog, non des
sources de touches. Le rétroéclairage n'apparaît pas parce qu'il est ouvert puis
refermé, pas conservé.

**Les autres GPIO.** `rbp` ouvre `/dev/gpiodrv` environ vingt-cinq fois au
démarrage. Seules deux broches sont identifiées. Les autres numéros se relèvent
sans risque **depuis les traces**, pas en balayant les broches : un traceur
passif sur `lseek` donne la liste exacte, après quoi chacune peut être lue en
sécurité puisque `rbp` la lit déjà en entrée.

## 6. Ce qui reste à valider sur appareil de toute façon

Les cinq critères de `rbp-performance-ui-map.md` §« Critères de validation »
n'ont jamais été exécutés : couleurs SOURCE intactes avant et après KEY/STEMS,
KEY et STEMS stables en Performance, transitions répétées
STATUS → KEY → STEMS → BEAT FX, absence de texte Aqua/Blue/Default, et
comportement conservé des sélecteurs matériels de pads.

## Ce que le mod fait physiquement, pour mémoire

Rien de persistant. `librx3_core.so` est préchargé, les mots ARM gardés sont
écrits dans la copie en mémoire de `rbp` avant son lancement et disparaissent à
la coupure, et aucune écriture ne touche la NAND ni `imagedata.dat`. Les quatre
images privées occupent des identifiants ajoutés (`0x1600`–`0x1603`), jamais des
identifiants Pioneer existants.
