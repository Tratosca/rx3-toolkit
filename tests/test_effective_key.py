# SPDX-License-Identifier: MPL-2.0
"""The key a deck is heard in once the tempo fader moves the pitch."""

import unittest

from tests import test_framework


class EffectiveKeyTests(unittest.TestCase):
    run_units = test_framework.FrameworkTests.run_units

    def test_tempo_moves_the_key_by_the_nearest_semitone(self):
        self.run_units(r'''
#include "keyshift/rx3_keyshift_module.c"
static int semis(int rate){int s=(int)(keyshift_effective_shift(rate)&0xffu);return s>=128?s-256:s;}
static int marked(int rate){return (keyshift_effective_shift(rate)&0x100u)!=0;}
int main(void) {
    /* Tempo in 0.01 %: 595 is +5.95 %, one semitone up. */
    assert(semis(0)==0 && !marked(0));
    assert(semis(595)==1 && !marked(595));
    assert(rx3_camelot_shifted(8,semis(595))==22); /* 5A heard as 12A */
    assert(semis(-561)==-1 && !marked(-561));
    assert(semis(300)==1 && marked(300));      /* +3 %: half a semitone, shown with "~" */
    assert(semis(145)==0 && marked(145));      /* just past a quarter semitone */
    assert(semis(1600)==3 && marked(1600));
    assert(semis(10000)==12 && !marked(10000)); /* WIDE top: one octave */
    assert(semis(-5000)==-12 && !marked(-5000));
    assert(semis(-9999)==-24 && marked(-9999));
    effective_enabled=1;effective_state[1]=keyshift_effective_shift(595);
    assert(keyshift_tempo_semitones(1)==1 && keyshift_tempo_semitones(0)==0);
    effective_enabled=0;
    assert(keyshift_tempo_semitones(1)==0);    /* switched off: the analysed key */
    return 0;
}
''', [], flags=('-Wno-unused-function',))


if __name__ == "__main__":
    unittest.main()
