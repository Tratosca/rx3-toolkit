<!-- SPDX-License-Identifier: MPL-2.0 -->
# Codes de touches du RX3 1.19

La table complète `ui::KeyInput::KeyCode`, extraite **statiquement** de `rbp`
(MD5 `cc3ee1a81489d6363dc800d01102ea5f`). Aucun appui n'a été nécessaire.

## D'où elle vient

`ui::KeyInput::keyCodeAsText()` (`0x0037cde4`, 2 884 octets) est un arbre de
comparaisons sur le `ushort` en `+8` de l'objet — le même champ que lit déjà
`rx3_stems_feature.h` — qui renvoie un nom pour chaque code. Décompiler la
fonction, relever les couples `(code, pointeur)` puis résoudre les pointeurs
dans `.rodata` donne la table entière.

Le décompilateur replie quelques branches en comparaisons de plage plutôt qu'en
égalités ; six codes ont donc été relus dans leur garde
(`Shift`, `SlipLoop`, `BeatJump`, `Pad1`, `Pad3`, `Pad8`) au lieu d'être
devinés.

**Contrôle indépendant.** L'extraction produit `Pad7 = 0x411d` et
`Pad8 = 0x411e`, exactement les deux valeurs que `rx3_stems_feature.h` portait
déjà en dur, établies auparavant par une tout autre voie.

## Ce que cela remplace

Cartographier la façade en capturant des trames SPI exige un appui par touche,
un opérateur devant l'appareil, et une fenêtre de synchronisation qui se rate
facilement — deux tentatives ont d'ailleurs échoué faute de synchronisation.
Cette table donne le même résultat en une lecture, hors ligne, sans appareil.

La capture matérielle garde un usage : elle seule dit **quel bit de quelle
trame** porte une touche. Mais pour *injecter* une touche il n'en faut pas :
`ui::PlayerInnards::onKey_*` prend un `IKeyInput` dont la disposition est
connue — code sur 16 bits en `+8`, canal en `+0x0a`, appui ou relâchement dans
le quartet bas de `+0x0b`.

## Les quatre sélecteurs de mode de pad

Les touches qui choisissent ce que font les huit pads, dans l'ordre du binaire :

| Code | Nom | Gestionnaire |
|---|---|---|
| `0x4113` | HotCue | `onKey_HotCue` `0x003030ec` |
| `0x4114` | AutoBeatLoop | `onKey_AutoBeatLoop` `0x003031cc` |
| `0x4115` | SlipLoop | `onKey_SlipBeatLoop` `0x00303238` |
| `0x4116` | BeatJump | `onKey_BeatJumpLoopMove` `0x00303294` |

Les huit pads suivent immédiatement : `0x4117` à `0x411e` pour Pad1 à Pad8.

## La table

### `0x02xx` — Navigation / browse / shortcuts / track filter / timer

| Code | Nom | Code | Nom |
|---|---|---|---|
| `0x0201` | Source | `0x0236` | TF_Color_Orange |
| `0x0202` | Browse | `0x0237` | TF_Color_Yellow |
| `0x0203` | TagList | `0x0238` | TF_Color_Green |
| `0x0204` | PlayList | `0x0239` | TF_Color_Aqua |
| `0x0205` | Search | `0x023a` | TF_Color_Blue |
| `0x0206` | Menu | `0x023b` | TF_Color_Pureple |
| `0x0207` | Media PC | `0x023d` | TF_MytagCategory1 |
| `0x0208` | Media RB | `0x023e` | TF_MytagCategory2 |
| `0x0209` | Media USB1 | `0x023f` | TF_MytagCategory3 |
| `0x020a` | Media USB2 | `0x0240` | TF_MytagCategory4 |
| `0x020b` | Info | `0x0241` | TF_Criteria1 |
| `0x0210` | Shortcut | `0x0242` | TF_Criteria2 |
| `0x0213` | DeckInfoSelect | `0x0243` | TF_Criteria3 |
| `0x0216` | Keyboard | `0x0244` | TF_Criteria4 |
| `0x0217` | TouchPanelOn | `0x0245` | TF_MyTagItem1_1 |
| `0x021a` | SC_LoadLock | `0x0246` | TF_MyTagItem1_2 |
| `0x021b` | SC_DeckSelect | `0x0248` | TF_MyTagItem1_4 |
| `0x021c` | SC_HotCueAutoLoad | `0x0249` | TF_MyTagItem1_5 |
| `0x021d` | SC_QuantizeValue | `0x024a` | TF_MyTagItem1_6 |
| `0x0222` | SC_MySettingLoad | `0x0273` | TIM_Preset1 |
| `0x0223` | SC_WaveformColor | `0x0274` | TIM_Preset2 |
| `0x0224` | SC_EqIso | `0x0275` | TIM_Preset3 |
| `0x0226` | SC_MixerMode | `0x0276` | TIM_Preset4 |
| `0x0227` | SC_ChannelFaderCurve | `0x0277` | TIM_Preset5 |
| `0x0228` | TF_ModePropetry | `0x0278` | TIM_Preset6 |
| `0x0229` | TF_ModeMyTag | `0x0279` | TIM_History1 |
| `0x022a` | TF_MyTagInfo | `0x027b` | TIM_History3 |
| `0x022b` | TF_Reset | `0x027c` | TIM_History4 |
| `0x022c` | TF_Valid_Bpm | `0x027d` | TIM_History5 |
| `0x022d` | TF_Valid_Key | `0x027e` | TIM_History6 |
| `0x022e` | TF_Valid_Rating | `0x027f` | TIM_Tenkey |
| `0x022f` | TF_Valid_Color | `0x0280` | TIM_Plus5Min |
| `0x0230` | TF_Edit_Bpm | `0x0281` | TIM_Minus5Min |
| `0x0231` | TF_Edit_BpmRange | `0x0282` | TIM_Plus1Min |
| `0x0232` | TF_Edit_Key | `0x0283` | TIM_Minus1Min |
| `0x0233` | TF_Edit_Rating | `0x0284` | TIM_StartPause |
| `0x0234` | TF_Color_Pink | `0x0285` | TIM_Clr |
| `0x0235` | TF_Color_Red |  |  |

