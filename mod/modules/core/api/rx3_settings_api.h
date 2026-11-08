/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_SETTINGS_API_H
#define RX3_SETTINGS_API_H
/* A module's options, as declared in its manifest ("settings"). The value of
 * a live option the DJ changed in Utility, by key ("key-sync.range"), or null
 * when the option has no live row: the module's environment then holds it.
 * Any thread, no allocation or waiting; the string has process lifetime.
 * Read it from tick() and keep the parsed result: a change applies within one
 * tick. Options declared "live": false are only ever read from the
 * environment, at the next insertion of the drive.
 */
struct rx3_settings_service {
    const char *(*value)(const char *key);
};
#endif
