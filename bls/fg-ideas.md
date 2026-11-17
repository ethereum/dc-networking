# [Pre-PQ] P2P Design for Decoupled Finality Gadget

This is about creating a new networking layer for the finality gadgt votes in decoupled consensus.



## My new ideas: PoV Subnets with permissionless gossip

Why subnets? Taking them all over is expensive

Why PoV? Latency improvement -> 

Inside subnet: can do either 

1) **all-to-all propagation** (can we pretend we receive, but just throw away? YES, because we are not critical! => no load on client.) 

Only drawback: we might have to send to 128 before finding the right destinary! But 128x 100bytes -> 10kB

or 
4) gossip (whatever is faster) or 
5) one-to-k for even faster, but less secure

Fallback for proposer: join subnet as listener (less critical)

## Alternative: pick your broker + gossip fallback


