/* SPDX-License-Identifier: MPL-2.0 */
#include "../api/rx3_module_api.h"
#include "rx3_modules.h"
#include "../services/rx3_hooks.h"
#include "../services/rx3_log.h"
#include "../services/rx3_mix_state.h"
#include "../services/rx3_notice.h"
extern const struct rx3_module *const rx3_bundle[];
extern const unsigned int rx3_bundle_count;
#define RX3_MODULE_LIMIT 32u
/* Not const: the firmware writer is bound by the core at startup, so host
   builds of this unit never link the ARM instruction adapter. */
static struct rx3_services services = {
    install_hook, uninstall_hook, log_line, rx3_mix_read, &rx3_notices, &rx3_dsp, &rx3_panels, rx3_wave_read, detach_hook, release_hook, &rx3_images, &rx3_browse, &rx3_titles,
    &rx3_input, &rx3_audio, rx3_log_number, &rx3_memory, 0,
    rx3_mix_claim, rx3_mix_release, rx3_wave_claim, rx3_wave_release, &rx3_loader
};
void rx3_modules_bind_writer(int (*writer)(unsigned long, const void *, const void *, unsigned int))
{
    services.write_guarded = writer;
}
static unsigned char active[RX3_MODULE_LIMIT];
static unsigned int failures;
static unsigned int notifications_enabled, notifications_active;
/* Stop closes admission before waiting. A late entrant sees the closed gate
   and never touches a module. No waiting occurs on the callback threads. */
static int enter_notification(void)
{
    __atomic_add_fetch(&notifications_active,1u,__ATOMIC_SEQ_CST);
    if (__atomic_load_n(&notifications_enabled,__ATOMIC_SEQ_CST)) return 1;
    __atomic_sub_fetch(&notifications_active,1u,__ATOMIC_SEQ_CST);
    return 0;
}
static void leave_notification(void)
{
    __atomic_sub_fetch(&notifications_active,1u,__ATOMIC_SEQ_CST);
}
unsigned int rx3_modules_failures(void) { return failures; }
unsigned int rx3_modules_start(void)
{
    failures = 0;
    if (rx3_bundle_count > RX3_MODULE_LIMIT) { failures = 1; return 0; }
    unsigned int count = 0;
    for (unsigned int i = 0; i < rx3_bundle_count; i++) {
        const struct rx3_module *module = rx3_bundle[i];
        if (active[i]) { count++; continue; }
        if (module->version != RX3_MODULE_API_VERSION ||
            module->size != sizeof(*module) || !module->start || !module->stop) {
            failures++;
            log_line("module refused: incompatible descriptor");
            continue;
        }
        if (module->configured && !module->configured()) continue;
        log_line("module configured:");
        log_line(module->name);
        if (!module->start(&services)) {
            failures++;
            module->stop();
            log_line("module refused: partial installation removed");
            log_line(module->name);
            continue;
        }
        active[i] = 1;
        log_line("module active:");
        log_line(module->name);
        count++;
    }
    __atomic_store_n(&notifications_enabled,1u,__ATOMIC_SEQ_CST);
    return count;
}
void rx3_modules_stop(void)
{
    __atomic_store_n(&notifications_enabled,0u,__ATOMIC_SEQ_CST);
    while (__atomic_load_n(&notifications_active,__ATOMIC_SEQ_CST)) usleep(1000u);
    if (rx3_bundle_count > RX3_MODULE_LIMIT) return;
    for (unsigned int i = rx3_bundle_count; i > 0; i--) {
        if (!active[i - 1]) continue;
        rx3_bundle[i - 1]->stop();
        active[i - 1] = 0;
    }
}

void rx3_modules_track_will_load(unsigned int deck, void *reader, const void *info)
{
    if (!enter_notification()) return;
    for (unsigned int i = 0; i < rx3_bundle_count; i++)
        if (active[i] && rx3_bundle[i]->track_will_load)
            rx3_bundle[i]->track_will_load(deck, reader, info);
    leave_notification();
}

void rx3_modules_track_did_load(unsigned int deck, void *reader, const void *info)
{
    if (!enter_notification()) return;
    for (unsigned int i = 0; i < rx3_bundle_count; i++)
        if (active[i] && rx3_bundle[i]->track_did_load)
            rx3_bundle[i]->track_did_load(deck, reader, info);
    leave_notification();
}

void rx3_modules_audio_started(unsigned int rate)
{
    if (!enter_notification()) return;
    for (unsigned int i=0; i<rx3_bundle_count; i++)
        if (active[i] && rx3_bundle[i]->audio_started)
            rx3_bundle[i]->audio_started(rate);
    leave_notification();
}
void rx3_modules_text_observed(const struct rx3_text_observation *text)
{
    if (!enter_notification()) return;
    for (unsigned int i=0; i<rx3_bundle_count; i++)
        if (active[i] && rx3_bundle[i]->text_observed)
            rx3_bundle[i]->text_observed(text);
    leave_notification();
}
void rx3_modules_report(void)
{
    if (!enter_notification()) return;
    for (unsigned int i=0; i<rx3_bundle_count; i++)
        if (active[i] && rx3_bundle[i]->report) rx3_bundle[i]->report();
    leave_notification();
}

int rx3_modules_uses_audio(void)
{
    if (rx3_bundle_count > RX3_MODULE_LIMIT) return 0;
    for (unsigned int i=0; i<rx3_bundle_count; i++)
        if (active[i] && rx3_bundle[i]->audio_started) return 1;
    return 0;
}
