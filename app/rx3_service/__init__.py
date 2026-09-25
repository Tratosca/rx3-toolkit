# SPDX-License-Identifier: MPL-2.0
"""What the application can do, named once, with no interface attached.

Every operation here takes plain values and returns plain values. Nothing opens
a dialog, nothing draws, nothing assumes a window exists. A window calls these;
so does a test, and so would a second window written in something else.

This exists because the panes had grown into the place where the work happens.
Naming the operations separately is what makes a screen cheap to add, and it is
also the only part of an interface decision that survives changing it.
"""
