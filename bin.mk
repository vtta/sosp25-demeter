SHELL := /bin/bash -O globstar

.PHONY: all clean
GUEST_KERNELS := demeter memtis nomad tpp
SCRIPTS := ansi2txt dram-pfn.py launcher.py $(addsuffix .py,$(GUEST_KERNELS))
MAX_VMS := 16
ROOT_IMGS := $(foreach i,$(shell seq 0 $(MAX_VMS)),bin/root$(i).img)

all: $(addprefix bin/,$(GUEST_KERNELS)) \
	bin/root.img $(ROOT_IMGS) \
	bin/cloud-hypervisor bin/virtiofsd \
	bin/damo bin/bind-stdin \
	$(addprefix bin/,$(SCRIPTS))

$(addprefix bin/,$(GUEST_KERNELS)): bin/%: build/%
	mkdir -p $@
	cp -vt $@ \
		$</**/compressed/vmlinux.bin \
		$</**/*.ko \
		$</vmlinux \
		$</System.map

ROOT_IMG_PARTS := root.img.zst.part0 root.img.zst.part1 root.img.zst.part2
$(ROOT_IMG_PARTS):
	aria2c -c -k1M -x16 \
		https://github.com/vtta/sosp25-demeter/releases/download/root.img/$@

bin/root.img: $(ROOT_IMG_PARTS)
	mkdir -p $(dir $@)
	cat $? | zstd -d -o $@

$(ROOT_IMGS): bin/root.img
	qemu-img create -f qcow2 -b $(notdir $<) -F qcow2 -o compression_type=zstd $@

bin/cloud-hypervisor: hypervisor/target/x86_64-unknown-linux-musl/release/cloud-hypervisor
	mkdir -p $(dir $@)
	cp -v $< $@

VIRTIOFSD_TARBALL := virtiofsd.zip
$(VIRTIOFSD_TARBALL):
	curl -LC- -o $@ \
		https://gitlab.com/-/project/21523468/uploads/b4a5fbe388739bbd833f822ef9d83e82/virtiofsd-v1.4.0.zip
bin/virtiofsd: $(VIRTIOFSD_TARBALL)
	mkdir -p $(dir $@)
	unzip -j $< -d $(dir $@)

bin/bind-stdin: script/bind-stdin.c
	$(CC) $(CFLAGS) -o $@ $<

$(addprefix bin/,$(SCRIPTS)): bin/%: script/%
	mkdir -p $(dir $@)
	cp -v $< $@

DAMO_TARBALL := damo.tgz
$(DAMO_TARBALL):
	curl -LC- -o $@ \
		https://github.com/damonitor/damo/archive/refs/tags/v2.7.3.tar.gz
bin/damo: $(DAMO_TARBALL)
	mkdir -p $@
	tar -axf $< --strip-components=1 -C $@

clean:
	rm -rf $(DAMO_TARBALL) $(ROOT_IMG_PARTS) $(VIRTIOFSD_TARBALL) bin
