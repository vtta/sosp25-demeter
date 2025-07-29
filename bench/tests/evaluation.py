from functools import partial
import logging
from contextlib import contextmanager
from itertools import dropwhile, product
from pathlib import Path
from typing import Iterable, cast
from datetime import datetime, timezone
import os

from bench.bench import Bench
from bench.utils import (
    Balloon,
    Kernel,
    collect_datapoints,
    erange,
    function_name,
    node_memory_total,
    node_to_cpus,
)

import pytest

LOGGER = logging.getLogger(__name__)


@pytest.fixture
def vm_numbers():
    """Fixture providing a list of VM numbers."""
    return [1, 5, 9]
    # return [1, 4, 7]


@pytest.fixture
def max_vm_number(vm_numbers):
    """Fixture providing the maximum number of VMs."""
    return max(vm_numbers)


@pytest.fixture
def avg_vm_number(vm_numbers):
    """Fixture providing the average number of VMs."""
    return sum(vm_numbers) // len(vm_numbers)


@pytest.fixture
def kernel_variants():
    """Fixture providing a list of kernel variants."""
    return Kernel


@pytest.fixture
def bench_base():
    """Fixture providing a base Bench configuration."""
    # https://docs.python.org/3/library/functools.html#functools.partial
    # partial allows us to provide default arguments while enabling overriding
    return partial(
        Bench,
        num=1,
        cpu=4,
        mem=16 << 30,
        dram_ratio=0.2,
        dram_node=1,
        pmem_node=3,
        # pmem_node=0,
        hetero=True,
        balloon=Balloon.hetero,
        env=dict(),
    )


@pytest.fixture
def bench_base_dram_only(bench_base):
    return partial(
        bench_base,
        dram_ratio=1.0,
        hetero=False,
        balloon=None,
        kernel=Kernel.demeter,
    )


@pytest.fixture
def bench_base_dram_only_pml(bench_base_dram_only):
    return partial(
        bench_base_dram_only,
        pml=True,
    )


@pytest.fixture
def bench_hbase(bench_base):
    return partial(
        bench_base,
        dram_node=0,
        pmem_node=2,
        dram_ratio=1.0,
        # hetero=True allocated guests memory nodes (zones) on fixed host nodes, forbids management from hypervisor
        hetero=False,
        # no balloon is needed if hetero=False
        balloon=None,
        # guest kernel makes no differences, as no numa node is assigned to guests
        kernel=Kernel.tpp,
    )


@pytest.fixture
def bench_large(bench_base):
    return partial(
        bench_base,
        cpu=36,
        mem=144 << 30,
        dram_ratio=0.25,
        balloon=None,
    )


@pytest.fixture
def bench_hlarge(bench_large):
    return partial(
        bench_large,
        dram_node=0,
        pmem_node=2,
        kernel=Kernel.tpp,
        hetero=False,
    )


@pytest.fixture
def gups_base():
    return partial(
        Bench.gups,
        thread=4,
        update=int(9e8),
        granularity=8,
        len=14 << 30,
        workload="hotset",
        hot=1 << 30,
        weight=9,
        reverse=True,
        report=1000,
        # dram_ratio=10000,
        dram_ratio=None,
    )

@pytest.fixture
def gups_base_pebs():
    return partial(
        Bench.gups_perf_only,
        thread=4,
        update=int(9e8),
        granularity=8,
        len=14 << 30,
        workload="hotset",
        hot=1 << 30,
        weight=9,
        reverse=True,
        report=None,
        dram_ratio=None,
    )


@pytest.fixture
def gups_large():
    return partial(
        Bench.gups,
        thread=36,
        update=400000000,
        granularity=8,
        len=126 << 30,
        workload="hotset",
        hot=9 << 30,
        weight=9,
        reverse=True,
        report=1000,
        dram_ratio=None,
    )


