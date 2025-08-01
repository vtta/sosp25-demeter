# [SOSP25] Demeter: A Scalable and Elastic Tiered Memory Solution for Virtualized Cloud via Guest Delegation

## Artifact Evaluation Instructions

### Overview

Demeter is a tiered memory management solution designed for virtualized environments that builds on modified versions of the Linux kernel and Cloud Hypervisor. This artifact allows evaluators to reproduce the key performance claims from our SOSP'25 paper.

**Key Claims to Validate:**

1. Demeter improves performance by up to 2× compared to existing hypervisor-based (TPP-H) approaches
2. Demeter achieves 28% average improvement (geometric mean) compared to the next best guest-based alternative (TPP)

**Evaluation Time:** ~31 hours total excluding environment preparation (26 hours for guest-delegated + 5 hours for hypervisor-based experiments)

### System Requirements

**Hardware Requirements:**

- Dual socket Intel Ice Lake server with:
  - At least 36 physical cores per CPU package
  - At least 128GiB DDR5 DRAM paired with 512GiB Intel Optane PMEM 200 series per socket
  - At least 1TiB available space on NVMe SSD

**Software Requirements:**

- Latest Clear Linux OS (version ≥43760) with development bundles:

  ```bash
  sudo swupd bundle-add os-clr-on-clr dev-utils
  ```

- Python 3.13 environment (setup instructions provided below)

**Important Notes:**

- This evaluation **requires specific hardware** (Intel Ice Lake + Optane PMEM) and cannot be run on other configurations
- We strongly recommend using `tmux` to prevent interruption during long-running experiments
- The artifact requires ~31 hours of continuous execution time

### Setup Instructions

#### Step 1: Python Environment Setup (~2 minutes)

```bash
python3 -m venv py313
source py313/bin/activate
pip install fire drgn jq pandas altair[all] poetry pydantic

# Fix Python 3.13 compatibility issue
sed -i 's/pipes/shlex/g' py313/lib/python3.13/site-packages/fire/trace.py
sed -i 's/pipes/shlex/g' py313/lib/python3.13/site-packages/fire/core.py
```

#### Step 2: Toolchain Installation (~10 minutes)

```bash
make -f toolchain.mk
```

This installs reproducible compilation infrastructure (LLVM/Clang and Rust toolchains).

#### Step 3: Kernel Compilation (~15 minutes)

```bash
make -f kernel.mk build
```

Builds all required kernels (Demeter and baseline implementations). Uses `ccache` for faster subsequent builds.

**Expected Output:**

- Source trees in `kernel/` directory
- Built kernels in `build/` directory
- Key kernels: `demeter`, `sota` (containing TPP, Nomad, Memtis variants (softlink))

#### Step 4: Hypervisor Compilation (~5 minutes)

```bash
make -f hypervisor.mk build
```

Builds the modified Cloud Hypervisor with Demeter patches.

#### Step 5: Workload Compilation (~20 minutes)

```bash
make -f workload.mk
```

Compiles all seven evaluation workloads and downloads required datasets.

#### Step 6: Binary Asset Collection (~5 minutes)

```bash
make -f bin.mk
make -f workload.mk install
```

Collects all required binaries for the benchmark framework.

#### Step 7: Host Kernel Installation (~20 minutes + reboot)

```bash
make -f kernel.mk install-host
```

**Verify Installation:**

```bash
sudo bootctl list
```

Confirm you see entries for both:

- `linux-6.10.0-demeterhost.conf` (for guest-delegated experiments)
- `linux-5.15.162-tpphost.conf` (for hypervisor-based experiments)

**Switch Kernels as Needed:**

```bash
# For guest-delegated experiments (Demeter, TPP, Nomad, Memtis)
sudo bootctl set-oneshot linux-6.10.0-demeterhost.conf
sudo reboot

# For hypervisor-based experiments (TPP-H)
sudo bootctl set-oneshot linux-5.15.162-tpphost.conf
sudo reboot
```

### Environment Setup

```bash
# Kill zombie processes
echo "cloud-hyperviso virtiofsd pcm-memory gdb" | xargs -n1 sudo pkill -9

# System configuration
ulimit -n 65535                                    # Increase file limits
sudo swapoff --all                                 # Disable swap
sudo sysctl -w vm.overcommit_memory=1              # Enable memory overcommit
echo 3 | sudo tee /proc/sys/vm/drop_caches >/dev/null  # Clear page cache

# Lock CPU frequency
echo 3000000 | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_{min,max}_freq >/dev/null

# Configure PMEM as NUMA nodes
sudo daxctl reconfigure-device --human --mode=system-ram all || true

# Setup VM networking
sudo script/network.bash --restart
```
### Quick Functionality Test (~2 minutes)

