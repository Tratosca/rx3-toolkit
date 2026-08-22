/* SPDX-License-Identifier: MPL-2.0
   Where rbp keeps the browse keys, and how it finishes one.

   Included by rx3_core_hook.c at the point this code used to sit, and only
   in the payload build. Nothing here is compiled for a deck. */
/* UiKey_KeyPush(index, encoder, release, press). rbp keeps the browse keys in
   a 230-entry table of 16-byte records -- state at +8, handler at +12 -- and
   BrowseKeyProcessing() walks it every UI cycle, calling the handler of every
   record whose state is non-zero. So marking a record is the whole of pressing
   a key: no front-panel micro, and no dependency on startUp(), which is why
   these buttons work under QEMU when the pads and the touch panel do not. */
#define UI_KEY_PUSH ((unsigned long)0x00120fc0)
/* BrowseKeyProcessing(): the pump that walks that table and calls each marked
   record's handler. It takes no arguments and finds the table itself, so it can
   be driven from here. Doing so is what made the keys dispatch at all before
   init() returned -- but see BROWSE_EVENT_FLAG below: dispatching it from this
   thread is also why the screen never followed. */
#define BROWSE_KEY_PUMP ((unsigned long)0x001210bc)
/* How rbp itself finishes a browse key, recovered from
   BrowseUiIf::InputKey (0x000cfc58):

       UiKey_KeyPush(code, ...)        -- mark the record
       if (!accepted) return 0;
       set_flg(*0x032671f4, 1);        -- wake Ui_EventTask, then return

   Ui_EventTask (0x001e79a0) blocks in wai_flg on that eventflag and, for bit 1,
   calls BrowseKeyProcessing itself -- but wrapped in the rest of the
   transaction: CheckBrowseRequestCancelCommand, a 300 ms repeat window,
   BrowseCommandCancel, and the KeyComplete/repaint that actually moves the
   screen. Calling the pump directly from the mod's poll thread runs the handler
   and skips all of that, which is exactly the symptom we measured: the key is
   accepted, ChangeBrowseMode is requested, and nothing is drawn.
   set_flg is the ITRON eventflag primitive at 0x00175bb8, signature
   int set_flg(int flgid, unsigned int setptn); the id is held in the word at
   BROWSE_EVENT_FLAG_ID, so it has to be dereferenced rather than passed. */
#define SET_FLG ((unsigned long)0x00175bb8)
#define BROWSE_EVENT_FLAG_ID ((unsigned long)0x032671f4)
#define BROWSE_EVENT_FLAG_KEY 1u
/* uiBrowse. getBrowseMode (0x001126d0) is nothing but movw/movt of this address
   followed by ldr r0,[r3], so the mode can be read straight out of memory --
   no call, and therefore no prologue to guard. Logging it either side of a
   press is the measurement that says whether the key changed anything. */
#define UI_BROWSE_MODE ((unsigned long)0x0326f8b8)
/* browseCommand, the two words ChangeBrowseMode (0x0010167c) writes: a pending
   flag and the mode being asked for. Recovered from ChangeBrowseMode_noGridOff,
   which builds the address inline as movw #0x906c / movt #0x326 and then does
   stmia r3,{r4,r5}. Note that ChangeBrowseMode returns 1 whether or not anyone
   ever acts on this, which is why its success proved nothing. */
#define BROWSE_COMMAND_PENDING ((unsigned long)0x0326906c)
/* ui::PlayerInnards::PlayerInnards. Hooked only to latch the two deck objects
   as they are built: onKey_* are methods, so injecting a key needs a real
   `this`, and under emulation no physical key ever arrives to supply one. */
#define PLAYER_INNARDS_CTOR ((unsigned long)0x00301160)
/* ui::KeyInput's vtable, plus the eight bytes of offset-to-top and RTTI that
   the Itanium ABI puts before the first entry -- an object's vptr points past
   them. A synthesised event needs this: uif::IKeyInput is an interface and the
   handlers call virtual methods on it, so a zeroed word here is a jump through
   a null pointer. That is not a guess; it is what segfaulted rbp. */
#define KEY_INPUT_VTABLE ((unsigned long)0x004e0100 + 8u)
/* Pub_GuiCom_SndDispInvalidate(uint mask): raises a display-invalidate flag per
   set bit. Under QEMU this emulator only ever draws when something forces it --
   the stock profile is a black screen for that reason, and the Performance
   screen is visible only because the mod calls REFRESH_GLYPH from outside the
   state machine. This is the general form, used to test whether a browse screen
   change is real but unpainted. */
#define GUI_DISP_INVALIDATE ((unsigned long)0x001349b8)
