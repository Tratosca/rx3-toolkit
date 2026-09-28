# Paquet de stems `.rx3stem`, versions 2 et 3

Un seul fichier `RX3_STEMS/<nom du morceau>.rx3stem` contient les stems
préparés, leur description et leurs waveforms. L'export automatique et l'import
manuel du Toolkit produisent ce format. L'ancien format `RX3STM1` et ses
sidecars restent lisibles ; ils ne sont pas réécrits à la simple lecture.

## Contenu

Le package contient un index binaire et un manifeste JSON interne. Les rôles
actuellement proposés par le Toolkit sont voix ou voix + batterie. La basse
séparée reste lisible dans les anciens paquets. L'instrumental (ou les autres instruments avec plusieurs
stems) reste calculé depuis le mix original ; sa waveform est incluse.
Le package est autonome pour ses stems et ses waveforms ; le morceau original
reste nécessaire au lecteur pour le mix complet et les instruments restants.

- Chaque stem sélectionné est inclus en PCM stéréo 44,1 kHz, signé 16 bits,
  sur la grille temporelle du lecteur, avec son rôle explicite dans l'index.
- La section waveform contient les colonnes à 150 Hz de chaque rôle, y compris
  le résiduel. Elle conserve le format PWV3 ou PWV5 du gabarit quand celui-ci
  est compatible. Sans gabarit utilisable, une grille PWV5 est calculée et
  l'identité d'analyse vaut zéro : aucune analyse Rekordbox n'est inventée.
- Le manifeste indique version, rôles, durée en trames, format, métadonnées
  du morceau, SHA-256 du fichier source et paramètres de préparation fournis.
- Les entrées portent longueur, offset et CRC32. Le lecteur refuse les
  chevauchements, rôles inconnus, données tronquées, axes temporels divergents,
  champs réservés non nuls et corruptions de sections.

L'en-tête fait 64 octets, little-endian : `<8sIIIIQQ24s>` — magic `RX3PKG2\0`,
version 2 ou 3, taille d'en-tête 64, nombre d'entrées, taille d'entrée 64,
taille totale, nombre de trames et 24 octets réservés nuls.
Chaque entrée `<IIQQII32s>` décrit type, rôle, offset, longueur, CRC32,
champ réservé nul et nom ASCII complété par des zéros. Les types sont PCM=1,
waveform=2 et manifeste=3 ; les bits PCM sont voix=2, batterie=4, basse=8.
Les sections sont contiguës : PCM dans l'ordre des rôles, waveform, manifeste.
Les formats internes PCM `RX3STM1` et waveform `RX3WAV1` restent versionnés.
La limite du package est 512 MiB, incluse dans le budget partagé des deux decks.

## Publication et lecture

Le Toolkit prépare et vérifie le package complet avant une seule publication
atomique avec relecture. Une waveform impossible à générer fait échouer cette
préparation ; l'ancien package reste présent. Les anciens `.rx3drums`,
`.rx3bass` et `.rx3wave` sont retirés seulement après publication réussie.
Le cache et la préécoute lisent des sections bornées du package.

Le worker du core charge le package en mémoire, vérifie ses sections et publie
l'ensemble des rôles d'un seul coup. Un package invalide est refusé entièrement.
Le service `waveform` du framework (API 4) copie les amplitudes sous la même
barrière de lecteurs que le PCM ; Stemwave ne conserve aucun pointeur vers
l'état privé du fournisseur.

## Stemwave et niveau de preuve

Activer `RX3_STEMWAVE=1` avec le fournisseur Stems. Les waveforms détaillées
utilisent alors les amplitudes embarquées pour les sélections partielles.
Le mix complet retrouve le rendu natif. RX3WAV3 analyse chaque combinaison
audio séparément ; les enveloppes ne sont pas additionnées. L'aperçu Blue conserve encore son filtre natif historique.
Un axe incompatible conserve la waveform native et produit un diagnostic.
Les anciens fichiers sans waveform embarquée conservent désormais le rendu natif.

Validé sur firmware 1.19 dans QEMU le 26 septembre 2026 : « DO IT », package
vocal + waveforms vocal/instrumental, activation instrumentale et vocale,
lecture, pause, restauration du mix complet. Les traces indiquent explicitement
`stems package: PCM and embedded waveform verified` puis
`stem waveform: rendered embedded package amplitudes`.
Session : `rx3-emulator/outputs/rx3-machine/20260926-104838`.
Les packages à un, deux et trois stems PCM sont également testés côté hôte et
par le lecteur C. Les trois modes d'affichage et la fidélité sur RX3 physique
restent à valider ; l'émulation ne les certifie pas.

## Inspection et migration d'une copie de travail

Depuis `rx3-toolbox` :

```sh
python3 -m app.stems.package inspect '/chemin/morceau.rx3stem'
python3 -m app.stems.package migrate --drive '/chemin/copie-cle' \
  --track '/chemin/copie-cle/Contents/artiste/album/morceau.aiff'
```

La migration conserve les PCM existants et les décrit comme provenant du
format v1, sans certifier rétrospectivement leur séparation. Elle reconstruit
les waveforms et vérifie que la durée du morceau correspond aux stems.
Pour le test courant, seule la copie `rx3-emulator/build/media/stemwave-usb`
a été modifiée ; `~/Desktop/clé` est resté intact.

## Waveform combinations (RX3WAV3)

New packages retain RX3PKG2 framing, with an RX3WAV3 version-3 waveform
member. The 128-byte header, 64-byte directory entries, and six-byte column
stride are unchanged. Masks 1..3 represent INST/VOCAL, or 1..7 with DRUMS;
bits are INST=1, VOCAL=2, DRUMS=4. Silence is implicit. Every curve is analyzed
from the exact reconstructed PCM combination, with its own PCM hash.

