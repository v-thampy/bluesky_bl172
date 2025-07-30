# plans/scan_functions.py

from bluesky.plans import scan
from bluesky.preprocessors import baseline_decorator
from bluesky.callbacks.mpl_plotting import LivePlot
from config.detectors import configure_eiger_for_burst
from config.counters import counters
from config.runengine import setup_runengine_with_databroker, LiveStatsPlot
from utils.logger import append_metadata_to_csv
from time import strftime
# from databroker import catalog

# Use the default catalog
# cat = catalog['bl172_experiments']


def setup_runengine_with_databroker():
    RE = RunEngine()
    bec = BestEffortCallback()
    RE.subscribe(bec)
    
    try:
        # Connect to your running Tiled server
        from tiled.client import from_uri
        catalog = from_uri("http://localhost:8000")
        RE.subscribe(catalog.v1.insert)
        print("✅ Connected to Tiled server at http://localhost:8000")
        return RE, catalog
    except Exception as e:
        print(f"⚠️ Could not connect to Tiled server: {e}")
        print("📝 Make sure Tiled server is running on port 8000 (tiled serve config /home/b_thampy/bluesky_bl172/config/tiled_server_config.yml --port 8000)")
        
        # Fallback to temp catalog
        print("🔄 Falling back to temporary catalog...")
        from databroker import temp
        catalog = temp()
        RE.subscribe(catalog.v1.insert)
        return RE, catalog


def run_burst_scan(
    motor,
    sample_name: str,
    motor_start: float,
    motor_stop: float,
    steps: int = 11,
    nframes: int = 10,
    frame_time: float = 0.002,
    file_prefix: str = "eiger_scan",
    live_signals: list = None,
    disable_roi_live: bool = None,
    max_frame_rate_for_live: float = 100.0,  # Hz
):
    """Your docstring stays the same..."""
    
    RE, cat = setup_runengine_with_databroker()
    
    # Configure Eiger detector
    eiger = configure_eiger_for_burst(nframes, frame_time, base_filename=file_prefix)
    
    # Calculate effective frame rate
    effective_frame_rate = nframes / (frame_time * nframes + 0.1)  # rough estimate
    
    # Auto-determine ROI live plotting based on frame rate
    if disable_roi_live is None:
        disable_roi_live = effective_frame_rate > max_frame_rate_for_live
        if disable_roi_live:
            print(f"⚠️ High frame rate ({effective_frame_rate:.1f} Hz) detected. "
                  f"Disabling ROI live plotting for performance.")
    
    # Setup live plotting for specified signals
    if live_signals:
        setup_live_plotting(RE, live_signals, motor, eiger, disable_roi_live)
    
    # Build metadata
    timestamp = strftime("%Y%m%d_%H%M%S")
    md = {
        "sample_name": sample_name,
        "scan_type": "eiger_burst_scan",
        "motor_name": motor.name,
        "motor_start": motor_start,
        "motor_stop": motor_stop,
        "nframes": nframes,
        "frame_time": frame_time,
        "effective_frame_rate": effective_frame_rate,
        "roi_live_disabled": disable_roi_live,
        "timestamp": timestamp,
    }
    
    if live_signals:
        md["live_signals"] = [str(sig) for sig in live_signals]
    
    # Record motor and counters as baseline
    baseline_devices = [motor] + counters
    scan_detectors = [eiger] + counters
    
    @baseline_decorator(baseline_devices)
    def _scan():
        return scan(scan_detectors, motor, motor_start, motor_stop, steps)
    
    # Execute plan
    RE(_scan(), md)
    
    # Export latest scan with error handling
    try:
        latest = cat[-1]
        h5name = f"{file_prefix}_{sample_name}_{timestamp}.h5"
        latest.export(h5name, fmt="hdf5")
        print(f"📁 Exported scan data to {h5name}")
    except Exception as e:
        print(f"⚠️ Could not export HDF5: {e}")
        print("📝 Data is still saved in the Tiled catalog")
    
    # Save metadata
    append_metadata_to_csv("scan_log.csv", md)
    print(f"✅ Scan '{sample_name}' complete. Metadata logged to scan_log.csv")


