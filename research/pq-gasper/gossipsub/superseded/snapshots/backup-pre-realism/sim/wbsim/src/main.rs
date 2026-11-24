//! One-subnet simulator node, meant to run under Shadow.
//!
//! Every host in the simulation runs this binary with the same run config and
//! its own `--id`. Two delivery modes for the same workload:
//!
//! * `gossip`: today's pipeline. Every node joins every subnet topic (votes) and the
//!   aggregate topic (proofs). Votes are gossiped.
//! * `direct`: WB-PQ. Voters send each vote straight to the subscribed aggregators
//!   of its topic (request/response).
//!
//! Proofs, in either mode (`proofs`): `flood` gossips each proof on an aggregate
//! topic every node joins; `pull` announces it to the proposer, which pulls the
//! largest plus one random proof per topic; `decoy` pushes it straight to a fixed
//! set of nodes that includes the proposer, so aggregators can't tell which it is.
//!
//! Proving is not executed; an aggregator waits `prove_ms` before emitting a
//! proof of `proof_bytes`. Signatures are random-free filler of the real size.
//!
//! Output: one JSON object per line on stdout (events and per-slot byte counters).

use std::{
    cmp::Reverse,
    collections::{BinaryHeap, HashMap, HashSet},
    io,
    net::Ipv4Addr,
    sync::Arc,
    time::{Duration, SystemTime, UNIX_EPOCH},
};

use async_trait::async_trait;
use futures::{AsyncRead, AsyncReadExt, AsyncWrite, AsyncWriteExt, StreamExt};
use libp2p::{
    gossipsub::{self, IdentTopic, MessageAuthenticity, MessageId, ValidationMode},
    identity::{ed25519, Keypair},
    multiaddr::Protocol,
    noise,
    request_response::{self, ProtocolSupport},
    swarm::{NetworkBehaviour, SwarmEvent},
    tcp, yamux, Multiaddr, PeerId, StreamProtocol, Swarm,
};
use rand::{rngs::StdRng, Rng, SeedableRng};
use serde::Deserialize;
use serde_json::json;
use sha2::{Digest, Sha256};

// Shadow's simulated wall clock starts at 2000-01-01T00:00:00Z.
const SHADOW_EPOCH_S: u64 = 946_684_800;
const PORT: u16 = 9000;

const T_VOTE: u8 = 1;
const T_ANNOUNCE: u8 = 2;
const T_PULL: u8 = 3;
const T_PROOF: u8 = 4;
/// A node's votes for one topic in one message: header, then u32 validator indices.
const T_VOTES: u8 = 5;
/// Flood mode: message `a` of slot `slot`, published by node `b`.
const T_MSG: u8 = 6;

#[derive(Deserialize, Clone, Copy, PartialEq, Eq, Debug)]
#[serde(rename_all = "lowercase")]
enum Mode {
    Gossip,
    Direct,
    /// One topic every node joins; `sched` lists each slot's messages (publisher, offset).
    Flood,
}

#[derive(Deserialize, Clone, Copy, PartialEq, Eq, Debug)]
#[serde(rename_all = "lowercase")]
enum Proofs {
    Flood,
    Pull,
    Decoy,
}

#[derive(Deserialize, Clone, Copy, PartialEq, Eq, Debug)]
#[serde(rename_all = "lowercase")]
enum Role {
    Voter,
    Aggregator,
    Proposer,
}

#[derive(Deserialize, Clone)]
struct NodeCfg {
    id: u32,
    ip: Ipv4Addr,
    role: Role,
    /// Validator indices hosted by this node; each casts one vote per slot.
    validators: Vec<u32>,
    /// Aggregators: the direct topic they serve. In gossip mode they aggregate the
    /// whole subnet that contains this topic.
    #[serde(default)]
    topic: u32,
    /// Flood mode: topics this node subscribes to (default: topic 0 only).
    #[serde(default)]
    topics: Option<Vec<u32>>,
    /// Flood mode: peers this node dials (default: `gossip_dial` random peers).
    #[serde(default)]
    dial: Option<Vec<u32>>,
    /// Gossipsub overrides for this node, applied over the run-wide `gs`.
    #[serde(default)]
    gs: Option<GsCfg>,
    /// Flood mode: the one topic this node forwards in when `no_forward` is set (it is a leaf in the others).
    #[serde(default)]
    home: Option<u32>,
}

/// Gossipsub parameters that differ from the Ethereum defaults; unset fields keep them.
#[derive(Deserialize, Clone, Default)]
struct GsCfg {
    mesh_n: Option<usize>,
    mesh_n_low: Option<usize>,
    mesh_n_high: Option<usize>,
    mesh_outbound_min: Option<usize>,
    gossip_lazy: Option<usize>,
    gossip_factor: Option<f64>,
    heartbeat_ms: Option<u64>,
    flood_publish: Option<bool>,
    idontwant_on_publish: Option<bool>,
    idontwant_threshold: Option<usize>,
    forward_queue_ms: Option<u64>,
    publish_queue_ms: Option<u64>,
    queue_len: Option<usize>,
    max_ihave_messages: Option<usize>,
    max_ihave_length: Option<usize>,
    /// Receive but never forward: validate manually and report every message as Ignore (own publishes still go out).
    no_forward: Option<bool>,
    /// Serial signature verification before forwarding/delivery: µs per signature carried by the message.
    verify_us_per_sig: Option<u64>,
    /// Mesh parameters for the node's home topic (NodeCfg::home); defaults 8/6/12/2.
    home_mesh_n: Option<usize>,
    home_mesh_n_low: Option<usize>,
    home_mesh_n_high: Option<usize>,
    home_mesh_outbound_min: Option<usize>,
}

impl GsCfg {
    fn over(&self, o: &GsCfg) -> GsCfg {
        macro_rules! m { ($($f:ident),*) => { GsCfg { $($f: o.$f.or(self.$f)),* } } }
        m!(mesh_n, mesh_n_low, mesh_n_high, mesh_outbound_min, gossip_lazy, gossip_factor, heartbeat_ms,
           flood_publish, idontwant_on_publish, idontwant_threshold, forward_queue_ms, publish_queue_ms, queue_len,
           max_ihave_messages, max_ihave_length, no_forward, verify_us_per_sig, home_mesh_n, home_mesh_n_low,
           home_mesh_n_high, home_mesh_outbound_min)
    }
}

