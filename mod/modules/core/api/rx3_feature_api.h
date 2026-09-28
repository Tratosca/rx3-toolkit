/* SPDX-License-Identifier: MPL-2.0
 *
 * Contract between the firmware-specific performance core and an on-screen
 * feature. The broker owns native rendering and touch objects. A feature owns
 * its labels, state and actions and never calls another feature.
 */

#ifndef RX3_FEATURE_API_H
#define RX3_FEATURE_API_H

#include "rx3_panel_api.h"

struct rx3_runtime_feature {
    const char *name;
    int active;
    const struct rx3_pad_row *row;
    int (*configured)(void);
    int (*install)(void);
    void (*remove)(void);
    void (*track_will_load)(unsigned int deck, void *reader,
                            const void *track_info);
    void (*track_did_load)(unsigned int deck, void *reader,
                           const void *track_info);
    void (*audio_started)(unsigned int sample_rate);
    void (*report)(void);
    void (*destroy_deck)(unsigned int deck);
};

#endif /* RX3_FEATURE_API_H */
