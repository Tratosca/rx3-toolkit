# Key Match amélioré (BROWSE)

Module sélectionnable dans la catégorie Harmonic mixing du Toolkit. Sa carte Key Match amélioré contient ses règles et son exemple BROWSE. Il peut être utilisé seul. Key Sync dépend de Key Match et de Key Shift pour proposer une transposition selon les règles sélectionnées. Il conserve les correspondances vertes existantes. Les suggestions sélectionnées utilisent une note jaune pour Energy Boost +2, orange pour +7 et rouge pour +4 expérimental, dans BROWSE et dans la colonne Tonalité supplémentaire. Aucun changement de tonalité n'est appliqué.

## Paramètres du Toolkit

Les cases sont indépendantes, enregistrées localement et exportées dans `modules/key-match/rules.txt`. Le bit 1 de l'ancienne option Diagonales est ignoré, sans changer les autres choix enregistrés. Les valeurs de 0 à 15 sont acceptées en entrée et normalisées avec le masque 14, jamais exécutées.

| Bit | Relation depuis le morceau de référence | Exemple | Couleur | Par défaut |
| --- | --- | --- | --- | --- |
| 2 | Energy Boost +2, même lettre | 8A vers 10A | Jaune | Non |
| 4 | Energy Boost +7, même lettre | 8A vers 3A | Orange | Non |
| 8 | Saut +4 expérimental, même lettre | 8A vers 12A | Rouge | Non |

Les nombres indiquent des déplacements sur la roue Camelot, pas des demi-tons de transposition. Le vert déjà fourni par le RX3 reste prioritaire, quelles que soient ses règles Traffic Light. Le module n'ajoute aucun signalement pour les diagonales. BROWSE et KEY SYNC partagent le jeu de correspondances natives observé et la référence MASTER. Sans référence locale exploitable, aucune suggestion supplémentaire n'est calculée.

Les Energy Boost sont des suggestions de transitions courtes, pas une garantie pour superposer deux mélodies. Le saut +4 peut produire une dissonance. Le Toolkit indique la couleur de chaque option et affiche ces réserves dans un avertissement.

Le lien « Guide Mixed In Key ↗ » dans les paramètres ouvre directement
[Use advanced harmonic mixing techniques](https://mixedinkey.com/book/use-advanced-harmonic-mixing-techniques/).

## Architecture et limites

Le module possède les règles, ses réglages et les hooks de composition du voyant.
Le core partage le chargement des lignes et de leurs métadonnées entre Key Match
et Browse Columns, via `services->browse`. Il fournit également les variantes
d’images RGB565 et la gestion des hooks.
Les trois couleurs reprennent le masque et la géométrie des cinq variantes du voyant natif. Chaque couleur dispose aussi d'un marqueur pour la colonne Tonalité. Le service d'images partagé réserve 24 emplacements, dont 19 utilisés par Key Match.
Les tonalités inconnues ne produisent pas de suggestion.

Les points d’entrée sont protégés par les signatures de `rbp` 1.19,
SHA-256 `60bcbd8876116bf09f0d8f747f95d7c7d3081ebd39d6fe14d56005a22f7f3b09`.
Le chargement sur une autre version dépend de ces signatures ; une déclaration
dans le manifeste ne constitue pas une validation matérielle.

## Suite prévue

- Suggestions avec transposition dans la plage autorisée par KEY SYNC, via un
  contrat de framework, sans dépendance directe entre les modules.
- Case de filtrage supplémentaire dans la vue filtre native.
- Validation sur RX3 physique et sur les autres chemins de navigation.

## Validation du 26 septembre 2026 (ancienne variante orange)

Les captures ci-dessous précèdent les trois couleurs et le retrait des diagonales. Elles ne valident pas ces changements.

- Compilation ARM du core et du module, avec `-Wall -Wextra -Werror`.
- 75 tests hôte : règles dirigées sur 24 × 24 tonalités et 16 configurations,
  export des réglages, cases et lien du Toolkit, préservation des catégories
  natives, bornes des messages, chargement/nettoyage partiel des hooks,
  variantes RGB565 et antialiasing ; suites framework et runtime existantes.
- Émulateur natif `rbp` 1.19, copie de la clé USB, référence 1A, masque 15 :
  3A et 5A orange ; 1A, 2A et 12A verts ; 4A et 9A sans voyant ajouté.
  Orange inspecté sur fonds de lignes alternés et sur la sélection bleue.
- Captures et reproduction : dépôt voisin `rx3-emulator`, répertoire
  `outputs/browse-key-match-pass/` (`launch.py`, `input.txt`, captures,
  `unit-tests.log`). Ces résultats ne constituent pas une validation RX3 physique.
- Changement de référence de 1A vers 3A vérifié dans Browse : 3A, 2A et
  4A verts, 5A orange, 1A et 12A sans voyant ajouté (`master-changed.png`).
