<!-- SPDX-License-Identifier: MPL-2.0 -->
# Local artifacts

A few tools under `tools/` read files this repository does not ship. Those files are yours: they live on your machine, they are produced there, and nothing here records or transmits anything about them.

So that no tool has to hardcode a place on somebody's disk, each such file is named by the **role** it fills, and the roles are mapped to paths by `tools/rx3_artifacts.py`.

## Roles

| Role | What the tool needs it to be |
| --- | --- |
| `imagedata` | The flat images array the player indexes to find a bitmap (logos, buttons) |
| `rbp` | The player application binary, as an ELF file |

## Where a role is looked up

The environment first, then the file. A role that neither names is not configured, and the tool says so rather than guessing.

1. **The role's environment variable**, spelled out in the table above: `RX3_IMAGE_DATA` for `imagedata`, `RX3_RBP` for `rbp`. Useful for a one-off run.
2. **`artifacts.toml`**, at the root of the checkout.

## `artifacts.toml`

This file is gitignored and stays that way. It is the one file in the checkout that says anything about how you have arranged your own machine, and it is of no use to anybody else.

```toml
# Absolute paths and ~ both work. Any role left out is simply not configured.
[artifacts]
imagedata = "~/lab/rx3/imagedata"
rbp = "~/lab/rx3/rbp"
```

## When a file is missing

The tool stops and tells you which role it wanted, what that file has to be, and where it looked. It will not tell you where to get one: that is outside what this project does, and the answer depends on equipment you either have or do not.