#[derive(Deserialize, Clone)]
struct RunCfg {
    mode: Mode,
    seed: u64,
    nodes: Vec<NodeCfg>,
    /// Validator v votes in direct topic v / votes_per_topic; topic t belongs to gossip
    /// subnet t / (topics / subnets). Every node joins every subnet in gossip mode.
    topics: u32,
    subnets: u32,
    votes_per_topic: u32,
    vote_bytes: usize,
    proof_bytes: usize,
    /// Simulated time (s since sim start) at which slot 0 begins.
    first_slot_s: f64,
    slot_s: f64,
    slots: u32,
    /// Offset of the vote into the slot and the spread of vote times.
    vote_offset_s: f64,
    vote_jitter_s: f64,
    /// Aggregators stop collecting at this offset into the slot.
    agg_deadline_s: f64,
    prove_ms: u64,
    proofs: Proofs,
    /// `decoy` proofs: the nodes every aggregator pushes its proof to (proposer included).
    #[serde(default)]
    decoys: Vec<u32>,
    /// Gossip mode: random peers each node dials at startup.
    gossip_dial: usize,
    /// Direct mode: a node signs all its validators' votes at one moment and sends
    /// them to each recipient as one message, instead of one message per vote.
    #[serde(default)]
    batch_votes: bool,
    /// Direct mode: dial aggregators just before voting instead of at startup.
    cold_connect: bool,
    /// Direct mode: proposer pulls once it has every announcement or after this wait.
    announce_wait_ms: u64,
    /// Flood mode: per slot, message k is [publisher, offset ms after slot start, topic, bytes,
    /// deadline ms]; topic defaults to 0 and bytes to `msg_bytes`.
    #[serde(default)]
    sched: Vec<Vec<Vec<u32>>>,
    /// Flood mode: number of topics (0..n_topics).
    #[serde(default)]
    n_topics: Option<u32>,
    /// Gossipsub overrides for every node.
    #[serde(default)]
    gs: Option<GsCfg>,
    #[serde(default)]
    msg_bytes: usize,
    /// Flood mode: byte and gossipsub counter snapshot interval (s).
    #[serde(default)]
    bin_s: f64,
    /// Flood mode: run on this long after the last slot so late deliveries show up.
    #[serde(default)]
    drain_s: f64,
    /// Flood mode peer manager: keep this many connected peers through discovery instead of static dials.
    /// Random discovery returns uniformly random nodes; subnet discovery (like an ENR attnets lookup)
    /// returns random nodes that join a given topic.
    #[serde(default)]
    peer_target: Option<usize>,
    /// Inbound connections beyond this many peers are refused.
    #[serde(default)]
    peer_max: Option<usize>,
    /// Keep at least this many connected peers in each joined topic (subnet discovery); pruning spares them.
    #[serde(default)]
    subnet_min_peers: Option<usize>,
    /// New dials per peer-manager tick from random discovery.
    #[serde(default)]
    pm_dials_per_tick: Option<usize>,
}

// ------------------------------------------------------------------ codec

#[derive(Clone, Default)]
struct RawCodec;

const KEEP: usize = 64 << 10;

async fn read_frame<T: AsyncRead + Unpin + Send>(io: &mut T) -> io::Result<Vec<u8>> {
    let mut len = [0u8; 4];
    io.read_exact(&mut len).await?;
    let len = u32::from_be_bytes(len) as usize;
    if len > 64 << 20 {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "frame too large"));
    }
    // Keep the first 64 KiB (header and validator indices) and read the rest, filler
    // standing in for signatures and proofs, into a scratch buffer. Holding every
    // in-flight 2 MB vote batch whole would need ~200 MB per aggregator.
    let mut buf = vec![0u8; len.min(KEEP)];
    io.read_exact(&mut buf).await?;
    let mut rest = len - buf.len();
    let mut scratch = [0u8; 16 << 10];
    while rest > 0 {
        let n = rest.min(scratch.len());
        io.read_exact(&mut scratch[..n]).await?;
        rest -= n;
    }
    Ok(buf)
}

async fn write_frame<T: AsyncWrite + Unpin + Send>(io: &mut T, data: &[u8]) -> io::Result<()> {
    io.write_all(&(data.len() as u32).to_be_bytes()).await?;
    io.write_all(data).await?;
    io.close().await
}

#[async_trait]
impl request_response::Codec for RawCodec {
    type Protocol = StreamProtocol;
    /// Shared, so a vote queued for 128 recipients is held once, not 128 times.
    type Request = Arc<Vec<u8>>;
    type Response = Vec<u8>;

    async fn read_request<T: AsyncRead + Unpin + Send>(&mut self, _: &StreamProtocol, io: &mut T) -> io::Result<Arc<Vec<u8>>> {
        read_frame(io).await.map(Arc::new)
    }
    async fn read_response<T: AsyncRead + Unpin + Send>(&mut self, _: &StreamProtocol, io: &mut T) -> io::Result<Vec<u8>> {
        read_frame(io).await
    }
    async fn write_request<T: AsyncWrite + Unpin + Send>(&mut self, _: &StreamProtocol, io: &mut T, r: Arc<Vec<u8>>) -> io::Result<()> {
        write_frame(io, &r).await
    }
    async fn write_response<T: AsyncWrite + Unpin + Send>(&mut self, _: &StreamProtocol, io: &mut T, r: Vec<u8>) -> io::Result<()> {
        write_frame(io, &r).await
    }
}

#[derive(NetworkBehaviour)]
struct Behaviour {
    gossipsub: gossipsub::Behaviour,
    rr: request_response::Behaviour<RawCodec>,
}

// ------------------------------------------------------------------ helpers

fn now_s() -> f64 {
    let d = SystemTime::now().duration_since(UNIX_EPOCH).unwrap();
    d.as_secs_f64() - SHADOW_EPOCH_S as f64
}

fn now_ns() -> u64 {
    (now_s() * 1e9) as u64
}

fn keypair(id: u32) -> Keypair {
    let mut seed = [0u8; 32];
    seed[..4].copy_from_slice(&id.to_be_bytes());
    seed[31] = 0x77;
    let sk = ed25519::SecretKey::try_from_bytes(seed).expect("32 bytes");
    Keypair::from(ed25519::Keypair::from(sk))
}

fn addr(n: &NodeCfg) -> Multiaddr {
    Multiaddr::empty()
        .with(Protocol::Ip4(n.ip))
        .with(Protocol::Tcp(PORT))
}

/// [type u8][slot u32][a u32][b u32][t_ns u64] + zero filler up to `size`.
fn encode(ty: u8, slot: u32, a: u32, b: u32, t_ns: u64, size: usize) -> Vec<u8> {
    let mut v = Vec::with_capacity(size.max(21));
    v.push(ty);
    v.extend_from_slice(&slot.to_be_bytes());
    v.extend_from_slice(&a.to_be_bytes());
    v.extend_from_slice(&b.to_be_bytes());
    v.extend_from_slice(&t_ns.to_be_bytes());
    v.resize(size.max(21), 0);
    v
}

fn decode(v: &[u8]) -> Option<(u8, u32, u32, u32, u64)> {
    if v.len() < 21 {
        return None;
    }
    let u = |r: std::ops::Range<usize>| u32::from_be_bytes(v[r].try_into().unwrap());
    Some((v[0], u(1..5), u(5..9), u(9..13), u64::from_be_bytes(v[13..21].try_into().unwrap())))
}

fn emit(v: serde_json::Value) {
    println!("{v}");
}

