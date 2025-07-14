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