def setup_live_plotting(RE, live_signals, motor, eiger, disable_roi_live=False):
    """
    Setup live plotting callbacks based on signal types.
    
    Parameters:
        RE : bluesky.RunEngine
            The RunEngine instance.
        live_signals : list
            List of signals to plot live.
        motor : ophyd.Device
            The scanning motor (for x-axis of LivePlot).
        eiger : ophyd.Device  
            The Eiger detector.
        disable_roi_live : bool
            Whether to skip ROI stats plotting.
    """
    for signal in live_signals:
        signal_name = _resolve_signal_name(signal, eiger)
        
        if signal_name is None:
            print(f"⚠️ Warning: Could not resolve signal '{signal}', skipping live plot.")
            continue
            
        # Skip ROI stats if disabled
        if disable_roi_live and _is_roi_signal(signal_name):
            print(f"🚫 Skipping ROI signal '{signal_name}' (high frame rate mode)")
            continue
        
        # Determine plot type and subscribe
        if _should_use_live_plot(signal_name, motor):
            # Use LivePlot for motor vs signal plotting
            callback = LivePlot(signal_name, motor.name, ax=None)
            RE.subscribe(callback)
            print(f"📊 LivePlot: {signal_name} vs {motor.name}")
        else:
            # Use LiveStatsPlot for time-series or individual value plotting
            callback = LiveStatsPlot(y_field=signal_name, x_field='time', 
                                   label=f"{signal_name} vs time")
            RE.subscribe(callback)
            print(f"📈 LiveStatsPlot: {signal_name} vs time")


def _resolve_signal_name(signal, eiger):
    """
    Resolve signal name from various input types.
    
    Parameters:
        signal : str or ophyd.Device or ophyd.Signal
            The signal to resolve.
        eiger : ophyd.Device
            Eiger detector for resolving stats signals.
    
    Returns:
        str or None : Resolved signal name.
    """
    if isinstance(signal, str):
        # Handle string signal names
        if signal.startswith('eiger'):
            # Handle eiger stats signals like 'eiger_stats1_mean'
            return signal
        return signal
    elif hasattr(signal, 'name'):
        # Handle ophyd objects with name attribute
        return signal.name
    else:
        return None


def _is_roi_signal(signal_name):
    """
    Check if a signal is an ROI/stats signal that might be expensive to plot live.
    
    Parameters:
        signal_name : str
            Name of the signal.
    
    Returns:
        bool : True if it's an ROI signal.
    """
    roi_indicators = ['stats', 'roi', 'mean', 'total', 'max', 'min', 'std']
    signal_lower = signal_name.lower()
    return any(indicator in signal_lower for indicator in roi_indicators)


def _should_use_live_plot(signal_name, motor):
    """
    Determine whether to use LivePlot vs LiveStatsPlot.
    
    LivePlot is better for:
    - Motor position vs detector signal during scans
    - Y vs X relationships
    
    LiveStatsPlot is better for:
    - Individual signals vs time
    - Monitoring signals that don't correlate with motor position
    
    Parameters:
        signal_name : str
            Name of the signal to plot.
        motor : ophyd.Device
            The scanning motor.
    
    Returns:
        bool : True to use LivePlot, False to use LiveStatsPlot.
    """
    # Use LivePlot for typical scan data (detector vs motor)
    scan_indicators = ['det', 'i0', 'i1', 'monitor', 'counts']
    signal_lower = signal_name.lower()
    
    # Use LivePlot if it looks like a detector signal
    for indicator in scan_indicators:
        if indicator in signal_lower:
            return True
    
    # Use LivePlot for counter/detector signals
    if any(counter.name == signal_name for counter in counters):
        return True
        
    # Use LiveStatsPlot for everything else (ROI stats, temperatures, etc.)
    return False


# Convenience function for common scan types
def run_simple_burst_scan(motor, sample_name, start, stop, steps=11, 
                         live_counters=True, live_roi=True):
    """
    Simplified burst scan with common live plotting options.
    
    Parameters:
        motor : ophyd.Device
            Motor to scan.
        sample_name : str
            Sample identifier.
        start, stop : float
            Scan range.
        steps : int
            Number of steps.
        live_counters : bool
            Enable live plotting of counters.
        live_roi : bool
            Enable live plotting of ROI stats.
    """
    live_signals = []
    
    if live_counters:
        live_signals.extend(['i0', 'i1', 'monitor'])
    
    if live_roi:
        live_signals.extend(['eiger_stats1_mean', 'eiger_stats1_total'])
    
    return run_burst_scan(
        motor=motor,
        sample_name=sample_name,
        motor_start=start,
        motor_stop=stop,
        steps=steps,
        live_signals=live_signals
    )