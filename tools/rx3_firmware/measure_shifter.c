/* SPDX-License-Identifier: MPL-2.0
 * Host harness for the hook's pitch shifter: shift a tone, emit raw stereo
 * float32 on stdout. measure_shifter.py scores it with the same metrics used
 * for the firmware's own effect, so the two are directly comparable. */
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include "../../mod/modules/stems/1.19/rx3_pitch_shift.h"

int main(int argc, char **argv)
{
    int semitones = argc > 1 ? atoi(argv[1]) : 7;
    int rate = argc > 2 ? atoi(argv[2]) : 44100;
    int frames = argc > 3 ? atoi(argv[3]) : 44100 * 2;
    int block = argc > 4 ? atoi(argv[4]) : 64;
    double frequency = argc > 5 ? atof(argv[5]) : 440.0;

    static float history[RX3_SHIFT_HISTORY * 2u];
    struct rx3_shifter state;
    rx3_shifter_init(&state, history);
    rx3_shifter_set_semitones(&state, semitones);

    float *buffer = malloc((size_t)block * 2u * sizeof(float));
    if (!buffer)
        return 1;
    for (int start = 0; start < frames; start += block) {
        int count = frames - start < block ? frames - start : block;
        for (int i = 0; i < count; i++) {
            double phase = 2.0 * M_PI * frequency * (start + i) / rate;
            buffer[i * 2] = (float)(0.5 * sin(phase));
            buffer[i * 2 + 1] = buffer[i * 2];
        }
        if (rx3_shifter_is_active(&state))
            rx3_shifter_process(&state, buffer, (unsigned int)count);
        else
            rx3_shifter_absorb(&state, buffer, (unsigned int)count);
        fwrite(buffer, sizeof(float), (size_t)count * 2u, stdout);
    }
    free(buffer);
    return 0;
}
