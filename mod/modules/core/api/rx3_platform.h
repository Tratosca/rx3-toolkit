/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_PLATFORM_H
#define RX3_PLATFORM_H
/* ARM EABI declarations; no host headers or extra libc imports. */
typedef unsigned int   size_t;
typedef int            ssize_t;
typedef long           off_t;
typedef unsigned char  uint8_t;
typedef unsigned short uint16_t;
typedef short          int16_t;
typedef unsigned int   uint32_t;
typedef unsigned long long uint64_t;
typedef unsigned long pthread_t;

extern int      open(const char *, int, ...);
extern ssize_t  read(int, void *, size_t);
extern ssize_t  readlink(const char *, char *, size_t);
extern ssize_t  write(int, const void *, size_t);
extern int      close(int);
extern off_t    lseek(int, off_t, int);
extern void    *mmap(void *, size_t, int, int, int, off_t);
extern int      munmap(void *, size_t);
extern int      mprotect(void *, size_t, int);
extern long     sysconf(int);
extern void    *memcpy(void *, const void *, size_t);
extern void    *memset(void *, int, size_t);
extern int      memcmp(const void *, const void *, size_t);
extern char    *getenv(const char *);
extern int      pthread_create(pthread_t *, const void *, void *(*)(void *), void *);
extern int      pthread_detach(pthread_t);
extern int      pthread_join(pthread_t, void **);
extern int      usleep(unsigned int);
extern int      gettimeofday(void *, void *);

#define O_RDONLY 0
#define O_WRONLY 1
#define O_NONBLOCK 04000
#define O_CREAT  0100
#define O_TRUNC  01000
#define O_APPEND 02000
#define SEEK_SET 0
#define SEEK_END 2
#define PROT_READ  1
#define PROT_WRITE 2
#define PROT_EXEC  4
#define MAP_PRIVATE   2
#define MAP_ANONYMOUS 0x20
#define MAP_FAILED ((void *)-1)
#define _SC_PAGESIZE 30


#endif