fn bandwidth(reg: &prometheus_client::registry::Registry) -> (u64, u64) {
    let mut s = String::new();
    prometheus_client::encoding::text::encode(&mut s, reg).unwrap();
    let (mut rx, mut tx) = (0u64, 0u64);
    for line in s.lines().filter(|l| l.starts_with("libp2p_bandwidth")) {
        let val: f64 = line.rsplit(' ').next().and_then(|x| x.parse().ok()).unwrap_or(0.0);
        if line.contains("Inbound") {
            rx += val as u64;
        } else if line.contains("Outbound") {
            tx += val as u64;
        }
    }
    (rx, tx)
}

/// Gossipsub counters summed over labels, keyed by metric name (`_total` dropped).
fn gossip_counters(reg: &prometheus_client::registry::Registry) -> serde_json::Map<String, serde_json::Value> {
    const KEEP: [&str; 12] = [
        "topic_msg_recv_counts_unfiltered", "topic_msg_recv_counts", "topic_msg_recv_bytes",
        "topic_msg_sent_counts", "topic_msg_sent_bytes", "topic_msg_published", "topic_iwant_msgs",
        "idontwant_msgs", "idontwant_msgs_ids", "forward_messages_dropped_per_topic",
        "timedout_messages_dropped_per_topic", "memcache_misses",
    ];
    let mut s = String::new();
    prometheus_client::encoding::text::encode(&mut s, reg).unwrap();
    let mut out = serde_json::Map::new();
    for line in s.lines().filter(|l| !l.starts_with('#')) {
        let name = line.split(|c| c == '{' || c == ' ').next().unwrap_or("");
        let name = name.strip_suffix("_total").unwrap_or(name);
        if name == "mesh_peer_counts" || KEEP.contains(&name) {
            let val: f64 = line.rsplit(' ').next().and_then(|x| x.parse().ok()).unwrap_or(0.0);
            let e = out.entry(name.to_string()).or_insert(json!(0u64));
            *e = json!(e.as_u64().unwrap_or(0) + val as u64);
        }
    }
    out
}

// ------------------------------------------------------------------ actions

#[derive(PartialEq, Eq, PartialOrd, Ord, Clone, Debug)]
enum Action {
    Dial(u32),
    DialAggregators,
    Vote { slot: u32, validator: u32 },
    VoteBatch(u32),
    Deadline(u32),
    EmitProof(u32),
    Pull(u32),
    Counters(u32),
    Publish { slot: u32, k: u32 },
    /// Flood mode: log this slot's receipt times (anything later counts as never).
    Report(u32),
    /// Peer manager heartbeat: prune above target, discover and dial below it.
    PeerManager,
    /// Log connections and mesh peers per joined topic (just before publishing starts).
    MeshLog(u32),
    /// Finish verifying the oldest message in Node::verifying.
    Validated,
    Tick,
    Exit,
}

struct Node {
    cfg: RunCfg,
    me: NodeCfg,
    peers: HashMap<PeerId, u32>,
    /// Aggregators per direct topic.
    agg_peers: HashMap<u32, Vec<PeerId>>,
    n_aggs: usize,
    proposer: PeerId,
    vote_topics: Vec<IdentTopic>,
    agg_topic: IdentTopic,
    queue: BinaryHeap<Reverse<(u64, Action)>>,
    rng: StdRng,
    /// Aggregator: votes collected per slot (validator set), proof bytes ready to serve.
    collected: HashMap<u32, HashSet<u32>>,
    closed: HashSet<u32>,
    proofs: HashMap<u32, Vec<u8>>,
    /// Proposer (direct): announcements per slot (topic, count, peer).
    announces: HashMap<u32, Vec<(u32, u32, PeerId)>>,
    pulled: HashSet<u32>,
    /// Votes received per slot by any node (gossip mode visibility).
    seen_votes: HashMap<u32, u32>,
    last_counters: (u64, u64),
    /// Requests waiting for a connection (cold connect); flushed on ConnectionEstablished.
    pending: HashMap<PeerId, Vec<Arc<Vec<u8>>>>,
    /// Flood mode: per slot, first receipt of each message in ms after slot start (-1: never).
    rx: HashMap<u32, Vec<i64>>,
    /// Leaf that never forwards (GsCfg::no_forward).
    no_forward: bool,
    /// With no_forward: the topic this node still forwards in.
    home_hash: Option<gossipsub::TopicHash>,
    verify_ns_per_sig: u64,
    /// FIFO of messages awaiting the (single, serial) verifier: id, source, slot, k.
    verifying: std::collections::VecDeque<(MessageId, PeerId, u32, u32, bool)>,
    verify_busy_until: u64,
    /// Messages gossipsub failed to send, cumulative from SlowPeer events:
    /// publish, forward, queue full, timed out.
    failed: [u64; 4],
    /// Peer manager: dials in flight (node id -> start ns), and counters: dials, prunes, refused inbound.
    dialing: HashMap<u32, u64>,
    pm: [u64; 3],
}

impl Node {
    fn topics_of(&self, i: u32) -> &[u32] {
        self.cfg.nodes[i as usize].topics.as_deref().unwrap_or(&[0])
    }

    fn pm_dial(&mut self, swarm: &mut Swarm<Behaviour>, id: u32) {
        let pid = keypair(id).public().to_peer_id();
        let opts = libp2p::swarm::dial_opts::DialOpts::peer_id(pid)
            .addresses(vec![addr(&self.cfg.nodes[id as usize])]).allocate_new_port().build();
        if swarm.dial(opts).is_ok() {
            self.dialing.insert(id, now_ns());
            self.pm[0] += 1;
        }
    }

