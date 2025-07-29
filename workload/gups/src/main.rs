use std::{
    cell::RefCell,
    marker, mem, ops, process, slice,
    sync::{self, Arc},
    time,
};

use async_std::{prelude::*, stream};
use futures::{channel::mpsc, join, pin_mut, select, FutureExt, StreamExt};
use mix_distribution::Mix;
use rand::distributions::{Distribution, Uniform};
use rayon::prelude::*;
use zipf::ZipfDistribution;

use structopt::StructOpt;

type Result<T> = std::result::Result<T, Box<dyn std::error::Error + Send + Sync>>;

/// GUPS hotset version with `weight` times as more updates going to the hot region than to the rest.
#[derive(StructOpt, Debug, Clone, Copy)]
#[structopt(name = "Gups", about = "Gibi updates per second.")]
struct Args {
    /// Number of worker threads
    #[structopt(short, long)]
    thread: usize,
    /// Number of updates in total
    #[structopt(short, long)]
    update: usize,
    /// Length of the entire memory region
    #[structopt(short, long)]
    len: usize,
    /// Granularity of each update
    #[structopt(short, long)]
    granularity: usize,
    /// Show the gups every given interval in ms
    #[structopt(short, long)]
    report: Option<u64>,
    /// Show the portion of memory pages mapped to the DRAM every given interval in ms
    #[structopt(short, long)]
    dram_ratio: Option<u64>,
    #[structopt(subcommand)]
    workload: Workload,
}

#[derive(StructOpt, Debug, Clone, Copy)]
enum Workload {
    /// Two random access region with fixed access frequency ratio
    Hotset {
        /// Length of the hot memory region
        #[structopt(short, long)]
        hot: usize,
        /// Weight ratio of hot region to the rest
        #[structopt(short, long)]
        weight: usize,
        /// Reverse the allocation of hot set and cold set
        #[structopt(short, long)]
        reverse: bool,
    },
    /// Zipfian distribution
    Zipf {
        /// The parameter of zipf distribution
        #[structopt(short, long)]
        exponent: f64,
        /// Index from the end of the memory region backwords
        #[structopt(short, long)]
        reverse: bool,
    },
    /// Random distribution
    Random {},
}

fn main() -> Result<()> {
    tracing_subscriber::fmt::init();
    let args = Args::from_args();
    tracing::info!("gups args {args:?}");
    if args.dram_ratio.unwrap_or(u64::MAX) != u64::MAX {
        // ensure the DRAM_PFN_RANGE is initialized
        let _ = *DRAM_PFN_RANGE;
    }
    let mem = vec![0xddu8; args.len].into_boxed_slice();
    tracing::info!("memory {:?} length {:?}", mem.as_ptr(), mem.len());
    async_std::task::block_on(main_loop(args, Arc::new(sync::RwLock::new(mem))))?;
    Ok(())
}

async fn main_loop(args: Args, mem: Arc<sync::RwLock<Box<[u8]>>>) -> Result<()> {
    // warm-up
    tracing::info!("warm up iteration start");
    iteration("first", args, mem.clone()).await?;
    // second
    tracing::info!("second iteration start");
    iteration("warm up", args, mem.clone()).await?;
    // final
    tracing::info!("third iteration start");
    iteration("last", args, mem.clone()).await?;

    Ok(())
}

async fn iteration(label: &str, args: Args, mem: Arc<sync::RwLock<Box<[u8]>>>) -> Result<()> {
    let (count_tx, count_rx) = mpsc::unbounded();
    let region = {
        let ptr = mem.read().unwrap().as_ptr();
        mem_region(ptr as _)
    };
    join!(
        async_std::task::spawn_blocking(move || gups_worker(args, mem, count_tx).unwrap()),
        reporting_actor(
            label,
            count_rx,
            time::Duration::from_millis(u64::MAX.min(args.report.unwrap_or(u64::MAX))),
            time::Duration::from_millis(u64::MAX.min(args.dram_ratio.unwrap_or(u64::MAX))),
            region,
        )
    );
    Ok(())
}

pub struct Mod<T, U, X: Copy>
where
    T: Distribution<U>,
    U: ops::Rem<X, Output = U>,
{
    distribution: T,
    len: X,
    _marker: marker::PhantomData<U>,
}
impl<T, U, X: Copy> Mod<T, U, X>
where
    T: Distribution<U>,
    U: ops::Rem<X, Output = U>,
{
    pub fn new(distribution: T, len: X) -> Self {
        Self {
            distribution,
            len,
            _marker: marker::PhantomData,
        }
    }
}
impl<T, U, X: Copy> Distribution<U> for Mod<T, U, X>
where
    T: Distribution<U>,
    U: ops::Rem<X, Output = U>,
{
    fn sample<R: rand::Rng + ?Sized>(&self, rng: &mut R) -> U {
        self.distribution.sample(rng) % self.len
    }
}

