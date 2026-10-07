/* SPDX-License-Identifier: MPL-2.0
 * RX3 read-only metadata transport. Separate process; never preloaded into rbp.
 * One request per TCP connection. PDB and ANLZ serve metadata; STAT and RANGE
 * serve bounded, read-only music-file bytes for host-side excerpt decoding.
 * The connection closes after each reply. No player audio buffer is touched.
 */
#ifndef AUDIO_PACE_NS
#define AUDIO_PACE_NS 4000000u
#endif
#if AUDIO_PACE_NS < 600000u
#error "Audio pacing below the 50 Mb/s bench floor is not permitted"
#endif
#ifdef __arm__
typedef unsigned int size_t;
typedef int ssize_t;
static long call6(long n,long a,long b,long c,long d,long e,long f) {
    register long r0 __asm__("r0")=a, r1 __asm__("r1")=b, r2 __asm__("r2")=c;
    register long r3 __asm__("r3")=d, r4 __asm__("r4")=e, r5 __asm__("r5")=f;
    register long r7 __asm__("r7")=n;
    __asm__ volatile("svc 0" : "+r"(r0) : "r"(r1),"r"(r2),"r"(r3),"r"(r4),"r"(r5),"r"(r7) : "memory","cc");
    return r0;
}
#define OPEN(p,f) call6(5,(long)(p),f,0,0,0,0)
#define OPENAT(d,p,f) call6(322,d,(long)(p),f,0,0,0)
#define READ(d,p,n) call6(3,d,(long)(p),n,0,0,0)
#define WRITE(d,p,n) call6(4,d,(long)(p),n,0,0,0)
#define SEND(d,p,n) call6(290,d,(long)(p),n,0x4000,0,0)
#define CLOSE(d) call6(6,d,0,0,0,0,0)
#define SEEK(d,n,w) call6(19,d,n,w,0,0,0)
#define SOCKET() call6(281,2,1,0,0,0,0)
#define BIND(d,p) call6(282,d,(long)(p),16,0,0,0)
#define LISTEN(d) call6(284,d,4,0,0,0,0)
#define ACCEPT(d,p,l) call6(285,d,(long)(p),(long)(l),0,0,0)
#define OPTION(d,level,name,p,n) call6(294,d,level,name,(long)(p),n,0)
#define SLEEP_NS(ns) do { long ts[2]={0,(ns)};(void)call6(162,(long)ts,0,0,0,0,0); } while(0)
#else
#include <stddef.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/socket.h>
#include <netinet/in.h>
#define OPEN(p,f) open(p,f)
#define OPENAT(d,p,f) openat(d,p,f)
#define READ(d,p,n) read(d,p,n)
#define WRITE(d,p,n) write(d,p,n)
#define SEND(d,p,n) send(d,p,n,0)
#define CLOSE(d) close(d)
#define SEEK(d,n,w) lseek(d,n,w)
#define SOCKET() socket(AF_INET,SOCK_STREAM,0)
#define BIND(d,p) bind(d,(const struct sockaddr *)(p),16)
#define LISTEN(d) listen(d,4)
#define ACCEPT(d,p,l) accept(d,(struct sockaddr *)(p),(socklen_t *)(l))
#define OPTION(d,level,name,p,n) setsockopt(d,level,name,p,n)
#define SLEEP_NS(ns) do { struct timespec ts={0,(ns)};(void)nanosleep(&ts,0); } while(0)
#include <time.h>
#endif

#ifdef __arm__
#define O_RDONLY_ 0
/* ARM uses different open-flag bits from asm-generic/x86. See
 * arch/arm/include/uapi/asm/fcntl.h in the Linux kernel. */
