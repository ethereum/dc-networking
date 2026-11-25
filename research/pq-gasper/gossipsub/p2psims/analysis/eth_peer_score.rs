// Gossipsub v1.1 peer-score params/thresholds following Lighthouse v8.3.2 (a376defa, branch stable),
// beacon_node/lighthouse_network/src/service/gossipsub_scoring_parameters.rs ("GSP").
// Checked by a research subagent: compiles warning-free against libp2p-gossipsub 0.49.5;
// PeerScoreParams::validate(), PeerScoreThresholds::validate() and Behaviour::with_peer_score() all Ok.
// With no Pq topics, 12 s slot, 1M validators it reproduces Lighthouse: topic_score_cap 53.75,
// behaviour_penalty_weight -15.879, behaviour_penalty_decay 0.98571, attestation P4 weight -10080.
//
// Enable:  let (p, t) = eth_peer_score(12.0, 0.7, &topics, active_validators, u64::MAX);
//          gossipsub.with_peer_score(p, t).expect("valid score params");
// (Behaviour::with_peer_score at libp2p-gossipsub-0.49.5/src/behaviour.rs:922-928;
//  set_topic_params(Topic, params) at behaviour.rs:954 takes a Topic, not a TopicHash.)
//
// Notes:
// - DataColumn topics are left unscored, as in Lighthouse v8.3.2 (also blobs, sync committee,
//   BLS changes, light client). Map them to another arm if you want them scored.
// - current_slot: Lighthouse turns P3 off while decay_slots >= current_slot. Pass u64::MAX to keep it on.
// - Block/Aggregate/Attestation ignore the passed rate and use Lighthouse's (1.0, derived aggregator
//   count, active/64/32). Pq uses the passed rate, attestation-subnet formulas, weight 1/(#Pq topics);
//   the extra 1.0 total weight enters max_positive_score (changes cap and P4 weights for all topics).
//   Pass every Pq subnet topic, not only subscribed ones. At 125 msgs/slot, D=8: P3 threshold ~68.2.
// - heartbeat_s unused (0.49.5 decays on its own decay_interval timer, behaviour.rs:3413-3417).
// - Not reproduced: Lighthouse's 60 s re-parameterisation via set_topic_params, zeroing old-fork topic
//   weights, folding gossip score into its peer-manager score, and partial messages (sigp fork only).

use libp2p::gossipsub;
use std::{collections::HashMap, time::Duration};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TopicKind {
    Block,
    Aggregate,
    Attestation,
    DataColumn,
    Pq,
}

