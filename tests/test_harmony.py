# SPDX-License-Identifier: MPL-2.0
"""The preview and both firmware clients must agree on the same policy."""
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from app.services import keyshift
from tests import test_framework

ROOT = pathlib.Path(__file__).resolve().parents[1]

class HarmonyTests(unittest.TestCase):
    run_units = test_framework.FrameworkTests.run_units

    def test_native_reference_tracks_master_and_preserves_native_key_set(self):
        self.run_units(r'''
#include "core/services/rx3_browse.c"
int install_hook(struct installed_hook *h,unsigned long a,const uint8_t g[8],void *r,void *o){(void)h;(void)a;(void)g;(void)r;(void)o;return 0;}
int hook_is_installed(const struct installed_hook *h){return h->record!=0;}
int detach_hook(struct installed_hook *h){(void)h;return 1;}
int release_hook(struct installed_hook *h){(void)h;return 1;}
static int selected_master;
static unsigned master(unsigned deck){return (int)deck==selected_master;}
int main(void) {
    uint8_t context[0x10b20]={0};master_on=master;
    assert(harmonic_reference().key==-1);
    context[0x10afc]=11;
    /* Preserve an observed native set including cross-letter neighbours. */
    unsigned native[]={4,1,3,5};
    for(unsigned i=0;i<4;i++)put_word(context+0x10b08+i*4,native[i]);
    observe_harmony(context);
    struct rx3_harmonic_reference ref=harmonic_reference();
    assert(ref.deck==0 && ref.key==3);
    assert(ref.native_keys==((1u<<3)|(1u<<0)|(1u<<2)|(1u<<4)));
    assert(rx3_harmonic_accepts(3,0,ref.native_keys,0));
    assert(!rx3_harmonic_accepts(3,1,ref.native_keys,0));
    publish_key(0,3,1);ref=harmonic_reference();
    assert(ref.key==17);
    assert(ref.native_keys==((1u<<17)|(1u<<14)|(1u<<16)|(1u<<18)));
    selected_master=1;assert(harmonic_reference().key==-1);
    /* Same USB source, different MASTER deck. */
    observe_harmony(context);assert(harmonic_reference().deck==1);
    selected_master=-1;assert(harmonic_reference().key==-1);
    selected_master=1;publish_key(1,-1,0);assert(harmonic_reference().key==-1);
    observe_harmony(context);publish_key(1,6,0);assert(harmonic_reference().key==6);
    assert(harmonic_reference().native_keys==((1u<<6)|(1u<<7)|(1u<<4)|(1u<<8)));
    selected_master=0;assert(harmonic_reference().key==17);
    selected_master=1;assert(harmonic_reference().key==6);
    context[0x10afc]=41;publish_key(1,3,0);observe_harmony(context);
    assert(harmonic_reference().key==3); /* storage location is irrelevant */
    return 0;
}
''', [])

    @unittest.skipUnless(shutil.which('clang'), 'C compiler required for solver parity')
    def test_preview_matches_runtime_for_all_keys_modes_and_rule_sets(self):
        source = r'''
#include <stdio.h>
#include "core/api/rx3_harmony.h"
int main(void) {
    const unsigned ranges[]={1,3,12};
    for(int reference=0;reference<24;reference++) {
        unsigned native=(1u<<reference)|(1u<<((reference+1)%24))|(1u<<((reference+3)%24));
        for(int track=0;track<24;track++)for(unsigned rules=0;rules<16;rules+=2)
        for(int mode=0;mode<2;mode++)for(unsigned r=0;r<3;r++)for(int shift=-12;shift<=12;shift+=12)
            putchar(12+rx3_harmonic_delta(track,shift,reference,native,rules,ranges[r],mode));
    }
    return 0;
}
'''
        expected = bytearray()
        for reference in range(24):
            native = (reference, (reference + 1) % 24, (reference + 3) % 24)
            for track in range(24):
                for rules in range(0, 16, 2):
                    for mode in ('identical', 'harmonic'):
                        for limit in (1, 3, 12):
                            for shift in (-12, 0, 12):
                                expected.append(12 + keyshift.preview_delta(track, reference, native, rules, limit, mode, shift))
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder)
            (path/'solver.c').write_text(source)
            subprocess.run(['clang','-std=c11','-O2','-Wall','-Werror','-I',str(ROOT/'mod/modules'),str(path/'solver.c'),'-o',str(path/'solver')],check=True,capture_output=True)
            actual = subprocess.run([str(path/'solver')],check=True,capture_output=True).stdout
        self.assertEqual(actual, expected)

    def test_preview_changes_with_mode_range_and_selected_rules(self):
        self.assertEqual(keyshift.preview()['target'], '9A')
        self.assertIsNone(keyshift.preview(mode='identical')['target'])
        self.assertEqual(keyshift.preview(6, 'identical')['shift'], 6)
        self.assertEqual([row['colour'] for row in keyshift.preview(rules=14)['rows']],
                         ['green','green',None,'yellow','orange','red',None,'green','green','green','yellow','red'])

    def test_preview_always_shows_every_colour_without_track_names(self):
        reference = keyshift.preview(rules=0)['rows']
        self.assertEqual({r['colour'] for r in reference}, {None, 'green', 'yellow', 'orange', 'red'})
        for rules in range(16):
            self.assertEqual(keyshift.preview(rules=rules)['rows'], reference)
        self.assertTrue(all(set(row) == {'number', 'key', 'colour'} for row in reference))
