/* SPDX-License-Identifier: MPL-2.0 */
#include "../api/rx3_platform.h"
#include "rx3_hooks.h"
#include "../firmware/rx3_patch.h"

struct hook_record {
    unsigned long address;
    uint8_t original[8];
    void *trampoline;
    void *original_slot;
    struct installed_hook *owner;
    int detached;
};
#define RX3_HOOK_LIMIT 48u
static struct hook_record records[RX3_HOOK_LIMIT];

/*
 * Copy the first eight bytes into a trampoline and append an absolute jump to
 * address+8. These stolen instructions have no PC-relative dependency:
 *   getStreamAt : ldrb r12,[r0,#0x9c] ; stmdb sp!,{r4..r8,r10,lr}
 *   load        : stmdb sp!,{r4..r11,lr} ; sub sp,sp,#0x5c
 *   onKey_Pad   : ldrh r3,[r1,#8] ; stmdb sp!,{r4..r11,lr}
 */
static void *prepare_raw_hook(struct hook_record *hook, unsigned long address,
                              const uint8_t guard[8])
{
    if (memcmp((const void *)address, guard, 8))
        return 0;

    uint32_t *trampoline = mmap(0, 4096, PROT_READ | PROT_WRITE,
                                MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (trampoline == MAP_FAILED)
        return 0;
    memcpy(trampoline, (const void *)address, 8);
    /* Relocate an ARM literal load in either stolen instruction. Browse's
       native scroll setup uses ADD followed by LDR r2,[pc,#imm12]. */
    for (unsigned int i=0;i<2;i++) {
        uint32_t op=trampoline[i];
        if ((op & 0xffff0000u)==0xe59f0000u && ((op>>12)&15u)!=15u) {
            trampoline[4+i]=*(const uint32_t *)(address+i*4u+8u+(op&0xfffu));
            trampoline[i]=(op&0xfffff000u)|8u;
        }
    }
    trampoline[2] = 0xe51ff004;                      /* ldr pc,[pc,#-4] */
    trampoline[3] = (uint32_t)(address + 8);
    clear_instruction_cache((unsigned long)trampoline,
                            (unsigned long)trampoline + 24u);
    if (mprotect(trampoline, 4096, PROT_READ | PROT_EXEC)) {
        munmap(trampoline, 4096);
        return 0;
    }

    hook->address = address;
    memcpy(hook->original, guard, sizeof(hook->original));
    hook->trampoline = trampoline;
    hook->detached = 1;
    return trampoline;
}


/* Variant for ldr r3,[pc,#imm12] followed by push. The trampoline loads a copy
   of the original literal value, replays push, and joins address+8. This
   preserves r3 without depending on the shared object's mapped address. */
static void *prepare_raw_pc_ldr_hook(struct hook_record *hook,
                                     unsigned long address,
                                     const uint8_t guard[8])
{
    if (memcmp((const void *)address, guard, 8))
        return 0;

    uint32_t instruction = *(const uint32_t *)address;
    if ((instruction & 0xfffff000u) != 0xe59f3000u)
        return 0;
    unsigned long literal_address = address + 8u + (instruction & 0xfffu);
    uint32_t literal_value = *(const uint32_t *)literal_address;

    uint32_t *trampoline = mmap(0, 4096, PROT_READ | PROT_WRITE,
                                MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (trampoline == MAP_FAILED)
        return 0;
    trampoline[0] = 0xe59f3008u;                    /* ldr r3,[pc,#8] */
    trampoline[1] = *(const uint32_t *)(address + 4u); /* push original */
    trampoline[2] = 0xe51ff004u;                    /* ldr pc,[pc,#-4] */
    trampoline[3] = (uint32_t)(address + 8u);
    trampoline[4] = literal_value;
    clear_instruction_cache((unsigned long)trampoline,
                            (unsigned long)trampoline + 20u);
    if (mprotect(trampoline, 4096, PROT_READ | PROT_EXEC)) {
        munmap(trampoline, 4096);
        return 0;
    }

    hook->address = address;
    memcpy(hook->original, guard, sizeof(hook->original));
    hook->trampoline = trampoline;
    hook->detached = 1;
    return trampoline;
}

static void publish_original(void *slot, void *trampoline)
{
    memcpy(slot, &trampoline, sizeof(trampoline));
    __atomic_thread_fence(__ATOMIC_RELEASE);
}

static void clear_original(void *slot)
{
    void *empty = 0;
    memcpy(slot, &empty, sizeof(empty));
    __atomic_thread_fence(__ATOMIC_RELEASE);
}

static int activate_hook(struct hook_record *hook, void *replacement)
{
    uint32_t patch[2] = {0xe51ff004u, (uint32_t)(unsigned long)replacement};
    enum rx3_replace_result result = replace_code(
        hook->address, patch, hook->original, sizeof(patch));

    if (result == RX3_REPLACE_APPLIED) {
        hook->detached = 0;
        return 1;
    }
    if (result == RX3_REPLACE_RECOVERY_PENDING)
        hook->detached = 0;
    return 0;
}

/* A single pool owns every detour, even across separately compiled modules.
 * A detached address stays reserved until callbacks have drained and its
 * trampoline has been released. No implicit hook chaining is allowed.
 */
static int install_owned_hook(struct installed_hook *handle,
                              unsigned long address, const uint8_t guard[8],
                              void *replacement, void *original_slot,
                              int pc_ldr)
{
    if (!handle || handle->record || !address || !guard || !replacement ||
        !original_slot) return 0;
    clear_original(original_slot);
    struct hook_record *slot = 0;
    for (unsigned int i = 0; i < RX3_HOOK_LIMIT; i++) {
        if (!records[i].owner) { if (!slot) slot = &records[i]; continue; }
        unsigned long other = records[i].address;
        if ((address >= other && address - other < 8u) ||
            (other > address && other - address < 8u)) return 0;
    }
    if (!slot) return 0;
    void *original = pc_ldr ? prepare_raw_pc_ldr_hook(slot, address, guard) :
                             prepare_raw_hook(slot, address, guard);
    if (!original) return 0;
    slot->owner = handle;
    slot->original_slot = original_slot;
    handle->record = slot;
    publish_original(original_slot, original);
    if (activate_hook(slot, replacement)) return 1;

    if (slot->detached) release_hook(handle);
    return 0;
}
int install_hook(struct installed_hook *handle, unsigned long address,
                 const uint8_t guard[8], void *replacement,
                 void *original_slot)
{
    return install_owned_hook(handle, address, guard, replacement,
                              original_slot, 0);
}
int install_pc_ldr_hook(struct installed_hook *handle, unsigned long address,
                        const uint8_t guard[8], void *replacement,
                        void *original_slot)
{
    return install_owned_hook(handle, address, guard, replacement,
                              original_slot, 1);
}
int hook_is_installed(const struct installed_hook *handle)
{
    return handle && handle->record && handle->record->owner == handle;
}
int detach_hook(struct installed_hook *handle)
{
    if (!handle || !handle->record) return 1;
    struct hook_record *record = handle->record;
    if (record->owner != handle) return 0;
    if (record->detached) return 1;
    if (write_code(record->address, record->original, sizeof(record->original))) return 0;
    record->detached = 1;
    return 1;
}
int release_hook(struct installed_hook *handle)
{
    if (!handle || !handle->record) return 1;
    struct hook_record *record = handle->record;
    if (record->owner != handle || !record->detached) return 0;
    if (record->trampoline && munmap(record->trampoline, 4096)) return 0;
    if (record->original_slot) clear_original(record->original_slot);
    memset(record, 0, sizeof(*record));
    handle->record = 0;
    return 1;
}
int uninstall_hook(struct installed_hook *handle)
{
    return detach_hook(handle) && release_hook(handle);
}
