/* SPDX-License-Identifier: MPL-2.0 */
/* Offline device benchmark. No sound device, shared player memory or hooks. */
#define RX3_OVERCUE_HOST
#include "../mod/modules/stems/overcue/overcue.c"

static double bench_time(int clock_id)
{
    struct timespec t;
    if (clock_gettime(clock_id, &t)) { perror("clock_gettime"); exit(2); }
    return t.tv_sec + t.tv_nsec * 1e-9;
}
static long bench_read_long(const char *path)
{
    FILE *f = fopen(path, "r"); long v = -1;
    if (f) { if (fscanf(f, "%ld", &v) != 1) v = -1; fclose(f); }
    return v;
}
static int bench_order(const void *a, const void *b)
{
    double x = *(const double *)a, y = *(const double *)b;
    return (x > y) - (x < y);
}
int main(int argc, char **argv)
{
    if (argc < 7 || argc > 8) {
        fprintf(stderr, "usage: bench ROOT MEDIA SECONDS DECKS PACED ROLE [PCM_OUTPUT]\n");
        return 2;
    }
    unsigned int seconds = (unsigned int)atoi(argv[3]), decks = (unsigned int)atoi(argv[4]);
    unsigned int paced = (unsigned int)atoi(argv[5]), role = (unsigned int)atoi(argv[6]);
    if (!seconds || seconds > 600 || !decks || decks > 2 || paced > 1 || role > 6) return 2;
    setvbuf(stdout, NULL, _IOLBF, 0);
    struct oc_bank *banks = calloc(decks, sizeof(*banks));
    oc_pair *out = malloc(OC_BLOCK * sizeof(*out));
    unsigned int capacity = seconds * 20 * decks + 100;
    double *times = calloc(capacity, sizeof(*times));
    if (!banks || !out || !times) return 2;
    FILE *sink = argc == 8 ? fopen(argv[7], "wbx") : NULL;
    if (argc == 8 && !sink) { perror("output"); return 2; }
    for (unsigned int d = 0; d < decks; d++)
        for (unsigned int r = 0; r < 7; r++) banks[d].roles[r].fd = -1;
    double init = bench_time(CLOCK_PROCESS_CPUTIME_ID);
    oc_filter_init();
    init = bench_time(CLOCK_PROCESS_CPUTIME_ID) - init;
    double open_cpu = bench_time(CLOCK_PROCESS_CPUTIME_ID);
    double open_wall = bench_time(CLOCK_MONOTONIC);
    for (unsigned int d = 0; d < decks; d++) {
        if (oc_bank_open(&banks[d], argv[1], argv[2]) != 1) {
            fprintf(stderr, "bank validation failed for deck %u\n", d); return 3;
        }
    }
    open_cpu = bench_time(CLOCK_PROCESS_CPUTIME_ID) - open_cpu;
    open_wall = bench_time(CLOCK_MONOTONIC) - open_wall;
    unsigned int track = (unsigned int)((uint64_t)banks[0].frames * 147 / 320);
    if (track < 44100) { fprintf(stderr, "At least one second required\n"); return 2; }
    double start = bench_time(CLOCK_MONOTONIC), process = bench_time(CLOCK_PROCESS_CPUTIME_ID);
    double cpu = 0, wall = 0, max_batch = 0, next_report = 0, energy = 0;
    unsigned int position = 0, done = 0, count = 0, overruns = 0, thermal_stop = 0;
    long maximum_temp = -1;
    const unsigned int total = seconds * 44100;
    while (done < total) {
        double elapsed = bench_time(CLOCK_MONOTONIC) - start;
        if (elapsed >= next_report) {
            long temp = bench_read_long("/sys/class/thermal/thermal_zone0/temp");
            if (temp > 1000) temp /= 1000;
            if (temp > maximum_temp) maximum_temp = temp;
            long freq = bench_read_long("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq");
            printf("{\"telemetry_s\":%.3f,\"temperature_c\":%ld,\"frequency_khz\":%ld}\n", elapsed, temp, freq);
            if (temp >= 75) { thermal_stop = 1; break; }
            next_report = elapsed + 1;
        }
        unsigned int n = total - done;
        if (n > OC_BLOCK) n = OC_BLOCK;
        if (n > track - position) n = track - position;
        double batch = bench_time(CLOCK_MONOTONIC);
        for (unsigned int d = 0; d < decks; d++) {
            double w = bench_time(CLOCK_MONOTONIC), c = bench_time(CLOCK_THREAD_CPUTIME_ID);
            /* The second deck uses real drums while the first uses ROLE. */
            if (!oc_convert(&banks[d], d ? 2 : role, position, n, out)) return 4;
            cpu += bench_time(CLOCK_THREAD_CPUTIME_ID) - c;
            double duration = bench_time(CLOCK_MONOTONIC) - w;
            wall += duration;
            if (count >= capacity) return 5;
            times[count++] = duration;
            for (unsigned int i = 0; i < n; i++) energy += (double)out[i].l * out[i].l + (double)out[i].r * out[i].r;
            if (sink && fwrite(out, sizeof(*out), n, sink) != n) return 6;
        }
        batch = bench_time(CLOCK_MONOTONIC) - batch;
        if (batch > max_batch) max_batch = batch;
        if (batch > n / 44100.0) overruns++;
        done += n; position += n;
        if (position == track) position = 0;
        if (paced) {
            double remaining = start + done / 44100.0 - bench_time(CLOCK_MONOTONIC);
            if (remaining > 0) usleep((unsigned int)(remaining * 1e6));
        }
    }
    double process_cpu = bench_time(CLOCK_PROCESS_CPUTIME_ID) - process;
    double elapsed = bench_time(CLOCK_MONOTONIC) - start;
    qsort(times, count, sizeof(*times), bench_order);
    printf("{\"result\":true,\"decks\":%u,\"paced\":%u,\"frames_per_deck\":%u,\"audio_seconds_per_deck\":%.6f,\"blocks\":%u,\"init_cpu_s\":%.6f,\"open_cpu_s\":%.6f,\"open_wall_s\":%.6f,\"conversion_cpu_s\":%.6f,\"conversion_wall_s\":%.6f,\"process_cpu_s\":%.6f,\"elapsed_s\":%.6f,\"block_wall_p50_ms\":%.3f,\"block_wall_p95_ms\":%.3f,\"block_wall_p99_ms\":%.3f,\"block_wall_max_ms\":%.3f,\"batch_wall_max_ms\":%.3f,\"batches_over_budget\":%u,\"max_temperature_c\":%ld,\"thermal_stop\":%u,\"rms\":%.9f,\"neon\":%u}\n",
           decks, paced, done, done / 44100.0, count, init, open_cpu, open_wall, cpu, wall, process_cpu, elapsed,
           count ? times[count/2]*1000 : 0, count ? times[(count-1)*95/100]*1000 : 0,
           count ? times[(count-1)*99/100]*1000 : 0, count ? times[count-1]*1000 : 0,
           max_batch*1000, overruns, maximum_temp, thermal_stop, done ? sqrt(energy/(done*2.0*decks)) : 0,
#ifdef OC_NEON
           1u
#else
           0u
#endif
    );
    for (unsigned int d = 0; d < decks; d++) oc_bank_close(&banks[d]);
    if (sink && fclose(sink)) return 6;
    free(banks); free(out); free(times);
    return thermal_stop ? 7 : 0;
}
