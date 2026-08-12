// SPDX-License-Identifier: MPL-2.0
/*
 * Asynchronous two-deck vocal stem hook for XDJ-RX3 firmware 1.19.
 *
 * The hook associates a basename-matched sidecar in PcmReader::load and
 * applies the selected component state in PcmReader::getStreamAt. Pad 7 and
 * pad 8 are independent instrumental and vocal toggles in Slip Loop mode.
 * Without a valid sidecar, audio and pad events follow the stock path.
 *
 * Both pads blink while a sidecar is being read and hold their colour once it
 * is resident, so the operator can see when the toggles become effective.
 *
 * Stems are copied into anonymous RAM before publication to the audio
 * thread. Removing the USB drive after a completed load therefore leaves no
 * active file mapping. int16 and float32 payloads are supported.
 *
 * PcmReader operates at 44,100 frames per second. ReaderImpl converts source
 * files before this buffer, so the sidecar frame index remains in the same
 * time domain for 44.1, 48, and 96 kHz input files.
 *
 * Instrumental output is full mix minus vocal. Both signals must originate
 * from the same decode path to preserve phase, delay, and gain alignment.
 */

#define GET_STREAM_AT ((unsigned long)0x0003d1e0)
#define PCM_LOAD      ((unsigned long)0x00038ff0)
#define ON_KEY_PAD    ((unsigned long)0x003060e8)
#define CHECK_SLIP_LED ((unsigned long)0x002fcc04)
#define SET_LED_COLOR  ((unsigned long)0x0033e4f8)
#define SET_LED_STATE  ((unsigned long)0x0033e3f4)

#define LOG_FILE  "/tmp/rx3-stems.log"

#define TRANSITION_FRAMES 256u

/* uif::Led::State, and the half-period of the loading indication. */
#define LED_OFF   0
#define LED_ON    1
#define LED_BLINK 2
#define BLINK_PERIOD_MS 50u

/* Reject a stem above this fraction of estimated available RAM. */
#define MEM_NUMERATOR   3
#define MEM_DENOMINATOR 5

/* Types and libc declarations. */

typedef unsigned int   size_t;
typedef int            ssize_t;
typedef long           off_t;
typedef unsigned char  uint8_t;
typedef unsigned short uint16_t;
typedef short          int16_t;
typedef unsigned int   uint32_t;
typedef unsigned long long uint64_t;
typedef unsigned long pthread_t;

extern int      open(const char *, int, ...);
extern ssize_t  read(int, void *, size_t);
extern ssize_t  write(int, const void *, size_t);
extern int      close(int);
extern off_t    lseek(int, off_t, int);
extern void    *mmap(void *, size_t, int, int, int, off_t);
extern int      munmap(void *, size_t);
extern int      mprotect(void *, size_t, int);
extern long     sysconf(int);
extern void    *memcpy(void *, const void *, size_t);
extern void    *memset(void *, int, size_t);
extern int      memcmp(const void *, const void *, size_t);
extern char    *getenv(const char *);
extern int      pthread_create(pthread_t *, const void *, void *(*)(void *), void *);
extern int      pthread_detach(pthread_t);

#define O_RDONLY 0
#define O_WRONLY 1
#define O_CREAT  0100
#define O_TRUNC  01000
#define O_APPEND 02000
#define SEEK_SET 0
#define SEEK_END 2
#define PROT_READ  1
#define PROT_WRITE 2
#define PROT_EXEC  4
#define MAP_PRIVATE   2
#define MAP_ANONYMOUS 0x20
#define MAP_FAILED ((void *)-1)
#define _SC_PAGESIZE 30

/* Data model. */

typedef struct { float left, right; } Float2;
typedef struct { int16_t left, right; } Short2;

typedef unsigned long (*get_stream_fn)(void *, unsigned long, Float2 *, unsigned long);
typedef int (*load_fn)(void *, const void *);
typedef int (*on_key_pad_fn)(void *, const void *);
typedef void (*check_slip_led_fn)(void *, void *);
typedef void (*set_led_color_fn)(void *, int, int, const void *);
/* uif::Led::setState(State, period_ms, started_at_ms, long, BrightnessState).
   With State 2 the panel runs the blink itself, so the rate of the LED refresh
   this hook rides on does not affect the cadence. */
typedef void (*set_led_state_fn)(void *, int, unsigned int, unsigned int, long, int);