    fn peer_manager(&mut self, swarm: &mut Swarm<Behaviour>) {
        let target = self.cfg.peer_target.unwrap();
        let smin = self.cfg.subnet_min_peers.unwrap_or(6);
        let now = now_ns();
        self.dialing.retain(|_, t| now < *t + 10_000_000_000);
        let mut conn: Vec<u32> = swarm.connected_peers().filter_map(|p| self.peers.get(p).copied()).collect();
        conn.sort();
        let mine: Vec<u32> = self.me.topics.clone().unwrap_or(vec![0]);
        let shared = |s: &Self, j: u32| -> Vec<u32> { s.topics_of(j).iter().copied().filter(|t| mine.contains(t)).collect() };
        let mut cnt: HashMap<u32, usize> = HashMap::new();
        for &j in &conn {
            for t in shared(self, j) {
                *cnt.entry(t).or_default() += 1;
            }
        }
        // prune down to target: peers sharing no joined topic first, never below smin in a topic
        if conn.len() > target {
            let mut order = conn.clone();
            for k in (1..order.len()).rev() {
                order.swap(k, self.rng.gen_range(0..=k));
            }
            order.sort_by_key(|&j| !shared(self, j).is_empty());
            let mut excess = conn.len() - target;
            for j in order {
                if excess == 0 {
                    break;
                }
                let ts = shared(self, j);
                if ts.iter().any(|t| cnt[t] <= smin) {
                    continue;
                }
                for t in ts {
                    *cnt.get_mut(&t).unwrap() -= 1;
                }
                swarm.disconnect_peer_id(keypair(j).public().to_peer_id()).ok();
                self.pm[1] += 1;
                excess -= 1;
            }
        }
        let n = self.cfg.nodes.len() as u32;
        let busy: HashSet<u32> = conn.iter().copied().chain(self.dialing.keys().copied()).chain([self.me.id]).collect();
        // subnet discovery: top up each joined topic to smin
        for &t in &mine {
            let have = cnt.get(&t).copied().unwrap_or(0);
            if have >= smin {
                continue;
            }
            let mut cands: Vec<u32> = (0..n).filter(|j| !busy.contains(j) && !self.dialing.contains_key(j)
                && self.topics_of(*j).contains(&t)).collect();
            for _ in 0..(smin - have).min(cands.len()) {
                let k = self.rng.gen_range(0..cands.len());
                let j = cands.swap_remove(k);
                self.pm_dial(swarm, j);
            }
        }
        // random discovery up to target
        let mut budget = self.cfg.pm_dials_per_tick.unwrap_or(32);
        let mut tries = 0;
        while conn.len() + self.dialing.len() < target && budget > 0 && tries < 1000 {
            tries += 1;
            let j = self.rng.gen_range(0..n);
            if busy.contains(&j) || self.dialing.contains_key(&j) {
                continue;
            }
            self.pm_dial(swarm, j);
            budget -= 1;
        }
        // fast heartbeat during warm-up, then like Lighthouse's 30 s
        let next = if now_s() < self.cfg.first_slot_s { 3.0 } else { 30.0 };
        self.schedule(now_s() + next, Action::PeerManager);
    }

    fn schedule(&mut self, at_s: f64, a: Action) {
        self.queue.push(Reverse(((at_s * 1e9) as u64, a)));
    }

    fn topic_of(&self, validator: u32) -> u32 {
        validator / self.cfg.votes_per_topic
    }

    fn subnet_of(&self, topic: u32) -> u32 {
        topic / (self.cfg.topics / self.cfg.subnets)
    }

    fn slot_start(&self, slot: u32) -> f64 {
        self.cfg.first_slot_s + slot as f64 * self.cfg.slot_s
    }

    fn plan(&mut self) {
        let cfg = self.cfg.clone();
        if cfg.mode == Mode::Flood {
            return self.plan_flood();
        }
        // connections
        if cfg.mode == Mode::Gossip || cfg.proofs == Proofs::Flood {
            // gossip mesh: dial a few random peers
            let n = cfg.nodes.len() as u32;
            let mut targets = HashSet::new();
            while targets.len() < cfg.gossip_dial.min(n as usize - 1) {
                let t = self.rng.gen_range(0..n);
                if t != self.me.id {
                    targets.insert(t);
                }
            }
            let mut targets: Vec<_> = targets.into_iter().collect();
            targets.sort();
            for t in targets {
                let at = 1.0 + self.rng.gen::<f64>() * 2.0;
                self.schedule(at, Action::Dial(t));
            }
        }
        if cfg.mode == Mode::Direct && !self.me.validators.is_empty() && !cfg.cold_connect {
            let at = 1.0 + self.rng.gen::<f64>() * 2.0;
            self.schedule(at, Action::DialAggregators);
        }
        if self.me.role == Role::Aggregator {
            // keep connections to whoever the proofs go to directly
            let targets = match cfg.proofs {
                Proofs::Flood => vec![],
                Proofs::Pull => vec![cfg.nodes.iter().find(|n| n.role == Role::Proposer).unwrap().id],
                Proofs::Decoy => cfg.decoys.clone(),
            };
            for t in targets {
                let at = 1.0 + self.rng.gen::<f64>();
                self.schedule(at, Action::Dial(t));
            }
        }
        for slot in 0..cfg.slots {
            let t0 = self.slot_start(slot);
            self.schedule(t0, Action::Counters(2 * slot));
            self.schedule(t0 + cfg.agg_deadline_s, Action::Counters(2 * slot + 1));
            if cfg.mode == Mode::Direct && cfg.cold_connect && !self.me.validators.is_empty() {
                // dial right before the vote (worst case: no persistent connection)
                self.schedule(t0 + cfg.vote_offset_s, Action::DialAggregators);
            }
            if cfg.batch_votes && !self.me.validators.is_empty() {
                let jitter = self.rng.gen::<f64>() * cfg.vote_jitter_s;
                self.schedule(t0 + cfg.vote_offset_s + jitter, Action::VoteBatch(slot));
            } else {
                for &v in &self.me.validators.clone() {
                    let jitter = self.rng.gen::<f64>() * cfg.vote_jitter_s;
                    self.schedule(t0 + cfg.vote_offset_s + jitter, Action::Vote { slot, validator: v });
                }
            }
            if self.me.role == Role::Aggregator {
                self.schedule(t0 + cfg.agg_deadline_s, Action::Deadline(slot));
            }
        }
        let end = self.slot_start(cfg.slots);
        self.schedule(end, Action::Counters(2 * cfg.slots));
        self.schedule(end + 0.5, Action::Exit);
    }

    fn plan_flood(&mut self) {
        let cfg = self.cfg.clone();
        let n = cfg.nodes.len() as u32;
        let mut targets = HashSet::new();
        while targets.len() < cfg.gossip_dial.min(n as usize - 1) {
            let t = self.rng.gen_range(0..n);
            if t != self.me.id {
                targets.insert(t);
            }
        }
        let mut targets: Vec<_> = targets.into_iter().collect();
        targets.sort();
        if let Some(d) = &self.me.dial {
            targets = d.clone(); // explicit list from gen_config (random draws above keep the rng in step)
        }
        if cfg.peer_target.is_some() {
            targets.clear(); // peering emerges from the peer manager instead
            let at = 1.0 + self.rng.gen::<f64>() * 2.0;
            self.schedule(at, Action::PeerManager);
        }
        for t in targets {
            let at = 1.0 + self.rng.gen::<f64>() * 2.0;
            self.schedule(at, Action::Dial(t));
        }
        for (slot, msgs) in cfg.sched.iter().enumerate() {
            let t0 = self.slot_start(slot as u32);
            // per slot, so a run stopped early still has every slot that ended before it
            self.schedule(t0 + cfg.slot_s + cfg.drain_s, Action::Report(slot as u32));
            self.schedule(t0 + cfg.vote_offset_s - 0.05, Action::MeshLog(slot as u32));
            for (k, e) in msgs.iter().enumerate() {
                let (publisher, off_ms) = (e[0], e[1]);
                if publisher == self.me.id {
                    self.schedule(t0 + off_ms as f64 / 1e3, Action::Publish { slot: slot as u32, k: k as u32 });
                }
            }
        }
        let end = self.slot_start(cfg.slots) + cfg.drain_s;
        let mut t = cfg.first_slot_s;
        while t <= end + 1e-9 {
            self.schedule(t, Action::Tick);
            t += cfg.bin_s;
        }
        self.schedule(end + 0.5, Action::Exit);
    }

