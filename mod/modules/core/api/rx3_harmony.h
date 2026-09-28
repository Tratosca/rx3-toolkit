/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_HARMONY_H
#define RX3_HARMONY_H
/* Bit 1 belonged to the retired diagonal rule. Keep the other bits stable. */
#define RX3_MATCH_BOOST_TWO 2u
#define RX3_MATCH_BOOST_SEVEN 4u
#define RX3_MATCH_FOUR 8u

/* Shared persisted rule mask; bit 1 is retired. */
static inline unsigned int rx3_match_rules(const char *value)
{
    if(value && value[0]>='0' && value[0]<='9') {
        unsigned int parsed=(unsigned int)(value[0]-'0');
        if(value[1]>='0' && value[1]<='9' && !value[2]) parsed=parsed*10u+(unsigned int)(value[1]-'0');
        else if(value[1]) parsed=16u;
        if(parsed<=15u)return parsed&14u;
    }
    return RX3_MATCH_BOOST_TWO;
}
static inline int rx3_camelot_compatible(int a, int b)
{
    if (a < 0 || b < 0 || a >= 24 || b >= 24) return 0;
    unsigned int an = (unsigned int)a / 2u, bn = (unsigned int)b / 2u;
    unsigned int al = (unsigned int)a & 1u, bl = (unsigned int)b & 1u;
    if (an == bn) return 1;
    if (al != bl) return 0;
    return (an + 1u) % 12u == bn || (bn + 1u) % 12u == an;
}


/* Return the matching rule, directed from the reference to the incoming track.
   These are suggestions, not guarantees for overlapping melodies. */
static inline int rx3_camelot_extended(int reference,int candidate,unsigned int rules)
{
    if(reference<0 || reference>=24 || candidate<0 || candidate>=24 ||
       rx3_camelot_compatible(reference,candidate)) return 0;
    unsigned int a=(unsigned int)reference/2u, b=(unsigned int)candidate/2u;
    unsigned int delta=(b+12u-a)%12u;
    if((reference&1)!=(candidate&1))return 0;
    if((rules&RX3_MATCH_BOOST_TWO) && delta==2u)return RX3_MATCH_BOOST_TWO;
    if((rules&RX3_MATCH_BOOST_SEVEN) && delta==7u)return RX3_MATCH_BOOST_SEVEN;
    if((rules&RX3_MATCH_FOUR) && delta==4u)return RX3_MATCH_FOUR;
    return 0;
}
static inline int rx3_camelot_matches(int reference,int candidate,unsigned int rules)
{
    return rx3_camelot_compatible(reference,candidate) ||
        rx3_camelot_extended(reference,candidate,rules);
}
/* Native compatibility comes from BROWSE, not an inferred wheel rule. */
static inline int rx3_harmonic_accepts(int reference,int candidate,unsigned native_keys,unsigned rules)
{
    if(reference<0 || reference>=24 || candidate<0 || candidate>=24)return 0;
    return (native_keys & (1u<<(unsigned)candidate)) != 0 ||
        rx3_camelot_extended(reference,candidate,rules)!=0;
}
static inline int rx3_harmonic_shifted(int key,int shift)
{
    if(key<0 || key>=24)return -1;
    int result=(key+shift*14)%24;return result<0?result+24:result;
}
static inline int rx3_harmonic_delta(int source,int current_shift,int reference,
                                    unsigned native_keys,unsigned rules,unsigned range,int harmonic)
{
    int here=rx3_harmonic_shifted(source,current_shift);
    if(here<0 || reference<0 || reference>=24 || range<1 || range>12)return 0;
    if(here==reference || (harmonic && rx3_harmonic_accepts(reference,here,native_keys,rules)))return 0;
    for(unsigned distance=1;distance<=range;distance++) {
        int fallback=0;
        for(int sign=1;sign>=-1;sign-=2) {
            int delta=sign*(int)distance,total=current_shift+delta;
            if(total < -12 || total > 12)continue;
            int target=rx3_harmonic_shifted(source,total);
            if(target==reference)return delta;
            if(!fallback && harmonic && rx3_harmonic_accepts(reference,target,native_keys,rules))fallback=delta;
        }
        if(fallback)return fallback;
    }
    return 0;
}
#endif
