#!/usr/bin/env python3
r"""Turn a Shadow run's beacon-chain logs into queryable parquet tables, with duckdb.

    ./logs-to-parquet.py <data-dir> parquet/<label>
    ./logs-to-parquet.py <data-dir> parquet/<label> --validate
    ./logs-to-parquet.py <data-dir> parquet/<label> --validate-only
    ./logs-to-parquet.py <data-dir> parquet/<label> --print-sql > <label>.sql

DuckDB is the engine.  It globs ``<run>/**/prysm/logs/beacon-chain.log``, reads
every log as one row per line, pulls the logfmt fields out with
``regexp_extract`` in SQL, and ``COPY (...) TO '<table>.parquet' (FORMAT
PARQUET)``.  This script only builds that SQL and hands it to the ``duckdb``
CLI; it never touches a log line.  ``--print-sql`` gives you the same script to
run by hand: ``./logs-to-parquet.py <data-dir> out --print-sql | duckdb``.

Parsing accounting is strict and lands in parquet, not in a log message:

    lines = matched_any + unmatched              (file_summary.parquet)
    matched = parsed + failed, per file, per table   (parse_stats.parquet)

A line "matches" a table when it carries that table's ``msg=`` marker.  It is
then either parsed into a row or counted as a failure -- never dropped quietly.
A row counts as parsed when every ``required`` field came back non-null
(``try_cast`` / ``try_strptime`` turn a malformed field into a null, not an
error), so ``matched = parsed + failed`` holds by construction.  The driver
prints both identities and exits non-zero if either fails to balance.


Tables
======

Every table carries ``node`` ("node7"), ``node_index`` (7, for sorting) and
``ts`` (the sim clock).  Join keys are (node, slot) and, where a validator is
involved, (node, slot, validator).

Adding a table is one entry in TABLES below: a ``msg=`` marker, the log fields
you want, and which of them must be present for the row to count as parsed.
The ffg_votes / ffg_inclusions entries are exactly that -- they are empty on
runs built before prysm 3cb8aa37 and fill in by themselves from run 25 on.

goldfish_votes -- msg="Goldfish vote", one row per availability (head) vote
    vote_slot, validator, seats, outcome, reason, class, arrived_ms,
    decided_ms, block_root, source
    outcome is accepted | local | queued | replayed | dropped; ``class`` is
    outcome with the drop reason appended ("dropped:slot_zero").
    The terminal outcomes are accepted, local, replayed and dropped.  "queued"
    and "replayed" are the same vote seen twice -- parked, then landed -- so
    counting queued as well double-counts.

finality_progression -- msg="Synced new block", the per-slot chain view
    slot, epoch, slot_in_epoch, block_root, block_hash, parent_root,
    parent_hash, justified_round, justified_root, finalized_round,
    finalized_root, finalized_slot, since_slot_start_ms,
    chain_service_processed_ms, builder_index, version

received_blocks -- msg="Received block", gossip arrival of each block
    slot, proposer_index, since_slot_start_ms, validation_time_ms, graffiti

payload_envelopes -- msg="Synced execution payload envelope"
    slot, block_root, block_hash, parent_hash

state_transitions -- msg="Finished applying state transition"
    slot, attestations, sync_bits_count, blob_kzg_commitment_count,
    builder_index, payload_hash, parent_hash

payload_attestations -- msg="Submitted payload attestation message"
    slot, validator_index, block_root

ffg_votes -- msg="FFG vote", one row per FFG attestation (prysm >= 3cb8aa37)
    att_slot, target_round, committee_index, validator, seats, outcome,
    arrived_ms, data_root, block_root.  outcome is gossip | local.
    data_root is the pool's grouping key -- two votes aggregate together
    exactly when it matches -- and block_root is the head the vote named.
    Both are empty on runs built before prysm f8ccc75f.

payload_ledger -- msg="Payload envelope", one row per envelope a node imported
    slot, block_root, builder_index, arrived_ms, tx_count, payload_bytes,
    gas_used, blob_count.  Every delivery route lands here -- gossip, the
    pending queue, a by-root fetch, initial sync, and the proposer's own
    publish -- so it is one row per envelope per node, not one per route.
    arrived_ms shares the vote ledger's clock basis (ms into the envelope's own
    slot), so payload arrival and vote arrival are directly comparable.
    blob_count is absent when the state carried no bid, so it can be null.

ptc_votes -- msg="PTC vote", one row per payload attestation a node took in
    slot, block_root, validator_index, payload_present, blob_data_available,
    arrived_ms, outcome ("gossip" incl. replayed, or "local")

data_columns -- msg="Data column", one row per data column sidecar
    slot, block_root, column_index (0-127), kzg_commitment_count, arrived_ms,
    outcome.  outcome is gossip | local: gossip fires on live gossip and on the
    Gloas pending-queue drain (carrying the true arrival time), local is a
    column the node built or reconstructed itself.  A proposer self-publishes
    its own 128 columns and logs none of them, so per-node counts are lower on
    the proposing node for its own slot.

ffg_aggregates -- msg="FFG aggregate", one row per aggregate seen or produced
    att_slot, target_round, committee_index, aggregator_index, seats,
    outcome, arrived_ms, validators.  outcome is gossip | local; validators is
    the comma-separated validator indices the aggregation bits name, so the
    seats of an aggregate can be joined back to the votes that filled them.

ffg_inclusions -- msg="FFG vote included", one row per attestation in a block
    att_slot, block_slot, inclusion_slots, committee_index, seats, validators,
    data_root, block_root.  validators is the same comma-separated naming of
    the included seats.

ffg_aggregate_groups -- msg="FFG aggregate groups", one row per aggregation duty
    att_slot, committee_index, aggregator_index, groups, chosen_data,
    chosen_seats, group_seats.  group_seats is the raw rendering
    "dataRoot8:blockRoot8:seats,..." sorted by seats descending; each group's
    seats is a bit UNION over that group's candidates, while chosen_seats is
    the single published attestation's own bit count.  Explode it with
    string_split / unnest when you need per-group rows.

parse_stats -- one row per (log file, table): matched, parsed, failed
file_summary -- one row per log file: lines, matched_any, unmatched


Validation
==========

``--validate`` runs exactly these queries against the written parquet and
prints their rows.  Nothing is interpreted: a check either returns zero rows
(exact) or returns the offending rows with their delta.  Run them by hand with
``duckdb -c "<query>"`` from this directory.

1. Seat conservation.  Every slot >= 1 must carry seats_per_slot * nodes
   terminal seats (512 * 128 = 65536 in run 23).  Zero rows = exact.

    SELECT vote_slot, sum(seats) AS seats, sum(seats) - 65536 AS delta
    FROM 'parquet/<label>/goldfish_votes.parquet'
    WHERE vote_slot >= 1 AND outcome IN ('accepted', 'local', 'replayed')
    GROUP BY vote_slot HAVING sum(seats) <> 65536
    ORDER BY vote_slot;

2. Slot 0 is its own shape -- the votes that arrive before the chain exists:

    SELECT class, count(*) AS rows, sum(seats) AS seats
    FROM 'parquet/<label>/goldfish_votes.parquet'
    WHERE vote_slot = 0 GROUP BY 1 ORDER BY 1;

3. First justification and first finalization, and whether every node agrees
   on the slot at which it happened (nodes = 128, min_slot = max_slot):

    SELECT 'justified' AS what, min(justified_round) AS round FROM ...
    -- see FIRST_ROUND_SQL below; it reports round, min/max slot, node count.

4. Nothing was dropped on the floor during conversion:

    SELECT "table", sum(matched) AS matched, sum(parsed) AS parsed,
           sum(failed) AS failed
    FROM 'parquet/<label>/parse_stats.parquet' GROUP BY 1 ORDER BY 1;

    SELECT sum(lines) AS lines, sum(matched_any) AS matched,
           sum(unmatched) AS unmatched
    FROM 'parquet/<label>/file_summary.parquet';

Everyday question -- vote arrival distribution per slot:

    SELECT vote_slot, count(*) AS votes,
           quantile_cont(arrived_ms, 0.5) AS p50_ms,
           quantile_cont(arrived_ms, 0.95) AS p95_ms, max(arrived_ms) AS max_ms
    FROM 'parquet/<label>/goldfish_votes.parquet'
    WHERE outcome = 'accepted' GROUP BY vote_slot ORDER BY vote_slot;
"""