    fn record_rx(&mut self, slot: u32, k: u32) {
        let Some(n) = self.cfg.sched.get(slot as usize).map(|m| m.len()) else { return };
        let ms = ((now_s() - self.slot_start(slot)) * 1e3).round() as i64;
        if ms > ((self.cfg.slot_s + self.cfg.drain_s) * 1e3) as i64 {
            return; // slot already reported
        }
        let v = self.rx.entry(slot).or_insert_with(|| vec![-1; n]);
        if let Some(x) = v.get_mut(k as usize) {
            if *x < 0 {
                *x = ms;
            }
        }
    }

    fn dial(&mut self, swarm: &mut Swarm<Behaviour>, id: u32) {
        let n = &self.cfg.nodes[id as usize];
        let pid = keypair(id).public().to_peer_id();
        if !swarm.is_connected(&pid) {
            let opts = libp2p::swarm::dial_opts::DialOpts::peer_id(pid).addresses(vec![addr(n)]).allocate_new_port().build();
            if let Err(e) = swarm.dial(opts) {
                emit(json!({"ev":"dial_err","node":self.me.id,"to":id,"err":e.to_string()}));
            }
        }
    }

    fn act(&mut self, swarm: &mut Swarm<Behaviour>, a: Action) -> bool {
        let cfg = self.cfg.clone();
        match a {
            Action::Dial(id) => self.dial(swarm, id),
            Action::DialAggregators => {
                // the aggregators of the topics this node's validators vote in
                let topics: HashSet<u32> = self.me.validators.iter().map(|&v| self.topic_of(v)).collect();
                let ids: Vec<u32> = cfg.nodes.iter()
                    .filter(|n| n.role == Role::Aggregator && topics.contains(&n.topic))
                    .map(|n| n.id).collect();
                for id in ids {
                    if id != self.me.id {
                        self.dial(swarm, id);
                    }
                }
            }
            Action::Vote { slot, validator } => {
                let t = now_ns();
                let msg = Arc::new(encode(T_VOTE, slot, validator, self.me.id, t, cfg.vote_bytes));
                let topic = self.topic_of(validator);
                emit(json!({"ev":"vote_tx","node":self.me.id,"slot":slot,"v":validator,"t":t as f64/1e9}));
                match cfg.mode {
                    Mode::Gossip | Mode::Flood => {
                        let vt = self.vote_topics[self.subnet_of(topic) as usize].clone();
                        if let Err(e) = swarm.behaviour_mut().gossipsub.publish(vt, msg.to_vec()) {
                            emit(json!({"ev":"publish_err","node":self.me.id,"err":format!("{e:?}")}));
                        }
                        // the publishing node "receives" its own vote
                        if self.me.role != Role::Voter {
                            self.on_vote(slot, validator, t, self.me.id);
                        }
                    }
                    Mode::Direct => {
                        for p in self.agg_peers[&topic].clone() {
                            if p == *swarm.local_peer_id() {
                                self.on_vote(slot, validator, t, self.me.id);
                            } else if swarm.is_connected(&p) {
                                swarm.behaviour_mut().rr.send_request(&p, msg.clone());
                            } else {
                                self.pending.entry(p).or_default().push(msg.clone());
                            }
                        }
                    }
                }
            }
            Action::VoteBatch(slot) => {
                let t = now_ns();
                let mut by_topic: HashMap<u32, Vec<u32>> = HashMap::new();
                for &v in &self.me.validators {
                    by_topic.entry(self.topic_of(v)).or_default().push(v);
                }
                emit(json!({"ev":"vote_tx","node":self.me.id,"slot":slot,"n":self.me.validators.len(),"t":t as f64/1e9}));
                for (topic, vs) in by_topic {
                    let mut m = encode(T_VOTES, slot, vs.len() as u32, self.me.id, t, (vs.len() * cfg.vote_bytes).max(21 + 4 * vs.len()));
                    for (k, v) in vs.iter().enumerate() {
                        m[21 + 4 * k..25 + 4 * k].copy_from_slice(&v.to_be_bytes());
                    }
                    let msg = Arc::new(m);
                    for p in self.agg_peers[&topic].clone() {
                        if p == *swarm.local_peer_id() {
                            self.on_votes(slot, &vs, t, self.me.id);
                        } else if swarm.is_connected(&p) {
                            swarm.behaviour_mut().rr.send_request(&p, msg.clone());
                        } else {
                            self.pending.entry(p).or_default().push(msg.clone());
                        }
                    }
                }
            }
            Action::Deadline(slot) => {
                self.closed.insert(slot);
                let n = self.collected.get(&slot).map_or(0, |s| s.len());
                emit(json!({"ev":"agg_close","node":self.me.id,"slot":slot,"count":n,"t":now_s()}));
                self.schedule(now_s() + cfg.prove_ms as f64 / 1e3, Action::EmitProof(slot));
            }
            Action::EmitProof(slot) => {
                let n = self.collected.get(&slot).map_or(0, |s| s.len()) as u32;
                let t = now_ns();
                let proof = encode(T_PROOF, slot, self.me.id, n, t, cfg.proof_bytes);
                emit(json!({"ev":"proof_tx","node":self.me.id,"slot":slot,"count":n,"t":t as f64/1e9}));
                match cfg.proofs {
                    Proofs::Flood => {
                        if let Err(e) = swarm.behaviour_mut().gossipsub.publish(self.agg_topic.clone(), proof) {
                            emit(json!({"ev":"publish_err","node":self.me.id,"err":format!("{e:?}")}));
                        }
                    }
                    Proofs::Decoy => {
                        let proof = Arc::new(proof);
                        for &d in &cfg.decoys {
                            let p = keypair(d).public().to_peer_id();
                            if d == self.me.id {
                                continue;
                            }
                            if swarm.is_connected(&p) {
                                swarm.behaviour_mut().rr.send_request(&p, proof.clone());
                            } else {
                                self.pending.entry(p).or_default().push(proof.clone());
                            }
                        }
                    }
                    Proofs::Pull => {
                        self.proofs.insert(slot, proof);
                        let ann = encode(T_ANNOUNCE, slot, self.me.id, n, t, 64);
                        let prop = self.proposer;
                        swarm.behaviour_mut().rr.send_request(&prop, Arc::new(ann));
                    }
                }
            }
            Action::Pull(slot) => {
                if self.pulled.insert(slot) {
                    let all = self.announces.get(&slot).cloned().unwrap_or_default();
                    let mut topics: Vec<u32> = all.iter().map(|a| a.0).collect::<HashSet<_>>().into_iter().collect();
                    topics.sort();
                    let mut picks = vec![];
                    for topic in topics {
                        let mut anns: Vec<(u32, PeerId)> = all.iter().filter(|a| a.0 == topic).map(|a| (a.1, a.2)).collect();
                        // largest aggregate (first announced among equals) + one random other
                        let best = anns.iter().enumerate().max_by_key(|(i, (c, _))| (*c, Reverse(*i))).map(|(i, _)| i).unwrap();
                        picks.push(anns.remove(best).1);
                        if !anns.is_empty() {
                            let r = self.rng.gen_range(0..anns.len());
                            picks.push(anns[r].1);
                        }
                    }
                    if picks.is_empty() {
                        return true;
                    }
                    emit(json!({"ev":"pull","node":self.me.id,"slot":slot,"n":picks.len(),"t":now_s()}));
                    for p in picks {
                        let req = encode(T_PULL, slot, self.me.id, 0, now_ns(), 21);
                        swarm.behaviour_mut().rr.send_request(&p, Arc::new(req));
                    }
                }
            }
            Action::Publish { slot, k } => {
                let e = &cfg.sched[slot as usize][k as usize];
                let size = e.get(3).map_or(cfg.msg_bytes, |&b| b as usize);
                let msg = encode(T_MSG, slot, k, self.me.id, now_ns(), size);
                let topic = self.vote_topics[e.get(2).copied().unwrap_or(0) as usize].clone();
                if let Err(e) = swarm.behaviour_mut().gossipsub.publish(topic, msg) {
                    emit(json!({"ev":"publish_err","node":self.me.id,"slot":slot,"k":k,"err":format!("{e:?}"),"t":now_s()}));
                }
                // the publisher holds its own message from the moment it publishes
                self.record_rx(slot, k);
            }
            Action::Report(slot) => {
                let r = self.rx.remove(&slot).unwrap_or_else(|| vec![-1; cfg.sched[slot as usize].len()]);
                emit(json!({"ev":"rx","node":self.me.id,"slot":slot,"r":r}));
            }
            Action::Validated => {
                if let Some((mid, src, slot, k, fwd)) = self.verifying.pop_front() {
                    let acc = if fwd { gossipsub::MessageAcceptance::Accept } else { gossipsub::MessageAcceptance::Ignore };
                    swarm.behaviour_mut().gossipsub.report_message_validation_result(&mid, &src, acc);
                    self.record_rx(slot, k);
                }
            }
            Action::PeerManager => self.peer_manager(swarm),
            Action::MeshLog(slot) => {
                let conns: Vec<u32> = swarm.connected_peers().filter_map(|p| self.peers.get(p).copied()).collect();
                let mut mesh = serde_json::Map::new();
                for &t in self.me.topics.clone().as_deref().unwrap_or(&[0]) {
                    let h = self.vote_topics[t as usize].hash();
                    let ids: Vec<u32> = swarm.behaviour().gossipsub.mesh_peers(&h).filter_map(|p| self.peers.get(p).copied()).collect();
                    mesh.insert(t.to_string(), json!(ids));
                }
                emit(json!({"ev":"mesh","node":self.me.id,"slot":slot,"conns":conns,"mesh":mesh}));
            }
            Action::Counters(_) | Action::Tick => {} // handled in main, which owns the registries
            Action::Exit => return false,
        }
        true
    }

