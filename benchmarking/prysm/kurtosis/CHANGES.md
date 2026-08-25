# Work plan: making the kurtosis README true

What the README describes versus what the fork's `kurtosis/` directory holds
today. Paths are relative to the repo root of
`github.com/sukunrt/prysm` @ `decoupled-casper`.

Four of the README's config values already have an injection path. Three do not:
`TARGET_COMMITTEE_SIZE`, `ATTESTATION_SUBNET_COUNT` and `SUBNETS_PER_NODE` never
reach the shipped chain config, and the FFG slot-start flag is never passed to a
validator client. Items 1-4 close that; items 5-6 are build and verify.

## Already in the tree — verified, no work

| | where | evidence |
|---|---|---|
| Heze stripped from the CL→EL fork map | `kurtosis/genesis-gen/patch-generator.sh` | `sed` on `genesis_add_heze` + `grep -q 'HEZE is CL-only'` |
| `SLOTS_PER_ROUND` in the CL template | same file | inserted before `SECONDS_PER_SLOT:`, asserted with `grep -q` |
| `AVAILABLE_ATTESTATION_DUE_BPS_HEZE` in the CL template | same file | same pattern |
| CL genesis state built by `prysmctl` | same file | `eth-genesis-state-generator` renamed, symlink to `prysm-genesis-state.sh` |
| `SLOTS_PER_ROUND` / `AVAILABLE_ATTESTATION_DUE_BPS_HEZE` image defaults | `kurtosis/Dockerfile.genesis-gen` | two `ENV` lines |
| `/apps/validator-mapping` back-ported from generator 6.2.0 | same file | `COPY --from=egg-newer` |
| three images built statically and tagged `:local` | `kurtosis/build-images.sh` | builds `beacon-chain`, `validator`, `prysmctl`, then three `docker build`s |
| REST-provider flag stripped inside the VC image | `kurtosis/validator-entrypoint.sh` | strips `--beacon-rest-api-provider`, execs `/validator` |
| **the gossipsub subscription buffer fix** | `beacon-chain/sync/subscriber.go:447-457` | `subscriptionOpts` returns `WithBufferSize(5000)` for the attestation topic and `4 * AvailableAttestationCommitteeSize` for the availability topic |
| `--decoupled-ffg-vote-at-slot-start` exists and is VC-only | `config/features/flags.go:247`, listed in `ValidatorFlags` at `:312` | jitter default 200 ms at `:254` |
| args file carries the forks, the BPO schedule, `supernode`, `SLOTS_PER_ROUND` | `kurtosis/network_params.yaml` | read in full |

## To do

### 1. Add `TARGET_COMMITTEE_SIZE` to the CL config template

**File:** `kurtosis/genesis-gen/patch-generator.sh`

`TARGET_COMMITTEE_SIZE` is absent from the generator template — verified by
grepping `/config/cl/config.yaml` inside
`ethpandaops/ethereum-genesis-generator:6.0.2`, the image
`Dockerfile.genesis-gen` builds on. It therefore keeps Prysm's mainnet default of
128 (`config/params/mainnet_config.go:78`). Insert it the way `SLOTS_PER_ROUND`
is inserted, after the existing `AVAILABLE_ATTESTATION_DUE_BPS_HEZE` block:

```diff
 grep -q '^AVAILABLE_ATTESTATION_DUE_BPS_HEZE' /config/cl/config.yaml
+
+# One committee per slot, holding the whole V/SLOTS_PER_ROUND pool.
+# SlotCommitteeCount = V / SLOTS_PER_ROUND / TARGET_COMMITTEE_SIZE, clamped to
+# [1, MAX_COMMITTEES_PER_SLOT] (beacon-chain/core/helpers/beacon_committee.go).
+# The key is absent from the upstream template, so this inserts it.
+comment5='# One committee per slot: the whole V/SLOTS_PER_ROUND pool, one seat set.'
+sed -i "/^SECONDS_PER_SLOT:/i $comment5\nTARGET_COMMITTEE_SIZE: \$TARGET_COMMITTEE_SIZE" \
+    /config/cl/config.yaml
+grep -q '^TARGET_COMMITTEE_SIZE' /config/cl/config.yaml
```

**Verify:** the build fails on the `grep -q` if the insert missed. After a run,
the config check in README step 5 prints `TARGET_COMMITTEE_SIZE: 3000` exactly
once.

### 2. Rewrite the two subnet lines **in place**

**File:** `kurtosis/genesis-gen/patch-generator.sh`

Unlike `TARGET_COMMITTEE_SIZE`, both subnet keys are already in the 6.0.2
template as literals — verified inside the image, lines 173 and 175:

