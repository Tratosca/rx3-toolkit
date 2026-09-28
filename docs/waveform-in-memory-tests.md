# Waveforms en mémoire : résultats des essais

Essais du 27 septembre 2026, sur le moteur local Python 3.12.13 avec NumPy 2.5.2
et SciPy 1.18.0 déjà installés. Aucun changement du chemin de production pendant
cette passe : le prototype et ses scripts sont dans
`local/research/waveform-memory-20260927/`.

## Résultat sur Antisocial

« Ed Sheeran - Antisocial (Extended MK Remix) », 323,7616 secondes, voix,
batterie et instrumental, **sept combinaisons et trois formats** :

| Variante | Temps mesuré |
|---|---:|
| Chemin intégré précédent, filtres FFmpeg et fichiers intermédiaires | 37,216 s |
| Filtres SciPy en mémoire, encodage de référence | 17,820 s |
| Filtres et encodage vectorisés, source décodée dans un fichier | 13,780 s |
| Décodage en flux, sept combinaisons alimentées par les mêmes blocs | **13,430 s** |

Le dernier essai inclut décodage, restitution des gains, reconstruction des
combinaisons, filtrage, extraction des pics, encodage Blue/RGB/3Band, empreintes
PCM et écriture de la section waveform. Il n'inclut pas le lancement à froid de
Python/SciPy, la vérification initiale du paquet ou la publication USB. Un passage
par variante, pas une moyenne ni une garantie de débit sur un autre ordinateur.

**Gain par rapport au calcul des trois formats actuel : ×2,77, soit −64 %.**
L'objectif exploratoire de moins de 15 secondes est atteint sur ce morceau.

La section entière de 2 040 306 octets est identique octet par octet à la
référence. SHA-256 :
`1f89e913beef729aff6982d2a3c41ed18576a30c03af8d26bbee4046644f3ea2`.
Les sept empreintes des PCM reconstruits sont identiques. Aucun écart Blue, RGB
ou 3Band. Le MP3 et le paquet d'origine restent inchangés.

## Comment le prototype fonctionne

FFmpeg ne fait plus que décoder le MP3 une fois, vers un pipe. Des blocs de deux
secondes alimentent les sept combinaisons ; les PCM des rôles sont lus directement
dans le paquet. Les gains sont appliqués une fois par bloc avant les combinaisons.
Les règles de float32 et de silence stéréo restent identiques.

Chaque combinaison conserve ses états de filtres SciPy `lfilter` entre les blocs.
Les pics sont réduits immédiatement en cellules de 150 Hz pour Blue et de 1 kHz
pour RGB/3Band. L'encodage Blue/RGB est vectorisé ; les normalisations et fenêtres
3Band gardent leur ordre d'opérations. Le traitement conserve des accumulateurs
de pics jusqu'à la normalisation finale, sans garder le PCM complet.

La variante en flux n'écrit **aucun fichier PCM ou de filtrage temporaire**.
Elle écrit uniquement la section waveform finale et le rapport de test.
Pic RSS du processus : **363 757 568 octets**, environ 364 Mo décimaux, contre
480–483 Mo pour les premières variantes. Cette valeur inclut Python/SciPy et les
pages mappées des rôles. Les blocs audio sont bornés ; les tableaux de pics, eux,
restent proportionnels à la durée. Il ne s'agit pas d'une borne universelle pour
tous les morceaux.

## Vérifications

- Huit cas synthétiques : silence, impulsions aux frontières de blocs, bruit avec
  dépassement de pleine échelle, plusieurs fréquences ; à 44,1 et 48 kHz.
  Blue, RGB et 3Band comparés au calcul actuel : zéro octet différent.
- Découpage en blocs d'une ou deux secondes : sorties identiques sur ces huit cas,
  y compris la dernière cellule incomplète.