    fn on_vote(&mut self, slot: u32, validator: u32, t_tx_ns: u64, from: u32) {
        *self.seen_votes.entry(slot).or_default() += 1;
        if self.me.role != Role::Aggregator {
            return;
        }
        let topic = self.topic_of(validator);
        let mine = match self.cfg.mode {
            Mode::Direct => topic == self.me.topic,
            Mode::Gossip | Mode::Flood => self.subnet_of(topic) == self.subnet_of(self.me.topic),
        };
        if !mine {
            return;
        }
        let late = self.closed.contains(&slot);
        if self.collected.entry(slot).or_default().insert(validator) {
            let t = now_s();
            emit(json!({"ev":"vote_rx","node":self.me.id,"slot":slot,"v":validator,"from":from,
                "lat":t - t_tx_ns as f64/1e9,"t":t,"late":late}));
        }
    }

    /// A batch of votes: one event with the number of new ones.
    fn on_votes(&mut self, slot: u32, vs: &[u32], t_tx_ns: u64, from: u32) {
        if self.me.role != Role::Aggregator {
            return;
        }
        let late = self.closed.contains(&slot);
        let mine: Vec<u32> = vs.iter().copied().filter(|&v| self.topic_of(v) == self.me.topic).collect();
        let set = self.collected.entry(slot).or_default();
        let n = mine.into_iter().filter(|&v| set.insert(v)).count();
        if n > 0 {
            let t = now_s();
            emit(json!({"ev":"vote_rx","node":self.me.id,"slot":slot,"n":n,"from":from,
                "lat":t - t_tx_ns as f64/1e9,"t":t,"late":late}));
        }
    }

    fn on_proof(&mut self, slot: u32, agg: u32, count: u32, t_tx_ns: u64, via: &str) {
        let t = now_s();
        {
            emit(json!({"ev":"proof_rx","node":self.me.id,"slot":slot,"agg":agg,"count":count,
                "lat":t - t_tx_ns as f64/1e9,"t":t,"via":via}));
        }
    }

