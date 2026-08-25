# Benchmarking with Prysm

The prysm fork for decoupled consensus is at: [prysm](https://github.com/sukunrt/prysm/tree/decoupled-casper)

## Scenario
The fork implements goldfish availability chain with Availability Attestations and a Casper FFG gadget. Using Casper instead of simplex keeps the code change minimal.

The fork implements all this for the Heze fork and only supports genesis at Heze.

## Configurations
The fork's knobs:

1. `--decoupled-ffg-vote-at-slot-start` (vc): cast the FFG vote at slot start instead of
   waiting for the block or the attestation due time. `--decoupled-ffg-vote-jitter` bounds
   the added random delay (default 200ms). A fixed offset on top of slot start exists as an
   unmerged change.
2. `--decoupled-ffg-head-source` (vc): which head the FFG attestation names — the beacon's
   answer at vote time (default) or the answer from the round's first vote.
3. `--decoupled-late-block-publish-bps` (beacon): hold block publication back to a set
   fraction of the slot, to force gate-caused head retreats in measurement runs.
4. `--goldfish-vote-ledger` (beacon): log every availability head vote and every drop,
   one line each, for per-slot seat reconciliation.
5. `AVAILABLE_ATTESTATION_DUE_BPS_HEZE` (chain config): the availability-vote deadline,
   in basis points of the slot (2500 = 3s of a 12s slot).

**It doesn't allow a pipelined structure with the finality vote in one slot and the
aggregate vote in the next.**
