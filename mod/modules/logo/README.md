<!-- SPDX-License-Identifier: MPL-2.0 -->
# 🖼️ Your own logo on the screen

Put your artwork where the player normally shows its own wordmark, in the middle of the performance screen.

Off by default. Nothing is written to the player: the artwork lives on the stick and is loaded into memory when the deck starts.

## What you need on the stick

One converted image, in a `logo` folder inside the mod. The toolbox converts a PNG, JPEG or WebP for you and writes the file at the size the screen expects.

You can supply a second image for the light display mode. If you only give one, the deck shows it in both modes.

## Getting it right

Give the converter the largest clean version of your artwork you have. It scales down well and up badly, like anything else.

Artwork with a transparent background works best: the transparent parts let the player's own background show through, so a logo of any shape sits properly instead of arriving in a box.

Very dark artwork disappears against the screen behind it. The toolbox says so before you write the stick rather than after you plug it in.

## If nothing changes on the deck

The player reads the artwork once, when it starts. Replacing the file on a stick that is already plugged in changes nothing until it restarts, and the mod asks for that restart on its own.

If the screen still shows the stock wordmark, the artwork was refused. The reason is in the session log on the stick, in plain words.

Logo can start with Core alone. The loader checks the native position and image ID before centering custom artwork, and restores the position on teardown without overwriting a later change by another owner. A rejected artwork or placement check prevents the selected runtime from reporting ready. This startup and placement correction has not yet run on hardware.
