# startup.py

from config.detectors import eiger
from config.counters import i0, i1, monitor, temp, counters
from config.motors import sample_y, th
from plans.scan_functions import run_burst_scan
from plans.alignment import scan_monitor_vs_motor
from plans.alignment_modular import (
    run_monitor_scan, fit_data, plot_fit, move_to_statistic, save_alignment_metadata
)
from utils.plot_tools import plot_multiple_signals, interactive_signal_plot
from utils.eiger_roi_gui import create_eiger_roi_gui, LiveRoiStatsPlot