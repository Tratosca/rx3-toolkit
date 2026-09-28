/* SPDX-License-Identifier: MPL-2.0 */
#include "../core/api/rx3_module_api.h"
#include "rx3_now_playing_decl.h"
static const struct rx3_services *framework;

#include "rx3_now_playing_feature.h"
static int start(const struct rx3_services *services)
{
    framework = services;
    return now_playing_feature_install();
}
const struct rx3_module rx3_now_playing_module = {
    RX3_MODULE_API_VERSION, sizeof(struct rx3_module), "now-playing",
    now_playing_feature_configured, start, now_playing_feature_remove, 0, 0, 0, 0, 0
};