enum stem_mode {
    MODE_NONE = 0,
    MODE_INSTRUMENTAL = 1,
    MODE_VOCAL = 2,
    MODE_BOTH = MODE_INSTRUMENTAL | MODE_VOCAL
};

enum sidecar_format { FORMAT_F32 = 1, FORMAT_S16 = 2 };

struct __attribute__((packed)) sidecar_header {
    char     magic[8];
    uint32_t sample_rate;
    uint32_t channels;
    uint32_t format;
    uint32_t header_size;
    uint64_t frames;
    uint8_t  reserved[32];
};

/* Expected prologues, checked before writing executable code. */
static const uint8_t get_stream_guard[8] = {
    0x9c, 0xc0, 0xd0, 0xe5, 0xf0, 0x45, 0x2d, 0xe9
};
static const uint8_t load_guard[8] = {
    0xf0, 0x4f, 0x2d, 0xe9, 0x5c, 0xd0, 0x4d, 0xe2
};
static const uint8_t pad_guard[8] = {
    0xb8, 0x30, 0xd1, 0xe1, 0xf0, 0x4f, 0x2d, 0xe9
};
/* This prologue contains a PC-relative ldr and requires literal relocation. */
static const uint8_t slip_led_guard[8] = {
    0xb4, 0x3d, 0x9f, 0xe5, 0xf0, 0x4f, 0x2d, 0xe9
};
static get_stream_fn original_get_stream;
static load_fn       original_load;
static on_key_pad_fn original_on_key_pad;
static check_slip_led_fn original_check_slip_led;

struct stem_payload {
    const void *data;
    uint32_t format;
    uint64_t frames;
    void *block;
    size_t block_size;
};

struct deck_context {
    volatile void *reader;
    volatile enum stem_mode mode;
    volatile uint32_t generation;
    volatile int armed;
    enum stem_mode rendered_mode;
    enum stem_mode transition_from;
    enum stem_mode transition_to;
    unsigned int transition_cursor;
    struct stem_payload vocal;
};

static struct deck_context decks[2];
static volatile unsigned int captured_pad_mask[2];
static const char *stems_dir;

struct load_request {
    struct deck_context *context;
    void *reader;
    uint32_t generation;
    char path[1024];
};

struct installed_hook {
    unsigned long address;
    uint8_t       original[8];
    void         *trampoline;
};

static struct installed_hook get_stream_hook;
static struct installed_hook load_hook;
static struct installed_hook pad_hook;
static struct installed_hook slip_led_hook;
/* Logging. */

static size_t str_length(const char *s)
{
    size_t n = 0;
    while (s[n])
        n++;
    return n;
}

static void log_line(const char *message)
{
    int fd = open(LOG_FILE, O_WRONLY | O_CREAT | O_APPEND, 0600);
    if (fd < 0)
        return;
    (void)write(fd, message, str_length(message));
    (void)write(fd, "\n", 1);
    close(fd);
}

static void log_number(const char *label, unsigned long value)
{
    char buffer[96];
    size_t n = 0;
    while (label[n] && n < sizeof(buffer) - 24) {
        buffer[n] = label[n];
        n++;
    }
    char digits[24];
    int d = 0;
    if (!value) {
        digits[d++] = '0';
    } else {
        while (value && d < (int)sizeof(digits)) {
            digits[d++] = (char)('0' + (value % 10u));
            value /= 10u;
        }
    }
    while (d > 0)
        buffer[n++] = digits[--d];
    buffer[n] = '\0';
    log_line(buffer);
}

/* Sidecar loading. */

/* Estimate immediately available or reclaimable RAM in KiB. */
static unsigned long meminfo_value(const char *buffer, ssize_t count,
                                   const char *key)
{
    size_t key_length = str_length(key);
    for (ssize_t i = 0; i + (ssize_t)key_length < count; i++) {
        if (memcmp(buffer + i, key, key_length))
            continue;
        ssize_t j = i + (ssize_t)key_length;
        while (j < count && (buffer[j] == ' ' || buffer[j] == '\t'))
            j++;
        unsigned long value = 0;
        while (j < count && buffer[j] >= '0' && buffer[j] <= '9')
            value = value * 10u + (unsigned long)(buffer[j++] - '0');
        return value;
    }
    return 0;
}

