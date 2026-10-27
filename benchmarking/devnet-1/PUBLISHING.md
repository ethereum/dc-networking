# Publish the Devnet 1 comparison

The dashboard is hosted on OpenAI Sites:
<https://dc-devnet-1-comparison.citrusvole32.chatgpt.site>.

Git holds the analysis scripts, the docs and the evidence files the findings
cite. The dashboard data (the `web/` reductions and `data/`) is git-ignored.
The raw 1.55 GB archive, working caches and source checkouts stay outside Git
and the public site.

## Build the package

From the repository root, using Python 3.11+ and Node, after building the data
as described in [README.md](README.md):

```sh
python3 benchmarking/devnet-1/analysis/package_site.py --output /tmp/dc-devnet-1-site
python3 benchmarking/devnet-1/analysis/check_publication.py /tmp/dc-devnet-1-site
DEVNET_SITE_ROOT=/tmp/dc-devnet-1-site/devnet-1 node benchmarking/devnet-1/analysis/test_app.cjs
python3 -m http.server 8767 --bind 127.0.0.1 --directory /tmp/dc-devnet-1-site
```

Use an empty output directory. Open <http://127.0.0.1:8767/devnet-1/>.
The package uses relative links, so it also works below a path.
It copies only files referenced by the current dataset and selected audit
documents. The public manifest records hashes for every published file and
removes the local archive directory from the public archive-location field.

## Updating the data

Re-run the analysis as described in [README.md](README.md) and check the
loaded windows. Commit the changed scripts, docs and cited evidence together,
then rebuild the package and republish it to the OpenAI site.

The historical Devnet 0 reduction (`data/devnet0-run.json.gz`, git-ignored)
keeps its original schema and archive hashes. It remains optional context with
unverified transaction load. The analysis's source pins and input archive
checksum remain the authority for reproduction.

The publication snapshot keeps the different workloads/topologies and
three-node sample visible. Publishing does not turn
the measurements into a controlled experiment or protocol-safety proof.
