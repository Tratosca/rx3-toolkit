<!-- SPDX-License-Identifier: MPL-2.0 -->
# Audit du dépôt, septembre 2026

Rapport de reprise en main, écrit en français pour son destinataire. Le reste du dépôt est en anglais. Les chemins cités sont ceux de l'arbre après la passe de rangement ; les anciens chemins sont donnés entre parenthèses quand ils aident à retrouver un historique.

## Ce que fait le projet

Le lecteur Pioneer XDJ-RX3 lit, sur chaque clé USB insérée, un fichier `autoexec.bin` chiffré avec une clé AES qu'il détient, et exécute le script qu'il contient en root. `app/rx3_runtime/build.py` assemble cette image : un orchestrateur shell (`mod/autoexec.sh`), un contrat de modules (`mod/lib/module-api.sh`), les empreintes acceptées du binaire `rbp` (`mod/1.19/compatibility.sh`) et un dossier par module choisi, dans l'ordre résolu depuis les manifestes. Sur le deck, l'orchestrateur vérifie l'identité de `rbp`, applique des patches d'octets en mémoire, précharge `librx3_core.so` (compilé depuis `mod/modules/core/1.19/rx3_core_hook.c` et les en-têtes des modules), relance `rbp` et remet l'état stock si quelque chose échoue. Le hook intercepte le chargement des pistes, l'audio, les pads et le dessin de l'écran pour les fonctions stems et key shift, et pour cinq modules portés en septembre depuis un build de référence (logo, samples, search-latin, stemwave, theme-white), dont aucun n'a encore tourné sur matériel.

