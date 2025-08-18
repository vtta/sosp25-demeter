import json
import logging
from contextlib import ExitStack
from io import StringIO
from itertools import chain, cycle, islice
from pathlib import Path
from subprocess import check_output, run

import fabric
from fabric.group import GroupException
from paramiko.ed25519key import Ed25519Key
from paramiko.ssh_exception import NoValidConnectionsError
from pydantic import BaseModel

from .bench import Bench
from .tasks import collect_logs
from .utils import Balloon, Kernel, daemon, node_to_cpus, pid_children, virtiofsd
from .vm_api import Api

LOGGER = logging.getLogger(__name__)
PUBLIC_KEY_TEXT = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINI0chGIKX8+R4oyO44rzLlAO+WBjzN5iJcQHp5pUtk3"
)
PRIVATE_KEY_TEXT = """-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW
QyNTUxOQAAACDSNHIRiCl/PkeKMjuOK8y5QDvlgY8zeYiXEB6eaVLZNwAAAJCP5DQjj+Q0
IwAAAAtzc2gtZWQyNTUxOQAAACDSNHIRiCl/PkeKMjuOK8y5QDvlgY8zeYiXEB6eaVLZNw
AAAEADukMln75L+JugPVHYDdF58mrKdT+DPbNROVEhI0QMDdI0chGIKX8+R4oyO44rzLlA
O+WBjzN5iJcQHp5pUtk3AAAADGpsaHVAcGM5MDA0OAE=
-----END OPENSSH PRIVATE KEY-----"""
PRIVATE_KEY = Ed25519Key.from_private_key(StringIO(PRIVATE_KEY_TEXT))


class MemoryStatistics(BaseModel):
    actual: int
    hetero_actual: int
    swap_in: int
    swap_out: int
    major_faults: int
    minor_faults: int
    free_memory: int
    total_memory: int
    available_memory: int
    disk_caches: int
    hugetlb_allocations: int
    hugetlb_failures: int
    dram_accesses: int
    dram_free: int
    dram_total: int
    pmem_accesses: int
    pmem_free: int
    pmem_total: int