```
SUBNETS_PER_NODE: 2
ATTESTATION_SUBNET_COUNT: 64
```

An insert-before-`SECONDS_PER_SLOT` patch would leave two definitions of each key
in the shipped config. Replace, and assert single definitions:

```diff
+# The subnet count must equal the committee count per slot: one committee ->
+# one subnet -> every node observes every raw FFG vote instead of a 1/64
+# sample. Both keys are already literals in the upstream template, so these
+# REPLACE those lines; inserting new ones would leave two definitions.
+sed -i 's|^SUBNETS_PER_NODE: 2$|SUBNETS_PER_NODE: $SUBNETS_PER_NODE|' \
+    /config/cl/config.yaml
+sed -i 's|^ATTESTATION_SUBNET_COUNT: 64$|ATTESTATION_SUBNET_COUNT: $ATTESTATION_SUBNET_COUNT|' \
+    /config/cl/config.yaml
+test "$(grep -c '^SUBNETS_PER_NODE' /config/cl/config.yaml)" = 1
+test "$(grep -c '^ATTESTATION_SUBNET_COUNT' /config/cl/config.yaml)" = 1
```

Leave `ATTESTATION_SUBNET_PREFIX_BITS` alone: it is not in the template, and the
mainnet default of 6 is harmless once the subnet count is 1 —
`computeSubscribedSubnet` returns `(permutated_prefix + index) % 1 == 0` for
every node.

`SUBNETS_PER_NODE: 1` is load-bearing, not cosmetic: `computeSubscribedSubnets`
(`beacon-chain/p2p/subnets.go:513-531`) loops `SubnetsPerNode` times, and at 2
would return `[0, 0]` — a duplicate long-lived subscription to subnet 0.

**Verify:** the two `test` lines fail the image build if a `sed` anchor stops
matching after a generator bump. After a run, README step 5 prints each key
exactly once with value `1`.

### 3. `ENV` defaults in the generator image

**File:** `kurtosis/Dockerfile.genesis-gen`

```diff
 ENV SLOTS_PER_ROUND=8
 ENV AVAILABLE_ATTESTATION_DUE_BPS_HEZE=2500
+ENV TARGET_COMMITTEE_SIZE=3000
+ENV ATTESTATION_SUBNET_COUNT=1
+ENV SUBNETS_PER_NODE=1
```

Required: `envsubst` turns an unset variable into the empty string, so without
these an args file that omits the key would ship `TARGET_COMMITTEE_SIZE:` with a
null value. The image `ENV` is the fallback; `extra_env` wins, because the
generator entrypoint sources `/defaults/defaults.env` first and `/config/values.env`
second (verified in `/work/entrypoint.sh`, lines 15 and 20).

**Verify:** `docker run --rm --entrypoint sh prysm-genesis-gen:local -c 'grep -n
"TARGET_COMMITTEE_SIZE\|SUBNETS_PER_NODE\|ATTESTATION_SUBNET_COUNT"
/config/cl/config.yaml'` prints three lines, each with a `$VAR` on the right.

### 4. Bring `kurtosis/network_params.yaml` up to the README's file

**File:** `kurtosis/network_params.yaml`

The file in the tree is the 2-node, 12s-slot shakeout. The README publishes the
6-node, 6s-slot devnet. Five edits:

```diff
     vc_image: prysm-validator:local
-    vc_extra_params: []
+    vc_extra_params:
+      - --decoupled-ffg-vote-at-slot-start
     use_separate_vc: true
     supernode: true
-    count: 2
+    count: 6
+    cl_extra_params:
+      - --goldfish-vote-ledger
+      - --minimum-peers-per-subnet=5
```

```diff
-  seconds_per_slot: 12
-  slot_duration_ms: 12000
-  num_validator_keys_per_node: 64
-  genesis_delay: 60
+  seconds_per_slot: 6
+  slot_duration_ms: 6000
+  num_validator_keys_per_node: 22
+  genesis_delay: 180
```

```diff
   extra_env:
     SLOTS_PER_ROUND: 8
+    AVAILABLE_ATTESTATION_DUE_BPS_HEZE: 2500
+    SLOT_DURATION_IN_SECONDS: 6
+    TARGET_COMMITTEE_SIZE: 3000
+    ATTESTATION_SUBNET_COUNT: 1
+    SUBNETS_PER_NODE: 1
```

Notes on each:

- `vc_extra_params` entries are appended verbatim to the validator command line
  (`ethereum-package/src/vc/prysm.star:117-119`) and the image's entrypoint shim
  strips only `--beacon-rest-api-provider`, so the flag passes through. Do not
  add `--decoupled-ffg-vote-jitter`: its default is already 200 ms.
