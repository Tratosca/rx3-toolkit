/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_STEMWAVE_DECL_H
#define RX3_STEMWAVE_DECL_H

#define WAVEFORM_STATE_BASE   ((unsigned long)0x03275930)
#define WAVEFORM_STATE_STRIDE ((unsigned long)0x0001e8a0)
#define WAVEFORM_MODE_OFFSET  0x0cu
#define WAVEFORM_COUNT_FLAT   0x14u
#define WAVEFORM_COUNT_BANDS  0x1cu
#define WAVEFORM_COUNT_BLUE   0x24u
#define WAVEFORM_COLUMNS_BASE  ((unsigned long)0x0449ff08)
#define WAVEFORM_COLUMN_STRIDE ((unsigned long)0x0083d600)
#define WAVEFORM_COLUMN_LIMIT  540000u
#define WAVEFORM_3BAND_BASE ((unsigned long)0x059901b0)
#define WAVEFORM_3BAND_BYTES 0xab0u
#define WAVEFORM_PALETTE_BASE ((unsigned long)0x004422f8)
#define WAVEFORM_PALETTE_BYTES 0x20u
#define WAVEFORM_REQUEST_RENEW ((unsigned long)0x001856fc)

enum waveform_shape {
    WAVEFORM_BLUE = 0,
    WAVEFORM_RGB = 1,
    WAVEFORM_3BAND = 2
};

#define STEMWAVE_COLOUR_NONE   0x0000u
#define STEMWAVE_COLOUR_ONE    0xf800u
#define STEMWAVE_COLOUR_TWO    0x07e0u
#define STEMWAVE_COLOUR_FOUR   0x7e5fu
#define STEMWAVE_COLOUR_EIGHT  0xffe0u
/* The initial cache is the ordinary two-stem full mix. */
#define STEMWAVE_MASK_INITIAL 3u

struct waveform_column {
    uint8_t amplitude[3];
    uint8_t reserved;
    uint32_t colour[3];
};
_Static_assert(sizeof(struct waveform_column) == 16u, "waveform column stride");

struct stemwave_selection {
    unsigned int selected;
    unsigned int available;
};

struct stemwave_style {
    unsigned int colour;
    unsigned int roles;
    int suppress_high;
};

struct stemwave_deck {
    volatile unsigned int drawn_mask;
    volatile unsigned int pending;
    volatile unsigned int columns;
    uint8_t package_amplitudes[WAVEFORM_COLUMN_LIMIT * 3u];
    uint8_t blue_original[WAVEFORM_3BAND_BYTES];
    uint8_t blue_filtered[WAVEFORM_3BAND_BYTES];
    volatile unsigned int blue_saved;
};

#endif /* RX3_STEMWAVE_DECL_H */
