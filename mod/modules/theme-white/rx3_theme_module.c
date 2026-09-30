/* SPDX-License-Identifier: MPL-2.0 */
/* Display mode. The module owns its conversion policy, the chrome decisions,
 * the SHIFT + SHORTCUT switch, the Utility row, the waveform palette and its
 * pixel arena. The core owns the tables, the fill adapter and SHIFT itself. */
#include "../core/api/rx3_module_api.h"
static const struct rx3_services *framework;
#define install_hook framework->install_hook
#define uninstall_hook framework->uninstall_hook
#define log_line framework->log_line
#define log_number framework->log_number

struct rx3_timeval { long seconds, microseconds; };
static uint64_t monotonic_enough_us(void)
{
    struct rx3_timeval value;
    if (gettimeofday(&value, 0))
        return 0;
    return (uint64_t)(unsigned long)value.seconds * 1000000u +
           (uint64_t)(unsigned long)value.microseconds;
}

#include "rx3_theme_decl.h"
#include "rx3_theme_feature.h"

/* The module's own worker: the Utility row can commit a choice without a
   redraw, the arena is allocated off the render path, and the dark remap's
   kill switch is a file. Nothing here touches a table or the display. */
static pthread_t theme_worker;
static int theme_worker_started;
static volatile int theme_worker_running;

static void *theme_watch(void *unused)
{
    (void)unused;
    while (__atomic_load_n(&theme_worker_running, __ATOMIC_SEQ_CST)) {
        usleep(50000u);
        utility_poll_theme_row();
        theme_prepare_conversion();
        if (theme_global_dark) {
            int sentinel = open(THEME_DARK_SENTINEL, O_RDONLY);
            if (sentinel >= 0) {
                close(sentinel);
                theme_global_dark = 0;
                log_line("theme: rx3-theme.off seen, global remap stopped");
            }
        }
    }
    return 0;
}

static int theme_configured(void)
{
    const char *theme = getenv("RX3_THEME");
    return theme && theme[0] != '\0';
}

static int theme_start(const struct rx3_services *services)
{
    framework = services;
    if (!services->images || !services->images->claim_variants || !services->input ||
        !services->panels || !services->memory)
        return 0;
    const char *theme = getenv("RX3_THEME");
    theme_enabled = theme && theme[0] != '\0';
    if (!theme_enabled) return 0;
    theme_read_mode(theme);
    if (!theme_feature_install()) return 0;
    __atomic_store_n(&theme_worker_running, 1, __ATOMIC_SEQ_CST);
    if (pthread_create(&theme_worker, 0, theme_watch, 0)) {
        theme_worker_running = 0;
        log_line("light theme: watcher could not start");
        return 0;
    }
    theme_worker_started = 1;
    return 1;
}

static void theme_stop(void)
{
    if (!framework) return;
    __atomic_store_n(&theme_worker_running, 0, __ATOMIC_SEQ_CST);
    if (theme_worker_started) {
        pthread_join(theme_worker, 0);
        theme_worker_started = 0;
    }
    if (framework->images && framework->input) theme_feature_remove();
    theme_enabled = 0;
}

const struct rx3_module rx3_theme_module = {
    .version = RX3_MODULE_API_VERSION, .size = sizeof(struct rx3_module),
    .name = "theme-white", .configured = theme_configured,
    .start = theme_start, .stop = theme_stop
};
