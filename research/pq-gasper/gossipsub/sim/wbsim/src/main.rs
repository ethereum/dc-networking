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
/// Flood mode with per-node publish files: T_MSG plus [kind u8][nsigs u16][track u8] after the header.
const T_MSG2: u8 = 7;

/// Message kinds (T_MSG2). PQ signatures are kind 0; the rest is background traffic.
const K_PQ: u8 = 0;
const K_BAD: u8 = 7;
const KIND_NAMES: [&str; 8] = ["pq", "block", "col", "att", "agg", "sync", "syncc", "bad"];

/// Topic ids: 0 global aggregate, 1..=99 PQ subnets, then background topics (see topic_name).
fn topic_name(t: u32) -> String {
    match t {
        0 => "xmss_signatures".into(),
        1..=99 => format!("xmss_{t}"),
        100 => "bg_block".into(),
        101 => "bg_agg".into(),
        102 => "bg_syncc".into(),
        200..=263 => format!("bg_att_{}", t - 200),
        300..=303 => format!("bg_sync_{}", t - 300),
        400..=527 => format!("bg_col_{}", t - 400),
        _ => format!("t_{t}"),
    }
}

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
    /// CPU slowness factor: verification costs are multiplied by this (1 = reference machine).
    #[serde(default)]
    cpu: Option<f64>,
    /// Parallel verification workers (default 1, serial).
    #[serde(default)]
    workers: Option<usize>,
    /// Offline intervals [from, to) in simulated seconds: leave (to = 1e9), join (from = 0), restart.
    /// Going offline drops the swarm (connections, mesh, scores, caches); coming back builds a new one.
    #[serde(default)]
    offline: Vec<(f64, f64)>,
    /// Behind NAT: not returned by discovery, refuses inbound connections.
    #[serde(default)]
    nat: bool,
    /// Per-node peer manager target and inbound cap (client mix); default the run-wide values.
    #[serde(default)]
    peer_target: Option<usize>,
    #[serde(default)]
    peer_max: Option<usize>,
}

/// One message this node publishes: slot, index within its class (PQ or background), offset ms,
/// topic, bytes, signatures carried, kind, tracked (receipt times logged).
#[derive(Deserialize, Clone, Copy)]
struct Pub(u32, u32, u32, u32, u32, u32, u8, u8);

/// Gossipsub v1.1 peer scoring with Lighthouse's parameters (gossipsub_scoring_parameters.rs).
#[derive(Deserialize, Clone)]
struct ScoreCfg {
    /// Active validators, for the attestation and aggregate rates Lighthouse derives its parameters from.
    active_validators: f64,
    /// PQ subnets and messages per subnet per slot; scored like attestation subnets.
    pq_subnets: u32,
    pq_rate: f64,
    /// Disconnect peers whose score falls below the gossip threshold (Lighthouse's peer manager bans
    /// peers well below it; this is the simple version).
    #[serde(default)]
    disconnect_below_gossip: bool,
    /// Override Lighthouse's slow-peer penalty weight (-10; 0 turns it off).
    #[serde(default)]
    slow_peer_weight: Option<f64>,
    /// Validation only: mesh-delivery (P3) activation in s on every topic, instead of 1 epoch / 17 slots.
    #[serde(default)]
    mesh_activation_s: Option<f64>,
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
    /// Message cache: heartbeats kept (Lighthouse 12) and gossiped (3).
    history_length: Option<usize>,
    history_gossip: Option<usize>,
    /// Slow-peer score weight in this node's view of its peers, overriding scoring.slow_peer_weight: -10 in the
    /// rust-libp2p clients (Lighthouse, Grandine), 0 in clients without the term (Prysm, Teku, Nimbus, Lodestar).
    slow_peer_weight: Option<f64>,
    /// Mesh-delivery (P3/P3b) weight on every topic in this node's view: 0 Lighthouse's -topic_weight (default;
    /// Lighthouse, Grandine), 1 off (Prysm: meshDeliveryIsScored = false), 2 -max_positive_score /
    /// (topic_weight * threshold^2), so a full deficit costs the whole max positive score (Teku, Lodestar, Nimbus).
    p3_mode: Option<u8>,
    /// Which requested ids of an IWANT get a scored promise (P7 when broken): 0 every id (rust-libp2p:
    /// Lighthouse, Grandine), 1 one random id (Prysm, Teku, Lodestar), 2 none (Nimbus). Modes 1 and 2 also
    /// re-request an unseen id that is still awaited from another peer; mode 0 waits for that promise to end (3 s).
    iwant_promise_mode: Option<u8>,
}

