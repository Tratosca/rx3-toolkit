/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_KEYSHIFT_METADATA_H
#define RX3_KEYSHIFT_METADATA_H
/* Observe the native deck metadata cache after its two writers return. These
 * run on the native browse communication task even when the performance page is hidden. No database
 * access, polling, native lock or drawable geometry is needed. */
#define KEYSHIFT_KEY_LINE 0x00112544u
static const uint8_t keyshift_key_line_guard[8]={0x30,0x34,0x0f,0xe3,0x26,0x33,0x40,0xe3};
static const uint8_t *(*keyshift_key_line)(unsigned)=(void *)KEYSHIFT_KEY_LINE;
static void (*keyshift_original_info)(void *,unsigned,unsigned);
static void (*keyshift_original_convert)(unsigned);
static struct installed_hook keyshift_info_hook,keyshift_convert_hook;
static unsigned keyshift_metadata_callbacks;
static void keyshift_read_metadata(unsigned deck)
{
    if(deck>1)return;
    const uint8_t *line=keyshift_key_line(deck);
    uint16_t kind=0,length=0;
    if(line){memcpy(&kind,line+8,2);memcpy(&length,line+32,2);}
    int key=line && kind==15 && length>0 && length<=13?
        keyshift_key_from_glyph_text((const uint16_t *)(line+34),length):-1;
    keyshift_publish_key(deck,key);
}
static void keyshift_metadata_info(void *data,unsigned count,unsigned deck)
{
    __atomic_add_fetch(&keyshift_metadata_callbacks,1u,__ATOMIC_SEQ_CST);
    keyshift_original_info(data,count,deck);
    keyshift_read_metadata(deck);
    __atomic_sub_fetch(&keyshift_metadata_callbacks,1u,__ATOMIC_SEQ_CST);
}
static void keyshift_metadata_convert(unsigned deck)
{
    __atomic_add_fetch(&keyshift_metadata_callbacks,1u,__ATOMIC_SEQ_CST);
    keyshift_original_convert(deck);
    keyshift_read_metadata(deck);
    __atomic_sub_fetch(&keyshift_metadata_callbacks,1u,__ATOMIC_SEQ_CST);
}
static void keyshift_metadata_remove(void)
{
    int info=keyshift_original_info && detach_hook(&keyshift_info_hook);
    int convert=keyshift_original_convert && detach_hook(&keyshift_convert_hook);
    while(__atomic_load_n(&keyshift_metadata_callbacks,__ATOMIC_SEQ_CST))usleep(1000);
    if(info){release_hook(&keyshift_info_hook);keyshift_original_info=0;}
    if(convert){release_hook(&keyshift_convert_hook);keyshift_original_convert=0;}
    keyshift_metadata_active=0;
}
static int keyshift_metadata_install(void)
{
#if defined(__arm__)
    if(memcmp((const void *)KEYSHIFT_KEY_LINE,keyshift_key_line_guard,8))return 0;
    static const uint8_t info_guard[8]={0xf0,0x4f,0x2d,0xe9,0x00,0x60,0xa0,0xe1};
    static const uint8_t convert_guard[8]={0xf0,0x47,0x2d,0xe9,0x00,0x50,0xa0,0xe1};
    keyshift_original_info=(void *)install_hook(&keyshift_info_hook,0x1093f0u,info_guard,(void *)keyshift_metadata_info);
    if(keyshift_original_info)
        keyshift_original_convert=(void *)install_hook(&keyshift_convert_hook,0x108fbcu,convert_guard,(void *)keyshift_metadata_convert);
    if(!keyshift_original_info || !keyshift_original_convert){keyshift_metadata_remove();return 0;}
    keyshift_metadata_active=1;
    log_line("keyshift: native deck metadata observer active");
    return 1;
#else
    return 0;
#endif
}
#endif
