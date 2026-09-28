# SPDX-License-Identifier: MPL-2.0

SHELL := /bin/sh

ifeq ($(origin CC),default)
CC := clang
endif

PYTHON ?= python3
CARGO ?= cargo
BUILD_DIR ?= build
# The version an operator reads in the deck's menu. Each module says which
# versions it is built for; this picks which of them a drive carries.
FIRMWARE ?= 1.19
MODULES ?=
# The key stays outside this repository. RX3_KEY saves retyping its path on
# every build; KEY= on the command line still wins.
KEY ?= $(RX3_KEY)
CORE_DIR := mod/modules/core
# One directory per module, so a new module is picked up without editing this
# file: its headers become hook prerequisites.
MODULE_HEADERS := $(shell find mod/modules -type f -name '*.h')
HOOK := $(BUILD_DIR)/librx3_core.so
HOOK_UNITS := $(shell $(PYTHON) -c 'import json; print(" ".join("mod/modules/" + p for p in json.load(open("$(CORE_DIR)/manifest.json"))["arm_hook"].get("sources", [])))')
AUTOEXEC := $(BUILD_DIR)/autoexec.bin
PATCH_ARGS := $(foreach patch,$(MODULES),--patch $(patch))

# -fno-builtin-memcmp is load-bearing. At -O2 clang rewrites `memcmp(a,b,n) == 0`
# into a call to bcmp, which rbp's libc does not export: the hook then fails to
# load with an undefined symbol and every run silently falls back to stock
# behaviour. Nothing warns about it, because the rewrite happens after the
# front end. tests/test_hook_symbols.py pins the resulting symbol set.
CFLAGS := --target=arm-linux-gnueabi -march=armv7-a -marm \
	-mfloat-abi=softfp -mfpu=neon -fPIC -fno-stack-protector \
	-fno-builtin-memcmp -fno-builtin-bcmp -fvisibility=hidden \
	-O2 -Wall -Wextra -Werror
LDFLAGS := -fuse-ld=lld -shared -nostdlib \
	-Wl,--hash-style=sysv -Wl,--build-id=none

# Experimental reader; ordinary builds have no new runtime imports.
ifeq ($(OVERCUE),1)
CFLAGS += -DRX3_OVERCUE_PROTOTYPE
HOOK_UNITS += mod/modules/stems/overcue/overcue.c
endif

.DEFAULT_GOAL := help

.PHONY: help hook autoexec app new-module test preflight clean overcue-audio

help:
	@printf '%s\n' \
	  'make hook                         compile the ARM EABI5 hook' \
	  'make autoexec KEY=/path/key       build the runtime for firmware $(FIRMWARE)' \
	  'make autoexec KEY=... MODULES="beatjump-32bars decoder-sleep"' \
	  'make app                          open the XDJ-RX3 Toolkit' \
	  'make new-module ID=browse-lock CATEGORY=screen    write the files a new module is made of' \
	  'make new-module ID=x CATEGORY=screen CORE=1       ... one that reacts while a track plays' \
	  'make test                         run source tests' \
	  'make preflight                    inspect publishable files' \
	  'make clean                        remove build/ only'

hook: $(HOOK)

# Offline prototype only; neither the firmware nor the default app needs Rust.
overcue-audio:
	CARGO_TARGET_DIR="$(abspath $(BUILD_DIR))/overcue-audio" $(CARGO) build --locked --release --manifest-path native/overcue-audio/Cargo.toml

$(HOOK): $(CORE_DIR)/rx3_core_hook.c $(HOOK_UNITS) $(MODULE_HEADERS) $(CORE_DIR)/manifest.json
	@mkdir -p "$(BUILD_DIR)"
	$(CC) $(CFLAGS) $(LDFLAGS) -o "$@" "$(CORE_DIR)/rx3_core_hook.c" $(HOOK_UNITS)
	@file "$@" | grep -q 'ELF 32-bit LSB shared object, ARM, EABI5'

autoexec:
	@test -n "$(KEY)" || { echo 'KEY=/path/outside/the/repository/aes256.key is required' >&2; exit 2; }
	@test -f "$(KEY)" || { echo 'key not found: $(KEY)' >&2; exit 2; }
	@mkdir -p "$(BUILD_DIR)"
	$(PYTHON) -m app.runtime.cli build \
	  --firmware "$(FIRMWARE)" $(PATCH_ARGS) --key "$(KEY)" --output "$(BUILD_DIR)"

app:
	$(PYTHON) app/ui/shell.py

# A module is three files whose names, namespacing and order field are
# conventions. Guessing them from a neighbouring module is how one of them ends
# up wrong.
new-module:
	@test -n "$(ID)" || { echo 'ID=<module-id> is required, e.g. make new-module ID=browse-lock CATEGORY=screen' >&2; exit 2; }
	$(PYTHON) -m app.runtime.scaffold --id "$(ID)" --name "$(NAME)" --category "$(CATEGORY)" \
	  $(if $(CORE),--core,)

test:
	$(PYTHON) -m unittest discover -s tests -p 'test_*.py'

preflight:
	./scripts/preflight.sh

clean:
	rm -rf "$(BUILD_DIR)"
