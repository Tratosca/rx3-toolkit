# SPDX-License-Identifier: MPL-2.0

SHELL := /bin/sh

ifeq ($(origin CC),default)
CC := clang
endif

PYTHON ?= python3
BUILD_DIR ?= build
FIRMWARE ?= 1.19
MODULES ?=
STEMS_DIR := runtime/modules/stems/$(FIRMWARE)
HOOK := $(BUILD_DIR)/librx3_stems.so
AUTOEXEC := $(BUILD_DIR)/autoexec.bin
PATCH_ARGS := $(foreach patch,$(MODULES),--patch $(patch))

CFLAGS := --target=arm-linux-gnueabi -march=armv7-a -marm \
	-mfloat-abi=softfp -mfpu=neon -fPIC -fno-stack-protector \
	-O2 -Wall -Wextra -Werror
LDFLAGS := -fuse-ld=lld -shared -nostdlib \
	-Wl,--hash-style=sysv -Wl,--build-id=none

.DEFAULT_GOAL := help

.PHONY: help hook autoexec gui stems-gui test preflight clean

help:
	@printf '%s\n' \
	  'make hook                         compile the ARM EABI5 hook' \
	  'make autoexec KEY=/path/key       build the default firmware 1.19 runtime' \
	  'make autoexec KEY=... MODULES="beatjump-32bars decoder-sleep"' \
	  'make gui                          open RX3 Mod Generator' \
	  'make stems-gui                    open RX3 Stem Studio' \
	  'make test                         run source tests' \
	  'make preflight                    inspect publishable files' \
	  'make clean                        remove build/ only'

hook: $(HOOK)

$(HOOK): $(STEMS_DIR)/rx3_stems_hook.c
	@mkdir -p "$(BUILD_DIR)"
	$(CC) $(CFLAGS) $(LDFLAGS) -o "$@" "$<"
	@file "$@" | grep -q 'ELF 32-bit LSB shared object, ARM, EABI5'

autoexec:
	@test -n "$(KEY)" || { echo 'KEY=/path/outside/the/repository/aes256.key is required' >&2; exit 2; }
	@test -f "$(KEY)" || { echo 'key not found: $(KEY)' >&2; exit 2; }
	@mkdir -p "$(BUILD_DIR)"
	$(PYTHON) tools/rx3_runtime/cli.py build \
	  --firmware "$(FIRMWARE)" $(PATCH_ARGS) --key "$(KEY)" --output "$(BUILD_DIR)"

gui:
	$(PYTHON) apps/rx3-mod-generator/main.py

stems-gui:
	$(PYTHON) apps/rx3-stem-studio/main.py

test:
	$(PYTHON) "$(STEMS_DIR)/test_regressions.py"
	$(PYTHON) -m unittest discover -s tests -p 'test_*.py'

preflight:
	./scripts/preflight.sh

clean:
	rm -rf "$(BUILD_DIR)"
