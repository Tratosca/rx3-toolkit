/* SPDX-License-Identifier: MPL-2.0 */
#include "../core/api/rx3_module_api.h"
#include "rx3_stemwave_decl.h"
static const struct rx3_services *framework;
#define EX_WAVE_RENEW_CHECK ((unsigned long)0x0012fc60)
typedef int (*ex_wave_renew_check_fn)(unsigned int);
static const uint8_t ex_wave_renew_guard[8] = {
    0xf0, 0x4f, 0x2d, 0xe9, 0x0c, 0xd0, 0x4d, 0xe2
};
static ex_wave_renew_check_fn original_ex_wave_renew_check;
static struct installed_hook ex_wave_renew_hook;

#include "rx3_stemwave_feature.h"
static int start(const struct rx3_services *services)
{
    framework = services;
    return stemwave_feature_install();
}
const struct rx3_module rx3_stemwave_module = {
    .version = RX3_MODULE_API_VERSION, .size = sizeof(struct rx3_module),
    .name = "stemwave", .configured = stemwave_feature_configured,
    .start = start, .stop = stemwave_feature_remove,
    .track_did_load = stemwave_feature_track_did_load, 0, 0, 0
};
