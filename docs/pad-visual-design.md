# Performance controls — visual refinement

Mode: Operate. Scope: the shared on-device renderer for STEMS, KEY and Samples.
Authority: RX3 1.19 native screen, shipped glyph atlases, the working pad gestures,
and the user's Rekordbox role colours. This is a refinement of that interface.

## Common treatment

- Keep the 39 px native touch band, layout solver, labels and atlas typeface.
- Neutral one-pixel frames; colour identifies a stem or selected state.
- Full-volume stem: a full semantic-colour face, readable name and a vivid inset status rail.
- Partial volume: the same frame, bright label, numeric percentage (number alone in narrow four-role cells), a six-pixel
  track and a six-pixel handle. The handle remains within the control at 0/100.
- A pressed control highlights its frame. Off removes the coloured face and status rail; its
  label stays readable so the control remains discoverable.
- KEY uses the same frames, caption contrast and status rail. Samples uses the
  same track/handle and retains its VOL readout/reset button.
- Inactive/status labels, loading blink, empty/error copy and all gestures keep
  their existing meanings. No decorative animation or new mode switch.

## Theme and semantic colour

Framework neutral tokens live next to the painter in `rx3_pad_widgets.h`.
Dark frame/track: `#41474d` / `#30363c`. Light: `#8c949c` / `#a5adb5`.
Handle: white in dark mode, `#202830` in light mode. Neutral backgrounds come from the active glyph atlas. Active/semantic cells use the unattenuated RGB565 semantic colour in both themes. The caption uses
white or dark keyed glyphs according to the face brightness; the alternate
ink is mapped into the selected atlas slot. Sliders use the same contrasting
ink colour for their fill and handle.

Role accents remain supplied by Stems: drums blue, vocal green, instrumental
red, optional bass yellow. Colours are not lifted, darkened or mixed with a neutral. They are not reused as loading or error colours.

## Verification

Real ARM-emulator captures cover STEMS toggles, partial levels and off, KEY
and shifted KEY, and Samples, in dark/light themes. The unit suite checks the
unchanged touch/layout contracts and the ARM build checks firmware imports.
Emulator evidence does not establish physical-device behaviour.

## Camelot colours on KEY

Only the current key fills its whole central cell with its Camelot colour.
The decrement/increment actions use neutral faces and the fixed labels −1/+1,
without target-key text or chevrons. Their small colour rails still preview the
adjacent key, and disappear at the absolute ±12 limits. Limits still clamp the
pitch; action labels remain stable. Unknown keys stay neutral.
Source palette: https://mixedinkey.com/camelot-wheel/ (RGB565).

## Harmonic feedback — Operate

The right-hand slot communicates a relationship or offers one action. It stays
in the same position while both track keys are known, preserving the stepper's
hit targets through changes in compatibility.

- **COMPATIBLE**: neutral, readable text on the band's own background. No
  button frame, filled action face, status rail, hover or pressed treatment.
  The original keys retain their full Camelot colours. A different hue on each
  deck is normal: compatibility does not mean the keys are identical.
- **KEY SYNC ±n**: a neutral button with a two-pixel Camelot contour identifying
  the proposed key. Its signed shift says what a press will do. The contour
  grows to three pixels while held and darkens on the light theme for contrast.
- **PAS DE SYNC**: passive text when neither compatibility nor a correction
  within the selected mode/range is available. This makes absence of an action
  explicit without moving the manual controls.
- **IDENTIQUE**: passive confirmation in Identical mode when keys already match.
- If either key is unknown, the comparison slot is omitted.

The core's STATUS widget consumes the complete gesture without firing, including
state changes during a hold. A gesture beginning on a status cannot turn into
a sync on release. This is a real non-actionable element, not a disabled-looking
button with an active hit target. Status ink is white on dark and dark on light,
using the shipped glyph atlases. Colour remains reserved for key identity and
action; no green success code competes with the vocal stem convention.
