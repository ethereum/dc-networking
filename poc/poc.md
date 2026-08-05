# DC/FF Proof-of-Concept Implementation

Wire-format and load baseline:
[`ssz.md`](../research/ssz.md). It distinguishes the executable AC/FG containers
from deprecated compact votes and from the healing paper's currently
unspecified SG pre-vote.

Overaching Goals:

- Show feasibility of our design.
- Show progress to different stakeholders.
- Figuring out potential blockers by co-designing theory and implementation.

## Goals by Mid-October (Cambridge)

**Main Goal:** **High confidence that a 4x (or 8x) reduction of round time is possible.**

This goal can be broken up into the following sub goals:

1. A stripped down proof of concept implementation
    - Running a simplified / simulated consensus, but with accurate attestation load.
    - Not just in simulation, but also deployed on WAN.
2. Obtaining empricial evidence to argue which design choices make sense in practice.
    - Not simulation only but also on geo-distributed servers
3. First version of networking specs


## Plan

1. Simulations via Shadow (up to ~4000 nodes, only FF stack)
2. Prysm on Shadow (full stack)
3. Prysm on [Kurtosis](https://ethpandaops.io/posts/kurtosis-deep-dive/) (full stack, via Ansible)
    a) local
    b) small scale -> tag onto August and October Glamsterdam tests
    b) then full scale before deployment and multiple clients (in 10 months)
4. Transition testing 
    

---


### Meeting with Pari

- [x] How many nodes could be run? 
    - 1500ish
    - There's a cap of 5k nodes
- [x] Costs, how long could we have the setup?
    - 15k$ per day (not bandwidth dependent)
- [x] Can we place them around the globe, or otherwise have edge based latencies?
    - yeah, they're in different data centers
        - 5 different regions 
- [x] Bandwidth restrictions
    - homenode vs supernode split configurable
- [x] What experiments do you recommend? (e.g., if we can't run full scale, larger AWS deployment with bandwidth restrictions)
    - our suggestion seems good
- [x] how can we better mock EL load in our simulations? 
    - panda tool can give the mempool traffic data on the mainnet currently
- [x] Can we just simulate current prysm with large subnets / 1/4th the epoch?
    - yes 
- [x] How do we have a representative validator distribution?
    - The system allows arbitrary validator counts. We should pick one which covers the worst cases

- @pari: Link for the work done for sparse blobpool
- @pari: panda setup instructions

---

### Prototyping questions raised by Francesco

- [ ] Check round subdivision difficulties
- [ ] Transition management
- [ ] Voting behavior fully specced out first?


---

### Yann's notes
- Need to be careful to design worst case experiments, such that its representative

### Sukun's notes

- decoupled consensus from genesis
- state object: SSZ
    - Load a gensis state file
- CL sends FCU to EL
- For metrics: Xatu listens to beacon api events
    - pushes it to a remote server
    - kurtosis gives this server out of the box
    - beacon api specification event stream
- ansible and kurtossi feature parity
    - in the past we've done 1500 node testing
        - used for blobs on fusaka last year
        - 15_000$ a day?
        - bandwidth limiter:
            - 20% supernodes, 5% supernodes
            - 80-90% of the network 50mbps down and 25Mbps up
            - block size: spammed it to get as large as possible:
    - kurtosis we've done 100
- easier to do this on a currently working CL as opposed to a new CL
- 600 node network in august or october for glamsterdam
    - we can get our costs amortized
    - we can run a 1/4th epoch length simulation in august
- The current system is 1 CL and 1 EL per machine. We can change it though. 




















