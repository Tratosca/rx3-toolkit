# Decoder polling interval, firmware 1.19

This module reduces the time for which the RX3 decoder thread sleeps between
iterations of its stream-reading loop. Its purpose is to make decoded audio
become available sooner after a seek or a large Beat Jump, where the stock
1 ms polling interval can contribute to a perceptible delay while the reader
refills or catches up.

The module changes the interval from `1000000` ns (1 ms) to `100000` ns
(0.1 ms) on both decks. This increases the decoder's polling frequency by a
factor of ten. It does **not**:

- enlarge the audio ring buffer;
- change Beat Jump distance, Quantize, or grid calculations;
- preload an entire track;
- guarantee a fixed 0.9 ms reduction in end-to-end audio latency.

The effective improvement depends on whether decoder scheduling is the active
bottleneck. More frequent wake-ups can also increase CPU usage. The 0.1 ms
value is therefore a responsiveness trade-off, not a general buffer-size
optimization.

This is a volatile runtime setting, not a binary patch. Power cycling restores
the stock value. `module.sh` registers `apply.sh` as a post-launch action with
the root runtime orchestrator.

The observed command path is:

```text
UDP 127.0.0.1:20000
  -> allinone_debug::bufsleep
  -> playengine::Player::setDecoderSleep
```

A different positive interval can be supplied explicitly:

```sh
./apply.sh 100000 /tmp/decoder-sleep.log
```

The script waits up to 20 seconds for the local debug console, validates the
interval, applies `bufsleep 0 <ns>` and `bufsleep 1 <ns>`, and reports failure
without modifying an executable or persistent storage. A failure leaves `rbp`
running with its existing decoder interval.
