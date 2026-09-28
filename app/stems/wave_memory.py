# SPDX-License-Identifier: MPL-2.0
"""Three waveform formats from bounded PCM blocks in the installed engine."""
import math
import numpy as np
from scipy.signal import lfilter
try:
    from .wave_encoding import three_band, required_memory
except ImportError:  # Standalone worker in packaged applications.
    from wave_encoding import three_band, required_memory

HEIGHT_SCALE = 2.9327451233027466e-08


def coefficients(frequency, high, rate):
    angle=2*math.pi*frequency/rate; cosine=math.cos(angle);alpha=math.sin(angle)/math.sqrt(2)
    b0=(1+cosine if high else 1-cosine)/2
    return np.array([b0,-(1+cosine) if high else 1-cosine,b0])/(1+alpha),np.array([1.,-2*cosine/(1+alpha),(1-alpha)/(1+alpha)])


class Envelope:
    def envelopes(self,bands,count):
        bands=np.asarray(bands);length=bands.shape[1];positions=np.arange(count,dtype=np.int64)
        stop=(length*(positions+1)+count-1)//count
        output=np.zeros((3,count),dtype=np.float64)
        for j,(back,decay) in enumerate(zip((300,200,100),(.99,.98,.97))):
            start=np.maximum(0,(length*positions+count-1)//count-back)
            env=output[j]
            for offset in range(int(np.max(stop-start))):
                index=start+offset;active=index<stop;value=bands[j,np.minimum(index,length-1)]
                updated=np.where(value<env,value+(env-value)*decay,value)
                env[active]=updated[active]
        return output


class Bank:
    def __init__(self,frames,rate):
        count=(frames*150+rate-1)//rate;total=(count*rate+149)//150
        milliseconds=(frames*1000+rate-1)//rate
        peaks=[np.zeros(count if i<2 else milliseconds,dtype=np.int32) for i in range(9)]
        specs={1:[(150,False)],3:[(100,False)],4:[(300,True),(3000,False)],5:[(1500,True)],6:[(300,False)],7:[(250,True),(1200,False)],8:[(3000,True),(9000,False)]}
        filters={i:[[*coefficients(freq,high,rate),np.zeros(2)] for freq,high in chain] for i,chain in specs.items()}
        offset=0
        self.frames,self.rate,self.count,self.total=frames,rate,count,total
        self.peaks,self.filters,self.offset=peaks,filters,offset

    def feed(self,full):
        frames,rate,count,total=self.frames,self.rate,self.count,self.total
        peaks,filters,offset=self.peaks,self.filters,self.offset
        valid=len(full);stop=offset+valid
        if stop==frames and stop<total:full=np.pad(full,((0,total-stop),(0,0)))
        channels=np.trunc(full.astype(np.float64)*32768)
        blue=np.trunc((channels[:,0]+channels[:,1])/2)
        channels=channels/32767
        left,right=channels[:,0],channels[:,1]
        mono=np.where(np.abs(np.abs(left)-np.abs(right))<.001,np.where(np.abs(left)>np.abs(right),left,right),(left+right)/2)
        for i in range(9):
            data=blue if i<2 else mono
            for filt in filters.get(i,[]):
                b,a,zi=filt;data,filt[2]=lfilter(b,a,data,zi=zi)
            cadence=150 if i<2 else 1000
            first=offset*cadence//rate
            last=min(len(peaks[i]),(stop*cadence+rate-1)//rate)
            boundaries=(np.arange(first,last+1,dtype=np.int64)*rate+cadence-1)//cadence-offset
            if i>=2:boundaries[-1]=min(boundaries[-1],valid)
            sliced=data[:boundaries[-1]];starts=boundaries[:-1]
            values=np.maximum(np.maximum.reduceat(sliced,starts),-np.minimum.reduceat(sliced,starts))
            if i>=2:values=values*32768
            peaks[i][first:last]=np.minimum(32767,np.trunc(values)).astype(np.int64)
        offset=stop
        self.offset=offset

    def finish(self):
        offset,frames,count,peaks=self.offset,self.frames,self.count,self.peaks
        if offset != frames:
            raise ValueError("Incomplete waveform input")
        values=[p.tolist() for p in peaks]
        return {b'PWV3':encode(*values[:6],count,b'PWV3'),
                b'PWV5':encode(*values[:6],count,b'PWV5'),
                b'PWV7':three_band(values[6:],count,accelerator=Envelope())}


def columns_from_blocks(blocks,frames,rate=44100,block_seconds=2):
    bank=Bank(frames,rate)
    for block in blocks:bank.feed(block)
    return bank.finish()


def columns(path,frames,tag,count,ffmpeg='ffmpeg',checkpoint=lambda:None,*,rate=44100,progress=lambda x:None,accelerator=None,block_seconds=2):
    pcm=np.memmap(path,dtype='<f4',mode='r',shape=(frames,2))
    size=rate*block_seconds
    def blocks():
        for start in range(0,frames,size):
            checkpoint();yield pcm[start:start+size]
    result=columns_from_blocks(blocks(),frames,rate,block_seconds)
    return result if tag is None else result[tag]


def encode(blue,low_blue,full_ms,low_ms,mid_ms,high_ms,count,tag):
    from scipy.ndimage import maximum_filter1d
    if tag==b'PWV3':
        values=np.asarray(blue,dtype=np.float64);lo=np.asarray(low_blue,dtype=np.float64)
        peak=values.max(initial=0);gain=32767/peak if peak else 0
        ratio=np.divide(lo,values,out=np.zeros_like(lo),where=values!=0)
        shade=np.where(values!=0,7-np.clip(np.trunc(ratio*8),0,7),7).astype(np.uint8)
        height=np.minimum(31,(np.trunc(values*gain).astype(np.int64)**2*HEIGHT_SCALE).astype(np.int64))
        return ((shade<<5)|height.astype(np.uint8)).tobytes()
    full_ms=np.asarray(full_ms,dtype=np.int64)
    starts=(len(full_ms)*np.arange(count)+count-1)//count
    def reduce(values):return np.maximum.reduceat(np.asarray(values),starts)
    low=reduce(maximum_filter1d(np.asarray(low_ms),25,mode='constant',cval=0))
    mid=reduce(maximum_filter1d(np.asarray(mid_ms),3,mode='constant',cval=0))
    high=reduce(high_ms);full=reduce(full_ms)
    include=np.ones(len(full_ms),dtype=bool)
    include[((len(full_ms)*np.arange(1,count)+count-1)//count)-1]=False;include[-1]=False
    maximum=full_ms[include].max(initial=0)
    height=((np.trunc(full*32767/maximum).astype(np.int64)**2*HEIGHT_SCALE).astype(np.int64)&31) if maximum else np.zeros(count,dtype=np.int64)
    r,g,b=(v.astype(np.float32) for v in (low,mid,high))
    peak=np.maximum(np.maximum(r,g),b);silent=peak==0
    scale=np.divide(np.float32(1),peak,out=np.zeros_like(peak),where=~silent)
    r,g,b=((v*np.float32(255))*scale for v in (r,g,b))
    cut=(r*g)*np.float32(.0013071897)
    cut=np.where(b<64,((b*np.float32(-.015625))*cut)+cut,np.float32(0))
    r=r-cut;g=g-cut
    g=((g*np.float32(-.00234375))*np.minimum(np.maximum(r,b),128))+g
    b=b*np.float32(1.3)
    r,g,b=(np.where(silent,7,np.clip(v,0,255).astype(np.int64)>>5) for v in (r,g,b))
    return ((r<<13)|(g<<10)|(b<<7)|(height<<2)).astype('>u2').tobytes()



def build(request, progress):
    """Decode once; child inherits the worker's owned process group."""
    import contextlib
    import hashlib
    import pathlib
    import subprocess
    import tempfile
    frames = request['frames']
    roles = request['roles']
    masks = 3 if len(roles) == 1 else 7
    if len(roles) not in (1, 2) or not 4410 <= frames <= 0x5000000:
        raise ValueError('Waveform input limits')
    if required_memory(frames, masks) > 512 * 1024**2:
        raise ValueError('Waveform memory budget exceeded')
    banks = {mask: Bank(frames, 44100) for mask in range(1, masks + 1)}
    digests = {mask: hashlib.sha256() for mask in banks}
    with contextlib.ExitStack() as stack:
        inputs = [stack.enter_context(open(role['path'], 'rb')) for role in roles]
        for source, role in zip(inputs, roles):
            source.seek(role['offset'])
        errors = stack.enter_context(tempfile.TemporaryFile())
        process = subprocess.Popen(
            [request['ffmpeg'], '-v', 'error', '-nostdin', '-flags2', '+skip_manual',
             '-i', request['source'], '-map', '0:a:0', '-vn', '-ar', '44100', '-ac', '2',
             '-f', 'f32le', 'pipe:1'], stdout=subprocess.PIPE, stderr=errors)
        try:
            for at in range(0, frames, 88200):
                size = min(88200, frames - at)
                raw = process.stdout.read(size * 8)
                if len(raw) != size * 8:
                    raise ValueError('Decoded source does not match the stem frame count')
                mix = np.frombuffer(raw, dtype='<f4').reshape(-1, 2)
                parts = []
                for source, gain in zip(inputs, request['gains']):
                    raw = source.read(size * 4)
                    if len(raw) != size * 4:
                        raise ValueError('Truncated stem PCM')
                    parts.append((np.frombuffer(raw, dtype='<i2').reshape(-1, 2).astype(np.float64)
                                  * gain).astype(np.float32))
                silent = np.all(mix == 0, axis=1)
                for mask, bank in banks.items():
                    if mask == masks:
                        values = mix
                    else:
                        residual = float(bool(mask & 1))
                        values = mix * np.float32(residual)
                        for i, part in enumerate(parts):
                            gain = np.float32((float(bool(mask & (1 << (i + 1)))) - residual) / 32768.)
                            values = np.add(values, part * gain)
                        values[silent] = mix[silent]
                    digests[mask].update(values.astype('<f4', copy=False).tobytes())
                    bank.feed(values)
                progress(.75 * (at + size) / frames)
            if process.stdout.read(1):
                raise ValueError('Decoded source exceeds the stem frame count')
            if process.wait(timeout=10):
                errors.seek(0)
                raise ValueError(errors.read(4096).decode(errors='replace'))
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            process.stdout.close()
    output = pathlib.Path(request['output'])
    count = (frames + 293) // 294
    # Each mask is six bytes per column; no audio scratch file is written.
    with output.open('wb') as target:
        for mask in range(1, masks + 1):
            data = banks.pop(mask).finish()
            packed = bytearray(count * 6)
            packed[0::6] = data[b'PWV3']
            for j in range(2): packed[1+j::6] = data[b'PWV5'][j::2]
            for j in range(3): packed[3+j::6] = data[b'PWV7'][j::3]
            target.write(packed)
            progress(.75 + .25 * mask / masks)
    return {'digests': [digests[mask].hexdigest() for mask in range(1, masks + 1)]}
