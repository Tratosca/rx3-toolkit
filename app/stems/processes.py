# SPDX-License-Identifier: MPL-2.0
"""Own child processes for one cancellable preparation or installation."""
import contextlib
import contextvars
import os
import signal
import subprocess
import threading


class Cancelled(Exception):
    pass


_current = contextvars.ContextVar("stems_processes", default=None)


def stop(process):
    """Stop the owned process group, including FFmpeg started by a separator."""
    if os.name == "nt":
        if process.poll() is None:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           capture_output=True, timeout=10)
            if process.poll() is None:
                process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                pass
            # A child can outlive the group leader.
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=10)


class Control:
    def __init__(self):
        self._lock = threading.Lock()
        self._cancelled = threading.Event()
        self._children = set()

    def checkpoint(self):
        if self._cancelled.is_set():
            raise Cancelled()

    def start(self, command, **kwargs):
        with self._lock:
            self.checkpoint()
            process = _spawn(command, **kwargs)
            self._children.add(process)
        return process

    def cancel(self):
        with self._lock:
            self._cancelled.set()
            children = tuple(self._children)
        for process in children:
            if process.poll() is None:
                stop(process)

    @contextlib.contextmanager
    def bind(self):
        token = _current.set(self)
        try:
            yield self
        finally:
            try:
                for process in tuple(self._children):
                    if process.poll() is None:
                        stop(process)
            finally:
                _current.reset(token)


def _spawn(command, **kwargs):
    if os.name != "nt":
        kwargs["start_new_session"] = True
    return subprocess.Popen(command, **kwargs)


def start(command, **kwargs):
    control = _current.get()
    return control.start(command, **kwargs) if control else _spawn(command, **kwargs)


def checkpoint():
    control = _current.get()
    if control:
        control.checkpoint()


def run(command, **kwargs):
    if _current.get() is None:
        return subprocess.run(command, **kwargs)
    if kwargs.pop("capture_output", False):
        kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    timeout = kwargs.pop("timeout", None)
    check = kwargs.pop("check", False)
    with start(command, **kwargs) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except BaseException:
            stop(process)
            raise
    checkpoint()
    if check and process.returncode:
        raise subprocess.CalledProcessError(process.returncode, command, stdout, stderr)
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
