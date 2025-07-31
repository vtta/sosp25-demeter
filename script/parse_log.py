#!/usr/bin/env python3
import json
import logging
import re
from dataclasses import InitVar, asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List

import fire
import jq
import pandas as pd

LOGGER = logging.getLogger(__name__)
FORMAT = "%(asctime)s %(levelname)-8s %(name)-15s %(message)s"
FLOAT = r"[+-]?(\d*\.\d+|\d+\.)([eE][+-]?\d+)?"
KERNEL = r"\d+\.\d+\.\d+(-\w+)?\+?"
TRANSFORM = jq.compile("""
.vms
| map(
    .metrics
    | map({ (.key): (.value) })
    | add
  )
""")


@dataclass
class Metric:
    key: str
    value: Any


@dataclass
class RegexMetric(Metric):
    """The value field from the parent is used as the default if no match is found."""

    file: InitVar[Path]
    regex: InitVar[str]

    def __post_init__(self, file, regex):
        if not file.exists():
            # LOGGER.warning(f"{file} does not exist")
            return
        pattern = re.compile(regex)
        try:
            if m := pattern.search(file.read_text()):
                self.value = m.group(self.key)
        except OSError as e:
            LOGGER.error(e)


@dataclass
class FnRegexMetric(RegexMetric):
    """The value field from the parent is used as the default if no match is found."""

    fn: InitVar[Callable[[Dict], Any]]

    def __post_init__(self, file, regex, fn):
        if not file.exists():
            # LOGGER.warning(f"{file} does not exist")
            return
        pattern = re.compile(regex)
        try:
            if m := pattern.search(file.read_text()):
                self.value = fn(m.groupdict())
        except OSError as e:
            LOGGER.error(e)


@dataclass
class ElapsedMetric(FnRegexMetric):
    regex: InitVar[str] = (
        r"Elapsed \(wall clock\) time \(h:mm:ss or m:ss\): ((?P<hh>\d+):)?(?P<mm>\d+):(?P<ss>\d+\.?\d*)"
    )
    fn: InitVar[Callable[[Dict], Any]] = lambda d: sum(
        map(lambda k, r: float(d.get(k) or 0) * r, ["hh", "mm", "ss"], [3600, 60, 1])
    )


