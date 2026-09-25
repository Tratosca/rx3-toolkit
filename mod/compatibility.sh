#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# The player binaries this set of addresses accepts.
#
# These are stock checksums. A drive pushed back in without a power cycle meets
# an rbp this runtime already patched, and mod/autoexec.sh puts the guarded words
# back before comparing, so a patched binary normalises onto the entry it started
# from rather than needing one of its own.
#
# To identify a checksum: take images/pdj.tar.gz out of a decrypted firmware
# update, and sha1sum pdj/rbp from it.

module_begin compatibility compatibility

# Firmware 1.19 stock, checked against the binary in that update.
register_rbp_sha1 cf309238491e73cdbdc1f08a09f7a3177e079068
# Firmware 1.20 stock, checked the same way. It differs from 1.19 in three
# bytes, none of them at an address this mod reads or writes.
register_rbp_sha1 3513d34b7ff7ae7b29e3041c6f44116ff2741f90
# Three entries that predate this record. They were registered in the first
# commit with no note of which build each one is, and the binaries are not to
# hand here, so they are left as they are rather than labelled by guesswork.
register_rbp_sha1 7b9d7a0333b6b0ad8adc47bb79875a977b80af75
register_rbp_sha1 fe0e8685790c0980dcb661077862018d956077e0
register_rbp_sha1 be05066245d857c654d297e40a5f6545dcfb3da4
