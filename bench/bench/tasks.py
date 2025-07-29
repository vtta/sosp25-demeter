# from fabric import task
import logging

from .utils import Balloon, Kernel

LOGGER = logging.getLogger(__name__)


def prepare_dirs(c, kernel):
    c.sudo("mkdir -p /home/clear /data /out")
    c.sudo("mount -t virtiofs data /data")
    c.sudo("mount -t virtiofs out /out")
    c.sudo("chown -R clear:clear /out /tmp")
    c.sudo(f"cp -rL /data/{kernel.value} /tmp/")
    c.sudo("rm -rf /lib/modules/$(uname -r)")
    c.sudo(f"ln -sf /tmp/{kernel.value} /lib/modules/$(uname -r)")
    c.sudo("depmod --all", hide=True)
    c.sudo("uname -a > /out/uname")


def prepare_kernel(c):
    c.sudo("sudo swupd autoupdate --disable", hide=True)
    c.sudo("sysctl -w kernel.kptr_restrict=0", hide=True)
    c.sudo("sysctl -w kernel.perf_event_paranoid=-1", hide=True)
    # c.sudo("sysctl -w kernel.perf_cpu_time_max_percent=25", hide=True)
    c.sudo("sysctl -w vm.overcommit_memory=1", hide=True)
    c.sudo("sysctl -w vm.compaction_proactiveness=0", hide=True)
    c.sudo("sysctl -w vm.extfrag_threshold=1000", hide=True)
    c.sudo("echo 2 | sudo tee /sys/kernel/mm/ksm/run", hide=True)
    c.sudo("echo 3 | sudo tee /proc/sys/vm/drop_caches", hide=True)
    c.sudo("echo 1 | sudo tee /sys/kernel/tracing/options/funcgraph-retval", hide=True, warn=True)
    c.sudo("echo never | sudo tee /sys/kernel/mm/transparent_hugepage/enabled", hide=True)
    c.sudo("echo never | sudo tee /sys/kernel/mm/transparent_hugepage/defrag", hide=True)
    c.sudo("swapoff -a")


def collect_logs(c):
    cp = [
        "/proc/vmstat",
        "/proc/zoneinfo",
        "/sys/kernel/debug/sched/numa_balancing",
        "/sys/kernel/debug/tracing/trace",
        "/sys/kernel/mm/",
    ]
    c.sudo("cp -rt /out " + " ".join(cp), hide=True, warn=True)
    mv = [
        "/home/clear/*.txt",
        "/home/clear/*.log",
        "/home/clear/*.err",
        "/home/clear/*.csv",
        "/home/clear/*.data",
    ]
    c.sudo("mv -ft /out " + " ".join(mv), hide=True, warn=True)
    c.sudo("dmesg > /out/dmesg")
    c.sudo("sysctl --all > /out/sysctl")


def enable_balloon(c, balloon):
    match Balloon(balloon):
        case Balloon.hetero:
            c.sudo("modprobe demeter_balloon")
        case Balloon.legacy:
            c.sudo("modprobe virtio_balloon")


def disable_tiering(c):
    c.sudo("sysctl -w kernel.numa_balancing=0", hide=True)
    c.sudo("echo 0 | sudo tee /sys/kernel/mm/numa/demotion_enabled", hide=True)


def launch(c, kernel, args, env: dict = {}, numactl="", time="/bin/time --verbose", launcher = None):
    if not launcher :
        match Kernel(kernel):
            case Kernel.demeter:
                launcher = "demeter.py "
            case Kernel.memtis:
                launcher = "memtis.py "
            case Kernel.nomad:
                launcher = "nomad.py "
            case Kernel.tpp:
                launcher = "tpp.py "
            # case Kernel.hemem:
            #     raise NotImplementedError
            case _:
                pass
    trap = "trap - SIGTERM; sudo pkill cat || true; sudo pkill nohup || true; kill 0"
    script = [
        f"trap {trap!r} SIGINT SIGTERM EXIT ;",
        'export PATH=/data:"$PATH" ;',
        *[f"export {k}={v} ;" for k, v in env.items()],
        f"sudo -E {numactl} {time} {launcher} {args}",
    ]
    LOGGER.info(" ".join(script))
    return c.run(" ".join(script))
