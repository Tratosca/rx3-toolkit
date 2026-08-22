/* SPDX-License-Identifier: MPL-2.0
   The commands a host sends in place of a front panel.

   Included by rx3_core_hook.c at the point this code used to sit, and only
   in the payload build. Nothing here is compiled for a deck. */
static int emulator_parse_coordinate(const char **cursor, int *value)
{
    const char *position = *cursor;
    int parsed = 0;
    int digits = 0;
    while (*position == ' ' || *position == '\t')
        position++;
    while (*position >= '0' && *position <= '9') {
        parsed = parsed * 10 + (*position - '0');
        position++;
        digits++;
    }
    *cursor = position;
    *value = parsed;
    return digits != 0;
}

/* Press and release one of rbp's browse keys by table index.

   The record only has to be marked: BrowseKeyProcessing() is already running
   in the UI cycle and dispatches whatever it finds. Press and release are two
   separate marks, and the release is what lets the key be pressed again --
   UiKey_KeyPush refuses a press while the record is still busy. */
static unsigned long emulator_browse_mode(void)
{
    return (unsigned long)*(volatile unsigned int *)UI_BROWSE_MODE;
}

/*
 * Is there an eventflag to post to?
 *
 * set_flg is the right way to finish a browse key -- it is what
 * BrowseUiIf::InputKey does -- but it only works if the flag object exists, and
 * under QEMU that is exactly what cannot be assumed: UiObjectManager::init()
 * never returns, so whatever creates the flag may never have run. Posting to an
 * id that was never created wedged a whole run: rbp stopped painting mid-press
 * and the container went unresponsive, which is a far worse failure than the
 * key simply doing nothing.
 *
 * The id is created by the ITRON layer as a small positive integer, and the
 * word starts as zero in a fresh .bss. Zero or an implausible value therefore
 * means "not created yet", and the caller falls back to driving the pump
 * directly -- the pre-existing behaviour, which at least dispatches the handler.
 */
#define BROWSE_EVENT_FLAG_MAX 1024

static int emulator_browse_flag_ready(void)
{
    int id = *(volatile int *)BROWSE_EVENT_FLAG_ID;
    return id > 0 && id <= BROWSE_EVENT_FLAG_MAX;
}

