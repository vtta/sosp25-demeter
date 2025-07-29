TOOLCHAIN_DIR ?= $(CURDIR)/toolchain
export RUSTUP_HOME := $(TOOLCHAIN_DIR)/rustup
export CARGO_HOME := $(TOOLCHAIN_DIR)/cargo
export RUSTFLAGS := -C linker=clang -C link-arg=-fuse-ld=mold
export RUSTC_WRAPPER := sccache

export LLVM := y
export CC := ccache clang
export CFLAGS :=
export CXX := ccache clang++
export HOSTCXX := ccache clang++
export CXXFLAGS :=
export PAHOLE := pahole --skip_encoding_btf_enum64
export KBUILD_BUILD_TIMESTAMP :=

export PATH := $(CARGO_HOME)/bin:$(TOOLCHAIN_DIR)/bin:$(PATH)
export LD_LIBRARY_PATH := $(TOOLCHAIN_DIR)/lib:$(TOOLCHAIN_DIR)/lib/x86_64-unknown-linux-gnu
