/* SPDX-License-Identifier: MPL-2.0 */
#include "../api/rx3_platform.h"
#include "rx3_patch.h"

void clear_instruction_cache(unsigned long first, unsigned long last)
{
#if defined(__arm__)
    register unsigned long r0 __asm__("r0") = first;
    register unsigned long r1 __asm__("r1") = last;
    register unsigned long r2 __asm__("r2") = 0;
    register unsigned long r7 __asm__("r7") = 0x0f0002u; /* __ARM_NR_cacheflush */
    __asm__ volatile("svc 0" : "+r"(r0) : "r"(r1), "r"(r2), "r"(r7) : "memory");
#else
    __builtin___clear_cache((char *)first, (char *)last);
#endif
}

int write_code(unsigned long address, const void *bytes, size_t length)
{
    /* Every caller writes a four-byte literal or an eight-byte detour. Keep
       the previous bytes until permissions have been restored successfully. */
    uint8_t previous[8];
    if (!address || !bytes || !length || length > sizeof(previous) ||
        address + length - 1u < address) return -1;
    long page_size = sysconf(_SC_PAGESIZE);
    if (page_size <= 0)
        page_size = 4096;
    unsigned long mask  = (unsigned long)page_size - 1u;
    unsigned long first = address & ~mask;
    unsigned long last  = (address + length - 1u) & ~mask;
    size_t span = (size_t)(last - first) + (size_t)page_size;

    memcpy(previous, (const void *)address, length);
    /* Retain execute permission: other native code can share this page.
       This does not make instruction replacement safe against live callers. */
    if (mprotect((void *)first, span, PROT_READ | PROT_WRITE | PROT_EXEC))
        return -1;
    memcpy((void *)address, bytes, length);
    clear_instruction_cache(address, address + length);
    if (mprotect((void *)first, span, PROT_READ | PROT_EXEC)) {
        memcpy((void *)address, previous, length);
        clear_instruction_cache(address, address + length);
        /* Even if this retry fails, the old code remains executable. */
        (void)mprotect((void *)first, span, PROT_READ | PROT_EXEC);
        return -1;
    }
    return 0;
}

int rx3_write_guarded(unsigned long address, const void *expected,
                      const void *replacement, unsigned int length)
{
    if (!address || !expected || !replacement || !length || length > 8u)
        return 0;
    if (memcmp((const void *)address, expected, length))
        return 0;
    return write_code(address, replacement, length) == 0;
}

enum rx3_replace_result replace_code(unsigned long address,
                                     const void *replacement,
                                     const void *rollback, size_t length)
{
    long page_size = sysconf(_SC_PAGESIZE);
    if (page_size <= 0)
        page_size = 4096;
    unsigned long mask = (unsigned long)page_size - 1u;
    unsigned long first = address & ~mask;
    unsigned long last = (address + length - 1u) & ~mask;
    size_t span = (size_t)(last - first) + (size_t)page_size;

    if (mprotect((void *)first, span, PROT_READ | PROT_WRITE | PROT_EXEC))
        return RX3_REPLACE_UNCHANGED;

    memcpy((void *)address, replacement, length);
    clear_instruction_cache(address, address + length);
    if (!mprotect((void *)first, span, PROT_READ | PROT_EXEC))
        return RX3_REPLACE_APPLIED;

    memcpy((void *)address, rollback, length);
    clear_instruction_cache(address, address + length);
    if (!mprotect((void *)first, span, PROT_READ | PROT_EXEC))
        return RX3_REPLACE_ROLLED_BACK;

    return RX3_REPLACE_RECOVERY_PENDING;
}
