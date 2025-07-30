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
        

# logging_setup.py
import logging

def setup_experiment_logger(name='beamline', log_file=None, level=logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Console output
    console_handler = logging.StreamHandler()
    console_format = logging.Formatter('[%(levelname)s] %(name)s: %(message)s')
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # Optional: file output
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_format = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)

    return logger