@dataclass
class VmMetrics:
    runid: Path
    vmid: Path
    vmnum: int
    metrics: List[Metric] = field(init=False)

    def __post_init__(self):
        self.metrics = [
            Metric(key="runid", value=self.runid.name),
            Metric(key="vmid", value=self.vmid.name),
            Metric(key="vmnum", value=str(self.vmnum)),
            RegexMetric(
                key="kernel",
                value=None,
                file=self.vmid / "cloud-hypervisor.stdout",
                regex=rf"Linux version (?P<kernel>{KERNEL})",
            ),
            FnRegexMetric(
                key="design",
                value=None,
                file=self.vmid / "cloud-hypervisor.stdout",
                regex=rf"Linux version (?P<kernel>\d+\.\d+\.\d+(-(?P<design>\w+))?\+?)",
                fn=lambda d: dict(
                    tpp="TPP",
                    nomad="Nomad",
                    memtis="Memtis",
                    demeter="Demeter",
                ).get(d["design"], d["design"]),
            ),
            FnRegexMetric(
                key="balloon",
                value="Static",
                file=self.vmid / "dmesg",
                regex=r"initcall init_module\+0x0/0x1000 \[(?P<balloon>\w+)_balloon\]",
                fn=lambda d: dict(
                    demeter="Demeter Balloon",
                    virtio="VirtIO Balloon",
                ).get(d["balloon"], d["balloon"]),
            ),
            RegexMetric(
                key="pgmigrate_success",
                value=None,
                file=self.vmid / "vmstat",
                regex=r"pgmigrate_success (?P<pgmigrate_success>\d+)",
            ),
            RegexMetric(
                key="folio_exchange_success",
                value=None,
                file=self.vmid / "vmstat",
                regex=r"folio_exchange_success (?P<folio_exchange_success>\d+)",
            ),
            RegexMetric(
                key="folio_exchange_failed",
                value=None,
                file=self.vmid / "vmstat",
                regex=r"folio_exchange_failed (?P<folio_exchange_failed>\d+)",
            ),
            RegexMetric(
                key="pebs_nr_sampled",
                value=None,
                file=self.vmid / "vmstat",
                regex=r"pebs_nr_sampled (?P<pebs_nr_sampled>\d+)",
            ),
            RegexMetric(
                key="pebs_nr_sampled_fmem",
                value=None,
                file=self.vmid / "vmstat",
                regex=r"pebs_nr_sampled_fmem (?P<pebs_nr_sampled_fmem>\d+)",
            ),
            RegexMetric(
                key="pebs_nr_sampled_smem",
                value=None,
                file=self.vmid / "vmstat",
                regex=r"pebs_nr_sampled_smem (?P<pebs_nr_sampled_smem>\d+)",
            ),
            RegexMetric(
                key="gups_throughput",
                value=None,
                file=self.vmid / "gups.log",
                regex=rf"iteration (?P<label>last) final (?P<gups_throughput>{FLOAT}) elapsed (?P<gups_elapsed>{FLOAT})s",
            ),
            RegexMetric(
                key="gups_elapsed",
                value=None,
                file=self.vmid / "gups.log",
                regex=rf"iteration (?P<label>last) final (?P<gups_throughput>{FLOAT}) elapsed (?P<gups_elapsed>{FLOAT})s",
            ),
            RegexMetric(
                key="exit_status",
                value=None,
                file=self.vmid / "gups.err",
                regex=r"Exit status: (?P<exit_status>\d+)",
            ),
            RegexMetric(
                key="percent_of_cpu",
                value=None,
                file=self.vmid / "gups.err",
                regex=r"Percent of CPU this job got: (?P<percent_of_cpu>\d+)%",
            ),
            RegexMetric(
                key="user_time",
                value=None,
                file=self.vmid / "gups.err",
                regex=rf"User time \(seconds\): (?P<user_time>{FLOAT})",
            ),
            RegexMetric(
                key="system_time",
                value=None,
                file=self.vmid / "gups.err",
                regex=rf"System time \(seconds\): (?P<system_time>{FLOAT})",
            ),
            ElapsedMetric(key="gups", value=None, file=self.vmid / "gups.err"),
            ElapsedMetric(key="xsbench", value=None, file=self.vmid / "xsbench.err"),
            ElapsedMetric(key="graph500", value=None, file=self.vmid / "graph500.err"),
            ElapsedMetric(key="pagerank", value=None, file=self.vmid / "pagerank.err"),
            ElapsedMetric(
                key="liblinear", value=None, file=self.vmid / "liblinear.err"
            ),
            ElapsedMetric(key="bwaves", value=None, file=self.vmid / "bwaves.err"),
            ElapsedMetric(key="btree", value=None, file=self.vmid / "btree.err"),
            ElapsedMetric(key="silo", value=None, file=self.vmid / "silo.err"),
            RegexMetric(
                key="memtis_cpu_usage",
                value=None,
                file=self.vmid / "cloud-hypervisor.stdout",
                regex=r"total runtime: (?P<memtis_runtime>\d+) ns, total cputime: (?P<memtis_cputime>\d+) us, cpu usage: (?P<memtis_cpu_usage>\d+)",
            ),
            RegexMetric(
                key="dram_ratio_first_gib",
                value=None,
                file=self.vmid / "gups.log",
                regex=rf"iteration (?P<label>last) dram portion per gb: \[(?P<dram_ratio_first_gib>{FLOAT})(, {FLOAT})*, (?P<dram_ratio_last_gib>{FLOAT})\]",
            ),
            RegexMetric(
                key="dram_ratio_last_gib",
                value=None,
                file=self.vmid / "gups.log",
                regex=rf"iteration (?P<label>last) dram portion per gb: \[(?P<dram_ratio_first_gib>{FLOAT})(, {FLOAT})*, (?P<dram_ratio_last_gib>{FLOAT})\]",
            ),
            RegexMetric(
                key="local_dram_miss_sample_period",
                value=None,
                file=self.vmid / "cloud-hypervisor.stdout",
                regex=r"created config=0x1d3 sample_period=(?P<local_dram_miss_sample_period>\d+)",
            ),
            RegexMetric(
                key="load_latency_sample_period",
                value=None,
                file=self.vmid / "cloud-hypervisor.stdout",
                # created config=0x1cd config1=0x30 sample_period=127
                regex=r"created config=0x1cd config1=(?P<load_latency_threshold>0x[\da-f]+) sample_period=(?P<load_latency_sample_period>\d+)",
            ),
            FnRegexMetric(
                key="load_latency_threshold",
                value=None,
                file=self.vmid / "cloud-hypervisor.stdout",
                regex=r"created config=0x1cd config1=(?P<load_latency_threshold>0x[\da-f]+) sample_period=(?P<load_latency_sample_period>\d+)",
                fn=lambda d: int(d["load_latency_threshold"], 0),
            ),
            RegexMetric(
                key="retired_stores_sample_period",
                value=None,
                file=self.vmid / "cloud-hypervisor.stdout",
                regex=r"created config=0x82d0 sample_period=(?P<retired_stores_sample_period>\d+)",
            ),
            RegexMetric(
                key="util_overflow_handler",
                value=None,
                file=self.vmid / "cloud-hypervisor.stdout",
                regex=r"overflow_handler=(?P<overflow_handler_ns>\d+) permyriad=(?P<util_overflow_handler>\d+)",
            ),
            RegexMetric(
                key="overflow_handler_ns",
                value=None,
                file=self.vmid / "cloud-hypervisor.stdout",
                regex=r"overflow_handler=(?P<overflow_handler_ns>\d+) permyriad=(?P<util_overflow_handler>\d+)",
            ),
            RegexMetric(
                key="util_policy",
                value=None,
                file=self.vmid / "cloud-hypervisor.stdout",
                regex=r"policy=(?P<policy_ns>\d+) permyriad=(?P<util_policy>\d+)",
            ),
            RegexMetric(
                key="policy_ns",
                value=None,
                file=self.vmid / "cloud-hypervisor.stdout",
                regex=r"policy=(?P<policy_ns>\d+) permyriad=(?P<util_policy>\d+)",
            ),
            RegexMetric(
                key="util_migration",
                value=None,
                file=self.vmid / "cloud-hypervisor.stdout",
                regex=r"migration=(?P<migration_ns>\d+) permyriad=(?P<util_migration>\d+)",
            ),
            RegexMetric(
                key="migration_ns",
                value=None,
                file=self.vmid / "cloud-hypervisor.stdout",
                regex=r"migration=(?P<migration_ns>\d+) permyriad=(?P<util_migration>\d+)",
            ),
            RegexMetric(
                key="util_perf_prepare",
                value=None,
                file=self.vmid / "cloud-hypervisor.stdout",
                regex=r"perf_prepare=(?P<perf_prepare_ns>\d+) permyriad=(?P<util_perf_prepare>\d+)",
            ),
            RegexMetric(
                key="perf_prepare_ns",
                value=None,
                file=self.vmid / "cloud-hypervisor.stdout",
                regex=r"perf_prepare=(?P<perf_prepare_ns>\d+) permyriad=(?P<util_perf_prepare>\d+)",
            ),
            RegexMetric(
                key="util_split",
                value=None,
                file=self.vmid / "cloud-hypervisor.stdout",
                regex=r"split=(?P<split_ns>\d+) permyriad=(?P<util_split>\d+)",
            ),
            RegexMetric(
                key="split_ns",
                value=None,
                file=self.vmid / "cloud-hypervisor.stdout",
                regex=r"split=(?P<split_ns>\d+) permyriad=(?P<util_split>\d+)",
            ),
            RegexMetric(
                key="ptea_scan_ns",
                value=None,
                file=self.vmid / "vmstat",
                regex=r"ptea_scan_ns (?P<ptea_scan_ns>\d+)",
            ),
            RegexMetric(
                key="ptea_scanned",
                value=None,
                file=self.vmid / "vmstat",
                regex=r"ptea_scanned (?P<ptea_scanned>\d+)",
            ),
            RegexMetric(
                key="lru_rotate_ns",
                value=None,
                file=self.vmid / "vmstat",
                regex=r"lru_rotate_ns (?P<lru_rotate_ns>\d+)",
            ),
            RegexMetric(
                key="demote_ns",
                value=None,
                file=self.vmid / "vmstat",
                regex=r"demote_ns (?P<demote_ns>\d+)",
            ),
            RegexMetric(
                key="hint_fault_ns",
                value=None,
                file=self.vmid / "vmstat",
                regex=r"hint_fault_ns (?P<hint_fault_ns>\d+)",
            ),
            RegexMetric(
                key="promote_ns",
                value=None,
                file=self.vmid / "vmstat",
                regex=r"promote_ns (?P<promote_ns>\d+)",
            ),
            RegexMetric(
                key="sampling_ns",
                value=None,
                file=self.vmid / "vmstat",
                regex=r"sampling_ns (?P<sampling_ns>\d+)",
            ),
            RegexMetric(
                key="ptext_ns",
                value=None,
                file=self.vmid / "vmstat",
                regex=r"ptext_ns (?P<ptext_ns>\d+)",
            ),
            RegexMetric(
                key="split_period_ms",
                value=None,
                file=self.vmid / "gups.err",
                regex=r"split_period_ms=(?P<split_period_ms>\d+)",
            ),
            RegexMetric(
                key="rtree_split_thresh",
                value=None,
                file=self.vmid / "gups.err",
                regex=r"rtree_split_thresh=(?P<rtree_split_thresh>\d+)",
            ),
            RegexMetric(
                key="nr_tlb_remote_flush",
                value=None,
                file=self.vmid / "vmstat",
                regex=r"nr_tlb_remote_flush (?P<nr_tlb_remote_flush>\d+)",
            ),
            RegexMetric(
                key="nr_tlb_local_flush_all",
                value=None,
                file=self.vmid / "vmstat",
                regex=r"nr_tlb_local_flush_all (?P<nr_tlb_local_flush_all>\d+)",
            ),
            RegexMetric(
                key="nr_tlb_local_flush_one",
                value=None,
                file=self.vmid / "vmstat",
                regex=r"nr_tlb_local_flush_one (?P<nr_tlb_local_flush_one>\d+)",
            ),
            RegexMetric(
                key="tlb_flush",
                value=None,
                file=self.vmid / "kvm" / "tlb_flush",
                regex=r"(?P<tlb_flush>\d+)",
            ),
            RegexMetric(
                key="remote_tlb_flush",
                value=None,
                file=self.vmid / "kvm" / "remote_tlb_flush",
                regex=r"(?P<remote_tlb_flush>\d+)",
            ),
            RegexMetric(
                key="silo_p50_latency",
                value=None,
                file=self.vmid / "silo.err",
                regex=r"p50_latency: (?P<silo_p50_latency>\d+.?\d*) ns",
            ),
            RegexMetric(
                key="silo_p90_latency",
                value=None,
                file=self.vmid / "silo.err",
                regex=r"p90_latency: (?P<silo_p90_latency>\d+.?\d*) ns",
            ),
            RegexMetric(
                key="silo_p95_latency",
                value=None,
                file=self.vmid / "silo.err",
                regex=r"p95_latency: (?P<silo_p95_latency>\d+.?\d*) ns",
            ),
            RegexMetric(
                key="silo_p99_latency",
                value=None,
                file=self.vmid / "silo.err",
                regex=r"p99_latency: (?P<silo_p99_latency>\d+.?\d*) ns",
            ),
        ]


