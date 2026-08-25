# Ethshadow

To run the simulations with shadow, we use ethshadow. 
The fork is located at: [ethshadow](https://github.com/sukunrt/ethshadow/tree/decoupled-sim)

## CL config

The chain config the simulations run with: [cl-config-goldfish.yaml](cl-config-goldfish.yaml).
It is the template ethshadow mounts over the genesis generator's `/config/cl/config.yaml`.
The important values: 
all forks at epoch 0 (genesis starts at Heze)

`SLOTS_PER_ROUND: 8` 

`TARGET_COMMITTEE_SIZE: 3000`
(one committee per slot holding the whole V/8 pool)

`ATTESTATION_SUBNET_COUNT: 1` (This should be equal to the committee count. The aim is to have dense subnets, with many voters and a large mesh so that latencies are upper bounded.)

`SUBNETS_PER_NODE: 2`
