/* SPDX-License-Identifier: MPL-2.0 */
/* Sample bank. The module owns the bank, its settings, voices, pad policy,
 * LED colours and panel; the core owns the native pad, key, LED and master
 * bus hooks and calls the module through typed services. */
#include "../core/api/rx3_module_api.h"
static const struct rx3_services *framework;
#define log_line framework->log_line
#define log_number framework->log_number

static size_t str_length(const char *s)
{
    size_t n = 0;
    while (s[n])
        n++;
    return n;
}

#include "rx3_samples_decl.h"
#include "rx3_samples_state.h"
#include "rx3_samples_panel.h"
#include "rx3_samples_feature.h"

static int samples_configured(void)
{
    const char *samples = getenv("RX3_SAMPLES_DIR");
    return samples && samples[0] != '\0';
}

static int samples_start(const struct rx3_services *services)
{
    framework = services;
    if (!services->input || !services->audio || !services->panels || !services->memory ||
        !services->loader) return 0;
    samples_enabled = samples_configured();
    return samples_feature_install();
}

static void samples_stop_module(void)
{
    if (!framework || !framework->input || !framework->audio || !framework->panels ||
        !framework->loader) return;
    samples_feature_remove();
    samples_enabled = 0;
}

const struct rx3_module rx3_samples_module = {
    .version = RX3_MODULE_API_VERSION, .size = sizeof(struct rx3_module),
    .name = "samples", .configured = samples_configured,
    .start = samples_start, .stop = samples_stop_module
};
