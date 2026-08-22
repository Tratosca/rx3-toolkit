# SPDX-License-Identifier: MPL-2.0

SHELL := /bin/sh

ifeq ($(origin CC),default)
CC := clang
endif

PYTHON ?= python3
BUILD_DIR ?= build
FIRMWARE ?= 1.19
MODULES ?=
# The key stays outside this repository. RX3_KEY saves retyping its path on
# every build; KEY= on the command line still wins.
KEY ?= $(RX3_KEY)
VARIANT ?= all
VERSION ?= 0.0.0-dev
PAYLOAD_DIR ?= $(BUILD_DIR)/payload
CORE_DIR := mod/modules/core/$(FIRMWARE)
# One directory per module, so a new module is picked up without editing this
# file: its headers become hook prerequisites and its guards join `make test`.
MODULE_HEADERS := $(wildcard mod/modules/*/$(FIRMWARE)/*.h)
MODULE_GUARDS := $(wildcard mod/modules/*/$(FIRMWARE)/test_regressions.py)
HOOK := $(BUILD_DIR)/librx3_core.so
PAYLOAD_HOOK := $(BUILD_DIR)/librx3_core_payload.so
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

.PHONY: help hook payload-hook autoexec app payload test preflight clean

help:
	@printf '%s\n' \
	  'make hook                         compile the ARM EABI5 hook' \
	  'make payload-hook                 compile the hook variant the payload ships' \
	  'make autoexec KEY=/path/key       build the default firmware 1.19 runtime' \
	  'make autoexec KEY=... MODULES="beatjump-32bars decoder-sleep"' \
	  'make app                          open the XDJ-RX3 Toolkit' \
	  'make payload                      assemble the mods into a runnable payload' \
	  'make payload VARIANT=keyshift     assemble one variant only' \
	  'make test                         run source tests' \
	  'make preflight                    inspect publishable files' \
	  'make clean                        remove build/ only'

hook: $(HOOK)

$(HOOK): $(CORE_DIR)/rx3_core_hook.c $(MODULE_HEADERS)
	@mkdir -p "$(BUILD_DIR)"
	$(CC) $(CFLAGS) $(LDFLAGS) -o "$@" "$(CORE_DIR)/rx3_core_hook.c"
	@file "$@" | grep -q 'ELF 32-bit LSB shared object, ARM, EABI5'

$(PAYLOAD_HOOK): $(CORE_DIR)/rx3_core_hook.c $(MODULE_HEADERS)
	@mkdir -p "$(BUILD_DIR)"
	$(CC) $(CFLAGS) -DRX3_EMULATOR_BUILD=1 $(LDFLAGS) \
	  -o "$@" "$(CORE_DIR)/rx3_core_hook.c"
	@file "$@" | grep -q 'ELF 32-bit LSB shared object, ARM, EABI5'

payload-hook: hook $(PAYLOAD_HOOK)

autoexec:
	@test -n "$(KEY)" || { echo 'KEY=/path/outside/the/repository/aes256.key is required' >&2; exit 2; }
	@test -f "$(KEY)" || { echo 'key not found: $(KEY)' >&2; exit 2; }
	@mkdir -p "$(BUILD_DIR)"
	$(PYTHON) tools/rx3_runtime/cli.py build \
	  --firmware "$(FIRMWARE)" $(PATCH_ARGS) --key "$(KEY)" --output "$(BUILD_DIR)"

app:
	$(PYTHON) apps/rx3-toolbox/main.py

# The one artefact a runner is given. Everything needed to run these mods is
# inside it; nothing in it points back at this repository.
payload: payload-hook
	$(PYTHON) -m tools.rx3_payload.cli --variant "$(VARIANT)" \
	  --output "$(PAYLOAD_DIR)" --version "$(VERSION)"

test:
	@set -e; for guard in $(MODULE_GUARDS); do $(PYTHON) "$$guard"; done
	$(PYTHON) -m unittest discover -s tests -p 'test_*.py'

preflight:
	./scripts/preflight.sh

clean:
	rm -rf "$(BUILD_DIR)"
