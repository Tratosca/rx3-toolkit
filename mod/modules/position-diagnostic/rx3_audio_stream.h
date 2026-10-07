/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_AUDIO_STREAM_H
#define RX3_AUDIO_STREAM_H
#include <stdint.h>

/* One producer per deck, one worker consumer. Audio callbacks never wait, do
 * I/O, allocate, or retry a full queue. Every slot is under the UDP MTU. */
#define AUDIO_RING_SLOTS 32u
#define AUDIO_PACKET_SAMPLES 512u
#define AUDIO_SAMPLE_RATE 22050u
struct audio_packet {
    uint32_t sequence;
    int32_t source_position;
    uint32_t generation;
    uint32_t dropped;
    uint16_t count;
    int16_t samples[AUDIO_PACKET_SAMPLES];
};
struct audio_ring {
    struct audio_packet packet[AUDIO_RING_SLOTS];
    volatile uint32_t head, tail, sequence, dropped, producing;
    uint32_t last_generation, last_frames;
    int32_t last_position;
    uint8_t has_last;
};
static int16_t audio_pcm16(float sample)
{
    if (sample != sample) sample = 0.0f;
    if (sample >= 1.0f) return 32767;
    if (sample <= -1.0f) return -32768;
    return (int16_t)(sample * 32767.0f);
}
static void audio_enqueue(struct audio_ring *ring, uint32_t generation,
                          int32_t position, const struct rx3_stereo *pcm,
                          unsigned int frames)
{
    if (!pcm || !frames || __atomic_exchange_n(&ring->producing, 1u, __ATOMIC_ACQUIRE)) {
        __atomic_add_fetch(&ring->dropped, 1u, __ATOMIC_RELAXED);
        return;
    }
    /* A surprising native block is truncated instead of extending callback
     * time or writing beyond the fixed slot. Only even source frames are sent. */
    if (frames > AUDIO_PACKET_SAMPLES * 2u) {
        frames = AUDIO_PACKET_SAMPLES * 2u;
        __atomic_add_fetch(&ring->dropped, 1u, __ATOMIC_RELAXED);
    }
    /* TimeStretch can render the same reader along two overlapping paths.
     * Keep one forward progression; a sufficiently large rewind is a cue or
     * loop wrap. Never let the doubled callback rate become doubled audio. */
    if (ring->has_last && generation == ring->last_generation &&
            (int64_t)position < (int64_t)ring->last_position + ring->last_frames &&
            (int64_t)ring->last_position - position < 4096) {
        __atomic_store_n(&ring->producing, 0u, __ATOMIC_RELEASE);
        return;
    }
    uint32_t head = __atomic_load_n(&ring->head, __ATOMIC_RELAXED);
    uint32_t tail = __atomic_load_n(&ring->tail, __ATOMIC_ACQUIRE);
    if (head - tail >= AUDIO_RING_SLOTS) {
        __atomic_add_fetch(&ring->dropped, 1u, __ATOMIC_RELAXED);
        __atomic_store_n(&ring->producing, 0u, __ATOMIC_RELEASE);
        return;
    }
    struct audio_packet *p = &ring->packet[head % AUDIO_RING_SLOTS];
    p->sequence = __atomic_fetch_add(&ring->sequence, 1u, __ATOMIC_RELAXED);
    p->source_position = position;
    p->generation = generation;
    p->dropped = __atomic_load_n(&ring->dropped, __ATOMIC_RELAXED);
    p->count = (uint16_t)((frames + 1u) / 2u);
    for (unsigned int i = 0; i < p->count; ++i) {
        float mono = 0.5f * (pcm[2u*i].left + pcm[2u*i].right);
        p->samples[i] = audio_pcm16(mono);
    }
    __atomic_store_n(&ring->head, head + 1u, __ATOMIC_RELEASE);
    ring->last_generation = generation;
    ring->last_position = position;
    ring->last_frames = frames;
    ring->has_last = 1u;
    __atomic_store_n(&ring->producing, 0u, __ATOMIC_RELEASE);
}
static int audio_dequeue(struct audio_ring *ring, struct audio_packet *out)
{
    uint32_t tail = __atomic_load_n(&ring->tail, __ATOMIC_RELAXED);
    if (tail == __atomic_load_n(&ring->head, __ATOMIC_ACQUIRE)) return 0;
    *out = ring->packet[tail % AUDIO_RING_SLOTS];
    __atomic_store_n(&ring->tail, tail + 1u, __ATOMIC_RELEASE);
    return 1;
}
#endif