import argparse
import os
import shutil
import subprocess
import sys

# (column, log field, sql type). "duration" means a Go duration string -> ms.
TABLES = {
    "goldfish_votes": {
        "marker": "Goldfish vote",
        "required": ["ts", "vote_slot", "validator", "outcome"],
        "order": "node_index, vote_slot, validator",
        "columns": [
            ("vote_slot", "voteSlot", "INTEGER"),
            ("validator", "validator", "INTEGER"),
            ("seats", "seats", "INTEGER"),
            ("outcome", "outcome", "VARCHAR"),
            ("reason", "reason", "VARCHAR"),
            ("arrived_ms", "arrivedMs", "INTEGER"),
            ("decided_ms", "decidedMs", "INTEGER"),
            ("block_root", "blockRoot", "VARCHAR"),
            ("source", "package", "VARCHAR"),
        ],
        # outcome plus the drop reason, so "dropped:slot_zero" is one value.
        "derived": [("class", "outcome || coalesce(':' || reason, '')")],
    },
    "finality_progression": {
        "marker": "Synced new block",
        "required": ["ts", "slot", "justified_round", "finalized_round"],
        "order": "node_index, slot",
        "columns": [
            ("slot", "slot", "INTEGER"),
            ("epoch", "epoch", "INTEGER"),
            ("slot_in_epoch", "slotInEpoch", "INTEGER"),
            ("block_root", "block", "VARCHAR"),
            ("block_hash", "blockHash", "VARCHAR"),
            ("parent_root", "parentRoot", "VARCHAR"),
            ("parent_hash", "parentHash", "VARCHAR"),
            ("justified_round", "justifiedRound", "INTEGER"),
            ("justified_root", "justifiedRoot", "VARCHAR"),
            ("finalized_round", "finalizedRound", "INTEGER"),
            ("finalized_root", "finalizedRoot", "VARCHAR"),
            ("finalized_slot", "finalizedSlot", "INTEGER"),
            ("since_slot_start_ms", "sinceSlotStartTime", "duration"),
            ("chain_service_processed_ms", "chainServiceProcessedTime", "duration"),
            ("builder_index", "builderIndex", "VARCHAR"),
            ("version", "version", "VARCHAR"),
        ],
    },
    "received_blocks": {
        "marker": "Received block",
        "required": ["ts", "slot"],
        "order": "node_index, slot",
        "columns": [
            ("slot", "blockSlot", "INTEGER"),
            ("proposer_index", "proposerIndex", "INTEGER"),
            ("since_slot_start_ms", "sinceSlotStartTime", "duration"),
            ("validation_time_ms", "validationTime", "duration"),
            ("graffiti", "graffiti", "VARCHAR"),
        ],
    },
    "payload_envelopes": {
        "marker": "Synced execution payload envelope",
        "required": ["ts", "slot"],
        "order": "node_index, slot",
        "columns": [
            ("slot", "slot", "INTEGER"),
            ("block_root", "blockRoot", "VARCHAR"),
            ("block_hash", "blockHash", "VARCHAR"),
            ("parent_hash", "parentHash", "VARCHAR"),
        ],
    },
    "state_transitions": {
        "marker": "Finished applying state transition",
        "required": ["ts", "slot"],
        "order": "node_index, slot",
        "columns": [
            ("slot", "slot", "INTEGER"),
            ("attestations", "attestations", "INTEGER"),
            ("sync_bits_count", "syncBitsCount", "INTEGER"),
            ("blob_kzg_commitment_count", "blobKzgCommitmentCount", "INTEGER"),
            ("builder_index", "builderIndex", "VARCHAR"),
            ("payload_hash", "payloadHash", "VARCHAR"),
            ("parent_hash", "parentHash", "VARCHAR"),
        ],
    },
    "payload_attestations": {
        "marker": "Submitted payload attestation message",
        "required": ["ts", "slot", "validator_index"],
        "order": "node_index, slot, validator_index",
        "columns": [
            ("slot", "slot", "INTEGER"),
            ("validator_index", "validatorIndex", "INTEGER"),
            ("block_root", "blockRoot", "VARCHAR"),
        ],
    },
    # Empty before prysm 3cb8aa37; the FFG ledger lines start in run 25.
    "ffg_votes": {
        "marker": "FFG vote",
        "required": ["ts", "att_slot", "outcome"],
        "order": "node_index, att_slot, validator",
        "columns": [
            ("att_slot", "attSlot", "INTEGER"),
            ("target_round", "targetRound", "INTEGER"),
            ("committee_index", "committeeIndex", "INTEGER"),
            ("validator", "validator", "INTEGER"),
            ("seats", "seats", "INTEGER"),
            ("outcome", "outcome", "VARCHAR"),
            ("arrived_ms", "arrivedMs", "INTEGER"),
            ("data_root", "dataRoot", "VARCHAR"),
            ("block_root", "blockRoot", "VARCHAR"),
            ("source", "package", "VARCHAR"),
        ],
    },
    "ffg_aggregates": {
        "marker": "FFG aggregate",
        "required": ["ts", "att_slot", "outcome"],
        "order": "node_index, att_slot, committee_index, aggregator_index",
        "columns": [
            ("att_slot", "attSlot", "INTEGER"),
            ("target_round", "targetRound", "INTEGER"),
            ("committee_index", "committeeIndex", "INTEGER"),
            ("aggregator_index", "aggregatorIndex", "INTEGER"),
            ("seats", "seats", "INTEGER"),
            ("outcome", "outcome", "VARCHAR"),
            ("arrived_ms", "arrivedMs", "INTEGER"),
            ("data_root", "dataRoot", "VARCHAR"),
            ("block_root", "blockRoot", "VARCHAR"),
            ("validators", "validators", "VARCHAR"),
        ],
    },
    # One row per execution payload envelope, whatever route delivered it.
    "payload_ledger": {
        "marker": "Payload envelope",
        "required": ["ts", "slot"],
        "order": "node_index, slot",
        "columns": [
            ("slot", "slot", "INTEGER"),
            ("block_root", "blockRoot", "VARCHAR"),
            ("builder_index", "builderIndex", "INTEGER"),
            ("arrived_ms", "arrivedMs", "INTEGER"),
            ("tx_count", "txCount", "INTEGER"),
            ("payload_bytes", "payloadBytes", "BIGINT"),
            ("gas_used", "gasUsed", "BIGINT"),
            ("blob_count", "blobCount", "INTEGER"),
        ],
    },
    # One row per data column sidecar a node saw or built.
    "data_columns": {
        "marker": "Data column",
        "required": ["ts", "slot", "column_index"],
        "order": "node_index, slot, column_index",
        "columns": [
            ("slot", "slot", "INTEGER"),
            ("block_root", "blockRoot", "VARCHAR"),
            ("column_index", "columnIndex", "INTEGER"),
            ("kzg_commitment_count", "kzgCommitmentCount", "INTEGER"),
            ("arrived_ms", "arrivedMs", "INTEGER"),
            ("outcome", "outcome", "VARCHAR"),
        ],
    },
    # One row per payload attestation (PTC vote) a node took in. outcome is
    # "gossip" for one accepted off the PTC topic, including one replayed once
    # its block landed, and "local" for one this node's own PTC member
    # published, which never traverses gossip.
    "ptc_votes": {
        "marker": "PTC vote",
        "required": ["ts", "slot", "validator_index"],
        "order": "node_index, slot, validator_index",
        "columns": [
            ("slot", "slot", "INTEGER"),
            ("block_root", "blockRoot", "VARCHAR"),
            ("validator_index", "validatorIndex", "INTEGER"),
            ("payload_present", "payloadPresent", "VARCHAR"),
            ("blob_data_available", "blobDataAvailable", "VARCHAR"),
            ("arrived_ms", "arrivedMs", "INTEGER"),
            ("outcome", "outcome", "VARCHAR"),
        ],
    },
    # One row per aggregation duty: how the duty's candidates split by data.
    "ffg_aggregate_groups": {
        "marker": "FFG aggregate groups",
        "required": ["ts", "att_slot", "groups"],
        "order": "node_index, att_slot, committee_index, aggregator_index",
        "columns": [
            ("att_slot", "attSlot", "INTEGER"),
            ("committee_index", "committeeIndex", "INTEGER"),
            ("aggregator_index", "aggregatorIndex", "INTEGER"),
            ("groups", "groups", "INTEGER"),
            ("chosen_data", "chosenData", "VARCHAR"),
            ("chosen_seats", "chosenSeats", "INTEGER"),
            ("group_seats", "groupSeats", "VARCHAR"),
        ],
    },
    "ffg_inclusions": {
        "marker": "FFG vote included",
        "required": ["ts", "att_slot", "block_slot"],
        "order": "node_index, block_slot, att_slot, committee_index",
        "columns": [
            ("att_slot", "attSlot", "INTEGER"),
            ("block_slot", "blockSlot", "INTEGER"),
            ("inclusion_slots", "inclusionSlots", "INTEGER"),
            ("committee_index", "committeeIndex", "INTEGER"),
            ("seats", "seats", "INTEGER"),
            ("data_root", "dataRoot", "VARCHAR"),
            ("block_root", "blockRoot", "VARCHAR"),
            ("validators", "validators", "VARCHAR"),
        ],
    },
}

