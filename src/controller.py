class RuleBasedController:
    def __init__(
        self,
        initial_interval=100_000,
        min_interval=50_000,
        max_interval=400_000
    ):
        self.interval = initial_interval
        self.min_interval = min_interval
        self.max_interval = max_interval

    def update(self, transfer_time=None, failure_detected=False):

        # Failures increase the need for frequent checkpoints.
        if failure_detected:
            self.interval = max(
                self.min_interval,
                self.interval // 2
            )

        # Slow transfers make frequent checkpointing expensive.
        elif transfer_time is not None and transfer_time > 0.12:
            self.interval = min(
                self.max_interval,
                self.interval * 2
            )

        # Fast transfers make more frequent checkpointing affordable.
        elif transfer_time is not None and transfer_time < 0.02:
            self.interval = max(
                self.min_interval,
                self.interval // 2
            )

        return self.interval