- Antisocial complet : 7 × 48 565 colonnes, trois formats, identiques à la référence.
- Corpus réel : **huit exports et 401 250 colonnes 3Band**, comparaison exacte aux
  fichiers Pioneer, test réussi en 17,959 s. Les empreintes des sources et analyses
  sont vérifiées par le test. Ce contrôle de corpus affirme l'identité 3Band ; il
  ne prétend pas revalider tout le corpus RGB/Blue.
- Décodage en flux identique au décodage existant ; sources plus longues et plus
  courtes que l'axe des stems refusées.
- Annulation pendant le décodage : exception propagée et processus enfant arrêté
  puis récolté. L'intégration complète à la file de tâches de l'application reste
  à valider lors du remplacement du worker.

SciPy utilise une réalisation de filtre différente de celle de FFmpeg : ces tests
valident les **octets finaux** sur les signaux et corpus cités, pas une identité
universelle des échantillons float64 filtrés. Windows et le paquet distribué
n'ont pas été testés dans cette passe.

## Décision proposée

Les résultats justifient l'intégration du calcul en mémoire et des trois formats
par défaut. Le choix de format et les alertes My Settings pourront alors être
supprimés. Pour les anciens paquets à format unique, compléter les waveforms sans
refaire la séparation. Garder le repli existant lorsque le moteur approprié est
absent, vérifier les limites mémoire avant allocation et préserver le mécanisme
de publication atomique. Cette passe teste la solution ; elle n'active pas encore
ces changements produit.

## Reproduction locale

Depuis la racine, avec le Python du moteur installé :

```sh
ENGINE_PYTHON='/Users/fbrille/Library/Application Support/RX3 Stem Studio/runtime/bin/python'
PYTHONDONTWRITEBYTECODE=1 "$ENGINE_PYTHON" local/research/waveform-memory-20260927/test_filters.py
PYTHONDONTWRITEBYTECODE=1 "$ENGINE_PYTHON" local/research/waveform-memory-20260927/test_stream.py
PYTHONDONTWRITEBYTECODE=1 "$ENGINE_PYTHON" local/research/waveform-memory-20260927/test_corpus.py
PYTHONDONTWRITEBYTECODE=1 "$ENGINE_PYTHON" local/research/waveform-memory-20260927/benchmark_stream.py
```

Preuves : `filter-tests.json`, `stream-tests.json`, `corpus.json`, `streamed.json`
et `streamed.rx3wave`, dans le même dossier local. Les scripts référencent le
corpus utilisateur local ; aucune donnée audio tierce n'est ajoutée au code public.

## Intégration effectuée

Le chemin de production utilise désormais `wave_memory.py`, chargé par le worker
optionnel du moteur installé. Le décodage FFmpeg hérite du groupe de processus
annulable ; les sorties temporaires sont nettoyées en cas d'erreur. Le calcul
précédent reste disponible si SciPy est absent ou si l'estimation dépasse 512 Mio.
Les trois formats sont préparés par défaut ; le choix de format et les alertes
My Settings ont disparu du parcours utilisateur. Les anciens fichiers peuvent
être complétés sans modification des PCM.

Essai réel du code intégré : **17,274 s** sur Antisocial, trois formats,
sept combinaisons, section complète strictement identique au SHA-256 ci-dessus.
Le lancement du worker est inclus ; des tests tournaient simultanément. Aucune
écriture sur la clé d'origine. Rapport :
`local/research/waveform-antisocial-20260927/production-memory.json`.

Validation de l'intégration : 108 tests Python réussis (accélération, formats,
paquets, migration, reprise, modes, gains, cache et localisation), trois scénarios
JavaScript réussis (écran Stems, preview et audio), et neuf contrôles natifs
pywebview réussis. La fenêtre de complétion est vérifiée en FR/EN, thèmes
clair/sombre à 880 pixels, sans débordement ni libellé non résolu. Les essais
incluent l'annulation du worker et le repli sans moteur accéléré.
