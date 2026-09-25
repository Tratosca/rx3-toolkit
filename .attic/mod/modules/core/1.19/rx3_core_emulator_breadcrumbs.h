/* SPDX-License-Identifier: MPL-2.0
   How far init() got, and the deck objects it built on the way.

   Included by rx3_core_hook.c at the point this code used to sit, and only
   in the payload build. Nothing here is compiled for a deck. */
/*
 * Breadcrumbs across UiObjectManager::init(), host-only.
 *
 * init() is entered -- rbp's own StaticInfomation milestone prints immediately
 * before it -- and never returns, so startUp() is never called and neither the
 * front-panel micros nor the touch panel are ever opened. Static analysis
 * cannot say where it stops: a reverse walk of the call graph from every
 * blocking primitive shows no init() callee reaching one, because C++
 * constructors dispatch through vtables and those edges do not exist in the
 * graph. The one thing that does answer it is watching which constructor is
 * entered and never left.
 *
 * Every prologue below is position-independent, which is what install_hook's
 * trampoline requires -- pushes, a register copy, an immediate move and one
 * stack adjustment, no PC-relative load among them.
 *
 * Five arguments because the widest of these takes five; forwarding more than a
 * callee reads is harmless under AAPCS, and it lets one wrapper shape serve all
 * of them rather than five subtly different ones.
 */
typedef void *(*breadcrumb_fn)(void *, void *, void *, void *, void *);

