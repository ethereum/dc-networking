# Posts

Write-ups meant to be shared. Each is one Markdown file that GitHub renders as it is, with its figures in [`charts/`](charts/).

| Post | What it says | Behind it |
|---|---|---|
| [Can PQ Gasper run on gossipsub?](pq-gasper-on-gossipsub.md) | Not at 1,600 signatures per subnet per slot: home nodes keep up with about 300. | [`research/pq-gasper/gossipsub/`](../research/pq-gasper/gossipsub/README.md) |
| [What a node needs to carry one PQ Gasper subnet](pq-gasper-subnet-specs.md) | About 100 Mbit/s of download and 75 to 100 of upload, on a line that loses almost no packets. | The study's reports for [2,048](../research/pq-gasper/gossipsub/results/pq-gasper-subnet-specs.md) and [1,024 nodes](../research/pq-gasper/gossipsub/results/pq-gasper-subnet-specs-1024.md) |
| [Emergency PQ Consensus Could Rely on Builders](pq-gasper-builders.md) | An exploration: for one fork, the proposers of the last few slots, or their builders, publish each slot's aggregate for EIP-7870 nodes. | [`research/pq-gasper/builders/sim/`](../research/pq-gasper/builders/sim/) |

[`charts/generate_charts.py`](charts/generate_charts.py) draws the charts of the two gossipsub posts. [`builders_overview.py`](../research/pq-gasper/builders/sim/builders_overview.py) draws `builders-overview.svg` for the builders post, which embeds the PNG next to it.

## Pasting a post into HackMD

HackMD cannot follow relative links or load relative images. Print the post with absolute ones and paste that:

```sh
# from the repository root; before a merge: REPO=yannvon/dc-networking REF=<branch>
REPO=ethereum/dc-networking REF=main
RAW=https://raw.githubusercontent.com/$REPO/$REF BLOB=https://github.com/$REPO/blob/$REF
sed -E -e "s#\]\(charts/([^)]*\.(svg|png))\)#]($RAW/posts/charts/\1)#g" \
       -e "s#\]\((charts/|[a-z0-9-]+\.md)#]($BLOB/posts/\1#g" \
       -e "s#\]\(\.\./#]($BLOB/#g" posts/pq-gasper-on-gossipsub.md
```
