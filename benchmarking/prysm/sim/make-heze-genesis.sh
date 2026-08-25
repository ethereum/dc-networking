#!/usr/bin/env bash
# Replace the generator's CL genesis with a Heze one built by prysmctl.
#
#   PRYSMCTL=path/to/prysmctl SIM_YAML=sim-100nodes-r1.yaml \
#       ./make-heze-genesis.sh <data-dir> <num-validators>
#
# Run this after "ethshadow --gen-only" and before Shadow.
#
# Binaries come from the environment: PRYSMCTL and GETH default to the names on
# PATH, SIM_YAML to sim.yaml.
#
# Why. ethshadow builds the CL genesis with ethpandaops'
# eth-genesis-state-generator. That tool tops out at a Gloas-shaped state, and
# even its Gloas state does not match this fork's container ("failed to
# unmarshal state, detected fork=gloas: invalid ssz encoding"). Genesis is Heze
# here and nothing upgrades into Heze - runtime/interop builds the Heze state
# directly - so prysmctl has to make it.
#
# The validator keystores come from eth2-val-tools over the mnemonic, so the
# genesis registry must hold exactly those pubkeys in that order. We therefore
# feed prysmctl a deposit_data.json for the same mnemonic and index range
# rather than its deterministic interop keys.
#
# The EL genesis is NOT rewritten. ethshadow has already run "geth init" for
# every node by the time this script runs, so the block prysmctl hashes has to
# be the block geth already stored. sim.yaml therefore sets GENESIS_TIMESTAMP
# to the real genesis instant and GENESIS_DELAY to 0, which is the only header
# field prysmctl would otherwise change. The script asserts the two hashes
# match before it writes anything.
set -euo pipefail

cd "$(dirname "$0")"
data_dir=${1:?usage: $0 <dataN> <num-validators>}
num_validators=${2:?usage: $0 <dataN> <num-validators>}
meta="$data_dir/metadata"
prysmctl=${PRYSMCTL:-prysmctl}
# SIM_YAML names the run's config; only the generator image is read out of it.
sim_yaml=${SIM_YAML:-sim.yaml}
image=$(grep -oP '(?<=generator_image: ).*' "$sim_yaml" | head -1)

val() { grep -oP "(?<=^export $1=\").*(?=\"$)" "$data_dir/values.env" | tail -1; }
mnemonic=$(val EL_AND_CL_MNEMONIC)
genesis_ts=$(val GENESIS_TIMESTAMP)
genesis_delay=$(val GENESIS_DELAY)
fork_version=$(val GENESIS_FORK_VERSION)
echo "genesis_ts=$genesis_ts delay=$genesis_delay fork_version=$fork_version"

# geth's ToBlock falls back to params.InitialBaseFee when baseFeePerGas is
# absent, which is what "geth init" already did; prysmctl refuses to guess, so
# write that same value in. The header is unchanged.
if [ "$(jq -r '.baseFeePerGas // "null"' "$meta/genesis.json")" = "null" ]; then
    chmod u+w "$meta/genesis.json"
    jq '.baseFeePerGas = "0x3b9aca00"' "$meta/genesis.json" > "$meta/genesis.json.tmp"
    mv "$meta/genesis.json.tmp" "$meta/genesis.json"
fi

# eth2-val-tools names the deposit amount "value"; prysmctl wants "amount".
docker run --rm -i --entrypoint eth2-val-tools "$image" deposit-data \
    --as-json-list \
    --source-min 0 --source-max "$num_validators" \
    --fork-version "$fork_version" \
    --withdrawal-credentials-type 0x00 \
    --validators-mnemonic "$mnemonic" \
    --withdrawals-mnemonic "$mnemonic" \
    | jq '[.[] | {pubkey, withdrawal_credentials, signature, deposit_data_root, amount: .value}]' \
    > "$meta/deposit_data.json"

# prysm's file writer refuses to overwrite a file that is not already 0600, and
# the generator ran as root in docker with a 0644 umask.
chmod 600 "$meta/genesis.ssz"

"$prysmctl" testnet generate-genesis \
    --fork heze \
    --num-validators "$num_validators" \
    --chain-config-file "$meta/config.yaml" \
    --deposit-json-file "$meta/deposit_data.json" \
    --geth-genesis-json-in "$meta/genesis.json" \
    --genesis-time "$genesis_ts" \
    --genesis-time-delay "$genesis_delay" \
    --output-ssz "$meta/genesis.ssz" \
    --output-json "$meta/genesis-state.json"

# Cross-check: the eth1 block the CL genesis names must be the block geth
# stored at init. A mismatch shows up at runtime only as "Unable to retrieve
# proof-of-stake genesis block data ... not found", and the chain never starts.
cl_hash=$(jq -r '.latest_block_hash' "$meta/genesis-state.json" \
    | base64 -d | xxd -p -c 32)
check_dir=$(mktemp -d -p /var/tmp genesis-check-XXXXXX)
el_hash=$("${GETH:-geth}" --datadir "$check_dir" \
    init "$meta/genesis.json" 2>&1 \
    | grep -oP '(?<=Successfully wrote genesis state).*hash=\K[0-9a-f.]+')
echo "CL genesis eth1 block hash: 0x$cl_hash"
echo "EL genesis block hash:      $el_hash (geth abbreviates)"
head=${el_hash%%..*}
tail=${el_hash##*..}
if [ "${cl_hash#"$head"}" = "$cl_hash" ] || [ "${cl_hash%"$tail"}" = "$cl_hash" ]; then
    echo "MISMATCH: the CL genesis names a block geth did not create." >&2
    echo "ethshadow ran 'geth init' before this script; the EL genesis must" >&2
    echo "already have its final timestamp when it does. See sim.yaml." >&2
    exit 1
fi

echo "wrote $meta/genesis.ssz ($(stat -c%s "$meta/genesis.ssz") bytes)"
