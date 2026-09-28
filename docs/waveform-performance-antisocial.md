# Calcul des waveforms — Antisocial (MK Remix)

Mesure locale du 27 septembre 2026 sur « Ed Sheeran - Antisocial (Extended MK Remix) », durée exacte 323,7616 secondes. Format **Blue**, conforme au réglage enregistré dans `Desktop/clé/RX3_STEMS/waveform-settings.json`.

Les trois stems audibles sont voix, batterie et instrumental. Le paquet stocke voix et batterie ; l’instrumental est reconstruit depuis le morceau original. Le calcul couvre les **sept combinaisons non vides**, à 150 colonnes/seconde, soit 48 565 colonnes par combinaison. Il ne s’agit donc pas de trois waveforms indépendantes.

## Résultats

- Code actuel, Python de l’application 3.14.7 : **75,920 s**.
- Code actuel, contrôle avec le même Python du moteur 3.12.13 : **59,123 s**.
- Prototype vectorisé, Python du moteur 3.12.13 + NumPy déjà installé : **10,038 s**.
- Écriture du paquet de test et vérifications des PCM : **0,235 s** supplémentaires.

**Gain à interpréteur identique : ×5,89 (−83 %).** Comparé à l’environnement actuel de l’application : ×7,56, avec un changement d’interpréteur en plus de la vectorisation. Les trois sorties sont identiques octet pour octet.

Ces mesures couvrent `waveform.build` : décodage du MP3, reconstruction, fichiers temporaires, filtrage, réduction des pics, encodage et validation de la waveform. L’extraction initiale du paquet est hors chronométrage. Les données sont lues sur le stockage local ; ce n’est pas une mesure de transfert vers une clé USB physique. Un passage par variante, sans affirmation de moyenne ni de performance Windows.

## Où passe le temps actuel ?

| Étape | Secondes | Prototype |
|---|---:|---:|
| Reconstruction des sept combinaisons | 45,351 | 0,771 |
| Lecture PCM et restitution du gain | 14,271 | 0,289 |
| Réduction des pics | 7,469 | 0,283 |
| Processus FFmpeg, décodage inclus | 7,365 | 7,576 |
| Encodage Blue | 0,087 | 0,145 |

Les chronométrages détaillés sont inclusifs : `columns` inclut FFmpeg, les pics et l’encodage ; il ne faut pas additionner tous les compteurs du JSON.

## Pistes d’accélération, par priorité

1. **Vectoriser le traitement PCM et les pics dans le moteur existant.** Le prototype remplace les boucles Python de `mixing.reconstruct_static`, `audition.read_pcm` et `wave_dsp.peaks` par des opérations NumPy. C’est le gain démontré. NumPy est déjà présent dans le moteur de séparation, mais absent de l’environnement léger de l’application : l’intégration recommandée passe par un worker de ce moteur, sans installer une nouvelle dépendance dans l’interface. Conserver un repli actuel si le moteur est absent. Préserver l’ordre des arrondis float32, la correction de gain et la règle de silence stéréo.
2. **Réduire les fichiers intermédiaires et les passages répétés.** `waveform.py:143–168` relit l’original et les stems pour chaque combinaison ; `wave_dsp.py:187–201` écrit puis relit deux sorties float64 pour Blue. Sur ce morceau, ces seules sorties représentent environ 1,60 Go écrits puis relus. Traiter les sept combinaisons par blocs et réduire les pics au fil du filtrage éviterait une partie des E/S. Gain restant non mesuré ; conserver les états des filtres entre blocs et les frontières exactes des colonnes.
3. **Paralléliser de façon bornée le filtrage des combinaisons.** Après vectorisation, FFmpeg représente environ les trois quarts du temps. Tester deux workers, puis adapter au CPU et au stockage, plutôt que lancer sept calculs par morceau sans limite. Gain non mesuré et pas nécessairement linéaire ; surveiller contention disque, mémoire, annulation et coexistence avec la séparation.
4. **Pour 3Band, vectoriser aussi les enveloppes à fenêtre glissante.** `wave_dsp.three_band` recommence une boucle de 100 à 300 millisecondes pour chaque colonne. Le benchmark Blue ne mesure pas ce coût. Une accélération de ce chemin exige sa propre référence et une comparaison binaire ; les résultats Blue ne se généralisent pas aux autres formats.

## Livrables et intégrité

Tout est sous `local/research/waveform-antisocial-20260927/` : scripts reproductibles, JSON des timings, waveform de référence, waveform vectorisée et paquet `.rx3stem` de test. Le prototype initial est limité à ce dossier. Son intégration ultérieure est décrite ci-dessous.

