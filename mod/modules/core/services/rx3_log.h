/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_LOG_H
#define RX3_LOG_H
void rx3_log_configure(void);
void log_line(const char *);
/* One line: the label followed by the decimal value. */
void rx3_log_number(const char *, unsigned long);
#endif