# fld() is the logfmt reader: key="quoted value" first, bare token second. The
# leading (?:^|\s) is what keeps `slot=` from matching inside `voteSlot=`.
PRELUDE = r"""
CREATE OR REPLACE MACRO fld(line, key) AS coalesce(
    nullif(regexp_extract(line, '(?:^|\s)' || key || '="([^"]*)"', 1), ''),
    nullif(regexp_extract(line, '(?:^|\s)' || key || '=([^\s"]\S*)', 1), ''));

-- Go duration strings: 39.46us, 6.55845ms, 0s. The micro sign is what Go
-- actually prints, so both spellings are here.
CREATE OR REPLACE MACRO dur_ms(v) AS
    try_cast(regexp_extract(v, '^([0-9.]+)', 1) AS DOUBLE) * CASE
        regexp_extract(v, '(ns|µs|us|ms|s|m)$', 1)
        WHEN 'ns' THEN 1e-6 WHEN 'µs' THEN 1e-3 WHEN 'us' THEN 1e-3
        WHEN 'ms' THEN 1.0 WHEN 's' THEN 1e3 WHEN 'm' THEN 6e4 END;

-- Materialised, not a view: every table below scans it once.
CREATE OR REPLACE TABLE loglines AS
SELECT regexp_extract(filename, '([^/]+)/prysm/logs/beacon-chain\.log$', 1) AS node,
       try_cast(regexp_extract(filename,
           '([0-9]+)/prysm/logs/beacon-chain\.log$', 1) AS INTEGER) AS node_index,
       filename, line
FROM read_csv('{glob}',
              columns = {{'line': 'VARCHAR'}}, delim = chr(1), quote = '',
              escape = '', header = false, all_varchar = true, filename = true);
"""

