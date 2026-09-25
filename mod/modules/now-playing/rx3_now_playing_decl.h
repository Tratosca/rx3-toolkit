/* SPDX-License-Identifier: MPL-2.0
 * What the deck is playing, sent to the computer on the rear USB port.
 *
 * The standalone player's own events say when something changes: a status
 * update, a track committed to a deck, a track taken off one, a channel going
 * on or off air. Its own accessors then say what the state is. Nothing here
 * polls the decks; the only timer is the heartbeat that lets a listener started
 * mid-set catch up.
 */

#ifndef RX3_NOW_PLAYING_DECL_H
#define RX3_NOW_PLAYING_DECL_H

/* Hooked. Each returns first, then this only records that a deck changed. */
#define NOW_PLAYING_STATUS_UPDATED ((unsigned long)0x002f1bf8)
#define NOW_PLAYING_LOAD_TRACK     ((unsigned long)0x002f20e4)
#define NOW_PLAYING_UNLOAD_RESULT  ((unsigned long)0x002f1e4c)
#define NOW_PLAYING_MIXER_ON_AIR_UPDATE ((unsigned long)0x00057fb0)

static const uint8_t now_playing_status_guard[8] = {
    0xf8, 0x40, 0x2d, 0xe9, 0x01, 0x20, 0xa0, 0xe1
};
static const uint8_t now_playing_load_guard[8] = {
    0xf0, 0x4f, 0x2d, 0xe9, 0x00, 0x40, 0xa0, 0xe1
};
static const uint8_t now_playing_unload_guard[8] = {
    0xf8, 0x40, 0x2d, 0xe9, 0x00, 0x40, 0xa0, 0xe1
};
static const uint8_t now_playing_mixer_guard[8] = {
    0xf8, 0x4f, 0x2d, 0xe9, 0x04, 0x8b, 0x2d, 0xed
};

/* Called, not hooked. Each name pairs with its guard, which is how
   scripts/check_addresses.py finds them. */
#define NOW_PLAYING_CURRENT_TRACK ((unsigned long)0x002f1410)
#define NOW_PLAYING_PLAY_MODE     ((unsigned long)0x000fd960)
#define NOW_PLAYING_PLAY_BPM      ((unsigned long)0x000fd1fc)
#define NOW_PLAYING_PLAY_TEMPO    ((unsigned long)0x000fd2dc)
#define NOW_PLAYING_ON_AIR        ((unsigned long)0x000fe34c)

static const uint8_t now_playing_current_track_guard[8] = {
    0x3c, 0x31, 0x90, 0xe5, 0x04, 0x00, 0x93, 0xe5
};
static const uint8_t now_playing_play_mode_guard[8] = {
    0xf8, 0x40, 0x2d, 0xe9, 0x00, 0x60, 0xa0, 0xe1
};
static const uint8_t now_playing_play_bpm_guard[8] = {
    0x08, 0x40, 0x2d, 0xe9, 0x00, 0x10, 0xa0, 0xe1
};
static const uint8_t now_playing_play_tempo_guard[8] = {
    0x24, 0x30, 0x9f, 0xe5, 0x00, 0x10, 0xa0, 0xe1
};
static const uint8_t now_playing_on_air_guard[8] = {
    0x01, 0x20, 0xa0, 0xe1, 0x30, 0x10, 0x9f, 0xe5
};

/* Where the player keeps what this reads. The channel byte counts from one. */
#define NOW_PLAYING_PLAYER_CHANNEL 0x26u
#define NOW_PLAYING_MUSIC_ID       0x04u
#define NOW_PLAYING_MUSIC_TITLE    0x28u
#define NOW_PLAYING_MIXER_ON_AIR_A 0x64u
#define NOW_PLAYING_MIXER_ON_AIR_B 0x65u
#define NOW_PLAYING_TITLE_UNITS    128u

typedef void (*now_playing_status_fn)(void *, int);
typedef int (*now_playing_load_fn)(void *, const void *);
typedef void (*now_playing_unload_fn)(void *, int, unsigned int, unsigned int);
typedef void (*now_playing_mixer_fn)(void *);
typedef void *(*now_playing_current_track_fn)(void *, int);
typedef int (*now_playing_deck_int_fn)(unsigned int);
typedef int (*now_playing_on_air_fn)(unsigned int, int);

/* The link the rear USB-B port brings up is link-local, so its directed
   broadcast reaches the computer on the other end and nothing routed. The
   limited broadcast 255.255.255.255 would leave on every interface. */
#define NOW_PLAYING_PORT 50123u
#define NOW_PLAYING_BROADCAST 0xfffffea9u      /* 169.254.255.255, network order */
#define NOW_PLAYING_HEARTBEAT_MS 2000
#define NOW_PLAYING_DATAGRAM_MAX 2048u

/* libc names this feature adds to the core's set. rbp imports every one of
   them itself, which is what tests/test_hook_symbols.py asks to be confirmed. */
struct pollfd {
    int   fd;
    short events;
    short revents;
};
struct now_playing_address {
    uint16_t family;
    uint16_t port;
    uint32_t address;
    uint8_t  zero[8];
};
extern size_t  strlen(const char *);
extern int     socket(int, int, int);
extern int     socketpair(int, int, int, int[2]);
extern int     setsockopt(int, int, int, const void *, unsigned int);
extern ssize_t sendto(int, const void *, size_t, int, const void *, unsigned int);
extern ssize_t send(int, const void *, size_t, int);
extern ssize_t recv(int, void *, size_t, int);
extern int     poll(struct pollfd *, unsigned long, int);

#define NOW_PLAYING_AF_UNIX   1
#define NOW_PLAYING_AF_INET   2
#define NOW_PLAYING_DGRAM     2
#define NOW_PLAYING_NONBLOCK  04000
#define NOW_PLAYING_SOL_SOCKET 1
#define NOW_PLAYING_SO_BROADCAST 6
#define NOW_PLAYING_DONTWAIT  0x40
#define NOW_PLAYING_POLLIN    0x0001

#endif /* RX3_NOW_PLAYING_DECL_H */
