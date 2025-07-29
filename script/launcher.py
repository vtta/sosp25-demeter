#!/usr/bin/env python3
import argparse
import ctypes
import os
import signal
import sys
from contextlib import ExitStack, contextmanager
from enum import Enum
from errno import EINVAL
from functools import partial
from pathlib import Path
from signal import SIGINT
from subprocess import DEVNULL, Popen, run


@contextmanager
def noop(pid: int = -1):
    try:
        yield
    finally:
        pass


@contextmanager
def demeter(pid: int = -1):
    procfs = Path("/proc/sys")
    sysfs = Path("/sys/kernel")
    targets = Path("/sys/kernel/mm/demeter/targets")
    modprobe = ["modprobe", "demeter_placement"]
    for modarg in [
        "load_latency_threshold",
        "load_latency_sample_period",
        "load_l3_miss_sample_period",
        "retired_stores_sample_period",
        "split_period_ms",
        "throttle_pulse_width_ms",
        "throttle_pulse_period_ms",
        "rtree_split_thresh",
        "rtree_exch_thresh",
    ]:
        exec(f"""if {modarg} := os.getenv("{modarg}", None):
            {modarg} = int({modarg})
            modprobe += [f"{{{modarg}=}}"]
        """)
    try:
        (procfs / "kernel" / "numa_balancing").write_text("0")
        (sysfs / "mm" / "numa" / "demotion_enabled").write_text("0")
        print(modprobe, file=sys.stderr)
        run(modprobe)
        (targets / "nr_targets").write_text("3")
        (targets / "0" / "pid").write_text(str(pid))
        yield
    finally:
        (targets / "0" / "pid").write_text("-1")


class Syscall(Enum):
    @staticmethod
    def build(nr, *argtypes):
        fn = ctypes.CDLL(None).syscall
        fn.argtypes = [ctypes.c_long, *argtypes]
        fn.restype = ctypes.c_long
        return partial(fn, nr)

    def __call__(self, *args, **kwargs):
        return self.value(*args, **kwargs)

    htmm_start = build(449, ctypes.c_int, ctypes.c_int)
    htmm_end = build(450, ctypes.c_int)


@contextmanager
def memtis(pid: int = -1):
    """Enable HTMM globally by default."""
    procfs = Path("/proc/sys")
    sysfs = Path("/sys/kernel")
    modargs = dict()
    for modarg in [
        "htmm_adaptation_period",
        "htmm_cooling_period",
        "htmm_cxl_mode",
        "htmm_demotion_period_in_ms",
        "htmm_gamma",
        "htmm_inst_sample_period",
        "htmm_mode",
        "htmm_nowarm",
        "htmm_promotion_period_in_ms",
        "htmm_sample_period",
        "htmm_skip_cooling",
        "htmm_split_period",
        "htmm_thres_cooling_alloc",
        "htmm_thres_hot",
        "htmm_thres_split",
        "htmm_util_weight",
        "ksampled_max_sample_ratio",
        "ksampled_min_sample_ratio",
        "ksampled_soft_cpu_quota",
    ]:
        exec(f"""if {modarg} := os.getenv("{modarg}", None):
            {modarg} = int({modarg})
            modargs["{modarg}"] = {modarg}
        """)
    try:
        (procfs / "kernel" / "numa_balancing").write_text("0")
        (sysfs / "mm" / "numa" / "demotion_enabled").write_text("0")
        for key, value in modargs.items():
            (sysfs / "mm" / "htmm" / key).write_text(str(value))
        Syscall.htmm_start(pid, 0)
        yield
    finally:
        Syscall.htmm_end(pid)


@contextmanager
def nomad(pid: int = -1):
    procfs = Path("/proc/sys")
    sysfs = Path("/sys/kernel")
    debugfs = sysfs / "debug"
    try:
        (procfs / "kernel" / "numa_balancing").write_text("2")
        (sysfs / "mm" / "numa" / "demotion_enabled").write_text("1")
        (procfs / "vm" / "demote_scale_factor").write_text("1000")
        # (debugfs / "sched" / "numa_balancing" / "scan_period_min_ms").write_text("1000")
        # (debugfs / "sched" / "numa_balancing" / "scan_period_max_ms").write_text("100000")
        # (debugfs / "sched" / "numa_balancing" / "scan_size_mb").write_text("256")
        # (debugfs / "sched" / "numa_balancing" / "scan_period_min_ms").write_text("10")
        # (debugfs / "sched" / "numa_balancing" / "scan_period_max_ms").write_text("2000")
        run(["modprobe", "async_promote"])
        yield
    finally:
        # (procfs / "kernel" / "numa_balancing").write_text("0")
        # (sysfs / "mm" / "numa" / "demotion_enabled").write_text("0")
        # run(["rmmod", "async_promote"])
        pass