Each 150-Hz cell stores BLUE/PWV3 (one byte), RGB/PWV5 (big-endian word),
and PWV7 (three bytes, low/mid/high). PWV7 replaces the approximate stacked
0..31 band heights of RX3WAV2. The new version prevents confusing those
representations. Readers retain RX3WAV1/2 support; old v2 BLUE/RGB remain
usable, while detailed 3Band falls back until its waveform is regenerated.
Verified cached PCM is reused without repeating separation.

The PWV7 analysis uses the same quantized stereo-to-mono projection as RGB,
Butterworth low-pass 300 Hz, band-pass 250–1200 Hz and band-pass 3000–9000 Hz.
Integer millisecond peaks feed envelopes with 300/200/100 ms look-back and
0.99/0.98/0.97 release factors. Gains come from 1200 whole-track windows,
are peak-limited and quantized to hundredths; the high band has a cosine
transfer. There is no new storage cost, no intermediate-volume combinations.

Core waveform service formats: 0 BLUE, 1 RGB, 2 legacy band heights, 3 PWV7.
PWV7 envelopes overlap: the renderer converts their boundaries to successive
coloured layers with the native mixed palette, rather than stacking their
absolute heights. Firmware display modes remain BLUE=0, RGB=1, 3Band=2.
Full mix continues to use the native waveform. Overview handling is unchanged.

An optional hash-pinned real-export regression uses
`RX3_WAVE_3BAND_MANIFEST` (operator-local JSON with source/dat/ext/2ex paths
and hashes). It compares the entire calculated PWV7 byte stream with the
export, not an image or a few samples. This does not certify every codec or
hardware rendering.

## Waveforms facultatives et calcul différé

La case « Calculer les waveforms des stems » est cochée par défaut et son choix
est mémorisé dans l’interface. Elle s’applique à la séparation et à l’import.
Décochée, elle permet de publier les PCM sans lancer l’analyse des waveforms.
Elle ne supprime pas les waveforms d’un paquet réutilisé. Le choix ne fait pas
partie de l’identité du cache de séparation.

Un paquet audio seul conserve le magic `RX3PKG2\0`, mais utilise **la version 3
de l’en-tête de paquet** et du manifeste. Son entrée waveform existe dans
l’index avec une longueur et un CRC nuls ; elle ne contient aucun octet.
Le manifeste porte `waveform: null` et conserve le SHA-256 du morceau source.
Les sections PCM et manifeste restent obligatoires et non vides. Une longueur
waveform nulle est interdite en version 2. Les anciens lecteurs refusent la
version 3 ; il faut donc installer le module Stems mis à jour pour ces paquets.
Les paquets avec waveforms restent en version 2, avec une section RX3WAV3.
Ces deux numéros de version concernent des structures distinctes.

Le lecteur signale l’absence volontaire par `0xfffffffe` au service waveform.
Stemwave conserve alors l’affichage original avant toute écriture, aperçu compris.
Le diagnostic d’axe incompatible reste `0xffffffff`.

Dans Stems, **Préparer les stems** traite la playlist sélectionnée : préparation
en trois stems, conversion des anciens formats, ajout de la batterie manquante
et complétion des waveforms. Les paquets complets valides sont conservés. Les API
de maintenance des waveforms restent disponibles pour compatibilité.
Elles vérifient le paquet complet et l’identité du morceau
original, réutilisent les PCM et préservent leur provenance. Le nouveau paquet
est vérifié avant remplacement atomique ; une erreur ou une annulation avant
publication conserve l’ancien. Le manifeste externe est actualisé après le
paquet ; une erreur d’écriture à cette étape laisse l’audio utilisable mais peut
nécessiter de réactualiser ce manifeste par un nouveau recalcul.

Les limites et estimations de taille tiennent compte du choix. Ajouter des
waveforms peut rendre trop volumineux un paquet audio seul proche de la limite :
le calcul différé contrôle cette limite avant l’analyse et conserve alors le paquet.

## Gain-preserving PCM (format 3)

New preparations bypass audio-separator's output peak normalization and write
floating-point intermediate WAVs. Input normalization, where the architecture
uses it, is still undone before encoding. PCM stays stereo s16 at 44.1 kHz.
The RX3STM1 header's format field is 3; bytes 32–35 contain a little-endian
float32 playback scale in [1, 64], with bytes 36–63 zero. Stored samples are
divided by this scale to fit s16; the reader restores it before mixing.
NaN, infinity, out-of-range scales and nonzero remaining bytes are rejected.
Format 2 keeps its zero-filled reserved field and unit gain.

The preview, waveform analysis, standalone loader and package loader use the
same scale. RAM and file size remain unchanged. An older mod rejects format 3,
so reinstall the mod before using newly prepared stems on the RX3. Existing
normalized files cannot recover their true scale from their header; regenerate
the affected role from the original track. The separator cache identity changed.

Validation: `test_stems_gain` exercises >0 dBFS preservation, cancellation,
preview transport, every waveform mask, native mixing and malformed gains.

### Hauteurs RGB hors plage

Le calcul PWV5 plafonne les hauteurs à 31 avant encodage. Un pic situé dans une
milliseconde exclue du normaliseur peut sinon produire une hauteur supérieure à
31 ; un masque binaire ferait retomber cette hauteur à zéro ou à une faible
valeur. Le plafonnement conserve un pic plein. Il corrige aussi un débordement
présent dans une colonne de la référence native Ladies’ Night : ce cas constitue
une différence volontaire avec l’export Pioneer. Les waveforms RGB déjà
préparées peuvent être recalculées depuis l’écran Stems, sans nouvelle séparation.