static void emulator_press_browse_key(int index, int hold_ms)
{
    typedef int (*ui_key_push_fn)(int, unsigned int, unsigned int, int);
    ui_key_push_fn push = (ui_key_push_fn)UI_KEY_PUSH;
    if (index < 0 || index >= 0xe6)
        return;
    /* Some keys are held rather than tapped -- MENU is up to three seconds --
       and the duration is measured by the pump while the record stays marked,
       so the hold has to happen between the two marks. Capped so a malformed
       command cannot park this thread indefinitely. */
    if (hold_ms < 30)
        hold_ms = 30;
    if (hold_ms > 5000)
        hold_ms = 5000;
    if (ui_key_push_usable < 0)
        ui_key_push_usable =
            memcmp((const void *)UI_KEY_PUSH, ui_key_push_guard,
                   sizeof(ui_key_push_guard)) == 0 &&
            memcmp((const void *)BROWSE_KEY_PUMP, browse_key_pump_guard,
                   sizeof(browse_key_pump_guard)) == 0 &&
            memcmp((const void *)SET_FLG, set_flg_guard,
                   sizeof(set_flg_guard)) == 0;
    if (!ui_key_push_usable) {
        log_line("rejected: unexpected UiKey_KeyPush prologue");
        return;
    }
    /* The press is only accepted when the record is idle, so a press that is
       refused means the previous one is still sitting there undispatched --
       which is how a stalled BrowseKeyProcessing tells itself apart from a
       handler that ran and simply had nothing to do. */
    typedef int (*browse_pump_fn)(void);
    typedef int (*set_flg_fn)(int, unsigned int);
    browse_pump_fn pump = (browse_pump_fn)BROWSE_KEY_PUMP;
    set_flg_fn wake = (set_flg_fn)SET_FLG;
    /* Post the eventflag and let Ui_EventTask run the pump on its own thread,
       the way BrowseUiIf::InputKey does. RX3_EMULATOR_PUMP=1 restores the old
       direct call, which is kept because it is the only thing that dispatches a
       key at all if the event task is not running -- and because it is the
       control this change has to be measured against. */
    /* RX3_EMULATOR_PUMP forces a route: 1 drives the pump from this thread, 0
       insists on the eventflag even when it looks absent. Unset picks the
       eventflag when there is one and falls back to the pump when there is
       not, which is what makes this safe to leave on by default. */
    const char *pump_setting = getenv("RX3_EMULATOR_PUMP");
    int flag_ready = emulator_browse_flag_ready();
    /* An empty value counts as unset, so the runner can pass the variable
       through unconditionally and still leave the choice here. */
    int pump_here = (pump_setting && pump_setting[0])
                        ? pump_setting[0] == '1'
                        : !flag_ready;
    unsigned long mode_before = emulator_browse_mode();
    /* Logged before the press, not after. A post to a flag that does not exist
       took the whole process down last time, and a line written afterwards
       would not have survived to say so. */
    log_number("emulator browse key = ", (unsigned long)index);
    log_number("emulator browse flag id = ",
               (unsigned long)*(volatile int *)BROWSE_EVENT_FLAG_ID);
    log_line(pump_here ? "emulator browse route = pump"
                       : "emulator browse route = eventflag");
    int accepted = push(index, 0u, 0u, 1);
    if (accepted) {
        if (pump_here)
            pump();
        else
            wake(*(volatile int *)BROWSE_EVENT_FLAG_ID, BROWSE_EVENT_FLAG_KEY);
    }
    usleep((unsigned int)hold_ms * 1000u);
    push(index, 0u, 1u, 0);
    if (pump_here)
        pump();
    else
        wake(*(volatile int *)BROWSE_EVENT_FLAG_ID, BROWSE_EVENT_FLAG_KEY);
    log_number("emulator browse key accepted = ", (unsigned long)(accepted != 0));
    log_number("emulator browse mode before = ", mode_before);
    /* Sampled over a second, not read once.
       Ui_EventTask runs on its own thread: reading the mode immediately after
       posting the flag cannot see a change that lands milliseconds later, and
       an earlier version of this probe reported "no change" for exactly that
       reason. ChangeBrowseMode does not set the mode itself either -- it marks
       browseCommand and something else acts on it -- so the pending word is
       logged next to the mode, to tell "nobody consumed the request" apart from
       "the request was consumed and the mode still did not move". */
    {
        unsigned int step;
        for (step = 0u; step < 10u; step++) {
            usleep(100000u);
            if (emulator_browse_mode() != mode_before)
                break;
        }
        log_number("emulator browse mode after = ", emulator_browse_mode());
        log_number("emulator browse settle ms = ", (unsigned long)(step + 1u) * 100u);
        log_number("emulator browse pending = ",
                   (unsigned long)*(volatile unsigned int *)BROWSE_COMMAND_PENDING);
        log_number("emulator browse requested = ",
                   (unsigned long)*(volatile unsigned int *)(BROWSE_COMMAND_PENDING + 4u));
    }
}

/*
 * Drive rbp's own touch panel, rather than standing in for it.
 *
 * TouchPanelComm::readFd does read(fd, buf, 6) on /dev/tsc2007_2-0048, which
 * the shim backs with a FIFO; writing that struct into it puts a touch through
 * the genuine Calibration -> TouchPanelHandler -> solveCoordToKey path, so the
 * stock controls answer, not only the mod's own panel. Reaching this at all
 * needed startUp() to run, which is why it could not be done before.
 *
 * Layout and calibration are the ones captured from 700 packets on real
 * hardware: six bytes, pressed / padding / x / y little-endian, with X
 * inverted. TouchAdValueHysteresis wants several consecutive samples agreeing
 * before it believes a press, so one packet is not a touch.
 */