pub struct Backwards<T, U, M>
where
    T: Distribution<U>,
    M: ops::Sub<U, Output = U> + Copy,
{
    distribution: T,
    minuend: M,
    _marker: marker::PhantomData<U>,
}
impl<T, U, M> Backwards<T, U, M>
where
    T: Distribution<U>,
    M: ops::Sub<U, Output = U> + Copy,
{
    pub fn new(distribution: T, minuend: M) -> Self {
        Self {
            distribution,
            minuend,
            _marker: marker::PhantomData,
        }
    }
}
impl<T, U, M> Distribution<U> for Backwards<T, U, M>
where
    T: Distribution<U>,
    M: ops::Sub<U, Output = U> + Copy,
{
    fn sample<R: rand::Rng + ?Sized>(&self, rng: &mut R) -> U {
        self.minuend - self.distribution.sample(rng)
    }
}

fn gups_worker(
    args: Args,
    mem: Arc<sync::RwLock<Box<[u8]>>>,
    count: mpsc::UnboundedSender<usize>,
) -> Result<()> {
    let (updates, thread, len, g) = (args.update, args.thread, args.len, args.granularity);
    let end = args.len / args.granularity;
    let mem = &mut **mem.write().unwrap();
    match args.workload {
        Workload::Hotset {
            hot,
            weight,
            reverse: r,
        } => {
            let split = hot / g;
            let v = [Uniform::new(0, split), Uniform::new(split, end)];
            let d = Mod::new(Mix::new(v, [weight, 1]).unwrap(), end);
            if r {
                gups_do(updates, thread, g, mem, Backwards::new(d, end - 1), count)?;
            } else {
                gups_do(updates, thread, g, mem, d, count)?;
            }
        }
        Workload::Zipf {
            exponent,
            reverse: r,
        } => {
            let nelems = len / g;
            let d = ZipfDistribution::new(nelems, exponent).unwrap();
            if r {
                gups_do(
                    updates,
                    thread,
                    g,
                    mem,
                    Backwards::new(d, nelems - 1),
                    count,
                )?;
            } else {
                gups_do(updates, thread, g, mem, d, count)?;
            }
        }
        Workload::Random {} => {
            let d = Uniform::new(0, end);
            gups_do(updates, thread, g, mem, d, count)?;
        }
    }
    Ok(())
}

thread_local! {
    static MEM: RefCell<&'static mut [u8]> = RefCell::default();
}
fn gups_do<D: Distribution<usize> + Sync>(
    updates: usize,
    thread: usize,
    granularity: usize,
    mem: &mut [u8],
    dist: D,
    count_tx: mpsc::UnboundedSender<usize>,
) -> Result<()> {
    let chunk_size = 4096;
    let do_init = || {
        // FIXME: We should be initializing each thread with a disjoint part of the memory
        MEM.with(|m| {
            let ptr = mem.as_ptr() as *mut _;
            let mem = unsafe { slice::from_raw_parts_mut(ptr, mem.len()) };
            m.replace(mem);
        });
    };
    let do_work = || {
        (0..updates)
            .into_par_iter()
            .map_init(rand::thread_rng, |rng, _| dist.sample(rng))
            .chunks(chunk_size)
            .for_each(|indices| {
                MEM.with(|m| {
                    let mem = &mut **m.borrow_mut();
                    indices.iter().for_each(|&index| {
                        update(mem, granularity, index);
                    })
                });
                count_tx.unbounded_send(indices.len()).unwrap();
            });
    };
    rayon::ThreadPoolBuilder::new()
        .num_threads(thread)
        .thread_name(|i| format!("gups-rayon-{}", i))
        .build_scoped(
            |thread| {
                do_init();
                tracing::info!("thread {:?} started", thread.index());
                thread.run();
            },
            |pool| {
                pool.install(do_work);
            },
        )?;
    Ok(())
}

