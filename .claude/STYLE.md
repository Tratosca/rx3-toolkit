# Writing style for rx3-toolkit

Project-specific rules for all user-facing text (UI strings, README, docs, release notes) and code text (comments, commits, logs). General writing principles live in the `redaction-ui-code` skill; this file holds the facts and terms that belong to this project only. When they conflict, this file wins.

## Languages and register

| Language | Register | Notes |
|---|---|---|
| English | Second person (*you*), present tense, neutral | Reference language for README, docs, commits, code |
| French | Vouvoiement, professionnel | Written natively from intent, never translated word for word |

## Glossary

| English | Français | Notes |
|---|---|---|
| XDJ-RX3 | XDJ-RX3 | Model name, never translated |
| [TODO: deck / unit] | platine | The hardware as a whole |
| USB drive | clé USB | |
| encryption key | clé de chiffrement | |
| maintenance mode | mode maintenance | Not "maintenance path" / "voie de maintenance" |
| source archive | archive source | The package published on Pioneer DJ's GPL page |
| sample | sample | A sound played from the pads (pads de samples, banque de samples). Not translated |
| sample (audio) | échantillon | The technical unit of digital audio (échantillons écrêtés) |
| stems | stems | Not translated |
| sidecar file (`.rx3stem`) | fichier sidecar (`.rx3stem`) | |
| pad | pad | |
| hot cue | hot cue | Masculine in French |
| power cycle | [TODO] | |

## Hardware labels

Reproduce labels exactly as printed on the unit, in capitals: SLIP LOOP, [TODO: other pad mode buttons used by the toolkit].

## Deck behaviour

Needed to write executable instructions. Unknown facts stay `[TODO]` in strings until filled here.

| Feature | How the user reaches it | What the user sees | Side effects |
|---|---|---|---|
| Sample page | Tap SAMPLES on the touchscreen | SAMPLES panel | Stored hot cues are not modified |
| Beat Jump ±32 | [TODO] | [TODO] | [TODO] |
| Stem control (INST, VOCAL, DRUMS; pad numbers awaiting hardware validation) | [TODO] | [TODO] | [TODO] |

## Legal text

The following statements must use identical wording in the README, the terms screen and NOTICE. Change them in all three places at once.

| Statement | FR string key | README section |
|---|---|---|
| Non-affiliation with Pioneer DJ and AlphaTheta | `terms.owner` | [TODO] |
| No warranty, MPL 2.0 | `terms.risk` | [TODO] |
| User responsibility, local law | `terms.law` | [TODO] |
| Key not distributed by the project | `terms.nothingElse` | [TODO] |

## Reference example

`samples.onDeck` (fr)

> Before: Sur la platine, appuie sur SLIP LOOP au-delà de ses propres pages : les pads sont la page suivante, et tes hot cues ne bougent pas.
>
> After: Sur la platine, touchez SAMPLES à l’écran. Chaque pad déclenche alors un sample. Les hot cues enregistrés ne sont pas modifiés.

## Checks

- Commits: Conventional Commits, enforced by commitlint.
- Prose: Vale, with the vocabulary above declared as accepted terms.
- i18n: same keys in every language, same placeholders in each pair, no `[TODO]` left at release.
## DJ-facing technical detail

Use “stem file” / “fichier de stems” in the preparation interface. Keep “sidecar” / “fichier sidecar” in technical details. This is an explicit exception to the glossary, not a change of file format. “Deck” / “unit” refers to “platine”; retain hardware labels DECK 1 / DECK 2. Write “éteignez puis rallumez la platine” for a power cycle. Never publish an unvalidated numerical stem pad mapping.