class Vm(BaseModel):
    id: int
    bench: Bench

    @property
    def out_dir(self) -> Path:
        return self.bench.out_dir / str(self.id)

    @property
    def tap(self) -> str:
        return f"ichb{self.id}"

    @property
    def ip(self) -> str:
        return f"192.168.92.{self.id + 100}"

    @property
    def mac(self) -> str:
        return f"2e:89:a8:e4:92:{self.id:02x}"

    @property
    def ssh_config(self):
        return dict(
            user="clear",
            connect_timeout=self.bench.timeout,
            connect_kwargs=dict(pkey=PRIVATE_KEY),
            # disable stdin
            config=fabric.Config(
                overrides=dict(
                    run=dict(
                        in_stream=False,
                    ),
                ),
            ),
        )

    def memory_stats(self):
        json = self._api.vm.counters.get().json().get("__balloon", None)
        return MemoryStatistics(**json) if json else None

    def resize(self, desired_vcpus=None, desired_ram=None, desired_balloon=None):
        LOGGER.info(f"resize {desired_vcpus=} {desired_ram=} {desired_balloon=}")
        return self._api.vm.resize.put(
            desired_vcpus=desired_vcpus,
            desired_ram=desired_ram,
            desired_balloon=desired_balloon,
        )

    def cmdline(self, design, total_mem, dram_size, pmem_size):
        cmdline = [
            # essentials
            "root=/dev/vda2",
            "rw",
            "tsc=reliable",
            "console=ttyS0",
            "noreplace-smp",
            # speedup boot
            "cryptomgr.notests",
            "no_timer_check",
            # debugging
            "no_hash_pointers",
            "log_buf_len=32M",
            "initcall_debug",
            "mitigations=off",
            "kunit.enable=1",
            "nokaslr",
            # environment
            "modprobe.blacklist=virtio_balloon",
            "transparent_hugepage=never",
            "cgroup_no_v1=all",
        ]
        match design:
            # case Kernel.hemem:
            #     # The first 1G exists due to historical reason on x86_64
            #     dram_offset = (1 << 30) + total_mem - dram_size
            #     pmem_offset = (1 << 30) + total_mem
            #     cmdline += [f"memmap={dram_size}!{dram_offset}", f"memmap={total_mem}!{pmem_offset}"]
            case _:
                pass
        return " ".join(cmdline)

    def args(
        self,
        hetero,
        id,
        cpu_node,
        vcpus,
        total_mem,
        dram_node,
        dram_size,
        pmem_node,
        pmem_size,
        kernel,
        cmdline,
        rootfs,
        data_socket,
        out_socket,
        tap,
        mac,
        balloon: Balloon | None,
        gdb,
        pml,
        api,
    ):
        host_cpus = list(
            islice(cycle(node_to_cpus(cpu_node)), vcpus * id, vcpus * (id + 1))
        )
        host_cpus = ",".join(str(c) for c in host_cpus)
        affinity = ",".join(f"{v}@[{host_cpus}]" for v in range(vcpus))
        args = dict(
            binary=["cloud-hypervisor"],
            cpu=["--cpus", f"boot={vcpus},affinity=[{affinity}]"],
            memory=["--memory", "size=0,shared=on"],
            zones=[
                "--memory-zone",
                f"id=dram,size={total_mem if balloon else dram_size},shared=on,host_numa_node={dram_node}",
                f"id=pmem,size={total_mem if balloon else pmem_size},shared=on,host_numa_node={pmem_node}",
            ]
            if hetero
            else ["--memory-zone", f"id=ram,size={total_mem},shared=on"],
            numa=[
                "--numa",
                f"guest_numa_id=0,cpus=[0-{vcpus - 1}]",
                "guest_numa_id=1,memory_zones=[dram]",
                "guest_numa_id=2,memory_zones=[pmem]",
            ]
            if hetero
            else [],
            kernel=["--kernel", f"{kernel}"],
            cmdline=["--cmdline", cmdline],
            disk=["--disk", f"path={rootfs}"],
            fs=[
                "--fs",
                f"tag=data,socket={data_socket}",
                f"tag=out,socket={out_socket}",
            ],
            net=["--net", f"tap={tap},mac={mac}"],
            balloon=[
                "--balloon",
                balloon.to_cmdline(total_mem, dram_size, pmem_size)
                if hetero
                else "size=[0,0]",
            ]
            if balloon
            else [],
            console=["--console", "off"],
            serial=["--serial", "tty"],
            gdb=["--gdb", f"path={gdb}"] if gdb else [],
            pml=["--hmem", "delay=10s,interval=100ms"] if pml else [],
            api=["--api-socket", f"path={api}"],
        )
        return list(chain.from_iterable(args.values()))

    def __enter__(self):
        self.out_dir.mkdir(exist_ok=True)
        ch_socket = self.out_dir / "cloud-hypervisor.socket"
        gdb_socket = self.out_dir / "cloud-hypervisor-gdb.socket"
        data_socket = self.out_dir / "virtiofsd.data.socket"
        out_socket = self.out_dir / "virtiofsd.out.socket"
        kernel = self.bench.data_dir / self.bench.kernel.value / "vmlinux.bin"
        rootfs = self.bench.data_dir / f"root{self.id}.img"
        args = self.args(
            hetero=self.bench.hetero,
            id=self.id,
            cpu_node=self.bench.dram_node,
            vcpus=self.bench.cpu,
            total_mem=self.bench.mem,
            dram_node=self.bench.dram_node,
            dram_size=self.bench.dram_size,
            pmem_node=self.bench.pmem_node,
            pmem_size=self.bench.pmem_size,
            kernel=kernel,
            cmdline=self.cmdline(
                design=self.bench.kernel,
                total_mem=self.bench.mem,
                dram_size=self.bench.dram_size,
                pmem_size=self.bench.pmem_size,
            ),
            rootfs=rootfs,
            data_socket=data_socket,
            out_socket=out_socket,
            tap=self.tap,
            mac=self.mac,
            balloon=self.bench.balloon,
            gdb=gdb_socket if self.bench.gdb else None,
            pml=self.bench.pml,
            api=ch_socket,
        )
        LOGGER.info(f"{args=}")
        self._stack = ExitStack().__enter__()
        try:
            # start vhost-user filesystem device first
            self._stack.enter_context(virtiofsd(self.bench.data_dir, data_socket))
            self._stack.enter_context(virtiofsd(self.out_dir, out_socket))
            # create and boot the vm through command-line
            ch = self._stack.enter_context(
                daemon(
                    args,
                    stdout=ch_socket.with_suffix(".stdout"),
                    stderr=ch_socket.with_suffix(".stderr"),
                )
            )
            self._pid = ch.pid
            self._api = Api(ch_socket)
            info = self._api.vm.info.get()
            LOGGER.info(f"vm {self.id} booting: {info=}")
            self._ssh = fabric.Connection(self.ip, **self.ssh_config)
        except BaseException as e:
            LOGGER.error(f"failed to start vm {self.id}: {e}")
            self._stack.close()
            raise e
        return self

    @property
    def pid(self):
        return self._pid

    def collect_kvm_logs(self):
        """see kvm_create_vm_debugfs() in kvm_main.c"""
        vm_debugfs = list(
            chain.from_iterable(
                check_output(
                    f"sudo find /sys/kernel/debug/kvm/ -name '{pid}-*'",
                    shell=True,
                    text=True,
                )
                .strip()
                .split()
                for pid in pid_children(self.pid)
            )
        )
        assert len(vm_debugfs) == 1, (
            f"there should only be one vm_debugfs for each vm, found {len(vm_debugfs)} directories"
        )
        dir = Path(vm_debugfs[0])
        check_output(
            f"""
                sudo cp -r {dir} {self.out_dir} ;
                sudo chown -R $(id -un):$(id -gn) {self.out_dir} ;
                ln -srf {self.out_dir}/{dir.name} {self.out_dir}/kvm ;
                find {self.out_dir} -type s -delete || true ;
            """,
            shell=True,
        )

    def __exit__(self, ty, val, tb):
        LOGGER.info(f"vm {self.id} stopping")
        if ty is None:
            collect_logs(self._ssh)
            self.collect_kvm_logs()
            self._ssh.sudo("poweroff", hide=True, warn=True)
        return self._stack.__exit__(ty, val, tb)

    def wait_for_boot(self):
        for retry in reversed(range(self.bench.timeout)):
            try:
                self._ssh.run("date -Is", hide=True)
            except NoValidConnectionsError:
                pass
            except GroupException:
                pass
            else:
                LOGGER.info(f"vm {self.id} booted")
                break
            if retry == 0:
                raise RuntimeError(f"vm {self.id} failed to boot")
