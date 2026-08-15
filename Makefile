# SPDX-License-Identifier: MPL-2.0

SHELL := /bin/sh

ifeq ($(origin CC),default)
CC := clang
endif

PYTHON ?= python3
BUILD_DIR ?= build
FIRMWARE ?= 1.19
MODULES ?=
CORE_DIR := mod/modules/core/$(FIRMWARE)
# One directory per module, so a new module is picked up without editing this
# file: its headers become hook prerequisites and its guards join `make test`.
MODULE_HEADERS := $(wildcard mod/modules/*/$(FIRMWARE)/*.h)
MODULE_GUARDS := $(wildcard mod/modules/*/$(FIRMWARE)/test_regressions.py)
HOOK := $(BUILD_DIR)/librx3_core.so
EMULATOR_HOOK := $(BUILD_DIR)/librx3_core_emulator.so
AUTOEXEC := $(BUILD_DIR)/autoexec.bin
PATCH_ARGS := $(foreach patch,$(MODULES),--patch $(patch))

# -fno-builtin-memcmp is load-bearing. At -O2 clang rewrites `memcmp(a,b,n) == 0`
# into a call to bcmp, which rbp's libc does not export: the hook then fails to
# load with an undefined symbol and every run silently falls back to stock
# behaviour. Nothing warns about it, because the rewrite happens after the
# front end. tests/test_hook_symbols.py pins the resulting symbol set.
CFLAGS := --target=arm-linux-gnueabi -march=armv7-a -marm \
	-mfloat-abi=softfp -mfpu=neon -fPIC -fno-stack-protector \
	-fno-builtin-memcmp -fno-builtin-bcmp \
	-O2 -Wall -Wextra -Werror
LDFLAGS := -fuse-ld=lld -shared -nostdlib \
	-Wl,--hash-style=sysv -Wl,--build-id=none

.DEFAULT_GOAL := help

.PHONY: help hook emulator-hook autoexec app test emulator-image emulate emulate-system emulate-system-fast emulate-system-window preflight clean

help:
	@printf '%s\n' \
	  'make hook                         compile the ARM EABI5 hook' \
	  'make emulator-hook                compile the interactive test hook' \
	  'make autoexec KEY=/path/key       build the default firmware 1.19 runtime' \
	  'make autoexec KEY=... MODULES="beatjump-32bars decoder-sleep"' \
	  'make app                          open the XDJ-RX3 Toolkit' \
	  'make test                         run source tests' \
	  'make emulator-image               build the ARM emulator container' \
	  'make emulate                      run rbp with all mods and export its framebuffer' \
	  'make emulate-system               boot the genuine U-Boot and RX3 kernel in QEMU' \
	  'make emulate-system-fast          boot the kernel, RX3 init, apl_start and rbp' \
	  'make emulate-system-window        show the framebuffer from the full system VM' \
	  'make preflight                    inspect publishable files' \
	  'make clean                        remove build/ only'

hook: $(HOOK)

$(HOOK): $(CORE_DIR)/rx3_core_hook.c $(MODULE_HEADERS)
	@mkdir -p "$(BUILD_DIR)"
	$(CC) $(CFLAGS) $(LDFLAGS) -o "$@" "$(CORE_DIR)/rx3_core_hook.c"
	@file "$@" | grep -q 'ELF 32-bit LSB shared object, ARM, EABI5'

$(EMULATOR_HOOK): $(CORE_DIR)/rx3_core_hook.c $(MODULE_HEADERS)
	@mkdir -p "$(BUILD_DIR)"
	$(CC) $(CFLAGS) -DRX3_EMULATOR_BUILD=1 $(LDFLAGS) \
	  -o "$@" "$(CORE_DIR)/rx3_core_hook.c"
	@file "$@" | grep -q 'ELF 32-bit LSB shared object, ARM, EABI5'

emulator-hook: hook $(EMULATOR_HOOK)

autoexec:
	@test -n "$(KEY)" || { echo 'KEY=/path/outside/the/repository/aes256.key is required' >&2; exit 2; }
	@test -f "$(KEY)" || { echo 'key not found: $(KEY)' >&2; exit 2; }
	@mkdir -p "$(BUILD_DIR)"
	$(PYTHON) tools/rx3_runtime/cli.py build \
	  --firmware "$(FIRMWARE)" $(PATCH_ARGS) --key "$(KEY)" --output "$(BUILD_DIR)"

app:
	$(PYTHON) apps/rx3-toolbox/main.py

test:
	@set -e; for guard in $(MODULE_GUARDS); do $(PYTHON) "$$guard"; done
	$(PYTHON) -m unittest discover -s tests -p 'test_*.py'

emulator-image:
	docker build --platform linux/arm/v7 \
	  --tag rx3-toolbox-emulator:1.19 tools/rx3_emulator/container

emulate: emulator-hook
	$(PYTHON) -m tools.rx3_emulator.cli --profile "$${PROFILE:-all}" \
	  --duration "$${DURATION:-300}" --window

emulate-system:
	$(PYTHON) -m tools.rx3_system_emulator.cli --mode "$${MODE:-all}" \
	  --timeout "$${TIMEOUT:-20}"

emulate-system-fast:
	$(PYTHON) -m tools.rx3_system_emulator.cli --mode fast \
	  --timeout "$${TIMEOUT:-75}"

emulate-system-window:
	$(PYTHON) -m tools.rx3_system_emulator.cli --mode fast --window \
	  --timeout "$${TIMEOUT:-300}"

preflight:
	./scripts/preflight.sh

clean:
	rm -rf "$(BUILD_DIR)"
