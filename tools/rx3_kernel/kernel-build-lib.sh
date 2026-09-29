#!/bin/sh
# SPDX-License-Identifier: MPL-2.0

rx3_kernel_make()
{
    make -C "$RX3_KERNEL_TREE" \
        ARCH=arm \
        CROSS_COMPILE=arm-linux-gnueabi- \
        CC=arm-linux-gnueabi-gcc-12 \
        HOSTCC=clang \
        KCFLAGS="-fno-pie -fno-pic" \
        "$@"
}

rx3_kernel_prepare()
{
    source_localversion=$(cat "$RX3_KERNEL_TREE/localversion")
    printf '%s%s\n' "$source_localversion" "$RX3_KERNEL_LOCALVERSION_APPEND" > \
        "$RX3_KERNEL_TREE/localversion"
    printf '%s\n' '#include <linux/compiler-gcc4.h>' > \
        "$RX3_KERNEL_TREE/include/linux/compiler-gcc12.h"
    rx3_kernel_make oldnoconfig prepare modules_prepare

    [ "$(cat "$RX3_KERNEL_TREE/include/config/kernel.release")" = \
        "$RX3_KERNEL_RELEASE" ] || {
        echo "prepared kernel has an unexpected release" >&2
        exit 1
    }

    # Linux 3.0 removes Module.symvers during modules_prepare. The production
    # CRCs define the ABI these additional modules must target.
    cp "$RX3_KERNEL_PRODUCTION_SYMVERS" "$RX3_KERNEL_TREE/Module.symvers"
}
