# Migration des stems de la release v0.5.2

Release vérifiée sur GitHub le 27 septembre 2026 : [v0.5.2](https://github.com/Tratosca/rx3-toolkit/releases/tag/v0.5.2). Le tag annoté local et distant correspond à `2a49406c3d75113ada74ed0190dfcf1618275baa`, commit `73bf2cedda4d1bab4666ae7f43efce59da265255`.

Le générateur publié appelle `write_sidecar(..., sample_format="s16")` ([source de la release](https://github.com/Tratosca/rx3-toolkit/blob/v0.5.2/tools/rx3_stems/job.py)). Le conteneur `RX3STM1` contient un en-tête de 64 octets suivi de PCM16 stéréo à 44,1 kHz. Le nouveau package peut embarquer ce fichier sans modifier un seul octet audio.

## Parcours dans Stems

1. Sélectionnez la clé USB et ouvrez sa bibliothèque ou votre export XML.
2. Sélectionnez la playlist à préparer.
3. Cliquez sur **Préparer les stems**. Le mode est fixé à **voix + batterie + instrumental**, avec le preset rapide (`quick`, Demucs à un shift) pour les nouveaux calculs. Les anciens réglages de qualité et de nombre de stems ne modifient plus ce comportement.
4. Le même job vérifie chaque titre : il conserve les paquets complets valides, ajoute la batterie aux voix existantes, convertit les anciens fichiers et complète les waveforms Blue/RGB/3Band. Aucun changement de preset ne déclenche à lui seul une nouvelle séparation d’un paquet valide.
5. Annulez ou relancez ce même bouton pour interrompre ou reprendre. Les titres terminés sont conservés. Seuls les titres de la playlist sélectionnée sont traités.

Il n’existe plus de fenêtre de migration ni de bouton distinct de complétion des waveforms. Les anciens appels `stems_migrate` délèguent au même job de préparation avec leur sélection de titres ; ils ne proposent plus de conversion en deux stems.

## Ce qui change dans les fichiers

**Titre possédant déjà la voix et la batterie :** copie exacte des anciens stems dans le package actuel et calcul CPU des waveforms pour les combinaisons de stems. Aucun séparateur ni encodeur audio n’est lancé pour le stem existant. Le décodage du morceau original sert uniquement à l’analyse des waveforms et à la vérification de la longueur.

**Batterie manquante :** le moteur de séparation existant produit la batterie manquante à partir du morceau original. Seul ce nouveau stem est encodé et aligné. Le stem vocal historique reste inchangé. Un modèle peut calculer plusieurs sorties en interne ; ses nouveaux résultats vocaux ne remplacent jamais l’ancien stem.

Les fichiers historiques sont copiés et vérifiés dans `RX3_STEMS/backup-v0.5.2` avant tout remplacement. Une sauvegarde différente n’est jamais écrasée. Le nouveau package est vérifié puis publié par remplacement atomique. Les anciens fichiers complémentaires sont conservés. Une erreur de calcul ou une annulation avant publication laisse l’ancien stem utilisable. Une interruption après publication conserve le package terminé et sa sauvegarde.

Le remux ne corrige pas un mauvais alignement historique et ne prétend pas certifier sa provenance. Les longueurs incompatibles sont refusées ; aucun ajustement silencieux ne masque la différence. Les anciens fichiers flottants créés hors du parcours standard v0.5.2 ne sont pas convertis implicitement en PCM16.

Les paquets récents en deux stems suivent également ce parcours : leur voix est copiée sans réencodage, et la provenance du nouveau calcul de batterie est enregistrée séparément. Les paquets récents sont associés à leur source par le SHA-256 embarqué, même si le manifeste externe est absent. Une source modifiée déclenche une nouvelle préparation ; un paquet corrompu est signalé sans écrasement.

Les packages migrés sont destinés au mod actuel. Aucune migration n’a été exécutée sur une clé réelle pendant le développement.

## Prévisualisation

Avec les waveforms préparées, les sons arrivent par blocs binaires de deux secondes dans un contexte audio à faible latence ; la lecture est disponible dès le premier bloc. Quand il fonctionne déjà, play et seek démarrent sans attente de promesse ; les commutations changent directement les gains. Une pause annule aussi un démarrage encore en attente de réveil du contexte.

Un worker local analyse les combinaisons de PCM signé par blocs bornés. Il conserve les filtres entre blocs et calcule les enveloppes par sélection ; les enveloppes des stems ne sont pas simplement additionnées. Les représentations 3Band, Blue et RGB couvrent tout le morceau et suivent les stems actifs. Le style est conservé localement. Aucun calcul d’analyse ni appel Python n’est nécessaire lors d’une commutation. Cette représentation de préécoute ne revendique pas une identité pixel à pixel avec les ressources graphiques de la platine.

## Vérifications

Les tests couvrent la copie bit à bit, la sauvegarde, la reprise, le refus d’une sauvegarde différente, l’ajout de batterie sans remplacement vocal, les différences de longueur, l’annulation avant publication et la création réelle des waveforms sur audio synthétique. Les tests JavaScript couvrent le chemin audio synchrone, les commutations sans arrêt ni appel Python, le seek local, les réponses périmées, l’annulation pendant le réveil audio, l’annulation de signaux identiques et la continuité des filtres entre blocs. La latence acoustique du périphérique de sortie et la lecture des packages sur RX3 réel restent à mesurer.

## Chargement progressif de la prévisualisation

Les paquets avec waveforms préparées utilisent un serveur HTTP strictement local
(`127.0.0.1`, port éphémère, jeton aléatoire par session). Aucun fichier arbitraire
n’est exposé : seules les tranches PCM de deux secondes de la session sont accessibles.
Le fichier original est décodé en arrière-plan par FFmpeg. Le transfert transporte
l’original en float32 et les stems en PCM16, sans encodage Base64 de l’audio ni
boucles de conversion par échantillon en Python. Le gain de chaque stem est
restitué dans le navigateur, avec le même arrondi float32 et la même gestion
du silence que le lecteur.

Les rôles sont programmés sur la même horloge Web Audio avec plusieurs blocs
d’avance. Une commutation agit sur les gains persistants sans redémarrer les
sources. Un déplacement déjà chargé est local ; une zone encore absente est
demandée en priorité, avec une attente possible le temps de sa réception. Une
sous-alimentation suspend l’avancement au dernier bloc disponible. La fermeture
ou un changement de morceau annule les requêtes et libère le décodeur et le serveur.
Les fichiers sans waveforms préparées gardent le parcours d’analyse antérieur.

Mesures locales du 27 septembre 2026 sur Antisocial (323,76 s, voix + batterie) :
- ancien parcours Python : 8,58 s pour produire tous les blocs Base64, hors
  transport pywebview et construction des buffers dans le navigateur ;
- nouveau parcours Python : métadonnées en 25 ms, premier bloc en 78 ms ;
- WKWebView réel : premier bloc prêt en 239 ms, métadonnées comprises, avec
  88 200 trames sur 14 277 888 chargées. Le test est muet et ne mesure pas la
  latence de sortie audio ni les performances sur Windows.

Tests : `tests/stems_audio.cjs`, `tests/stems_preview.cjs`,
`tests/test_stems_preview.py`. Ils couvrent le démarrage anticipé, la
synchronisation des blocs, les gains, le seek prioritaire, la pause, les réponses
obsolètes, l’annulation, l’intégrité des sources et les restrictions du serveur.