@pytest.fixture
def btree_base():
    return partial(
        Bench.btree,
        n=2 * 10**8,
        l=2 * 10**10,
    )


@pytest.fixture
def bwaves_base():
    return partial(
        Bench.bwaves,
    )


@pytest.fixture
def graph500_base():
    return partial(
        Bench.graph500,
        s=24,
        e=24,
        n=16,
    )


@pytest.fixture
def liblinear_base():
    return partial(
        Bench.liblinear,
        m=4,
        s=2,
    )


@pytest.fixture
def liblinear_large():
    return partial(
        Bench.liblinear,
        m=36,
        s=6,
        model="/data/kdd12",
    )


@pytest.fixture
def pagerank_base():
    return partial(
        Bench.pagerank,
        i=20,
        n=3,
    )


@pytest.fixture
def silo_base():
    return partial(
        Bench.silo,
        b="ycsb",
        t=4,
        s=55000,
        n=100000000,
    )


@pytest.fixture
def silo_large():
    return partial(
        Bench.silo,
        b="ycsb",
        t=36,
        s=400000,
        n=1000000000,
    )


@pytest.fixture
def xsbench_base():
    return partial(
        Bench.xsbench,
        t=4,
        l=32,
        g=25000,
        p=10000000,
    )


def test_gups(bench_base, gups_base, vm_numbers, kernel_variants):
    with collect_datapoints(function_name()):
        for vmnum, kernel in product(vm_numbers, kernel_variants):
            gups_base(bench_base(num=vmnum, kernel=kernel))


def test_btree(bench_base, btree_base, vm_numbers, kernel_variants):
    with collect_datapoints(function_name()):
        for vmnum, kernel in product(vm_numbers, kernel_variants):
            btree_base(bench_base(num=vmnum, kernel=kernel))


def test_bwaves(bench_base, bwaves_base, vm_numbers, kernel_variants):
    with collect_datapoints(function_name()):
        for vmnum, kernel in product(vm_numbers, kernel_variants):
            bwaves_base(bench_base(num=vmnum, kernel=kernel))


def test_graph500(bench_base, graph500_base, vm_numbers, kernel_variants):
    with collect_datapoints(function_name()):
        for vmnum, kernel in product(vm_numbers, kernel_variants):
            graph500_base(bench_base(num=vmnum, kernel=kernel))


def test_liblinear(bench_base, liblinear_base, vm_numbers, kernel_variants):
    with collect_datapoints(function_name()):
        for vmnum, kernel in product(vm_numbers, kernel_variants):
            liblinear_base(bench_base(num=vmnum, kernel=kernel))


def test_pagerank(bench_base, pagerank_base, vm_numbers, kernel_variants):
    with collect_datapoints(function_name()):
        for vmnum, kernel in product(vm_numbers, kernel_variants):
            pagerank_base(bench_base(num=vmnum, kernel=kernel))


def test_silo(bench_base, silo_base, vm_numbers, kernel_variants):
    with collect_datapoints(function_name()):
        for vmnum, kernel in product(vm_numbers, kernel_variants):
            silo_base(bench_base(num=vmnum, kernel=kernel))


def test_xsbench(bench_base, xsbench_base, vm_numbers, kernel_variants):
    with collect_datapoints(function_name()):
        for vmnum, kernel in product(vm_numbers, kernel_variants):
            xsbench_base(bench_base(num=vmnum, kernel=kernel))


