#!/usr/bin/env python3
"""
anchor_check.py -- Lane C (RQ4): index set, anchor and bit layout for staggered FG committees.

A faithful, scaled-down re-implementation of every consensus-specs code path that writes
activation_epoch / exit_epoch (and the paths that grow or rewrite the registry) evolves a
synthetic registry along a common chain to a target block T and then along four branches
that descend from T:

  A  healthy DC finality (one finalization per round), exits, a slashing, a consolidation,
     new deposits, an EL full exit;
  B  finality stalls at T, different exits, two slashings, balance drains that trigger
     ejections, a different consolidation, deposits that never become processable, and four
     empty epochs;
  C  identical to A (same blocks, same finality) plus ONE extra voluntary exit right after T;
  D  identical to A plus EIP-6914 index reuse and extra deposits that reuse indices.

It then checks:

  [H2]  every observed change of activation_epoch / exit_epoch goes FAR_FUTURE -> v with
        v >= c + 1 + MAX_SEED_LOOKAHEAD, c the current epoch at the write (diffed state
        snapshots, independent of the transcription), and the bound is attained;
  [R]   the recommended rule  I(r) = Active(E), E = compute_epoch_at_round(r), keyed by
        (E, D(E)), D(E) = block root at slot compute_start_slot_at_epoch(E - 4) - 1,
        gives ONE index set and ONE bit layout per (branch, epoch) across all states of a
        branch, and IDENTICAL sets and layouts on every pair of branches sharing D(E);
  [O2a] Francesco's Active(epoch(T.slot)) is identical in every state descending from T;
  [O4]  Mikhail's finalized-epoch rule (DC-spec get_beacon_committee) diverges: across
        branches with different finality, across branches with IDENTICAL finality (registry
        length), and along a single chain inside one round and across an epoch boundary;
        and DC-spec is_valid_aggregation_bits rejects a whole aggregate for one bit of a
        validator that exited between vote and inclusion ("poison bit");
  [O3]  Roberto's finalized anchor changes inside nearly every round's inclusion window;
  [6914] index reuse leaves the voting window untouched but rewrites far-past sets and
        index->pubkey;
  [gen] genesis: Active(e) for e <= 4 is the genesis set;
  and prints the mainnet-scale numbers quoted in analysis/anchor.md (churn, O5 lag costs,
  O1 waste from cited registry counts, cache sizes, finality-lag threshold).

Citations: ethereum/consensus-specs @ a7ab94b (2026-04-24); "DC-spec" = Mikhail Kalinin's
mkalinin/eth2.0-specs dc-feature specs/_features/decoupled-consensus/beacon-chain.md as
fetched 2026-10-02 (line numbers of that copy); EIP-8061 from ethereum/EIPs.

Stdlib only, deterministic.  Run:  python3 sim/anchor_check.py
"""
import bisect
import hashlib
import random
import sys
from array import array

# ---------------------------------------------------------------------------
# Constants (mainnet values)
# ---------------------------------------------------------------------------
ETH = 10**9                                       # Gwei per ETH
FAR_FUTURE_EPOCH = 2**64 - 1
SLOTS_PER_EPOCH = 32
GENESIS_EPOCH = 0                                 # phase0/beacon-chain.md:190
MAX_SEED_LOOKAHEAD = 4                            # phase0/beacon-chain.md:266
MIN_VALIDATOR_WITHDRAWABILITY_DELAY = 256         # phase0/beacon-chain.md:338
SHARD_COMMITTEE_PERIOD = 256                      # phase0/beacon-chain.md:339
EPOCHS_PER_SLASHINGS_VECTOR = 8192                # phase0/beacon-chain.md:276
EFFECTIVE_BALANCE_INCREMENT = 1 * ETH             # phase0/beacon-chain.md:257
HYSTERESIS_QUOTIENT = 4                           # phase0/beacon-chain.md:239
HYSTERESIS_DOWNWARD_MULTIPLIER = 1                # phase0/beacon-chain.md:240
HYSTERESIS_UPWARD_MULTIPLIER = 5                  # phase0/beacon-chain.md:241
EJECTION_BALANCE = 16 * ETH                       # phase0/beacon-chain.md:346
CHURN_LIMIT_QUOTIENT = 2**16                      # phase0/beacon-chain.md:348
SLOTS_PER_HISTORICAL_ROOT = 8192                  # phase0/beacon-chain.md:269
MIN_ACTIVATION_BALANCE = 32 * ETH                 # electra/beacon-chain.md:161
MAX_EFFECTIVE_BALANCE_ELECTRA = 2048 * ETH        # electra/beacon-chain.md:162
MIN_SLASHING_PENALTY_QUOTIENT_ELECTRA = 4096      # electra/beacon-chain.md:168
MAX_PENDING_DEPOSITS_PER_EPOCH = 16               # electra/beacon-chain.md:204
MIN_PER_EPOCH_CHURN_LIMIT_ELECTRA = 128 * ETH     # electra/beacon-chain.md:218
MAX_PER_EPOCH_ACTIVATION_EXIT_CHURN_LIMIT = 256 * ETH  # electra/beacon-chain.md:219
CHURN_LIMIT_QUOTIENT_GLOAS = 2**15                # EIPs/EIPS/eip-8061.md:43
CONSOLIDATION_CHURN_LIMIT_QUOTIENT = 2**16        # eip-8061.md:44
MAX_PER_EPOCH_ACTIVATION_CHURN_LIMIT = 256 * ETH  # eip-8061.md:45
SAFE_EPOCHS_TO_REUSE_INDEX = 2**16                # _features/eip6914/beacon-chain.md:34
SLOTS_PER_ROUND = 8                               # DC-spec:295
COMMITTEES_PER_ROUND = 2048                       # DC-spec:282

# Recommended layout parameters (Lane A picks the schedule, Lane B the subnet count).
FG_COHORTS_PER_ROUND = 23                         # C (Q17 grid); also checked for 8, 11, 22
FG_SUBNETS_PER_COHORT = 4                         # S (sim scale; Lane B sizes this)
FG_ROTATION_PERIOD_ROUNDS = 10                    # K (slow +1 rotation; Lane A)
FG_ERA_EPOCHS = 4                                 # era length for the era-hash variant (sim scale)
FG_ANCHOR_LOOKBACK = 1 + MAX_SEED_LOOKAHEAD       # = 5 epochs

CHURN_MODE = "eip8061"   # DC-spec:1053 calls get_activation_churn_limit (EIP-8061)

SEED = 20261002
N_REGISTRY = 12_000
E0 = 70_000              # large enough that EIP-6914 reuse can trigger (> 65,536 + withdrawable)
COMMON_EPOCHS = 8        # target T sits in epoch E0 + 8
BRANCH_EPOCHS = 12       # branches run through epoch E0 + 8 + 12

FAILURES = []


def check(cond, msg):
    if not cond:
        FAILURES.append(msg)
        print("  FAIL:", msg)
    return cond


# ---------------------------------------------------------------------------
# Time helpers (phase0/beacon-chain.md:893-917, DC-spec:805-830)
# ---------------------------------------------------------------------------
def compute_epoch_at_slot(slot):
    return slot // SLOTS_PER_EPOCH


def compute_start_slot_at_epoch(epoch):
    return epoch * SLOTS_PER_EPOCH


def compute_activation_exit_epoch(epoch):        # phase0/beacon-chain.md:913-917
    return epoch + 1 + MAX_SEED_LOOKAHEAD


def compute_round_at_slot(slot):                 # DC-spec:805-809
    return slot // SLOTS_PER_ROUND


def compute_start_slot_at_round(rnd):            # DC-spec:815-819
    return rnd * SLOTS_PER_ROUND


def compute_epoch_at_round(rnd):                 # DC-spec:825-830
    return compute_epoch_at_slot(compute_start_slot_at_round(rnd))


# ---------------------------------------------------------------------------
# State model
# ---------------------------------------------------------------------------
class Validator:
    __slots__ = ("pubkey", "compounding", "effective_balance", "slashed",
                 "activation_eligibility_epoch", "activation_epoch", "exit_epoch",
                 "withdrawable_epoch")

    def __init__(self, pubkey, compounding, effective_balance, slashed=False,
                 elig=FAR_FUTURE_EPOCH, act=FAR_FUTURE_EPOCH, exit_=FAR_FUTURE_EPOCH,
                 wd=FAR_FUTURE_EPOCH):
        self.pubkey = pubkey
        self.compounding = compounding
        self.effective_balance = effective_balance
        self.slashed = slashed
        self.activation_eligibility_epoch = elig
        self.activation_epoch = act
        self.exit_epoch = exit_
        self.withdrawable_epoch = wd

    def clone(self):
        v = Validator.__new__(Validator)
        for k in Validator.__slots__:
            setattr(v, k, getattr(self, k))
        return v


