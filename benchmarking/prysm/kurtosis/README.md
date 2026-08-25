# Running the decoupled-consensus devnet with kurtosis

The fork ships its own kurtosis harness in `kurtosis/`, so one clone gives you
both the client and the harness. `ethereum-package` is used unmodified,
read-only.

The devnet this brings up is:

| | value |
|---|---|
| genesis fork | Heze (every earlier fork at epoch 0) |
| round length | `SLOTS_PER_ROUND: 8` |
| committee | one committee per slot holding the whole per-slot pool |
| attestation subnets | one, so every node observes every raw FFG vote |
| FFG vote timing | cast at slot start, not on block arrival |

## Prerequisites

- docker
- the `kurtosis` CLI
- a Go toolchain with cgo available (the images hold statically linked binaries
  built on the host)
- a checkout of `ethpandaops/ethereum-package` at commit `0350d2e9`. Older
  checkouts launch `buildoor` with flags the current image rejects; the pin is
  what the harness is known to run against.

## 1. Clone

```sh
git clone -b decoupled-casper https://github.com/sukunrt/prysm.git
git clone https://github.com/ethpandaops/ethereum-package.git
git -C ethereum-package checkout 0350d2e9
```

Everything below is run from the `prysm` checkout.

## 2. Build the images

```sh
./kurtosis/build-images.sh
```

| image | contents |
|---|---|
| `prysm-beacon-chain:local` | the beacon node |
| `prysm-validator:local` | the validator client, behind an entrypoint shim |
| `prysm-genesis-gen:local` | patched `ethereum-genesis-generator` |

