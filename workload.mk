include environment.mk
# BUG: openmp in the llvm toolchain is not working, revert to gcc when required
export CC := gcc
export CXX := g++

.PHONY: all clean default

default: all

GUPS_BIN := workload/gups/target/x86_64-unknown-linux-musl/release/gups
$(GUPS_BIN): workload/gups/Cargo.toml
	cd workload/gups; cargo build --release --target=x86_64-unknown-linux-musl

BTREE_BIN := workload/btree/bench_btree_mt
$(BTREE_BIN): workload/btree/Makefile
	make -C workload/btree

BWAVES_BIN := workload/bwaves/bwaves_s workload/bwaves/bwaves_s.in

GRAPH500_BIN := workload/graph500/omp-csr/omp-csr
$(GRAPH500_BIN): workload/graph500/Makefile
	make -C workload/graph500 omp-csr/omp-csr

LIBLINEAR_BIN := workload/liblinear/train workload/liblinear/kdda
$(LIBLINEAR_BIN): workload/liblinear/Makefile
	make -C workload/liblinear

PAGERANK_BIN := workload/gapbs/pr workload/gapbs/benchmark/graphs/twitter.sg
$(PAGERANK_BIN): workload/gapbs/Makefile
	make -C workload/gapbs

SILO_BIN := workload/silo/out-perf.masstree/benchmarks/dbtest
$(SILO_BIN): workload/silo/Makefile
	make -C workload/silo dbtest

XSBENCH_BIN := workload/xsbench/XSBench
$(XSBENCH_BIN): workload/xsbench/Makefile
	make -C workload/xsbench

all: $(GUPS_BIN) $(BTREE_BIN) $(BWAVES_BIN) $(GRAPH500_BIN) \
	$(LIBLINEAR_BIN) $(PAGERANK_BIN) $(SILO_BIN) $(XSBENCH_BIN)

clean:
	cd workload/gups; cargo clean
	make -C workload/btree clean
	make -C workload/graph500 clean
	make -C workload/liblinear clean
	make -C workload/gapbs clean
	make -C workload/silo clean
	make -C workload/xsbench clean