MATCHED_VIEW = """
CREATE OR REPLACE VIEW {name}__matched AS
SELECT node, node_index, filename,
       try_strptime(fld(line, 'time'), '%Y-%m-%d %H:%M:%S.%f') AS ts,
{exprs}
FROM loglines WHERE line LIKE '%msg="{marker}"%';
"""


def column_expr(col, key, typ):
    if typ == "duration":
        return "dur_ms(fld(line, '%s'))" % key
    if typ == "VARCHAR":
        return "fld(line, '%s')" % key
    return "try_cast(fld(line, '%s') AS %s)" % (key, typ)


def build_sql(run_dir, out_dir):
    """The whole conversion, as one self-contained SQL script."""
    glob = "%s/**/prysm/logs/beacon-chain.log" % run_dir.rstrip("/")
    parts = [PRELUDE.format(glob=glob)]

    for name, spec in TABLES.items():
        exprs = ",\n".join("       %s AS %s" % (column_expr(*c), c[0])
                           for c in spec["columns"])
        parts.append(MATCHED_VIEW.format(name=name, marker=spec["marker"], exprs=exprs))
        ok = " AND ".join("%s IS NOT NULL" % r for r in spec["required"])
        cols = ", ".join(c[0] for c in spec["columns"])
        cols += "".join(", %s AS %s" % (e, c) for c, e in spec.get("derived", ()))
        parts.append(
            "COPY (SELECT node, node_index, ts, {cols} FROM {name}__matched\n"
            "      WHERE {ok} ORDER BY {order})\n"
            "  TO '{out}/{name}.parquet' (FORMAT PARQUET, COMPRESSION ZSTD);\n".format(
                cols=cols, name=name, ok=ok, order=spec["order"], out=out_dir))
        parts.append(
            "CREATE OR REPLACE VIEW {name}__stats AS\n"
            "SELECT filename AS file, node, '{name}' AS \"table\", count(*) AS matched,\n"
            "       count(*) FILTER (WHERE {ok}) AS parsed,\n"
            "       count(*) FILTER (WHERE NOT ({ok})) AS failed\n"
            "FROM {name}__matched GROUP BY 1, 2;\n".format(name=name, ok=ok))

    union = "\nUNION ALL\n".join("SELECT * FROM %s__stats" % n for n in TABLES)
    parts.append("COPY (%s ORDER BY \"table\", node)\n"
                 "  TO '%s/parse_stats.parquet' (FORMAT PARQUET, COMPRESSION ZSTD);\n"
                 % (union, out_dir))

    # Every line of every log is either matched by some marker or explicitly
    # counted as unmatched, so nothing can go missing between log and parquet.
    any_marker = "\n            OR ".join(
        "line LIKE '%%msg=\"%s\"%%'" % s["marker"] for s in TABLES.values())
    parts.append(
        "COPY (SELECT filename AS file, node, node_index, count(*) AS lines,\n"
        "             count(*) FILTER (WHERE {m}) AS matched_any,\n"
        "             count(*) FILTER (WHERE NOT ({m})) AS unmatched\n"
        "      FROM loglines GROUP BY 1, 2, 3 ORDER BY node_index)\n"
        "  TO '{out}/file_summary.parquet' (FORMAT PARQUET, COMPRESSION ZSTD);\n".format(
            m=any_marker, out=out_dir))
    return "\n".join(parts)


