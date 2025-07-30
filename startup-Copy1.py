# startup.py

import importlib

# Standard Bluesky imports
from bluesky.plans import *
from bluesky.plan_stubs import *
from bluesky import RunEngine
from bluesky.utils import short_uid
from bluesky.callbacks import LiveTable, LivePlot
from bluesky.callbacks.broker import LiveImage

from config.detectors import eiger
from config.detectors import *
from config.counters import *
from config.motors import sx, sy, sz, th, sfpx, motor_list
from config.runengine import setup_runengine_with_databroker

from plans.scan_functions import run_burst_scan
from plans.alignment import scan_monitor_vs_motor
from plans.alignment_modular import (
    run_monitor_scan, fit_data, plot_fit, move_to_statistic, save_alignment_metadata
)

from utils.plot_tools import plot_multiple_signals, interactive_signal_plot
from utils.eiger_roi_gui import create_eiger_roi_gui, LiveRoiStatsPlot
from utils.eiger_funcs import *

RE, catalog = setup_runengine_with_databroker()

from bluesky.magics import BlueskyMagics
get_ipython().register_magics(BlueskyMagics)

#BlueskyMagics.detectors = [eiger, counters]
BlueskyMagics.positioners = motor_list

get_eiger_config(eiger)


import IPython

ipython = IPython.get_ipython()

if ipython is not None:
    ipython_version = IPython.__version__
    major_version = int(ipython_version.split('.')[0])
    minor_version = int(ipython_version.split('.')[1])

    if major_version < 8 or (major_version == 8 and minor_version < 1):
        ipython.magic("load_ext autoreload")
        ipython.magic("autoreload 2")
    else:
        ipython.run_line_magic(magic_name="load_ext", line="autoreload")
        ipython.run_line_magic(magic_name="autoreload", line="2")
    print("\nAutoreload enabled.")
else:
    print("\nAutoreload not enabled.")