Côté ordinateur, `app/main.py` est une fenêtre Tkinter à deux onglets : construction de la clé (`app/mod_generator.py`) et préparation des stems (`app/stems_preparation.py`, qui pilote `app/rx3_stems` : lecture Rekordbox, provisionnement d'un runtime de séparation, encodage des fichiers `.rx3stem`). Une seconde fenêtre (`app/shell.py`, pywebview, `app/bridge.py`, `app/web/`, les services de `app/rx3_service/`) est en cours : elle appelle 2 de ses 16 opérations, ne sait ni construire une clé ni lancer une séparation, et n'est pas celle que PyInstaller gèle.

Le README dit maintenant cela. Avant cette passe, il listait 7 modules là où l'application en propose 12, et il demandait aux utilisateurs Linux d'installer WebKit pour une application qui embarque encore Tkinter ; CONTRIBUTING parlait d'une seule application Tkinter.

## Ce qui posait problème

### Cassé

- Pillow (`app/rx3_logo/container.py`, `app/rx3_service/logo.py`, `mod/modules/core/1.19/build_labels.py`) : importé, jamais déclaré. Dix-huit tests en erreur et l'écran Logo de la nouvelle fenêtre inutilisable. Réglé : déclaré dans `requirements-release.txt`.
- `mod/modules/logging/1.19/module.sh` : le message affiché sur le deck disait que rien ne tenait la clé ouverte, alors que `mod/autoexec.sh` garde `rbp_stdout.txt` ouvert tant que le lecteur joue. C'était la direction rassurante d'une phrase fausse, celle qui coûte un dossier sur une clé FAT. Réglé : l'avertissement est remis.
- `mod/modules/theme-white/1.19/manifest.json` et `mod/modules/core/1.19/manifest.json` : `build_files` incomplet. L'application gelée n'embarque que ce qui y est déclaré, donc une compilation depuis les sources dans l'application aurait échoué sur un en-tête absent ; la CI le cachait en fournissant toujours le hook précompilé. Réglé.
- `mod/modules/beatjump-32bars/1.19/manifest.json` disait « bars » là où le module saute des beats, un facteur quatre dans le nom que l'application affiche. Réglé.
- `mod/modules/logging/1.19/manifest.json`, `mod/modules/telnet/1.19/manifest.json` : un espace en tête du nom, rendu tel quel. Réglé.
- `.github/workflows/ci.yml` exécute `app/shell.py --self-test`, fichier non suivi. Tout commit du workflow sans ce fichier rend la CI rouge. Consigne pour la phase de commits : les deux vont ensemble.
- Une copie de la clé AES à la racine du dépôt, identique à celle rangée hors de l'arbre suivi, jamais entrée dans l'historique (vérifié sur toutes les refs). Réglé : la copie de la racine est supprimée. Aucune rotation nécessaire.
- Trois scripts non suivis à la racine et un journal dans `local/`, appartenant à une autre enquête : un balayage HTTP d'identifiants d'un service tiers, sans rapport avec ce projet, et incompatible avec la position légale sur laquelle repose le portage des modules. Rien ne les référençait. Réglé : sortis du dépôt vers le dossier de quarantaine, à supprimer par vous. Leurs noms sont dans la note privée `local/CLEANUP-local.md`, pas ici.

### Ce qui ralentissait toute évolution

- La suite de tests : 213 tests et 162 assertions textuelles dans huit gardes de modules, plus de 3 000 lignes, dont 150 tests pour une fenêtre qui ne livre pas. Toute édition de `rx3_core_hook.c` cassait une garde sans qu'un deck se comporte différemment. Réglé selon le critère que le CHANGELOG avait déjà posé : 61 tests dans 12 fichiers, zéro garde, moins de dix secondes. Détail dans CLEANUP.md.
- Deux racines d'import (`tests/test_module_consistency.py` insérait `tools/` dans `sys.path`) : deux objets module pour un même fichier, un monkeypatch sur le mauvais ne fait rien. Réglé : une seule racine, `app.`.
- Le code de production en trois endroits (`apps/rx3-toolbox/`, `tools/` avec dix paquets dont quatre sans consommateur, `scripts/`), un module chargé par chemin. Réglé : tout le côté ordinateur est sous `app/`, importé comme `app.x` ; `tools/` et `apps/` n'existent plus ; le générateur d'étiquettes vit à côté des assets qu'il dessine.
- Dix-huit blocs `#if defined(RX3_EMULATOR_BUILD)` dans le hook et trois en-têtes (695 lignes) pour un émulateur qui a quitté le dépôt, avec un assembleur de payload que la CI n'exécutait jamais. Réglé : retirés, avec la preuve que `librx3_core.so` est identique à l'octet près avant et après (même SHA-256).
- `rx3_core_hook.c` nomme à la main chaque en-tête de module qu'il compile, pendant que le Makefile suggère une découverte par glob. Un nouveau module ne compile ses en-têtes qu'une fois le `.c` édité. Pas de refonte : une ligne dans CLAUDE.md, et `make new-module` imprime l'étape.
- Cinq noms par module liés par convention seule (`id`, dossier, `runtime_directory`, namespace shell, préfixe C), et les variables `RX3_*` tapées à la main dans `module.sh` et dans le C. Une ligne dans CLAUDE.md, la liste dans REFERENCES.
- `app/toolkit.spec` gèle `main.py` avec `excludes=["ssl", ...]`, que pywebview rend impossible (`scripts/check_macos_bundle.py` le dit). La nouvelle fenêtre ne pourra pas être gelée telle quelle. Reste : un changement d'empaquetage ne se vérifie que sur les quatre runners de la CI.
- CI sur Python 3.12, poste sur 3.14. Reste, consigné dans CLAUDE.md.

### Cosmétique

- Trois mots pour des choses qui en avaient déjà un : « Stem Studio » pour une application disparue, « sidecar » pour le fichier stem (130 occurrences, 27 fichiers, jusque dans les identifiants C et un message de log du hook), « bench » pour l'émulateur. Réglé : `stems_preparation`, `stem` partout, et le mot « bench » est parti avec le payload.
- « toolbox » contre « toolkit ». Réglé par `app/` : le mot « toolbox » ne désigne plus rien dans l'arbre.
- `.gitignore` ignorait `/.venv*/` mais pas `venv/`, et `*.iso` deux fois. Réglé.
- Dossiers `__pycache__` orphelins de fichiers disparus. Réglé.
- Documentation : `CONTRIBUTING.md` (une seule application Tkinter, table des chemins, règle du patcher), `REFERENCES.md` (table des cibles make sans `new-module` et avec `payload`, onglets nommés d'après une ancienne version, exemples d'outils partis, variables d'environnement incomplètes), `README.md` (7 modules sur 12, WebKit), `docs/README.md` (titre différent du document), `THIRD_PARTY_NOTICES.md` (sans pywebview ni Pillow). Réglé.
- `scripts/smoke_desktop_app.py` (21 lignes) lançait l'exécutable gelé avec `--self-test`. Réglé : une ligne du workflow.

### Hors git, dans le dossier du projet

`local/` (1,0 Go), `outputs/` (197 Mo), `artifacts/` (360 Ko) : rien dans le code ne les lit. Environ 740 Mo de résultats d'émulateur régénérables, de copies de firmware dupliquées, de builds d'avant le premier commit et d'artefacts de recherche déjà repris dans le CHANGELOG ont été déplacés vers `~/Desktop/rx3-toolbox-attic/`, arborescence conservée, sans rien supprimer ; les notes de recherche ont été fusionnées en trois documents. Le détail, avec les chemins complets, est dans `local/CLEANUP-local.md` (ignoré par git, parce que ces chemins nomment l'auteur du build de référence, dont l'attribution est différée).

## Ce qui a été fait, dans l'ordre

Aucun commit n'a été fait pendant cette passe, par décision de l'utilisateur ; chaque lot a été vérifié sur l'arbre de travail avec `make hook test preflight`, les deux self-tests, et pour le lot 4 un empaquetage PyInstaller local sur macOS suivi du self-test de l'exécutable gelé. Un tag `snapshot/before-cleanup`, posé sans commit sur aucune branche, contient l'arbre complet d'avant la passe (282 fichiers) et rend n'importe quel fichier avec `git checkout snapshot/before-cleanup -- <chemin>`.

1. Branche `chore/audit-and-cleanup`, tag-instantané, amorce de CLAUDE.md.
2. Tests réduits à ce qui protège (61), gardes retirées, Makefile et `make new-module` sans gardes, Pillow déclaré.
3. Racine nettoyée, branches locales fusionnées supprimées, `feat/emulator-and-font` archivée sous un tag puis supprimée, matériel de laboratoire trié.
4. Corrections du paquet « cassé ».
5. Un seul `app/`, orphelins en `.attic/`, variante émulateur retirée à hash identique.
6. Un mot par concept : stems preparation, stem.
7. Documentation réalignée, CLAUDE.md, règle `mod/**`, hook `preflight` avant commit.

Reste à faire, à la phase de commits : le déplacement vers `.attic/` entre dans le premier commit qui touche ces fichiers, puis `git rm -r .attic/` dans un commit isolé, après `make hook test preflight`.