    fn on_event(&mut self, swarm: &mut Swarm<Behaviour>, ev: SwarmEvent<BehaviourEvent>) {
        match ev {
            SwarmEvent::Behaviour(BehaviourEvent::Gossipsub(gossipsub::Event::Message { message, message_id, propagation_source })) => {
                // a leaf (no_forward) still forwards in its home topic
                let fwd = !self.no_forward || self.home_hash.as_ref() == Some(&message.topic);
                if self.verify_ns_per_sig > 0 {
                    if let Some((T_MSG, slot, k, _, _)) = decode(&message.data) {
                        let nsigs = self.cfg.sched.get(slot as usize).and_then(|m| m.get(k as usize))
                            .and_then(|e| e.get(5)).copied().unwrap_or(1).max(1) as u64;
                        let start = self.verify_busy_until.max(now_ns());
                        self.verify_busy_until = start + nsigs * self.verify_ns_per_sig;
                        self.verifying.push_back((message_id, propagation_source, slot, k, fwd));
                        self.queue.push(Reverse((self.verify_busy_until, Action::Validated)));
                        return;
                    }
                }
                if self.no_forward {
                    let acc = if fwd { gossipsub::MessageAcceptance::Accept } else { gossipsub::MessageAcceptance::Ignore };
                    swarm.behaviour_mut().gossipsub.report_message_validation_result(&message_id, &propagation_source, acc);
                }
                if let Some((ty, slot, a, b, t)) = decode(&message.data) {
                    match ty {
                        T_VOTE => self.on_vote(slot, a, t, b),
                        T_PROOF => self.on_proof(slot, a, b, t, "gossip"),
                        T_MSG => self.record_rx(slot, a),
                        _ => {}
                    }
                }
            }
            // messages rust-libp2p dropped from a peer's send queue (full, or queued past
            // forward_queue_duration = 1 s / publish_queue_duration = 5 s)
            SwarmEvent::Behaviour(BehaviourEvent::Gossipsub(gossipsub::Event::SlowPeer { failed_messages: f, .. })) => {
                for (c, x) in self.failed.iter_mut().zip([f.publish, f.forward, f.priority + f.non_priority, f.timeout]) {
                    *c += x as u64;
                }
                if self.cfg.mode == Mode::Flood {
                    return; // cumulative counts go out with every tick
                }
                emit(json!({"ev":"slow_peer","node":self.me.id,"publish":f.publish,"forward":f.forward,
                    "queue_full":f.priority + f.non_priority,"timeout":f.timeout,"t":now_s()}));
            }
            SwarmEvent::Behaviour(BehaviourEvent::Rr(request_response::Event::Message { peer, message, .. })) => match message {
                request_response::Message::Request { request, channel, .. } => {
                    let mut resp = vec![0u8];
                    if let Some((ty, slot, a, b, t)) = decode(&request) {
                        let from = self.peers.get(&peer).copied().unwrap_or(u32::MAX);
                        match ty {
                            T_VOTE => self.on_vote(slot, a, t, from),
                            T_VOTES => {
                                let vs: Vec<u32> = (0..a as usize)
                                    .map(|k| u32::from_be_bytes(request[21 + 4 * k..25 + 4 * k].try_into().unwrap()))
                                    .collect();
                                self.on_votes(slot, &vs, t, from);
                            }
                            T_ANNOUNCE => {
                                let topic = self.cfg.nodes[a as usize].topic;
                                let e = self.announces.entry(slot).or_default();
                                e.push((topic, b, peer));
                                let got = e.len();
                                emit(json!({"ev":"announce_rx","node":self.me.id,"slot":slot,"agg":a,"count":b,"t":now_s()}));
                                let n_aggs = self.n_aggs;
                                if got == 1 {
                                    let at = now_s() + self.cfg.announce_wait_ms as f64 / 1e3;
                                    self.schedule(at, Action::Pull(slot));
                                }
                                if got >= n_aggs {
                                    self.schedule(now_s(), Action::Pull(slot));
                                }
                            }
                            T_PROOF => self.on_proof(slot, a, b, t, "push"),
                            T_PULL => {
                                if let Some(p) = self.proofs.get(&slot) {
                                    resp = p.clone();
                                }
                            }
                            _ => {}
                        }
                    }
                    let _ = swarm.behaviour_mut().rr.send_response(channel, resp);
                }
                request_response::Message::Response { response, .. } => {
                    if let Some((T_PROOF, slot, a, b, t)) = decode(&response) {
                        self.on_proof(slot, a, b, t, "pull");
                    }
                }
            },
            SwarmEvent::Behaviour(BehaviourEvent::Rr(request_response::Event::OutboundFailure { peer, error, .. })) => {
                emit(json!({"ev":"rr_fail","node":self.me.id,"peer":self.peers.get(&peer),"err":error.to_string(),"t":now_s()}));
            }
            SwarmEvent::ConnectionEstablished { peer_id, endpoint, num_established, .. } => {
                if let Some(&j) = self.peers.get(&peer_id) {
                    self.dialing.remove(&j);
                }
                if let Some(max) = self.cfg.peer_max {
                    if endpoint.is_listener() && num_established.get() == 1 && swarm.connected_peers().count() > max {
                        swarm.disconnect_peer_id(peer_id).ok();
                        self.pm[2] += 1;
                        return;
                    }
                }
                for req in self.pending.remove(&peer_id).unwrap_or_default() {
                    swarm.behaviour_mut().rr.send_request(&peer_id, req);
                }
            }
            SwarmEvent::OutgoingConnectionError { peer_id, error, .. } => {
                if let Some(j) = peer_id.and_then(|p| self.peers.get(&p).copied()) {
                    self.dialing.remove(&j);
                    if self.cfg.peer_target.is_some() {
                        return; // the peer manager retries elsewhere; refused or crossed dials are normal
                    }
                }
                emit(json!({"ev":"conn_err","node":self.me.id,"peer":peer_id.and_then(|p| self.peers.get(&p).copied()),"err":error.to_string(),"t":now_s()}));
            }
            _ => {}
        }
    }
}