#define TSC2007_FIFO "/tmp/rx3emu-device-tsc2007_2-0048.fifo"
#define TOUCH_SAMPLES 8u

static void emulator_write_touch_sample(int pressed, int x_raw, int y_raw)
{
    uint8_t packet[6];
    int fd = open(TSC2007_FIFO, O_WRONLY | O_NONBLOCK);
    if (fd < 0) {
        log_number("touch sample open failed = ", (unsigned long)(-fd));
        return;
    }
    packet[0] = (uint8_t)(pressed ? 1 : 0);
    packet[1] = 0u;
    packet[2] = (uint8_t)(x_raw & 0xff);
    packet[3] = (uint8_t)((x_raw >> 8) & 0xff);
    packet[4] = (uint8_t)(y_raw & 0xff);
    packet[5] = (uint8_t)((y_raw >> 8) & 0xff);
    {
        ssize_t written = write(fd, packet, sizeof(packet));
        if (written != (ssize_t)sizeof(packet))
            log_number("touch sample short write = ", (unsigned long)written);
    }
    close(fd);
}

static void emulator_hardware_touch(int x, int y)
{
    log_line("hardware touch: entered");
    if (x < 0 || x >= 1280 || y < 0 || y >= 720)
        return;
    /* The panel is 800 rows tall even though the visible mode is 720, so the
       Y divisor is not the screen height. Both axes stay inside 32 bits. */
    int x_raw = 37 + (1280 - x) * 3976 / 1280;
    int y_raw = 72 + y * 3856 / 800;
    for (unsigned int i = 0; i < TOUCH_SAMPLES; i++) {
        emulator_write_touch_sample(1, x_raw, y_raw);
        usleep(20000u);
    }
    /* Release twice: the same hysteresis that debounces the press debounces
       the lift, and a control that never sees one stays held. */
    emulator_write_touch_sample(0, x_raw, y_raw);
    usleep(20000u);
    emulator_write_touch_sample(0, x_raw, y_raw);
    log_number("emulator hardware touch x = ", (unsigned long)x);
    log_number("emulator hardware touch y = ", (unsigned long)y);
}

/*
 * Press one of rbp's own player keys.
 *
 * The four pad-mode selectors and the eight pads are methods on PlayerInnards,
 * not entries in the browse-key table, so pressing one means calling the
 * handler with a real object and a real uif::IKeyInput. The object comes from
 * the constructor hook above -- no physical key ever arrives here to supply
 * one. The event layout is the one rx3_stems_feature.h already decodes: the
 * 16-bit code at +8, the 1-based channel at +10, and press or release in the
 * low nibble of +11.
 *
 * Codes are from REFERENCES.md appendix A, recovered statically.
 */
static void emulator_press_player_key(unsigned int code, unsigned int deck)
{
    typedef int (*on_key_fn)(void *, const void *);
    unsigned long handler;
    uint8_t event[64];
    void *player;

    if (deck > 1u)
        return;
    player = player_innards[deck];
    if (!player) {
        log_line("player key ignored: no PlayerInnards latched yet");
        return;
    }
    if (code >= 0x4117u && code <= 0x411eu)
        handler = ON_KEY_PAD;
    else if (code == 0x4113u)
        handler = ON_KEY_HOT_CUE;
    else if (code == 0x4114u)
        handler = ON_KEY_BEAT_LOOP;
    else if (code == 0x4115u)
        handler = ON_KEY_SLIP_LOOP;
    else if (code == 0x4116u)
        handler = ON_KEY_BEAT_JUMP;
    else {
        log_number("player key has no handler route, code = ",
                   (unsigned long)code);
        return;
    }

    memset(event, 0, sizeof(event));
    {
        unsigned long vptr = KEY_INPUT_VTABLE;
        memcpy(event, &vptr, sizeof(uint32_t));
    }
    event[8] = (uint8_t)(code & 0xffu);
    event[9] = (uint8_t)((code >> 8) & 0xffu);
    event[10] = (uint8_t)(deck + 1u);
    event[11] = 0u;                       /* press */
    ((on_key_fn)handler)(player, event);
    /* Release as its own event: the pad-mode handlers act on the press and the
       mod's own hooks key their STATUS restore off the same nibble, so a press
       never delivered a release would leave the control held. */
    usleep(30000u);
    event[11] = 3u;
    ((on_key_fn)handler)(player, event);
    log_number("emulator player key = ", (unsigned long)code);
    log_number("emulator player key deck = ", (unsigned long)(deck + 1u));
}

