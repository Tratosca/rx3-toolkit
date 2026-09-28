/* SPDX-License-Identifier: MPL-2.0 */
#include "../core/api/rx3_module_api.h"
typedef struct { float left, right; } Float2;
#define RX3_PITCH_DIAGNOSTIC 1
#define TAB_IMAGE_KEY 0x1600u
static const struct rx3_services *framework;
#define install_hook framework->install_hook
#define detach_hook framework->detach_hook
#define release_hook framework->release_hook
#define log_line framework->log_line
#include "rx3_keyshift_decl.h"
static struct installed_hook timestretch_manager_hook;
static timestretch_manager_fn original_timestretch_manager;
struct rx3_timeval { long seconds, microseconds; };
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

static uint64_t monotonic_enough_us(void)
{
    struct rx3_timeval value;
    if (gettimeofday(&value, 0))
        return 0;
    return (uint64_t)(unsigned long)value.seconds * 1000000u +
           (uint64_t)(unsigned long)value.microseconds;
}

static int block_is_silent(const Float2 *output, unsigned long frames)
{
    for (unsigned long i = 0; i < frames; i++)
        if (output[i].left != 0.0f || output[i].right != 0.0f)
            return 0;
    return 1;
}
#include "rx3_keyshift.h"
#include "rx3_keyshift_panel.h"
#include "rx3_keyshift_metadata.h"
#include "rx3_keyshift_feature.h"
const struct rx3_module rx3_keyshift_module = {
    .version=RX3_MODULE_API_VERSION, .size=sizeof(struct rx3_module),
    .name="keyshift", .configured=keyshift_feature_configured,
    .start=keyshift_feature_install, .stop=keyshift_feature_remove,
    .track_will_load=keyshift_feature_track_will_load,
    .track_did_load=keyshift_feature_track_did_load,
    .audio_started=rx3_keyshift_start_audio,
    .text_observed=keyshift_capture_text, .report=rx3_keyshift_report
};