static unsigned long memory_available_kb(void)
{
    char buffer[2048];
    int fd = open("/proc/meminfo", O_RDONLY);
    if (fd < 0)
        return 0;
    ssize_t count = read(fd, buffer, sizeof(buffer) - 1);
    close(fd);
    if (count <= 0)
        return 0;
    buffer[count] = '\0';

    /* Linux 3.0.101 has no MemAvailable field. Fall back to a conservative
       estimate from free, buffer, and cache pages. */
    unsigned long available = meminfo_value(buffer, count, "MemAvailable:");
    if (available)
        return available;
    return meminfo_value(buffer, count, "MemFree:") +
           meminfo_value(buffer, count, "Buffers:") +
           meminfo_value(buffer, count, "Cached:");
}

static int read_exactly(int fd, void *destination, size_t length)
{
    uint8_t *cursor = destination;
    while (length) {
        ssize_t got = read(fd, cursor, length > 0x100000u ? 0x100000u : length);
        if (got <= 0)
            return -1;
        cursor += got;
        length -= (size_t)got;
    }
    return 0;
}

static void release_payload(struct stem_payload *payload)
{
    if (payload->block)
        munmap(payload->block, payload->block_size);
    memset(payload, 0, sizeof(*payload));
}

static int load_sidecar(const char *path, struct stem_payload *destination)
{
    memset(destination, 0, sizeof(*destination));
    int fd = open(path, O_RDONLY);
    if (fd < 0) {
        log_line("rejected: sidecar is not readable");
        return -1;
    }

    off_t size = lseek(fd, 0, SEEK_END);
    if (size < (off_t)sizeof(struct sidecar_header) || lseek(fd, 0, SEEK_SET) != 0) {
        close(fd);
        log_line("rejected: sidecar is truncated");
        return -1;
    }

    struct sidecar_header header;
    if (read_exactly(fd, &header, sizeof(header))) {
        close(fd);
        log_line("rejected: sidecar header is unreadable");
        return -1;
    }

    unsigned int frame_size;
    if (header.format == FORMAT_F32)
        frame_size = sizeof(Float2);
    else if (header.format == FORMAT_S16)
        frame_size = sizeof(Short2);
    else {
        close(fd);
        log_line("rejected: unknown format (1=float32, 2=int16)");
        return -1;
    }

    /* PcmReader uses a fixed 44,100 Hz internal time domain. */
    if (memcmp(header.magic, "RX3STM1", 7) || header.sample_rate != 44100 ||
        header.channels != 2 || header.header_size != sizeof(header) ||
        header.frames == 0 || header.frames > (0xffffffffu - sizeof(header)) / frame_size ||
        (uint64_t)header.header_size + header.frames * frame_size != (uint64_t)size) {
        close(fd);
        log_line("rejected: inconsistent sidecar header");
        return -1;
    }

    size_t payload = (size_t)(header.frames * frame_size);

    unsigned long available_kb = memory_available_kb();
    if (available_kb) {
        unsigned long needed_kb = (unsigned long)(payload >> 10);
        if (needed_kb > available_kb / MEM_DENOMINATOR * MEM_NUMERATOR) {
            close(fd);
            log_number("rejected: sidecar KiB required = ", needed_kb);
            log_number("          estimated KiB available = ", available_kb);
            return -1;
        }
    }

    void *block = mmap(0, payload, PROT_READ | PROT_WRITE,
                       MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (block == MAP_FAILED) {
        close(fd);
        log_line("rejected: anonymous RAM allocation failed");
        return -1;
    }

    if (read_exactly(fd, block, payload)) {
        munmap(block, payload);
        close(fd);
        log_line("rejected: incomplete sidecar read");
        return -1;
    }
    close(fd);

    /* Make the completed payload read-only. An accidental audio-thread write
       then fails explicitly instead of silently corrupting samples. */
    (void)mprotect(block, payload, PROT_READ);

    destination->block      = block;
    destination->block_size = payload;
    destination->data       = block;
    destination->format     = header.format;
    destination->frames     = header.frames;

    log_number("sidecar resident frames = ", (unsigned long)header.frames);
    log_number("sidecar resident KiB = ", (unsigned long)(payload >> 10));
    log_number("sidecar format = ", (unsigned long)header.format);
    return 0;
}

static int path_in_stems(const char *filename, size_t filename_length,
                         char *output, size_t capacity)
{
    size_t n = 0;
    while (stems_dir[n] && n + 1u < capacity) {
        output[n] = stems_dir[n];
        n++;
    }
    if (stems_dir[n] || n + 2u + filename_length > capacity)
        return -1;
    if (n && output[n - 1u] != '/')
        output[n++] = '/';
    for (size_t i = 0; i < filename_length; i++)
        output[n++] = filename[i];
    output[n] = '\0';
    return 0;
}

/* StTrackInfo starts with an inline NUL-terminated path. ReaderImpl::loadFile
   passes it directly to endsWithIgnoreCase, which calls strlen(r0), and then
   to createSourceInputStream. Derive only the basename:
     /USB/Artist - Title.aiff -> $RX3_STEMS_DIR/Artist - Title.rx3stem */
static int sidecar_path_for_track(const void *track_info, char *output,
                                  size_t capacity)
{
    const char *track_path = (const char *)track_info;
    if (!track_path || !track_path[0] || !stems_dir || capacity < 16u)
        return -1;

    const char *base = track_path;
    const char *dot = 0;
    for (const char *p = track_path; *p; p++) {
        if (*p == '/' || *p == '\\') {
            base = p + 1;
            dot = 0;
        } else if (*p == '.') {
            dot = p;
        }
    }
    if (!base[0])
        return -1;
    const char *name_end = base + str_length(base);
    const char *end = dot && dot > base ? dot : name_end;
    char filename[768];
    size_t n = 0;
    while (base < end && n + 1u < sizeof(filename))
        filename[n++] = *base++;
    static const char suffix[] = ".rx3stem";
    for (size_t i = 0; i < sizeof(suffix); i++) {
        if (n + i >= sizeof(filename))
            return -1;
        filename[n + i] = suffix[i];
    }
    return path_in_stems(filename, n + sizeof(suffix) - 1u, output, capacity);
}

static int sidecar_is_readable(const char *path)
{
    int fd = open(path, O_RDONLY);
    if (fd < 0)
        return 0;
    close(fd);
    return 1;
}

static void *sidecar_loader(void *opaque)
{
    struct load_request *request = opaque;
    struct stem_payload next;
    int loaded = !load_sidecar(request->path, &next);
    struct deck_context *context = request->context;

    if (loaded && context->generation == request->generation &&
        context->reader == request->reader) {
        /* Temporarily remove the reader from the lookup table while publishing
           the payload. getStreamAt remains on the stock path until complete. */
        context->reader = 0;
        __sync_synchronize();
        release_payload(&context->vocal);
        context->vocal = next;
        __sync_synchronize();
        context->reader = request->reader;
        log_number("asynchronous sidecar ready on deck = ",
                   (unsigned long)(context - decks) + 1u);
    } else {
        if (loaded)
            release_payload(&next);
        if (!loaded && context->generation == request->generation &&
            context->reader == request->reader)
            context->armed = 0;
        if (context->generation != request->generation)
            log_line("asynchronous sidecar discarded: track was replaced");
    }
    munmap(request, 4096u);
    return 0;
}

/* Hook installation. */

static void clear_instruction_cache(unsigned long first, unsigned long last)
{
    register unsigned long r0 __asm__("r0") = first;
    register unsigned long r1 __asm__("r1") = last;
    register unsigned long r2 __asm__("r2") = 0;
    register unsigned long r7 __asm__("r7") = 0x0f0002u; /* __ARM_NR_cacheflush */
    __asm__ volatile("svc 0" : "+r"(r0) : "r"(r1), "r"(r2), "r"(r7) : "memory");
}

static int write_code(unsigned long address, const void *bytes, size_t length)
{
    long page_size = sysconf(_SC_PAGESIZE);
    if (page_size <= 0)
        page_size = 4096;
    unsigned long mask  = (unsigned long)page_size - 1u;
    unsigned long first = address & ~mask;
    unsigned long last  = (address + length - 1u) & ~mask;
    size_t span = (size_t)(last - first) + (size_t)page_size;

    if (mprotect((void *)first, span, PROT_READ | PROT_WRITE))
        return -1;
    memcpy((void *)address, bytes, length);
    clear_instruction_cache(address, address + length);
    if (mprotect((void *)first, span, PROT_READ | PROT_EXEC))
        return -1;
    return 0;
}

static void uninstall_hook(struct installed_hook *hook)
{
    if (!hook->address)
        return;
    (void)write_code(hook->address, hook->original, sizeof(hook->original));
    if (hook->trampoline)
        munmap(hook->trampoline, 4096);
    memset(hook, 0, sizeof(*hook));
}

/*
 * Copy the first eight bytes into a trampoline and append an absolute jump to
 * address+8. These stolen instructions have no PC-relative dependency:
 *   getStreamAt : ldrb r12,[r0,#0x9c] ; stmdb sp!,{r4..r8,r10,lr}
 *   load        : stmdb sp!,{r4..r11,lr} ; sub sp,sp,#0x5c
 *   onKey_Pad   : ldrh r3,[r1,#8] ; stmdb sp!,{r4..r11,lr}
 */
static void *install_hook(struct installed_hook *hook, unsigned long address,
                          const uint8_t guard[8], void *replacement)
{
    if (memcmp((const void *)address, guard, 8))
        return 0;

    uint32_t *trampoline = mmap(0, 4096, PROT_READ | PROT_WRITE,
                                MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (trampoline == MAP_FAILED)
        return 0;
    memcpy(trampoline, (const void *)address, 8);
    trampoline[2] = 0xe51ff004;                      /* ldr pc,[pc,#-4] */
    trampoline[3] = (uint32_t)(address + 8);
    clear_instruction_cache((unsigned long)trampoline,
                            (unsigned long)trampoline + 16u);
    if (mprotect(trampoline, 4096, PROT_READ | PROT_EXEC)) {
        munmap(trampoline, 4096);
        return 0;
    }

    uint32_t patch[2] = {0xe51ff004, (uint32_t)(unsigned long)replacement};
    if (write_code(address, patch, sizeof(patch))) {
        munmap(trampoline, 4096);
        return 0;
    }

    hook->address = address;
    memcpy(hook->original, guard, sizeof(hook->original));
    hook->trampoline = trampoline;
    return trampoline;
}

/* Variant for ldr r3,[pc,#imm12] followed by push. The trampoline loads a copy
   of the original literal value, replays push, and joins address+8. This
   preserves r3 without depending on the shared object's mapped address. */
static void *install_pc_ldr_hook(struct installed_hook *hook,
                                 unsigned long address,
                                 const uint8_t guard[8], void *replacement)
{
    if (memcmp((const void *)address, guard, 8))
        return 0;

    uint32_t instruction = *(const uint32_t *)address;
    if ((instruction & 0xfffff000u) != 0xe59f3000u)
        return 0;
    unsigned long literal_address = address + 8u + (instruction & 0xfffu);
    uint32_t literal_value = *(const uint32_t *)literal_address;

    uint32_t *trampoline = mmap(0, 4096, PROT_READ | PROT_WRITE,
                                MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (trampoline == MAP_FAILED)
        return 0;
    trampoline[0] = 0xe59f3008u;                    /* ldr r3,[pc,#8] */
    trampoline[1] = *(const uint32_t *)(address + 4u); /* push original */
    trampoline[2] = 0xe51ff004u;                    /* ldr pc,[pc,#-4] */
    trampoline[3] = (uint32_t)(address + 8u);
    trampoline[4] = literal_value;
    clear_instruction_cache((unsigned long)trampoline,
                            (unsigned long)trampoline + 20u);
    if (mprotect(trampoline, 4096, PROT_READ | PROT_EXEC)) {
        munmap(trampoline, 4096);
        return 0;
    }

    uint32_t patch[2] = {0xe51ff004u, (uint32_t)(unsigned long)replacement};
    if (write_code(address, patch, sizeof(patch))) {
        munmap(trampoline, 4096);
        return 0;
    }

    hook->address = address;
    memcpy(hook->original, guard, sizeof(hook->original));
    hook->trampoline = trampoline;
    return trampoline;
}

/* Audio mixing. */

static struct deck_context *context_for_reader(const void *reader)
{
    for (unsigned int i = 0; i < 2u; i++)
        if (decks[i].reader == reader)
            return &decks[i];
    return 0;
}

static struct deck_context *context_for_player(const void *player)
{
    unsigned int player_no = *(const uint8_t *)((const uint8_t *)player + 0x26u);
    if (player_no < 1u || player_no > 2u)
        return 0;
    return &decks[player_no - 1u];
}

static Float2 vocal_at(const struct deck_context *context, unsigned long index)
{
    Float2 sample;
    if (context->vocal.format == FORMAT_S16) {
        const Short2 *source = (const Short2 *)context->vocal.data + index;
        sample.left  = (float)source->left  * (1.0f / 32768.0f);
        sample.right = (float)source->right * (1.0f / 32768.0f);
    } else {
        sample = ((const Float2 *)context->vocal.data)[index];
    }
    return sample;
}

static Float2 sample_for_mode(Float2 full, Float2 vocal, enum stem_mode selected)
{
    if (selected == MODE_NONE) {
        Float2 silence = {0.0f, 0.0f};
        return silence;
    }
    if (selected == MODE_VOCAL)
        return vocal;
    if (selected == MODE_INSTRUMENTAL) {
        Float2 instrumental = {full.left - vocal.left, full.right - vocal.right};
        return instrumental;
    }
    return full;
}

/* An all-zero block represents an unbuffered region filled by getStreamAt.
   Leave it unchanged. */
static int block_is_silent(const Float2 *output, unsigned long frames)
{
    for (unsigned long i = 0; i < frames; i++)
        if (output[i].left != 0.0f || output[i].right != 0.0f)
            return 0;
    return 1;
}

static void apply_mix(struct deck_context *context, unsigned long position,
                      Float2 *output, unsigned long frames,
                      enum stem_mode selected)
{
    if (selected != context->transition_to) {
        context->transition_from   = context->rendered_mode;
        context->transition_to     = selected;
        context->transition_cursor = 0;
    }

    if (context->transition_cursor >= TRANSITION_FRAMES) {
        context->rendered_mode = selected;
        if (selected == MODE_BOTH)
            return;
        for (unsigned long i = 0; i < frames; i++) {
            if (output[i].left == 0.0f && output[i].right == 0.0f)
                continue;
            output[i] = sample_for_mode(output[i], vocal_at(context, position + i), selected);
        }
        return;
    }

    for (unsigned long i = 0; i < frames; i++) {
        Float2 full  = output[i];
        /* A call may be partially zero-filled. Never turn a stock zero frame
           into vocal audio or inverted vocal audio. */
        if (full.left == 0.0f && full.right == 0.0f)
            continue;
        Float2 vocal = vocal_at(context, position + i);
        Float2 destination = sample_for_mode(full, vocal, context->transition_to);
        if (context->transition_cursor < TRANSITION_FRAMES) {
            Float2 source = sample_for_mode(full, vocal, context->transition_from);
            float alpha = (float)(context->transition_cursor + 1u) / (float)TRANSITION_FRAMES;
            output[i].left  = source.left  + (destination.left  - source.left)  * alpha;
            output[i].right = source.right + (destination.right - source.right) * alpha;
            context->transition_cursor++;
            if (context->transition_cursor == TRANSITION_FRAMES)
                context->rendered_mode = context->transition_to;
        } else {
            output[i] = destination;
        }
    }
}

/* Hook replacements. */

static unsigned long hooked_get_stream(void *reader, unsigned long position,
                                       Float2 *output, unsigned long frames)
{
    unsigned long result = original_get_stream(reader, position, output, frames);

    struct deck_context *context = context_for_reader(reader);
    if (!context || !context->vocal.data)
        return result;
    if ((uint64_t)position + frames > context->vocal.frames)
        return result;

    enum stem_mode selected = context->mode;
    if (selected == MODE_BOTH && context->transition_cursor >= TRANSITION_FRAMES &&
        context->rendered_mode == MODE_BOTH)
        return result;
    if (block_is_silent(output, frames))
        return result;

    apply_mix(context, position, output, frames, selected);
    return result;
}

static int hooked_load(void *reader, const void *track_info)
{
    unsigned int channel = *(const uint32_t *)((const uint8_t *)reader + 0x20u);
    struct deck_context *context = channel < 2u ? &decks[channel] : 0;
    char path[1024];
    int has_sidecar = context &&
                      !sidecar_path_for_track(track_info, path, sizeof(path)) &&
                      sidecar_is_readable(path);

    /* Detach before original_load. The old audio thread may continue but no
       longer sees the stem. Its payload remains allocated until stock load
       stops that thread synchronously, preventing use-after-munmap. */
    if (context)
        context->reader = 0;
    int result = original_load(reader, track_info);
    if (!context) {
        log_number("sidecar ignored: unknown PcmReader channel = ", channel);
        return result;
    }

    context->generation++;
    context->armed = has_sidecar;
    release_payload(&context->vocal);
    context->mode = MODE_BOTH;
    context->rendered_mode = MODE_BOTH;
    context->transition_from = MODE_BOTH;
    context->transition_to = MODE_BOTH;
    context->transition_cursor = TRANSITION_FRAMES;
    __sync_synchronize();
    context->reader = reader;

    if (has_sidecar) {
        struct load_request *request = mmap(0, 4096u, PROT_READ | PROT_WRITE,
                                            MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        if (request != MAP_FAILED) {
            request->context = context;
            request->reader = reader;
            request->generation = context->generation;
            size_t path_length = str_length(path) + 1u;
            memcpy(request->path, path, path_length);
            pthread_t thread;
            if (!pthread_create(&thread, 0, sidecar_loader, request)) {
                pthread_detach(thread);
                log_number("asynchronous sidecar load started, deck = ", channel + 1u);
            } else {
                munmap(request, 4096u);
                log_line("sidecar disabled: loader thread creation failed");
            }
        } else {
            log_line("sidecar disabled: request allocation failed");
        }
    }
    return result;
}

static int hooked_on_key_pad(void *player_innards, const void *key_input)
{
    const uint8_t *event = (const uint8_t *)key_input;
    uint16_t key_code = (uint16_t)event[8] | ((uint16_t)event[9] << 8);
    unsigned int operation = event[11] & 0x0fu;

    /* Pads 7 and 8 use key codes 0x411d and 0x411e. */
    if (key_code < 0x411du || key_code > 0x411eu)
        return original_on_key_pad(player_innards, key_input);

    unsigned int bit = 1u << (key_code - 0x411du);
    unsigned int object_channel = *(const uint8_t *)((const uint8_t *)player_innards + 0x26u);
    unsigned int event_channel = event[10];
    unsigned int ui_channel = event_channel >= 1u && event_channel <= 2u
                            ? event_channel : object_channel;
    if (event_channel >= 1u && event_channel <= 2u &&
        object_channel != event_channel) {
        log_number("pad object/event channel mismatch, object = ", object_channel);
        log_number("pad uses event channel = ", event_channel);
    }
    struct deck_context *context = ui_channel >= 1u && ui_channel <= 2u
                                 ? &decks[ui_channel - 1u] : 0;
    unsigned int deck = context ? (unsigned int)(context - decks) : 0u;

    /* onKey_SlipBeatLoop writes 2 at PlayerInnards+0x74. onKey_Pad uses this
       value as its path selector. event[10] can contain UI channel 0 rather
       than the deck enum expected by UiGetPadModeSlipLoopFlg. */
    int slip_loop = *(const uint32_t *)((const uint8_t *)player_innards + 0x74u) == 2u;

    /* Operation 0 is press. Consume a captured gesture through release even
       when pad mode changes between the two events. */
    if (operation == 0u && slip_loop && context && context->reader &&
        context->armed) {
        captured_pad_mask[deck] |= bit;
        enum stem_mode selected = context->mode;
        if (key_code == 0x411du)
            selected = (enum stem_mode)(selected ^ MODE_INSTRUMENTAL);
        else
            selected = (enum stem_mode)(selected ^ MODE_VOCAL);
        context->mode = selected;
        if (selected == MODE_VOCAL)
            log_line("SLIP LOOP PAD 8 : vocal");
        else if (selected == MODE_INSTRUMENTAL)
            log_line("SLIP LOOP PAD 7 : instrumental");
        else if (selected == MODE_NONE)
            log_line("SLIP LOOP : mute");
        else
            log_line("SLIP LOOP : both");
        return 1;
    }

    if (context && (captured_pad_mask[deck] & bit)) {
        /* Operations 2 and 3 are the release variants used by the stock Hot
           Cue path, including release after a long press. */
        if (operation == 2u || operation == 3u)
            captured_pad_mask[deck] &= ~bit;
        return 1;
    }

    return original_on_key_pad(player_innards, key_input);
}

struct rgb { uint8_t red, green, blue; };

/* checkSlipBeatLoopLedState has already populated LedStat. The list contains
   both decks. Each 44-byte uif::Led stores its ID at +0 and channel at +4.
   Filtering both fields prevents one deck from changing the other deck's
   visual state. Other pad modes remain on the stock path. */
static void hooked_check_slip_led(void *player, void *led_stat)
{
    static const struct rgb instrumental_rgb = {255u, 0u, 0u};
    static const struct rgb vocal_rgb        = {0u, 255u, 0u};

    original_check_slip_led(player, led_stat);

    struct deck_context *context = context_for_player(player);
    if (!context || !context->reader || !context->armed)
        return;

    uint16_t count = *(const uint16_t *)((const uint8_t *)led_stat + 4u);
    uint8_t *entries = *(uint8_t **)((uint8_t *)led_stat + 8u);
    if (!entries || count > 256u)
        return;

    /* Armed but not yet resident: the sidecar is still being read. Both pads
       blink until the payload is published, then they hold the selection. */
    int loading = !context->vocal.data;
    /* LedStat+0 is the millisecond stamp the manager wrote for this refresh. */
    uint32_t now = *(const uint32_t *)led_stat;

    enum stem_mode selected = context->mode;
    int instrumental_on = (selected & MODE_INSTRUMENTAL) != 0;
    int vocal_on = (selected & MODE_VOCAL) != 0;
    uint32_t deck_channel = (uint32_t)(context - decks) + 1u;

    for (uint16_t i = 0; i < count; i++) {
        uint8_t *led = entries + (size_t)i * 44u;
        uint32_t id = *(const uint32_t *)led;
        uint32_t channel = *(const uint32_t *)(led + 4u);
        if (channel != deck_channel)
            continue;
        const struct rgb *colour;
        int lit;
        if (id == 24u) {
            colour = &instrumental_rgb;
            lit = instrumental_on;
        } else if (id == 25u) {
            colour = &vocal_rgb;
            lit = vocal_on;
        } else {
            continue;
        }
        if (loading) {
            /* setState leaves a blink that already runs at this period alone,
               so the two pads stay in step from one refresh to the next. */
            ((set_led_state_fn)SET_LED_STATE)(led, LED_BLINK, BLINK_PERIOD_MS,
                                              now, 0, 0);
            ((set_led_color_fn)SET_LED_COLOR)(led, LED_BLINK, 0, colour);
        } else {
            ((set_led_color_fn)SET_LED_COLOR)(led, LED_ON, lit ? 0 : 1, colour);
        }
    }
}

/* Lifecycle. */

__attribute__((constructor)) static void initialize(void)
{
    stems_dir = getenv("RX3_STEMS_DIR");
    if (!stems_dir || !stems_dir[0])
        return;

    for (unsigned int i = 0; i < 2u; i++) {
        decks[i].mode = MODE_BOTH;
        decks[i].rendered_mode = MODE_BOTH;
        decks[i].transition_from = MODE_BOTH;
        decks[i].transition_to = MODE_BOTH;
        decks[i].transition_cursor = TRANSITION_FRAMES;
    }

    original_get_stream = (get_stream_fn)install_hook(
        &get_stream_hook, GET_STREAM_AT, get_stream_guard, (void *)hooked_get_stream);
    if (!original_get_stream) {
        log_line("rejected: unexpected PcmReader::getStreamAt prologue");
        return;
    }

    original_load = (load_fn)install_hook(
        &load_hook, PCM_LOAD, load_guard, (void *)hooked_load);
    if (!original_load) {
        uninstall_hook(&get_stream_hook);
        original_get_stream = 0;
        log_line("rejected: unexpected PcmReader::load prologue; first hook removed");
        return;
    }

    original_on_key_pad = (on_key_pad_fn)install_hook(
        &pad_hook, ON_KEY_PAD, pad_guard, (void *)hooked_on_key_pad);
    if (!original_on_key_pad) {
        uninstall_hook(&load_hook);
        uninstall_hook(&get_stream_hook);
        original_load = 0;
        original_get_stream = 0;
        log_line("rejected: unexpected PlayerInnards::onKey_Pad prologue; hooks removed");
        return;
    }

    original_check_slip_led = (check_slip_led_fn)install_pc_ldr_hook(
        &slip_led_hook, CHECK_SLIP_LED, slip_led_guard,
        (void *)hooked_check_slip_led);
    if (!original_check_slip_led) {
        uninstall_hook(&pad_hook);
        uninstall_hook(&load_hook);
        uninstall_hook(&get_stream_hook);
        original_on_key_pad = 0;
        original_load = 0;
        original_get_stream = 0;
        log_line("rejected: unexpected Slip Loop LED prologue; hooks removed");
        return;
    }

    log_line("RX3 stems hook active; asynchronous loading and deck-filtered LEDs");
}

__attribute__((destructor)) static void finalize(void)
{
    uninstall_hook(&slip_led_hook);
    uninstall_hook(&pad_hook);
    uninstall_hook(&load_hook);
    uninstall_hook(&get_stream_hook);
    for (unsigned int i = 0; i < 2u; i++)
        release_payload(&decks[i].vocal);
}
