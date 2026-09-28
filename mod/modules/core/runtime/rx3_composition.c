/* SPDX-License-Identifier: MPL-2.0 */
#include "../api/rx3_module_api.h"
/* Composition root only. The framework does not include module code. */
extern const struct rx3_module rx3_key_match_module;
extern const struct rx3_module rx3_browse_columns_module;
extern const struct rx3_module rx3_keyshift_module;
extern const struct rx3_module rx3_search_module;
extern const struct rx3_module rx3_now_playing_module;
extern const struct rx3_module rx3_stemwave_module;
const struct rx3_module *const rx3_bundle[] = {
    &rx3_key_match_module, &rx3_browse_columns_module, &rx3_keyshift_module, &rx3_search_module, &rx3_now_playing_module, &rx3_stemwave_module
};
const unsigned int rx3_bundle_count = sizeof(rx3_bundle) / sizeof(rx3_bundle[0]);
