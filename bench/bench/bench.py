import datetime
import logging
import sys
import time
from contextlib import ExitStack, contextmanager
from pathlib import Path
from threading import Event
from subprocess import check_output
from typing import Optional

import fabric
from fabric.exceptions import GroupException
from paramiko.ssh_exception import SSHException
from pydantic import BaseModel

from .tasks import *
from .utils import (
    PAGE_SIZE,
    Balloon,
    Kernel,
    function_name,
    node_memory_free,
    round_down,
    round_up,
)
from .workload import *

FORMAT = "%(asctime)s %(levelname)-8s %(name)-15s %(message)s"
LOGGER = logging.getLogger(__name__)


class Bench(BaseModel):
    """The configurations for running the bench"""

    num: int = 1  # How many VMs to launch
    cpu: int = 4  # How many vCPUs for each VM
    mem: int = 16 << 30  # How memory in byte for each VM
    dram_ratio: float = 0.4  # Initial DRAM ratio out of all system-ram
    dram_node: int = 1  # Which node is DRAM
    pmem_node: int = 3  # Which node is PMEM
    kernel: Kernel = Kernel.demeter  # Which design to use, could be hagent,
    hetero: bool = True  # Whether enable heterogeneous memory or not
    # pcm_memory: bool = False  # Whether record memory bandwidth when running workloads or not
    timeout: int = 60  # Timeout or retry on ssh connection
    balloon: Optional[Balloon] = (
        Balloon.hetero
    )  # Use our balloon the the traditional virtio-balloon
    gdb: bool = False  # Whether enable gdb or not
    env: dict = {}  # Additional environment variables to pass to the launcher
    pml: bool = False  # Whether enable PML or not

    @property
    def dram_size(self) -> int:
        return round_down(self.mem * self.dram_ratio, PAGE_SIZE)

    @property
    def pmem_size(self) -> int:
        return round_up(self.mem * (1 - self.dram_ratio), PAGE_SIZE)

    @property
    def out_dir(self) -> Path:
        if not hasattr(self, "_out"):
            self._out = str(
                Path("archive") / datetime.datetime.now().astimezone().isoformat()
            )
        return Path(self._out)

    @property
    def data_dir(self) -> Path:
        return Path("data")

    def _enable_logging(self):
        logger = logging.getLogger()
        handler = logging.FileHandler(self.out_dir / "main.log")
        formatter = logging.Formatter(FORMAT)
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    def _guests_prepare(self, vms):
        if self.hetero:
            # try allocating memory for balloon while avoiding OOM
            remain = len(vms)
            for retry in reversed(range(self.timeout)):
                while remain > 0:
                    free = node_memory_free(self.dram_node)
                    vmmem = self.mem
                    if not self.balloon:
                        vmmem *= self.dram_ratio
                    enough = free // vmmem
                    batch = min(enough, remain)
                    if batch == 0:
                        break
                    LOGGER.info(f"preparing guest id {remain - batch}..{remain}")
                    group = fabric.ThreadingGroup(
                        *[vm.ip for vm in vms[remain - batch : remain]],
                        **vms[0].ssh_config,
                    )
                    prepare_dirs(group, kernel=self.kernel)
                    prepare_kernel(group)
                    if self.balloon:
                        enable_balloon(group, balloon=self.balloon)
                        balloon_wait = int(self.mem >> 30) * 3
                        group.sudo(f"sleep {balloon_wait}")
                    remain -= batch
                if remain == 0:
                    break
                if retry == 0:
                    raise RuntimeError("Not enough memory for all VMs")
        else:
            LOGGER.info(f"preparing guest id 0..{len(vms)}")
            group = fabric.ThreadingGroup(*[vm.ip for vm in vms], **vms[0].ssh_config)
            prepare_dirs(group, kernel=self.kernel)
            prepare_kernel(group)
            if self.balloon:
                enable_balloon(group, balloon=self.balloon)
                balloon_wait = int(self.mem >> 30) * 3
                group.sudo(f"sleep {balloon_wait}")

    def _guests_wait(self, vms):
        [vm.wait_for_boot() for vm in vms]

    @contextmanager
    def guests(self):
        from .vm import Vm

        out = self.out_dir
        out.mkdir(parents=True)
        self._enable_logging()
        LOGGER.info("starting guests for workload:")
        LOGGER.info(" ".join(f"'{arg}'" for arg in sys.argv))
        LOGGER.info(self.model_dump())
        Path("out").unlink(missing_ok=True)
        Path("out").symlink_to(out)
        with ExitStack() as stack:
            # fix permissions after all process shutdown
            stack.callback(
                lambda: check_output(
                    f"sudo chown -R $(id -un):$(id -gn) {out}", shell=True
                )
            )
            vms = [stack.enter_context(Vm(id=id, bench=self)) for id in range(self.num)]
            self._guests = fabric.ThreadingGroup(
                *map(lambda vm: vm.ip, vms), **vms[0].ssh_config
            )
            self._guests_wait(vms)
            self._guests_prepare(vms)
            stack.callback(
                lambda: check_output(
                    f"sudo cp -r /sys/kernel/debug/kvm {out}", shell=True
                )
            )

            # if self.pcm_memory:
            #     stack.enter_context(pcm_memory(out / "pcm-memory.csv"))
            exit_evt = Event()
            try:
                yield self._guests
            except GroupException as e:
                LOGGER.warning(f"SSH error: {e}")
            except SSHException as e:
                LOGGER.warning(f"SSH error: {e}")
            finally:
                LOGGER.info("all guests stopping")
                exit_evt.set()

    def manual(self):
        with self.guests() as guests:
            time.sleep(999999999)

    def run(self, script):
        with self.guests() as guests:
            LOGGER.info(f"running script: {script!r}")
            guests.run(script)

    def _benchmark(self, name: str, launcher=None, **kwargs):
        if not launcher and not self.hetero:
            launcher = " "
        LOGGER.info(kwargs)
        args = eval(f"{name}_args(**kwargs)")
        args += f"2> /out/{name}.err | /data/ansi2txt | tee /out/{name}.log "
        default_env = dict(OMP_NUM_THREADS=self.cpu)
        with self.guests() as guests:
            result = launch(
                guests,
                self.kernel,
                args=args,
                env=default_env | self.env,
                launcher=launcher,
            )
            if result.failed:
                LOGGER.info(f"{name} failed")
                LOGGER.info(result)
            else:
                LOGGER.info(f"{name} finished")

    def gups(self, **kwargs):
        return self._benchmark(function_name(), **kwargs)

    def gups_perf_only(self, **kwargs):
        """
        mem_trans_retired.load_latency_gt_64
             [Counts randomly selected loads when the latency from first dispatch to
              completion is greater than 64 cycles Supports address when precise.
              Unit: cpu]
              cpu/event=0xcd,period=0x7d3,umask=0x1,ldlat=0x40/
        """
        perf_record = [
            "perf",
            "record",  # "-vvv",
            "--event",
            "mem_trans_retired.load_latency_gt_64:Pu",
            "--count",
            "4093",
            # "--phys-data",
            "--data",
            "--weight",
            "--output",
            "perf.data",
        ]
        return self._benchmark("gups", launcher=" ".join(perf_record), **kwargs)

    def graph500(self, **kwargs):
        return self._benchmark(function_name(), **kwargs)

    def pagerank(self, **kwargs):
        return self._benchmark(function_name(), **kwargs)

    def xsbench(self, **kwargs):
        return self._benchmark(function_name(), **kwargs)

    def bwaves(self, **kwargs):
        return self._benchmark(function_name(), **kwargs)

    def roms(self, **kwargs):
        return self._benchmark(function_name(), **kwargs)

    def liblinear(self, **kwargs):
        return self._benchmark(function_name(), **kwargs)

    def btree(self, **kwargs):
        return self._benchmark(function_name(), **kwargs)

    def silo(self, **kwargs):
        return self._benchmark(function_name(), **kwargs)
