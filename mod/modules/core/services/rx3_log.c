/* SPDX-License-Identifier: MPL-2.0 */
#include "../api/rx3_platform.h"
#include "rx3_log.h"
extern size_t strlen(const char *);

/* Where the log goes. RX3_LOG_FILE moves it; nothing else does. Read once in
   initialize(), so a hook that logs never touches the environment. */
static const char *log_file_path = "/tmp/rx3-stems.log";
/* The log lives on the drive a DJ is playing from. Past this it stops, once,
   with a line saying so, rather than filling the medium during a set. */
#define LOG_LIMIT_BYTES 0x20000
static char log_limit_reached;

void log_line(const char *message)
{
    if (log_limit_reached)
        return;
    int fd = open(log_file_path, O_WRONLY | O_CREAT | O_APPEND, 0600);
    if (fd < 0)
        return;
    if (lseek(fd, 0, SEEK_END) > LOG_LIMIT_BYTES) {
        log_limit_reached = 1;
        (void)write(fd, "log limit reached; further logging suppressed\n", 46u);
        close(fd);
        return;
    }
    /* One write, not two. Several threads log, and a message that arrives in
       two pieces can have another thread's line land between them. */
    char buffer[512];
    size_t n = strlen(message);
    if (n > sizeof(buffer) - 2u)
        n = sizeof(buffer) - 2u;
    memcpy(buffer, message, n);
    buffer[n] = '\n';
    (void)write(fd, buffer, n + 1u);
    close(fd);
}

void rx3_log_configure(void)
{
    const char *path = getenv("RX3_LOG_FILE");
    if (path && path[0]) log_file_path = path;
}
