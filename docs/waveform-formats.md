# Formats de waveforms des stems

Le Toolkit prépare ensemble **Blue, RGB et 3Band**, pour les sept
combinaisons audibles du mode trois stems. Aucun choix de format ni confirmation My Settings n'est
nécessaire. Changer l'affichage du RX3 ne nécessite donc pas de recalcul pour les
nouveaux paquets.

## Calcul et compatibilité

Le moteur installé utilise NumPy et SciPy pour décoder la source une seule fois,
filtrer des blocs de deux secondes en mémoire et produire les trois formats.
Il n'écrit pas de PCM ou de filtrage intermédiaire. L'estimation mémoire est
limitée à 512 Mio ; au-delà, ou sans ce moteur, le chemin précédent reste utilisé.
Cette estimation n'est pas une mesure de mémoire disponible sur l'ordinateur.

Les anciens paquets restent lisibles. **Préparer les stems** complète les formats
manquants dans la playlist sélectionnée, dans le même job que la migration et
l’ajout de batterie. Les paquets trois stems déjà complets et valides sont
conservés. Il n’y a plus de fenêtre ni de bouton de complétion séparé.

La complétion vérifie l'identité de la source, copie les PCM existants sans
séparation ni réencodage et remplace le paquet de façon atomique. L'annulation
ne publie pas le morceau en cours ; les morceaux déjà terminés restent valides.
Les anciens profils de format et empreintes My Settings ne conditionnent plus
ce parcours. Les API explicites de format restent disponibles pour compatibilité.

## Lecture et contrat binaire

Le conteneur RX3PKG2 est conservé. La préparation complète utilise RX3WAV3,
format MULTI, à 150 colonnes/seconde : un octet Blue, deux RGB, trois 3Band.
RX3WAV4 à format unique reste lisible. Le numéro 4 désigne cette variante de
stockage ; utiliser la version 3 pour les trois formats n'est pas une régression.

Le mod actuel fournit le format choisi sur le RX3. Pour un ancien paquet où ce
format manque, il conserve la waveform native du morceau d'origine, qui ne
reflète alors pas les stems coupés. Le son des stems reste utilisable.
La prévisualisation utilise directement les colonnes stockées.

## Mesures et validation

Sur Antisocial (5 min 24 s), le chemin intégré a produit les trois formats et
sept combinaisons en **17,274 s**, lancement du worker compris, lors d'un essai
local également accompagné de tests automatisés. L'ancien chemin complet
mesurait 37,216 s. Le prototype chaud mesurait 13,430 s. Ces mesures excluent la
séparation et la publication du paquet sur USB ; ce ne sont pas des garanties.

Les 2 040 306 octets de la section sont identiques à la référence complète :
`1f89e913beef729aff6982d2a3c41ed18576a30c03af8d26bbee4046644f3ea2`.
Voir `docs/waveform-in-memory-tests.md` pour les signaux et le corpus testés.
Windows, le paquet distribué et une platine physique ne sont pas validés par ces
essais locaux.
