# SPDX-License-Identifier: MPL-2.0
import pathlib
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from app.services import key_match
from app.localization import LocalizedError
from app.ui.bridge import Bridge
from app.runtime import build
from tests import test_framework

class KeyMatchTests(unittest.TestCase):
    run_units = test_framework.FrameworkTests.run_units

    def test_rules_and_build_configuration(self):
        self.assertEqual(key_match.files(), {'rules.txt': b'0\n'})
        for saved in range(16):
            self.assertEqual(key_match.files(saved), {'rules.txt': f'{saved & 14}\n'.encode()})
        for bad in (True, None, -1, 16, '3', '$(id)'):
            with self.assertRaises(LocalizedError): key_match.files(bad)
        result=SimpleNamespace(output='autoexec.bin',size=1,sha256='x',patches=('key-match',))
        bridge=Bridge()
        with patch('app.ui.bridge.build_module.build_runtime',return_value=result) as writer, patch.object(bridge,'_settle'):
            bridge._build('1.19',['key-sync'],pathlib.Path('key'),pathlib.Path('.'),None,build.Cancellation(),1,'identical',15)
        self.assertEqual(writer.call_args.kwargs['supplied_files'],{'key-match':{'rules.txt':b'14\n'}, 'key-sync': {'sync-range.txt': b'1\n', 'sync-mode.txt': b'identical\n'}})

    def test_harmonic_modules_have_independent_selection_and_sync_dependencies(self):
        definitions = build.discover_patches(None, '1.19')
        expected = {'keyshift': ['core', 'keyshift'], 'key-match': ['core', 'key-match'],
                    'key-sync': ['core', 'keyshift', 'key-match', 'key-sync']}
        for selected, ids in expected.items():
            self.assertEqual([p.patch_id for p in build.resolve_patches(definitions, [selected])], ids)
        bridge = Bridge()
        enabled = bridge.mod_selection('1.19', [], 'key-sync', True)['value']
        self.assertEqual(set(enabled), set(expected['key-sync']))
        for dependency in ('keyshift', 'key-match'):
            disabled = bridge.mod_selection('1.19', enabled, dependency, False)['value']
            self.assertNotIn('key-sync', disabled)
        self.assertNotIn('key-match', build.required_closure(definitions, ['keyshift']))

    def test_directed_harmonic_rules_exhaustively(self):
        self.run_units(r'''
#include "core/api/rx3_harmony.h"
int main(void) {
    assert(rx3_match_rules(0)==2 && rx3_match_rules("")==2);
    assert(rx3_match_rules("15")==14 && rx3_match_rules("1")==0);
    assert(rx3_match_rules("16")==2 && rx3_match_rules("2x")==2);
    assert(rx3_match_rules("-1")==2 && rx3_match_rules("$(id)")==2);
    for(int a=0;a<24;a++)for(int b=0;b<24;b++)for(unsigned mask=0;mask<16;mask++) {
        int delta=(b/2-a/2+12)%12;
        int expected=0;
        if((a%2)==(b%2)) {
            if((mask&2)&&delta==2)expected=2;
            if((mask&4)&&delta==7)expected=4;
            if((mask&8)&&delta==4)expected=8;
        }
        if(rx3_camelot_compatible(a,b))expected=0;
        assert(rx3_camelot_extended(a,b,mask)==expected);
    }
    assert(!rx3_camelot_extended(14,13,15)); /* 8A -> 7B: no added diagonal */
    assert(!rx3_camelot_extended(13,14,15));
    assert(!rx3_camelot_extended(14,17,1)); /* opposite diagonal */
    assert(rx3_camelot_extended(14,18,2)); /* 8A -> 10A */
    assert(!rx3_camelot_extended(18,14,2)); /* energy is directed */
    assert(!rx3_camelot_extended(-1,0,15));assert(!rx3_camelot_extended(0,24,15));
    return 0;
}
''',[])

    def test_shell_migrates_saved_rules_without_executing_them(self):
        script = pathlib.Path('mod/modules/key-match/module.sh').read_text()
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            config = root / 'rules.txt'
            core = root / 'core'
            core.write_bytes(b'x')
            script = script.replace('/mnt/iso/modules/key-match/rules.txt', str(config))
            prefix = f'CORE_OBJECT="{core}"\n' + '''module_begin(){ :; }
register_prepare_hook(){ :; }
module_disabled_by_switch(){ return 1; }
module_export(){ printf '%s=%s\\n' "$1" "$2"; }
'''
            cases = [(None, 2), *[(str(n), n & 14) for n in range(16)],
                     ('16', 2), ('$(touch injected)', 2)]
            for raw, expected in cases:
                if raw is not None:
                    config.write_text(raw + '\n')
                result = subprocess.run(['sh'], input=prefix + script + '\nkey_match_prepare\n',
                                        text=True, capture_output=True, check=True, cwd=temp)
                self.assertIn(f'RX3_KEY_MATCH_RULES={expected}\n', result.stdout)
                self.assertFalse((root / 'injected').exists())

    def test_native_module_classifies_without_touching_green_or_unknown(self):
        self.run_units(r'''
#include "core/api/rx3_module_api.h"
#include "key-match/rx3_key_match_module.c"
static unsigned installs,removed,fail_install,draw_category=120,draw_image=0xa12;
static unsigned registered,fail_registration;
static struct {unsigned source;uint16_t from,to;} variants_seen[24];
static int shown;
static int native_icon(unsigned c,int selected,int side){(void)selected;return side?228:(c==52?227:225);}
static int native_show(void *w,int object,int im){(void)w;(void)object;shown=im;return 1;}
static void native_set(unsigned side,unsigned row){(void)row;assert(icon(draw_category,0,side)==227);show_icon(0,0,draw_image);}
static int install(struct installed_hook *h,unsigned long addr,const uint8_t g[8],void *r,void *o){
    (void)h;(void)g;assert(r);installs++;
    void *original=0;
    if(installs!=fail_install) {
        if(addr==SET_ICON)original=(void *)native_set;
        else if(addr==SHOW_ICON)original=(void *)native_show;
        else {assert(addr==ICON_ID);original=(void *)native_icon;}
    }
    memcpy(o,&original,sizeof(original));return original!=0;
}
static int detach(struct installed_hook *h){(void)h;return 1;}
static unsigned reg(const void *o,unsigned source,uint16_t from,uint16_t to){
    assert(o && registered<24);
    if(++registered==fail_registration)return 0;
    if(source==227)assert(from==7755);
    else assert(source>=0xa0f&&source<=0xa13&&from==2016);
    variants_seen[registered-1].source=source;
    variants_seen[registered-1].from=from;variants_seen[registered-1].to=to;
    return 0x1700+registered-1;
}
static void unreg(const void *o){assert(o);removed++;registered=0;}
static int add_marker(const void *o,const struct rx3_browse_marker *m){assert(o&&m==&markers);return 1;}
static void remove_marker(const void *o){assert(o);}
static const struct rx3_browse_service browse={.marker=add_marker,.unregister_owner=remove_marker};
static const struct rx3_image_service images={.register_recolour=reg,.unregister_owner=unreg};
static const struct rx3_services api={.install_hook=install,.detach_hook=detach,.release_hook=detach,.images=&images,.browse=&browse};
static void expect_colour(unsigned id,unsigned source,uint16_t rgb){
    assert(id>=0x1700 && id<0x1700+registered);
    assert(variants_seen[id-0x1700].source==source && variants_seen[id-0x1700].to==rgb);
}
int main(void){
    unsetenv("RX3_KEY_MATCH");assert(!configured());setenv("RX3_KEY_MATCH","1",1);assert(configured());
    setenv("RX3_KEY_MATCH_RULES","15",1);assert(start(&api));assert(rules==14 && registered==19);
    unsigned categories[]={KEY_YELLOW,KEY_ORANGE,KEY_RED};
    unsigned candidates[]={19,5,23}; /* from 8A: 10A, 3A, 12A */
    uint16_t rgb[]={0xffe0,0xfc00,0xf800};
    for(unsigned c=0;c<3;c++) {
        assert(category(15,candidates[c],7)==categories[c]);
        assert(category(15,candidates[c],15)==categories[c]);
        assert(category(15,candidates[c],52)==52); /* native green wins */
        expect_colour(badge(categories[c]),227,rgb[c]);
        draw_category=categories[c];
        for(unsigned selected=0;selected<2;selected++) {
            assert(icon(categories[c],selected,0)==227);
            assert(icon(categories[c],selected,1)==228); /* native side policy */
        }
        for(draw_image=0xa0f;draw_image<=0xa13;draw_image++) {
            set_icon(0,0);expect_colour(shown,draw_image,rgb[c]);
            assert(!composing && !pending_colour);
            show_icon(0,0,draw_image);assert(shown==(int)draw_image);
        }
    }
    draw_image=0xa12;draw_category=52;set_icon(0,0);assert(shown==0xa12);
    assert(category(15,15,15)==15);expect_colour(badge(52),227,0x07e0);
    assert(!badge(7) && !badge(119) && !badge(123));
    assert(category(0,19,7)==7 && category(15,0,7)==7);
    assert(category(25,19,7)==7 && category(15,25,7)==7);
    /* F# (2B) -> Abm (1A) and Bbm (3A): never add a diagonal marker. */
    assert(category(4,1,7)==7 && category(4,5,7)==7);
    assert(category(4,1,52)==52 && category(4,5,52)==52);
    for(unsigned mask=0;mask<16;mask++) {
        rules=mask;
        for(unsigned c=0;c<3;c++)
            assert(category(15,candidates[c],7)==((mask&(2u<<c))?categories[c]:7));
    }
    stop();assert(removed==1 && !registered);
    setenv("RX3_KEY_MATCH_RULES","1",1);assert(start(&api));assert(rules==0);stop();
    setenv("RX3_KEY_MATCH_RULES","bad",1);assert(start(&api));assert(rules==2);stop();
    unsetenv("RX3_KEY_MATCH_RULES");assert(start(&api));assert(rules==2);stop();
    for(unsigned failure=1;failure<=3;failure++) {
        installs=0;fail_install=failure;assert(!start(&api));stop();assert(!registered);
    }
    fail_install=0;
    for(unsigned failure=1;failure<=19;failure++) {
        installs=0;fail_registration=failure;assert(!start(&api));stop();assert(!registered);
    }
    return 0;
}
''',[])

    def test_recoloured_image_preserves_mask_and_bounds(self):
        self.run_units(r'''
#include "core/services/rx3_images.c"
static struct {uint32_t record[11];uint16_t pixels[4];} fixture;
static void *lookup(unsigned id){assert(id==227);return fixture.record;}
int main(void){
    assert(IMAGE_LIMIT>=19); /* all three colours, native states and badges fit */
    assert(recolour(0x07e0,0x07e0,0xffe0)==0xffe0);
    assert(recolour(0x07e0,0x07e0,0xf800)==0xf800);
    assert(recolour(0x07e0,0x07e0,0xfc00)==0xfc00);
    assert(recolour(0x03e0,0x07e0,0xfc00)==0x7a00); /* antialiasing */
    assert(recolour(0xf81f,0x07e0,0xfc00)==0xf81f); /* key mask */
    const unsigned char owner=1,other=2;
    uint8_t *record=(void *)fixture.record;
    uint16_t w=2,h=2;uint32_t offset=44;
    memcpy(record+4,&w,2);memcpy(record+6,&h,2);memcpy(record+32,&offset,4);record[24]=2;
    fixture.pixels[0]=0xf81f;fixture.pixels[1]=7755;fixture.pixels[2]=0xffff;fixture.pixels[3]=0;
    assert(!rx3_images.register_recolour(0,227,7755,0xfc00));
    unsigned id=rx3_images.register_recolour(&owner,227,7755,0xfc00);assert(id && rx3_image_count()==1);
    assert(rx3_image_resolve(id,lookup,&fixture));
    uint32_t resolved;memcpy(&resolved,(uint8_t *)variants[0].record+12,4);
    assert(resolved==(uint32_t)(unsigned long)variants[0].pixels);
    assert(variants[0].pixels[0]==0xf81f && variants[0].pixels[1]==0xfc00);
    assert(variants[0].pixels[2]==0xffff && variants[0].pixels[3]==0);
    rx3_images.unregister_owner(&other);assert(rx3_image_count()==1);
    w=1025;memcpy(record+4,&w,2);assert(!rx3_image_resolve(id,lookup,&fixture));
    rx3_images.unregister_owner(&owner);assert(!rx3_image_count());assert(!rx3_image_resolve(id,lookup,&fixture));
    for(unsigned i=0;i<IMAGE_LIMIT;i++)assert(rx3_images.register_recolour(&owner,227,7755,0xfc00));
    assert(!rx3_images.register_recolour(&owner,227,7755,0xfc00));
    return 0;
}
''',[])