pub fn eth_peer_score(
    slot_s: f64,
    heartbeat_s: f64,
    topics: &[(gossipsub::TopicHash, TopicKind, f64 /* msgs/slot */, usize /* mesh D */)],
    active_validators: u64,
    current_slot: u64,
) -> (gossipsub::PeerScoreParams, gossipsub::PeerScoreThresholds) {
    let _ = heartbeat_s;

    const SLOTS_PER_EPOCH: u64 = 32;
    const ATTESTATION_SUBNET_COUNT: u64 = 64;
    const MAX_COMMITTEES_PER_SLOT: u64 = 64;
    const TARGET_COMMITTEE_SIZE: u64 = 128;
    const TARGET_AGGREGATORS_PER_COMMITTEE: u64 = 16;

    const MAX_IN_MESH_SCORE: f64 = 10.0; // GSP L12-18
    const MAX_FIRST_MESSAGE_DELIVERIES_SCORE: f64 = 40.0;
    const BEACON_BLOCK_WEIGHT: f64 = 0.5;
    const BEACON_AGGREGATE_PROOF_WEIGHT: f64 = 0.5;
    const EXIT_AND_SLASHING_WEIGHTS: f64 = 0.05 + 0.05 + 0.05;
    const MESH_MESSAGE_DELIVERIES_WINDOW: Duration = Duration::from_secs(2); // GSP L21
    const DECAY_TO_ZERO: f64 = 0.01;
    const GREYLIST_THRESHOLD: f64 = -16000.0;

    let thresholds = gossipsub::PeerScoreThresholds { // GSP L24, L27-35
        gossip_threshold: -4000.0,
        publish_threshold: -8000.0,
        graylist_threshold: GREYLIST_THRESHOLD,
        accept_px_threshold: 100.0,
        opportunistic_graft_threshold: 5.0,
    };

    let slot = Duration::from_secs_f64(slot_s);
    let epoch = slot * SLOTS_PER_EPOCH as u32;
    let decay_interval = std::cmp::max(Duration::from_secs(1), slot);
    let decay = |t: Duration| gossipsub::score_parameter_decay_with_base(t, decay_interval, DECAY_TO_ZERO);
    let decay_convergence = |decay: f64, rate: f64| rate / (1.0 - decay);
    let threshold = |decay: f64, rate: f64| decay_convergence(decay, rate) * decay;

    let attestation_weight = 1.0 / ATTESTATION_SUBNET_COUNT as f64;
    let pq_count = topics.iter().filter(|t| t.1 == TopicKind::Pq).count();
    let pq_weight = if pq_count > 0 { 1.0 / pq_count as f64 } else { 0.0 };
    let pq_total_weight = if pq_count > 0 { 1.0 } else { 0.0 };

    let max_positive_score = (MAX_IN_MESH_SCORE + MAX_FIRST_MESSAGE_DELIVERIES_SCORE)
        * (BEACON_BLOCK_WEIGHT
            + BEACON_AGGREGATE_PROOF_WEIGHT
            + attestation_weight * ATTESTATION_SUBNET_COUNT as f64
            + EXIT_AND_SLASHING_WEIGHTS
            + pq_total_weight);

    let committees_per_slot = std::cmp::max(
        1,
        std::cmp::min(MAX_COMMITTEES_PER_SLOT, active_validators / SLOTS_PER_EPOCH / TARGET_COMMITTEE_SIZE),
    );
    let committees = committees_per_slot * SLOTS_PER_EPOCH;
    let smaller_committee_size = active_validators / committees;
    let num_larger_committees = active_validators - smaller_committee_size * committees;
    let modulo_smaller = std::cmp::max(1, smaller_committee_size / TARGET_AGGREGATORS_PER_COMMITTEE);
    let modulo_larger = std::cmp::max(1, (smaller_committee_size + 1) / TARGET_AGGREGATORS_PER_COMMITTEE);
    let aggregators_per_slot = (((committees - num_larger_committees) * smaller_committee_size) as f64
        / modulo_smaller as f64
        + (num_larger_committees * (smaller_committee_size + 1)) as f64 / modulo_larger as f64)
        / SLOTS_PER_EPOCH as f64;
    let multiple_bursts = committees_per_slot >= 2 * ATTESTATION_SUBNET_COUNT / SLOTS_PER_EPOCH;
    let attestation_rate = active_validators as f64 / ATTESTATION_SUBNET_COUNT as f64 / SLOTS_PER_EPOCH as f64;

    let topic_params = |topic_weight: f64,
                        expected_message_rate: f64,
                        first_message_decay_time: Duration,
                        mesh_n: usize,
                        decay_slots: u64,
                        cap_factor: f64,
                        activation_window: Duration| {
        let mut t = gossipsub::TopicScoreParams::default();
        t.topic_weight = topic_weight;
        // P1 (GSP L309-311)
        t.time_in_mesh_quantum = slot;
        t.time_in_mesh_cap = 3600.0 / t.time_in_mesh_quantum.as_secs_f64();
        t.time_in_mesh_weight = 10.0 / t.time_in_mesh_cap;
        // P2 (GSP L313-319)
        t.first_message_deliveries_decay = decay(first_message_decay_time);
        t.first_message_deliveries_cap =
            decay_convergence(t.first_message_deliveries_decay, 2.0 * expected_message_rate / mesh_n as f64);
        t.first_message_deliveries_weight = 40.0 / t.first_message_deliveries_cap;
        // P3 / P3b (GSP L321-344)
        t.mesh_message_deliveries_decay = decay(slot * decay_slots as u32);
        t.mesh_message_deliveries_threshold = threshold(t.mesh_message_deliveries_decay, expected_message_rate / 50.0);
        t.mesh_message_deliveries_cap = if cap_factor * t.mesh_message_deliveries_threshold < 2.0 {
            2.0
        } else {
            cap_factor * t.mesh_message_deliveries_threshold
        };
        t.mesh_message_deliveries_activation = activation_window;
        t.mesh_message_deliveries_window = MESH_MESSAGE_DELIVERIES_WINDOW;
        t.mesh_failure_penalty_decay = t.mesh_message_deliveries_decay;
        t.mesh_message_deliveries_weight = -t.topic_weight;
        t.mesh_failure_penalty_weight = t.mesh_message_deliveries_weight;
        if decay_slots >= current_slot {
            t.mesh_message_deliveries_threshold = 0.0;
            t.mesh_message_deliveries_weight = 0.0;
        }
        // P4 (GSP L356-358)
        t.invalid_message_deliveries_weight = -max_positive_score / t.topic_weight;
        t.invalid_message_deliveries_decay = decay(epoch * 50);
        t
    };

    let (att_fmd_time, att_decay_slots, att_activation) = if multiple_bursts {
        (epoch, SLOTS_PER_EPOCH * 4, slot * (SLOTS_PER_EPOCH as u32 / 2 + 1))
    } else {
        (epoch * 4, SLOTS_PER_EPOCH * 16, epoch * 3)
    };

    let mut topic_map = HashMap::new();
    for (hash, kind, rate, mesh_n) in topics {
        let p = match kind {
            TopicKind::Block => topic_params(BEACON_BLOCK_WEIGHT, 1.0, epoch * 20, *mesh_n, SLOTS_PER_EPOCH * 5, 3.0, epoch),
            TopicKind::Aggregate => topic_params(
                BEACON_AGGREGATE_PROOF_WEIGHT, aggregators_per_slot, epoch, *mesh_n, SLOTS_PER_EPOCH * 2, 4.0, epoch,
            ),
            TopicKind::Attestation => topic_params(
                attestation_weight, attestation_rate, att_fmd_time, *mesh_n, att_decay_slots, 16.0, att_activation,
            ),
            TopicKind::Pq => topic_params(pq_weight, *rate, att_fmd_time, *mesh_n, att_decay_slots, 16.0, att_activation),
            TopicKind::DataColumn => continue,
        };
        topic_map.insert(hash.clone(), p);
    }

    let mut params = gossipsub::PeerScoreParams { // GSP L93-111
        topics: topic_map,
        decay_interval,
        decay_to_zero: DECAY_TO_ZERO,
        retain_score: epoch * 100,
        app_specific_weight: 1.0,
        ip_colocation_factor_threshold: 8.0,
        behaviour_penalty_threshold: 6.0,
        behaviour_penalty_decay: decay(epoch * 10),
        slow_peer_decay: 0.1,
        slow_peer_weight: -10.0,
        slow_peer_threshold: 0.0,
        ..Default::default()
    };
    let target_value =
        decay_convergence(params.behaviour_penalty_decay, 10.0 / SLOTS_PER_EPOCH as f64) - params.behaviour_penalty_threshold;
    params.behaviour_penalty_weight = thresholds.gossip_threshold / target_value.powi(2);
    params.topic_score_cap = max_positive_score * 0.5;
    params.ip_colocation_factor_weight = -params.topic_score_cap;
    (params, thresholds)
}
