/*
 * Minimal legacy ARM Linux boot stub for the RX3 1.19 kernel.
 *
 * QEMU's sabrelite machine normally boots a device-tree kernel, while the
 * Pioneer kernel uses the pre-DT ATAG protocol and the mx6q_sabresd machine
 * id.  Keep this shim deliberately tiny: it changes neither the kernel nor
 * the firmware root filesystem.
 */

    .syntax unified
    .cpu cortex-a9
    .arm
    .section .text.boot, "ax"
    .global _start

_start:
    cpsid   if
    mov     r0, #0
    ldr     r1, =3980              /* MACH_TYPE_MX6Q_SABRESD */
    ldr     r2, =0x10000100        /* ATAG list */
    ldr     r3, =0x10008000        /* uImage payload load/entry address */
    bx      r3

    .org 0x100

    /* ATAG_CORE */
    .word   5
    .word   0x54410001
    .word   1
    .word   4096
    .word   0

    /* ATAG_MEM: 1 GiB at the i.MX6 MMDC base. */
    .word   4
    .word   0x54410002
    .word   0x40000000
    .word   0x10000000

    /* ATAG_CMDLINE */
    .word   (.Lcmdline_end - .Lcmdline + 3) / 4 + 2
    .word   0x54410009
.Lcmdline:
    .asciz  "console=ttymxc0,115200 earlyprintk=serial,ttymxc0,115200 keep_bootcon ignore_loglevel rdinit=/init"
.Lcmdline_end:
    .balign 4

#if RX3_INITRD_SIZE
    /* ATAG_INITRD2: external fast-mode rootfs, overlaid on the built-in one. */
    .word   4
    .word   0x54420005
    .word   RX3_INITRD_START
    .word   RX3_INITRD_SIZE
#endif

    /* ATAG_NONE */
    .word   0
    .word   0
