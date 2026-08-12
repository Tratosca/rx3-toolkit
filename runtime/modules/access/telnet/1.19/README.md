# Diagnostic access, firmware 1.19

`module.sh` starts the BusyBox Telnet daemon after `rbp` has been restarted and
adds pseudo-terminal entries to the volatile `/etc/securetty` copy. It changes
neither NAND nor the firmware image stored on the unit.

Telnet is unencrypted. Use this module only on an isolated, trusted link and
omit it from the packaged image when diagnostic access is unnecessary.