- `--minimum-peers-per-subnet=5` is needed only because `count: 6` gives each
  node 5 peers while the flag defaults to 6
  (`cmd/beacon-chain/flags/base.go:277-281`). Drop it at `N >= 8`.
- `SLOT_DURATION_IN_SECONDS: 6` is required whenever `seconds_per_slot != 12`.
  The current ethereum-package exports `SLOT_DURATION_MS` but not
  `SLOT_DURATION_IN_SECONDS` (verified in
  `static_files/genesis-generation-config/el-cl/values.env.tmpl`), and generator
  6.0.2's `defaults.env` falls back to 12, which the CL template feeds straight
  into `SECONDS_PER_SLOT`. Without it, duties run on a 12s cadence against a 6s
  clock.
- `--goldfish-vote-ledger` is what `kurtosis/votetally.py` and the
  committee-shape grep read.

**Verify (sanity check, done statically — read the validator, do not run
kurtosis):** every key in the README's args file was checked against
`ethereum-package/src/package_io/sanity_check.star`. Root keys `participants`,
`network_params`, `ethereum_genesis_generator_params`, `additional_services`,
`wait_for_finalization`, `global_log_level` are all in the combined root set.
Participant keys `el_type`, `el_image`, `cl_type`, `cl_image`, `vc_type`,
`vc_image`, `vc_extra_params`, `cl_extra_params`, `use_separate_vc`, `supernode`,
`count` are all in `PARTICIPANT_CATEGORIES["participants"]`. All sixteen
`network_params` keys are in `SUBCATEGORY_PARAMS["network_params"]`.
`ethereum_genesis_generator_params` allows exactly `image` and `extra_env`. The
file passes.

`extra_env` is the only route for the three new keys: `sanity_check` `fail()`s on
any `network_params` key outside its list, and none of
`target_committee_size` / `attestation_subnet_count` / `subnets_per_node` is in
it. `extra_env` is a free-form dict, JSON-encoded into `values.env` as
`export K=V`.

### 5. Rebuild

```sh
./kurtosis/build-images.sh
```

Items 1-3 only take effect at image build time. The buffer fix is already in the
tree, so the same rebuild picks it up.

### 6. Optional: an FFG-side log parser

`kurtosis/votetally.py` reconciles the availability head votes seat by seat, but
nothing parses the FFG ledger lines the beacon writes under
`--goldfish-vote-ledger`:

| line | source |
|---|---|
| `FFG vote` outcome=gossip | `beacon-chain/sync/vote_ledger.go` |
| `FFG vote` outcome=local | `beacon-chain/rpc/prysm/v1alpha1/validator/attester.go` |
| `FFG aggregate` | `beacon-chain/sync/vote_ledger.go` |
| `FFG vote included` | `beacon-chain/blockchain/process_block.go` |

The README's verification does not need it — the committee-shape check is a
`sort -u` over `committeeIndex=`, and the buffer check is a metric. A
`ffgtally.py` alongside `votetally.py` would cover observability (distinct
`validator=` per node per slot), aggregate completeness (`seats=` summed per
`dataRoot`) and inclusion (`inclusionSlots=1` covering the committee). Not
required for the README to be true.

## Checklist

1. Edit `kurtosis/genesis-gen/patch-generator.sh` — insert `TARGET_COMMITTEE_SIZE`
   (item 1).
2. Edit the same file — replace the two subnet literals, with the two `test`
   assertions (item 2).
3. Edit `kurtosis/Dockerfile.genesis-gen` — three `ENV` lines (item 3).
4. Edit `kurtosis/network_params.yaml` — the three diffs in item 4.
5. `./kurtosis/build-images.sh`.
6. `docker run --rm --entrypoint sh prysm-genesis-gen:local -c 'grep -c ...'` —
   three template lines present, subnet keys defined exactly once.
7. `kurtosis run --enclave decoupled ../ethereum-package --args-file
   kurtosis/network_params.yaml`.
8. README step 5, in order: config keys and counts, VC flag on every VC and no
   beacon, one committee of `V/8` at slot 5, `p2p_pubsub_undeliverable_total` at
   0 and one `beacon_attestation_*` topic per node.
9. Only if the FFG-side checks are wanted beyond greps: item 6.

## Not verified here

- The public branch `decoupled-casper` at `github.com/sukunrt/prysm` was taken as
  given; the checkout this was written against was inspected locally, not
  fetched from the remote.
- The `/eth/v1/beacon/states/{state_id}/committees` response shape is asserted
  from the route's registration, not from a live call.
- Everything else above states what was read in the source, the generator image,
  or the ethereum-package checkout.