- Waveforms de référence et vectorisée identiques, SHA-256 : `fb4a9a671e7270a1ddc8c006e3e55ac3619c94697305dbbc2ec6a78e640404d5`.
- Paquet de test : `Ed Sheeran - Antisocial (Extended MK Remix).rx3stem`, 114 564 750 octets, validé par `package.read`, format PWV3, sept combinaisons.
- PCM voix et batterie identiques dans le paquet de test ; aucune nouvelle séparation.
- SHA-256 du MP3 et du paquet d’origine inchangés. Aucun remplacement dans `Desktop/clé`.

L’ordre de grandeur de 1–2 minutes précédemment affiché correspond bien au code actuel sur cet exemple. Après intégration et validation multi-format du prototype, il faudra revoir cette estimation ; annoncer dès maintenant dix secondes pour tous les ordinateurs et toutes les clés serait injustifié.

## Intégration du chemin accéléré

Le chemin accéléré est désormais intégré. `wave_acceleration.py` lance
`wave_worker.py` avec le Python du moteur déjà installé. L'application ne dépend
pas directement de NumPy et n'installe rien ; le calcul existant reste disponible
si le moteur/NumPy est absent. Les erreurs survenant pendant un calcul ne sont
pas masquées par un nouveau calcul automatique.

- Reconstruction vectorisée avec correction du gain et silence stéréo identiques.
- Deux combinaisons traitées par lot, avec lecture/correction des rôles partagées.
- Deux filtrages concurrents au maximum ; pour les trois formats ensemble,
  retour à un seul si l'espace temporaire disponible ne couvre pas les deux lots.
- Pics et enveloppes à fenêtre glissante 3Band vectorisés ; grandes tables
  transférées en binaire plutôt qu’en JSON ; arrondis et encodage
  conservés. Les fichiers intermédiaires de filtrage existent toujours.
- Processus enregistrés dans le contrôle d'annulation existant, contexte transmis
  aux threads et fermeture du worker en fin de calcul ou en cas d'erreur.
- Worker autonome inclus dans la recette de packaging ; paquet distribué et
  Windows non validés lors de cette passe.

Antisocial complet : **Blue 6,529 s**, soit **×11,63** contre le code antérieur
exécuté par le même Python de l'application (75,920 s). La waveform Blue complète
est identique octet pour octet à la référence. **3Band 16,114 s**, identique octet
pour octet à la section du paquet original corrigé en gain. Fichiers d'origine
inchangés, aucune publication sur la clé.

Validation : 80 tests exécutés, 78 réussis et 2 ignorés faute de fixtures externes.
Les sept nouveaux tests vérifient notamment les sept masques avec gain, les quatre
sorties (Blue/RGB/3Band/tous formats), les limites des fenêtres 3Band, l'égalité
entre calcul parallèle et repli, la progression monotone, les erreurs worker,
l'annulation et l'absence du moteur. Un prochain travail peut supprimer les
fichiers temporaires de filtrage eux-mêmes ; il nécessitera de conserver les états des
filtres et les frontières exactes des colonnes.

## Calcul des trois formats ensemble

Antisocial complet, mêmes sept combinaisons : **37,216 s** avec le chemin final
accéléré et deux filtrages au maximum. Le premier essai en série prenait 43,544 s.
Un essai intermédiaire concurrent avec les tests prenait 35,200 s : ne pas en
faire une moyenne ni attribuer cet écart à une seule optimisation.

La section tous formats occupe **2 040 306 octets**, contre **340 531 octets** pour
Blue seul, soit **1 699 775 octets supplémentaires** (environ 1,5 % du paquet audio
de 114,6 Mo). Les sorties Blue et 3Band extraites sont identiques aux références
réelles ; la section complète est également identique entre le calcul série et
le calcul parallèle (SHA-256 `1f89e913beef729aff6982d2a3c41ed18576a30c03af8d26bbee4046644f3ea2`).

Recommandation produit : calculer les trois formats par défaut devient raisonnable
pour supprimer le choix et les recalculs lors d'un changement de réglage sur le
RX3. Le compromis mesuré est environ 31 secondes supplémentaires par morceau de
5 min 24 s par rapport à Blue seul. Mille morceaux représentent encore plusieurs
heures : ce n'est pas gratuit. Le format unique reste le comportement produit
actuel ; le benchmark tous formats n'a pas modifié ce choix ni écrit sur la clé.

## Intégration du calcul en mémoire

Le chemin intégré prépare désormais Blue, RGB et 3Band ensemble : **17,274 s**
sur Antisocial avec les sept combinaisons, worker inclus. Résultat identique
octet pour octet à la référence complète. Voir
[les essais en mémoire](waveform-in-memory-tests.md) et
[le parcours actuel](waveform-formats.md). Les mesures précédentes de cette
page restent les résultats historiques des chemins FFmpeg et à format unique.
