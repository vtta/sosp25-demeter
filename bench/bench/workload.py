from pathlib import Path
from typing import Literal


def gups_args(
    bin: Path | str = Path("/data/gups"),
    thread: int = 4,
    update: int = int(8e8),
    granularity: int = 8,
    len: int = 14 << 30,
    workload: Literal["hotset", "zipf", "random"] = "hotset",
    hot: int = 1 << 30,
    weight: int = 9,
    reverse: bool = True,
    exponent: float = 0.99,
    # ms
    report: int | None = 1000,
    dram_ratio: int | None = None,  # report the percentage of memory in DRAM
):
    delta = (2 << 20) * thread  # avoid some trivial corner cases
    len -= delta
    hot -= delta
    args = f"{str(bin)} --{thread=} --{update=} --{len=} --{granularity=} "
    args += f"--{report=} " if report is not None else ""
    args += f"--dram-ratio {dram_ratio} " if dram_ratio is not None else ""
    match workload:
        case "hotset":
            args += f"{workload} --{hot=} --{weight=} "
            args += "--reverse " if reverse else ""
        case "zipf":
            args += f"{workload} --{exponent=} "
            args += "--reverse " if reverse else ""
        case "random":
            pass
        case _:
            raise ValueError(f"workload {workload} not supported")
    return args


def graph500_args(
    bin: Path | str = Path("/data/omp-csr"),
    s: int = 24,  # (memory exponentially)
    e: int = 24,  # (memory linearly)
    n: int = 10,  # (runtime)
):
    bin = str(bin)
    args = f"{bin} -V -s {s} -e {e} -n {n} "
    return args


def pagerank_args(
    bin: Path | str = Path("/data/pr"),
    f: Path | str = Path("/data/twitter.sg"),
    i: int = 20,
    n: int = 5,  # (runtime)
):
    bin, f = str(bin), str(f)
    args = f"{bin} -l -a -f {f} -n {n} -i {i} "
    return args


def xsbench_args(
    bin: Path | str = Path("/data/XSBench"),
    t: int = 4,  # threads
    l: int = 34,  # XS Lookups per Particle
    g: int = 25000,  # Gridpoints (per Nuclide) (memory linearly)
    p: int = 10000000,  # Particle Histories (runtime)
):
    bin = str(bin)
    args = f"{bin} -m history -G unionized -t {t} -l {l} -g {g} -p {p} "
    return args


def bwaves_args():
    args = "/data/bind-stdin /data/bwaves_s.in /data/bwaves_s "
    return args


# memtis (67.9GB)
# /data/train -m 36 -s 6 /data/kdd12
def liblinear_args(
    bin: Path | str = Path("/data/train"),
    m: int = 4,
    s: int = 2,
    model: Path | str = Path("/data/kdda"),
):
    bin, model = str(bin), str(model)
    args = f"{bin} -m {m} -s {s} {model} /dev/null "
    return args


def btree_args(
    bin: Path | str = Path("/data/bench_btree_mt"),
    n: int = 2 * 10**8,  # elements
    l: int = 2 * 10**10,  # lookups
):
    bin = str(bin)
    args = f"{bin} -- -n {n} -l {l} "
    return args


# silo(b="tpcc", s=10, n=5000000)
# memtis (58.1 GB)
# /data/dbtest --verbose --slow-exit --parallel-loading --bench ycsb --num-threads 36 --scale-factor 400000 --ops-per-worker=1000000000
def silo_args(
    bin: Path | str = Path("/data/dbtest"),
    b: str = "ycsb",
    t: int = 4,
    s: int = 55000,
    n: int = 100000000,
):
    bin = str(bin)
    args = bin + " --verbose --slow-exit --parallel-loading "
    args += f"--bench={b} --num-threads={t} --scale-factor={s} --ops-per-worker={n} "
    return args