async fn reporting_actor(
    label: &str,
    mut count: mpsc::UnboundedReceiver<usize>,
    gups_dur: time::Duration,
    ratio_dur: time::Duration,
    region: pagemap::MemoryRegion,
) {
    let region = region.clone();
    let chunk_size = 1usize << 30;
    let mut gups_intvl = stream::interval(gups_dur).fuse();
    let ratio_intvl = stream::interval(ratio_dur)
        .fuse()
        .then(|_| async_std::task::spawn_blocking(move || dram_ratio(region, chunk_size)));
    pin_mut!(ratio_intvl);
    let mut period = 0;
    let mut total = 0;
    let start = time::Instant::now();
    tracing::info!("iteration {label} reporting worker started");
    loop {
        select! {
            n = count.next().fuse() => match n {
                Some(c) => {
                    period += c;
                    total +=c;
                },
                // All sender dropped
                None => break,
            },
            n = gups_intvl.next().fuse() => match n {
                Some(_) => {
                    let hitherto = total as f64 / start.elapsed().as_secs_f64() / chunk_size as f64;
                    let instaneous = period as f64 / gups_dur.as_secs_f64() / chunk_size as f64;
                    tracing::info!("GUPS: iteration {label} hitherto {hitherto:.6} instaneous {instaneous:.6}");
                    period = 0;
                }
                None => unreachable!(),
            },
            n = ratio_intvl.next().fuse() => match n {
                Some(ratios) => {
                    tracing::info!("iteration {label} dram portion per gb: {ratios:?}");
                }
                None => unreachable!(),
            },
        }
    }
    let elapsed = start.elapsed();
    let gups = total as f64 / elapsed.as_secs_f64() / chunk_size as f64;
    tracing::info!("GUPS: iteration {label} final {gups:.6} elapsed {elapsed:?}");
}

fn update(mem: &mut [u8], g: usize, i: usize) {
    fn update<T: num_traits::WrappingAdd + num_traits::NumCast>(mem: &mut [u8], i: usize) {
        let ptr = mem.as_mut_ptr();
        let len = mem.len();
        let s = unsafe { slice::from_raw_parts_mut::<T>(ptr as _, len / mem::size_of::<T>()) };
        s[i] = s[i].wrapping_add(&num_traits::cast(1).unwrap());
    }
    match g {
        1 => update::<u8>(mem, i),
        2 => update::<u16>(mem, i),
        4 => update::<u32>(mem, i),
        8 => update::<u64>(mem, i),
        16 => update::<u128>(mem, i),
        _ => unimplemented!(),
    };
}

fn mem_region(addr: u64) -> pagemap::MemoryRegion {
    let maps = pagemap::maps(process::id() as _).unwrap();
    let map = maps
        .iter()
        .filter(|entry| entry.memory_region().contains(addr))
        .next()
        .unwrap();
    map.memory_region()
}

fn dram_ratio(region: pagemap::MemoryRegion, chunk_size: usize) -> Vec<f64> {
    let ptes = pagemap::PageMap::new(process::id() as _)
        .unwrap()
        .pagemap_region(&region)
        .unwrap();
    ptes.chunks(chunk_size / *PAGE_SIZE)
        .map(|ptes| {
            let dram = ptes
                .iter()
                .filter(|e| e.present() && DRAM_PFN_RANGE.contains(&e.pfn().unwrap()))
                .count();
            dram as f64 / ptes.len() as f64
        })
        .collect()
}

// The drgn script to get dram pfn range:
// ```python
// #!/usr/bin/env python3
//
// import drgn
// from drgn.helpers.linux import for_each_node_state
//
// def eprint(*args, **kwargs):
//     import sys
//     print(*args, file=sys.stderr, **kwargs)
//
// prog = drgn.program_from_kernel()
// try:
//     prog.load_debug_info(["/tmp/vmlinux"] )
// except drgn.MissingDebugInfoError as e:
//     eprint("Failed to load debug info: %s" % e)
// dram_nid = next(for_each_node_state(prog.constant("N_MEMORY")))
// dram_node = prog["node_data"][dram_nid]
// start_pfn = dram_node.node_start_pfn
// end_pfn = start_pfn + dram_node.node_spanned_pages
//
// print(start_pfn.value_(), end_pfn.value_())
// ```
lazy_static::lazy_static! {
    static ref PAGE_SIZE: usize = pagemap::page_size().unwrap() as _;

    static ref DRAM_PFN_RANGE : ops::Range<u64> = {
        let output = process::Command::new("sudo").arg("-E").arg("dram-pfn.py").env("LD_PRELOAD", "")
            .output()
            .unwrap();
        tracing::info!("drgn output: {output:?}");
        let mut pfns = std::str::from_utf8(&output.stdout).unwrap().split_whitespace().take(2);
        let start = pfns.next().unwrap().parse().unwrap();
        let end = pfns.next().unwrap().parse().unwrap();
        tracing::info!("dram pfn range: {start}..{end}");
        start..end
    };
}
