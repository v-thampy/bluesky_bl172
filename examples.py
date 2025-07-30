from databroker import catalog
from utils.plot_tools import plot_multiple_signals

run = catalog['my_catalog'][-1]
plot_multiple_signals(run, y_fields=["i0", "i1", "monitor"], title="Beamline counters")


from utils.plot_tools import interactive_signal_plot
interactive_signal_plot(run, signal_names=["i0", "i1", "eiger4M_stats1_total", "monitor"])

from databroker import catalog
from utils.plot_tools import plot_signal_vs_motor

run = catalog['my_catalog'][-1]  # latest scan
plot_signal_vs_motor(run, y_field="i1", x_field="sample_y")
plot_signal_vs_motor(run, y_field="eiger4M_stats1_total")


# Burst Scans
from plans.scan_functions import run_burst_scan
from config.motors import sx  # or sy, th, etc.

run_burst_scan(
    motor=sx,
    sample_name="Si_sample",
    motor_start=-1,
    motor_stop=1,
    steps=21,
    nframes=100,
    frame_time=0.001
)


# Regular scans
from plans.wrapped_scan import run_scan_with_counters
from config.detectors import eiger
from config.motors import sx
from config.counters import i0, i1

run_scan_with_counters(
    detectors=[eiger],        # add Eiger optionally
    motor=sx,
    start=-1,
    stop=1,
    steps=31,
    relative=False,
    live_signals=[i0, i1, "stats1_total"]  # mix of counter objects or string names
)