#define BREADCRUMB(name, address, ...)                                        \
    static const uint8_t name##_crumb_guard[8] = {__VA_ARGS__};               \
    static struct installed_hook name##_crumb_hook;                           \
    static breadcrumb_fn original_##name##_crumb;                             \
    static void *hooked_##name##_crumb(void *a, void *b, void *c, void *d,    \
                                       void *e)                               \
    {                                                                         \
        void *result;                                                         \
        log_line("init: enter " #name);                                       \
        result = original_##name##_crumb(a, b, c, d, e);                      \
        log_line("init: leave " #name);                                       \
        return result;                                                        \
    }

BREADCRUMB(PcController, 0x002e7ce0,
           0xf8, 0x40, 0x2d, 0xe9, 0x02, 0x60, 0xa0, 0xe1)
BREADCRUMB(UsbStorageManager, 0x00322878,
           0xf0, 0x4f, 0x2d, 0xe9, 0x14, 0xd0, 0x4d, 0xe2)
BREADCRUMB(BrowseUiIfDpl, 0x0033b658,
           0x00, 0x20, 0xa0, 0xe3, 0xf8, 0x4f, 0x2d, 0xe9)
BREADCRUMB(UsbBrowser, 0x0031ed7c,
           0xf8, 0x45, 0x2d, 0xe9, 0x08, 0x70, 0x80, 0xe2)
BREADCRUMB(addServer, 0x0031e850,
           0xf0, 0x41, 0x2d, 0xe9, 0x00, 0x50, 0xa0, 0xe1)

/* One level down, inside UsbStorageManager -- the constructor the first round
   showed entering and never leaving. These are its only calls that can reach a
   blocking primitive.
   juce::CriticalSection::enter at 0x003c05ac is deliberately absent: it begins
   with a PC-relative branch, so copying it into a trampoline would send it
   somewhere else. It is a veneer, not a function body. */
BREADCRUMB(GpioManager, 0x00028cd8,
           0xf0, 0x41, 0x2d, 0xe9, 0x18, 0xd0, 0x4d, 0xe2)
BREADCRUMB(startThread, 0x003b62fc,
           0x38, 0x40, 0x2d, 0xe9, 0x0c, 0x50, 0x80, 0xe2)
BREADCRUMB(registA, 0x0031ff70,
           0x4c, 0x30, 0x90, 0xe5, 0xf0, 0x45, 0x2d, 0xe9)
BREADCRUMB(registB, 0x0037828c,
           0x38, 0x40, 0x2d, 0xe9, 0x80, 0x40, 0x80, 0xe2)

/* Same, but logged only the first time. For anything on a polling loop, where
   the question is "does this run at all" and a line per call would flood the
   log badly enough to distort rbp's timing. */
#define BREADCRUMB_ONCE(name, address, ...)                                   \
    static const uint8_t name##_crumb_guard[8] = {__VA_ARGS__};               \
    static struct installed_hook name##_crumb_hook;                           \
    static breadcrumb_fn original_##name##_crumb;                             \
    static void *hooked_##name##_crumb(void *a, void *b, void *c, void *d,    \
                                       void *e)                               \
    {                                                                         \
        static volatile unsigned int seen;                                    \
        if (!seen) {                                                          \
            seen = 1u;                                                        \
            log_line("init: first " #name);                                   \
        }                                                                     \
        return original_##name##_crumb(a, b, c, d, e);                        \
    }

BREADCRUMB_ONCE(TouchPanelOpenDevice, 0x002d6c9c,
                0x38, 0x40, 0x2d, 0xe9, 0x00, 0x40, 0xa0, 0xe1)
BREADCRUMB_ONCE(TouchPanelReadFd, 0x002db4cc,
                0xf8, 0x40, 0x2d, 0xe9, 0x00, 0x40, 0xa0, 0xe1)
/* The reader thread body itself. rbp imports no epoll symbols -- those calls
   are internal, so LD_PRELOAD cannot see them and cannot tell "the thread never
   started" from "its epoll registration failed and it returned silently". A
   code hook can. */
BREADCRUMB_ONCE(TouchPanelRun, 0x002d7614,
                0xf0, 0x45, 0x2d, 0xe9, 0x02, 0x8b, 0x2d, 0xed)

/* Latches the two deck objects as they are constructed. Not a breadcrumb: the
   point is the pointer, not the log line. */
static struct installed_hook player_innards_hook;
static breadcrumb_fn original_player_innards_ctor;
static void *hooked_player_innards_ctor(void *object, void *b, void *c,
                                        void *d, void *e)
{
    void *result = original_player_innards_ctor(object, b, c, d, e);
    unsigned int channel = *(const uint8_t *)((const uint8_t *)object + 0x26u);
    if (channel >= 1u && channel <= 2u && !player_innards[channel - 1u]) {
        player_innards[channel - 1u] = object;
        log_number("emulator latched PlayerInnards channel = ", channel);
    }
    return result;
}

#define INSTALL_BREADCRUMB(name, address)                                     \
    do {                                                                      \
        original_##name##_crumb = (breadcrumb_fn)install_hook(                \
            &name##_crumb_hook, (unsigned long)(address),                     \
            name##_crumb_guard, (void *)hooked_##name##_crumb);               \
        if (!original_##name##_crumb)                                         \
            log_line("breadcrumb rejected: " #name);                          \
    } while (0)

/* Installed unconditionally, unlike the breadcrumbs: without a latched object
   the front-panel buttons in the emulator window have nothing to call, and
   that is ordinary functionality rather than a diagnostic. */
static void install_player_innards_latch(void)
{
    original_player_innards_ctor = (breadcrumb_fn)install_hook(
        &player_innards_hook, PLAYER_INNARDS_CTOR, player_innards_guard,
        (void *)hooked_player_innards_ctor);
    if (!original_player_innards_ctor)
        log_line("rejected: unexpected PlayerInnards prologue");
}

static void install_init_breadcrumbs(void)
{
    /* Off unless asked for. These sit on rbp's startup path, so they are a
       diagnostic to switch on, not something every run should carry. */
    const char *requested = getenv("RX3_EMULATOR_TRACE_INIT");
    if (!requested || requested[0] != '1')
        return;
    INSTALL_BREADCRUMB(PcController, 0x002e7ce0);
    INSTALL_BREADCRUMB(UsbStorageManager, 0x00322878);
    INSTALL_BREADCRUMB(BrowseUiIfDpl, 0x0033b658);
    INSTALL_BREADCRUMB(UsbBrowser, 0x0031ed7c);
    INSTALL_BREADCRUMB(addServer, 0x0031e850);
    INSTALL_BREADCRUMB(GpioManager, 0x00028cd8);
    INSTALL_BREADCRUMB(startThread, 0x003b62fc);
    INSTALL_BREADCRUMB(registA, 0x0031ff70);
    INSTALL_BREADCRUMB(registB, 0x0037828c);
    INSTALL_BREADCRUMB(TouchPanelOpenDevice, 0x002d6c9c);
    INSTALL_BREADCRUMB(TouchPanelReadFd, 0x002db4cc);
    INSTALL_BREADCRUMB(TouchPanelRun, 0x002d7614);
    log_line("init breadcrumbs installed");
}
