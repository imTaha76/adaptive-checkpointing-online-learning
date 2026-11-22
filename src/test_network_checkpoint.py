
from network_simulator import NetworkSimulator
from pathlib import Path
import time

CHECKPOINT_SIZE_MB = 10

network = NetworkSimulator()

for condition in ["normal", "congested", "unstable"]:
    network.set_condition(condition)

    print(f"\nTesting {condition} network...")

    start = time.time()

    network.simulate_transfer(CHECKPOINT_SIZE_MB)

    elapsed = time.time() - start

    print(f"Measured transfer delay: {elapsed:.3f} seconds")

print("\nNetwork simulation test completed.")
