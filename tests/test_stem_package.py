# SPDX-License-Identifier: MPL-2.0
import dataclasses
import json
import pathlib
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from app.stems import analysis, audition, cache, package, safety, stem, waveform

ROOT = pathlib.Path(__file__).resolve().parents[1]

class PackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.frames = 4410
        self.inputs = {}
        for index, role in enumerate(stem.ROLE_ORDER):
            p = self.root / (role + '.pcm')
            p.write_bytes(stem.HEADER.pack(stem.MAGIC,44100,2,2,64,self.frames,b'\0'*32) + struct.pack('<hh',100+index,-100-index)*self.frames)
            self.inputs[role] = p
        self.template = analysis.Template(b'PWV5',b'\0'*30,15,(), '11'*32)

    def make(self, count=3):
        inputs = dict(list(self.inputs.items())[:count])
        wave = self.root/'track.rx3wave'
        roles = dict((r,(bytes([0,4*(i+1)])*15,'22'*32)) for i,r in enumerate(list(waveform.ROLE_IDS)[:count+1]))
        waveform.write(wave,self.template,self.frames,'33'*32,roles)
        out=self.root/'track.rx3stem'
        package.write(out,inputs,wave,{'title':'test'})
        return out

    def test_single_file_self_describes_each_selected_set_and_audition(self):
        for count in (1,2,3):
            with self.subTest(count=count):
                out=self.make(count)
                parsed=package.read(out)
                self.assertEqual(parsed['roles'],stem.ROLE_ORDER[:count])
                self.assertEqual(parsed['manifest']['source_sha256'],'33'*32)
                self.assertEqual(parsed['waveform']['count'],15)
                files,frames,rejected=audition.role_files(self.root,'track')
                self.assertEqual((len(files),frames,rejected),(count,self.frames,[]))
                for member, original in zip(files,self.inputs.values()):
                    with member.open() as stream:
                        self.assertEqual(stream.read(),original.read_bytes())
                        self.assertEqual(stream.read(),b'')
                        with self.assertRaises(ValueError):stream.seek(member.length+1)

    def test_crc_directory_and_truncation_are_rejected(self):
        out=self.make(); data=out.read_bytes()
        for changed in (data[:-1],data+b'x',data[:800]+bytes([data[800]^1])+data[801:],
                        data[:64]+struct.pack('<I',9)+data[68:]):
            out.write_bytes(changed)
            with self.assertRaises((ValueError,struct.error)):package.read(out)
        out.write_bytes(data)
        self.assertEqual(package.read(out)['frames'],self.frames)

    def test_failed_build_leaves_old_package_and_no_partial_publication(self):
        out=self.make(); before=out.read_bytes()
        bad=self.root/'bad';bad.write_bytes(b'incomplete')
        with self.assertRaises((ValueError,struct.error)):package.publish(bad,out)
        self.assertEqual(out.read_bytes(),before)

    def test_publish_removes_only_obsolete_sidecars(self):
        local=self.make(); target=self.root/'new.rx3stem'
        for suffix in ('.rx3drums','.rx3bass','.rx3wave'):target.with_suffix(suffix).write_bytes(b'old')
        package.publish(local,target)
        self.assertEqual(package.read(target)['roles'],stem.ROLE_ORDER)
        self.assertFalse(target.with_suffix('.rx3wave').exists())
        self.assertTrue(local.exists())

    def test_cache_verifies_package_then_extracts_bounded_pcm(self):
        out=self.make(); entry={'stem':out.name,'stems':[{'role':r,'file':out.name,'bytes':out.stat().st_size,'sha256':safety.digest(out)} for r in stem.ROLE_ORDER]}
        result=cache.verified_files(self.root,entry,stem.ROLE_ORDER)
        self.assertEqual(tuple(result),stem.ROLE_ORDER)
        self.assertEqual(safety.digest(result['drums']),safety.digest(self.inputs['drums']))
        entry['stems'][0]['sha256']='00'*32
        self.assertIsNone(cache.verified_files(self.root,entry,stem.ROLE_ORDER))

    def test_manual_import_publishes_one_package_for_all_roles(self):
        from app.stems import importing
        from app.stems.rekordbox import Track
        from package_fixture import wave_fixture
        source = self.inputs['vocals']
        track = Track('1', 'test', 'artist', 1, source, True)
        report = {'frames': self.frames, 'roles': {r: {'clippedSamples': 0} for r in self.inputs}}
        with patch.object(importing, 'prepare', return_value=(self.inputs, report)), \
             patch.object(safety, 'require_library_closed'), \
             patch.object(waveform, 'build', side_effect=wave_fixture):
            entry = importing.publish(track, self.inputs, self.root)
        output = self.root/'RX3_STEMS'
        self.assertEqual([p.name for p in output.glob('*.rx3*')], ['vocals.rx3stem'])
        parsed = package.read(output/'vocals.rx3stem')
        self.assertEqual(parsed['roles'], stem.ROLE_ORDER)
        self.assertEqual({item['file'] for item in entry['stems']}, {'vocals.rx3stem'})
        self.assertTrue(entry['checks']['waveform'])

    @unittest.skipUnless(shutil.which('cc'),'C compiler required')
    def test_real_c_loader_accepts_package_and_rejects_corruption(self):
        out=self.make()
        source=self.root/'test.c'; exe=self.root/'test'
        def function(path, name):
            text = path.read_text()
            start = text.index('static unsigned int ' + name + '(')
            body = text.index('{', start)
            level, end = 1, body + 1
            while level:
                level += (text[end] == '{') - (text[end] == '}')
                end += 1
            return text[start:end]
        functions = function(ROOT/'mod/modules/stems/rx3_stems_audio.h', 'stems_available') + '\n' + function(ROOT/'mod/modules/stems/rx3_stems_feature.h', 'stems_waveform')
        source.write_text(r'''
#include <stdint.h>
#include <stddef.h>
#include <pthread.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/mman.h>
#include <assert.h>
#define RX3_PLATFORM_H
#include "core/api/rx3_module_api.h"
#include "stems/rx3_stems_decl.h"
static unsigned long memory_available_kb(void) { return 1024*1024; }
static int mock_reserve(const void *o, unsigned long bytes, unsigned long floor_kb) {
    (void)o; unsigned long kb = bytes / 1024u + (bytes % 1024u != 0u), have = memory_available_kb();
    return !floor_kb || (have > floor_kb && have - floor_kb >= kb);
}
static void mock_move(const void *o, unsigned long b) { (void)o; (void)b; }
static unsigned long mock_held(void) { return 0; }
static const struct rx3_memory_service memory_mock={mock_reserve,mock_move,mock_move,mock_move,memory_available_kb,mock_held};
static const struct rx3_services stem_services={.memory=&memory_mock};
static const struct rx3_services *framework=&stem_services;
static unsigned mapped,checks,cancel_at;
static void *tracked_map(void *a,size_t n,int p,int f,int d,off_t o) {
 void *result=mmap(a,n,p,f,d,o);if(result!=MAP_FAILED)mapped++;return result;
}
static int tracked_unmap(void *p,size_t n) {int result=munmap(p,n);if(!result)mapped--;return result;}
static int cancel_load(const void *unused) {(void)unused;return ++checks==cancel_at;}
#define mmap tracked_map
#define munmap tracked_unmap
#include "stems/rx3_stems_package.h"
''' + functions + r'''
int main(int argc,char **argv) {
 (void)argc; int fd=open(argv[1],O_RDONLY);assert(fd>=0);
 struct stems_io io={cancel_load,0};
 if(argv[2][0]=='c')cancel_at=(unsigned)(argv[2][1]-'0');
 struct stem_payload next[3]={0};unsigned count=stems_package_load(fd,next,0,cancel_at?&io:0);
 if(cancel_at) {
  assert(!count && !mapped && checks==cancel_at);
  for(unsigned i=0;i<3;i++)assert(!next[i].data && !next[i].block);
  close(fd);return 0;
 }
 if(argv[2][0]=='0') {assert(!count);return 0;}
 if(argv[2][0]=='3') {
  assert(count==3 && !next[0].wave && next[0].block && !next[1].block);
  if(next[1].format==FORMAT_S16_GAIN) assert(next[1].pcm_gain==1.25f);
  assert(((const int16_t*)next[2].data)[0]==102);
  struct stems_deck_context *c=&stems_decks[0];
  memcpy(c->payloads,next,sizeof(next));c->armed=1;c->reader=c;
  uint8_t untouched[45];memset(untouched,99,sizeof(untouched));
  assert(stems_waveform(0,0,0,untouched,0)==0xfffffffeu);
  assert(stems_waveform(0,1,1,untouched,15)==0xfffffffeu);
  for(unsigned i=0;i<45;i++) assert(untouched[i]==99);
  assert(!c->readers_active);
  munmap(next[0].block,next[0].block_size);close(fd);return 0;
 }
 assert(count==3 && next[0].wave && next[0].block && !next[1].block);
 assert(((const int16_t*)next[2].data)[0]==102);
 assert(((const struct rx3_wave_header*)next[0].wave)->count==15);
 struct stems_deck_context *c=&stems_decks[0];
 memcpy(c->payloads,next,sizeof(next));c->armed=1;c->reader=c;c->selection=0xff;
 if(argv[2][0]=='4') {
  const struct rx3_wave_header *h=(const void*)next[0].wave;
  unsigned fmt=h->stride==3u?3u:h->stride-1u;
  uint8_t packed[46];
  for(unsigned mask=0;mask<=7;mask++) {
   memset(packed,99,sizeof(packed));
   assert(stems_waveform(0,mask,fmt,packed,15)==15);
   assert(packed[15*h->stride]==99);
   for(unsigned i=0;i<15*h->stride;i++)assert(packed[i]==(mask?mask:0));
  }
  unsigned missing=fmt==0u?1u:0u;
  memset(packed,99,sizeof(packed));
  assert(stems_waveform(0,0,missing,packed,0)==0xfffffffeu);
  assert(stems_waveform(0,1,missing,packed,15)==0xfffffffeu);
  for(unsigned i=0;i<46;i++)assert(packed[i]==99);
  assert(!c->readers_active);
  munmap(next[0].block,next[0].block_size);close(fd);return 0;
 }
 if(argv[2][0]=='2') {
  uint8_t packed[46];
  for(unsigned mask=0;mask<=7;mask++) for(unsigned slot=0;slot<3;slot++) {
   unsigned fmt=slot==2?3:slot, stride=slot+1;
   memset(packed,99,sizeof(packed));
   assert(stems_waveform(0,mask,fmt,packed,15)==15);
   for(unsigned i=0;i<15;i++) for(unsigned j=0;j<stride;j++)
    assert(packed[i*stride+j]==(mask?(fmt==0?mask:fmt==1?mask+j+1:mask+j):0));
   assert(packed[15*stride]==99);
  }
  assert(stems_waveform(0,7,2,packed,15)==0);
  assert(stems_waveform(0,7,2,packed,14)==0xffffffffu);
  munmap(next[0].block,next[0].block_size);close(fd);return 0;
 }
 uint8_t amplitudes[46];memset(amplitudes,99,sizeof(amplitudes));
 assert(stems_waveform(0,2,1,amplitudes,15)==15 && amplitudes[1]==4);
 assert(stems_waveform(0,1,1,amplitudes,15)==0);
 assert(stems_waveform(0,4,1,amplitudes,15)==15 && amplitudes[1]==12);
 assert(stems_waveform(0,8,1,amplitudes,15)==0);
 assert(stems_waveform(0,5,1,amplitudes,15)==0);
 assert(amplitudes[30]==99 && !c->readers_active);
 assert(stems_waveform(0,16,1,amplitudes,15)==0);
 assert(stems_waveform(0,2,1,amplitudes,14)==0xffffffffu);
 c->reader=0;assert(stems_waveform(0,2,1,amplitudes,15)==0);
 munmap(next[0].block,next[0].block_size);close(fd);return 0;
}''')
        subprocess.run(['cc','-std=c11','-I'+str(ROOT/'mod/modules'),str(source),'-o',str(exe)],check=True,capture_output=True)
        subprocess.run([str(exe),str(out),'1'],check=True,capture_output=True)
        for checkpoint in range(1,10):
            subprocess.run([str(exe),str(out),f'c{checkpoint}'],check=True,capture_output=True)
        wave=self.root/'combinations.rx3wave'
        combinations={mask:(bytes([mask,mask+1,mask+2,mask,mask+1,mask+2])*15,'22'*32) for mask in range(1,8)}
        waveform.write_combinations(wave,self.template,self.frames,'33'*32,combinations)
        package.write(out,self.inputs,wave,{})
        subprocess.run([str(exe),str(out),'2'],check=True,capture_output=True)
        data=bytearray(out.read_bytes());data[800]^=1;out.write_bytes(data)
        subprocess.run([str(exe),str(out),'0'],check=True,capture_output=True)
        for tag,stride in ((b'PWV3',1),(b'PWV5',2),(b'PWV7',3)):
            single={mask:(bytes([mask])*15*stride,'22'*32) for mask in range(1,8)}
            waveform.write_combinations(wave,self.template,self.frames,'33'*32,single,tag)
            package.write(out,self.inputs,wave,{})
            self.assertEqual(package.read(out)['waveform']['format'],tag)
            subprocess.run([str(exe),str(out),'4'],check=True,capture_output=True)
        package.write(out,self.inputs,None,{'source_sha256':'33'*32})
        subprocess.run([str(exe),str(out),'3'],check=True,capture_output=True)
        for path in self.inputs.values():
            data=bytearray(path.read_bytes())
            struct.pack_into('<I',data,16,3)
            struct.pack_into('<f',data,32,1.25)
            path.write_bytes(data)
        package.write(out,self.inputs,None,{'source_sha256':'33'*32})
        self.assertEqual(audition.gain(package.read(out)['members'][1]),1.25)
        subprocess.run([str(exe),str(out),'3'],check=True,capture_output=True)
        data=bytearray(out.read_bytes());struct.pack_into('<I',data,8,2);out.write_bytes(data)
        subprocess.run([str(exe),str(out),'0'],check=True,capture_output=True)