impl GsCfg {
    fn over(&self, o: &GsCfg) -> GsCfg {
        macro_rules! m { ($($f:ident),*) => { GsCfg { $($f: o.$f.or(self.$f)),* } } }
        m!(mesh_n, mesh_n_low, mesh_n_high, mesh_outbound_min, gossip_lazy, gossip_factor, heartbeat_ms,
           flood_publish, idontwant_on_publish, idontwant_threshold, forward_queue_ms, publish_queue_ms, queue_len,
           max_ihave_messages, max_ihave_length, no_forward, verify_us_per_sig, home_mesh_n, home_mesh_n_low,
           home_mesh_n_high, home_mesh_outbound_min, history_length, history_gossip, slow_peer_weight,
           p3_mode, iwant_promise_mode)
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
    /// Flood mode: read this node's publishes from <pub_dir>/<id>.json (list of Pub) instead of `sched`.
    #[serde(default)]
    pub_dir: Option<String>,
    /// With pub_dir: PQ messages per slot (receipt vector length).
    #[serde(default)]
    pq_counts: Vec<u32>,
    /// Verification cost before forwarding, µs per signature, by message kind (K_PQ uses
    /// gs.verify_us_per_sig when set). Multiplied by the node's cpu factor.
    #[serde(default)]
    verify_us_kind: Vec<u64>,
    /// Connection churn: after warm-up, each connection is dropped by the peer manager at rate
    /// 1/conn_life_s (exponential lifetimes), unless that takes a joined topic below subnet_min_peers.
    #[serde(default)]
    conn_life_s: Option<f64>,
    /// After warm-up, run the peer manager every 5 s instead of 30 s while below target (discovery refill).
    #[serde(default)]
    pm_refill: bool,
    #[serde(default)]
    scoring: Option<ScoreCfg>,
    /// libp2p ping every this many seconds; RTTs are logged (network validation).
    #[serde(default)]
    ping_s: Option<f64>,
    /// IGNORE (no forward, not recorded) a flood message received more than this many seconds after it was
    /// published. Clients ignore re-received blocks, attestations and aggregates through their first-seen rules;
    /// without this, a message held in a stalled connection past gossipsub's 60 s duplicate cache is accepted as
    /// new by every node and re-floods the network. Counted as stale_pq / stale_bg in the tick events.
    #[serde(default)]
    max_msg_age_s: Option<f64>,
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
    ping: libp2p::swarm::behaviour::toggle::Toggle<libp2p::ping::Behaviour>,
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

/// Gossipsub counters summed over labels, keyed by metric name (`_total` dropped). PQ topics keep the plain
/// name; background topics are summed per class as `bg_<class>:<name>` (e.g. `bg_att:topic_msg_recv_counts`).
/// Mesh inclusion/churn events and scoring penalties are also split by reason (`<name>:<reason>`).
fn gossip_counters(reg: &prometheus_client::registry::Registry) -> serde_json::Map<String, serde_json::Value> {
    const KEEP: [&str; 20] = [
        "topic_msg_recv_counts_unfiltered", "topic_msg_recv_counts", "topic_msg_recv_bytes",
        "topic_msg_sent_counts", "topic_msg_sent_bytes", "topic_msg_published", "topic_iwant_msgs",
        "idontwant_msgs", "idontwant_msgs_ids", "forward_messages_dropped_per_topic",
        "timedout_messages_dropped_per_topic", "memcache_misses", "mesh_peer_inclusion_events",
        "mesh_peer_churn_events", "scoring_penalties", "iwant_rpcs", "iwant_promises", "broken_promises",
        "message_deficit_per_topic", "iwant_rerequests",
    ];
    let mut s = String::new();
    prometheus_client::encoding::text::encode(&mut s, reg).unwrap();
    let mut out = serde_json::Map::new();
    for line in s.lines().filter(|l| !l.starts_with('#')) {
        let name = line.split(|c| c == '{' || c == ' ').next().unwrap_or("");
        let name = name.strip_suffix("_total").unwrap_or(name);
        if name == "mesh_peer_counts" || KEEP.contains(&name) {
            let val: f64 = line.rsplit(' ').next().and_then(|x| x.parse().ok()).unwrap_or(0.0);
            let label = |k: &str| line.split(&format!("{k}=\"")).nth(1).and_then(|r| r.split('"').next());
            let mut key = match label("hash") {
                Some(h) if h.starts_with("bg_") => {
                    let class = h[3..].split('_').next().unwrap_or("");
                    format!("bg_{class}:{name}")
                }
                _ => name.to_string(),
            };
            if let Some(r) = label("reason").or_else(|| label("penalty")) {
                key = format!("{key}:{r}");
            }
            let e = out.entry(key).or_insert(json!(0u64));
            *e = json!(e.as_u64().unwrap_or(0) + val as u64);
        }
    }
    out
}

/// Lighthouse's gossipsub scoring parameters and thresholds (beacon_node/lighthouse_network/src/service/
/// gossipsub_scoring_parameters.rs at a376def), for mainnet constants (12 s slots, 32-slot epochs, 64
/// attestation subnets, 16 target aggregators per committee) and a large current slot (mesh delivery
/// scoring active). The PQ subnets are scored like attestation subnets: weight 1/pq_subnets each and
/// their own message rate, and they add to the maximum positive score like the attestation subnets do.
fn eth_peer_score(sc: &ScoreCfg, mesh_n: usize, p3_mode: u8)
                  -> (gossipsub::PeerScoreParams, gossipsub::PeerScoreThresholds) {
    use gossipsub::{PeerScoreParams, PeerScoreThresholds, TopicScoreParams};
    let thresholds = PeerScoreThresholds {
        gossip_threshold: -4000.0,
        publish_threshold: -8000.0,
        graylist_threshold: -16000.0,
        accept_px_threshold: 100.0,
        opportunistic_graft_threshold: 5.0,
    };
    let slot = Duration::from_secs(12);
    let epoch = slot * 32;
    let decay_interval = slot;
    let decay_to_zero: f64 = 0.01;
    let decay = |t: Duration| decay_to_zero.powf(1.0 / (t.as_secs_f64() / decay_interval.as_secs_f64()));
    let convergence = |d: f64, rate: f64| rate / (1.0 - d);
    let (block_w, agg_w, att_w) = (0.5, 0.5, 1.0 / 64.0);
    let pq_w = if sc.pq_subnets > 0 { 1.0 / sc.pq_subnets as f64 } else { 0.0 };
    let max_positive = (10.0 + 40.0) * (block_w + agg_w + 1.0 + 0.15 + if sc.pq_subnets > 0 { 1.0 } else { 0.0 });
    let mut p = PeerScoreParams {
        decay_interval,
        decay_to_zero,
        retain_score: epoch * 100,
        app_specific_weight: 1.0,
        ip_colocation_factor_threshold: 8.0,
        behaviour_penalty_threshold: 6.0,
        behaviour_penalty_decay: decay(epoch * 10),
        slow_peer_decay: 0.1,
        slow_peer_weight: sc.slow_peer_weight.unwrap_or(-10.0),
        slow_peer_threshold: 0.0,
        ..Default::default()
    };
    let target = convergence(p.behaviour_penalty_decay, 10.0 / 32.0) - p.behaviour_penalty_threshold;
    p.behaviour_penalty_weight = thresholds.gossip_threshold / target.powi(2);
    p.topic_score_cap = max_positive * 0.5;
    p.ip_colocation_factor_weight = -p.topic_score_cap;
    // topic params: weight, expected messages per slot, first-delivery decay, mesh-delivery info
    let topic = |w: f64, rate: f64, first_decay: Duration, mesh: Option<(u64, f64, Duration)>| {
        let mut t = TopicScoreParams::default();
        t.topic_weight = w;
        t.time_in_mesh_quantum = slot;
        t.time_in_mesh_cap = 3600.0 / 12.0;
        t.time_in_mesh_weight = 10.0 / t.time_in_mesh_cap;
        t.first_message_deliveries_decay = decay(first_decay);
        t.first_message_deliveries_cap = convergence(t.first_message_deliveries_decay, 2.0 * rate / mesh_n as f64);
        t.first_message_deliveries_weight = 40.0 / t.first_message_deliveries_cap;
        if let Some((decay_slots, cap_factor, activation)) = mesh {
            t.mesh_message_deliveries_decay = decay(slot * decay_slots as u32);
            t.mesh_message_deliveries_threshold =
                convergence(t.mesh_message_deliveries_decay, rate / 50.0) * t.mesh_message_deliveries_decay;
            t.mesh_message_deliveries_cap = (cap_factor * t.mesh_message_deliveries_threshold).max(2.0);
            t.mesh_message_deliveries_activation = activation;
            t.mesh_message_deliveries_window = Duration::from_secs(2);
            t.mesh_failure_penalty_decay = t.mesh_message_deliveries_decay;
            t.mesh_message_deliveries_weight = match p3_mode {
                1 => 0.0,
                2 => -max_positive / (t.topic_weight * t.mesh_message_deliveries_threshold.powi(2)),
                _ => -t.topic_weight,
            };
            t.mesh_failure_penalty_weight = t.mesh_message_deliveries_weight;
        } else {
            t.mesh_message_deliveries_weight = 0.0;
            t.mesh_message_deliveries_threshold = 0.0;
            t.mesh_failure_penalty_weight = 0.0;
        }
        t.invalid_message_deliveries_weight = -max_positive / t.topic_weight;
        t.invalid_message_deliveries_decay = decay(epoch * 50);
        t
    };
    // aggregators per slot: 64 committees x 16 target aggregators (Lighthouse's formula gives ~1,024)
    let att_rate = sc.active_validators / 64.0 / 32.0;
    let agg_rate = 64.0 * 16.0;
    let multi = true; // 64 committees per slot >= 2 * 64 / 32
    let att_mesh = Some((32 * if multi { 4 } else { 16 }, 16.0, if multi { slot * 17 } else { epoch * 3 }));
    p.topics.insert(IdentTopic::new(topic_name(100)).hash(), topic(block_w, 1.0, epoch * 20, Some((32 * 5, 3.0, epoch))));
    p.topics.insert(IdentTopic::new(topic_name(101)).hash(), topic(agg_w, agg_rate, epoch, Some((32 * 2, 4.0, epoch))));
    let att = topic(att_w, att_rate, epoch, att_mesh);
    for s in 0..64 {
        p.topics.insert(IdentTopic::new(topic_name(200 + s)).hash(), att.clone());
    }
    if sc.pq_subnets > 0 {
        let pq = topic(pq_w, sc.pq_rate, epoch, att_mesh);
        for s in 1..=sc.pq_subnets {
            p.topics.insert(IdentTopic::new(topic_name(s)).hash(), pq.clone());
        }
    }
    if let Some(s) = sc.mesh_activation_s {
        for t in p.topics.values_mut() {
            t.mesh_message_deliveries_activation = Duration::from_secs_f64(s);
        }
    }
    (p, thresholds)
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
    /// Publish my_pubs[i] (per-node publish file).
    Pub(u32),
    /// Flood mode: log this slot's receipt times (anything later counts as never).
    Report(u32),
    /// Peer manager heartbeat: prune above target, discover and dial below it.
    PeerManager,
    /// Log connections and mesh peers per joined topic (just before publishing starts).
    MeshLog(u32),
    /// Finish verifying message `seq` in Node::verifying.
    Validated(u64),
    /// Churn: drop the swarm (all connections and gossipsub state) / build a new one.
    GoOffline,
    GoOnline,
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
    /// Gossipsub validates manually (report_message_validation_result for every flood message).
    validating: bool,
    /// Messages being verified, by sequence number: id, source, slot, k, accept, kind, tracked.
    verifying: HashMap<u64, (MessageId, PeerId, u32, u32, gossipsub::MessageAcceptance, u8, bool)>,
    verify_seq: u64,
    /// Verification stats: messages verified, total µs from receipt to verdict (queue + work), max µs.
    vstat: [u64; 3],
    /// Each verification worker's busy-until time (ns).
    verify_free: Vec<u64>,
    /// This node's publishes (per-node file, or its entries of `sched`).
    my_pubs: Vec<Pub>,
    /// Background receipt times per slot: (index, ms after slot start), tracked messages only.
    rxbg: HashMap<u32, Vec<(u32, i64)>>,
    online: bool,
    /// Peer manager: time of the previous run (connection churn uses the elapsed time).
    pm_last: f64,
    /// Messages gossipsub failed to send, cumulative from SlowPeer events:
    /// publish, forward, queue full, timed out.
    failed: [u64; 4],
    /// Flood messages ignored as older than max_msg_age_s, cumulative: PQ, background.
    stale: [u64; 2],
    /// Peer manager: dials in flight (node id -> start ns), and counters: dials, prunes, refused inbound,
    /// churned connections, score disconnects, offline transitions.
    dialing: HashMap<u32, u64>,
    pm: [u64; 6],
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
        let target = self.me.peer_target.or(self.cfg.peer_target).unwrap();
        let smin = self.cfg.subnet_min_peers.unwrap_or(6);
        let now = now_ns();
        let elapsed = now_s() - self.pm_last;
        self.pm_last = now_s();
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
        // drop a peer unless that takes a joined topic below smin
        let drop_peer = |s: &mut Self, swarm: &mut Swarm<Behaviour>, cnt: &mut HashMap<u32, usize>, j: u32| -> bool {
            let ts = shared(s, j);
            if ts.iter().any(|t| cnt[t] <= smin) {
                return false;
            }
            for t in ts {
                *cnt.get_mut(&t).unwrap() -= 1;
            }
            swarm.disconnect_peer_id(keypair(j).public().to_peer_id()).ok();
            true
        };
        let warm = now_s() >= self.cfg.first_slot_s;
        // scoring: disconnect peers below the gossip threshold
        if let Some(sc) = self.cfg.scoring.clone().filter(|sc| sc.disconnect_below_gossip) {
            let _ = sc;
            let bad: Vec<u32> = conn.iter().copied().filter(|&j| {
                swarm.behaviour().gossipsub.peer_score(&keypair(j).public().to_peer_id()).is_some_and(|x| x < -4000.0)
            }).collect();
            for j in bad {
                let ts = shared(self, j);
                for t in ts {
                    *cnt.get_mut(&t).unwrap() -= 1;
                }
                swarm.disconnect_peer_id(keypair(j).public().to_peer_id()).ok();
                self.pm[4] += 1;
                conn.retain(|&x| x != j);
            }
        }
        // connection churn: each connection ends at rate 1/conn_life_s
        if let (Some(life), true) = (self.cfg.conn_life_s, warm) {
            let p = 1.0 - (-elapsed / life).exp();
            let mut gone = vec![];
            for &j in &conn {
                if self.rng.gen::<f64>() < p && drop_peer(self, swarm, &mut cnt, j) {
                    self.pm[3] += 1;
                    gone.push(j);
                }
            }
            conn.retain(|j| !gone.contains(j));
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
                if !drop_peer(self, swarm, &mut cnt, j) {
                    continue;
                }
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
                && !self.cfg.nodes[*j as usize].nat && self.topics_of(*j).contains(&t)).collect();
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
            if busy.contains(&j) || self.dialing.contains_key(&j) || self.cfg.nodes[j as usize].nat {
                continue;
            }
            self.pm_dial(swarm, j);
            budget -= 1;
        }
        // fast heartbeat during warm-up, then like Lighthouse's 30 s (5 s while below target with pm_refill,
        // standing in for discovery results arriving between heartbeats)
        let below = swarm.connected_peers().count() < target;
        let next = if !warm { 3.0 } else if self.cfg.pm_refill && below { 5.0 } else { 30.0 };
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
        if let Some(dir) = &cfg.pub_dir {
            let f = format!("{dir}/{}.json", self.me.id);
            self.my_pubs = serde_json::from_slice(&std::fs::read(&f).unwrap_or_else(|_| b"[]".to_vec())).expect("pub file");
        } else {
            for (slot, msgs) in cfg.sched.iter().enumerate() {
                for (k, e) in msgs.iter().enumerate() {
                    if e[0] == self.me.id {
                        let g = |i: usize, d: u32| e.get(i).copied().unwrap_or(d);
                        self.my_pubs.push(Pub(slot as u32, k as u32, e[1], g(2, 0), g(3, cfg.msg_bytes as u32), g(5, 1), K_PQ, 1));
                    }
                }
            }
        }
        for slot in 0..cfg.slots {
            let t0 = self.slot_start(slot);
            // per slot, so a run stopped early still has every slot that ended before it
            self.schedule(t0 + cfg.slot_s + cfg.drain_s, Action::Report(slot));
            self.schedule(t0 + cfg.vote_offset_s - 0.05, Action::MeshLog(slot));
        }
        for i in 0..self.my_pubs.len() {
            let p = self.my_pubs[i];
            self.schedule(self.slot_start(p.0) + p.2 as f64 / 1e3, Action::Pub(i as u32));
        }
        for &(a, b) in &self.me.offline.clone() {
            self.schedule(a.max(0.0), Action::GoOffline);
            if b < 1e8 {
                self.schedule(b, Action::GoOnline);
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

    fn pq_count(&self, slot: u32) -> Option<usize> {
        if self.cfg.pub_dir.is_some() {
            self.cfg.pq_counts.get(slot as usize).map(|&x| x as usize)
        } else {
            self.cfg.sched.get(slot as usize).map(|m| m.len())
        }
    }

    fn record_bg(&mut self, slot: u32, k: u32) {
        if slot >= self.cfg.slots {
            return;
        }
        let ms = ((now_s() - self.slot_start(slot)) * 1e3).round() as i64;
        if ms > ((self.cfg.slot_s + self.cfg.drain_s) * 1e3) as i64 {
            return;
        }
        self.rxbg.entry(slot).or_default().push((k, ms));
    }

    /// A received or own message: PQ receipt vector, or the tracked-background list.
    fn record(&mut self, slot: u32, k: u32, kind: u8, track: bool) {
        if kind == K_PQ {
            self.record_rx(slot, k);
        } else if track && kind != K_BAD {
            self.record_bg(slot, k);
        }
    }

    /// Verification time for a message of `kind` carrying `nsigs` signatures.
    fn verify_cost_ns(&self, kind: u8, nsigs: u64) -> u64 {
        let per = if kind == K_PQ && self.verify_ns_per_sig > 0 {
            self.verify_ns_per_sig
        } else {
            self.cfg.verify_us_kind.get(kind as usize).copied().unwrap_or(0) * 1000
        };
        (per as f64 * nsigs.max(1) as f64 * self.me.cpu.unwrap_or(1.0)) as u64
    }

    fn record_rx(&mut self, slot: u32, k: u32) {
        let Some(n) = self.pq_count(slot) else { return };
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
            Action::Pub(i) => {
                if !self.online {
                    return true; // offline: nothing goes out (the message is lost, as for a down validator)
                }
                let Pub(slot, k, _, topic, size, nsigs, kind, track) = self.my_pubs[i as usize];
                let msg = if cfg.pub_dir.is_some() {
                    let mut m = encode(T_MSG2, slot, k, self.me.id, now_ns(), (size as usize).max(25));
                    m[21] = kind;
                    m[22..24].copy_from_slice(&(nsigs.min(65535) as u16).to_be_bytes());
                    m[24] = track;
                    m
                } else {
                    encode(T_MSG, slot, k, self.me.id, now_ns(), size as usize)
                };
                if let Err(e) = swarm.behaviour_mut().gossipsub.publish(IdentTopic::new(topic_name(topic)), msg) {
                    if kind == K_PQ {
                        emit(json!({"ev":"publish_err","node":self.me.id,"slot":slot,"k":k,"err":format!("{e:?}"),"t":now_s()}));
                    }
                }
                // the publisher holds its own message from the moment it publishes
                self.record(slot, k, kind, track == 1);
            }
            Action::Report(slot) => {
                let r = self.rx.remove(&slot).unwrap_or_else(|| vec![-1; self.pq_count(slot).unwrap_or(0)]);
                emit(json!({"ev":"rx","node":self.me.id,"slot":slot,"r":r,"on":self.online}));
                if let Some(b) = self.rxbg.remove(&slot) {
                    emit(json!({"ev":"rxbg","node":self.me.id,"slot":slot,"r":b}));
                }
            }
            Action::Validated(seq) => {
                if let Some((mid, src, slot, k, acc, kind, track)) = self.verifying.remove(&seq) {
                    let ok = !matches!(acc, gossipsub::MessageAcceptance::Reject);
                    swarm.behaviour_mut().gossipsub.report_message_validation_result(&mid, &src, acc);
                    if ok {
                        self.record(slot, k, kind, track);
                    }
                }
            }
            Action::PeerManager => {
                if self.online {
                    self.peer_manager(swarm);
                }
            }
            Action::MeshLog(slot) => {
                if !self.online {
                    return true;
                }
                let conns: Vec<u32> = swarm.connected_peers().filter_map(|p| self.peers.get(p).copied()).collect();
                let mut mesh = serde_json::Map::new();
                for &t in self.me.topics.clone().as_deref().unwrap_or(&[0]) {
                    let h = IdentTopic::new(topic_name(t)).hash();
                    let ids: Vec<u32> = swarm.behaviour().gossipsub.mesh_peers(&h).filter_map(|p| self.peers.get(p).copied()).collect();
                    mesh.insert(t.to_string(), json!(ids));
                }
                // peer scores of connected peers (scoring on): min, mean, max, number below 0
                let sc: Vec<f64> = swarm.connected_peers().filter_map(|p| swarm.behaviour().gossipsub.peer_score(p)).collect();
                let score = if sc.is_empty() { json!(null) } else {
                    json!([sc.iter().cloned().fold(f64::MAX, f64::min), sc.iter().sum::<f64>() / sc.len() as f64,
                           sc.iter().cloned().fold(f64::MIN, f64::max), sc.iter().filter(|&&x| x < 0.0).count()])
                };
                // negatively scored peers (scoring validation): (peer id, score)
                let neg: Vec<(Option<u32>, f64)> = swarm.connected_peers()
                    .filter_map(|p| swarm.behaviour().gossipsub.peer_score(p).filter(|&x| x < 0.0).map(|x| (self.peers.get(p).copied(), x)))
                    .collect();
                emit(json!({"ev":"mesh","node":self.me.id,"slot":slot,"conns":conns,"mesh":mesh,"score":score,"neg":neg}));
            }
            Action::GoOffline | Action::GoOnline => {} // handled in main, which owns the swarm
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
                let flood_msg = match decode(&message.data) {
                    Some((T_MSG, slot, k, _, _)) => {
                        let nsigs = self.cfg.sched.get(slot as usize).and_then(|m| m.get(k as usize))
                            .and_then(|e| e.get(5)).copied().unwrap_or(1).max(1);
                        Some((slot, k, K_PQ, nsigs, true))
                    }
                    Some((T_MSG2, slot, k, _, _)) if message.data.len() >= 25 => Some((slot, k, message.data[21],
                        u16::from_be_bytes([message.data[22], message.data[23]]) as u32, message.data[24] == 1)),
                    _ => None,
                };
                // decode()'s last field is the publish time (ns) for T_MSG and T_MSG2
                if let (Some(max), Some((_, _, kind, _, _)), Some((_, _, _, _, t_pub))) =
                    (self.cfg.max_msg_age_s, flood_msg, decode(&message.data))
                {
                    if now_ns().saturating_sub(t_pub) as f64 > max * 1e9 {
                        if self.validating {
                            swarm.behaviour_mut().gossipsub.report_message_validation_result(
                                &message_id, &propagation_source, gossipsub::MessageAcceptance::Ignore);
                        }
                        self.stale[(kind != K_PQ) as usize] += 1;
                        return;
                    }
                }
                if let (true, Some((slot, k, kind, nsigs, track))) = (self.validating, flood_msg) {
                    let acc = if kind == K_BAD {
                        gossipsub::MessageAcceptance::Reject // invalid signature: P4 penalty for the sender
                    } else if fwd {
                        gossipsub::MessageAcceptance::Accept
                    } else {
                        gossipsub::MessageAcceptance::Ignore
                    };
                    let cost = self.verify_cost_ns(kind, nsigs as u64);
                    if cost == 0 {
                        let ok = !matches!(acc, gossipsub::MessageAcceptance::Reject);
                        swarm.behaviour_mut().gossipsub.report_message_validation_result(&message_id, &propagation_source, acc);
                        if ok {
                            self.record(slot, k, kind, track);
                        }
                        return;
                    }
                    // earliest-free of the node's verification workers
                    let w = (0..self.verify_free.len()).min_by_key(|&i| self.verify_free[i]).unwrap();
                    let done = self.verify_free[w].max(now_ns()) + cost;
                    self.verify_free[w] = done;
                    let d_us = (done - now_ns()) / 1000;
                    self.vstat[0] += 1;
                    self.vstat[1] += d_us;
                    self.vstat[2] = self.vstat[2].max(d_us);
                    self.verify_seq += 1;
                    self.verifying.insert(self.verify_seq, (message_id, propagation_source, slot, k, acc, kind, track));
                    self.queue.push(Reverse((done, Action::Validated(self.verify_seq))));
                    return;
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
                        T_MSG2 if message.data.len() >= 25 => self.record(slot, a, message.data[21], message.data[24] == 1),
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
                if self.me.nat && endpoint.is_listener() {
                    swarm.disconnect_peer_id(peer_id).ok(); // behind NAT: inbound never reaches the node
                    self.pm[2] += 1;
                    return;
                }
                if let Some(max) = self.me.peer_max.or(self.cfg.peer_max) {
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
            SwarmEvent::Behaviour(BehaviourEvent::Ping(libp2p::ping::Event { peer, result: Ok(rtt), .. })) => {
                emit(json!({"ev":"ping","node":self.me.id,"peer":self.peers.get(&peer),"rtt_ms":rtt.as_secs_f64() * 1e3,"t":now_s()}));
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

/// Gossipsub settings resolved for this node.
struct GsSetup {
    gs: GsCfg,
    no_forward: bool,
    home_hash: Option<gossipsub::TopicHash>,
    verify_ns_per_sig: u64,
    validating: bool,
}

fn gs_setup(cfg: &RunCfg, me: &NodeCfg) -> GsSetup {
    let gs = cfg.gs.clone().unwrap_or_default().over(&me.gs.clone().unwrap_or_default());
    let no_forward = gs.no_forward.unwrap_or(false);
    let home_hash = me.home.filter(|_| no_forward).map(|t| IdentTopic::new(topic_name(t)).hash());
    let verify_ns_per_sig = gs.verify_us_per_sig.unwrap_or(0) * 1000;
    // per-node publish files: always validate manually (verification delays, invalid messages)
    let validating = no_forward || verify_ns_per_sig > 0 || cfg.pub_dir.is_some();
    GsSetup { gs, no_forward, home_hash, verify_ns_per_sig, validating }
}

/// A fresh swarm: new gossipsub state (mesh, scores, caches, backoffs). Its metrics are registered in the same
/// registries as earlier swarms' (after a restart), so the summed counters stay cumulative.
fn build_swarm(cfg: &RunCfg, me: &NodeCfg, st: &GsSetup, registry: &mut prometheus_client::registry::Registry,
               gs_registry: &mut prometheus_client::registry::Registry, online: bool) -> Swarm<Behaviour> {
    let gs = &st.gs;
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
        .history_length(gs.history_length.unwrap_or(6))
        .history_gossip(gs.history_gossip.unwrap_or(3))
        .fanout_ttl(Duration::from_secs(60))
        .duplicate_cache_time(Duration::from_secs(60))
        .max_transmit_size(4 << 20)
        .flood_publish(gs.flood_publish.unwrap_or(false))
        .validation_mode(ValidationMode::Anonymous)
        // as Lighthouse (config.rs L528): with Anonymous authenticity, an echo of our own message would otherwise
        // count as an invalid SelfOrigin delivery (P4) against the honest peer that forwarded it
        .allow_self_origin(true)
        .message_id_fn(|m: &gossipsub::Message| MessageId::from(Sha256::digest(&m.data)[..20].to_vec()));
    if let Some(h) = &st.home_hash {
        gb.mesh_n_for_topic(gs.home_mesh_n.unwrap_or(8), h.clone())
            .mesh_n_low_for_topic(gs.home_mesh_n_low.unwrap_or(6), h.clone())
            .mesh_n_high_for_topic(gs.home_mesh_n_high.unwrap_or(12), h.clone())
            .mesh_outbound_min_for_topic(gs.home_mesh_outbound_min.unwrap_or(2), h.clone());
    }
    if st.validating {
        gb.validate_messages();
    }
    if let Some(m) = gs.iwant_promise_mode {
        gb.iwant_promise_mode(m);
    }
    let gcfg = gb.build().expect("gossipsub config");
    let mut gsb = gossipsub::Behaviour::new(MessageAuthenticity::Anonymous, gcfg).expect("gossipsub");
    if let Some(sc) = &cfg.scoring {
        let (mut params, thr) = eth_peer_score(sc, gs.mesh_n.unwrap_or(8), gs.p3_mode.unwrap_or(0));
        if let Some(w) = gs.slow_peer_weight {
            params.slow_peer_weight = w;
        }
        // This node's view, to check the per-client scoring: P3 weight, threshold and the cost of a full deficit
        // (topic_weight * weight * threshold^2) on PQ subnet 1, attestation subnet 0 and the block topic.
        let p3 = |t: u32| params.topics.get(&IdentTopic::new(topic_name(t)).hash()).map(|p| {
            let full = p.topic_weight * p.mesh_message_deliveries_weight * p.mesh_message_deliveries_threshold.powi(2);
            json!([p.mesh_message_deliveries_weight, p.mesh_message_deliveries_threshold, full])
        });
        emit(json!({"ev":"score_cfg","node":me.id,"slow_peer_weight":params.slow_peer_weight,"p3_pq":p3(1),
                    "p3_att":p3(200),"p3_block":p3(100),"iwant_promise_mode":gs.iwant_promise_mode.unwrap_or(0)}));
        gsb.with_peer_score(params, thr).expect("peer score params");
    }
    let gsb = gsb.with_metrics(gs_registry, Default::default());
    let ping = cfg.ping_s.map(|s| libp2p::ping::Behaviour::new(libp2p::ping::Config::new().with_interval(Duration::from_secs_f64(s))));

    let mut swarm = libp2p::SwarmBuilder::with_existing_identity(keypair(me.id))
        .with_tokio()
        .with_tcp(tcp::Config::default().nodelay(true), noise::Config::new, yamux::Config::default)
        .expect("tcp")
        .with_bandwidth_metrics(registry)
        .with_behaviour(|_| Behaviour {
            gossipsub: gsb,
            rr: request_response::Behaviour::new(
                [(StreamProtocol::new("/wb-pq/1"), ProtocolSupport::Full)],
                request_response::Config::default()
                    .with_request_timeout(Duration::from_secs(20))
                    .with_max_concurrent_streams(1024),
            ),
            ping: ping.into(),
        })
        .expect("behaviour")
        .with_swarm_config(|c| c.with_idle_connection_timeout(Duration::from_secs(3600)))
        .build();
    if !online {
        return swarm; // offline: not listening, no subscriptions
    }
    swarm.listen_on(addr(me)).expect("listen");
    if cfg.mode == Mode::Flood {
        for &t in me.topics.as_deref().unwrap_or(&[0]) {
            swarm.behaviour_mut().gossipsub.subscribe(&IdentTopic::new(topic_name(t))).unwrap();
        }
    }
    if cfg.mode == Mode::Gossip {
        for s in 0..cfg.subnets {
            swarm.behaviour_mut().gossipsub.subscribe(&IdentTopic::new(format!("votes_subnet_{s}"))).unwrap();
        }
    }
    if cfg.proofs == Proofs::Flood {
        swarm.behaviour_mut().gossipsub.subscribe(&IdentTopic::new("aggregate_and_proof")).unwrap();
    }
    swarm
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
    let st = gs_setup(&cfg, &me);
    // a node that joins later (offline from t = 0) starts without listening
    let online0 = !me.offline.iter().any(|&(a, b)| a <= 1.0 && b > 1.0);
    let mut swarm = build_swarm(&cfg, &me, &st, &mut registry, &mut gs_registry, online0);

    let vote_topics: Vec<IdentTopic> = if cfg.mode == Mode::Flood {
        (0..cfg.n_topics.unwrap_or(1)).map(|t| IdentTopic::new(topic_name(t))).collect()
    } else {
        (0..cfg.subnets).map(|s| IdentTopic::new(format!("votes_subnet_{s}"))).collect()
    };
    let agg_topic = IdentTopic::new("aggregate_and_proof");

    let peers: HashMap<PeerId, u32> = cfg.nodes.iter().map(|n| (keypair(n.id).public().to_peer_id(), n.id)).collect();
    let mut agg_peers: HashMap<u32, Vec<PeerId>> = HashMap::new();
    for n in cfg.nodes.iter().filter(|n| n.role == Role::Aggregator) {
        agg_peers.entry(n.topic).or_default().push(keypair(n.id).public().to_peer_id());
    }
    let n_aggs = agg_peers.values().map(|v| v.len()).sum();
    // flood mode has no proposer; any peer id will do
    let proposer = keypair(cfg.nodes.iter().find(|n| n.role == Role::Proposer).map_or(0, |n| n.id)).public().to_peer_id();
    let workers = me.workers.unwrap_or(1).max(1);
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
        no_forward: st.no_forward,
        home_hash: st.home_hash.clone(),
        verify_ns_per_sig: st.verify_ns_per_sig,
        validating: st.validating,
        verifying: HashMap::new(),
        verify_seq: 0,
        vstat: [0; 3],
        verify_free: vec![0; workers],
        my_pubs: vec![],
        rxbg: HashMap::new(),
        online: online0,
        pm_last: 0.0,
        failed: [0; 4],
        stale: [0; 2],
        dialing: HashMap::new(),
        pm: [0; 6],
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
                                ("stale_pq", node.stale[0]), ("stale_bg", node.stale[1]),
                                ("f_publish", node.failed[0]), ("f_forward", node.failed[1]),
                                ("f_queue_full", node.failed[2]), ("f_timeout", node.failed[3]),
                                ("pm_dials", node.pm[0]), ("pm_prunes", node.pm[1]), ("pm_refused", node.pm[2]),
                                ("pm_churned", node.pm[3]), ("pm_score_dc", node.pm[4]), ("pm_restarts", node.pm[5]),
                                ("online", node.online as u64), ("v_n", node.vstat[0]), ("v_us", node.vstat[1]),
                                ("v_max_us", node.vstat[2])] {
                                ev.insert(k.into(), json!(v));
                            }
                            ev.insert("ev".into(), json!("tick"));
                            ev.insert("t".into(), json!((now_s() * 1e3).round() / 1e3));
                            emit(serde_json::Value::Object(ev));
                            continue;
                        }
                        // churn: the old swarm is dropped (connections close, gossipsub state is lost)
                        Action::GoOffline => {
                            if node.online {
                                swarm = build_swarm(&node.cfg, &node.me, &st, &mut registry, &mut gs_registry, false);
                                node.online = false;
                                node.verifying.clear();
                                node.dialing.clear();
                                node.pm[5] += 1;
                                emit(json!({"ev":"offline","node":id,"t":now_s()}));
                            }
                            continue;
                        }
                        Action::GoOnline => {
                            if !node.online {
                                swarm = build_swarm(&node.cfg, &node.me, &st, &mut registry, &mut gs_registry, true);
                                node.online = true;
                                node.verify_free.iter_mut().for_each(|x| *x = 0);
                                emit(json!({"ev":"online","node":id,"t":now_s()}));
                                node.schedule(now_s() + 0.1, Action::PeerManager);
                            }
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
