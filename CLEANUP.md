<!-- SPDX-License-Identifier: MPL-2.0 -->
# Nettoyage, septembre 2026

Ce que la passe de rangement a retiré de l'arbre, avec la preuve pour chaque fichier. Les fichiers suivis par git sont en `.attic/`, arborescence conservée, en attente du commit qui les supprimera. Les fichiers que git n'a jamais suivis sont dans `~/Desktop/rx3-toolbox-attic/`, hors du dépôt, et n'entreront jamais dans l'historique. Le tag `snapshot/before-cleanup` contient de toute façon l'arbre complet d'avant la passe.

Preuve de non-usage, appliquée à chaque entrée : aucune référence statique dans l'arbre (grep sur le nom et sur le chemin), absent du Makefile, de la CI et de `app/toolkit.spec`, hors d'atteinte des mécanismes dynamiques du dépôt (glob des `manifest.json` par `app/rx3_runtime/build.py` et par le spec, `*_feature.h` et `*_panel.h`, découverte `test_*.py` de `unittest`, wildcard `mod/modules/*/1.19/*.h` du Makefile), et aucune mention dans un `.md` autre que le CHANGELOG.

## Mort

| Fichier | Preuve |
| --- | --- |
| `.attic/tools/rx3_runtime/patch_r38_ui.py` | Expérimentation sur un build d'avant le premier commit. Aucune référence, aucun `__main__` appelé, hors des globs. |
| `.attic/tools/rx3_patcher/` (4 fichiers) | Contreparties hors ligne des patches d'octets de deux modules. Seul lecteur : `tests/test_beat_jump_patches.py` et une classe de `tests/test_module_consistency.py`, supprimés. Les tables qui s'exécutent sont dans `module.sh`. Décision de l'utilisateur. |
| `.attic/tools/rx3_payload/` (2 fichiers) | Assembleur du payload d'un émulateur qui a quitté le dépôt (CHANGELOG, « The emulator moved to its own repository »). Atteint par `make payload` seulement, que la CI n'exécutait jamais. Décision de l'utilisateur. |
| `.attic/mod/modules/core/1.19/rx3_core_emulator_{keys,breadcrumbs,harness}.h` | Inclus uniquement sous `RX3_EMULATOR_BUILD`, que seul `make payload-hook` définissait. Les 18 blocs gardés ont été retirés de `rx3_core_hook.c` ; `librx3_core.so` a le même SHA-256 avant et après. |
| `.attic/app/{main,mod_generator,stems_preparation,theme}.py` | La fenêtre Tkinter, remplacée par celle de `app/shell.py`, qui fait maintenant les cinq écrans et que PyInstaller gèle. Aucun test ne les importe (vérifié : `tests/test_mod_generator.py` et `tests/test_stems.py` ne parlent qu'aux moteurs). Sortis du spec, du Makefile et de la CI dans le même lot. `theme.py` importe `tkinter` au niveau du module : tant que quelque chose l'importait, Tk entrait dans le paquet livré. |
| `.attic/scripts/smoke_desktop_app.py` | Remplacé par une ligne de `.github/workflows/ci.yml` ; aucun autre appelant. |
| `.attic/tools/rx3_stems/make_sidecar.py` | Ligne de commande vers l'encodeur que l'application pilote déjà. Cité une fois dans REFERENCES, jamais exécuté par rien. Décision de l'utilisateur. |
| `.attic/tools/rx3_assets/__init__.py` | Fichier vide d'un paquet dont le seul module a rejoint `mod/modules/core/1.19/build_labels.py`. |
| `.attic/tests/test_beat_jump_patches.py`, `test_decoder_sleep_patch.py`, `test_package_release.py`, `test_payload_geometry.py` | Tests hors du critère retenu (un deck qui se comporte mal, une clé ou une piste abîmée, un mod qui charge sans rien faire, un engagement de LEGAL.md). Le premier et le dernier n'avaient plus de sujet après le départ du patcher et du payload. |
| `.attic/mod/modules/core/1.19/assets/labels/` (87 bitmaps, 1,4 Mo) | Étiquettes entières, une image par légende, jamais déclarées dans `manifest.json` ni chargées par le core. La voie que le CHANGELOG désignait est prise, mais par un atlas d'une image par caractère : une légende entière ne sait pas écrire `*3A +2`, qui vaut vingt-quatre tonalités par vingt-cinq transpositions, ni un niveau. `build_labels.py` reste et écrit l'atlas. |
| `.attic/mod/modules/{core,keyshift,stems}/1.19/test_regressions.py` | Gardes textuelles sur le C (85 assertions) : elles cassaient à chaque édition sans qu'un deck se comporte différemment. Retirées avec la boucle du Makefile et le gabarit de `make new-module`. |
| Quarantaine hors dépôt : 14 tests et 5 gardes jamais suivis (`test_bridge`, `test_logo_container`, `test_macos_bundle`, `test_rekordbox_export`, `test_render_probe`, `test_samples_audio`, `test_samples_config`, `test_service_*`, `test_session_log`, `test_stemwave_runtime`, et les gardes des cinq modules portés) | Même critère. Ils testaient la fenêtre en cours et ses services, qui ne livrent pas. |
| Quarantaine hors dépôt : trois scripts d'expérimentation d'empaquetage à la racine (`spike_webview.py`, `spike_webview.spec`, `spike.html`) | Leur docstring dit « Delete this once it has answered ». La réponse est dans `scripts/check_macos_bundle.py`. |
| Quarantaine hors dépôt : trois fichiers d'une autre enquête (deux scripts à la racine, un journal dans `local/`) | Sans rapport avec le projet ; nommés seulement dans `local/CLEANUP-local.md`. |
| Quarantaine hors dépôt : `app.asar` à la racine, `tools/rx3_firmware/iso_extract.py` | Une archive tierce ignorée par git, et un lecteur ISO référencé par rien. |
| Supprimés directement : `aes256.key` à la racine (copie identique, `cmp`, de la clé rangée hors de l'arbre suivi), `mod/modules/beatjump/` (un `__pycache__` d'un fichier disparu), `tests/__pycache__` (quatre `.pyc` sans source) | Ignorés par git, sans référence, régénérables ou dupliqués. |
| Branches locales : `feat/emulator-and-font` (3 commits, archivée sous le tag `archive/feat-emulator-and-font` avant suppression), `chore/lower-the-contribution-overhead`, `chore/scope-legal-and-docs`, `fix/module-index-crlf`, `fix/intel-mac-separation-runtime` (toutes fusionnées dans `main`) | Les branches distantes ne sont pas touchées. |

Tests conservés et pourquoi, fichier par fichier :

| Fichier | Tests | Ce qui casserait sans eux |
| --- | --- | --- |
| `tests/test_hook_symbols.py` | 3 | le hook qui ne charge plus en silence (`bcmp`), l'incident du CHANGELOG |
| `tests/test_firmware_image.py` | 5 | une image que le deck ignore ; le codec retiré qui revient |
| `tests/test_mod_generator.py` | 7 | `autoexec.bin` tronqué sur une clé arrachée, ordre de chargement, cycles, index CRLF, la construction elle-même |
| `tests/test_module_api.py` | 8 | hooks enregistrés et exécutés, deux modules sur une même adresse, rollback complet, réinsertion sans redémarrage, se mettre de côté sans arrêter la session, processus mort qui termine l'attente |
| `tests/test_module_consistency.py` | 3 | en-tête `.rx3stem` déclaré en Python et lu en C, opt-out sans échec |
| `tests/test_rbp_identity.py` | 2 | un `rbp` déjà patché reconnu à la réinsertion, un binaire étranger encore refusé |
| `tests/test_stems_directory.py` | 2 | une clé qui revient sous un autre nom de périphérique ne relance pas `rbp` |
| `tests/test_stems.py` | 6 | nom de stem identique à celui de l'export, troncature du deck reproduite, collisions refusées, stem existant conservé, gain rétabli, padding remis |
| `tests/test_names.py`, `tests/test_docs_hygiene.py` | 7 | engagements de LEGAL.md |
| `tests/test_media_guard.py` | 8 | une deuxième clé montée n'arrête pas le lecteur, un zombie n'est pas un lecteur vivant |
| `tests/test_runtime_transitions.py` | 10 | chargeur de stems qui refuse un en-tête faux, trampoline conservé après restauration ratée, watcher terminé avant nettoyage |

## Douteux, gardés

- `app/shell.py`, `app/bridge.py`, `app/web/`, `app/rx3_service/`, `app/rx3_logo/`, `app/rx3_samples/` : atteints par un seul self-test de la CI, ne livrent pas, mais c'est le chantier « Polished interface » de la feuille de route.
- `mod/modules/core/1.19/assets/*-selected.rgb565` : chargés à l'exécution par `module.sh` du core ; le CHANGELOG dit qu'ils partiront quand la question de palette sera tranchée.

`[TODO: à vérifier]` : le dépôt de l'émulateur, s'il vit encore ailleurs, consommait `make payload` ; il n'a plus de source ici.

## Vivant

Tout le reste de l'arbre suivi : atteint par le Makefile, la CI, le spec, l'application, ou un glob du moteur de build.
