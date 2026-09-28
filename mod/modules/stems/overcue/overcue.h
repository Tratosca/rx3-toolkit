/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_OVERCUE_H
#define RX3_OVERCUE_H
/* Experimental adapter. Positions and output are always on the 44.1 kHz grid.
 * The worker alone opens files, verifies pages and resamples. */
/* Cumulative per-deck worker timings include read, verify, inflate and SRC.
 * A block represents 4096 / 44100 seconds; emulator clocks are not device CPU.
 * Snapshots never block the caller. Counters reset at adapter startup. */
struct rx3_overcue_stats {
    unsigned long long cpu_us,wall_us;
    unsigned int timed_blocks,max_cpu_us,max_wall_us,clock_errors;
    unsigned int hits,misses,blocks;
};
int rx3_overcue_stats(unsigned int deck,struct rx3_overcue_stats *out);
int rx3_overcue_start(void);
void rx3_overcue_stop(void);
void rx3_overcue_track(unsigned int deck, const char *path);
unsigned int rx3_overcue_status(unsigned int deck);
int rx3_overcue_render(unsigned int deck, unsigned int position,
                       void *stereo_float, unsigned int frames, unsigned int mask);
#endif
