# Cartographie UI Performance de `rbp` 1.19

Cette note sépare les faits extraits du binaire, les observations sur le RX3 et
la stratégie de patch. Les adresses sont celles du `rbp` XDJ-RX3 1.19, MD5
`cc3ee1a81489d6363dc800d01102ea5f`.

## Objets statiques confirmés

| Groupe | Objet | Adresse | Image | Contenu natif |
|---|---|---:|---:|---|
| STATUS / BEAT FX | `...IMG_BEATFX_6` | `0x531804` | `0x1598` | BEAT FX sélectionné |
| STATUS / BEAT FX | `...IMG_STATUS_5` | `0x53181C` | `0x1599` | STATUS sélectionné |
| STATUS / BEAT FX | parent `..._4` | `0x531834` | — | lien combiné |
| ZOOM / GRID | `...IMG_GRID_3` | `0x531840` | `0x15C9` | GRID sélectionné |
| ZOOM / GRID | `...IMG_ZOOM_2` | `0x531858` | `0x15CA` | ZOOM sélectionné |
| ZOOM / GRID | parent `..._1` | `0x531870` | — | lien combiné |
| SOURCE / couleur | `...BGCOLOR_BTN_10` | `0x52BC58` | `0x0D7E` | bouton de couleur |

Les bitmaps `0x1598/0x1599` mesurent 180×50. Les bitmaps `0x15C9/0x15CA`
mesurent 152×32. Ils appartiennent bien à `PLAY_MODE_TOP`; leur capture est
donc un ancrage valable pour la rangée KEY/STEMS.

## Collision démontrée

Les IDs `0x0D7C` à `0x0D84` (3452 à 3460), précédemment décrits comme des
« swatches sans usage », sont les ressources actives du sélecteur de couleur
SOURCE. Leur extraction depuis `imagedata.dat` affiche littéralement :

- Aqua ;
- Blue ;
- Default ;
- Green ;
- Orange ;
- Pink.

Le patch les remplaçait en RAM par les bitmaps KEY/STEMS et les réutilisait
comme IDs de dessin. Cette collision explique simultanément les fuites dans
SOURCE et les retours intermittents de « Aqua / Blue / Default ». Les surfaces
DirectFB étant décodées et cachées, un remplacement tardif des pixels ne peut
pas rendre ce détournement déterministe.

## Machines d’état natives

`setBeatFxSelected()` écrit un booléen à `buf_PlayGroup + 464`.
`Ui_CycleTask()` détecte sa modification, puis `UiNotifyDispInfoUpdate()` fait
passer l'affichage Performance dans l’état `7` lorsque BEAT FX est sélectionné.
STATUS et BEAT FX sont donc une seule machine d’état native.

ZOOM/GRID est indépendant : `UiKey_ZoomGrid()` commute
`CmnInfo.GridAdjustModeFlg`; `ZoomGridIndicator()` expose ensuite le mode et la
direction à `PlayInfoDataUpdate()`.

KEY/STEMS doit rester un état d’extension séparé, tout en utilisant les deux
glyphes ZOOM/GRID uniquement comme points d’ancrage géométriques et de
rafraîchissement.

## Table d’images native

- `NS_GetImageCount()` retourne `0x15CD` (5581 entrées).
- Chaque entrée de `g_ImageTableAddr` mesure 44 octets.
- `NS_GetImageInfoByID()` rejette tout ID supérieur ou égal à `0x15CD`.
- `NS_PALRender_DrawImage()` résout systématiquement l’ID avec cette fonction.

Le premier essai d’interception de `NS_GetImageInfoByID()` a été rejeté : cette
fonction est exécutée continuellement par le renderer et son patch à chaud de
8 octets introduit une fenêtre non atomique. Le candidat segfaultait après
l’activation du resolver et l’autoexec restaurait correctement `rbp`.

La méthode retenue ne hooke aucune fonction chaude :

1. un mot ARM gardé, écrit dans `rbp` avant son lancement, remplace
   `movw r3,#0x15CC` par `movw r3,#0x1603` ;
2. le core alloue une table secondaire de `0x1604 × 44` octets ;
3. les 5581 records officiels y sont copiés et leurs offsets sont relocalisés
   pour continuer à viser le bloc de pixels Pioneer original ;
4. quatre records RGB565 privés occupent `0x1600`–`0x1603` ;
5. le pointeur global de table est publié atomiquement après préparation
   complète.

Le bloc et les IDs Pioneer d’origine restent inchangés. Le modèle de relocation
vérifie les 5581 pointeurs officiels ainsi que les quatre pointeurs privés.

## Critères de validation sur le RX3

1. SOURCE affiche ses couleurs d’origine avant et après l’ouverture de KEY ou
   STEMS.
2. KEY et STEMS restent visibles en mode Performance sans clignotement.
3. Les transitions répétées STATUS → KEY → STEMS → BEAT FX reconstruisent les
   deux moitiés du panneau à chaque fois.
4. Aucun texte Aqua, Blue ou Default n’apparaît en mode Performance.
5. Les commandes KEY/STEMS et les sélecteurs matériels de pads conservent leur
   comportement accepté.