@dataclass
class RunMetrics:
    runid: Path
    vms: List[VmMetrics] = field(init=False)
    metrics: List[Metric] = field(init=False)

    def __post_init__(self):
        vmnum = sum(
            1
            for _ in filter(
                lambda p: p.is_dir() and p.name.isdigit(), self.runid.iterdir()
            )
        )
        self.vms = []
        for vmfolder in self.runid.iterdir():
            if vmfolder.is_dir() and vmfolder.name.isdigit():
                self.vms.append(VmMetrics(runid=self.runid, vmid=vmfolder, vmnum=vmnum))
        self.metrics = []


class PathEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Path):
            return str(o)
        return super().default(o)


def parse_log(start=0, stop=None, dir=Path("bench/archive")):
    """
    Example: say one run include a total of 4 invocations of different kernels.
    Then report(-4) means last run, and report(-8, -4) means the second last run.
    """
    # find the newest num folders under archive/
    newest = sorted(filter(Path.is_dir, Path(dir).iterdir()), key=lambda x: x.name)[
        start:stop
    ]
    data = []
    for folder in newest:
        metrics = asdict(RunMetrics(folder))
        metrics = TRANSFORM.input(
            json.loads(json.dumps(metrics, cls=PathEncoder))
        ).first()
        data.extend(metrics)
    # print(json.dumps(data))
    return pd.json_normalize(data)


def main(**kwargs):
    data = parse_log(**kwargs)
    print(data.to_csv())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format=FORMAT)
    fire.Fire(main)
