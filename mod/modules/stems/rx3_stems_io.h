/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_STEMS_IO_H
#define RX3_STEMS_IO_H
/* Cancellation is observed between bounded reads/CRC chunks. A kernel read
   already blocked on the device cannot be interrupted by this protocol. */
#define STEMS_IO_CHUNK 65536u
struct stems_io {
    int (*cancelled)(const void *);
    const void *context;
};
static int stems_io_cancelled(const struct stems_io *io)
{
    return io && io->cancelled && io->cancelled(io->context);
}
static int stems_read(int fd, void *destination, size_t length, const struct stems_io *io)
{
    uint8_t *cursor = destination;
    while (length) {
        if (stems_io_cancelled(io)) return -1;
        size_t count = length > STEMS_IO_CHUNK ? STEMS_IO_CHUNK : length;
        ssize_t got = read(fd, cursor, count);
        if (got <= 0) return -1;
        cursor += got;
        length -= (size_t)got;
    }
    return stems_io_cancelled(io) ? -1 : 0;
}
#endif
