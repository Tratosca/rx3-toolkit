# KEY SYNC — évolution harmonique

Demande de François : terminer d’abord les fonds colorés des contrôles, puis
étendre KEY SYNC avec un mode harmonique configurable dans le Toolkit.

- Conserver le mode actuel « Identique ».
- Ajouter « Harmonique » : même tonalité, voisins ±1 Camelot de même mode,
  relative majeure/mineure (même numéro, autre lettre).
- Chercher la plus petite transposition en demi-tons dans la limite ±x.
- Si déjà compatible, afficher « Compatible » sans correction.
- Conserver x = 1 par défaut et les transpositions effectives des deux decks.
- Ne pas inclure les transitions expressives/energy boost dans ce mode.

Cas de référence accepté : face à 8A, 9A est déjà compatible. 10A abaissé
d’un demi-ton donne 3A, incompatible ; abaissé de deux donne 8A. Avec x = 1,
aucune correction ; avec x = 2, KEY SYNC propose −2.

Implémenté : les deux modes sont disponibles dans le Toolkit, avec persistance
locale et intégration dans le module généré. Le mode Identique reste le défaut.
L’état KEY MATCH est informatif et ne modifie pas la transposition. En cas
d’égalité de distance, une cible identique est préférée, puis le sens positif.
Les tests vérifient le cas de référence et la minimalité sur les 24 tonalités,
les transpositions des deux decks et les limites absolues de ±12 demi-tons.
