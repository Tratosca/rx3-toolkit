<!-- SPDX-License-Identifier: MPL-2.0 -->
# Decoder wait

The Toolkit exposes this setting under Modules > Advanced. It is enabled by default and required by both Beat Jump modules. The control is locked while either module needs it; otherwise it can be switched independently.

After rbp starts, `apply.sh` waits up to 20 seconds for the internal UDP console on port 20000. It sends `bufsleep 0 100000` and `bufsleep 1 100000` over loopback, setting each deck's decoder sleep interval to 100,000 nanoseconds (100 microseconds), versus the documented stock interval of 1 millisecond. `DECODER_SLEEP_NS` can override that value.

This reduces the wait between decoder retries. It does not change Beat Jump distances or the delay between successive Beat Jump commands. More frequent retries can improve audio recovery after a jump or seek, at the cost of more CPU wakeups. The end-to-end improvement has not been measured here.

The setting is volatile and resets at power-off. It does not modify flash or executable bytes. The helper receives one datagram of up to 4096 bytes, waits at most five polling intervals of one second, and fails on an empty reply, timeout or transport error. Its receive child and temporary file are cleaned up on exit. The script logs responses but does not validate their content or read the configured value back: it reports responses received and explicitly leaves application unverified. If the console or Bash is unavailable, it logs a failure and leaves the runtime running.

See [Faster decoder polling](../../../REFERENCES.md#8-faster-decoder-polling).
