# Accent-insensitive Search (`search-latin`)

Firmware: **XDJ-RX3 1.19**

This module makes the RX3 SEARCH comparison accent-insensitive for the common
Latin characters used by the hardware-validated V14 patch.

Examples:

- `NINO` finds `NIÑO`
- `CANCION` finds `CANCIÓN`
- `MUSICA` finds `MÚSICA`
- `PINGUINO` finds `PINGÜINO`

It changes only the SEARCH normalization routine. Displayed artist/title
metadata is not rewritten.

## Reverse-engineering notes

- Target executable: `/root/pdj/rbp`
- Stock firmware 1.19 SHA-1:
  `cf309238491e73cdbdc1f08a09f7a3177e079068`
- Normalization routine: `shape()` at VA `0x001644FC`
- File patch block offset: `1426684`
- Block size: `316` bytes
- Original block SHA-1:
  `b73c213bc86cab17abfe67e77224a57379f4f532`
- V14 block SHA-1:
  `fb4dea578d9dc450cc14d001cf1f5ecf6cbc7f35`
- Full V14 `rbp` SHA-1:
  `919f384cc1b6aa790649ba4bd7a5bf82e8fa8c4a`
- Guarded 32-bit words changed by this module: `78`

The original V14 was tested on real XDJ-RX3 hardware: `rbp` restarted
successfully, remained alive after the 8-second validation window, and SEARCH
matched the intended folded forms.

## Fold table

```text
A À Á Â Ã Ä Å Æ  a à á â ã ä å æ  -> A
C Ç              c ç                -> C
E È É Ê Ë        e è é ê ë          -> E
I Ì Í Î Ï        i ì í î ï          -> I
N Ñ              n ñ                -> N
O Ò Ó Ô Õ Ö Ø    o ò ó ô õ ö ø      -> O
U Ù Ú Û Ü        u ù ú û ü          -> U
Y Ý Ÿ            y ý ÿ               -> Y
```

The V14 machine-code block also contains its original handling for the
remaining Latin-1 entries; this module reproduces the **exact V14 bytes** rather
than reimplementing the routine from a new C compiler build.

## Safety / scope

This contribution contains only the guarded words needed by the toolkit.
It does **not** include an encryption key, firmware image, manufacturer binary,
or `autoexec.bin`.
