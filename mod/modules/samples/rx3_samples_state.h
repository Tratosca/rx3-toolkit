/* SPDX-License-Identifier: MPL-2.0 */
static volatile unsigned int samples_mode;
static volatile unsigned int samples_callbacks_enabled;
static volatile unsigned int samples_audio_active;
static unsigned int samples_volume = SAMPLES_VOLUME_DEFAULT;
static unsigned int samples_volume_touched;
static struct samples_config samples_config;
static struct sample_slot samples_slots[SAMPLES_PAD_COUNT];
static struct sample_bank_slot samples_bank[SAMPLES_PAD_COUNT];


/* A shared sample can be held from either deck. Releasing one owner must not
   silence the other. Input events serialize updates; audio only reads voices. */
static unsigned int samples_pad_hold[SAMPLES_PAD_COUNT];
