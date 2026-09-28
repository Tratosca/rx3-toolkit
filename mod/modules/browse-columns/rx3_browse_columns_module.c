/* SPDX-License-Identifier: MPL-2.0 */
#include "../core/api/rx3_module_api.h"
static const struct rx3_services *framework;
static const unsigned char owner;
static const uint16_t bpm[]={'B','P','M',0},key[]={'K','E','Y',0},artist[]={'A','R','T','I','S','T',0},duration[]={'T','I','M','E',0};
static struct rx3_browse_column selected;
static int configured(void){const char *s=getenv("RX3_BROWSE_COLUMNS");return s && s[0]=='1';}
static int start(const struct rx3_services *services)
{
    framework=services;selected.field=13;selected.caption=bpm;
    const char *s=getenv("RX3_BROWSE_FIELD");
    if(s && s[0]=='7' && !s[1]){selected.field=7;selected.caption=artist;}
    else if(s && s[0]=='1' && s[1] && !s[2]) {
        if(s[1]=='1'){selected.field=11;selected.caption=duration;}
        else if(s[1]=='5'){selected.field=15;selected.caption=key;}
    }
    return framework->browse->column(&owner,&selected);
}
static void stop(void){framework->browse->unregister_owner(&owner);}
const struct rx3_module rx3_browse_columns_module={
    .version=RX3_MODULE_API_VERSION,.size=sizeof(struct rx3_module),.name="browse-columns",
    .configured=configured,.start=start,.stop=stop
};
