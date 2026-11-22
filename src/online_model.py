
import numpy as np
from sklearn.linear_model import SGDRegressor


class OnlineTransferPredictor:

    def __init__(self):
        self.model = SGDRegressor(
            loss="squared_error",
            penalty="l2",
            alpha=0.0001,
            learning_rate="constant",
            eta0=0.01,
            random_state=42
        )

        self.is_trained = False
        self.observations = 0

    def extract_features(
        self,
        file_size_bytes,
        local_save_time,
        previous_transfer_time,
        previous_throughput,
        checkpoint_interval=None
    ):
        # Checkpoint interval is deliberately excluded:
        # it does not determine the size of our current JSON checkpoint.
        return np.array([[
            max(0, file_size_bytes) / 10_000_000,
            max(0, local_save_time) * 1000 / 100,
            np.log1p(max(0, previous_transfer_time) * 1000) / 10,
            np.log1p(max(0, previous_throughput)) / 10
        ]], dtype=float)

    def predict(
        self,
        file_size_bytes,
        local_save_time,
        previous_transfer_time,
        previous_throughput,
        checkpoint_interval=None
    ):
        if not self.is_trained or self.observations < 5:
            return None

        features = self.extract_features(
            file_size_bytes,
            local_save_time,
            previous_transfer_time,
            previous_throughput
        )

        predicted_log_time = self.model.predict(features)[0]

        return max(0.0, float(np.expm1(predicted_log_time)))

    def update(
        self,
        file_size_bytes,
        local_save_time,
        previous_transfer_time,
        previous_throughput,
        checkpoint_interval=None,
        actual_transfer_time=None
    ):
        if actual_transfer_time is None or actual_transfer_time < 0:
            return

        features = self.extract_features(
            file_size_bytes,
            local_save_time,
            previous_transfer_time,
            previous_throughput
        )

        target = np.array([
            np.log1p(actual_transfer_time)
        ])

        self.model.partial_fit(features, target)

        self.is_trained = True
        self.observations += 1

        print(
            f"[ONLINE ML] Model updated "
            f"| Observations: {self.observations}",
            flush=True
        )
