import csv
from pathlib import Path

def append_metadata_to_csv(filepath, metadata):
    filepath = Path(filepath)
    filepath.parent.mkdir(exist_ok=True)
    is_new = not filepath.exists()
    with open(filepath, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=metadata.keys())
        if is_new:
            writer.writeheader()
        writer.writerow(metadata)