/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_BROWSE_API_H
#define RX3_BROWSE_API_H
#include "rx3_platform.h"
/* Metadata categories are native semantic values, not coordinates.
 * Descriptors and callbacks have process lifetime; registration and removal
 * run on the lifecycle thread. Classification runs on the database worker.
 * A single optional column and a single marker provider share the row hook. */
struct rx3_browse_column { unsigned int field; const uint16_t *caption; };
struct rx3_browse_marker {
    unsigned int (*category)(unsigned int reference,unsigned int key,unsigned int native_category);
    unsigned int (*image)(unsigned int category);
};
/* Current local MASTER and its native Traffic Light set, zero-based Camelot.
 * key=-1 means no usable reference. Values are copied, never borrowed. */
struct rx3_harmonic_reference { int deck,key; unsigned int native_keys; };
struct rx3_browse_service {
    int (*column)(const void *owner,const struct rx3_browse_column *);
    int (*marker)(const void *owner,const struct rx3_browse_marker *);
    void (*unregister_owner)(const void *owner);
    struct rx3_harmonic_reference (*reference)(void);
    void (*deck_key)(unsigned int deck,int source_key,int semitones);
};
extern const struct rx3_browse_service rx3_browse;
#endif
