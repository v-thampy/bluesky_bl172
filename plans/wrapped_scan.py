# plans/wrapped_scan.py

from bluesky.plans import scan, rel_scan
from config.counters import counters
from config.runengine import setup_runengine_with_databroker
from bluesky.callbacks.mpl_plotting import LivePlot
from config.runengine import LiveStatsPlot

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
    RE, _ = setup_runengine_with_databroker()

    all_detectors = counters + detectors  # counters always included
    md = metadata or {}

    # Attach live plots if requested
    if live_signals:
        for signal in live_signals:
            if hasattr(signal, "name"):
                signal = signal.name
            RE.subscribe(LiveStatsPlot(y_field=signal, x_field=motor.name))

    plan = rel_scan if relative else scan
    RE(plan(all_detectors, motor, start, stop, steps), md)