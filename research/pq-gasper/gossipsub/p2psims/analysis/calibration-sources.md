# Mainnet calibration sources (research subagent, fetched 2026-11-06)

Live pages (WonderNetwork, Probelab): archive before citing.

## 1. RTT (ms, WonderNetwork "Average", https://wondernetwork.com/pings/<A>/<B>, fetched 2026-11-06)
Key pairs: NYC-CHI 18, NYC-SFO 63, NYC-LON 70, NYC-FRA 91, NYC-AMS 76, NYC-PAR 82, NYC-HEL 116, NYC-SIN 228, NYC-TYO 166,
NYC-SEL 204, NYC-SYD 197, NYC-GRU 110; SFO-LON 140, SFO-FRA 156, SFO-SIN 173, SFO-TYO 104, SFO-SYD 149;
LON-FRA 18, LON-AMS 8, LON-PAR 8, LON-HEL 33, LON-SIN 155, LON-TYO 242, LON-SEL 232, LON-SYD 255, LON-GRU 193;
FRA-AMS 11, FRA-PAR 17, FRA-HEL 26, FRA-SIN 157, FRA-TYO 233, FRA-HKG 181, FRA-SYD 248; HEL-SIN 177, HEL-TYO 260;
SIN-TYO 66, SIN-SEL 83, SIN-HKG 30, SIN-SYD 92; TYO-SEL 31, TYO-HKG 90 (59 other dir), TYO-SYD 99; SEL-SYD 166;
HKG-SYD 127; SYD-GRU 313; SIN-GRU 324. Washington: NYC 7.6, CHI 21, SFO 61, LON 75, FRA 89, SIN 207, TYO 149.
Falkenstein: FRA 6.1, LON 25, AMS 12, HEL 34, NYC 96, SIN 152, TYO 271. Dublin: LON 11, FRA 26, NYC 84.
Jitter (mdev) small: NYC-LON 0.65, NYC-FRA 2.3. Asymmetric outliers (SEL-PAR 340 vs 242): use min or mean.
(Full 16x16 matrix in the subagent result; ask if needed.)

## 2. Geography / hosting
- Probelab countries, 24h, dialable discv5 CL nodes (~8,207): US 31.4, DE 15.5, FI 6.3, FR 5.3, JP 4.5, GB 4.2, CA 3.8,
  SG 3.6, NL 3.3, AU 1.9, other 20.1 %. https://probelab.io/ethereum/mainnet/charts/countries-avg/fullscreen/?max_agents=6&max_countries=10
- Cities (last crawl): Ashburn 6.9, Bockau DE (likely Hetzner Falkenstein) 6.4, Helsinki 6.1, Frankfurt 5.6, Tokyo 2.9,
  Singapore 2.8, London 2.1, NY/Dublin/Amsterdam ~1.5 each. US east 1,964 vs west 607. https://probelab.io/ethereum/mainnet/charts/peers-by-city-map/fullscreen/
- Cloud 64.9 % / non-cloud 35.1 % (dialable only). https://probelab.io/ethereum/mainnet/charts/cloud-prevalence-avg/fullscreen/?max_agents=6
- "Multiple Sides of 36 Coins" https://arxiv.org/pdf/2511.15388 (2025): hosting 0.76 / ISP 0.23; continents EU 46.5, NA 43.3, AS 6.2, SA 2.0, OC 1.7.
- Suggested 10-city mapping: Ashburn/NY ~28, US-West ~7, Frankfurt 15.5, Helsinki 6.3, Paris 5.3, London(+IE) 5.8,
  Amsterdam 3.3, Tokyo 4.5, Singapore 3.6, Sydney 1.9, Seoul 1.5; spread ~17 % over Europe; Sao Paulo 0.2.

## 3. Access links
- FCC MBA 13th report (data Sep-Oct 2022, last report) https://docs.fcc.gov/public/attachments/FCC-24-136A6.pdf:
  median idle RTT fiber 7-14 ms, cable 12-24, DSL 23-34 (by tier DSL 20-61); subscribers with >=1 % peak loss:
  DSL 0-4 %, cable 1-4 %, fiber 0-3 %. No jitter, no fixed wireless.
- ThousandEyes 2018 cloud benchmark: inter-region loss <0.1 %, jitter <0.1 ms.
- Estimates (unsourced): fixed wireless +25-40 ms, 0.5-1 % loss; residential jitter 1-5 ms.

## 4. Churn
- No Ethereum churn data from Probelab.
- 36 Coins (Apr-Sep 2025): Ethereum discv5 median daily retention ~80 %; <50 % of IPs up uninterrupted over 16 days (IP-based).
- Li et al. https://eprint.iacr.org/2025/588.pdf (Dec 2024): >2/3 of active discv5 nodes online consistently over 15 days.
- Estimate: restart every 2-4 weeks per node; model ~70-80 % stable, ~20 % cycling daily.