ACCOUNTING_SQL = """
.print
.print == parse accounting: matched = parsed + failed, per table
SELECT "table", sum(matched) AS matched, sum(parsed) AS parsed,
       sum(failed) AS failed, sum(matched) - sum(parsed) - sum(failed) AS delta
FROM '{out}/parse_stats.parquet' GROUP BY 1 ORDER BY 1;

.print == per-file parse failures (zero rows = none)
SELECT file, "table", matched, parsed, failed
FROM '{out}/parse_stats.parquet' WHERE failed > 0 ORDER BY failed DESC LIMIT 50;

.print == line accounting: lines = matched_any + unmatched
SELECT count(*) AS files, sum(lines) AS lines, sum(matched_any) AS matched_any,
       sum(unmatched) AS unmatched,
       sum(lines) - sum(matched_any) - sum(unmatched) AS delta,
       (SELECT sum(matched) FROM '{out}/parse_stats.parquet') AS matched_per_table,
       (SELECT sum(matched) FROM '{out}/parse_stats.parquet') - sum(matched_any)
           AS double_matched
FROM '{out}/file_summary.parquet';

.print == rows written per table
{rowcounts}
"""

VALIDATE_SQL = """
.print
.print == 1. seat conservation, slots >= 1 (zero rows = exact {expect} everywhere)
SELECT vote_slot, sum(seats) AS seats, sum(seats) - {expect} AS delta
FROM '{out}/goldfish_votes.parquet'
WHERE vote_slot >= 1 AND outcome IN ('accepted', 'local', 'replayed')
GROUP BY vote_slot HAVING sum(seats) <> {expect} ORDER BY vote_slot;

.print == 1b. slots covered and the seat total they carry
SELECT count(DISTINCT vote_slot) AS slots, min(vote_slot) AS first_slot,
       max(vote_slot) AS last_slot, sum(seats) AS terminal_seats,
       count(DISTINCT node) AS nodes
FROM '{out}/goldfish_votes.parquet'
WHERE vote_slot >= 1 AND outcome IN ('accepted', 'local', 'replayed');

.print == 2. slot 0 shape
SELECT class, count(*) AS rows, sum(seats) AS seats, count(DISTINCT node) AS nodes
FROM '{out}/goldfish_votes.parquet' WHERE vote_slot = 0 GROUP BY 1 ORDER BY 1;

.print == 2b. every outcome, all slots
SELECT class, count(*) AS rows, sum(seats) AS seats
FROM '{out}/goldfish_votes.parquet' GROUP BY 1 ORDER BY 1;

.print == 3. first justification / finalization, and node agreement
SELECT 'justified' AS what, min(justified_round) AS round,
       min(slot) AS first_slot, max(slot) AS last_slot,
       count(DISTINCT node) AS nodes
FROM '{out}/finality_progression.parquet'
WHERE justified_round = (SELECT min(justified_round)
                         FROM '{out}/finality_progression.parquet'
                         WHERE justified_round > 0)
UNION ALL
SELECT 'finalized', min(finalized_round), min(slot), max(slot),
       count(DISTINCT node)
FROM '{out}/finality_progression.parquet'
WHERE finalized_round = (SELECT min(finalized_round)
                         FROM '{out}/finality_progression.parquet'
                         WHERE finalized_round > 0);

.print == 3b. nodes that disagree on the first slot of round 1 (zero rows = all agree)
SELECT node, min(slot) FILTER (WHERE justified_round = 1) AS justified_at,
       min(slot) FILTER (WHERE finalized_round = 1) AS finalized_at
FROM '{out}/finality_progression.parquet'
GROUP BY node
HAVING justified_at IS DISTINCT FROM (
           SELECT min(slot) FROM '{out}/finality_progression.parquet'
           WHERE justified_round = 1)
    OR finalized_at IS DISTINCT FROM (
           SELECT min(slot) FROM '{out}/finality_progression.parquet'
           WHERE finalized_round = 1)
ORDER BY node;
"""


