import logging
import os
import signal
import subprocess
import time
from contextlib import contextmanager
from enum import Enum
from pathlib import Path

LOGGER = logging.getLogger(__name__)

PAGE_SIZE = 4096


class Kernel(str, Enum):
    demeter = "demeter"
    memtis = "memtis"
    nomad = "nomad"
    tpp = "tpp"
    # hemem = "hemem"
    # vanilla = "vanilla"


class Balloon(str, Enum):
    hetero = "hetero"
    legacy = "legacy"

    def to_size(self, total_mem: int, dram_avail: int, pmem_avail: int):
        match self:
            case Balloon.hetero:
                return (total_mem - dram_avail, total_mem - pmem_avail)
            case Balloon.legacy:
                return (total_mem - dram_avail + total_mem - pmem_avail, 0)

    def to_cmdline(self, total_mem: int, dram_avail: int, pmem_avail: int):
        d, p = self.to_size(total_mem, dram_avail, pmem_avail)
        # ,statistics=1000ms
        match self:
            case Balloon.hetero:
                return f"size=[{d},{p}],heterogeneous_memory=on"
            case Balloon.legacy:
                return f"size=[{d},{p}]"


def erange(start, end, mul):
    while start < end:
        yield start
        start *= mul


def node_memory_total(node: int) -> int:
    import numa

    return numa.memory.node_memory_info(node)[0]


def node_memory_free(node: int) -> int:
    import numa

    return numa.memory.node_memory_info(node)[0]


def memory_nodes():
    import numa

    return filter(
        lambda n: node_memory_total(n) > 0, range(numa.info.get_max_possible_node() + 1)
    )


def node_to_cpus(node: int):
    from numa import LIBNUMA, utils

    cpu_mask = LIBNUMA.numa_allocate_cpumask()
    LIBNUMA.numa_bitmask_clearall(cpu_mask)
    res = LIBNUMA.numa_node_to_cpus(node, cpu_mask)
    if res == 0:
        return utils.get_bitset_list(cpu_mask)
    else:
        return []


@contextmanager
def daemon(args, stdout, stderr, sudo=False):
    with open(stdout, "w") as stdout, open(stderr, "w") as stderr:
        LOGGER.info(f"starting daemon {args[0]!r}")
        LOGGER.info(" ".join(f"{arg!r}" for arg in args))
        p = subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            preexec_fn=os.setsid if sudo else None,
        )
        try:
            yield p
        finally:
            if sudo:
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)
            else:
                p.terminate()
            p.wait()
            LOGGER.info(f"daemon {args[0]!r} exited with {p.returncode}")


def sshfs(ip: str, mount: Path):
    return daemon(
        ["sshfs", "-o", "allow_other,direct_io", f"clear@{ip}:/", f"{mount}"],
        stdout=mount.with_suffix(".stdout"),
        stderr=mount.with_suffix(".stderr"),
    )


def virtiofsd(shared: Path, socket: Path):
    return daemon(
        [
            "virtiofsd",
            "--cache=never",
            f"--socket-path={socket}",
            f"--shared-dir={shared}",
        ],
        stdout=socket.with_suffix(".stdout"),
        stderr=socket.with_suffix(".stderr"),
    )


def cloud_hypervisor(socket: Path):
    return daemon(
        ["cloud-hypervisor", "--api-socket", f"{socket}"],
        stdout=socket.with_suffix(".stdout"),
        stderr=socket.with_suffix(".stderr"),
    )


def pcm_memory(csv: Path):
    return daemon(
        ["sudo", "pcm-memory", "-nc", f"-csv={csv}"],
        stdout=csv.with_suffix(".stdout"),
        stderr=csv.with_suffix(".stderr"),
        sudo=True,
    )


def round_down(n, m):
    return int(n) // m * m


def round_up(n, m):
    return (int(n) + m - 1) // m * m


def function_name():
    import inspect
    from types import FrameType
    from typing import cast

    current = cast(FrameType, inspect.currentframe())
    caller = cast(FrameType, current.f_back)
    return caller.f_code.co_name


@contextmanager
def collect_datapoints(name: str, archive=Path("archive")):
    from datetime import datetime

    start = datetime.now()
    try:
        yield
    finally:
        end = datetime.now()
        time.sleep(1)

        def check_ts(d: Path) -> bool:
            ts = datetime.fromtimestamp(d.stat().st_ctime)
            return d.is_dir() and start < ts < end

        store = archive / (start.astimezone().isoformat() + "-" + name)
        store.mkdir(parents=True, exist_ok=True)
        [d.rename(store / d.name) for d in filter(check_ts, archive.iterdir())]


def pid_children(pid):
    """Get all child processes recursively for a given PID."""
    import subprocess

    out = subprocess.check_output(
        f"sudo pstree -p {pid} | grep -o '[[:digit:]]*'",
        shell=True,
    )
    return [int(pid) for pid in out.decode().strip().split()]
