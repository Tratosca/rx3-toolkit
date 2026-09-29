# SPDX-License-Identifier: MPL-2.0
"""Execute startup with failed firmware hooks and minimal module selections."""
import json
import re
import unittest
from tests import test_runtime_transitions as transitions
function, MODULES = transitions.function, transitions.MODULES


class StartupTests(unittest.TestCase):
    run_c = transitions.RuntimeTransitionTests.run_c

    def test_ready_marker_identifies_the_player_that_installed_hooks(self):
        source = MODULES/'core/rx3_core_hook.c'
        code = function(source, 'self_pid') + function(source, 'publish_ready')
        self.run_c(r'''
#define READY_FILE "/tmp/rx3-performance.ready"
#define O_WRONLY 1
#define O_CREAT 0100
#define O_TRUNC 01000
static char marker[16];
static unsigned marker_length;
static int ready_open(const char *path, int flags, ...) {
    if (!strcmp(path, "/proc/self/stat")) { assert(flags == 0); return 4; }
    assert(!strcmp(path, READY_FILE));
    assert(flags == (O_WRONLY | O_CREAT | O_TRUNC)); return 3;
}
static long ready_read(int fd, void *data, size_t length) {
    assert(fd == 4 && length >= 7);
    memcpy(data, "4242 (x)", 8);
    return 8;
}
static long ready_write(int fd, const void *data, size_t length) {
    assert(fd == 3 && length < sizeof(marker));
    memcpy(marker, data, length);
    marker_length = (unsigned)length;
    return (long)length;
}
static int ready_close(int fd) { assert(fd == 3 || fd == 4); return 0; }
#define open ready_open
#define read ready_read
#define write ready_write
#define close ready_close
#define O_RDONLY 0
''' + code + r'''
int main(void) {
    publish_ready();
    assert(marker_length == 5 && !memcmp(marker, "4242\n", 5));
    return 0;
}
''')

    def test_logo_placement_and_guarded_restore(self):
        self.run_c('''
#include "logo/rx3_logo_decl.h"
#include "logo/rx3_logo_geometry.h"
int main(void) {
    uint32_t record[2]={0x00b2018b,LOGO_IMAGE_INDEX};
    assert(logo_place(record,492,70));
    assert(record[0]==(390u | (125u<<16)));
    logo_restore_position(record); assert(record[0]==0x00b2018b);
    assert(logo_place(record,888,445)); assert(record[0]==192u);
    logo_restore_position(record);
    assert(logo_place(record,101,51));
    assert(record[0]==(586u | (135u<<16)));
    record[0]=42; logo_restore_position(record); assert(record[0]==42);
    assert(!logo_place(record,100,100));
    record[0]=0x00b2018b; record[1]=0;
    assert(!logo_place(record,100,100)); assert(record[0]==0x00b2018b);
    return 0;
}
''')

    def test_startup_readiness_is_all_or_nothing(self):
        code = function(MODULES/'core/rx3_core_hook.c', 'initialize')
        code = code.replace('__attribute__((constructor)) ', '')
        # Stub firmware boundaries, retaining the real constructor control flow.
        decl = []
        for name in sorted(set(re.findall(r'\b\w+_fn\b', code))):
            decl.append(f'typedef void *{name};')
        for name in sorted(set(re.findall(r'\boriginal_\w+', code))):
            decl.append(f'static void *{name};')
        for name in sorted(set(re.findall(r'&(\w+_hook)\b', code))):
            decl.append(f'static int {name};')
        locals_ = set(re.findall(r'static const uint8_t (\w+)\[', code))
        for name in sorted(set(re.findall(r'\b\w+_guard\b', code))-locals_):
            decl.append(f'static uint8_t {name}[8];')
        for name in sorted(set(re.findall(r'\bhooked_\w+', code))):
            decl.append(f'#define {name} ((void *)1)')
        constants = ['PCM_LOAD','SET_BEATFX_STORAGE','ON_KEY_HOT_CUE',
                     'ON_KEY_BEAT_LOOP','ON_KEY_SLIP_LOOP','ON_KEY_BEAT_JUMP',
                     'BEATFX_XPAD_CTOR','PAL_DRAW_TEXT','PAL_DRAW_IMAGE','SOLVE_TOUCH','AUDIO_START']
        decl += [f'#define {name} {i+1}' for i,name in enumerate(constants)]
        self.run_c('''
#include <stdlib.h>
#include "keyshift/rx3_keyshift_text.h"
static unsigned int keyshift_sync_range=1;
static unsigned int keyshift_sync_harmonic;
static unsigned int keyshift_match_rules;
#define READY_FILE "ready"
#define THEME_DARK_SENTINEL "off"
#define RENDER_PROBE_FILE "probe"
#define TRANSITION_FRAMES 256u
#define O_WRONLY 1
#define O_TRUNC 2
static const char *stems_dir;
static int keyshift_enabled,samples_enabled,messages_enabled,theme_enabled;
static int theme_light,theme_light_active,theme_global_dark,theme_light_armed;
static int logo_enabled,main_logo_ready,render_probe_enabled;
static uint64_t theme_start_light_not_before_us,tab_install_not_before_us;
static int state_thread_running,state_thread_started,state_thread;
static struct { unsigned selection,transition_cursor; } stems_decks[2];
static unsigned selection,ready,hook_calls,reject_hook,feature_fail,standalone_fail;
static unsigned stops,cleanup,standalone_started,logo_fail;
static int player_process_initialized,player_process=1;
static int is_player_process(void){return player_process;}
/* bits: logo=1, keyshift=2, stems=4, theme=8, samples=16, search=32. */
static char *setting(const char *s) {
    if(!strcmp(s,"RX3_LOGO"))return selection&1?"1":0;
    if(!strcmp(s,"RX3_KEYSHIFT"))return selection&2?"1":0;
    if(!strcmp(s,"RX3_STEMS_DIR"))return selection&4?"stems":0;
    if(!strcmp(s,"RX3_THEME"))return selection&8?"s":0;
    if(!strcmp(s,"RX3_SAMPLES_DIR"))return selection&16?"samples":0;
    return 0;
}
#define getenv setting
static int marker_open(const char *p,int f,int m){(void)p;(void)f;(void)m;ready=0;return 1;}
#define open marker_open
static void close(int fd){(void)fd;}
static void rx3_log_configure(void){}
static void log_line(const char *s){(void)s;}
static void log_number(const char *s,unsigned long n){(void)s;(void)n;}
static int rx3_message_allowed(void){return 1;}
static uint64_t monotonic_enough_us(void){return 1;}
static int logo_feature_install(void){main_logo_ready=!logo_fail;return main_logo_ready;}
static void logo_feature_remove(void){main_logo_ready=0;}
static unsigned configure_features(void){return !!stems_dir+!!theme_enabled+!!samples_enabled;}
static unsigned install_features(void){return configure_features()-(feature_fail?1:0);}
static unsigned rx3_modules_start(void){standalone_started++;return selection&(32|2)?1:0;}
static int rx3_modules_uses_audio(void){return !!(selection&2);}
static unsigned rx3_modules_failures(void){return standalone_fail;}
static unsigned rx3_image_count(void){return 0;}
static unsigned rx3_browse_count(void){return 0;}
static unsigned rx3_panel_count(void){return (selection&(64|2))?1:0;}
static void rx3_modules_stop(void){stops++;}
static void uninstall_performance_hooks(void){cleanup++;logo_feature_remove();}
static void publish_ready(void){ready=1;}
static void *install_hook(void *h,unsigned long a,const void *g,void *r){
    (void)h;(void)a;(void)g;(void)r;hook_calls++;return hook_calls==reject_hook?0:(void *)1;
}
#define pthread_create(a,b,c,d) (0)
''' + '\n'.join(decl) + '\n' + code + '''
static void run(unsigned mask,unsigned hook,unsigned feature,unsigned standalone) {
    selection=mask;reject_hook=hook;feature_fail=feature;standalone_fail=standalone;
    ready=1;hook_calls=0;stops=0;cleanup=0;standalone_started=0;main_logo_ready=0;
    initialize();
}
int main(void) {
    player_process=0;run(4|32,0,0,0);
    assert(ready && !hook_calls && !stops && !cleanup && !standalone_started);
    assert(!player_process_initialized);player_process=1;
    run(1,0,0,0);assert(ready && hook_calls && main_logo_ready);
    run(1|32,0,0,0);assert(ready && hook_calls && standalone_started==1);
    for(unsigned mask=2;mask<=16;mask<<=1){run(mask,0,0,0);assert(ready);}
    run(32,0,0,0);assert(ready && !hook_calls);
    run(32|64,0,0,0);assert(ready && hook_calls);
    run(32|64,1,0,0);assert(!ready && stops && cleanup);
    run(0,0,0,0);assert(!ready && !hook_calls);
    run(4|32,1,0,0);assert(!ready && cleanup && !standalone_started);
    run(4|32,0,1,0);assert(!ready && cleanup && !standalone_started);
    run(4|32,0,0,1);assert(!ready && cleanup && stops);
    run(32,0,0,1);assert(!ready && stops);
    logo_fail=1;run(1|32,0,0,0);assert(!ready && !hook_calls && !standalone_started);
    return 0;
}
''')

    def test_player_identity_rejects_inherited_preload_and_read_failures(self):
        code = function(MODULES/'core/rx3_core_hook.c', 'is_player_process')
        self.run_c('''
#define O_RDONLY 0
static const char *comm;
static int closes;
static int open(const char *path,int mode) {
    assert(!strcmp(path,"/proc/self/comm"));assert(mode==O_RDONLY);
    return comm?3:-1;
}
static int read(int fd,void *out,unsigned size) {
    assert(fd==3);unsigned n=strlen(comm);if(n>size)n=size;
    memcpy(out,comm,n);return n;
}
static void close(int fd){assert(fd==3);closes++;}
''' + code + '''
int main(void) {
    comm="rbp\\n";assert(is_player_process());
    comm="sh\\n";assert(!is_player_process());
    comm="udhcpc\\n";assert(!is_player_process());
    comm="rbp-helper\\n";assert(!is_player_process());
    comm="";assert(!is_player_process());
    comm=0;assert(!is_player_process());assert(closes==5);
    return 0;
}
''')

    def test_foreign_process_teardown_does_not_touch_player_state(self):
        code = function(MODULES/'core/rx3_core_hook.c', 'finalize')
        code = code.replace('__attribute__((destructor)) ', '')
        self.run_c('''
static int player_process_initialized,state_thread_running=1,state_thread_started,state_thread;
static unsigned cleanup,stops,destroyed;
static void join_thread(int t,void *p){(void)t;(void)p;assert(0);}
#define pthread_join join_thread
static void rx3_modules_stop(void){stops++;}
static void uninstall_performance_hooks(void){cleanup++;}
static void destroy(unsigned deck){assert(deck<2);destroyed++;}
#define RUNTIME_FEATURE_COUNT 1u
static struct {void (*destroy_deck)(unsigned);} runtime_features[1]={{destroy}};
''' + code + '''
int main(void) {
    finalize();assert(state_thread_running && !cleanup && !stops && !destroyed);
    player_process_initialized=1;finalize();
    assert(!state_thread_running && cleanup==1 && stops==1 && destroyed==2);
    return 0;
}
''')

    def test_light_tab_assets_are_shipped_complete(self):
        root=MODULES/'core'
        manifest=json.loads((root/'manifest.json').read_text())
        files={row['target']:root/row['source'] for row in manifest['files']}
        for name in ('key-selected','stems-selected','status-none-selected','none-selected','samples-selected','samples-none-selected','samples-beatfx-selected'):
            light=files[name+'-light.rgb565'].read_bytes()
            self.assertEqual(len(light),180*50*2)
            self.assertNotEqual(light,files[name+'.rgb565'].read_bytes())
        for feature in ('key','stems'):
            for state in ('none','selected'):
                name=f'single-{feature}-{state}'
                self.assertEqual(len(files[name+'.rgb565'].read_bytes()),180*50*2)
                self.assertEqual(len(files[name+'-light.rgb565'].read_bytes()),180*50*2)
