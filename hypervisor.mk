.PHONY: all ch clean build

all: ch

CH_BASE_TARBALL = cloud-hypervisor-base.tar.gz
$(CH_BASE_TARBALL):
	curl -LC- -o $@ \
		https://github.com/cloud-hypervisor/cloud-hypervisor/archive/refs/tags/v36.0.tar.gz

CH_SOURCE_DIR := hypervisor
$(CH_SOURCE_DIR):
	mkdir -p $@

ch: $(CH_SOURCE_DIR)/.stamp
$(CH_SOURCE_DIR)/.stamp: patch/hypervisor.patch $(CH_BASE_TARBALL) $(CH_SOURCE_DIR)
	tar -axf $(CH_BASE_TARBALL) --strip-components=1 -C $(CH_SOURCE_DIR)
	@echo "Applying hypervisor patch..."
	patch -d $(CH_SOURCE_DIR) -p1 < $<
	touch $@

build: ch
	cd $(CH_SOURCE_DIR); cargo build --release --target x86_64-unknown-linux-musl

clean:
	rm -rf $(CH_SOURCE_DIR) $(CH_BASE_TARBALL)
