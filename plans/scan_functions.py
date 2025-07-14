# plans/scan_functions.py

from bluesky.plans import scan
from bluesky.preprocessors import baseline_decorator
from config.detectors import configure_eiger_for_burst
from config.motors import motor
from config.counters import counters
from config.runengine import setup_live_callbacks
from utils.logger import append_metadata_to_csv
from time import strftime
from databroker import catalog

# Use the default catalog
cat = catalog['my_catalog']

# Auto record all counters + motor state before/after
baseline_devices = [motor] + counters

def run_burst_scan(
    sample_name: str,
    motor_start: float,
    motor_stop: float,
    steps: int = 11,
    nframes: int = 10,
    frame_time: float = 0.002,
    file_prefix: str = "eiger_scan",
):
    from bluesky import RunEngine
    RE, _ = setup_runengine_with_databroker()
    
    # Configure Eiger
    eiger = configure_eiger_for_burst(nframes, frame_time, base_filename=file_prefix)
    
    # Add live callbacks
    for cb in setup_live_callbacks(eiger):
        RE.subscribe(cb)
    
    # Build metadata
    timestamp = strftime("%Y%m%d_%H%M%S")
    md = {
        "sample_name": sample_name,
        "scan_type": "eiger_burst_scan",
        "motor_start": motor_start,
        "motor_stop": motor_stop,
        "nframes": nframes,
        "frame_time": frame_time,
        "timestamp": timestamp,
    }

    @baseline_decorator(baseline_devices)
    def _scan():
        return scan([eiger], motor, motor_start, motor_stop, steps)

    # Run scan
    RE(_scan(), md)

    # Export metadata
    latest = cat[-1]
    h5name = f"{file_prefix}_{sample_name}_{timestamp}.h5"
    latest.export(h5name, fmt="hdf5")

    append_metadata_to_csv("scan_log.csv", md)

    print(f"✅ Scan '{sample_name}' complete. Metadata saved to {h5name}")