def run_duckdb(sql, duckdb_bin, threads):
    head = "SET threads = %d;\n.mode box\n" % threads
    proc = subprocess.run([duckdb_bin], input=head + sql, text=True)
    if proc.returncode:
        sys.exit("duckdb exited %d" % proc.returncode)


def main():
    ap = argparse.ArgumentParser(description="beacon logs -> parquet, via duckdb",
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", help="a finished run's data dir")
    ap.add_argument("out_dir", help="output dir for the parquet tables")
    ap.add_argument("--duckdb", default=os.environ.get("DUCKDB", "duckdb"))
    ap.add_argument("--threads", type=int, default=min(32, os.cpu_count() or 8))
    ap.add_argument("--print-sql", action="store_true",
                    help="write the generated SQL to stdout and stop")
    ap.add_argument("--validate", action="store_true",
                    help="run the seat/round reconciliation after converting")
    ap.add_argument("--validate-only", action="store_true",
                    help="skip conversion; run_dir is ignored")
    ap.add_argument("--seats", type=int, default=512, help="seats per slot per node")
    ap.add_argument("--nodes", type=int, default=128)
    args = ap.parse_args()

    sql = build_sql(args.run_dir, args.out_dir)
    if args.print_sql:
        print(sql)
        return

    duckdb_bin = shutil.which(args.duckdb) or args.duckdb
    if not shutil.which(duckdb_bin):
        sys.exit("duckdb CLI not found (looked for %r); set --duckdb or $DUCKDB"
                 % args.duckdb)

    if not args.validate_only:
        os.makedirs(args.out_dir, exist_ok=True)
        rowcounts = "\nUNION ALL\n".join(
            "SELECT '%s' AS \"table\", count(*) AS rows FROM '%s/%s.parquet'"
            % (n, args.out_dir, n) for n in TABLES)
        run_duckdb(sql + ACCOUNTING_SQL.format(
            out=args.out_dir, rowcounts=rowcounts + "\nORDER BY 1;"),
            duckdb_bin, args.threads)

    if args.validate or args.validate_only:
        run_duckdb(VALIDATE_SQL.format(out=args.out_dir,
                                       expect=args.seats * args.nodes),
                   duckdb_bin, args.threads)


if __name__ == "__main__":
    main()
