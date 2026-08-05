# FF Networking by Research Team 


## Yann's Improvements


=> Option 2 or Option 5 make most sense


Option 2 has the issue that it increases latency. 
Option 5 has the issue that target selection happens very quickly, which might lead to bad side effects.
- However Option 2 only increases it by 2 Delta (in theory)
- Actually, you could parametrize between 2 and 5, voting can start whenever we want, without big changes! The important thing is that aggregation will only happen next slot.


PQ design: aggregate the best you have. 


Idea: Back-Off / Optimistic design - we go for all, already now :) 

1. Much more impressive 
2. Might not have opportunity in future to improve
3. Flexible
4. we need something to strive for
5. already go in the direction of PQ => which will be multi-stage too!

- back-off is also needed because if the first collection is skip, we might skip even with 2/3 honest.
=> if we don't reach 2/3, we delay the start of the next round by 2x (8 -> 16) 

### Idea 1:
- maintain subnet infrastructure (8 slots)
- send immediately to voluntary brokers (cheap side channel)
    - load: 8x regular load for super node
    - 1M x 100B = 100MB in ~8 seconds. 100Mbit/s most optimistic, but opening connections is worst part.
    - 1 128KB array just to store indicies.. for single aggregation..
    - WRONG: 12KB for one
    -


Open questions:
- Is it too much to even have 1 bit index per block?
- How does PQ improve this?
- 
