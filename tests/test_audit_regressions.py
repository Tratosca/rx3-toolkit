# SPDX-License-Identifier: MPL-2.0
"""Failure injection and deterministic interleavings from the runtime audit."""
import pathlib
import socket
import subprocess
import tempfile
import threading
import unittest

from tests import test_framework as harness
from tests.test_runtime_transitions import function

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULES = ROOT / 'mod/modules'


class AuditRegressions(unittest.TestCase):
    run_units = harness.FrameworkTests.run_units

    def test_patch_failure_restores_bytes_before_trampoline_release(self):
        patch = (MODULES / 'core/firmware/rx3_patch.c').read_text()
        writer = 'int write_code(' + patch.split('int write_code(', 1)[1]
        self.run_units(r'''
#include "core/services/rx3_hooks.h"
#include "core/firmware/rx3_patch.h"
static uint32_t arena[1024];
static unsigned protects,freed,fail_at,fail_twice;
void *mmap(void *a,size_t n,int p,int f,int d,off_t o) {
 (void)a;(void)n;(void)p;(void)f;(void)d;(void)o;return arena;
}
int munmap(void *p,size_t n){(void)p;(void)n;freed++;return 0;}
int mprotect(void *p,size_t n,int f){
 (void)p;(void)n;
 assert(f & PROT_EXEC); /* never make a native code page non-executable */
 protects++;return protects==fail_at || (fail_twice && protects==fail_at+1)?-1:0;
}
void clear_instruction_cache(unsigned long a,unsigned long b){assert(b>a);}
''' + writer + r'''
int main(void){
 for(unsigned pc=0;pc<2;pc++) for(unsigned failure=1;failure<=3;failure++) {
  uint32_t code[4]={0xe59f3000,0xe92d4010,0x12345678,0};
  uint8_t guard[8];memcpy(guard,code,8);struct installed_hook hook={0};
  protects=freed=0;fail_at=failure;fail_twice=failure==3;
  void *original=0;
  int installed=RX3_INSTALL_HOOK(pc?install_pc_ldr_hook:install_hook,
                                 original,&hook,(unsigned long)code,guard,(void *)1234);
  assert(!installed && !memcmp(code,guard,8));
  if(failure==3) {
   assert(original && hook_is_installed(&hook) && !freed);
   fail_at=fail_twice=0;
   assert(uninstall_hook(&hook));
  }
  assert(!original && !hook_is_installed(&hook) && freed==1);
 }
 uint32_t code[4]={1,2,3,4};uint8_t guard[8];memcpy(guard,code,8);
 struct installed_hook hook={0};protects=freed=fail_at=fail_twice=0;
 void *original=0;
 assert(RX3_INSTALL_HOOK(install_hook,original,&hook,(unsigned long)code,guard,(void *)1234));
 fail_at=protects+2; /* RX restoration on detach */
 assert(!detach_hook(&hook) && hook_is_installed(&hook) && !freed);
 assert(code[0]==0xe51ff004 && code[1]==1234);
 fail_at=0;assert(uninstall_hook(&hook) && freed==1 && !memcmp(code,guard,8));
 assert(write_code((unsigned long)code,guard,0)==-1);
 assert(write_code((unsigned long)code,guard,9)==-1);
 return 0;
}
''', ['core/services/rx3_hooks.c'], ['-Dmmap=audit_map', '-Dmunmap=audit_unmap', '-Dmprotect=audit_protect'])

    def test_core_rejection_keeps_originals_when_restore_fails(self):
        core = MODULES / 'core/rx3_core_hook.c'
        # Shared input, audio and fill hooks belong to their services now; the
        # core's own performance hooks remain its to remove.
        hooks = {'beatfx_xpad_ctor':'beatfx_xpad_ctor', 'beat_jump':'on_key_beat_jump',
                 'slip_loop':'on_key_slip_loop', 'beat_loop':'on_key_beat_loop',
                 'hot_cue':'on_key_hot_cue', 'set_beatfx':'set_beatfx_selected',
                 'touch':'solve_touch', 'draw_image':'draw_image', 'image_info':'image_info',
                 'draw_text':'draw_text', 'load':'load', 'audio_start':'audio_start'}
        declarations = '\n'.join(f'static int {hook}_hook; static void *original_{original};'
                                  for hook, original in hooks.items())
        setup = '\n'.join(f'original_{original}=(void *)1;' for original in hooks.values())
        verify = '\n'.join(f'assert(original_{original}==(&{hook}_hook==failed?(void *)1:0));'
                                   for hook, original in hooks.items())
        rejection = core.read_text().split('reject_performance_hooks:\n', 1)[1].split('\n}', 1)[0]
        self.run_units(declarations + r'''
static int *failed;
static int uninstall_hook(int *hook){return hook!=failed;}
static void park_native_performance_touches(int x){(void)x;}
static void rx3_modules_stop(void){}
static void log_line(const char *text){(void)text;}
''' + function(core, 'uninstall_performance_hooks') + '\nstatic void reject(void){\n' + rejection + '\n}\n' +
        'int main(void){\n' + setup + '\nfailed=&load_hook;reject();\n' + verify + '\n' + setup +
        '\nfailed=&audio_start_hook;reject();\n' + verify + '\nreturn 0;}\n', [])

    def test_sample_retrigger_survives_audio_cursor_publication(self):
        self.run_units(r'''
typedef struct rx3_stereo Float2;
#include "samples/rx3_samples_decl.h"
static struct sample_slot voices[8];
static unsigned inject;
static int interleaved_cas(volatile unsigned *p,unsigned old,unsigned next){
 if(inject){inject=0;samples_voice_command(&voices[0],0);}
 return __atomic_compare_exchange_n(p,&old,next,0,__ATOMIC_SEQ_CST,__ATOMIC_SEQ_CST);
}
#define __sync_bool_compare_and_swap interleaved_cas
#include "samples/rx3_samples_audio.h"
int main(void){
 int16_t pcm[32];for(unsigned i=0;i<32;i++)pcm[i]=16384;
 Float2 output[16]={0};
 for(unsigned i=0;i<8;i++)voices[i].position=SAMPLE_SLOT_IDLE;
 voices[0]=(struct sample_slot){pcm,16,0,SAMPLE_MODE_ONCE,100};
 inject=1;samples_mix(voices,output,16,100);
 assert(samples_voice_position(&voices[0])==0 && output[0].left==0.25f);
 memset(output,0,sizeof(output));samples_mix(voices,output,16,100);
 assert(samples_voice_position(&voices[0])==SAMPLE_SLOT_IDLE && output[0].left==0.25f);
 /* Same cursor on a looping voice must also retain the new generation. */
 voices[0].mode=SAMPLE_MODE_LOOP;samples_voice_command(&voices[0],0);
 inject=1;samples_mix(voices,output,1,100);
 assert(samples_voice_position(&voices[0])==0);
 samples_mix(voices,output,1,100);assert(samples_voice_position(&voices[0])==1);
 samples_voice_command(&voices[0],SAMPLE_SLOT_IDLE);
 assert(samples_voice_position(&voices[0])==SAMPLE_SLOT_IDLE);
 /* Counter wrap cannot alter cursor decoding. */
 voices[0].position=~SAMPLE_CURSOR_MASK;samples_voice_command(&voices[0],0);
 assert(samples_voice_position(&voices[0])==0);
 return 0;
}
''', [], ['-Wno-unused-function'])

    def test_recolour_refreshes_table_offset_and_dimensions(self):
        self.run_units(r'''
#include "core/services/rx3_images.c"
static struct {uint8_t record[44];uint16_t pixels[4];} tables[2];
static unsigned current;
static void *lookup(unsigned id){(void)id;return tables[current].record;}
int main(void){
 for(unsigned i=0;i<2;i++){
  uint16_t w=2,h=1;uint32_t off=44;
  memcpy(tables[i].record+4,&w,2);memcpy(tables[i].record+6,&h,2);
  memcpy(tables[i].record+32,&off,4);tables[i].record[24]=1;
  tables[i].pixels[0]=0x07e0;tables[i].pixels[1]=i?0xffff:0x0000;
  tables[i].pixels[2]=0xf81f;tables[i].pixels[3]=0xffff;
 }
 static int owner;unsigned id=rx3_images.register_recolour(&owner,227,0x07e0,0xf800);
 assert(rx3_image_resolve(id,lookup,&tables[0]));assert(variants[0].pixels[0]==0xf800);
 current=1;assert(rx3_image_resolve(id,lookup,&tables[1]));assert(variants[0].pixels[1]==0xffff);
 uint32_t off=48;memcpy(tables[1].record+32,&off,4);
 assert(rx3_image_resolve(id,lookup,&tables[1]));assert(variants[0].pixels[0]==0xf81f);
 off=44;memcpy(tables[1].record+32,&off,4);uint16_t w=1,h=2;
 memcpy(tables[1].record+4,&w,2);memcpy(tables[1].record+6,&h,2);
 assert(rx3_image_resolve(id,lookup,&tables[1]));assert(variants[0].source_width==1 && variants[0].source_height==2);
 current=0;assert(rx3_image_resolve(id,lookup,&tables[0]));assert(variants[0].pixels[1]==0);
 return 0;
}
''', [])

    def test_decoder_helper_propagates_missing_and_empty_replies(self):
        source = (MODULES / 'decoder-sleep/apply.sh').read_text()
        helper = source.split("<<'DEBUG_HELPER'\n", 1)[1].split('\nDEBUG_HELPER', 1)[0]
        # Same helper and delimiter, on a private loopback port; shorten timeout.
        for reply in (None, b'\0', b'console reply\0'):
            with self.subTest(reply=reply), socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
                server.bind(('127.0.0.1', 0));server.settimeout(2)
                port = server.getsockname()[1]
                errors = []
                def receive():
                    try:
                        data, peer = server.recvfrom(1024)
                        if data != b'bufsleep 0 100000\n': errors.append(data)
                        if reply is not None: server.sendto(reply, peer)
                    except Exception as error: errors.append(error)
                worker = threading.Thread(target=receive);worker.start()
                with tempfile.TemporaryDirectory() as directory:
                    path = pathlib.Path(directory) / 'helper.sh'
                    path.write_text(helper.replace('/20000', f'/{port}').replace('sleep 1', 'sleep 0.05'))
                    result = subprocess.run(['/bin/bash', str(path), 'bufsleep', '0', '100000'],
                                            capture_output=True, text=True, timeout=3)
                worker.join(timeout=3)
                self.assertFalse(worker.is_alive());self.assertFalse(errors)
                self.assertEqual(result.returncode == 0, reply == b'console reply\0')
                if reply == b'console reply\0': self.assertEqual(result.stdout, 'console reply\n')
        self.assertNotIn('applied to both decks', source)

    def test_shifter_seed_matches_previous_reset_history(self):
        self.run_units(r'''
#include "keyshift/rx3_pitch_shift.h"
int main(void){
 float history[RX3_SHIFT_HISTORY*2],expected[RX3_SHIFT_HISTORY*2],input[8194];
 for(unsigned i=0;i<8194;i++)input[i]=(float)((int)i-4000)*0.001f;
 unsigned sizes[]={1,3,128,511,4096,4097};
 for(unsigned n=0;n<sizeof(sizes)/sizeof(sizes[0]);n++) {
  unsigned frames=sizes[n];struct rx3_shifter a={0},b={0};
  rx3_shifter_init(&a,expected);
  for(unsigned i=0;i<RX3_SHIFT_HISTORY;i++) {
   expected[i*2]=input[(i%frames)*2];expected[i*2+1]=input[(i%frames)*2+1];
  }
  a.written=RX3_SHIFT_HISTORY;rx3_shifter_seed(&b,history,input,frames);
  assert(!memcmp(history,expected,sizeof(history)));
  b.history=a.history;assert(!memcmp(&a,&b,sizeof(a)));
 }
 return 0;
}
''', [], ['-Wno-unused-function'])

    def test_legacy_stems_fallback_reads_valid_prefix_once(self):
        load = function(MODULES / 'stems/rx3_stems_loader.h', 'stems_load_set')
        self.run_units(r'''
#include "stems/rx3_stems_io.h"
struct stem_payload {unsigned frames,block_size;};
static unsigned calls[3],released,fail_index,mismatch;
static int stems_load_payload(int fd,struct stem_payload *p,unsigned resident,const struct stems_io *io){
 (void)io;
 assert(fd>=0 && fd<3);calls[fd]++;assert(resident==10u+(unsigned)fd*100u);
 if((unsigned)fd==fail_index && !mismatch)return 0;
 p->block_size=100;p->frames=(unsigned)fd==fail_index && mismatch?42:100;
 return 1;
}
static void release_payload(struct stem_payload *p){released+=p->block_size!=0;memset(p,0,sizeof(*p));}
''' + load + r'''
int main(void){
 int fds[3]={0,1,2};
 for(unsigned failure=0;failure<4;failure++)for(unsigned different=0;different<2;different++) {
  if(different && failure==0)continue;
  struct stem_payload next[3]={0};memset(calls,0,sizeof(calls));released=0;
  fail_index=failure;mismatch=different;
  unsigned count=stems_load_set(fds,next,10,0);
  assert(count==(failure<3?failure:3));
  for(unsigned i=0;i<3;i++)assert(calls[i]==(i<=failure));
  assert(released==(different && failure<3));
  for(unsigned i=0;i<count;i++)assert(next[i].frames==100 && next[i].block_size==100);
 }
 return 0;
}
''', [], ['-Wno-unused-function'])

    def test_search_stop_waits_for_native_callback_before_release(self):
        self.run_units(r'''
#include "search-latin/rx3_search_module.c"
static unsigned entered,allow_exit,detached,released;
static void original(uint16_t *text,void *context,int length){
 (void)text;(void)context;(void)length;
 __atomic_store_n(&entered,1,__ATOMIC_SEQ_CST);
 while(!__atomic_load_n(&allow_exit,__ATOMIC_SEQ_CST))usleep(1000);
}
static int detach(struct installed_hook *h){(void)h;__atomic_store_n(&detached,1,__ATOMIC_SEQ_CST);return 1;}
static int release(struct installed_hook *h){(void)h;assert(!search_callbacks);released++;return 1;}
static const struct rx3_services services={.detach_hook=detach,.release_hook=release};
static void *callback(void *arg){(void)arg;hooked_search_shape(0,0,0);return 0;}
static void *stop(void *arg){(void)arg;search_latin_feature_remove();return 0;}
int main(void){
 framework=&services;original_search_shape=original;pthread_t a,b;
 assert(!pthread_create(&a,0,callback,0));
 while(!__atomic_load_n(&entered,__ATOMIC_SEQ_CST))usleep(1000);
 assert(!pthread_create(&b,0,stop,0));
 while(!__atomic_load_n(&detached,__ATOMIC_SEQ_CST))usleep(1000);
 assert(original_search_shape==original);
 __atomic_store_n(&allow_exit,1,__ATOMIC_SEQ_CST);
 pthread_join(a,0);pthread_join(b,0);
 assert(released==1 && !original_search_shape && !search_callbacks);return 0;
}
''', [], ['-pthread'])

    def test_now_playing_retains_live_hooks_and_drains_before_release(self):
        remove = function(MODULES / 'now-playing/rx3_now_playing_feature.h', 'now_playing_feature_remove')
        self.run_units(r'''
#include "core/api/rx3_module_api.h"
static unsigned now_playing_callbacks,detached,released,fail;
static int now_playing_running,now_playing_thread_started;
static pthread_t now_playing_thread;
static int now_playing_wake[2]={-1,-1},now_playing_socket=-1;
static struct installed_hook now_playing_mixer_hook,now_playing_unload_hook,now_playing_load_hook,now_playing_status_hook;
static void *original_now_playing_mixer,*original_now_playing_unload,*original_now_playing_load,*original_now_playing_status;
#define NOW_PLAYING_DONTWAIT 0
static int send(int fd,const void *data,size_t n,int flags){(void)fd;(void)data;(void)n;(void)flags;return 1;}
static int detach(struct installed_hook *h){(void)h;__atomic_add_fetch(&detached,1,__ATOMIC_SEQ_CST);return !fail;}
static int release(struct installed_hook *h){(void)h;assert(!now_playing_callbacks);released++;return 1;}
static const struct rx3_services services={.detach_hook=detach,.release_hook=release};
static const struct rx3_services *framework=&services;
''' + remove + r'''
static void *stop(void *arg){(void)arg;now_playing_feature_remove();return 0;}
int main(void){
 original_now_playing_mixer=original_now_playing_unload=original_now_playing_load=original_now_playing_status=(void *)1;
 fail=1;now_playing_feature_remove();assert(!released && original_now_playing_load);
 fail=0;detached=0;now_playing_callbacks=1;pthread_t thread;
 assert(!pthread_create(&thread,0,stop,0));
 while(__atomic_load_n(&detached,__ATOMIC_SEQ_CST)<4)usleep(1000);
 assert(original_now_playing_load);
 __atomic_store_n(&now_playing_callbacks,0,__ATOMIC_SEQ_CST);pthread_join(thread,0);
 assert(released==4 && !original_now_playing_load && !original_now_playing_mixer);
 return 0;
}
''', [], ['-pthread'])
