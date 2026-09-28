/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_KEYSHIFT_FEATURE_H
#define RX3_KEYSHIFT_FEATURE_H
static int keyshift_feature_configured(void)
{
    const char *value=getenv("RX3_KEYSHIFT");
    return value && value[0]=='1';
}
static int keyshift_feature_install(const struct rx3_services *services)
{
    framework=services;
    const char *sync=getenv("RX3_KEY_SYNC");
    keyshift_sync_enabled=sync && sync[0]=='1' && sync[1]==0;
    keyshift_sync_range=keyshift_parse_sync_range(getenv("RX3_KEY_SYNC_RANGE"));
    keyshift_sync_harmonic=keyshift_parse_sync_mode(getenv("RX3_KEY_SYNC_MODE"));
    keyshift_match_rules=rx3_match_rules(getenv("RX3_KEY_MATCH_RULES"));
    rx3_keyshift_install();
    if(rx3_keyshift_ready())keyshift_metadata_install();
    return rx3_keyshift_ready() && framework->panels->register_row(&keyshift_row);
}
static void keyshift_feature_remove(void)
{
    keyshift_metadata_remove();
    framework->panels->unregister_row(&keyshift_row);
    if(framework->browse && framework->browse->deck_key) {
        framework->browse->deck_key(0,-1,0);framework->browse->deck_key(1,-1,0);
    }
    rx3_keyshift_remove();
}
static void keyshift_feature_track_will_load(unsigned int deck, void *reader,
                                           const void *track_info)
{
    (void)reader; (void)track_info;
    /* Native metadata can precede PcmReader::load. The native cache
       writers own invalidation when the observer is active. */
    if(keyshift_metadata_active)return;
    if(deck<2)__atomic_store_n(&keyshift_track_key[deck],-1,__ATOMIC_SEQ_CST);
    if(framework->browse && framework->browse->deck_key)framework->browse->deck_key(deck,-1,0);
    __atomic_store_n(&keyshift_refresh_pending,1u,__ATOMIC_SEQ_CST);
}
static void keyshift_feature_track_did_load(unsigned int deck, void *reader,
                                           const void *track_info)
{
    (void)reader; (void)track_info;
    rx3_keyshift_reload(deck);
    if(deck<2 && framework->browse && framework->browse->deck_key)
        framework->browse->deck_key(deck,keyshift_base_key(deck),0);
    __atomic_store_n(&keyshift_refresh_pending,1u,__ATOMIC_SEQ_CST);
}
#endif