class State:
    def __init__(self):
        self.slot = 0
        self.validators = []
        self.balances = []
        self.pubkey_index = {}
        self.pending_deposits = []        # [pubkey, compounding, amount, slot]
        self.pending_consolidations = []  # (source, target)
        self.deposit_balance_to_consume = 0
        self.exit_balance_to_consume = 0
        self.earliest_exit_epoch = 0
        self.consolidation_balance_to_consume = 0
        self.earliest_consolidation_epoch = 0
        self.finalized_slot = 0           # DC-spec:462
        self.chain_slots = []             # slots of this branch's blocks, ascending
        self.chain_roots = []
        self.eip6914 = False
        self.tab_cache = None
        self.reuse_log = []

    def clone(self):
        s = State.__new__(State)
        s.__dict__.update(self.__dict__)
        s.validators = [v.clone() for v in self.validators]
        s.balances = list(self.balances)
        s.pubkey_index = dict(self.pubkey_index)
        s.pending_deposits = [list(d) for d in self.pending_deposits]
        s.pending_consolidations = list(self.pending_consolidations)
        s.chain_slots = list(self.chain_slots)
        s.chain_roots = list(self.chain_roots)
        s.reuse_log = list(self.reuse_log)
        s.tab_cache = None
        return s


def get_current_epoch(st):
    return compute_epoch_at_slot(st.slot)


def is_active_validator(v, epoch):               # phase0/beacon-chain.md:698-702
    return v.activation_epoch <= epoch < v.exit_epoch


def get_active_validator_indices(st, epoch):     # phase0/beacon-chain.md:1027-1033
    return [i for i, v in enumerate(st.validators)
            if v.activation_epoch <= epoch < v.exit_epoch]


def is_slashable_validator(v, epoch):            # phase0/beacon-chain.md:736-742
    return (not v.slashed) and (v.activation_epoch <= epoch < v.withdrawable_epoch)


def get_total_active_balance(st):
    e = get_current_epoch(st)
    if st.tab_cache is not None and st.tab_cache[0] == e:
        return st.tab_cache[1]
    tab = sum(v.effective_balance for v in st.validators
              if v.activation_epoch <= e < v.exit_epoch)
    tab = max(EFFECTIVE_BALANCE_INCREMENT, tab)
    st.tab_cache = (e, tab)
    return tab


def root_index_at(st, slot):
    """Index into the branch's block list of the latest block with slot <= ``slot``."""
    return bisect.bisect_right(st.chain_slots, slot) - 1


def get_block_root_at_slot(st, slot):            # phase0/beacon-chain.md:1006-1011 semantics
    assert slot < st.slot <= slot + SLOTS_PER_HISTORICAL_ROOT
    i = root_index_at(st, slot)
    return st.chain_roots[max(i, 0)]


def block_slot_at(st, slot):
    i = root_index_at(st, slot)
    return st.chain_slots[max(i, 0)]


# ---------------------------------------------------------------------------
# Churn (electra/beacon-chain.md:608-632; eip-8061.md:52-78)
# ---------------------------------------------------------------------------
def _round_down(x):
    return x - x % EFFECTIVE_BALANCE_INCREMENT


