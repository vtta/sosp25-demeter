#!/usr/bin/env python3

import drgn
from drgn.helpers.linux import for_each_node_state


def eprint(*args, **kwargs):
    import sys
    print(*args, file=sys.stderr, **kwargs)


prog = drgn.program_from_kernel()
try:
    prog.load_debug_info(["/tmp/vmlinux"])
except drgn.MissingDebugInfoError as e:
    eprint("Failed to load debug info: %s" % e)
dram_nid = next(for_each_node_state(prog.constant("N_MEMORY")))
dram_node = prog["node_data"][dram_nid]
start_pfn = dram_node.node_start_pfn
end_pfn = start_pfn + dram_node.node_spanned_pages

print(start_pfn.value_(), end_pfn.value_())