/* Ask rbp to invalidate display regions. A diagnostic: if a key changes the
   screen state but nothing repaints, forcing this is what makes the difference
   visible -- and if it changes nothing, the screen state never changed. */
static void emulator_invalidate_display(unsigned int mask)
{
    typedef void (*invalidate_fn)(unsigned int);
    if (memcmp((const void *)GUI_DISP_INVALIDATE, gui_invalidate_guard,
               sizeof(gui_invalidate_guard))) {
        log_line("rejected: unexpected SndDispInvalidate prologue");
        return;
    }
    ((invalidate_fn)GUI_DISP_INVALIDATE)(mask);
    log_number("emulator display invalidate mask = ", (unsigned long)mask);
}

static void emulator_apply_touch(int x, int y)
{
    const struct rx3_panel_feature *panel;
    if (x < 0 || x >= 1280 || y < 0 || y >= 720)
        return;

    if (y >= 363 && y <= 413) {
        const struct rx3_panel_feature *requested = 0;
        if (x >= 1090 && x <= 1179)
            requested = panel_for_slot(0u);
        else if (x >= 1181 && x <= 1270)
            requested = panel_for_slot(1u);
        if (requested) {
            emulator_forced_panel = requested->panel_id;
            emulator_panel_applied = 1u;
            select_custom_panel(requested->panel_id);
            log_number("emulator touch selected panel = ", requested->panel_id);
        }
        return;
    }

    if (y >= 433 && y <= 483 && x >= 1090 && x <= 1270) {
        emulator_forced_panel = 0u;
        emulator_panel_applied = 0u;
        overlay_panel = 0u;
        captured_native_touch = 0;
        configure_native_performance_touches(0u);
        original_set_beatfx_selected(x >= 1181 ? 1 : 0);
        refresh_performance_ui();
        log_line(x >= 1181 ? "emulator touch selected BEAT FX"
                           : "emulator touch selected STATUS");
        return;
    }

    panel = panel_for_id(overlay_panel);
    if (panel && y >= 521 && y <= 560) {
        unsigned int deck = x >= 640 ? 1u : 0u;
        int local_x = x - (int)(deck * 640u);
        for (unsigned int control = 0; control < panel->control_count; control++) {
            if (local_x >= panel->lefts[control] &&
                local_x <= panel->rights[control]) {
                panel->activate(deck, control);
                refresh_performance_ui();
                log_number("emulator touch deck = ", deck + 1u);
                log_number("emulator touch control = ", control);
                return;
            }
        }
    }
}

