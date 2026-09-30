/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_MODULES_H
#define RX3_MODULES_H
unsigned int rx3_modules_start(void);
unsigned int rx3_modules_failures(void);
void rx3_modules_stop(void);
void rx3_modules_track_did_load(unsigned int, void *, const void *);
void rx3_modules_track_will_load(unsigned int, void *, const void *);
struct rx3_text_observation;
void rx3_modules_audio_started(unsigned int);
void rx3_modules_text_observed(const struct rx3_text_observation *);
void rx3_modules_report(void);
int rx3_modules_uses_audio(void);
void rx3_modules_bind_writer(int (*)(unsigned long, const void *, const void *, unsigned int));
#endif