## 5. NAT / undialable
- Heimbach et al. USENIX Sec '25 https://www.usenix.org/system/files/usenixsecurity25-heimbach.pdf: 16.5K IPs/day discovered vs 8.1K reachable (~50 %, upper bound).
- Estimate 30-50 % undialable.

## 6. Clients and peer targets
- Probelab agents 24h: Lighthouse 50.5, Prysm 20.8, Nimbus 8.9, Teku 7.8, Lodestar 2.8, Erigon 2.1, Hermes 2.6, other 1.1 %.
- Defaults: Lighthouse target 200 (+10 % excess); Prysm max 70; Teku 64-100; Nimbus 160 (hard max 1.5x); Lodestar 200/210; Grandine 200.
  (Source links in the subagent result: sigp/lighthouse a376def peer_manager/config.rs L11, prysm cmd/flags.go L161-164, teku DiscoveryConfig L31-34,
  nimbus conf.nim L337-344, lodestar network/options.ts L57-58, grandine runtime/src/defaults.rs L18.)

## 7. Propagation (calibration targets)
- Block arrival after slot start, Xatu sentries 2026-11-05 (Probelab gossipsub-arrival-times-cdf): EU p50 1.98 / p90 3.42 / p99 4.11 s;
  NA 2.14 / 3.59 / 5.27; AS 2.13 / 3.59 / 4.67; OC 2.11 / 3.59 / 4.18.
- Prysm receiver post-BPO1 (Dec 2025): p50 1.77, p95 3.75, p99 3.97 s. https://ethresear.ch/t/block-blob-propagation-with-peerdas/23801
- Attestations (missed slots, pure propagation): mean +831 ms after 4 s; subnet supermajority <830 ms, p95 1,962 ms.
  https://ethresear.ch/t/an-analysis-of-attestation-timings-in-a-6-s-slot/23016
- Reldo 2026-02 (Xatu): attestations p50 4.63 / p95 9.5 s; aggregates p50 8.0 / p95 10.5 s; data columns p10 1.2 / p50 1.78 / p95 3.2 s.

## 8. Sizes / constants (consensus-specs 204fb4a)
- SUBNETS_PER_NODE 2, 64 attestation subnets, 128 custody groups / column subnets, SAMPLES_PER_SLOT 8, CUSTODY_REQUIREMENT 4,
  VALIDATOR_CUSTODY_REQUIREMENT 8, custody = clamp(balance/32 ETH, 8, 128) (supernode at 4,096 ETH).
- BPO2 max 21 blobs (target 14). DataColumnSidecar 356 + 2,144 x blobs B (30.4 KB at 14).
- SingleAttestation 240 B (~28k/slot at ~900k validators); aggregate ~500 B, ~1,040/slot; 512 sync msgs (144 B), ~64 contributions (360 B).
- Block compressed: 50-100 kB for 59.6 % of arrivals (Probelab heatmap 2026-11-05); EIP-7928 analysis avg 79 KiB snappy.
- Gossipsub: D 8/6/12, D_lazy 6, heartbeat 0.7 s, mcache 6/3, seen_ttl 2 epochs.

## 9. Bandwidth / duplicates
- Probelab Hermes node (Oct 30-Nov 6 2026), block+attestation+blob topics only: in ~163 kB/s median (p95 200), out ~194 kB/s (p95 315).
- Duplicates per unique msg 2026-11-05: beacon_block p50 3 / p90 6 / p99 8; attestation subnets p50 2 / p90 4 / p99 5-6;
  inbound duplicate bytes ~2.5x first-delivery bytes.
- Fusaka-devnet-5 (ethPandaOps, Oct 2025): full node ~4-8 Mb/s; validating node peaks 15-20 Mb/s (10 blobs), 17-25 (14); supernode rx ~200-400 Mb/s.

## 10. Verification costs
- DKKW hash-based XMSS (eprint 2025/055, M3 Pro, 1 thread): Poseidon2 TSW w=2 verify 351 us (2.65 KiB), w=4 603 us; SHA-3 w=2 26 us.
- leanSig (eprint 2025/1332): hash counts only, no timings. Estimate 0.3-0.6 ms per verify.
- BLS verify ~1.0-1.2 ms (estimate; c-kzg 2-pairing 0.80 ms). KZG cell proof batch ~54 us/cell; client data-column gossip verify p95 9-14 ms (Lodestar 126).

## 11. Peer scoring
- All clients: gossip -4000, publish -8000, graylist -16000, acceptPX 100, opportunistic graft 5 (Nimbus: acceptPX 0, graft 0).
- See eth_peer_score.rs (Lighthouse v8.3.2 port).
