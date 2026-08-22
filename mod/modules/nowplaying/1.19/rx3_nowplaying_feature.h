/* SPDX-License-Identifier: MPL-2.0 - now playing (final) */
#ifndef RX3_NOWPLAYING_FEATURE_H
#define RX3_NOWPLAYING_FEATURE_H

extern int  socket(int, int, int);
extern int  setsockopt(int, int, int, const void *, unsigned int);
extern long sendto(int, const void *, size_t, int, const void *, unsigned int);

#define NOWPLAYING_FILE      "/tmp/rx3-nowplaying.txt"
#define NOWPLAYING_PATH_MAX  512u
#define NP_ADDR_LIMITED  0xFFFFFFFFu
#define NP_ADDR_APIPA    0xFFFFFEA9u

struct np_sa { unsigned short f; unsigned short p; unsigned int a; unsigned char z[8]; };
static char nowplaying_paths[2][NOWPLAYING_PATH_MAX];
static int np_fd = -1;

static void np_send(unsigned int addr, const char *b, unsigned int n)
{
    if (np_fd < 0) {
        int fd = socket(2, 2, 0);
        if (fd < 0) return;
        int on = 1;
        (void)setsockopt(fd, 1, 6, &on, sizeof(on));
        np_fd = fd;
    }
    struct np_sa d;
    memset(&d, 0, sizeof(d));
    d.f = 2;
    d.p = (unsigned short)((50123u >> 8) | (50123u << 8));
    d.a = addr;
    (void)sendto(np_fd, b, n, 0, &d, sizeof(d));
}

static void nowplaying_broadcast(void)
{
    char buf[2u * (NOWPLAYING_PATH_MAX + 8u) + 32u];
    unsigned int n = 0u;
    const char *hb = "hb\tRX3 nowplaying alive\n";
    for (const char *h = hb; *h; ) buf[n++] = *h++;
    for (unsigned int deck = 0; deck < 2u; deck++) {
        const char *p = nowplaying_paths[deck];
        buf[n++] = (char)('0' + deck);
        buf[n++] = '\t';
        while (*p && n < sizeof(buf) - 2u) buf[n++] = *p++;
        buf[n++] = '\n';
    }
    np_send(NP_ADDR_LIMITED, buf, n);
    np_send(NP_ADDR_APIPA, buf, n);
    int fd = open(NOWPLAYING_FILE, O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (fd >= 0) { (void)write(fd, buf, n); (void)close(fd); }
}

static void *nowplaying_beacon(void *arg)
{
    (void)arg;
    for (;;) { nowplaying_broadcast(); usleep(2000000u); }
    return 0;
}

static int nowplaying_feature_configured(void) { return getenv("RX3_NOWPLAYING") != 0; }
static int nowplaying_feature_install(void)
{
    pthread_t t;
    if (pthread_create(&t, 0, nowplaying_beacon, 0) == 0) pthread_detach(t);
    return 1;
}
static void nowplaying_feature_remove(void) {}

static void nowplaying_feature_track_did_load(unsigned int deck, void *reader,
                                              const void *track_info)
{
    (void)reader;
    if (deck >= 2u) return;
    const char *path = (const char *)track_info;
    unsigned int i = 0u;
    if (path) {
        while (path[i] && i < NOWPLAYING_PATH_MAX - 1u) {
            nowplaying_paths[deck][i] = path[i];
            i++;
        }
    }
    nowplaying_paths[deck][i] = '\0';
    nowplaying_broadcast();
    log_line("nowplaying: track loaded");
}

#endif /* RX3_NOWPLAYING_FEATURE_H */