#define O_DIRECTORY_ (1 << 14)
#define O_NOFOLLOW_ (1 << 15)
#else
#define O_RDONLY_ O_RDONLY
#define O_DIRECTORY_ O_DIRECTORY
#define O_NOFOLLOW_ O_NOFOLLOW
#endif
#define MAX_REQUEST 1024u
#define MAX_PDB (16u*1024u*1024u)
#define MAX_ANALYSIS (4u*1024u*1024u)
#define MAX_AUDIO_FILE (512u*1024u*1024u)
#define MAX_AUDIO_RANGE (256u*1024u)
#ifndef AUDIO_SESSION_BUDGET
#define AUDIO_SESSION_BUDGET (8u*1024u*1024u)
#endif
#ifndef METADATA_PORT
#define METADATA_PORT 50131u
#endif
static unsigned char buffer[4096];
static unsigned int audio_bytes_sent;

static size_t length(const char *s) { size_t n=0; while(s[n]) n++; return n; }
static int equal(const char *a,const char *b) {
    size_t i=0; while(a[i] && b[i] && a[i]==b[i]) i++; return a[i]==0 && b[i]==0;
}
static int prefix(const char *a,const char *b) {
    size_t i=0; while(b[i]) { if(a[i]!=b[i]) return 0; i++; } return 1;
}
static int suffix(const char *a,const char *b) {
    size_t al=length(a),bl=length(b); return al>=bl && equal(a+al-bl,b);
}
static int send_all(int fd,const unsigned char *data,size_t count) {
    while(count) { long n=SEND(fd,data,count); if(n<=0) return 0; data+=n;count-=(size_t)n; }
    return 1;
}

/* Walk each path component with O_NOFOLLOW: no symlink can escape the USB.
 * Analysis paths may come from a PDB row, so never trust them as filesystem paths. */
static int open_relative(int root,const char *path,int audio) {
    char component[256];
    int parent=root,owned=0;
    const char *cursor=path;
    for (;;) {
        size_t n=0;
        while(cursor[n] && cursor[n]!='/') {
            char c=cursor[n];
            if(n+1>=sizeof(component) ||
               (audio ? ((unsigned char)c<32 || c=='\\') :
                !((c>='A'&&c<='Z')||(c>='a'&&c<='z')||
                  (c>='0'&&c<='9')||c=='.'))) goto bad;
            component[n]=c;n++;
        }
        if(!n || (n==1 && component[0]=='.') ||
           (n==2 && component[0]=='.' && component[1]=='.')) goto bad;
        component[n]=0;
        int more=cursor[n]=='/';
        int next=(int)OPENAT(parent,component,O_RDONLY_|O_NOFOLLOW_|
                             (more?O_DIRECTORY_:0));
        if(next<0) goto bad;
        if(owned) CLOSE(parent);
        parent=next;owned=1;
        if(!more) return parent;
        cursor+=n+1;
    }
bad:
    if(owned) CLOSE(parent);
    return -1;
}

static int allowed(const char *request,const char **relative,unsigned int *limit) {
    if(equal(request,"PDB")) {
        *relative="PIONEER/rekordbox/export.pdb";
        *limit=MAX_PDB;return 1;
    }
    if(!prefix(request,"ANLZ /PIONEER/USBANLZ/")) return 0;
    const char *path=request+5;
    size_t n=length(path);
    if(n<35 || n>240-5 ||
       !(suffix(path,"/ANLZ0000.DAT") || suffix(path,"/ANLZ0000.EXT"))) return 0;
    *relative=path+1;*limit=MAX_ANALYSIS;return 1;
}

