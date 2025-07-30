# plans/wrapped_scan.py

from bluesky.plans import scan, rel_scan
from config.counters import counters
from config.runengine import setup_runengine_with_databroker
from config.runengine import LiveStatsPlot  # Custom callback for ROI/com/statistics
from bluesky.callbacks.mpl_plotting import LivePlot

def run_scan_with_counters(
    detectors,
    motor,
    start,
    stop,
    steps,
    *,
    relative=False,
    live_signals=None,
    metadata=None,
):
    """
    Run a motor scan with counters included by default.

    Parameters:
        detectors : list
            List of additional detectors (e.g. [eiger]).
        motor : Ophyd motor
            Motor to scan.
        start : float
            Start position.
        stop : float
            Stop position.
        steps : int
            Number of steps.
        relative : bool, optional
            If True, perform a relative scan.
        live_signals : list, optional
            List of signals (objects or names) to plot live.
        metadata : dict, optional
            Metadata to attach to the run.
    """
    RE, _ = setup_runengine_with_databroker()

    all_detectors = counters + detectors
    md = metadata or {}

    # Attach live plots for requested signals
    if live_signals:
        for signal in live_signals:
            sig_name = signal.name if hasattr(signal, "name") else signal
            RE.subscribe(LiveStatsPlot(y_field=sig_name, x_field=motor.name))

    plan = rel_scan if relative else scan
    RE(plan(all_detectors, motor, start, stop, steps), md)
