/* SPDX-License-Identifier: MPL-2.0 */
#ifndef OC_JSON_H
#define OC_JSON_H
/* Bounded parser for the public index. Token next skips a complete value. */
struct oc_token { unsigned int start,end,next; };
struct oc_json {const char *s;unsigned int size,pos,count;struct oc_token *t;};
#define OC_TOKENS 131072u
static int oc_hex(char c) {return c>='0'&&c<='9'?c-'0':c>='a'&&c<='f'?c-'a'+10:c>='A'&&c<='F'?c-'A'+10:-1;}
static void oc_space(struct oc_json *j) {while(j->pos<j->size && (j->s[j->pos]==' '||j->s[j->pos]=='\n'||j->s[j->pos]=='\r'||j->s[j->pos]=='\t')) j->pos++;}
static int oc_value(struct oc_json *j,unsigned int depth)
{
    oc_space(j);if(depth>32||j->pos>=j->size||j->count>=OC_TOKENS) return -1;
    unsigned int id=j->count++;struct oc_token *t=&j->t[id];t->start=j->pos;
    char c=j->s[j->pos++];
    if(c=='{'||c=='[') {
        char end=c=='{'?'}':']';oc_space(j);
        if(j->pos<j->size&&j->s[j->pos]==end) j->pos++;
        else for(;;) {
            oc_space(j);
            if(c=='{' && (j->pos>=j->size||j->s[j->pos]!='"')) return -1;
            if(oc_value(j,depth+1)<0) return -1;
            if(c=='{') {oc_space(j);if(j->pos>=j->size||j->s[j->pos++]!=':')return -1;if(oc_value(j,depth+1)<0)return -1;}
            oc_space(j);if(j->pos>=j->size)return -1;
            char sep=j->s[j->pos++];if(sep==end)break;if(sep!=',')return -1;
        }
    } else if(c=='"') {
        int closed=0;
        while(j->pos<j->size) {
            unsigned char ch=(unsigned char)j->s[j->pos++];if(ch=='"'){closed=1;break;}if(ch<32)return -1;
            if(ch=='\\') {
                if(j->pos>=j->size)return -1;char e=j->s[j->pos++];
                if(e=='u') {for(unsigned int k=0;k<4;k++) if(j->pos>=j->size||oc_hex(j->s[j->pos++])<0)return -1;}
                else if(e!='"'&&e!='\\'&&e!='/'&&e!='b'&&e!='f'&&e!='n'&&e!='r'&&e!='t')return -1;
            }
        }
        if(!closed)return -1;
    } else {
        while(j->pos<j->size) {char x=j->s[j->pos];if(x==','||x=='}'||x==']'||x==' '||x=='\n'||x=='\r'||x=='\t')break;j->pos++;}
        unsigned int n=j->pos-t->start;const char *p=j->s+t->start;
        if(!((n==4&&!memcmp(p,"true",4))||(n==5&&!memcmp(p,"false",5))||(n==4&&!memcmp(p,"null",4)))) {
            unsigned int k=0;if(p[k]=='-')k++;if(k>=n)return -1;
            if(p[k]=='0')k++;else {if(p[k]<'1'||p[k]>'9')return -1;while(k<n&&p[k]>='0'&&p[k]<='9')k++;}
            if(k<n&&p[k]=='.'){k++;unsigned int b=k;while(k<n&&p[k]>='0'&&p[k]<='9')k++;if(k==b)return -1;}
            if(k<n&&(p[k]=='e'||p[k]=='E')) {k++;if(k<n&&(p[k]=='+'||p[k]=='-'))k++;unsigned int b=k;while(k<n&&p[k]>='0'&&p[k]<='9')k++;if(k==b)return -1;}
            if(k!=n)return -1;
        }
    }
    t->end=j->pos;t->next=j->count;return (int)id;
}
static int oc_string(struct oc_json *j,int id,char *out,unsigned int cap)
{
    if(id<0||j->s[j->t[id].start]!='"')return 0;
    unsigned int p=j->t[id].start+1,end=j->t[id].end-1,n=0;
    while(p<end) {
        unsigned int c=(unsigned char)j->s[p++];
        if(c=='\\') {
            c=(unsigned char)j->s[p++];
            if(c=='u') {
                c=0;for(unsigned int k=0;k<4;k++)c=(c<<4)|(unsigned int)oc_hex(j->s[p++]);
                if(c>=0xd800&&c<=0xdbff) {
                    if(p+6>end||j->s[p++]!='\\'||j->s[p++]!='u')return 0;
                    unsigned int lo=0;for(unsigned int k=0;k<4;k++)lo=(lo<<4)|(unsigned int)oc_hex(j->s[p++]);
                    if(lo<0xdc00||lo>0xdfff)return 0;c=0x10000+((c-0xd800)<<10)+(lo-0xdc00);
                } else if(c>=0xdc00&&c<=0xdfff)return 0;
                if(c<32)return 0;
                if(c>=0x80) {
                    unsigned int bytes=c<0x800?2:c<0x10000?3:4;if(n+bytes>=cap)return 0;
                    out[n++]=(char)((bytes==2?0xc0:bytes==3?0xe0:0xf0)|(c>>(6*(bytes-1))));
                    for(unsigned int k=bytes-1;k;k--)out[n++]=(char)(0x80|((c>>(6*(k-1)))&63));continue;
                }
            } else if(c=='b'||c=='f'||c=='n'||c=='r'||c=='t')return 0;
        }
        if(n+1>=cap||!c)return 0;out[n++]=(char)c;
    }
    out[n]=0;return 1;
}
static int oc_key(struct oc_json *j,int object,const char *key)
{
    if(object<0||j->s[j->t[object].start]!='{')return -1;
    int found=-1;char name[128];
    for(unsigned int k=(unsigned int)object+1;k<j->t[object].next;) {
        unsigned int v=k+1;if(v>=j->count)return -1;
        if(oc_string(j,(int)k,name,sizeof(name))&&!strcmp(name,key)) {if(found>=0)return -1;found=(int)v;}
        k=j->t[v].next;
    }
    return found;
}
static int oc_number(struct oc_json *j,int id,unsigned int *out)
{
    if(id<0)return 0;unsigned int v=0;
    for(unsigned int k=j->t[id].start;k<j->t[id].end;k++) {
        char c=j->s[k];if(c<'0'||c>'9'||v>429496729u||(v==429496729u&&c>'5'))return 0;v=v*10+(unsigned int)(c-'0');
    }
    *out=v;return 1;
}
static int oc_digest(struct oc_json *j,int object,const char *key,uint8_t out[32])
{
    char text[65];if(!oc_string(j,oc_key(j,object,key),text,sizeof(text))||strlen(text)!=64)return 0;
    for(unsigned int i=0;i<32;i++) {int a=oc_hex(text[i*2]),b=oc_hex(text[i*2+1]);if(a<0||b<0)return 0;out[i]=(uint8_t)(a*16+b);}
    return 1;
}
#endif
