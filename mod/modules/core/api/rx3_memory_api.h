/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_MEMORY_API_H
#define RX3_MEMORY_API_H
/* One ledger for every resident allocation a module makes: stems, sample
 * banks, image arenas. A module reserves before it allocates, settles once
 * the pages are resident (the kernel then counts them), and releases when it
 * frees them. A reservation is granted when the estimated available RAM,
 * less the reservations other owners still have in flight, covers the bytes
 * and leaves the caller's floor; a zero floor records without refusing.
 * Each module keeps its own ceilings. These calls read /proc: never on the
 * audio, input or render threads.
 */
struct rx3_memory_service {
    int (*reserve)(const void *owner, unsigned long bytes, unsigned long floor_kb);
    void (*settle)(const void *owner, unsigned long bytes);
    /* A reservation whose allocation failed or was cancelled. */
    void (*abandon)(const void *owner, unsigned long bytes);
    void (*release)(const void *owner, unsigned long bytes);
    /* Zero when unknown. */
    unsigned long (*available_kb)(void);
    /* Settled bytes across every owner, for diagnostics. */
    unsigned long (*held)(void);
};
extern const struct rx3_memory_service rx3_memory;
#endif
