# SPDX-License-Identifier: MPL-2.0
"""Executable ownership rules: modules reach the core through its public API only."""
import json
import pathlib
import re
import unittest

from tests import test_framework

MODULES = test_framework.MODULES
from tests.test_runtime_transitions import function



class ModuleBoundaryTests(unittest.TestCase):
    run_units = test_framework.FrameworkTests.run_units

    def test_all_module_includes_respect_public_api(self):
        for source in MODULES.rglob('*'):
            if source.suffix not in ('.h', '.c'):
                continue
            origin = source.relative_to(MODULES)
            for name in re.findall(r'^\s*#\s*include\s*"([^"]+)"', source.read_text(), re.M):
                target = (source.parent / name).resolve()
                with self.subTest(source=str(origin), include=name):
                    self.assertTrue(target.is_file(), 'unresolved local include')
                    self.assertTrue(target.is_relative_to(MODULES), 'include escapes module tree')
                    dest = target.relative_to(MODULES)
                    if origin.parts[:2] == ('core', 'api'):
                        self.assertEqual(dest.parts[:2], ('core', 'api'), 'public API exposes private implementation')
                    if origin.parts[0] == dest.parts[0]:
                        continue
                    # The core never includes a module; a module sees only the API.
                    self.assertNotEqual(origin.parts[0], 'core', 'core includes module code')
                    self.assertEqual(dest.parts[:2], ('core', 'api'), 'module depends on a sibling or core internals')

    def test_core_assets_are_shared_only_and_every_asset_has_one_package_owner(self):
        self.assertEqual({p.name for p in (MODULES/'core/assets').iterdir()}, {
            'glyph-atlas-dark.rgb565', 'glyph-atlas-light.rgb565',
            'status-none-selected.rgb565', 'status-none-selected-light.rgb565',
        })
        declared = set()
        for manifest in MODULES.glob('*/manifest.json'):
            for record in json.loads(manifest.read_text())['files']:
                source = (manifest.parent / record['source']).resolve()
                self.assertTrue(source.is_relative_to(manifest.parent), 'module packages foreign content')
                self.assertNotIn(source, declared)
                declared.add(source)
        for asset in MODULES.glob('*/assets/*'):
            self.assertIn(asset, declared, f'unpackaged asset: {asset}')
        self.assertIn('rx3_asshole_artwork.h', json.loads((MODULES/'asshole-mode/manifest.json').read_text())['build_files'])
        for source in (MODULES/'core').rglob('*'):
            if source.suffix in ('.c', '.h'):
                text = source.read_text()
                self.assertNotIn('title_eye_coverage', text)
                self.assertNotIn('rx3-samples-selected.rgb565', text)
                self.assertNotIn('rx3-key-selected.rgb565', text)
                self.assertNotIn('rx3-stems-selected.rgb565', text)

    def test_tab_slots_have_one_owner_and_use_that_owners_packaged_assets(self):
        slots = set()
        for manifest in MODULES.glob('*/manifest.json'):
            data = json.loads(manifest.read_text())
            packaged = {item['target'] for item in data['files']}
            script = (manifest.parent/'module.sh').read_text()
            for owner, slot, name in re.findall(r'^\s*stage_panel_asset (\S+) (\d+) (\S+) \|\|', script, re.M):
                self.assertEqual(owner, data['id'])
                self.assertNotIn(slot, slots)
                slots.add(slot)
                self.assertIn(name+'.rgb565', packaged)
                self.assertIn(name+'-light.rgb565', packaged)
        self.assertEqual(slots, {f'{i:02d}' for i in range(11)})

    def test_asshole_module_links_alone_and_releases_partial_artwork(self):
        self.run_units(r'''
#include "core/api/rx3_module_api.h"
extern const struct rx3_module rx3_asshole_module;
static const struct rx3_title_provider *policy;
static const void *owner;
static unsigned registrations, removals, releases, fail_at, reject;
static unsigned bitmap(const void *who,unsigned source,const uint16_t *pixels,unsigned w,unsigned h) {
 assert(who && source==0xbf3 && pixels && w==26 && h==24);
 registrations++;return registrations==fail_at?0:0x1700+registrations;
}
static void remove_images(const void *who){assert(who);removals++;}
static int acquire(const void *who,const struct rx3_title_provider *p) {
 assert(who && p && p->image(0,0) && p->image(0,1));
 if(reject)return 0;owner=who;policy=p;return 1;
}
static void release(const void *who){releases++;if(who==owner){owner=0;policy=0;}}
static const struct rx3_image_service images={.register_bitmap=bitmap,.unregister_owner=remove_images};
static const struct rx3_title_service titles={acquire,release};
int main(void) {
 struct rx3_services s={.images=&images,.titles=&titles};
 assert(rx3_asshole_module.start(&s));assert(registrations==4 && policy);
 assert(!policy->hidden(0) && !policy->hidden(1));unsigned image=policy->image(0,0);
 policy->activate(0);assert(policy->hidden(0) && !policy->hidden(1));
 assert(policy->image(0,0)!=image && policy->image(0,1)!=policy->image(0,0));
 rx3_asshole_module.stop();assert(!policy && removals==1 && releases==1);
 fail_at=registrations+2;assert(!rx3_asshole_module.start(&s));
 rx3_asshole_module.stop();assert(!policy && removals==2 && releases==2);
 fail_at=0;reject=1;assert(!rx3_asshole_module.start(&s));
 rx3_asshole_module.stop();assert(!policy && removals==3);
 reject=0;assert(rx3_asshole_module.start(&s));assert(!policy->hidden(0));
 rx3_asshole_module.stop();return 0;
}
''', ['asshole-mode/rx3_asshole_module.c'])

    def test_tab_loader_reads_only_selected_contributions_and_rejects_missing_assets(self):
        self.run_units(r'''
#include <fcntl.h>
#define TAB_IMAGE_COUNT 11u
#define TAB_IMAGE_BYTES 18000u
static uint8_t tab_image_pixels[11][18000],light_tab_image_pixels[11][18000];
static unsigned light_tab_assets_ready,opened,missing_light,missing_dark;
static const char *configuration(const char *key) {
 if(!strcmp(key,"RX3_TAB_DARK_10"))return "stems-dark";
 if(!strcmp(key,"RX3_TAB_LIGHT_10"))return missing_light?0:"stems-light";
 return 0;
}
static int open_image(const char *path,int flags) {
 assert(flags==O_RDONLY);opened++;
 if(!strcmp(path,"stems-dark"))return missing_dark?-1:4;
 assert(!strcmp(path,"stems-light"));return 5;
}
static int read_exactly(int fd,void *out,size_t n){assert(n==18000);memset(out,fd,n);return 0;}
static int close_image(int fd){assert(fd==4 || fd==5);return 0;}
static void log_line(const char *s){assert(s);}
#define getenv configuration
#define open open_image
#define close close_image
''' + function(MODULES/'core/rx3_core_hook.c', 'load_tab_pixels') + r'''
int main(void) {
 assert(load_tab_pixels() && opened==2 && light_tab_assets_ready);
 assert(tab_image_pixels[10][0]==4 && light_tab_image_pixels[10][0]==5);
 for(unsigned i=0;i<10;i++)assert(!tab_image_pixels[i][0]);
 missing_light=1;assert(load_tab_pixels() && !light_tab_assets_ready && opened==3);
 missing_dark=1;assert(!load_tab_pixels() && opened==4);
 return 0;
}
''', [])

    def test_shell_stages_owned_artwork_and_tracks_generation_without_live_replacement(self):
        import subprocess
        import tempfile
        from tests.test_module_api import HARNESS, MODULE_API
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            package = root/'modules/stems'
            package.mkdir(parents=True)
            dark = package/'example.rgb565'
            light = package/'example-light.rgb565'
            dark.write_bytes(b'dark')
            light.write_bytes(b'light')
            runtime = root/'runtime'
            runtime.mkdir()
            api = root/'module-api.sh'
            api.write_text(MODULE_API.read_text().replace('/mnt/iso/modules/', str(root/'modules')+'/')
                           .replace('/root/pdj/', str(runtime)+'/'))
            body = r'''
rbp_environment_value() {
 case "$1" in
 RX3_TAB_DARK_10) printf %s "$running_dark" ;;
 RX3_TAB_LIGHT_10) printf %s "$running_light" ;;
 esac
}
stage_panel_asset stems 10 example || exit 10
[ "$RUNTIME_STAGE_COUNT" = 2 ] && [ "$NEED_RBP_RESTART" = 1 ] || exit 11
[ ! -e "$RX3_TAB_DARK_10" ] || exit 12
commit_runtime_stage && discard_runtime_stage || exit 13
[ "$(cat "$RX3_TAB_DARK_10")" = dark ] || exit 14
running_dark=$RX3_TAB_DARK_10
running_light=$RX3_TAB_LIGHT_10
NEED_RBP_RESTART=0
stage_panel_asset stems 10 example || exit 15
[ "$RUNTIME_STAGE_COUNT" = 0 ] && [ "$NEED_RBP_RESTART" = 0 ] || exit 16
printf changed > "PACKAGE/example.rgb565"
stage_panel_asset stems 10 example || exit 17
[ "$RUNTIME_STAGE_COUNT" = 1 ] && [ "$NEED_RBP_RESTART" = 1 ] || exit 18
[ "$(cat "$RX3_TAB_DARK_10")" = dark ] || exit 19
discard_runtime_stage
rm "PACKAGE/example-light.rgb565"
stage_panel_asset stems 10 example || exit 20
[ -z "$RX3_TAB_LIGHT_10" ] || exit 21
discard_runtime_stage
rm "PACKAGE/example.rgb565"
if stage_panel_asset stems 10 example; then exit 22; fi
'''.replace('PACKAGE',str(package))
            result = subprocess.run(['sh','-s','--',str(api)],input=HARNESS+body,
                                    capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
