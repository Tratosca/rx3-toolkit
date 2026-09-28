<!-- SPDX-License-Identifier: MPL-2.0 -->
# RX3 kernel module builds

## Production ABI profiles

Kernel source identifies symbol names and types, but it does not establish the
CRCs used by the kernel running on the player. Configuration and vendor source
changes affect those CRCs, and a symbol table published for an earlier firmware
release is not evidence for a later release. A profile must therefore be
derived from `Module.symvers` recovered from the exact production firmware it
names, or from another production artifact that exposes the same `__crc_*`
values. Verify the firmware version and kernel release on the device before
using that data.

Keep only `vmlinux` entries needed by the feature and pin the profile with:

```sh
sha256sum production.symvers >production.symvers.sha256
tools/rx3_kernel/validate-symvers.py profile \
  production.symvers production.symvers.sha256
```

The checksum detects accidental profile changes; it does not attest the source
of the CRCs. Each feature recipe's README must record how its production table
was recovered, the firmware and kernel release it was matched against, and any
device loading used to validate the finished modules. Review that evidence when
adding or changing a profile.