# figure 10-12
def test_hypervisor_realworld_workloads(
    bench_hbase,
    max_vm_number,
    gups_base,
    btree_base,
    bwaves_base,
    graph500_base,
    liblinear_base,
    pagerank_base,
    silo_base,
    xsbench_base,
):
    assert "5.15.162-tpphost" == os.uname().release
    vm_numbers = [max_vm_number]
    kernel_variants = [Kernel.tpp]
    with collect_datapoints(function_name()):
        test_gups(bench_hbase, gups_base, vm_numbers, kernel_variants)
        test_btree(bench_hbase, btree_base, vm_numbers, kernel_variants)
        test_bwaves(bench_hbase, bwaves_base, vm_numbers, kernel_variants)
        test_graph500(bench_hbase, graph500_base, vm_numbers, kernel_variants)
        test_liblinear(bench_hbase, liblinear_base, vm_numbers, kernel_variants)
        test_pagerank(bench_hbase, pagerank_base, vm_numbers, kernel_variants)
        test_silo(bench_hbase, silo_base, vm_numbers, kernel_variants)
        test_xsbench(bench_hbase, xsbench_base, vm_numbers, kernel_variants)


# figure 10-11
def test_delegated_realworld_workloads(
    bench_base,
    vm_numbers,
    kernel_variants,
    gups_base,
    btree_base,
    bwaves_base,
    graph500_base,
    liblinear_base,
    pagerank_base,
    silo_base,
    xsbench_base,
):
    assert "6.10.0-demeterhost" == os.uname().release
    with collect_datapoints(function_name()):
        test_gups(bench_base, gups_base, vm_numbers, kernel_variants)
        test_btree(bench_base, btree_base, vm_numbers, kernel_variants)
        test_bwaves(bench_base, bwaves_base, vm_numbers, kernel_variants)
        test_graph500(bench_base, graph500_base, vm_numbers, kernel_variants)
        test_liblinear(bench_base, liblinear_base, vm_numbers, kernel_variants)
        test_pagerank(bench_base, pagerank_base, vm_numbers, kernel_variants)
        test_silo(bench_base, silo_base, vm_numbers, kernel_variants)
        test_xsbench(bench_base, xsbench_base, vm_numbers, kernel_variants)


# figure 6-7
def test_ablation_balloon(bench_base, gups_base, max_vm_number, kernel_variants):
    with collect_datapoints(function_name()):
        for kernel, balloon in product(kernel_variants, [*Balloon, None]):
            gups_base(bench_base(num=max_vm_number, kernel=kernel, balloon=balloon))


# figure 9a
def test_ablation_sensitivity_acess_tracking(bench_base, gups_base, avg_vm_number):
    with collect_datapoints(function_name()):
        for period, thresh in product(
            [127, 257, 509, 1021, 2039, 4093, 8191, 16381, 32771, 65537],
            range(48, 128 + 1, 8),
        ):
            gups_base(
                bench_base(
                    num=avg_vm_number,
                    balloon=None,
                    env=dict(
                        load_latency_sample_period=period,
                        load_latency_threshold=thresh,
                    ),
                ),
            )


# figure 9b
def test_ablation_sensitivity_hotness_classification(
    bench_base, gups_base, avg_vm_number
):
    with collect_datapoints(function_name()):
        for period, thresh in product(
            erange(128, 65536 + 1, 2),
            range(5, 35 + 1, 3),
        ):
            gups_base(
                bench_base(
                    num=avg_vm_number,
                    balloon=None,
                    env=dict(
                        split_period_ms=period,
                        rtree_split_thresh=thresh,
                    ),
                ),
            )


# table 1
def test_delegated_gups(bench_large, gups_large, kernel_variants):
    assert "6.10.0-demeterhost" == os.uname().release
    with collect_datapoints(function_name()):
        for kernel in kernel_variants:
            gups_large(bench_large(kernel=kernel))

# table 1
def test_hypervisor_gups(bench_hlarge, gups_large):
    assert "5.15.162-tpphost" == os.uname().release
    with collect_datapoints(function_name()):
        gups_large(bench_hlarge())

# figure 13?
def test_gups_perf_vs_pml(gups_base, gups_base_pebs, bench_base_dram_only, bench_base_dram_only_pml):
    assert "6.10.0-demeterhost" == os.uname().release
    with collect_datapoints(function_name()):
        gups_base_pebs(bench_base_dram_only())
        gups_base(bench_base_dram_only_pml())

