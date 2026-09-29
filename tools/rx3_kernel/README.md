<!-- SPDX-License-Identifier: MPL-2.0 -->
# RX3 kernel module builds

This directory owns the toolchain and ABI checks shared by optional kernel
modules. Feature-specific Kconfig and Kbuild steps live in
`tools/rx3_<module>_kernel`.

A published kernel source tree must contain the production `.config`,
`include/config/kernel.release`, and matching source. The builder copies that
tree into an isolated container, prepares it for the production release, and
then rejects outputs with the wrong architecture, vermagic, modversion table,
or position-independent relocations.

Build the common toolchain image once:

```sh
make kernel-builder
```

Fetch Pioneer's checksum-pinned GPL source release:

```sh
make kernel-source FIRMWARE=1.19
```

Build one module's artifacts:

```sh
make kernel-modules \
  MODULE=example \
  FIRMWARE=1.19 \
  KERNEL_SOURCE=/path/to/prepared/kernel
```

Outputs go to `build/artifacts/<firmware>/<module>/`. They are ignored by Git.
A runtime manifest marks a generated input with `"artifact": true`; packaging
then reads it from that directory instead of the module's source directory.

A module with multiple hardware implementations keeps each recipe under
`tools/rx3_<module>_kernel/profiles/<profile>/` and selects one explicitly:

```sh
make kernel-modules \
  MODULE=example \
  PROFILE=example-device \
  FIRMWARE=1.19 \
  KERNEL_SOURCE=/path/to/prepared/kernel
```

Profile outputs go to
`build/artifacts/<firmware>/<module>/<profile>/`.

## Feature recipe contract

`tools/rx3_<module>_kernel` contains:

- `build.sh`, executed inside the offline container with the copied kernel tree
  as its first argument and an empty output directory as its second;
- `modules.list`, one output `.ko` filename per line;
- `production.symvers`, the minimal production CRC entries imported by those
  outputs, and `production.symvers.sha256`, which pins that profile's contents;
- any original compatibility source or Kbuild files the feature owns.

A recipe that needs source outside the published kernel tree also provides:

- `fetch-sources.sh`, which writes pinned inputs into the supplied cache;
- `sources.sha256`, which verifies every fetched input before use;
- `prepare-recipe.sh`, which expands or transforms those inputs inside a
  temporary copy of the recipe.

All three source-hook files must be present together. The common runner keeps
downloads outside Git, verifies them before preparation, and passes only the
prepared recipe into the offline kernel build container.

The recipe sources `/tool/kernel-build-lib.sh`, changes Kconfig as needed, calls
`rx3_kernel_prepare`, and builds through `rx3_kernel_make`. The common runner
provides the firmware release, validates every filename declared by
`modules.list`, and proves that the minimal production symbol profile exactly
covers the built modules' external versioned imports.

## Production ABI profiles

Kernel source identifies symbol names and types, but it does not establish the
CRCs used by the kernel running on the player. Configuration and vendor source
changes affect those CRCs, and a symbol table published for an earlier firmware
release is not evidence for a later release. A profile must therefore be
derived from `Module.symvers` recovered from the exact production firmware it
names, or from another production artifact that exposes the same `__crc_*`
values. Verify the firmware version and kernel release on the device before
using that data.

Start with the full recovered production table, build the feature's complete
module set, and retain only the `vmlinux` entries referenced by the resulting
modules. Entries satisfied by another module in the same `modules.list` belong
to that module, not to `production.symvers`. The validator enforces this
minimal boundary: it rejects missing or unused production symbols, CRCs that
do not match the built modules, and inconsistent CRCs across sibling modules.

Commit the minimal profile and regenerate its pin with:

```sh
sha256sum production.symvers >production.symvers.sha256
```

The checksum detects accidental profile changes; it does not attest the source
of the CRCs. Each feature recipe's README must record how its production table
was recovered, the firmware and kernel release it was matched against, and any
device loading used to validate the finished modules. Review that evidence
when adding or changing a profile. A successful offline build proves internal
ABI consistency, while loading on matching hardware remains the final check.