static void emulator_poll_touch(void)
{
    char command[64];
    ssize_t count;
    const char *cursor;
    int sequence, x, y;
    /* A plain file, not the FIFO.
       The FIFO needed a rendezvous -- a blocking O_RDONLY open on one side, a
       blocking O_WRONLY open on the other -- and delivery was unreliable in
       practice: whole runs arrived in which no command was seen at all, while
       every readiness check passed. Holding the descriptor open instead made
       it no better. The runner already writes the same command to
       touch.command and replaces it atomically, so reading that file has no
       rendezvous to miss, no buffer to drain and nothing to lose; the sequence
       number was always what distinguished a new command from a re-read. */
    int descriptor = open("/tmp/rx3emu/touch.command", O_RDONLY);
    if (descriptor < 0)
        return;
    count = read(descriptor, command, sizeof(command) - 1u);
    close(descriptor);
    if (count <= 0)
        return;
    command[count] = '\0';
    cursor = command;
    if (!emulator_parse_coordinate(&cursor, &sequence) || sequence <= 0 ||
        (unsigned int)sequence == emulator_touch_sequence)
        return;
    while (*cursor == ' ' || *cursor == '\t')
        cursor++;
    /* "<seq> k <index> [hold_ms]" presses a browse key, "<seq> <x> <y>" a
       screen point. The letter keeps the two apart without making either
       ambiguous, and an absent hold means a tap. */
    if (*cursor == 'k') {
        cursor++;
        if (!emulator_parse_coordinate(&cursor, &x))
            return;
        if (!emulator_parse_coordinate(&cursor, &y))
            y = 0;
        emulator_touch_sequence = (unsigned int)sequence;
        emulator_press_browse_key(x, y);
        return;
    }
    /* "<seq> t <x> <y>" goes through the real touch panel instead of the mod's
       own routing, so stock controls answer too. Kept as a separate verb
       rather than replacing the coordinate form: one click must not travel
       both paths and toggle a control twice. */
    /* "<seq> p <code> <deck>" presses a player key: the pad-mode selectors and
       the eight pads, which are PlayerInnards methods rather than browse-key
       table entries. */
    if (*cursor == 'p') {
        cursor++;
        if (emulator_parse_coordinate(&cursor, &x)) {
            if (!emulator_parse_coordinate(&cursor, &y))
                y = 0;
            emulator_touch_sequence = (unsigned int)sequence;
            emulator_press_player_key((unsigned int)x, (unsigned int)y);
        }
        return;
    }
    /* "<seq> r <mask>" forces a display invalidate. */
    if (*cursor == 'r') {
        cursor++;
        if (emulator_parse_coordinate(&cursor, &x)) {
            emulator_touch_sequence = (unsigned int)sequence;
            emulator_invalidate_display((unsigned int)x);
        }
        return;
    }
    if (*cursor == 't') {
        cursor++;
        if (emulator_parse_coordinate(&cursor, &x) &&
            emulator_parse_coordinate(&cursor, &y)) {
            emulator_touch_sequence = (unsigned int)sequence;
            emulator_hardware_touch(x, y);
        }
        return;
    }
    if (emulator_parse_coordinate(&cursor, &x) &&
        emulator_parse_coordinate(&cursor, &y)) {
        emulator_touch_sequence = (unsigned int)sequence;
        emulator_apply_touch(x, y);
    }
}

static void emulator_activate_initial_panel(void)
{
    /* Deliberately not gated on the pad-label template: the subtree that
       carries one only draws once BEAT FX is selected, which is what this
       function is on its way to doing. Waiting for it here deadlocks. The
       capture sits ahead of the interception instead, so the first pass after
       activation supplies the face and every pass after it is correct. */
    if (!emulator_forced_panel || emulator_panel_applied ||
        !tab_assets_ready || !text_template_ready ||
        !stock_tab_backing_ready || !beatfx_touch_areas[0])
        return;
    emulator_panel_applied = 1u;
    overlay_panel = emulator_forced_panel;
    original_set_beatfx_selected(1);
    configure_native_performance_touches(emulator_forced_panel);
    refresh_performance_ui();
    log_number("emulator activated feature panel = ",
               emulator_forced_panel);
}

static void *emulator_touch_loop(void *unused)
{
    (void)unused;
    log_line("emulator virtual touch channel ready");
    /* Stay out of the way while rbp starts.
       The FIFO this replaced blocked until a writer appeared, so the thread
       cost nothing during startup. Polling a file costs a wake-up per
       interval from the moment the library loads, and DirectFBCreate under
       QEMU is sensitive enough to that competition to fail outright -- six
       runs out of six, where the same build without this loop running early
       succeeds. Nothing can be sent before the window exists anyway. */
    usleep(8000000u);
    while (state_thread_running) {
        emulator_poll_touch();
        /* 150 ms is well inside a click's reaction time and a fraction of the
           wake-ups the 50 ms interval cost. */
        usleep(150000u);
    }
    return 0;
}
