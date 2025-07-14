from bluesky import RunEngine
from bluesky.callbacks.best_effort import BestEffortCallback
from databroker.manager import Manager
from databroker.v2 import Broker
from pathlib import Path
from bluesky.callbacks import CallbackBase
import matplotlib.pyplot as plt
import numpy as np

def setup_runengine_with_databroker():
    RE = RunEngine()
    bec = BestEffortCallback()
    RE.subscribe(bec)
    data_dir = Path.home() / "bluesky_data"
    data_dir.mkdir(exist_ok=True)
    mgr = Manager.from_config({
        "catalog": {"metadatastore": {"dbpath": str(data_dir)}}
    })
    cat = Broker(mgr)
    RE.subscribe(cat.v1.insert)
    return RE, cat

class LiveStatsPlot(CallbackBase):
    def __init__(self, y_field, x_field='motor', label="Live Stats"):
        self.xs, self.ys = [], []
        self.x_field = x_field
        self.y_field = y_field
        self.fig, self.ax = plt.subplots()
        self.line, = self.ax.plot([], [], 'o-')
        self.ax.set_title(label)
        self.ax.set_xlabel(x_field)
        self.ax.set_ylabel(y_field)
        plt.ion()
        plt.show()

    def event(self, doc):
        if self.x_field in doc['data'] and self.y_field in doc['data']:
            self.xs.append(doc['data'][self.x_field])
            self.ys.append(doc['data'][self.y_field])
            self.line.set_data(self.xs, self.ys)
            self.ax.relim()
            self.ax.autoscale_view()
            plt.pause(0.01)