Before running full experiments, verify the setup works:

```bash
# Activate Python environment
source py313/bin/activate
export PATH="$(realpath bin):$PATH"

# Make sure the PMEM is configured as NUMA node
sudo numactl --hardware
# Make sure there is network bridge named virbr921
sudo ip a

# Test with 3 VMs
poetry -C bench install
poetry -C bench run python3 -m bench \
	--num 3 --kernel demeter --mem 17179869184 \
  --dram-ratio 0.2 --dram_node 0 --pmem_node 2 \
  run 'echo "Hello, Demeter!" | sudo tee /out/hello.log'
```

**Expected:** Logs appear in a timestamp taged folder under `bench/archive/`, containing "Hello, Demeter!" message in `hello.log`.

## Main Evaluation

### Part 1: Guest-Delegated Designs (~26 hours)

**Prerequisites:**

- Current kernel: `6.10.0-demeterhost` (verify with `uname -r`)
- System configured with environment setup script

```bash
# Ensure correct kernel
if [[ $(uname -r) != "6.10.0-demeterhost" ]]; then
    echo "Wrong kernel! Switch to demeterhost kernel and reboot."
    exit 1
fi

# Run environment setup again

# Start evaluation
poetry -C bench run pytest tests/evaluation.py -k test_delegated_realworld_workloads
```

**What This Tests:**

- Demeter vs. TPP, Nomad, and Memtis on all 7 workloads
- ~26 hours total runtime
- Progress visible in terminal output

### Part 2: Hypervisor-Based Design (~5 hours)

**Prerequisites:**

- Current kernel: `5.15.162-tpphost` (verify with `uname -r`)

```bash
# Switch kernel if needed
if [[ $(uname -r) != "5.15.162-tpphost" ]]; then
    sudo bootctl set-oneshot linux-5.15.162-tpphost.conf
    sudo reboot
fi

# Run environment setup again

# Start evaluation
poetry -C bench run pytest tests/evaluation.py -k test_hypervisor_realworld_workloads
```

**What This Tests:**

- TPP-H (hypervisor-based) baseline on all 7 workloads
- ~5 hours total runtime

### Results Analysis

After both experiment phases complete:

```bash
# Find your log directories
ls -la bench/archive/

# Run analysis (replace paths with your actual log directories)
python3 script/plot.py \
  --guest_log_dir bench/archive/YYYY-MM-DDTHH:MM:SS-test_delegated_realworld_workloads/ \
  --host_log_dir bench/archive/YYYY-MM-DDTHH:MM:SS-test_hypervisor_realworld_workloads/
```

**Expected Output:**

- `chart.svg` file with performance comparison
- Results should show:
  - Up to 2× improvement over TPP-H (hypervisor-based)
  - (Calculate geometric mean manually for vmnum=9) 28% average improvement over TPP (guest-based)

## Workload Descriptions

The evaluation includes seven real-world applications:

1. **silo**: In-memory OLTP database (transaction processing)
2. **btree**: High-performance B-tree index engine (data structures)
3. **graph500**: Graph processing benchmark (graph analytics)
4. **pagerank**: Twitter social network analysis
5. **liblinear**: Machine learning with KDD CUP 2010 dataset (ML training)
6. **bwaves**: Blast wave scientific simulation (HPC)
7. **xsbench**: Nuclear reactor physics simulation (scientific computing)

## Troubleshooting

### Common Issues

1. **Kernel Boot Issues**: Verify boot entries with `sudo bootctl list` and ensure memory mapping parameters are correct
2. **VM Startup Failures**: Check that networking is properly configured and no zombie processes remain
3. **Out of Memory**: Ensure swap is disabled and memory overcommit is enabled
5. **Missing Dependencies**: Ensure all compilation steps completed successfully and binaries exist

### Debug Commands

```bash
# Check current kernel and boot options
uname -r
cat /proc/cmdline

# Verify memoy configuration
sudo numactl --hardware

# Check VM network
sudo ip addr

# Monitor system resources
htop
```

## Artifact Structure Reference

```
.
├── patch/              # Kernel and hypervisor patches
├── workload/           # Workload source code
├── bench/              # Pytest-based benchmark framework
├── script/             # Data processing and visualization
├── config/             # Kernel configuration files
├── toolchain/          # Toolchains for compilation (after make -f toolchain.mk)
├── kernel/             # Kernel source trees (after make -f kernel.mk)
├── hypervisor/         # Hypervisor source trees (after make -f hypervisor.mk)
├── build/              # Built kernels (after make -f kernel.mk build)
├── bin/                # Binary assets for VMs (after make -f bin.mk)
└── *.mk                # Build infrastructure makefiles
```

