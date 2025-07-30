from bluesky import RunEngine
# from databroker.v2 import Broker
from pathlib import Path
from bluesky.callbacks import CallbackBase
import matplotlib.pyplot as plt
import numpy as np


def setup_runengine_with_databroker():
    # from bluesky.callbacks.best_effort import BestEffortCallback
    RE = RunEngine()
    # bec = BestEffortCallback()
    # RE.subscribe(bec)
    try:
        from tiled.client import from_uri
        catalog = from_uri("http://localhost:8000")
        print("✅ Connected to Tiled native catalog at /")
        return RE, catalog
    except Exception as e:
        print(f"⚠️ Could not connect to Tiled server: {e}")
        raise RuntimeError("No working data catalog could be established. Tiled server must be running.") from e


class LiveStatsPlot(CallbackBase):
    def __init__(self, y_field, x_field='motor', label="Live Stats"):
        self.xs = []
        self.ys = []
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

            # Calculate stats
            x = np.array(self.xs)
            y = np.array(self.ys)
            if len(x) >= 5:
                com = np.sum(x * y) / np.sum(y)
                peak_idx = np.argmax(y)
                peak_x = x[peak_idx]
                peak_y = y[peak_idx]

                # FWHM estimation
                half_max = peak_y / 2
                indices = np.where(y >= half_max)[0]
                if len(indices) >= 2:
                    fwhm = x[indices[-1]] - x[indices[0]]
                else:
                    fwhm = np.nan

                self.ax.set_title(
                    f"{self.y_field}: Peak={peak_y:.1f} @ {peak_x:.2f}, "
                    f"COM={com:.2f}, FWHM={fwhm:.2f}"
                )
            plt.pause(0.01)


def setup_live_callbacks(det):
    from bluesky.callbacks.broker import LiveImage
    return [
        LiveImage(det.image, cmap="viridis"),
        LiveStatsPlot(y_field=det.stats1.mean.name, x_field='motor', label='ROI Mean w/ Stats'),
    ]