@contextmanager
def tpp(pid: int = -1):
    procfs = Path("/proc/sys")
    sysfs = Path("/sys/kernel")
    debugfs = sysfs / "debug"
    try:
        (procfs / "kernel" / "numa_balancing").write_text("2")
        (sysfs / "mm" / "numa" / "demotion_enabled").write_text("1")
        (procfs / "vm" / "demote_scale_factor").write_text("1000")
        # (debugfs / "sched" / "numa_balancing" / "scan_period_min_ms").write_text("1000")
        # (debugfs / "sched" / "numa_balancing" / "scan_period_max_ms").write_text("100000")
        # (debugfs / "sched" / "numa_balancing" / "scan_size_mb").write_text("256")
        # (debugfs / "sched" / "numa_balancing" / "scan_period_min_ms").write_text("10")
        # (debugfs / "sched" / "numa_balancing" / "scan_period_max_ms").write_text("2000")
        yield
    finally:
        # (procfs / "kernel" / "numa_balancing").write_text("0")
        # (sysfs / "mm" / "numa" / "demotion_enabled").write_text("0")
        pass


@contextmanager
def daemon(args, label: str | None = None, out=Path("/out"), sudo=True):
    stdout = (out / (label or args[0])).with_suffix(".log")
    stderr = (out / (label or args[0])).with_suffix(".err")
    with open(stdout, "w") as stdout, open(stderr, "w") as stderr:
        p = Popen(
            args,
            stdin=DEVNULL,
            stdout=stdout,
            stderr=stderr,
            preexec_fn=os.setsid if sudo else None,
        )
        try:
            yield p
        finally:
            os.killpg(os.getpgid(p.pid), signal.SIGINT) if sudo else p.send_signal(
                signal.SIGINT
            )
            p.wait()


@contextmanager
def trace():
    with ExitStack() as stack:
        for t in [
            # [["mmap_lock_acquire_returned.bt"]],
            # [["tlb_flush.py"]],
            # [["funclatency.py", "(handle_mm_fault|change_prot_numa|__update_pginfo)"], "fault_time"],
        ]:
            stack.enter_context(daemon(*t))
        try:
            yield stack
        finally:
            pass


def parent(ctxfn, child: int):
    parent = os.getpid()
    err = -1
    with ctxfn(child), trace():
        print(f"{parent=} {child=}")
        try:
            pid, status = os.waitpid(child, 0)
            err = os.waitstatus_to_exitcode(status)
        except KeyboardInterrupt:
            os.kill(child, SIGINT)
    sys.exit(err)


def child(file, *args):
    print(f"execvp({file=}, {args=}")
    os.execvp(file, args)


@contextmanager
def cgroup(pid, memtis: bool = False):
    root = Path("/sys/fs/cgroup/")
    group = Path("/sys/fs/cgroup/bench")
    try:
        group.mkdir(parents=True, exist_ok=True)
        if memtis:
            (group / "memory.htmm_enabled").write_text("enabled")
        (group / "cgroup.procs").write_text(str(pid))
        yield
    finally:
        (root / "cgroup.procs").write_text(str(pid))
        group.rmdir()


def prog2ctx(prog):
    ctx = dict(demeter=demeter, memtis=memtis, nomad=nomad, tpp=tpp, noop=noop)
    return ctx[prog]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Launch a program with tiered memory support enabled."
    )
    parser.add_argument("CHILD", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    prog = Path(parser.prog).stem
    with cgroup(os.getpid(), prog == "memtis"):
        ctxfn = prog2ctx(prog)
        child_args = args.CHILD
        if child_args and child_args[0] == "--":
            child_args.pop(0)
        if not child_args:
            parser.print_help()
            sys.exit(EINVAL)
        pid = os.fork()
        parent(ctxfn, pid) if pid > 0 else child(child_args[0], *child_args)
