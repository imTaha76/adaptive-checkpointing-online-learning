import csv
import fcntl
import os

from pathlib import Path


def append_csv_row(path, fields, record):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a+", newline="") as file:
        fcntl.flock(file.fileno(), fcntl.LOCK_EX)

        try:
            file.seek(0, os.SEEK_END)
            is_empty = file.tell() == 0

            writer = csv.DictWriter(file, fieldnames=fields)

            if is_empty:
                writer.writeheader()

            writer.writerow(record)

            file.flush()
            os.fsync(file.fileno())

        finally:
            fcntl.flock(file.fileno(), fcntl.LOCK_UN)
