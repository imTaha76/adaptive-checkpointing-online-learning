
import random
import time


class NetworkSimulator:
    def __init__(self, condition="normal"):
        self.set_condition(condition)

    def set_condition(self, condition):
        self.condition = condition

        if condition == "normal":
            self.latency_ms = 10
            self.bandwidth_mbps = 100

        elif condition == "congested":
            self.latency_ms = 150
            self.bandwidth_mbps = 10

        elif condition == "unstable":
            self.latency_ms = random.randint(10, 200)
            self.bandwidth_mbps = random.randint(5, 100)

        else:
            raise ValueError("Unknown network condition")

    def simulate_transfer(self, data_size_mb):
        bandwidth_MBps = self.bandwidth_mbps / 8

        transfer_time = data_size_mb / bandwidth_MBps
        total_delay = transfer_time + self.latency_ms / 1000

        print(
            f"[NETWORK] {self.condition} | "
            f"Latency: {self.latency_ms} ms | "
            f"Bandwidth: {self.bandwidth_mbps} Mbps | "
            f"Transfer: {total_delay:.3f}s",
            flush=True
        )

        # Simulate the time taken by the transfer
        time.sleep(total_delay)

        return total_delay