def churn_limits(tab, mode):
    """(activation, exit, consolidation) churn in Gwei for total active balance ``tab``."""
    if mode == "electra":
        balance = _round_down(max(MIN_PER_EPOCH_CHURN_LIMIT_ELECTRA, tab // CHURN_LIMIT_QUOTIENT))
        act_exit = min(MAX_PER_EPOCH_ACTIVATION_EXIT_CHURN_LIMIT, balance)
        return act_exit, act_exit, balance - act_exit
    churn = _round_down(max(MIN_PER_EPOCH_CHURN_LIMIT_ELECTRA, tab // CHURN_LIMIT_QUOTIENT_GLOAS))
    return (min(MAX_PER_EPOCH_ACTIVATION_CHURN_LIMIT, churn), churn,
            _round_down(tab // CONSOLIDATION_CHURN_LIMIT_QUOTIENT))


def get_activation_churn_limit(st):
    return churn_limits(get_total_active_balance(st), CHURN_MODE)[0]


def get_exit_churn_limit(st):
    return churn_limits(get_total_active_balance(st), CHURN_MODE)[1]


def get_consolidation_churn_limit(st):
    return churn_limits(get_total_active_balance(st), CHURN_MODE)[2]


def compute_exit_epoch_and_update_churn(st, exit_balance):   # electra:770-792, eip-8061:169-193
    earliest = max(st.earliest_exit_epoch, compute_activation_exit_epoch(get_current_epoch(st)))
    per_epoch = get_exit_churn_limit(st)
    if st.earliest_exit_epoch < earliest:
        to_consume = per_epoch
    else:
        to_consume = st.exit_balance_to_consume
    if exit_balance > to_consume:
        bal = exit_balance - to_consume
        add = (bal - 1) // per_epoch + 1
        earliest += add
        to_consume += add * per_epoch
    st.exit_balance_to_consume = to_consume - exit_balance
    st.earliest_exit_epoch = earliest
    return st.earliest_exit_epoch


def compute_consolidation_epoch_and_update_churn(st, balance):  # electra:798-824
    earliest = max(st.earliest_consolidation_epoch,
                   compute_activation_exit_epoch(get_current_epoch(st)))
    per_epoch = get_consolidation_churn_limit(st)
    if st.earliest_consolidation_epoch < earliest:
        to_consume = per_epoch
    else:
        to_consume = st.consolidation_balance_to_consume
    if balance > to_consume:
        bal = balance - to_consume
        add = (bal - 1) // per_epoch + 1
        earliest += add
        to_consume += add * per_epoch
    st.consolidation_balance_to_consume = to_consume - balance
    st.earliest_consolidation_epoch = earliest
    return st.earliest_consolidation_epoch


# ---------------------------------------------------------------------------
# Mutators and operations
# ---------------------------------------------------------------------------
def initiate_validator_exit(st, index):          # electra:717-731
    v = st.validators[index]
    if v.exit_epoch != FAR_FUTURE_EPOCH:
        return
    v.exit_epoch = compute_exit_epoch_and_update_churn(st, v.effective_balance)
    v.withdrawable_epoch = v.exit_epoch + MIN_VALIDATOR_WITHDRAWABILITY_DELAY


def slash_validator(st, index):                  # electra:834-852 (rewards omitted: balances only)
    epoch = get_current_epoch(st)
    initiate_validator_exit(st, index)
    v = st.validators[index]
    v.slashed = True
    v.withdrawable_epoch = max(v.withdrawable_epoch, epoch + EPOCHS_PER_SLASHINGS_VECTOR)
    st.balances[index] = max(0, st.balances[index]
                             - v.effective_balance // MIN_SLASHING_PENALTY_QUOTIENT_ELECTRA)


def op_voluntary_exit(st, index):                # electra:1706-1727 / gloas:1493-1505
    v = st.validators[index]
    c = get_current_epoch(st)
    if not (is_active_validator(v, c) and v.exit_epoch == FAR_FUTURE_EPOCH
            and c >= v.activation_epoch + SHARD_COMMITTEE_PERIOD):
        return False
    initiate_validator_exit(st, index)
    return True


def op_el_full_exit(st, index):                  # electra:1735-1777 (full-exit branch)
    return op_voluntary_exit(st, index)


def op_attester_slashing(st, index):             # phase0:1970-1983 / DC-spec:1265-1278
    if is_slashable_validator(st.validators[index], get_current_epoch(st)):
        slash_validator(st, index)
        return True
    return False


def op_deposit_request(st, pubkey, compounding, amount):   # electra:1809-; gloas:1452-1461
    st.pending_deposits.append([pubkey, compounding, amount, st.slot])


def op_consolidation_request(st, src, tgt):     # electra:1869-1941 (pubkey/credential checks elided)
    if src == tgt or get_consolidation_churn_limit(st) <= MIN_ACTIVATION_BALANCE:
        return False
    s, t = st.validators[src], st.validators[tgt]
    c = get_current_epoch(st)
    if not t.compounding:
        return False
    if not (is_active_validator(s, c) and is_active_validator(t, c)):
        return False
    if s.exit_epoch != FAR_FUTURE_EPOCH or t.exit_epoch != FAR_FUTURE_EPOCH:
        return False
    if c < s.activation_epoch + SHARD_COMMITTEE_PERIOD:
        return False
    s.exit_epoch = compute_consolidation_epoch_and_update_churn(st, s.effective_balance)
    s.withdrawable_epoch = s.exit_epoch + MIN_VALIDATOR_WITHDRAWABILITY_DELAY
    st.pending_consolidations.append((src, tgt))
    return True


def op_drain(st, index, new_balance):
    """NOT a spec function: stand-in for the (TODO, DC-spec:102) inactivity leak, which only
    lowers balances; the ejection then happens through the spec's own registry update."""
    st.balances[index] = min(st.balances[index], new_balance)


# ---------------------------------------------------------------------------
# Registry growth (altair:246-258, electra:1575-1615, eip6914:43-62, DC-spec:1243-1258)
# ---------------------------------------------------------------------------
def get_index_for_new_validator(st):
    if st.eip6914:
        c = get_current_epoch(st)
        for i, v in enumerate(st.validators):
            if c > v.withdrawable_epoch + SAFE_EPOCHS_TO_REUSE_INDEX and st.balances[i] == 0:
                return i
    return len(st.validators)


def add_validator_to_registry(st, pubkey, compounding, amount):
    index = get_index_for_new_validator(st)
    max_eb = MAX_EFFECTIVE_BALANCE_ELECTRA if compounding else MIN_ACTIVATION_BALANCE
    v = Validator(pubkey, compounding, min(amount - amount % EFFECTIVE_BALANCE_INCREMENT, max_eb))
    if index == len(st.validators):
        st.validators.append(v)
        st.balances.append(amount)
    else:
        old = st.validators[index]
        st.reuse_log.append((index, old.pubkey, pubkey, get_current_epoch(st),
                             old.activation_epoch, old.exit_epoch, old.withdrawable_epoch))
        del st.pubkey_index[old.pubkey]
        st.validators[index] = v
        st.balances[index] = amount
    st.pubkey_index[pubkey] = index


def apply_pending_deposit(st, dep):              # electra:960-976 (signatures assumed valid)
    pubkey, compounding, amount, _ = dep
    if pubkey not in st.pubkey_index:
        add_validator_to_registry(st, pubkey, compounding, amount)
    else:
        st.balances[st.pubkey_index[pubkey]] += amount


# ---------------------------------------------------------------------------
# Epoch processing, in DC-spec:1006-1030 / gloas:864-884 order
# ---------------------------------------------------------------------------
def dc_finalized_epoch(st):
    return compute_epoch_at_slot(st.finalized_slot)


def process_registry_updates(st):                # electra:909-925
    c = get_current_epoch(st)
    activation_epoch = compute_activation_exit_epoch(c)
    # is_eligible_for_activation (phase0:721-730) compares against the finalized epoch.  The
    # DC spec never updates state.finalized_checkpoint (DC-spec:1008 drops
    # process_justification_and_finalization), so as written no post-fork validator would ever
    # activate; we use the evident intent, epoch(state.finalized_slot) (cf. DC-spec:1062).
    fin = dc_finalized_epoch(st)
    for i, v in enumerate(st.validators):
        if v.activation_eligibility_epoch == FAR_FUTURE_EPOCH and \
                v.effective_balance >= MIN_ACTIVATION_BALANCE:          # electra:480-488
            v.activation_eligibility_epoch = c + 1
        elif is_active_validator(v, c) and v.effective_balance <= EJECTION_BALANCE:
            initiate_validator_exit(st, i)
        elif v.activation_eligibility_epoch <= fin and v.activation_epoch == FAR_FUTURE_EPOCH:
            v.activation_epoch = activation_epoch


def process_pending_deposits(st):                # DC-spec:1050-1104 (= eip-8061:105-161 + finalized_slot)
    next_epoch = get_current_epoch(st) + 1
    available = st.deposit_balance_to_consume + get_activation_churn_limit(st)
    processed = 0
    nxt = 0
    postpone = []
    reached = False
    for dep in st.pending_deposits:
        if dep[3] > st.finalized_slot:           # DC-spec:1062
            break
        if nxt >= MAX_PENDING_DEPOSITS_PER_EPOCH:
            break
        exited = withdrawn = False
        idx = st.pubkey_index.get(dep[0])
        if idx is not None:
            v = st.validators[idx]
            exited = v.exit_epoch < FAR_FUTURE_EPOCH
            withdrawn = v.withdrawable_epoch < next_epoch
        if withdrawn:
            apply_pending_deposit(st, dep)
        elif exited:
            postpone.append(dep)                 # DC-spec:1081-1083
        else:
            reached = processed + dep[2] > available
            if reached:
                break
            processed += dep[2]
            apply_pending_deposit(st, dep)
        nxt += 1
    st.pending_deposits = st.pending_deposits[nxt:] + postpone
    st.deposit_balance_to_consume = available - processed if reached else 0


def process_pending_consolidations(st):          # electra:1060-1081
    next_epoch = get_current_epoch(st) + 1
    k = 0
    for src, tgt in st.pending_consolidations:
        s = st.validators[src]
        if s.slashed:
            k += 1
            continue
        if s.withdrawable_epoch > next_epoch:
            break
        amt = min(st.balances[src], s.effective_balance)
        st.balances[src] -= amt
        st.balances[tgt] += amt
        k += 1
    st.pending_consolidations = st.pending_consolidations[k:]


def process_effective_balance_updates(st):       # electra:1090-1106
    inc = EFFECTIVE_BALANCE_INCREMENT // HYSTERESIS_QUOTIENT
    down, up = inc * HYSTERESIS_DOWNWARD_MULTIPLIER, inc * HYSTERESIS_UPWARD_MULTIPLIER
    for i, v in enumerate(st.validators):
        bal = st.balances[i]
        max_eb = MAX_EFFECTIVE_BALANCE_ELECTRA if v.compounding else MIN_ACTIVATION_BALANCE
        if bal + down < v.effective_balance or v.effective_balance + up < bal:
            v.effective_balance = min(bal - bal % EFFECTIVE_BALANCE_INCREMENT, max_eb)


# --- H2: independent diff check of every lifecycle change -------------------
H2 = {"activation_writes": 0, "exit_writes": 0, "new_entries": 0, "reuses": 0,
      "tight_activation": None, "tight_exit": None, "min_margin": None}


def lifecycle_snapshot(st):
    return ([v.activation_epoch for v in st.validators], [v.exit_epoch for v in st.validators],
            [v.pubkey for v in st.validators])


def check_h2(st, before, c, where):
    acts0, exits0, pks0 = before
    for i, v in enumerate(st.validators):
        if i >= len(acts0):
            H2["new_entries"] += 1
            check(v.activation_epoch == FAR_FUTURE_EPOCH and v.exit_epoch == FAR_FUTURE_EPOCH,
                  f"H2: new entry {i} not FAR_FUTURE ({where})")
            continue
        if v.pubkey != pks0[i]:                  # EIP-6914 overwrite of a whole record
            H2["reuses"] += 1
            check(v.activation_epoch == FAR_FUTURE_EPOCH and v.exit_epoch == FAR_FUTURE_EPOCH,
                  f"H2: reused entry {i} not FAR_FUTURE")
            check(exits0[i] + MIN_VALIDATOR_WITHDRAWABILITY_DELAY + SAFE_EPOCHS_TO_REUSE_INDEX < c,
                  f"H2: reuse of {i} inside the safety window")
            continue
        for name, old, new in (("activation", acts0[i], v.activation_epoch),
                               ("exit", exits0[i], v.exit_epoch)):
            if old == new:
                continue
            H2[name + "_writes"] += 1
            check(old == FAR_FUTURE_EPOCH, f"H2: {name}_epoch of {i} rewritten {old}->{new}")
            check(new >= c + FG_ANCHOR_LOOKBACK,
                  f"H2: {name}_epoch of {i} set to {new} < c+5 (c={c}, {where})")
            margin = new - c
            if H2["min_margin"] is None or margin < H2["min_margin"]:
                H2["min_margin"] = margin
            if margin == FG_ANCHOR_LOOKBACK and H2["tight_" + name] is None:
                H2["tight_" + name] = (i, c, new, where)


def process_epoch(st):
    before = lifecycle_snapshot(st)
    c = get_current_epoch(st)
    st.tab_cache = None
    process_registry_updates(st)
    # process_slashings: balance-only (electra:934-955) -- no lifecycle write, omitted
    process_pending_deposits(st)
    process_pending_consolidations(st)
    process_effective_balance_updates(st)
    st.tab_cache = None
    check_h2(st, before, c, f"process_epoch({c})")


def process_slots(st, slot):                     # DC-spec:933-945
    assert st.slot < slot
    while st.slot < slot:
        if (st.slot + 1) % SLOTS_PER_EPOCH == 0:
            process_epoch(st)
        st.slot += 1


REG_LEN_AT = {}       # block root -> len(validators) in its post-state (for Roberto's O3)


def apply_block(st, slot, ops):
    process_slots(st, slot)
    lifecycle_ops = [op for op in ops if op[0] in ("exit", "el_exit", "slash", "consolidate")]
    before = lifecycle_snapshot(st) if lifecycle_ops else None
    for op in ops:
        kind = op[0]
        if kind == "exit":
            op_voluntary_exit(st, op[1])
        elif kind == "el_exit":
            op_el_full_exit(st, op[1])
        elif kind == "slash":
            op_attester_slashing(st, op[1])
        elif kind == "deposit":
            op_deposit_request(st, op[1], op[2], op[3])
        elif kind == "consolidate":
            op_consolidation_request(st, op[1], op[2])
        elif kind == "drain":
            op_drain(st, op[1], op[2])
        elif kind == "finalize":                 # stand-in for process_height_events (DC-spec:970-988)
            st.finalized_slot = max(st.finalized_slot, op[1])
        else:
            raise ValueError(kind)
    if before is not None:
        check_h2(st, before, get_current_epoch(st), f"block@{slot}")
    parent = st.chain_roots[-1]
    root = hashlib.sha256(parent + slot.to_bytes(8, "little") + repr(ops).encode()).digest()
    st.chain_slots.append(slot)
    st.chain_roots.append(root)
    REG_LEN_AT[root] = len(st.validators)
    return root


# ---------------------------------------------------------------------------
# Recommended rule R: index set, anchor, membership, bit layout
# ---------------------------------------------------------------------------
GENESIS_ROOT = b"\x00" * 32


def get_fg_dependent_root(st, epoch):
    """D(epoch): root of the latest block at or before the last slot of epoch - 5."""
    if epoch < FG_ANCHOR_LOOKBACK:
        return GENESIS_ROOT
    return get_block_root_at_slot(st, compute_start_slot_at_epoch(epoch - MAX_SEED_LOOKAHEAD) - 1)


def get_fg_index_set(st, rnd):
    epoch = compute_epoch_at_round(rnd)
    # valid on any state that has processed epoch - 5 (i.e. epoch <= current + 4)
    assert st.slot >= compute_start_slot_at_epoch(epoch - MAX_SEED_LOOKAHEAD)
    return get_active_validator_indices(st, epoch)


def get_fg_era_seed(st, rnd):
    era = compute_epoch_at_round(rnd) // FG_ERA_EPOCHS
    return hashlib.sha256(b"fg-era" + era.to_bytes(8, "little")
                          + get_fg_dependent_root(st, era * FG_ERA_EPOCHS)).digest()


def fg_group_and_subnet(index, cohorts, subnets, seed):
    if seed is None:                             # striping
        return index % cohorts, (index // cohorts) % subnets
    h = hashlib.sha256(seed + index.to_bytes(8, "little")).digest()
    return int.from_bytes(h[0:8], "little") % cohorts, int.from_bytes(h[8:16], "little") % subnets


def get_fg_rotation(rnd, cohorts):
    return (rnd // FG_ROTATION_PERIOD_ROUNDS) % cohorts


def get_fg_committee_index(index, rnd, cohorts, subnets, seed=None):
    g, s = fg_group_and_subnet(index, cohorts, subnets, seed)
    cohort = (g + get_fg_rotation(rnd, cohorts)) % cohorts
    return cohort * subnets + s


def fg_layout_from_set(index_set, rnd, cohorts=FG_COHORTS_PER_ROUND,
                       subnets=FG_SUBNETS_PER_COHORT, seed=None):
    """Committee q -> ascending member list; bit position = rank in that list."""
    layout = [[] for _ in range(cohorts * subnets)]
    for i in index_set:                           # index_set is ascending
        layout[get_fg_committee_index(i, rnd, cohorts, subnets, seed)].append(i)
    return layout


def get_fg_attesting_indices(st, rnd, committee_bits, aggregation_bits, layout=None):
    if layout is None:
        layout = fg_layout_from_set(get_fg_index_set(st, rnd), rnd)
    out, offset = set(), 0
    for q in committee_bits:
        members = layout[q]
        for k, idx in enumerate(members):
            if aggregation_bits[offset + k]:
                out.add(idx)
        offset += len(members)
    assert len(aggregation_bits) == offset        # cf. electra:1533-1534
    return out


def digest_list(lst):
    return hashlib.sha256(array("I", lst).tobytes()).hexdigest()[:16]


def digest_layout(layout):
    h = hashlib.sha256()
    for members in layout:
        h.update(array("I", members).tobytes())
        h.update(b"|")
    return h.hexdigest()[:16]


# ---------------------------------------------------------------------------
# Mikhail's rule as written (O4): DC-spec:856-873, 700-721
# ---------------------------------------------------------------------------
def mk_index_list(st):
    fe = dc_finalized_epoch(st)
    return [i for i in range(len(st.validators)) if st.validators[i].exit_epoch > fe]


def mk_layout(st, rnd, lst=None):
    lst = mk_index_list(st) if lst is None else lst
    n = len(lst)
    out = []
    for k in range(COMMITTEES_PER_ROUND):
        start, end = n * k // COMMITTEES_PER_ROUND, n * (k + 1) // COMMITTEES_PER_ROUND
        out.append([lst[(i + rnd) % n] for i in range(start, end)])
    return out


def position_in(layout, index):
    for q, members in enumerate(layout):
        if index in members:
            return q, members.index(index)
    return None


def mk_is_valid_aggregation_bits(st, layout, committee, members_set):
    """DC-spec:700-721 for one committee: reject if any set bit is not active now."""
    c = get_current_epoch(st)
    attesters = [i for i in layout[committee] if i in members_set]
    if not attesters:
        return False
    return all(is_active_validator(st.validators[i], c) for i in attesters)


# ---------------------------------------------------------------------------
# Scenario
# ---------------------------------------------------------------------------
def build_base_state(rng):
    st = State()
    st.slot = compute_start_slot_at_epoch(E0) - 1
    base_root = hashlib.sha256(b"base-block").digest()
    st.chain_slots = [st.slot]
    st.chain_roots = [base_root]
    REG_LEN_AT[base_root] = N_REGISTRY
    max_exit = 0
    cats = {"withdrawn_old": 0, "exited_recent": 0, "exiting": 0, "pending": 0, "active": 0}
    for i in range(N_REGISTRY):
        u = rng.random()
        if u < 0.15:                              # long exited and withdrawn (EIP-6914-reusable)
            act = rng.randint(1000, 2000)
            ex = act + rng.randint(200, 1500)
            v = Validator(i, False, 0, act=act, elig=act - 6, exit_=ex,
                          wd=ex + MIN_VALIDATOR_WITHDRAWABILITY_DELAY)
            bal = 0
            cat = "withdrawn_old"
        elif u < 0.20:                            # recently exited
            act = rng.randint(1000, 60_000)
            ex = rng.randint(E0 - 400, E0 - 1)
            wd = ex + MIN_VALIDATOR_WITHDRAWABILITY_DELAY
            v = Validator(i, False, 32 * ETH, act=act, elig=act - 6, exit_=ex, wd=wd)
            bal = 0 if wd < E0 else 32 * ETH
            cat = "exited_recent"
        elif u < 0.205:                           # exit initiated before the base state
            act = rng.randint(1000, E0 - 300)
            ex = rng.randint(E0 + 1, E0 + 6)
            max_exit = max(max_exit, ex)
            v = Validator(i, False, 32 * ETH, act=act, elig=act - 6, exit_=ex,
                          wd=ex + MIN_VALIDATOR_WITHDRAWABILITY_DELAY)
            bal = 32 * ETH
            cat = "exiting"
        elif u < 0.21:                            # in the registry, not yet active
            elig = E0 - 2 if rng.random() < 0.5 else FAR_FUTURE_EPOCH
            v = Validator(i, False, 32 * ETH, elig=elig)
            bal = 32 * ETH
            cat = "pending"
        else:
            act = rng.randint(1000, E0 - 300)
            if rng.random() < 0.5:
                eb = 2048 * ETH if rng.random() < 0.85 else rng.randint(33, 2047) * ETH
                v = Validator(i, True, eb, act=act, elig=act - 6)
            else:
                v = Validator(i, False, 32 * ETH, act=act, elig=act - 6)
            bal = v.effective_balance + rng.randint(0, ETH // 2)
            cat = "active"
        cats[cat] += 1
        st.validators.append(v)
        st.balances.append(bal)
        st.pubkey_index[i] = i
    st.earliest_exit_epoch = max_exit
    st.finalized_slot = st.slot - 16
    return st, cats


def pick(rng, st, pred, k):
    c = get_current_epoch(st)
    pool = [i for i, v in enumerate(st.validators) if pred(v, c)]
    rng.shuffle(pool)
    return pool[:k]


def plain_exitable(v, c):
    return (not v.compounding and is_active_validator(v, c) and v.exit_epoch == FAR_FUTURE_EPOCH
            and c >= v.activation_epoch + SHARD_COMMITTEE_PERIOD and not v.slashed)


def compounding_target(v, c):
    return v.compounding and is_active_validator(v, c) and v.exit_epoch == FAR_FUTURE_EPOCH


def dc_round_finality(st, slot, done):
    """DC happy path: one finalization per round, 2/3 into the round (DC-spec:114-117),
    finalizing the latest block at or before the end of the previous round."""
    rnd = compute_round_at_slot(slot)
    if slot % SLOTS_PER_ROUND >= 5 and rnd not in done:
        done.add(rnd)
        return [("finalize", block_slot_at(st, compute_start_slot_at_round(rnd) - 1))]
    return []


class Recorder:
    """Per-branch observations taken at every block's post-state."""

    def __init__(self, name):
        self.name = name
        self.act = {}         # epoch -> set of digests of Active(epoch)
        self.act_list = {}    # epoch -> the list itself (first observation)
        self.dep = {}         # epoch -> set of D(epoch)
        self.layout = {}      # round -> set of R layout digests
        self.mk = {}          # round -> list of (slot, digest, len, fin_epoch) for O4
        self.mk_lists = {}    # round -> {slot: index list} (sampled)
        self.dep_final = []   # (slot, round, D-slot <= finalized_slot)
        self.fin_slot = {}    # block slot -> finalized_slot in its post-state

    def observe(self, st, track_mk):
        cur = get_current_epoch(st)
        rnd = compute_round_at_slot(st.slot)
        for e in (cur - 1, cur, cur + 1, cur + MAX_SEED_LOOKAHEAD):
            lst = get_active_validator_indices(st, e)
            self.act.setdefault(e, set()).add(digest_list(lst))
            self.act_list.setdefault(e, lst)
            self.dep.setdefault(e, set()).add(get_fg_dependent_root(st, e))
        for r in (rnd - 1, rnd):
            # recomputed from THIS state for the invariance check (current + previous round,
            # i.e. the whole inclusion window of DC-spec:657-660)
            lay_here = fg_layout_from_set(get_fg_index_set(st, r), r)
            self.layout.setdefault(r, set()).add(digest_layout(lay_here))
        dslot = block_slot_at(st, compute_start_slot_at_epoch(cur - MAX_SEED_LOOKAHEAD) - 1)
        self.dep_final.append((st.slot, rnd, dslot <= st.finalized_slot))
        self.fin_slot[st.slot] = st.finalized_slot
        if track_mk:
            for r in (rnd - 1, rnd):
                lst = mk_index_list(st)
                self.mk.setdefault(r, []).append((st.slot, digest_list(lst), len(lst),
                                                  dc_finalized_epoch(st), len(st.validators)))
                self.mk_lists.setdefault(r, {})[st.slot] = lst


def run_branch(st, name, start_slot, end_slot, schedule, block_rng, p_block, finality,
               gap_epochs=(), track_mk=True, rec=None, forced=(), hook=None):
    rec = rec or Recorder(name)
    done_rounds = set()
    carry = []
    roots = {}
    for slot in range(start_slot, end_slot + 1):
        carry += schedule.get(slot, [])
        if compute_epoch_at_slot(slot) in gap_epochs:
            continue
        if slot not in forced and block_rng.random() >= p_block:
            continue
        ops = carry
        carry = []
        if finality == "round":
            # finality ops are computed on the pre-block state's chain, as DC finalizes
            # already-known blocks
            ops = ops + dc_round_finality(st, slot, done_rounds)
        roots[slot] = apply_block(st, slot, ops)
        rec.observe(st, track_mk)
        if hook is not None:
            hook(st)
    return rec, roots


def poison_hook_factory(result):
    """At the first block of each epoch E+1, take a validator x that is active in E and exits at
    E+1, put its bit in an aggregate for the last round of E (included in round r+1, which
    DC-spec:657-660 allows), and evaluate both inclusion rules on this inclusion state."""
    seen = set()

    def hook(st):
        cur = get_current_epoch(st)
        if result or cur in seen:
            return
        seen.add(cur)
        r_last = compute_round_at_slot(compute_start_slot_at_epoch(cur) - 1)
        if compute_round_at_slot(st.slot) != r_last + 1:
            return
        prev_active = get_active_validator_indices(st, cur - 1)
        cands = [i for i in prev_active if st.validators[i].exit_epoch == cur]
        mk_lay = mk_layout(st, r_last)
        for x in cands:
            pos = position_in(mk_lay, x)
            if pos is None:
                continue
            mk_ok = mk_is_valid_aggregation_bits(st, mk_lay, pos[0], {x})
            lay = fg_layout_from_set(get_fg_index_set(st, r_last), r_last)
            q, bit = position_in(lay, x)
            bits = [0] * len(lay[q])
            bits[bit] = 1
            decoded = get_fg_attesting_indices(st, r_last, [q], bits, lay)
            counted = [i for i in decoded if is_active_validator(st.validators[i], cur)]
            result.update(x=x, epoch=cur, r_last=r_last, slot=st.slot, mk_ok=mk_ok,
                          decoded=sorted(decoded), counted=len(counted))
            return
    return hook


def schedule_ops(plan):
    sched = {}
    for slot, ops in plan:
        sched.setdefault(slot, []).extend(ops)
    return sched


def genesis_check():
    """Genesis caveat: activation_epoch = GENESIS_EPOCH is written by
    initialize_beacon_state_from_eth1 (phase0:1315-1317) before any epoch is processed; every
    later write is >= c + 5 >= 5, so Active(e) for e <= 4 is the genesis set and D(e) is the
    genesis block root."""
    rng = random.Random(SEED + 99)
    st = State()
    st.slot = 0
    st.chain_slots, st.chain_roots = [0], [GENESIS_ROOT]
    for i in range(400):
        pending = i % 20 == 0
        v = Validator(i, False, 32 * ETH, act=FAR_FUTURE_EPOCH if pending else GENESIS_EPOCH,
                      elig=FAR_FUTURE_EPOCH if pending else GENESIS_EPOCH)
        st.validators.append(v)
        st.balances.append(32 * ETH)
        st.pubkey_index[i] = i
    genesis_set = [get_active_validator_indices(st, e) for e in range(5)]
    drained = [i for i in range(400) if i % 20 != 0 and rng.random() < 0.03]
    done = set()
    for slot in range(1, 7 * SLOTS_PER_EPOCH):
        ops = [("drain", i, 15 * ETH) for i in drained] if slot == 3 else []
        ops += [("deposit", 10_000 + slot, False, 32 * ETH)] if slot % 37 == 0 else []
        ops += dc_round_finality(st, slot, done)
        apply_block(st, slot, ops)
        for e in range(5):
            check(get_active_validator_indices(st, e) == genesis_set[e],
                  f"genesis: Active({e}) changed at slot {slot}")
        check(get_fg_dependent_root(st, 3) == GENESIS_ROOT, "genesis: D(e<5) = genesis root")
    later = get_active_validator_indices(st, 6)
    print(f"  genesis: Active(0..4) fixed by the genesis state through slot {st.slot} "
          f"(with ejections and activations happening); Active(6) already differs by "
          f"{len(set(genesis_set[4]) ^ set(later))} indices")


def main():
    rng = random.Random(SEED)
    print("anchor_check.py -- Lane C (RQ4).  seed", SEED, "| churn mode", CHURN_MODE)
    st, cats = build_base_state(rng)
    print(f"registry {N_REGISTRY}: " + ", ".join(f"{k} {v}" for k, v in cats.items()))
    tab = get_total_active_balance(st)
    a, e, cn = churn_limits(tab, CHURN_MODE)
    print(f"total active balance {tab / ETH / 1e6:.2f}M ETH -> churn act/exit/cons "
          f"{a // ETH}/{e // ETH}/{cn // ETH} ETH per epoch")

    s0 = compute_start_slot_at_epoch
    # ---------------- common prefix ----------------
    common_rng = random.Random(SEED + 1)
    plan = []
    exits0 = pick(common_rng, st, plain_exitable, 5)
    plan.append((s0(E0) + 3, [("exit", i) for i in exits0[:3]]))
    plan.append((s0(E0 + 1) + 10, [("deposit", 1_000_000 + k, False, 32 * ETH) for k in range(3)]))
    srcs = pick(common_rng, st, plain_exitable, 4)
    tgts = pick(common_rng, st, compounding_target, 4)
    plan.append((s0(E0 + 2) + 5, [("consolidate", srcs[0], tgts[0])]))
    slashed0 = pick(common_rng, st, lambda v, c: is_active_validator(v, c) and not v.slashed, 1)
    plan.append((s0(E0 + 2) + 20, [("slash", slashed0[0])]))
    plan.append((s0(E0 + 3) + 12, [("exit", i) for i in exits0[3:5]]))
    plan.append((s0(E0 + 6) + 20, [("deposit", 1_000_100 + k, False, 32 * ETH) for k in range(4)]))
    more = pick(common_rng, st, plain_exitable, 3)
    plan.append((s0(E0 + 7) + 9, [("exit", more[0]), ("exit", more[1]), ("el_exit", more[2])]))
    s_dep = s0(E0 + COMMON_EPOCHS) + 2
    t_slot = s0(E0 + COMMON_EPOCHS) + 6
    common_sched = schedule_ops(plan)

    rec_common = Recorder("common")
    block_rng = random.Random(SEED + 2)
    done_rounds = set()
    carry = []
    v_topup = None
    for slot in range(st.slot + 1, t_slot + 1):
        carry += common_sched.get(slot, [])
        if slot not in (s_dep, t_slot) and block_rng.random() >= 0.9:
            continue
        ops = carry
        carry = []
        if slot == s_dep:
            # top-up for an active 0x01 validator v sized to the activation churn, then a new w
            churn = get_activation_churn_limit(st)
            v_topup = pick(common_rng, st, plain_exitable, 1)[0]
            ops = ops + [("deposit", v_topup, False, churn - 16 * ETH),
                         ("deposit", 2_000_000, False, 32 * ETH)]
        ops = ops + dc_round_finality(st, slot, done_rounds)
        apply_block(st, slot, ops)
        rec_common.observe(st, False)
    e_T = compute_epoch_at_slot(t_slot)
    print(f"target T: slot {t_slot} (epoch e_T = E0+{e_T - E0}), finalized_slot {st.finalized_slot}"
          f" (epoch E0+{dc_finalized_epoch(st) - E0}); top-up queued for v = {v_topup}")
    francesco_T = digest_list(get_active_validator_indices(st, e_T))

    # ---------------- branches ----------------
    end_slot = s0(e_T + BRANCH_EPOCHS + 1) - 1
    stA, stB = st.clone(), st.clone()
    rA = random.Random(SEED + 10)
    planA = []
    for k in range(0, BRANCH_EPOCHS + 1):
        ep = e_T + k
        ex = pick(rA, st, plain_exitable, 2)
        planA.append((s0(ep) + 3 if k else t_slot + 1, [("exit", i) for i in ex]))
    planA.append((s0(e_T + 1) + 7, [("slash", pick(rA, st, lambda v, c: is_active_validator(v, c)
                                                    and not v.slashed, 1)[0])]))
    planA.append((s0(e_T + 1) + 1, [("deposit", 3_000_000 + k, False, 32 * ETH) for k in range(4)]))
    planA.append((s0(e_T + 2) + 9, [("consolidate", srcs[1], tgts[1])]))
    planA.append((s0(e_T + 3) + 12, [("el_exit", pick(rA, st, plain_exitable, 1)[0])]))
    schedA = schedule_ops(planA)
    blocks_A_rng_seed = SEED + 11

    rB = random.Random(SEED + 20)
    planB = [(t_slot + 14, [("exit", i) for i in pick(rB, st, plain_exitable, 3)]),
             (s0(e_T + 1) + 4, [("slash", i) for i in pick(rB, st, lambda v, c: is_active_validator(v, c)
                                                         and not v.slashed, 2)]),
             (s0(e_T + 1) + 10, [("drain", i, 15 * ETH + ETH // 2)
                                 for i in pick(rB, st, plain_exitable, 6)]),
             (s0(e_T + 1) + 15, [("deposit", 4_000_000 + k, False, 32 * ETH) for k in range(5)]),
             (s0(e_T + 2) + 2, [("consolidate", srcs[2], tgts[2])])]
    schedB = schedule_ops(planB)

    print("running branch A (healthy finality) ...")
    poison = {}
    recA, rootsA = run_branch(stA, "A", t_slot + 1, end_slot, schedA,
                              random.Random(blocks_A_rng_seed), 0.85, "round",
                              hook=poison_hook_factory(poison))
    print("running branch B (finality stalled at T, ejections, 4 empty epochs) ...")
    gapB = tuple(range(e_T + 5, e_T + 9))
    recB, rootsB = run_branch(stB, "B", t_slot + 1, end_slot, schedB, random.Random(SEED + 21),
                              0.85, "none", gap_epochs=gapB)
    print("running branch C (= A + one extra exit of v) ...")
    stC = st.clone()
    first_after_T = min(rootsA)
    schedC = {k: list(v) for k, v in schedA.items()}
    schedC.setdefault(first_after_T, []).append(("exit", v_topup))
    recC, rootsC = run_branch(stC, "C", t_slot + 1, end_slot, schedC,
                              random.Random(blocks_A_rng_seed), 0.85, "round")
    print("running branch D (= A + EIP-6914 index reuse + 6 extra deposits) ...")
    stD = st.clone()
    stD.eip6914 = True
    schedD = {k: list(v) for k, v in schedA.items()}
    schedD.setdefault(t_slot + 20, []).extend(("deposit", 5_000_000 + k, False, 32 * ETH)
                                              for k in range(6))
    recD, rootsD = run_branch(stD, "D", t_slot + 1, end_slot, schedD,
                              random.Random(blocks_A_rng_seed), 0.85, "round")
    check(sorted(rootsA) == sorted(rootsC) == sorted(rootsD), "A/C/D share block slots")
    check(recA.fin_slot == recC.fin_slot == recD.fin_slot,
          "A, C, D have identical finalized_slot at every block")

    branches = {"A": (stA, recA), "B": (stB, recB), "C": (stC, recC), "D": (stD, recD)}
    for rec in (recA, recB, recC, recD):
        for e, ds in rec_common.act.items():
            rec.act.setdefault(e, set()).update(ds)
        for e, ds in rec_common.dep.items():
            rec.dep.setdefault(e, set()).update(ds)
        for e, l in rec_common.act_list.items():
            rec.act_list.setdefault(e, l)
        for r, ds in rec_common.layout.items():
            rec.layout.setdefault(r, set()).update(ds)

    # =====================================================================
    print("\n[H2] lifecycle writes (diffed snapshots of every epoch transition and op block)")
    print(f"  activation_epoch writes {H2['activation_writes']}, exit_epoch writes "
          f"{H2['exit_writes']}, new registry entries {H2['new_entries']}, EIP-6914 reuses "
          f"{H2['reuses']}; min(value - c) = {H2['min_margin']} epochs")
    check(H2["min_margin"] == FG_ANCHOR_LOOKBACK, "H2 bound c+5 attained")
    ta, tx = H2["tight_activation"], H2["tight_exit"]
    if ta:
        print(f"  tight activation: index {ta[0]} activation_epoch {ta[2]} = c+5 written at c={ta[1]} ({ta[3]})")
    if tx:
        print(f"  tight exit:       index {tx[0]} exit_epoch {tx[2]} = c+5 written at c={tx[1]} ({tx[3]})")
    check(ta is not None and tx is not None, "both bounds attained (tightness of e-5)")
    genesis_check()

    # =====================================================================
    print("\n[R] invariance along each branch: one Active(E) and one layout per (branch, E / round)")
    for name, (_, rec) in branches.items():
        multi_e = [e for e, ds in rec.act.items() if len(ds) != 1]
        multi_r = [r for r, ds in rec.layout.items() if len(ds) != 1]
        check(not multi_e, f"{name}: Active(E) not unique for epochs {multi_e[:5]}")
        check(not multi_r, f"{name}: R layout not unique for rounds {multi_r[:5]}")
        print(f"  {name}: {len(rec.act)} epochs, {len(rec.layout)} rounds observed -> unique: "
              f"{not multi_e and not multi_r}")

    print("\n[R] cross-branch: identical sets and layouts wherever D(E) is shared")
    shared_max = {}
    for x, y in (("A", "B"), ("A", "C"), ("A", "D"), ("B", "C"), ("B", "D"), ("C", "D")):
        rx, ry = branches[x][1], branches[y][1]
        common_e = sorted(set(rx.act) & set(ry.act))
        same_d = [e for e in common_e if rx.dep[e] == ry.dep[e] and len(rx.dep[e]) == 1]
        diff_d = [e for e in common_e if rx.dep[e] != ry.dep[e]]
        ok = all(rx.act[e] == ry.act[e] for e in same_d)
        rounds = [r for r in set(rx.layout) & set(ry.layout) if compute_epoch_at_round(r) in same_d]
        ok_l = all(rx.layout[r] == ry.layout[r] for r in rounds)
        check(ok and ok_l, f"R differs between {x} and {y} despite equal D(E)")
        differ_after = sum(1 for e in diff_d if rx.act[e] != ry.act[e])
        shared_max[(x, y)] = max(same_d) if same_d else None
        print(f"  {x}-{y}: D(E) shared for E <= E0+{max(same_d) - E0} ({len(same_d)} epochs, "
              f"{len(rounds)} rounds): sets equal {ok}, layouts equal {ok_l}; "
              f"epochs with different D: {len(diff_d)}, of which sets differ: {differ_after}")
    check(all(v == e_T + MAX_SEED_LOOKAHEAD for v in shared_max.values()),
          "shared window ends exactly at e_T + 4")

    # Other cohort counts and the era-hash composition (seed derived from D(era start), which is
    # an ancestor of D(E) for every E in the era), recomputed from each branch's recorded sets.
    def era_seed(rec, rnd):
        era = compute_epoch_at_round(rnd) // FG_ERA_EPOCHS
        (d,) = rec.dep[era * FG_ERA_EPOCHS]
        return hashlib.sha256(b"fg-era" + era.to_bytes(8, "little") + d).digest()

    # the seed recomputed from each branch's FINAL state (block_roots history) is the one seen live
    for n in "ABCD":
        for r in range(e_T * 4, (e_T + MAX_SEED_LOOKAHEAD + 1) * 4):
            check(get_fg_era_seed(branches[n][0], r) == era_seed(branches[n][1], r),
                  f"{n}: era seed for round {r} not recoverable from a later state")

    eq_stripe = eq_hash = True
    n_layouts = 0
    for C in (8, 11, 22, 23):
        for (x, y) in (("A", "B"), ("A", "C"), ("A", "D"), ("B", "C")):
            rx, ry = branches[x][1], branches[y][1]
            for e in range(e_T - 1, e_T + MAX_SEED_LOOKAHEAD + 1):
                for r in range(e * 4, e * 4 + 4):
                    for seeded in (False, True):
                        sx = era_seed(rx, r) if seeded else None
                        sy = era_seed(ry, r) if seeded else None
                        lx = fg_layout_from_set(rx.act_list[e], r, C, FG_SUBNETS_PER_COHORT, sx)
                        ly = fg_layout_from_set(ry.act_list[e], r, C, FG_SUBNETS_PER_COHORT, sy)
                        same = digest_layout(lx) == digest_layout(ly)
                        n_layouts += 1
                        if seeded:
                            eq_hash &= same
                        else:
                            eq_stripe &= same
    check(eq_stripe and eq_hash, "layouts equal for C in {8,11,22,23}, striping and era-hash")
    print(f"  {n_layouts} layout comparisons (C in {{8, 11, 22, 23}} x 4 branch pairs x rounds of "
          f"E0+{e_T - 1 - E0}..E0+{e_T + 4 - E0} x 2 compositions): striping equal {eq_stripe}, "
          f"era-hash equal {eq_hash}")

    # (E, D) keying: empty epochs on B
    same_d_diff_e = []
    recBd = recB.dep
    for e1 in sorted(recBd):
        for e2 in sorted(recBd):
            if e1 < e2 and recBd[e1] == recBd[e2] and recB.act[e1] != recB.act[e2]:
                same_d_diff_e.append((e1, e2))
    print(f"  B (empty epochs E0+{gapB[0] - E0}..E0+{gapB[-1] - E0}): {len(same_d_diff_e)} epoch "
          f"pairs share D but have different Active -> cache key must be (E, D(E)), not D alone")
    check(len(same_d_diff_e) > 0, "empty epochs produce shared-D, different-set pairs")

    # D(E(r)) finalized?
    for name in ("A", "B"):
        rec = branches[name][1]
        bad = [s for s, r, fin in rec.dep_final if not fin]
        first = bad[0] if bad else None
        if name == "A":
            check(not bad, "A: D(E(current round)) always finalized under healthy DC finality")
        print(f"  {name}: blocks where D(E(current round)) is not finalized: {len(bad)} of "
              f"{len(rec.dep_final)}"
              + (f" (first at slot {first}, {first - t_slot} slots after T)" if first else ""))

    # =====================================================================
    print("\n[O2a] Francesco: Active(epoch(T.slot)) from every state descending from T")
    vals = {n: digest_list(get_active_validator_indices(branches[n][0], e_T)) for n in "ABCD"}
    obs = set()
    for n in "ABCD":
        obs |= branches[n][1].act.get(e_T, set())
    ok = len(set(vals.values()) | {francesco_T} | obs) == 1
    check(ok, "O2a set differs between states descending from T")
    print(f"  identical at T, along all branches and in the four final states: {ok}")

    # Mikhail 1589 variant: active at e_T plus anyone with an activation assigned after e_T
    def mk1589(stx):
        return [i for i, v in enumerate(stx.validators)
                if v.exit_epoch > e_T and v.activation_epoch != FAR_FUTURE_EPOCH]
    va, vb = mk1589(stA), mk1589(stB)
    extra = sorted(set(va) - set(vb))
    print(f"  variant 'active at e_T + activations assigned later' (msg 1589): |A| {len(va)} vs "
          f"|B| {len(vb)}; in A only: {extra[:6]}{' ...' if len(extra) > 6 else ''}")
    check(len(va) != len(vb), "1589 variant diverges between A and B")
    late = [i for i in extra if stA.validators[i].activation_epoch > e_T]
    print(f"  of these, {len(late)} were activated on A after T (finality-gated, never on B)")
    # staleness of the target-anchored set while the FG is stuck on T (branch B)
    curB = get_current_epoch(stB)
    s_T = set(get_active_validator_indices(stB, e_T))
    s_now = set(get_active_validator_indices(stB, curB))
    print(f"  O2a on B (target stuck at T for {curB - e_T} epochs): Active(e_T) has {len(s_T - s_now)} "
          f"members no longer active (dead bits) and misses {len(s_now - s_T)} active validators; "
          f"R uses Active(E(r)) = exact")

    # =====================================================================
    print("\n[O4] Mikhail's finalized-epoch rule (DC-spec:856-873) -- counterexamples")
    # (a) A vs B, different finality, inside the shared-D window
    win_rounds = [r for r in sorted(set(recA.mk) & set(recB.mk))
                  if e_T <= compute_epoch_at_round(r) <= e_T + MAX_SEED_LOOKAHEAD]
    shown = False
    n_diff = n_disjoint = 0
    for r in win_rounds:
        a0 = recA.mk[r][0]
        b0 = recB.mk[r][0]
        if not ({o[1] for o in recA.mk[r]} & {o[1] for o in recB.mk[r]}):
            n_disjoint += 1
        if a0[1] != b0[1]:
            n_diff += 1
            if not shown:
                la = mk_layout(None, r, recA.mk_lists[r][a0[0]])
                lb = mk_layout(None, r, recB.mk_lists[r][b0[0]])
                probe = next(i for i in recA.mk_lists[r][a0[0]]
                             if position_in(la, i) != position_in(lb, i))
                pa, pb = position_in(la, probe), position_in(lb, probe)
                ra = branches["A"][1].act_list[compute_epoch_at_round(r)]
                rpos = position_in(fg_layout_from_set(ra, r), probe)
                print(f"  (a) round {r} (epoch E0+{compute_epoch_at_round(r) - E0}): A list len {a0[2]} "
                      f"(fin epoch E0+{a0[3] - E0}) vs B len {b0[2]} (fin E0+{b0[3] - E0}); validator "
                      f"{probe} sits at (committee, bit) {pa} on A but {pb} on B; R puts it at {rpos} on both")
                shown = True
    print(f"      rounds in the window (E0+{e_T - E0}..E0+{e_T + 4 - E0}) whose first O4 view differs "
          f"A vs B: {n_diff}/{len(win_rounds)}; with NO state on A agreeing with any state on B: "
          f"{n_disjoint}/{len(win_rounds)}")
    check(n_diff > 0, "O4 differs across branches with different finality")
    # (b) single chain, inside one round, and over the whole inclusion window (rounds r, r+1)
    inside = []
    unstable = 0
    for r, obs_r in recA.mk.items():
        same_round = [o for o in obs_r if compute_round_at_slot(o[0]) == r]
        if len({o[1] for o in same_round}) > 1:
            inside.append((r, same_round))
        if len({o[1] for o in obs_r}) > 1:
            unstable += 1
    if inside:
        r, obs_r = inside[0]
        chg = next(k for k in range(1, len(obs_r)) if obs_r[k][1] != obs_r[k - 1][1])
        o0, o1 = obs_r[chg - 1], obs_r[chg]
        print(f"  (b) A, one chain: {len(inside)} rounds whose O4 layout changes mid-round; e.g. round "
              f"{r}: slot {o0[0]} (len {o0[2]}, fin epoch E0+{o0[3] - E0}) -> slot {o1[0]} "
              f"(len {o1[2]}, fin epoch E0+{o1[3] - E0})")
    print(f"      rounds on A whose O4 layout is not constant over their inclusion window (rounds r and "
          f"r+1, DC-spec:657-660): {unstable}/{len(recA.mk)}; for R: 0/{len(recA.layout)} (asserted above)")
    check(bool(inside), "O4 layout changes inside a round on one chain")
    # (c) A vs C: identical finality, different registry length
    c_diff = []
    for r in sorted(set(recA.mk) & set(recC.mk)):
        for (sa, da, la_, fa, ra_), (sc, dc_, lc, fc, rc) in zip(recA.mk[r], recC.mk[r]):
            if sa == sc and recA.fin_slot[sa] == recC.fin_slot[sc] and da != dc_:
                c_diff.append((r, sa, la_, lc, ra_, rc, recA.fin_slot[sa]))
                break
    c_win = [x for x in c_diff if compute_epoch_at_round(x[0]) <= e_T + MAX_SEED_LOOKAHEAD]
    if c_win:
        r, s, la_, lc, ra_, rc, fs = c_win[0]
        r_equal = all(recA.layout[x[0]] == recC.layout[x[0]] for x in c_win)
        print(f"  (c) A vs C, SAME finalized_slot {fs} at the same block slot {s}: round {r}: registry "
              f"{ra_} vs {rc}, O4 list {la_} vs {lc} -> layouts differ; {len(c_win)} such rounds inside "
              f"the shared-D window ({len(c_diff)} overall); R equal for all of them: {r_equal}")
        check(r_equal, "R equal where O4 differs (A vs C)")
    check(bool(c_win), "O4 differs with identical finality (registry length)")
    # (d) one chain, previous-round inclusion across an epoch boundary
    across = []
    for r, obs_r in recA.mk.items():
        e_r = compute_epoch_at_round(r)
        own = [o for o in obs_r if compute_epoch_at_slot(o[0]) == e_r]
        nxt = [o for o in obs_r if compute_epoch_at_slot(o[0]) == e_r + 1]
        if own and nxt and own[-1][1] != nxt[0][1]:
            across.append((r, own[-1], nxt[0]))
    if across:
        r, o0, o1 = across[0]
        print(f"  (d) A, one chain: {len(across)} last-of-epoch rounds whose O4 layout changes at the "
              f"boundary (votes included in the next round decode differently); e.g. round {r}: "
              f"registry {o0[4]} -> {o1[4]}, list {o0[2]} -> {o1[2]}")
    check(bool(across), "O4 layout changes across the epoch boundary on one chain")

    # poison bit: validator exiting at E+1 votes in the last round of E (DC-spec:714-718)
    check(bool(poison), "poison-bit scenario found on A")
    if poison:
        print(f"  poison bit: validator {poison['x']} (exit_epoch E0+{poison['epoch'] - E0}) votes in "
              f"round {poison['r_last']} (last of epoch E0+{poison['epoch'] - 1 - E0}); at the inclusion "
              f"block (slot {poison['slot']}, next round): DC-spec is_valid_aggregation_bits accepts "
              f"the aggregate: {poison['mk_ok']}; R decodes {poison['decoded']} and counts "
              f"{poison['counted']} -> aggregate stays includable, the bit simply does not count")
        check(not poison["mk_ok"] and poison["decoded"] == [poison["x"]], "poison-bit demonstration")

    # =====================================================================
    print("\n[EIP-6914] index reuse on D")
    reuses = stD.reuse_log
    print(f"  reuses on D: {len(reuses)}; e.g. {reuses[:2]}")
    check(len(reuses) > 0, "EIP-6914 reuse exercised")
    if reuses:
        j, old_pk, new_pk, ce, old_act, old_exit, old_wd = reuses[0]
        print(f"  index {j}: pubkey {stA.validators[j].pubkey} on A vs {stD.validators[j].pubkey} on D "
              f"-> an index->pubkey cache must be keyed by the anchor or invalidated on reuse")
        e_old = old_act + 1
        on_a = j in get_active_validator_indices(stA, e_old)
        on_d = j in get_active_validator_indices(stD, e_old)
        print(f"  Active({e_old}) (old validator's era) contains {j}: A {on_a}, D {on_d} -> past sets are "
              f"only recoverable for E >= c - {SAFE_EPOCHS_TO_REUSE_INDEX + MIN_VALIDATOR_WITHDRAWABILITY_DELAY}")
        check(on_a and not on_d, "reuse rewrites history beyond the safety window")
        recent_ok = all(get_active_validator_indices(stA, e) == get_active_validator_indices(stD, e)
                        for e in range(e_T - 2, e_T + MAX_SEED_LOOKAHEAD + 1))
        print(f"  Active(E) for E in [e_T-2, e_T+4] equal on A and D: {recent_ok}")
        check(recent_ok, "reuse leaves the voting window untouched")

    # =====================================================================
    print("\n[cache] distinct (E, D(E)) index sets a gossip node needs")
    entries = {}
    for name, (_, rec) in branches.items():
        for e, ds in rec.dep.items():
            for d in ds:
                entries.setdefault(e, set()).add(d)
    per_e = {e: len(ds) for e, ds in entries.items() if e >= e_T - 1}
    print("  per epoch E (all four branches): " + ", ".join(
        f"E0+{e - E0}:{n}" for e, n in sorted(per_e.items())))
    check(all(n == 1 for e, n in per_e.items() if e <= e_T + MAX_SEED_LOOKAHEAD),
          "one cache entry per epoch while D is shared")
    deltas = []
    for e in sorted(recA.act_list):
        if e + 1 in recA.act_list:
            s1, s2 = set(recA.act_list[e]), set(recA.act_list[e + 1])
            deltas.append(len(s1 ^ s2))
    print(f"  per-epoch delta |Active(E) xor Active(E+1)| on A: max {max(deltas)}, mean "
          f"{sum(deltas) / len(deltas):.1f} (n_active ~ {len(recA.act_list[e_T])})")

    # Roberto (O3, msgs 1639-1641): anchor = latest finalized block; STF accepts only that anchor.
    slotsA = sorted(recA.fin_slot)
    rounds_A = sorted({compute_round_at_slot(s) for s in slotsA})
    anchors_A = [recA.fin_slot[s] for s in slotsA]
    n_changes = sum(1 for k in range(1, len(anchors_A)) if anchors_A[k] != anchors_A[k - 1])
    resend = 0
    for r in rounds_A:
        window = [recA.fin_slot[s] for s in slotsA if compute_round_at_slot(s) in (r, r + 1)]
        if len(set(window)) > 1:
            resend += 1
    differ_AB = sum(1 for s in slotsA if s in recB.fin_slot and recA.fin_slot[s] != recB.fin_slot[s])
    common_AB = sum(1 for s in slotsA if s in recB.fin_slot)
    print(f"  O3 (anchor = latest finalized): on A the anchor changed {n_changes} times in "
          f"{len(rounds_A)} rounds; rounds whose inclusion window (r, r+1) spans an anchor change, "
          f"i.e. votes that need a second copy under the new anchor: {resend}/{len(rounds_A)}; "
          f"blocks at the same slot on A and B with different anchors: {differ_AB}/{common_AB}")

    def roberto_set(stx, rec):
        fs = rec.fin_slot[max(rec.fin_slot)]
        root_f = stx.chain_roots[root_index_at(stx, fs)]
        n_f = REG_LEN_AT[root_f]
        fe = compute_epoch_at_slot(fs)
        return [i for i in range(n_f) if stx.validators[i].exit_epoch > fe]
    vA = roberto_set(stA, recA)
    vB = roberto_set(stB, recB)
    curA, curB = get_current_epoch(stA), get_current_epoch(stB)
    actA, actB = get_active_validator_indices(stA, curA), get_active_validator_indices(stB, curB)
    print(f"  O3 set V(F) at the end: A {len(vA)} entries for {len(actA)} active "
          f"({1 - len(set(actA) & set(vA)) / len(vA):.2%} dead bits); B (F frozen at T) {len(vB)} for "
          f"{len(actB)} active ({1 - len(set(actB) & set(vB)) / len(vB):.2%} dead bits)")

    # compactness on the synthetic registry (end of A)
    cur = get_current_epoch(stA)
    nreg, nact = len(stA.validators), len(get_active_validator_indices(stA, cur))
    nmk = len(mk_index_list(stA))
    print(f"\n[bits] synthetic registry at end of A: registry {nreg}, Active {nact} -> O1 wastes "
          f"{1 - nact / nreg:.1%}; O4 list {nmk} (wastes {1 - nact / nmk:.2%}); R wastes 0")

    # =====================================================================
    print("\n[mainnet-scale numbers]")
    S = 36_000_000 * ETH                       # eip-8061.md:218
    for mode in ("electra", "eip8061"):
        a, e, cn = churn_limits(S, mode)
        print(f"  S = 36M ETH, {mode}: activation {a // ETH}, exit {e // ETH}, consolidation "
              f"{cn // ETH} ETH/epoch")
        for slot_s in (12, 10):
            ep_s = slot_s * SLOTS_PER_EPOCH
            for label, secs in (("1 h", 3600), ("6 h", 6 * 3600), ("1 day", 86400)):
                lag = secs / ep_s
                out = (e + cn) * lag / S
                inn = a * lag / S
                print(f"    O5 lag {label:>5} @{slot_s}s slots ({lag:6.1f} epochs): stake exited "
                      f"since snapshot <= {out:.3%}, new stake unable to vote <= {inn:.3%}; "
                      f"indices at 32 ETH: <= {int((e + cn) * lag / (32 * ETH))} wasted, "
                      f"<= {int(a * lag / (32 * ETH))} blocked")
    # O1 with cited registry counts
    jgm = {"active": 1_051_655, "exited": 770_114, "pending": 417, "activating": 394, "exiting": 2}
    reg = sum(jgm.values())
    print(f"  O1 waste, mainnet 2025-03-13 (testnets/2025-03-13.json, jgm): registry {reg}, "
          f"non-active {reg - jgm['active'] - jgm['exiting']} -> "
          f"{(reg - jgm['active'] - jgm['exiting']) / reg:.1%} of bits")
    print("  O1 waste, mainnet 2025-08-22 (consensus-dev/2025-08-22.json, arnetheduck): '>2M, ~1M exited'"
          f" -> ~{1_000_000 / 2_000_000:.0%} of bits")
    for n in (120_000, 500_000, 1_000_000):
        print(f"  cache entry, sorted uint32 indices, n = {n:>9,}: {n * 4 / 1e6:.2f} MB")
    print(f"  Prysm committee-cache entry (ShuffledIndices + SortedIndices, 8-byte indices, "
          f"cache/committees.go:14-19), n = 1,000,000: {2 * 8 * 1_000_000 / 1e6:.0f} MB; "
          f"x32 entries under non-finality: {32 * 16:.0f} MB")
    a, e, cn = churn_limits(S, "eip8061")
    d_ex16, d_ex32, d_cons, d_act = (e // EJECTION_BALANCE, e // (32 * ETH), cn // (32 * ETH),
                                     a // (32 * ETH))
    print(f"  per-epoch index-set delta bound at S = 36M ETH (EIP-8061): exits <= "
          f"{d_ex16} (at 16 ETH) / {d_ex32} (at 32 ETH), consolidation sources <= {d_cons} "
          f"(at 32 ETH), activations <= {d_act} -> <= {d_ex16 + d_cons + d_act} indices/epoch")
    # O4 at mainnet scale: committee boundaries start_k = n*k // 2048 after one append / removal
    n = 1_000_000
    moved = sum(1 for k in range(COMMITTEES_PER_ROUND)
                if n * k // COMMITTEES_PER_ROUND != (n + 1) * k // COMMITTEES_PER_ROUND)
    print(f"  O4 at n = {n:,}: one registry append moves the first member of {moved} of "
          f"{COMMITTEES_PER_ROUND} committees; one removal at list position p shifts every later "
          f"position, i.e. all bits of all committees after p (for p = n/2: "
          f"{COMMITTEES_PER_ROUND - (n // 2) * COMMITTEES_PER_ROUND // n} committees)")
    lag_slots = 4 * SLOTS_PER_EPOCH + 1
    print(f"  D(E(r)) of the round being voted on is finalized whenever finality lag <= {lag_slots} slots = {lag_slots * 12 / 60:.1f} min "
          f"(12 s) / {lag_slots * 10 / 60:.1f} min (10 s)")
    print(f"  FG duties for epoch E known from slot start(E-4): {4 * SLOTS_PER_EPOCH * 12 / 60:.1f} min "
          f"ahead at 12 s (attester duties today: 1 epoch = {SLOTS_PER_EPOCH * 12 / 60:.1f} min)")
    print(f"  evidence window for R voters: >= {MIN_VALIDATOR_WITHDRAWABILITY_DELAY} epochs = "
          f"{MIN_VALIDATOR_WITHDRAWABILITY_DELAY * SLOTS_PER_EPOCH * 12 / 3600:.1f} h after the round; "
          f"O2a: e_T + {MIN_VALIDATOR_WITHDRAWABILITY_DELAY + 1} - c epochs")

    print("\nRESULT:", "PASS" if not FAILURES else f"FAIL ({len(FAILURES)})")
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    sys.exit(main())