static int hex_digit(char c) {
    if(c>='0'&&c<='9') return c-'0';
    if(c>='a'&&c<='f') return c-'a'+10;
    if(c>='A'&&c<='F') return c-'A'+10;
    return -1;
}
static int decode_audio_path(const char *hex,char *out,size_t capacity) {
    size_t n=length(hex);
    if(!n || (n&1) || n/2>=capacity) return 0;
    for(size_t i=0;i<n/2;i++) {
        int a=hex_digit(hex[2*i]),b=hex_digit(hex[2*i+1]);
        if(a<0||b<0) return 0;
        unsigned char c=(unsigned char)((a<<4)|b);
        if(c<32 || c==127 || c=='\\') return 0;
        out[i]=(char)c;
    }
    out[n/2]=0;
    if(!prefix(out,"Contents/")) return 0;
    return suffix(out,".wav") || suffix(out,".aif") || suffix(out,".aiff") ||
           suffix(out,".flac") || suffix(out,".mp3") || suffix(out,".m4a") ||
           suffix(out,".aac") || suffix(out,".WAV") || suffix(out,".AIFF") ||
           suffix(out,".FLAC") || suffix(out,".MP3");
}
static int parse_uint(const char *s,unsigned int *value) {
    unsigned int n=0;if(!*s) return 0;
    for(;*s;s++) {
        if(*s<'0'||*s>'9' || n>429496729u) return 0;
        unsigned int next=n*10u+(unsigned int)(*s-'0');
        if(next<n) return 0;
        n=next;
    }
    *value=n;return 1;
}
static size_t decimal(char *out,unsigned int n) {
    char reversed[10];size_t k=0;
    do { reversed[k++]=(char)('0'+n%10);n/=10; } while(n);
    for(size_t i=0;i<k;i++) out[i]=reversed[k-i-1];
    return k;
}
static void serve_audio(int client,int root,char *request) {
    int stat=prefix(request,"STAT "),range=prefix(request,"RANGE ");
    if(!stat && !range) { send_all(client,(const unsigned char *)"ERR\n",4);return; }
    char *hex=request+(stat?5:6),*offset_text=0,*count_text=0;
    if(range) {
        for(char *p=hex;*p;p++) if(*p==' ') { *p=0;offset_text=p+1;break; }
        if(!offset_text) goto error;
        for(char *p=offset_text;*p;p++) if(*p==' ') { *p=0;count_text=p+1;break; }
        if(!count_text) goto error;
    }
    char path[512];
    if(!decode_audio_path(hex,path,sizeof(path))) goto error;
    unsigned int offset=0,count=0;
    if(range && (!parse_uint(offset_text,&offset) || !parse_uint(count_text,&count) ||
                 count==0 || count>MAX_AUDIO_RANGE ||
                 count>AUDIO_SESSION_BUDGET-audio_bytes_sent)) goto error;
    int file=open_relative(root,path,1);
    if(file<0) goto error;
    long size=SEEK(file,0,2);
    if(size<0 || (unsigned long)size>MAX_AUDIO_FILE ||
       (range && ((unsigned long)offset>(unsigned long)size ||
                  count>(unsigned long)size-offset))) { CLOSE(file);goto error; }
    char header[48];size_t n=0;
    if(stat) {
        header[n++]='S';header[n++]='I';header[n++]='Z';header[n++]='E';header[n++]=' ';
        n+=decimal(header+n,(unsigned int)size);header[n++]='\n';
        send_all(client,(const unsigned char *)header,n);CLOSE(file);return;
    }
    if(SEEK(file,(long)offset,0)<0) { CLOSE(file);goto error; }
    /* Charge the whole accepted range before sending. A peer that disconnects
     * after a partial write must not recover its unused allowance by retrying. */
    audio_bytes_sent+=count;
    header[n++]='D';header[n++]='A';header[n++]='T';header[n++]='A';header[n++]=' ';
    n+=decimal(header+n,count);header[n++]=' ';
    n+=decimal(header+n,(unsigned int)size);header[n++]='\n';
    if(send_all(client,(const unsigned char *)header,n)) {
        unsigned int remaining=count;
        while(remaining) {
            unsigned int want=remaining<sizeof(buffer)?remaining:sizeof(buffer);
            long read_count=READ(file,buffer,want);
            if(read_count<=0) break;
            if(!send_all(client,buffer,(size_t)read_count)) break;
            remaining-=(unsigned int)read_count;
            SLEEP_NS(AUDIO_PACE_NS);
        }
    }
    CLOSE(file);return;
error:
    send_all(client,(const unsigned char *)"ERR\n",4);
}