The script builds `beacon-chain`, `validator` and `prysmctl` statically (cgo for
blst, `netgo,osusergo` so nothing reaches for glibc's NSS), then builds the three
images. Each is tagged `:local` and with the working copy's change id. Nothing is
pushed; kurtosis reads the local docker daemon.

The generator image is where every chain-config value has to land:
`cl_extra_params` cannot carry a file that is not in the container, and
ethereum-package builds both the CL config and the EL genesis out of that image.
`kurtosis/genesis-gen/patch-generator.sh` adds or rewrites the CL config template
lines; `kurtosis/Dockerfile.genesis-gen` holds the `ENV` defaults;
`ethereum_genesis_generator_params.extra_env` in the args file overrides both.

## 3. The args file

`kurtosis/network_params.yaml`, complete:

```yaml
participants:
  - el_type: geth
    # Pinned, not :latest. geth master rejects every forkchoiceUpdatedV4
    # without the ePBS builder-deposit system contract, which
    # ethereum-genesis-generator 6.0.2 does not deploy.
    el_image: ethpandaops/geth:glamsterdam-devnet-8
    cl_type: prysm
    cl_image: prysm-beacon-chain:local
    vc_type: prysm
    vc_image: prysm-validator:local
    use_separate_vc: true
    # Fulu is at epoch 0 and the package refuses to start a PeerDAS network
    # unless a node is a supernode. Full custody everywhere also keeps
    # sampling-driven column fetches out of the attestation measurements.
    supernode: true
    count: 6
    cl_extra_params:
      # One log line per availability head vote and per drop, which is what
      # the seat reconciliation reads.
      - --goldfish-vote-ledger
      # Default is 6, and a 6-node enclave offers each node only 5 peers, so
      # the subnet-peer search would never settle. See Parameters.
      - --minimum-peers-per-subnet=5
    vc_extra_params:
      # Cast the FFG attestation at slot start (plus <=200 ms jitter) instead
      # of on block arrival, so publish time does not depend on block
      # propagation. VC-only flag. Do not set --decoupled-ffg-vote-jitter;
      # its default is already 200 ms.
      - --decoupled-ffg-vote-at-slot-start

network_params:
  network: kurtosis
  network_id: "3151908"
  preset: mainnet
  seconds_per_slot: 6
  slot_duration_ms: 6000
  # 6 x 22 = 132 validators. See Parameters for why the total stays above 128.
  num_validator_keys_per_node: 22
  # Enough for six nodes' images, keys and genesis before slot 0.
  genesis_delay: 180

  # Genesis is Heze: prysmctl builds the Heze state directly, nothing upgrades
  # into it at runtime, so every fork is at epoch 0. Gloas must be 0 too --
  # that is what puts amsterdamTime on the EL genesis, which
  # forkchoiceUpdatedV4 requires.
  deneb_fork_epoch: 0
  electra_fork_epoch: 0
  fulu_fork_epoch: 0
  gloas_fork_epoch: 0
  heze_fork_epoch: 0

  # An explicit single-entry BLOB_SCHEDULE: the generator builds it out of the
  # BPO_* vars, so exactly one non-default BPO gives exactly one entry.
  bpo_1_epoch: 0
  bpo_1_max_blobs: 6
  bpo_1_target_blobs: 3
  bpo_2_epoch: 18446744073709551615

ethereum_genesis_generator_params:
  image: prysm-genesis-gen:local
  extra_env:
    # Four rounds to the 32-slot epoch.
    SLOTS_PER_ROUND: 8
    # How far into the slot an availability attestation is due, in basis
    # points of the slot.
    AVAILABLE_ATTESTATION_DUE_BPS_HEZE: 2500
    # The generator's CL template reads SECONDS_PER_SLOT from this variable
    # and the package exports only SLOT_DURATION_MS, so without this line the
    # config ships the template default of 12 next to a 6s clock and duties
    # run on a 12s cadence. Required whenever seconds_per_slot is not 12.
    SLOT_DURATION_IN_SECONDS: 6
    # One committee per slot, holding the whole V/SLOTS_PER_ROUND pool.
    TARGET_COMMITTEE_SIZE: 3000
    # Subnet count == committees per slot, so every node sees every raw vote.
    ATTESTATION_SUBNET_COUNT: 1
    # Load-bearing: at 2 a node would take out two long-lived subscriptions to
    # the same subnet 0.
    SUBNETS_PER_NODE: 1

additional_services: []
wait_for_finalization: false
global_log_level: info
```

## 4. Run

```sh
kurtosis run --enclave decoupled ../ethereum-package \
    --args-file kurtosis/network_params.yaml
kurtosis enclave inspect decoupled
kurtosis service logs decoupled cl-1-prysm-geth --follow
```

## 5. Verify

**The config shipped.** It lands at `/network-configs/config.yaml` on every
beacon node and every validator client, and is passed as `--chain-config-file`.

```sh
cid=$(docker ps --filter name=cl-1-prysm-geth -q)
for k in SLOTS_PER_ROUND TARGET_COMMITTEE_SIZE ATTESTATION_SUBNET_COUNT SUBNETS_PER_NODE; do
    docker exec "$cid" grep -c "^$k" /network-configs/config.yaml
    docker exec "$cid" grep    "^$k" /network-configs/config.yaml
done
```

Each count must be `1`, then the values `8`, `3000`, `1`, `1`. A count of `2`
means a template line was inserted where it should have been replaced.

**The VC flag.**

```sh
kurtosis service logs decoupled vc-1-geth-prysm | grep -i decoupled-ffg-vote-at-slot-start
for c in $(docker ps --filter name=vc- -q); do
    docker inspect --format '{{json .Args}}' "$c" | grep -c decoupled-ffg-vote-at-slot-start
done
```

The log line comes from the feature-flag banner at startup. Expect the flag
exactly once on every validator client's argv and on no beacon node's.

**The committee shape**, once a few slots have passed:

```sh
curl -s "http://127.0.0.1:<cl-http-port>/eth/v1/beacon/states/head/committees?slot=5" \
    | jq '[.data[] | {index, n: (.validators|length)}]'
```

Expect exactly one entry, `index: 0`, holding `V / SLOTS_PER_ROUND` validators
(`132 / 8 = 16` for the args file above). The same fact is in the beacon logs
under `--goldfish-vote-ledger`:

```sh
docker logs <cl-1 container> 2>&1 | grep 'FFG vote' \
    | grep -o 'committeeIndex=[0-9]*' | sort -u     # only committeeIndex=0
```

**Nothing dropped by gossipsub.** `p2p_pubsub_undeliverable_total` on the
`beacon_attestation_*` family must stay at 0 across the measurement window. It is
the only trace of a message gossipsub dropped for a full subscriber buffer: such
a message never reaches validation and never reaches the app, so no other counter
moves. One attestation subnet delivers a whole slot's votes in one burst, which
is why the fork raises that buffer well above the 32-message default.

```sh
kurtosis/scrape.sh decoupled <outdir> 6            # one metrics sample per slot
kurtosis/summarize.py <outdir> --slot-seconds 6 --skip-slots 32
```

`p2p_pubsub_topic_active` in the same output should show a single
`beacon_attestation_*` topic per node.

## Measure

```sh
kurtosis/scrape.sh <enclave> <outdir> <seconds_per_slot>
kurtosis/summarize.py <outdir> --slot-seconds <seconds_per_slot> --skip-slots 32
docker logs <each cl container> > <logdir>/cl-N.log
kurtosis/votetally.py <logdir> --validators <V>
kurtosis/vclogs.py <logdir>
```

`votetally.py --validators` reconstructs the seat schedule from the number you
give it, so passing the run's real total validator count is not optional.
`kurtosis/elscan.py <el-rpc-url>` reports blob gas per execution block, and
`go run ./kurtosis/blobsend -rpc http://127.0.0.1:<el-rpc> -interval 6s` drives
blob traffic if a run needs payloads that are not empty.

## Parameters

Node count (`participants[0].count`) and validators per node
(`network_params.num_validator_keys_per_node`) are free. Their consequences:

**Committee size.** Committees per slot is
`V / SLOTS_PER_ROUND / TARGET_COMMITTEE_SIZE`, clamped to at least 1. With
`SLOTS_PER_ROUND: 8` and a target of 3000 that floors to 0 for any `V < 48000`,
so the clamp returns one committee holding the whole `V/8` pool. The committee
size is simply `V/8`.

| V | pool = V/8 | committees/slot | committee size |
|---|---|---|---|
| 132 | 16 | 1 | 16 |
| 400 | 50 | 1 | 50 |
| 2000 | 250 | 1 | 250 |
| 20000 | 2500 | 1 | 2500 |
| 48000 | 6000 | **2** | 3000 |

Above `V = 48000` a second committee forms and the one-committee/one-subnet rule
breaks; `ATTESTATION_SUBNET_COUNT` would have to rise with it.

**Aggregators per slot** are `committee_size / 16`, floored at 1. A 16-seat
committee gets exactly one aggregator; anything above 32 seats gets more than
one.

**Keep the total above ~128 validators.** `prysmctl testnet generate-genesis`
does not return when there are too few validators to fill the payload-timeliness
committee window. Shrink `num_validator_keys_per_node` as you raise `count`, not
the total.

**Peers per subnet at small N.** `--minimum-peers-per-subnet` defaults to 6, and
an N-node enclave offers each node N-1 peers, so at `N <= 6` the subnet-peer
search never settles and re-runs every slot. Either run `N >= 8` or pass
`--minimum-peers-per-subnet=<N-1>` in `cl_extra_params`, as the args file above
does.

**Gossip scoring turns on above 128 validators.** Attestation-subnet peer scoring
is skipped while the active validator count is below
`ATTESTATION_SUBNET_COUNT * SLOTS_PER_EPOCH * 8 / 2`. At 64 subnets that is 8192
and scoring never engaged; at 1 subnet it is **128**, so any run with `V >= 128`
scores attestation-subnet peers. The scoring model expects `V/SLOTS_PER_EPOCH`
messages per subnet per slot while the fork delivers `V/SLOTS_PER_ROUND`, a 4x
over-delivery. Over-delivery is capped rather than penalised, but if peers start
scoring each other down on subnet 0, this is where to look.

**Log volume.** `--goldfish-vote-ledger` writes roughly `min(V, 512) + V/8` lines
per node per slot, plus aggregates and inclusions. The availability-attestation
committee is a fixed 512 seats, so below `V = 512` validators hold several seats
each and the topic carries V messages per slot; at or above 512 it carries 512.

**Genesis time.** Genesis builds one keystore per key plus the registry. If
`kurtosis run` reports nodes starting after slot 0, raise `genesis_delay`.

## Things that are normal

- **Config parse errors at startup.** The generator's CL template carries keys
  this build does not have. Prysm parses the file strictly, logs one error line
  and carries on; the values are unused. A key absent from the file keeps its
  mainnet default.
- **Deposit-poller chain-id mismatch.** kurtosis' network id versus the config's.
  It only disables deposit following.

## Things that are not

- **The EL is pinned.** `ethpandaops/geth:glamsterdam-devnet-8`. Newer geth
  expects the ePBS builder-deposit system contract in the EL genesis alloc and
  answers every `forkchoiceUpdatedV4` with `empty system contract: no code at
  0x0000bFF46984e3725691FA540a8C7589300D8282`, so no proposer ever gets a local
  payload and the chain sits at slot 0. Whoever bumps the EL has to teach the
  generator that contract first.
- **Heze must stay CL-only.** The upstream generator maps every CL fork to the
  next EL fork by ordinal, so Heze would schedule `bogotaTime`; geth then demands
  the next engine-API version while Prysm keeps calling `forkchoiceUpdatedV4` for
  its Gloas-shaped blocks, every fcu fails, and the chain stalls at the boundary.
  `patch-generator.sh` disables `genesis_add_heze` for exactly this reason.
- **The Prysm VC must talk gRPC.** Its REST client has no Gloas/Heze SSZ block
  codec and panics the first time a duty comes due. ethereum-package passes
  `--beacon-rest-api-provider` unconditionally and Prysm enables the REST client
  on the flag's mere presence, which no `vc_extra_params` value can undo — the
  validator image's entrypoint shim strips the flag instead.
