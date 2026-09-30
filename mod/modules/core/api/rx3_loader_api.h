/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_LOADER_API_H
#define RX3_LOADER_API_H
/* One background worker for the files modules load: stems, sample banks.
 * Jobs run one at a time, in submission order, off every player thread, so
 * a job may open, read, map and wait. The worker allocates nothing; each job
 * owns its context. What a file means stays with the module.
 *
 * claim() and release() run on the serial startup/shutdown thread. submit()
 * may run on any thread but the audio threads; it copies the job and fails
 * when the queue is full. release() stops accepting the owner's jobs, drops
 * the queued ones (their discard runs), and returns once the owner's running
 * job has finished: a running job sees stopping() and should return early.
 */
struct rx3_load_job {
    void (*run)(void *context);
    void (*discard)(void *context);   /* optional: a job that never ran */
    void *context;
};
struct rx3_loader_service {
    int (*claim)(const void *owner);
    int (*submit)(const void *owner, const struct rx3_load_job *);
    int (*stopping)(const void *owner);
    void (*release)(const void *owner);
};
extern const struct rx3_loader_service rx3_loader;
#endif
