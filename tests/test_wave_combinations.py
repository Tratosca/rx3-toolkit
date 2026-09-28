# SPDX-License-Identifier: MPL-2.0
"""Native display decoding and refresh lifecycle for calculated combinations."""
import unittest
from tests import test_runtime_transitions as transitions


class WaveCombinationTests(unittest.TestCase):
    run_c = transitions.RuntimeTransitionTests.run_c

    def test_native_formats_and_shape_change_refresh(self):
        self.run_c(r'''
#include "stems/rx3_stemwave_decl.h"
#include "stems/rx3_stemwave_render.h"
int main(void) {
 struct waveform_column columns[2];
 const uint8_t blue[]={0x1f,0xe0};
 stemwave_decode_columns(columns,blue,2,WAVEFORM_BLUE);
 assert(columns[0].amplitude[0]==31 && columns[1].amplitude[0]==0);
 assert(columns[0].colour[0]!=columns[1].colour[0]);
 const uint8_t rgb[]={0xe0,0x7c,0x03,0xfc};
 stemwave_decode_columns(columns,rgb,2,WAVEFORM_RGB);
 assert(columns[0].amplitude[0]==31 && columns[0].colour[0]==0xe000);
 assert(columns[1].amplitude[0]==31 && columns[1].colour[0]==0x1c);
 const uint8_t bands[]={20,8,3,0,0,0};
 stemwave_decode_columns(columns,bands,2,WAVEFORM_3BAND);
 assert(columns[0].amplitude[0]==20 && columns[0].amplitude[1]==8 && columns[0].amplitude[2]==3);
 assert(columns[0].colour[0]==0x02bc && columns[0].colour[1]==0xfd20 && columns[0].colour[2]==0xffff);
 assert(!columns[1].amplitude[0] && !columns[1].amplitude[1] && !columns[1].amplitude[2]);
 const uint8_t pwv7[]={80,50,20,0,0,0};
 stemwave_decode_pwv7(columns,pwv7,2);
 assert(columns[0].amplitude[0]==20 && columns[0].colour[0]==0xf75a);
 assert(columns[0].amplitude[1]==30 && columns[0].colour[1]==0xb341);
 assert(columns[0].amplitude[2]==30 && columns[0].colour[2]==0x02bc);
 assert(!columns[1].amplitude[0]);
 /* Every ordering/tie: each pixel gets the union of the active bands. */
 const unsigned palette[]={0,0xffff,0xfd20,0xff9a,0x02bc,0xd6ff,0xb341,0xf75a};
 for(unsigned low=0;low<5;low++) for(unsigned mid=0;mid<5;mid++) for(unsigned high=0;high<5;high++) {
  uint8_t input[3]={low,mid,high};stemwave_decode_pwv7(columns,input,1);
  unsigned y=0;
  for(unsigned layer=0;layer<3;layer++) for(unsigned j=0;j<columns[0].amplitude[layer];j++,y++)
   assert(columns[0].colour[layer]==palette[(high>y?1:0)|(mid>y?2:0)|(low>y?4:0)]);
  unsigned peak=low>mid?low:mid;peak=peak>high?peak:high;assert(y==peak);
 }
 struct stemwave_deck state={0};
 assert(stemwave_renew_action(&state,0,3)==STEMWAVE_REQUEST);
 assert(stemwave_renew_action(&state,1,3)==STEMWAVE_KEEP);
 assert(stemwave_renew_action(&state,0,3)==STEMWAVE_PAINT);
 assert(stemwave_renew_action(&state,0,3)==STEMWAVE_KEEP);
 assert(stemwave_renew_action(&state,0,3|(WAVEFORM_3BAND<<8))==STEMWAVE_REQUEST);
 return 0;
}
''')
