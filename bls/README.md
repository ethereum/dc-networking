# BLS-era material

[ACDC #191](https://forkcast.org/calls/acdc/191) (2026-11-12) dropped BLS
decoupled consensus: DC work targets post-quantum signatures from the start
([`research/pq/`](../research/pq/README.md)). The files here assumed BLS. They
are kept for reference and no longer maintained.

- [`explainer.md`](explainer.md): the BLS-era proposal. One cohort per slot,
  a 16 s vote window, VRF duties, a 12.5 kB bitfield per subround. Was
  `design/explainer.md`.
- [`ssz.md`](ssz.md): wire objects and byte accounting on the
  `simplex-healing` containers, with 96 B BLS signatures. Was `research/ssz.md`.
- [`fg.md`](fg.md), [`fg-ideas.md`](fg-ideas.md): early FG notes, the second
  titled "[Pre-PQ]". Were `research/fg/fg.md` and `research/fg/ideas.md`.

Still BLS-based elsewhere:

- Q17–Q19 in [`research/fg/`](../research/fg/): the schedule logic stays
  relevant. The parts that assume BLS are flagged at the top of each note.
- [`benchmarking/`](../benchmarking/): every devnet and simulation run so far
  carries BLS votes.
- [`personal/yann/mumbai-dc-networking-bls.html`](../personal/yann/mumbai-dc-networking-bls.html):
  the Mumbai networking breakout deck (2026-11-02).
