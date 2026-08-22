<!-- SPDX-License-Identifier: MPL-2.0 -->
# 🔌 Diagnostic Telnet access

Opens a shell on the player, over the rear computer USB port, for poking around.

**You almost certainly do not want this.** It is off by default and it should
stay off unless you are debugging something and know what you are looking for.

> [!WARNING]
> Telnet is unencrypted — everything, including the login, crosses the wire in
> plain text. Use it on a direct, isolated cable and nothing else. Never on a
> venue network, never on anything shared.

The root password is not distributed here, and asking for it in an issue will not
produce one.

Like everything else in this project, it changes nothing permanent: the service
runs from memory and disappears when you power off.

## If you are reporting a bug

You probably want **Session logging** instead. It writes what happened to the
stick, which is what a bug report actually needs, and it does not open a shell on
your player.