### `0x04xx` — Recording and effects

| Code | Nom | Code | Nom |
|---|---|---|---|
| `0x0401` | USB REC | `0x0493` | EffectQuantize |
| `0x0402` | TrackMark |  |  |

### `0x08xx` — Microphone

| Code | Nom | Code | Nom |
|---|---|---|---|
| `0x0814` | MicSW | `0x0816` | MicEqLowKnob |
| `0x0815` | MicEqHiKnob |  |  |

### `0x41xx` — Deck: transport, pads, jog

| Code | Nom | Code | Nom |
|---|---|---|---|
| `0x4101` | Play/Pause | `0x4116` | BeatJump |
| `0x4102` | CUE | `0x4117` | Pad1 |
| `0x4103` | Shift | `0x4118` | Pad2 |
| `0x4104` | Vinyl | `0x4119` | Pad3 |
| `0x4107` | TempoRange | `0x411a` | Pad4 |
| `0x4108` | MasterTempo | `0x411b` | Pad5 |
| `0x4109` | TempoSlider | `0x411c` | Pad6 |
| `0x410a` | TimeMode/ACue | `0x411d` | Pad7 |
| `0x410b` | DeckQuantize | `0x411e` | Pad8 |
| `0x410f` | Reverse | `0x411f` | SearchFwd |
| `0x4111` | Master | `0x4120` | SearchRev |
| `0x4112` | Sync | `0x4121` | VinylSpeedAdjust |
| `0x4113` | HotCue | `0x4124` | CueDelete |
| `0x4114` | AutoBeatLoop | `0x4126` | NeedleSearch |
| `0x4115` | SlipLoop |  |  |

### `0x42xx` — Deck: browse and selection

| Code | Nom | Code | Nom |
|---|---|---|---|
| `0x420c` | RotarySelector | `0x4212` | DeckSelect |
| `0x420d` | Back | `0x4214` | TrackFwd |
| `0x420e` | TagTrack | `0x4215` | TrackRev |
| `0x420f` | TrackFilter |  |  |

### `0x43xx` — Jog and load

| Code | Nom | Code | Nom |
|---|---|---|---|
| `0x4305` | JogWheel | `0x4322` | CallNext |
| `0x4306` | JogTouch | `0x4323` | CallPrev |
| `0x4311` | Load |  |  |

### `0x44xx` — Mixer and beat effects

| Code | Nom | Code | Nom |
|---|---|---|---|
| `0x4403` | MasterLvKnob | `0x448b` | BeatEffectSW |
| `0x4404` | BoothLvKnob | `0x448c` | BfxChSW |
| `0x4406` | HeadphoneLvKnob | `0x448d` | EffectOnOff |
| `0x4407` | MasterCue | `0x448e` | TimeKnob |
| `0x4408` | LinkCue | `0x4490` | BeatPrev |
| `0x4409` | AuxGainSw | `0x4491` | BeatNext |
| `0x440a` | AuxLvKnob | `0x4492` | Tap |

### `0x60xx` — Crossfader

| Code | Nom | Code | Nom |
|---|---|---|---|
| `0x6017` | CrossFader | `0x6018` | FaderCurveSW |

### `0x80xx` — Power and touch calibration

| Code | Nom | Code | Nom |
|---|---|---|---|
| `0x8001` | Power | `0x8002` | UsbStop |

Total : 146 codes.


## Les identifiants de LED

Même méthode, autre table : un tableau de `char *` à `0x004de050`, indexé par
identifiant de LED, les trous comblés par `Unknown Led`.

L'indice brut du tableau vaut l'énumération **moins un** : l'entrée brute 23 est
`Pad7`, et `rx3_stems_feature.h` utilise depuis toujours l'identifiant 24 pour
la pastille 7, valeur établie par une voie indépendante. Les deux concordent une
fois le décalage appliqué, ce qui valide le tableau autant que le mod.

| Id | LED | Id | LED | Id | LED |
|---:|---|---:|---|---:|---|
| 1 | Play/Pause | 14 | HotCue | 24 | Pad7 |
| 2 | Cue | 15 | AutoBeatLoop | 25 | Pad8 |
| 3 | Vinyl | 16 | SlipLoop | 26 | Jog |
| 4 | Sync | 17 | BeatJump | 27 | JogCenter |
| 5 | Master | 18 | **Pad1** | 28 | CueMarker |
| 6 | MasterTempo | 19 | Pad2 | 29 | Load |
| 7 | LoopIn | 20 | Pad3 | 30 | LoadIllumi |
| 8 | LoopOut | 21 | Pad4 | 41 | CfxFilter |
| 9 | Reloop | 22 | Pad5 | 47 | Tap |
| 10 | Reverse | 23 | Pad6 | 48 | EffectOnOff |
| 11 | Slip | | | 50 | HeadphoneCue |
| 12 | Quantize | | | 51 | MasterCue |

Les quatre sélecteurs de mode ont donc **une touche et une LED** portant le même
nom mais des numéros différents : `HotCue` est la touche `0x4113` et la LED 14.
C'est ce qui fait qu'appuyer sur un sélecteur change une couleur — l'entrée et
la sortie sont deux chemins distincts.
