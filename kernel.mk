include environment.mk
KERNEL_TARGETS := olddefconfig bzImage modules compile_commands.json scripts_gdb
DEMETER_KERNELS := demeter demeterhost
SOTA_KERNELS := memtis nomad tpp tpphost
GUEST_KERNELS := demeter memtis nomad tpp
HOST_KERNELS := demeterhost tpphost
JOBS ?= $(shell nproc)

.PHONY: all clean demeter sota \
	build $(addprefix build-,$(DEMETER_KERNELS) $(SOTA_KERNELS)) \
	install-guest $(addprefix install-,$(GUEST_KERNELS))
all: demeter sota

# Alternative mirrors:
# https://github.com/torvalds/linux/archive/refs/tags/v6.10.tar.gz
# https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.10.tar.gz
# https://cdn.kernel.org/pub/linux/kernel/v5.x/linux-5.15.162.tar.gz
DEMETER_BASE_TARBALL = demeter-base.tar.gz
$(DEMETER_BASE_TARBALL):
	curl -LC- -o $@ \
		https://github.com/gregkh/linux/archive/refs/tags/v6.10.tar.gz

DEMETER_SOURCE_DIR := kernel/demeter
demeter: $(DEMETER_SOURCE_DIR)/.stamp
$(DEMETER_SOURCE_DIR)/.stamp: patch/demeter.patch $(DEMETER_BASE_TARBALL) $(DEMETER_SOURCE_DIR)
	tar -axf $(DEMETER_BASE_TARBALL) --strip-components=1 -C $(DEMETER_SOURCE_DIR)
	@echo "Applying Demeter patch..."
	patch -d $(DEMETER_SOURCE_DIR) -p1 < $<
	touch $@

SOTA_BASE_TARBALL = sota-base.tar.gz
$(SOTA_BASE_TARBALL):
	curl -LC- -o $@ \
		https://github.com/gregkh/linux/archive/refs/tags/v5.15.162.tar.gz

SOTA_SOURCE_DIR := kernel/sota
sota: $(SOTA_SOURCE_DIR)/.stamp
$(SOTA_SOURCE_DIR)/.stamp: patch/sota.patch $(SOTA_BASE_TARBALL) $(SOTA_SOURCE_DIR)
	tar -axf $(SOTA_BASE_TARBALL) --strip-components=1 -C $(SOTA_SOURCE_DIR)
	@echo "Applying SOTA patch..."
	patch -d $(SOTA_SOURCE_DIR) -p1 < $<
	touch $@

$(DEMETER_SOURCE_DIR) $(SOTA_SOURCE_DIR):
	mkdir -p $@

# $(call make-kernel,<config>,<srctree>,<objtree>[,<targets>])
make-kernel = $(shell set -ex; \
						mkdir -p $(3); \
						[ -f $(3)/.config ] || cp $(1) $(3)/.config; \
						echo make -j $(JOBS) -C $(2) O=$(3) $(4);)
build: $(addprefix build-,$(DEMETER_KERNELS) $(SOTA_KERNELS))
$(addprefix build-,$(DEMETER_KERNELS)): build-%: config/%.config demeter
	ccache --zero-stats
	$(call make-kernel,$<,$(@:build-%=$(CURDIR)/kernel/%),$(@:build-%=$(CURDIR)/build/%),$(KERNEL_TARGETS))
	ccache --show-stats

$(addprefix build-,$(SOTA_KERNELS)): build-%: config/%.config sota
	ccache --zero-stats
	$(call make-kernel,$<,$(@:build-%=$(CURDIR)/kernel/%),$(@:build-%=$(CURDIR)/build/%),$(KERNEL_TARGETS))
	ccache --show-stats

install-guest: $(addprefix install-,$(GUEST_KERNELS))
$(addprefix install-guest-,$(GUEST_KERNELS)): install-guest-%: build-%
	mkdir -p $(<:build-%=bin/%)
	cp -vt $(<:build-%=bin/%) \
		$(<:build-%=build/%)/**/compressed/vmlinux.bin \
		$(<:build-%=build/%)/**/*.ko \
		$(<:build-%=build/%)/**/vmlinux

clean:
	rm -rf build $(DEMETER_BASE_TARBALL) $(DEMETER_SOURCE_DIR) $(SOTA_BASE_TARBALL) $(SOTA_SOURCE_DIR)
