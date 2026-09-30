/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_TITLE_API_H
#define RX3_TITLE_API_H
/* Module-owned policy and artwork, called on the native UI thread. Storage
   and callbacks remain resident until process exit. No hot unloading. */
struct rx3_title_provider {
    int (*hidden)(unsigned int deck);
    void (*activate)(unsigned int deck);
    unsigned int (*image)(unsigned int deck,int light);
};
/* Core owns native object identity, gesture capture and invalidation only.
   Exclusive provider. Acquire/release execute during serialized lifecycle. */
struct rx3_title_service {
    int (*acquire)(const void *owner,const struct rx3_title_provider *provider);
    void (*release)(const void *owner);
};
extern const struct rx3_title_service rx3_titles;
#endif
