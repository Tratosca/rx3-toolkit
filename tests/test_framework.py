# SPDX-License-Identifier: MPL-2.0
"""Compile the public contracts without the performance implementation."""
import pathlib
import shutil
import subprocess
import tempfile
import unittest

from app.runtime.build import compile_arm_hook, discover_patches
from tests.test_hook_symbols import ALLOWED, undefined_symbols

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULES = ROOT / 'mod/modules'


class FrameworkTests(unittest.TestCase):
    def run_units(self, body, units, flags=()):
        if 'core/runtime/rx3_modules.c' in units and 'core/services/rx3_images.c' not in units:
            units = [*units, 'core/services/rx3_images.c']
        if 'core/runtime/rx3_modules.c' in units and 'core/services/rx3_titles.c' not in units:
            units = [*units, 'core/services/rx3_titles.c']
        if 'core/runtime/rx3_modules.c' in units:
            # The service table names every shared service.
            for unit in ('core/services/rx3_input.c', 'core/services/rx3_audio.c',
                         'core/services/rx3_memory.c', 'core/services/rx3_loader.c'):
                if unit not in units:
                    units = [*units, unit]
        compiler = shutil.which('clang') or shutil.which('cc')
        if not compiler:
            self.skipTest('native C compiler required')
        with tempfile.TemporaryDirectory() as temporary:
            directory = pathlib.Path(temporary)
            # Use the host ABI for executable tests; the production build uses
            # the ARM declarations. No firmware entry point is executed here.
            header = directory / 'host.h'
            header.write_text('''
#define RX3_PLATFORM_H
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdlib.h>
#include <assert.h>
#include <sys/types.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <pthread.h>
#include <unistd.h>
extern int gettimeofday(void *, void *);
''')
            source = directory / 'test.c'
            # Services link against the hook and log units. A test that links
            # the real units, or defines its own doubles, replaces these weak
            # ones, which live in a unit of their own for that reason.
            stubs = directory / 'weak_services.c'
            stubs.write_text(r'''
struct installed_hook;
__attribute__((weak)) void *install_hook(struct installed_hook *h, unsigned long a, const uint8_t g[8], void *r) { (void)h; (void)a; (void)g; (void)r; return 0; }
__attribute__((weak)) void *install_pc_ldr_hook(struct installed_hook *h, unsigned long a, const uint8_t g[8], void *r) { (void)h; (void)a; (void)g; (void)r; return 0; }
__attribute__((weak)) int uninstall_hook(struct installed_hook *h) { (void)h; return 1; }
__attribute__((weak)) int detach_hook(struct installed_hook *h) { (void)h; return 1; }
__attribute__((weak)) int release_hook(struct installed_hook *h) { (void)h; return 1; }
__attribute__((weak)) void log_line(const char *s) { (void)s; }
__attribute__((weak)) void rx3_log_number(const char *s, unsigned long v) { (void)s; (void)v; }
''')
            if 'core/runtime/rx3_modules.c' in units:
                body += '\n#include \"core/api/rx3_browse_api.h\"\nconst struct rx3_browse_service rx3_browse={0};\n'
            source.write_text(body)
            binary = directory / 'test'
            subprocess.run([compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                            '-include', str(header), '-I', str(MODULES), *flags,
                            str(source), str(stubs), *(str(MODULES / unit) for unit in units),
                            '-o', str(binary)], check=True, capture_output=True, text=True)
            subprocess.run([str(binary)], check=True, capture_output=True, text=True)

    def test_key_metadata_is_independent_of_drawing_and_load_order(self):
        self.run_units(r'''
#include "keyshift/rx3_keyshift_module.c"
static uint8_t lines[2][568];
static unsigned reads,sets,converts;
static const uint8_t *get_line(unsigned deck) {assert(deck<2);reads++;return lines[deck];}
static void set_line(unsigned deck,unsigned kind,const char *key) {
    uint16_t k=(uint16_t)kind,n=(uint16_t)strlen(key);
    memset(lines[deck],0,568);memcpy(lines[deck]+8,&k,2);memcpy(lines[deck]+32,&n,2);
    for(unsigned i=0;i<n;i++){uint16_t ch=(unsigned char)key[i];memcpy(lines[deck]+34+i*2,&ch,2);}
}
static void info(void *data,unsigned count,unsigned deck) {
    (void)count;sets++;if(deck<2)set_line(deck,15,data?data:"");
}
static void convert(unsigned deck){converts++;if(deck<2)set_line(deck,15,"9A");}
static const struct rx3_services services={0};
int main(void) {
    framework=&services;keyshift_key_line=get_line;
    keyshift_original_info=info;keyshift_original_convert=convert;keyshift_metadata_active=1;
    keyshift_metadata_info("9A",1,1);
    assert(keyshift_track_key[1]==16 && keyshift_track_key[0]==-1);
    keyshift_feature_track_will_load(1,0,0);keyshift_feature_track_did_load(1,0,0);
    assert(keyshift_track_key[1]==16); /* Metadata arrived before decoder. */
    keyshift_feature_track_will_load(0,0,0);keyshift_feature_track_did_load(0,0,0);
    keyshift_metadata_info("1A",1,0);
    assert(keyshift_track_key[0]==0); /* Metadata arrived after decoder. */
    keyshift_metadata_info("8A",1,2);assert(reads==2 && sets==3);
    keyshift_metadata_info(0,0,1);assert(keyshift_track_key[1]==-1 && keyshift_track_key[0]==0);
    keyshift_metadata_convert(1);assert(keyshift_track_key[1]==16 && converts==1);
    keyshift_metadata_info("unknown",1,1);assert(keyshift_track_key[1]==-1);
    set_line(1,4,"1A");keyshift_read_metadata(1);assert(keyshift_track_key[1]==-1);
    static const uint16_t old_key[]={'1','A',0};
    struct rx3_text_observation old={0x1101,{0,310,120,340},old_key,2};
    keyshift_capture_text(&old);assert(keyshift_track_key[1]==-1);
    return 0;
}
''', [], flags=('-Wno-unused-function',))

    def test_keyshift_links_without_core_and_owns_its_panel(self):
        self.run_units(r'''
#include "core/api/rx3_module_api.h"
extern const struct rx3_module rx3_keyshift_module;
static const struct rx3_pad_row *row;
static unsigned installs, detached, released, reject, reject_row;
static void *hook(struct installed_hook *h,unsigned long a,const uint8_t g[8],void *r) {
    (void)h; (void)g; assert(a==0x000a0e54 && r); installs++;
    return reject ? 0 : (void *)1;
}
static int detach(struct installed_hook *h){(void)h;detached++;return 1;}
static int release(struct installed_hook *h){(void)h;released++;return 1;}
static void log_message(const char *s){assert(s);}
static int add(const struct rx3_pad_row *r){if(reject_row)return 0;row=r;return 1;}
static void remove_row(const struct rx3_pad_row *r){if(row==r)row=0;}
static const struct rx3_panel_service panels={add,remove_row,0,0};
static struct rx3_harmonic_reference reference(void) {
    return (struct rx3_harmonic_reference){1,14,(1u<<12)|(1u<<14)|(1u<<15)|(1u<<16)};
}
static const struct rx3_browse_service browse={.reference=reference};
static const struct rx3_services services={.browse=&browse,.install_hook=hook,.log_line=log_message,
    .panels=&panels,.detach_hook=detach,.release_hook=release};
int main(void) {
    unsetenv("RX3_KEYSHIFT");assert(!rx3_keyshift_module.configured());
    setenv("RX3_KEYSHIFT","1",1);assert(rx3_keyshift_module.configured());
    setenv("RX3_KEY_SYNC","1",1);setenv("RX3_KEY_SYNC_RANGE","2",1);setenv("RX3_KEY_SYNC_MODE","harmonic",1);
    setenv("RX3_KEY_MATCH_RULES","0",1);
    assert(rx3_keyshift_module.start(&services));
    assert(row && row->panel_id==1 && installs==1);
    assert(rx3_keyshift_module.audio_started && rx3_keyshift_module.text_observed);
    /* Manual shift and track replacement through public callbacks only. */
    static const uint16_t key0[]={'1','0','A',0}, key1[]={'8','A',0};
    struct rx3_text_observation text={0x1101,{0,90,120,120},key0,3};
    rx3_keyshift_module.text_observed(&text);
    assert(row->needs_refresh() && !row->needs_refresh());
    text.box[1]=310;text.box[3]=340;text.text=key1;text.length=2;
    rx3_keyshift_module.text_observed(&text);
    assert(row->kind(0,1)==RX3_PAD_OUTLINE_BUTTON);
    row->fire(0,1,0); /* 10A -> 8A, minus two semitones. */
    assert(row->caption(0,0,1)[0]=='8' && row->caption(0,0,1)[4]=='-' && row->caption(0,0,1)[5]=='2');
    assert(row->kind(0,1)==RX3_PAD_STATUS && row->caption(0,1,0)[0]=='K' && row->caption(0,1,0)[4]=='M');
    row->fire(0,0,2);assert(row->caption(0,0,1)[4]=='-' && row->caption(0,0,1)[5]=='1');
    rx3_keyshift_module.track_will_load(0,0,0);
    assert(row->caption(0,0,1)[0]=='K' && row->caption(0,0,1)[4]=='-'); /* replaced key remains unknown until observed */
    assert(row->needs_refresh());
    /* Native drawing may publish the new key before the load returns. */
    text.box[1]=90;text.box[3]=120;text.text=key1;text.length=2;
    rx3_keyshift_module.text_observed(&text);
    if(rx3_keyshift_module.track_did_load)rx3_keyshift_module.track_did_load(0,0,0);
    assert(row->caption(0,0,1)[0]=='8' && row->caption(0,0,1)[1]=='A');
    rx3_keyshift_module.stop();assert(!row && detached==1 && released==1);
    reject=1;assert(!rx3_keyshift_module.start(&services));
    rx3_keyshift_module.stop();assert(!row);
    reject=0;reject_row=1;assert(!rx3_keyshift_module.start(&services));
    rx3_keyshift_module.stop();assert(!row && installs==3);
    return 0;
}
''', ['keyshift/rx3_keyshift_module.c'], flags=('-Wno-unused-function',))

    def test_stop_drains_public_notifications_before_module_cleanup(self):
        self.run_units(r'''
#include "core/api/rx3_module_api.h"
#include "core/runtime/rx3_modules.h"
#include <sched.h>
static unsigned entered, finish, done, stopping, stopped, texts, reports, loads;
static int start(const struct rx3_services *s){assert(s->detach_hook && s->release_hook);return 1;}
static void stop(void){assert(__atomic_load_n(&done,__ATOMIC_SEQ_CST));stopped++;}
static void audio(unsigned rate){
    assert(rate==48000);__atomic_store_n(&entered,1,__ATOMIC_SEQ_CST);
    while(!__atomic_load_n(&finish,__ATOMIC_SEQ_CST))sched_yield();
    __atomic_store_n(&done,1,__ATOMIC_SEQ_CST);
}
static void text(const struct rx3_text_observation *t){assert(t->layer==42);texts++;}
static void report(void){reports++;}
static void will_load(unsigned deck,void *reader,const void *info){assert(deck==1 && !reader && !info);loads++;}
static const struct rx3_module module={.version=RX3_MODULE_API_VERSION,
    .size=sizeof(struct rx3_module),.name="observer",.start=start,.stop=stop,
    .audio_started=audio,.text_observed=text,.report=report,.track_will_load=will_load};
const struct rx3_module *const rx3_bundle[]={&module};
const unsigned int rx3_bundle_count=1;
void *install_hook(struct installed_hook *h,unsigned long a,const uint8_t g[8],void *r){
    (void)h;(void)a;(void)g;(void)r;return 0;
}
int uninstall_hook(struct installed_hook *h){(void)h;return 1;}
int detach_hook(struct installed_hook *h){(void)h;return 1;}
int release_hook(struct installed_hook *h){(void)h;return 1;}
void log_line(const char *s){(void)s;}
static void *notify(void *unused){(void)unused;rx3_modules_audio_started(48000);return 0;}
static void *shutdown_modules(void *unused){
    (void)unused;__atomic_store_n(&stopping,1,__ATOMIC_SEQ_CST);rx3_modules_stop();return 0;
}
int main(void){
    struct rx3_text_observation t={.layer=42};
    rx3_modules_text_observed(&t);rx3_modules_report();assert(!texts && !reports);
    rx3_modules_track_will_load(1,0,0);assert(!loads);
    assert(rx3_modules_start()==1 && rx3_modules_uses_audio());
    rx3_modules_text_observed(&t);rx3_modules_report();assert(texts==1 && reports==1);
    rx3_modules_track_will_load(1,0,0);assert(loads==1);
    pthread_t audio_thread,stop_thread;
    assert(!pthread_create(&audio_thread,0,notify,0));
    while(!__atomic_load_n(&entered,__ATOMIC_SEQ_CST))sched_yield();
    assert(!pthread_create(&stop_thread,0,shutdown_modules,0));
    while(!__atomic_load_n(&stopping,__ATOMIC_SEQ_CST))sched_yield();
    usleep(10000);
    __atomic_store_n(&finish,1,__ATOMIC_SEQ_CST);
    pthread_join(audio_thread,0);pthread_join(stop_thread,0);assert(stopped==1);
    rx3_modules_audio_started(48000);rx3_modules_text_observed(&t);rx3_modules_report();
    assert(texts==1 && reports==1 && !rx3_modules_uses_audio());
    rx3_modules_track_will_load(1,0,0);assert(loads==1);
    rx3_modules_stop();assert(stopped==1);return 0;
}
''', ['core/runtime/rx3_modules.c','core/services/rx3_mix_state.c',
              'core/services/rx3_notice.c','core/services/rx3_dsp.c',
              'core/services/rx3_panels.c'], flags=('-pthread',))

    def test_core_does_not_include_or_call_keyshift_implementation(self):
        core = (MODULES/'core/rx3_core_hook.c').read_text()
        self.assertNotIn('../keyshift/', core)
        self.assertNotIn('keyshift_', core)
        module = (MODULES/'keyshift/rx3_keyshift_module.c').read_text()
        self.assertNotIn('../core/services/', module)
        self.assertNotIn('../core/runtime/', module)
        panel = (MODULES/'keyshift/rx3_keyshift_panel.h').read_text()
        self.assertNotIn('performance_refresh_pending', panel)
        self.assertNotIn('overlay_panel', panel)

    def test_lifecycle_failure_is_local_and_stop_runs_in_reverse_order(self):
        self.run_units('''
#include "core/api/rx3_module_api.h"
#include "core/runtime/rx3_modules.h"
static unsigned int enabled=1, fail=1, started[2], stopped[2], sequence;
static int configured(void) { return enabled; }
static int start_a(const struct rx3_services *s) { assert(s->log_line); started[0]++; return 1; }
static int start_b(const struct rx3_services *s) { assert(s->install_hook); started[1]++; return !fail; }
static void stop_a(void) { stopped[0]=++sequence; }
static void stop_b(void) { stopped[1]=++sequence; }
const struct rx3_module rx3_search_module={RX3_MODULE_API_VERSION,sizeof(struct rx3_module),"a",configured,start_a,stop_a,0,0,0,0,0};
const struct rx3_module rx3_now_playing_module={RX3_MODULE_API_VERSION,sizeof(struct rx3_module),"b",configured,start_b,stop_b,0,0,0,0,0};
const struct rx3_module *const rx3_bundle[]={&rx3_search_module,&rx3_now_playing_module};
const unsigned int rx3_bundle_count=2;
void *install_hook(struct installed_hook *h,unsigned long a,const uint8_t g[8],void *r) {
    (void)h;(void)a;(void)g;(void)r; return 0;
}
int uninstall_hook(struct installed_hook *h) { (void)h; return 1; }
int detach_hook(struct installed_hook *h) { (void)h; return 1; }
int release_hook(struct installed_hook *h) { (void)h; return 1; }
void log_line(const char *s) { assert(s); }
int main(void) {
    assert(rx3_modules_start()==1 && started[0]==1 && started[1]==1);
    assert(stopped[0]==0 && stopped[1]==1);
    assert(rx3_modules_failures()==1);
    fail=0; assert(rx3_modules_start()==2 && started[0]==1 && started[1]==2);
    assert(rx3_modules_failures()==0);
    rx3_modules_stop(); assert(stopped[1]==2 && stopped[0]==3);
    rx3_modules_stop(); assert(sequence==3);
    enabled=0; assert(rx3_modules_start()==0); rx3_modules_stop(); assert(sequence==3);
    return 0;
}
''', ['core/runtime/rx3_modules.c', 'core/services/rx3_mix_state.c', 'core/services/rx3_notice.c', 'core/services/rx3_dsp.c', 'core/services/rx3_panels.c'])

    def test_search_module_has_no_link_to_core_state(self):
        self.run_units('''
#include "core/api/rx3_module_api.h"
extern const struct rx3_module rx3_search_module;
static void (*shape)(uint16_t *,void *,int);
static unsigned int calls, removed;
static void original(uint16_t *text,void *context,int length) {
    (void)context; calls++; if(text && length) text[0]=0x00e9;
}
static void *install(struct installed_hook *h,unsigned long a,const uint8_t g[8],void *r) {
    assert(h && a==0x001644fc && g[0]==0x18); shape=r; return original;
}
static int remove_hook(struct installed_hook *h) { assert(h); removed++; return 1; }
static void log_message(const char *s) { assert(s); }
int main(void) {
    struct rx3_services services={.install_hook=install,.detach_hook=remove_hook,.release_hook=remove_hook,.log_line=log_message};
    assert(!rx3_search_module.configured());
    setenv("RX3_SEARCH_LATIN","1",1); assert(rx3_search_module.configured());
    assert(rx3_search_module.start(&services));
    uint16_t text[]={0x00e0,0x0178,0x00f7,0};
    shape(text,0,4); assert(calls==1 && text[0]=='E' && text[1]=='Y' && text[2]==0x00f7);
    shape(0,0,0); assert(calls==2);
    rx3_search_module.stop(); assert(removed==2);
    return 0;
}
''', ['search-latin/rx3_search_module.c'], ['-D_POSIX_C_SOURCE=200809L'])

    def test_hook_ownership_and_failed_restoration_keep_the_trampoline(self):
        self.run_units(r'''
#include "core/services/rx3_hooks.h"
#include "core/firmware/rx3_patch.h"
static uint8_t arena[64][4096];
static unsigned int allocated, freed, writes;
static int fail_write, fail_release;
void *mmap(void *a,size_t n,int p,int f,int d,off_t o) {
    (void)a;(void)p;(void)f;(void)d;(void)o;
    assert(n==4096 && allocated<64); return arena[allocated++];
}
int munmap(void *p,size_t n) { assert(p && n==4096); if(fail_release)return -1; freed++; return 0; }
int mprotect(void *p,size_t n,int f) { (void)p;(void)n;(void)f; return 0; }
void clear_instruction_cache(unsigned long a,unsigned long b) { assert(b>a); }
int write_code(unsigned long address,const void *bytes,size_t n) {
    assert(n==8); if(fail_write)return -1; memcpy((void *)address,bytes,n); writes++;return 0;
}
int main(void) {
    uint32_t code[4]={1,2,3,4};
    uint8_t guard[8];memcpy(guard,code,8);
    struct installed_hook first={0}, second={0};
    void *original=install_hook(&first,(unsigned long)code,guard,(void *)1234);
    assert(original && allocated==1 && hook_is_installed(&first));
    assert(!install_hook(&first,(unsigned long)(code+2),guard,(void *)1234));
    /* Even a guard matching the detour cannot stack a second owner. */
    uint8_t patched[8];memcpy(patched,code,8);
    assert(!install_hook(&second,(unsigned long)code,patched,(void *)5678));
    assert(!install_hook(&second,(unsigned long)(code+1),patched,(void *)5678));
    assert(!release_hook(&first) && !freed);
    struct installed_hook copied=first;assert(!detach_hook(&copied) && !release_hook(&copied));
    fail_write=1; uninstall_hook(&first);
    assert(hook_is_installed(&first) && !freed);
    fail_write=0; assert(detach_hook(&first)); assert(!memcmp(code,guard,8));
    unsigned int before=writes;assert(detach_hook(&first) && writes==before);
    assert(!install_hook(&second,(unsigned long)code,guard,(void *)5678));
    fail_release=1;assert(!release_hook(&first) && hook_is_installed(&first));
    fail_release=0;assert(release_hook(&first) && !hook_is_installed(&first) && freed==1);
    assert(install_hook(&second,(unsigned long)code,guard,(void *)5678));
    uninstall_hook(&second);uninstall_hook(&second);assert(freed==2);
    uint32_t literal_code[5]={0xe0803080,0xe59f2000,0,0x12345678,0};
    memcpy(guard,literal_code,8);
    uint32_t *relocated=install_hook(&first,(unsigned long)literal_code,guard,(void *)1234);
    assert(relocated && relocated[0]==0xe0803080 && relocated[1]==0xe59f2008);
    assert(relocated[5]==0x12345678 && relocated[3]==(uint32_t)(unsigned long)(literal_code+2));
    uninstall_hook(&first);assert(!memcmp(guard,literal_code,8));
    uint8_t wrong[8]={0};assert(!install_hook(&first,(unsigned long)code,wrong,(void *)1234));
    assert(!hook_is_installed(&first));
    return 0;
}
''', ['core/services/rx3_hooks.c'], ['-Dmmap=framework_test_map',
                               '-Dmunmap=framework_test_unmap', '-Dmprotect=framework_test_protect'])

    def test_modules_link_without_the_performance_core(self):
        self.run_units(r'''
#include "core/api/rx3_module_api.h"
extern const struct rx3_module rx3_now_playing_module, rx3_stemwave_module;
int main(void) {
    unsetenv("RX3_NOW_PLAYING");unsetenv("RX3_STEMS_DIR");
    assert(!rx3_now_playing_module.configured());
    assert(!rx3_stemwave_module.configured());
    setenv("RX3_STEMS_DIR", "/tmp/stems", 1);
    assert(rx3_stemwave_module.configured());
    unsetenv("RX3_STEMS_DIR");
    assert(!rx3_stemwave_module.configured());
    assert(rx3_now_playing_module.size==sizeof(struct rx3_module));
    assert(rx3_stemwave_module.track_did_load);
    return 0;
}
''', ['now-playing/rx3_now_playing_module.c', 'stems/rx3_stemwave_module.c'],
                       ['-D_POSIX_C_SOURCE=200809L'])

    def test_mix_provider_owns_only_its_registration_and_publishes_values(self):
        self.run_units(r'''
#include "core/services/rx3_mix_state.h"
static struct rx3_mix_state first(unsigned int deck) {
    struct rx3_mix_state value={deck ? 2u:1u,15u,1u};return value;
}
static struct rx3_mix_state second(unsigned int deck) {
    (void)deck;struct rx3_mix_state value={0,3,0};return value;
}
int main(void) {
    assert(!rx3_mix_read(0).ready && !rx3_mix_claim(0));
    assert(rx3_mix_claim(first) && !rx3_mix_claim(second));
    assert(rx3_mix_read(0).selected==1 && rx3_mix_read(1).selected==2);
    struct rx3_mix_state copy=rx3_mix_read(0);copy.selected=0;
    assert(!copy.selected && rx3_mix_read(0).selected==1);
    assert(!rx3_mix_read(2).ready);
    rx3_mix_release(second);assert(rx3_mix_read(0).ready);
    rx3_mix_release(first);assert(!rx3_mix_read(0).ready);
    assert(rx3_mix_claim(second));assert(rx3_mix_read(1).available==3);
    return 0;
}
''', ['core/services/rx3_mix_state.c'])

    def test_host_build_uses_only_packaged_manifest_files_and_known_imports(self):
        patches = discover_patches()
        core = next(p for p in patches if p.patch_id == 'core')
        self.assertTrue(core.arm_hook.sources)
        with tempfile.TemporaryDirectory() as temporary:
            bundle = pathlib.Path(temporary)
            for patch in patches:
                destination = bundle / patch.patch_id
                destination.mkdir()
                paths = list(patch.build_files)
                if patch.arm_hook:
                    paths.append(patch.arm_hook.source)
                for name in paths:
                    target = destination / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(patch.directory / name, target)
            output = bundle / 'core.so'
            compile_arm_hook(bundle / 'core' / core.arm_hook.source, output,
                             sources=tuple(bundle / p for p in core.arm_hook.sources))
            self.assertEqual(undefined_symbols(output) - ALLOWED, set())

    def test_generated_module_compiles_against_the_public_contract(self):
        from app.runtime.scaffold import scaffold
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            generated = scaffold(root, 'framework-example', 'Framework example', ['1.19'], True, 'diagnostics')
            core = root / 'mod/modules/core'
            core.mkdir()
            # The whole public contract and nothing else from the core.
            (core / 'api').mkdir()
            for header in (MODULES / 'core/api').glob('*.h'):
                shutil.copy2(header, core / 'api' / header.name)
            source = next(p for p in generated if p.suffix == '.c')
            output = root / 'module.so'
            compile_arm_hook(source, output)
            self.assertEqual(undefined_symbols(output) - ALLOWED, set())