#[tokio::main(flavor = "current_thread")]
async fn main() {
    let args: Vec<String> = std::env::args().collect();
    let cfg_path = args.iter().position(|a| a == "--cfg").map(|i| args[i + 1].clone()).expect("--cfg");
    let id: u32 = args.iter().position(|a| a == "--id").map(|i| args[i + 1].parse().unwrap()).expect("--id");
    let cfg: RunCfg = serde_json::from_slice(&std::fs::read(&cfg_path).expect("read cfg")).expect("parse cfg");
    let me = cfg.nodes[id as usize].clone();
    assert_eq!(me.id, id);

    let mut registry = prometheus_client::registry::Registry::default();
    let mut gs_registry = prometheus_client::registry::Registry::default();
    let kp = keypair(id);
    let gs = cfg.gs.clone().unwrap_or_default().over(&me.gs.clone().unwrap_or_default());
    let mut gb = gossipsub::ConfigBuilder::default();
    gb
        // Ethereum consensus-spec gossipsub parameters (overridable through `gs`)
        .heartbeat_interval(Duration::from_millis(gs.heartbeat_ms.unwrap_or(700)))
        .mesh_n(gs.mesh_n.unwrap_or(8))
        .mesh_n_low(gs.mesh_n_low.unwrap_or(6))
        .mesh_n_high(gs.mesh_n_high.unwrap_or(12))
        .mesh_outbound_min(gs.mesh_outbound_min.unwrap_or(2))
        // rust-libp2p slices peers[..len - retain_scores] when pruning, so it must not exceed a small mesh
        .retain_scores(4.min(gs.mesh_n.unwrap_or(8)))
        .gossip_lazy(gs.gossip_lazy.unwrap_or(6))
        .gossip_factor(gs.gossip_factor.unwrap_or(0.25))
        .idontwant_on_publish(gs.idontwant_on_publish.unwrap_or(false))
        .idontwant_message_size_threshold(gs.idontwant_threshold.unwrap_or(1000))
        .forward_queue_duration(Duration::from_millis(gs.forward_queue_ms.unwrap_or(1000)))
        .publish_queue_duration(Duration::from_millis(gs.publish_queue_ms.unwrap_or(5000)))
        .connection_handler_queue_len(gs.queue_len.unwrap_or(5000))
        .max_ihave_messages(gs.max_ihave_messages.unwrap_or(10))
        .max_ihave_length(gs.max_ihave_length.unwrap_or(5000))
        .history_length(6)
        .history_gossip(3)
        .fanout_ttl(Duration::from_secs(60))
        .duplicate_cache_time(Duration::from_secs(60))
        .max_transmit_size(4 << 20)
        .flood_publish(gs.flood_publish.unwrap_or(false))
        .validation_mode(ValidationMode::Anonymous)
        .message_id_fn(|m: &gossipsub::Message| MessageId::from(Sha256::digest(&m.data)[..20].to_vec()));
    let no_forward = gs.no_forward.unwrap_or(false);
    let topic_name = |t: u32| if t == 0 { "xmss_signatures".to_string() } else { format!("xmss_{t}") };
    let home_hash = me.home.filter(|_| no_forward).map(|t| IdentTopic::new(topic_name(t)).hash());
    if let Some(h) = &home_hash {
        gb.mesh_n_for_topic(gs.home_mesh_n.unwrap_or(8), h.clone())
            .mesh_n_low_for_topic(gs.home_mesh_n_low.unwrap_or(6), h.clone())
            .mesh_n_high_for_topic(gs.home_mesh_n_high.unwrap_or(12), h.clone())
            .mesh_outbound_min_for_topic(gs.home_mesh_outbound_min.unwrap_or(2), h.clone());
    }
    let verify_ns_per_sig = gs.verify_us_per_sig.unwrap_or(0) * 1000;
    if no_forward || verify_ns_per_sig > 0 {
        gb.validate_messages();
    }
    let gcfg = gb.build().expect("gossipsub config");

    let mut swarm = libp2p::SwarmBuilder::with_existing_identity(kp)
        .with_tokio()
        .with_tcp(tcp::Config::default().nodelay(true), noise::Config::new, yamux::Config::default)
        .expect("tcp")
        .with_bandwidth_metrics(&mut registry)
        .with_behaviour(|_| Behaviour {
            gossipsub: gossipsub::Behaviour::new(MessageAuthenticity::Anonymous, gcfg)
                .expect("gossipsub")
                .with_metrics(&mut gs_registry, Default::default()),
            rr: request_response::Behaviour::new(
                [(StreamProtocol::new("/wb-pq/1"), ProtocolSupport::Full)],
                request_response::Config::default()
                    .with_request_timeout(Duration::from_secs(20))
                    .with_max_concurrent_streams(1024),
            ),
        })
        .expect("behaviour")
        .with_swarm_config(|c| c.with_idle_connection_timeout(Duration::from_secs(3600)))
        .build();

    swarm.listen_on(addr(&me)).expect("listen");
    let vote_topics: Vec<IdentTopic> = if cfg.mode == Mode::Flood {
        (0..cfg.n_topics.unwrap_or(1))
            .map(|t| IdentTopic::new(topic_name(t)))
            .collect()
    } else {
        (0..cfg.subnets).map(|s| IdentTopic::new(format!("votes_subnet_{s}"))).collect()
    };
    let agg_topic = IdentTopic::new("aggregate_and_proof");
    if cfg.mode == Mode::Flood {
        for &t in me.topics.as_deref().unwrap_or(&[0]) {
            swarm.behaviour_mut().gossipsub.subscribe(&vote_topics[t as usize]).unwrap();
        }
    }
    if cfg.mode == Mode::Gossip {
        for t in &vote_topics {
            swarm.behaviour_mut().gossipsub.subscribe(t).unwrap();
        }
    }
    if cfg.proofs == Proofs::Flood {
        swarm.behaviour_mut().gossipsub.subscribe(&agg_topic).unwrap();
    }

    let peers: HashMap<PeerId, u32> = cfg.nodes.iter().map(|n| (keypair(n.id).public().to_peer_id(), n.id)).collect();
    let mut agg_peers: HashMap<u32, Vec<PeerId>> = HashMap::new();
    for n in cfg.nodes.iter().filter(|n| n.role == Role::Aggregator) {
        agg_peers.entry(n.topic).or_default().push(keypair(n.id).public().to_peer_id());
    }
    let n_aggs = agg_peers.values().map(|v| v.len()).sum();
    // flood mode has no proposer; any peer id will do
    let proposer = keypair(cfg.nodes.iter().find(|n| n.role == Role::Proposer).map_or(0, |n| n.id)).public().to_peer_id();
    let mut node = Node {
        rng: StdRng::seed_from_u64(cfg.seed ^ (id as u64).wrapping_mul(0x9E37_79B9_7F4A_7C15)),
        cfg,
        me,
        peers,
        agg_peers,
        n_aggs,
        proposer,
        vote_topics,
        agg_topic,
        queue: BinaryHeap::new(),
        collected: HashMap::new(),
        closed: HashSet::new(),
        proofs: HashMap::new(),
        announces: HashMap::new(),
        pulled: HashSet::new(),
        seen_votes: HashMap::new(),
        last_counters: (0, 0),
        pending: HashMap::new(),
        rx: HashMap::new(),
        no_forward,
        home_hash,
        verify_ns_per_sig,
        verifying: Default::default(),
        verify_busy_until: 0,
        failed: [0; 4],
        dialing: HashMap::new(),
        pm: [0; 3],
    };
    node.plan();
    emit(json!({"ev":"start","node":id,"role":format!("{:?}",node.me.role),"t":now_s()}));

    loop {
        let next = node.queue.peek().map(|Reverse((t, _))| *t).unwrap();
        let wait = Duration::from_nanos(next.saturating_sub(now_ns()));
        tokio::select! {
            ev = swarm.select_next_some() => node.on_event(&mut swarm, ev),
            _ = tokio::time::sleep(wait) => {
                while node.queue.peek().is_some_and(|Reverse((t, _))| *t <= now_ns()) {
                    let Reverse((_, a)) = node.queue.pop().unwrap();
                    let a = match a {
                        // counters need the registry, which lives in main
                        Action::Counters(idx) => {
                            // idx = 2*slot + phase; log the interval that just ended
                            let (rx, tx) = bandwidth(&registry);
                            let (prx, ptx) = node.last_counters;
                            let conns = swarm.connected_peers().count();
                            if idx > 0 {
                                let (slot, phase) = ((idx - 1) / 2, ["votes", "proofs"][((idx - 1) % 2) as usize]);
                                emit(json!({"ev":"bytes","node":id,"role":format!("{:?}",node.me.role),
                                    "slot":slot,"phase":phase,"rx":rx-prx,"tx":tx-ptx,
                                    "votes_seen":node.seen_votes.get(&slot).copied().unwrap_or(0),"conns":conns}));
                            } else {
                                emit(json!({"ev":"bytes_warmup","node":id,"rx":rx,"tx":tx,"conns":conns}));
                            }
                            node.last_counters = (rx, tx);
                            continue;
                        }
                        Action::Tick => {
                            let (rx, tx) = bandwidth(&registry);
                            let mut ev = gossip_counters(&gs_registry);
                            for (k, v) in [("node", id as u64), ("rx", rx), ("tx", tx),
                                ("conns", swarm.connected_peers().count() as u64),
                                ("f_publish", node.failed[0]), ("f_forward", node.failed[1]),
                                ("f_queue_full", node.failed[2]), ("f_timeout", node.failed[3]),
                                ("pm_dials", node.pm[0]), ("pm_prunes", node.pm[1]), ("pm_refused", node.pm[2])] {
                                ev.insert(k.into(), json!(v));
                            }
                            ev.insert("ev".into(), json!("tick"));
                            ev.insert("t".into(), json!((now_s() * 1e3).round() / 1e3));
                            emit(serde_json::Value::Object(ev));
                            continue;
                        }
                        a => a,
                    };
                    if !node.act(&mut swarm, a) {
                        return;
                    }
                }
            }
        }
    }
}
