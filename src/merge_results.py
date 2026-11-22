import csv
from pathlib import Path

checkpoint_file = Path("results/checkpoint_events.csv")
transfer_file = Path("results/network_transfers.csv")
output_file = Path("results/combined_runtime_dataset.csv")

checkpoint_data = {}

with checkpoint_file.open(newline="") as file:
    for row in csv.DictReader(file):
        key = (row["worker_id"], row["completed_until"])
        checkpoint_data[key] = row

merged_rows = []
unmatched = 0
excluded = 0

with transfer_file.open(newline="") as file:
    for transfer in csv.DictReader(file):
        if transfer["network_profile"] == "unspecified":
            excluded += 1
            continue

        key = (transfer["worker_id"], transfer["completed_until"])
        local = checkpoint_data.get(key)

        if local is None:
            unmatched += 1
            continue

        merged_rows.append({
            "network_profile": transfer["network_profile"],
            "worker_id": transfer["worker_id"],
            "completed_until": transfer["completed_until"],
            "file_size_bytes": transfer["file_size_bytes"],
            "local_save_time_seconds": local["local_save_time_seconds"],
            "transfer_time_seconds": transfer["transfer_time_seconds"],
            "throughput_mbps": transfer["throughput_mbps"],
            "status": transfer["status"]
        })

fields = [
    "network_profile",
    "worker_id",
    "completed_until",
    "file_size_bytes",
    "local_save_time_seconds",
    "transfer_time_seconds",
    "throughput_mbps",
    "status"
]

with output_file.open("w", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields)
    writer.writeheader()
    writer.writerows(merged_rows)

print("DATASET MERGE SUMMARY")
print("=" * 40)
print(f"Matched records: {len(merged_rows)}")
print(f"Excluded unspecified records: {excluded}")
print(f"Unmatched records: {unmatched}")
print(f"Output: {output_file}")
