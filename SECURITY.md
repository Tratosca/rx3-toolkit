# Security

Do not open an issue containing an encryption key, firmware image, dump,
credential, or personal data. Treat an exposed key as compromised; deleting it
from a commit does not remove it from Git history.

The runtime rejects unknown executable hashes and function prologues and
requires a RAM-backed effective root mount before modification. Changes to
these checks require validation against the exact target binary and hardware.

## Reporting

Report a vulnerability through GitHub's private security advisory form on this
repository, under Security, Report a vulnerability. Do not open a public issue.

`[TODO: verify with maintainer]` No response or disclosure timeline is committed
to yet.
