/* SPDX-License-Identifier: MPL-2.0 */
#include "../core/api/rx3_module_api.h"
#include "rx3_position_snapshot.h"
#include "rx3_audio_stream.h"
/* Linux ARM socket ABI, same existing libc imports as Now Playing. */
extern int socket(int, int, int);
extern int setsockopt(int, int, int, const void *, unsigned int);
extern ssize_t sendto(int, const void *, size_t, int, const void *, unsigned int);
struct position_address { uint16_t family, port; uint32_t address; uint8_t zero[8]; };
static const struct rx3_services *framework;
static struct position_slot slots[2];
static struct audio_ring audio_rings[2];
static unsigned int running, claimed, thread_started;
static pthread_t worker_thread;
static int udp = -1;
static int audio_udp = -1;
static char owner;
static void stream(unsigned int deck, const void *reader, int position,
                   struct rx3_stereo *output, unsigned int frames)
{
    if (deck < 2u) {
        position_observe(&slots[deck], reader, position, frames);
        audio_enqueue(&audio_rings[deck],
                      __atomic_load_n(&slots[deck].generation, __ATOMIC_RELAXED),
                      position, output, frames);
    }
}
static void loading(unsigned int deck, void *reader, const void *info)
{
    (void)reader; (void)info;
    if (deck < 2u) position_loading(&slots[deck]);
}
static void loaded(unsigned int deck, void *reader, const void *info)
{
    (void)info;
    if (deck < 2u) position_loaded(&slots[deck], reader);
}
struct text { char bytes[768]; unsigned int n; };
static void literal(struct text *t, const char *s)
{
    while (*s && t->n < sizeof(t->bytes)) t->bytes[t->n++] = *s++;
}
static void number(struct text *t, unsigned int n)
{
    char b[10]; unsigned int used = 0;
    do { b[used++] = (char)('0' + n % 10u); n /= 10u; } while (n);
    while (used && t->n < sizeof(t->bytes)) t->bytes[t->n++] = b[--used];
}
static void emit(unsigned int sequence)
{
    struct text t = {{0}, 0};
    literal(&t, "{\"type\":\"position-diagnostic\",\"version\":1,\"sequence\":"); number(&t, sequence);
    literal(&t, ",\"units\":\"unverified\",\"decks\":[");
    for (unsigned int i=0; i<2u; i++) {
        struct position_value v = {0};
        int valid = position_read(&slots[i], &v);
        unsigned int generation = __atomic_load_n(&slots[i].generation, __ATOMIC_SEQ_CST);
        valid = valid && v.generation == generation;
        literal(&t, i ? ",{\"deck\":" : "{\"deck\":"); number(&t, i+1u);
        literal(&t, ",\"readerGeneration\":"); number(&t, generation);
        /* Diagnostic only: a reader observation is NOT an audible/play state. */
        literal(&t, ",\"sample\":");
        if (!valid) literal(&t, "null");
        else {
            literal(&t, "{\"generation\":"); number(&t, v.generation);
            literal(&t, ",\"observation\":"); number(&t, v.observation);
            literal(&t, ",\"rawPosition\":");
            if (v.raw < 0) literal(&t, "-");
            number(&t, v.raw < 0 ? 0u-(unsigned int)v.raw : (unsigned int)v.raw);
            literal(&t, ",\"frames\":"); number(&t, v.frames); literal(&t, "}");
        }
        literal(&t, "}");
    }
    literal(&t, "]}\n");
    struct position_address to = {2, (uint16_t)((50124u>>8u)|((50124u&255u)<<8u)), 0xfffffea9u, {0}};
    if (t.n < sizeof(t.bytes)) (void)sendto(udp,t.bytes,t.n,0x40,&to,sizeof(to));
}
static void *worker(void *unused)
{
    (void)unused; unsigned int sequence = 0;
    struct position_address audio_to = {2, (uint16_t)((50127u>>8u)|((50127u&255u)<<8u)), 0xfffffea9u, {0}};
    while (__atomic_load_n(&running, __ATOMIC_SEQ_CST)) {
        if (sequence++ % 5u == 0u) emit(sequence / 5u);
        /* Drain outside the audio thread, at most 10 packets/deck/tick. A
         * stalled peer cannot hold up the producer; the ring drops instead. */
        for (unsigned int deck=0; deck<2u; ++deck)
            for (unsigned int n=0; n<10u; ++n) {
                struct audio_packet p;
                if (!audio_dequeue(&audio_rings[deck], &p)) break;
                uint8_t packet[32u + AUDIO_PACKET_SAMPLES*2u] = {0};
                /* Wire v1: RX3A, version, deck, sample rate, sequence,
                 * generation, source frame, drops, sample count, PCM16LE. */
                packet[0]='R'; packet[1]='X'; packet[2]='3'; packet[3]='A';
                packet[4]=1; packet[5]=(uint8_t)(deck+1u);
                const uint32_t words[5] = {AUDIO_SAMPLE_RATE,p.sequence,
                                            p.generation,(uint32_t)p.source_position,p.dropped};
                for (unsigned int w=0; w<5u; ++w)
                    for (unsigned int b=0; b<4u; ++b)
                        packet[8u+4u*w+b]=(uint8_t)(words[w]>>(8u*b));
                packet[28]=(uint8_t)p.count; packet[29]=(uint8_t)(p.count>>8u);
                for (unsigned int i=0; i<p.count; ++i) {
                    uint16_t value=(uint16_t)p.samples[i];
                    packet[32u+2u*i]=(uint8_t)value;
                    packet[33u+2u*i]=(uint8_t)(value>>8u);
                }
                (void)sendto(audio_udp,packet,32u+2u*p.count,0x40,&audio_to,sizeof(audio_to));
            }
        usleep(10000u); /* Position remains <=20 Hz below. */
    }
    return 0;
}
static int configured(void)
{
    const char *s = getenv("RX3_POSITION_DIAGNOSTIC");
    return s && s[0]=='1';
}
static void stop(void)
{
    __atomic_store_n(&running,0u,__ATOMIC_SEQ_CST);
    if (thread_started) { pthread_join(worker_thread,0); thread_started=0; }
    if (claimed) { framework->audio->release_deck_stream(&owner); claimed=0; }
    if (udp>=0) close(udp);
    if (audio_udp>=0) close(audio_udp);
    udp=audio_udp=-1;
}
static int start(const struct rx3_services *s)
{
    framework=s;
    memset(slots,0,sizeof(slots));
    memset(audio_rings,0,sizeof(audio_rings));
    udp=socket(2,2,0);
    audio_udp=socket(2,2,0);
    int on=1;
    if (udp<0 || audio_udp<0 || setsockopt(udp,1,6,&on,sizeof(on)) ||
        setsockopt(audio_udp,1,6,&on,sizeof(on))) return 0;
    if (!s->audio->claim_deck_stream(&owner,stream)) return 0;
    claimed=1;
    __atomic_store_n(&running,1u,__ATOMIC_SEQ_CST);
    if (pthread_create(&worker_thread,0,worker,0)) return 0;
    thread_started=1;
    s->log_line("position diagnostic: raw observations, units unverified, UDP 50124");
    return 1;
}
const struct rx3_module rx3_position_diagnostic_module = {
    RX3_MODULE_API_VERSION, sizeof(struct rx3_module), "position-diagnostic",
    configured,start,stop,loaded,0,0,0,loading
};
