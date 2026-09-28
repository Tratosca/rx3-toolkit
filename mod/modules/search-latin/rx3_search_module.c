/* SPDX-License-Identifier: MPL-2.0 */
#include "../core/api/rx3_module_api.h"
#include "rx3_search_decl.h"
static const struct rx3_services *framework;
#define SEARCH_SHAPE ((unsigned long)0x001644fc)
typedef void (*search_shape_fn)(uint16_t *, void *, int);
static const uint8_t search_shape_guard[8] = {
    0x18, 0xd0, 0x4d, 0xe2, 0x0c, 0x00, 0x8d, 0xe5
};
static search_shape_fn original_search_shape;
static struct installed_hook search_shape_hook;

#include "rx3_search_feature.h"
static int start(const struct rx3_services *services)
{
    framework = services;
    return search_latin_feature_install();
}
const struct rx3_module rx3_search_module = {
    RX3_MODULE_API_VERSION, sizeof(struct rx3_module), "search-latin",
    search_latin_feature_configured, start, search_latin_feature_remove, 0, 0, 0, 0, 0
};