static void serve_client(int client,int root) {
    char request[MAX_REQUEST+1];size_t count=0;
    while(count<MAX_REQUEST) {
        long n=READ(client,request+count,1);
        if(n!=1) return;
        if(request[count++]=='\n') break;
    }
    if(!count || request[count-1]!='\n') return;
    request[count-1]=0;
    if(prefix(request,"STAT ") || prefix(request,"RANGE ")) {
        serve_audio(client,root,request);return;
    }
    const char *relative=0;unsigned int limit=0;
    if(!allowed(request,&relative,&limit)) { send_all(client,(const unsigned char *)"ERR\n",4);return; }
    int file=open_relative(root,relative,0);
    if(file<0) { send_all(client,(const unsigned char *)"ERR\n",4);return; }
    long size=SEEK(file,0,2);
    if(size<0 || (unsigned long)size>limit || SEEK(file,0,0)<0) {
        CLOSE(file);send_all(client,(const unsigned char *)"ERR\n",4);return;
    }
    /* Never read a content byte before confirming the peer accepts the header.
     * Even on huge/corrupt files, no more than the fixed limit is transmitted. */
    if(send_all(client,(const unsigned char *)"OK\n",3)) {
        unsigned int total=0;
        for (;;) {
            long n=READ(file,buffer,sizeof(buffer));
            if(n<=0) break;
            if((unsigned int)n>limit-total) break;
            if(!send_all(client,buffer,(size_t)n)) break;
            total+=(unsigned int)n;
            SLEEP_NS(4000000u); /* Metadata stays near 1 MiB/s in every build. */
        }
    }
    CLOSE(file);
}

static int run(const char *root_path) {
#ifndef LOCAL_TEST
    if(!(prefix(root_path,"/media/usb1/") || prefix(root_path,"/media/usb2/"))) return 2;
#endif
    int root=(int)OPEN(root_path,O_RDONLY_|O_DIRECTORY_|O_NOFOLLOW_);
    if(root<0) return 3;
    int listener=(int)SOCKET();
    if(listener<0) { CLOSE(root);return 4; }
    int reuse=1;
    (void)OPTION(listener,1,2,&reuse,4);
    unsigned char address[16]={2,0,(unsigned char)(METADATA_PORT>>8),
                               (unsigned char)METADATA_PORT,
                               0,0,0,0,0,0,0,0,0,0,0,0};
#ifdef LOCAL_TEST
    address[4]=127;address[5]=0;address[6]=0;address[7]=1;
#ifdef __APPLE__
    address[0]=16;address[1]=2;
#endif
#endif
    if(BIND(listener,address)<0 || LISTEN(listener)<0) {
        CLOSE(listener);CLOSE(root);return 5;
    }
    for (;;) {
        unsigned char peer[16]={0};unsigned int peer_length=sizeof(peer);
        int client=(int)ACCEPT(listener,peer,&peer_length);
        if(client<0) continue;
#ifndef LOCAL_TEST
        if(peer_length<8 || peer[4]!=169 || peer[5]!=254) { CLOSE(client);continue; }
#endif
        /* A silent or stalled client cannot trap this process indefinitely. */
        long timeout[2]={2,0};
        (void)OPTION(client,1,20,timeout,sizeof(timeout));
        (void)OPTION(client,1,21,timeout,sizeof(timeout));
#if defined(LOCAL_TEST) && defined(__APPLE__)
        { int no_sigpipe=1;(void)OPTION(client,SOL_SOCKET,SO_NOSIGPIPE,&no_sigpipe,4); }
#endif
        serve_client(client,root);
        CLOSE(client);
    }
}

#ifdef __arm__
__attribute__((used)) static int entry(long *stack) {
    return stack[0]==2?run(((char **)(stack+1))[1]):1;
}
__asm__(".global _start\n_start:\nmov r0, sp\nbl entry\nmov r7, #1\nsvc 0\n");
#else
int main(int argc,char **argv) { return argc==2?run(argv[1]):1; }
#endif
