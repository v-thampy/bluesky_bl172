import ipywidgets as widgets
from IPython.display import display, clear_output
import matplotlib.pyplot as plt
from bluesky.callbacks import CallbackBase

def create_eiger_roi_gui(eiger, roi_index=1):
    roi = getattr(eiger, f"roi{roi_index}")
    stats = getattr(eiger, f"stats{roi_index}")
    x = widgets.IntSlider(min=0, max=2048, description="X")
    y = widgets.IntSlider(min=0, max=2048, description="Y")
    w = widgets.IntSlider(min=1, max=2048, value=100, description="Width")
    h = widgets.IntSlider(min=1, max=2048, value=100, description="Height")
    apply_btn = widgets.Button(description="Apply ROI")
    output = widgets.Output()
    def apply_roi(_):
        roi.min_xyz.min_x.put(x.value)
        roi.min_xyz.min_y.put(y.value)
        roi.size.x.put(w.value)
        roi.size.y.put(h.value)
        with output:
            clear_output()
            print(f"✅ ROI set: X={x.value}, Y={y.value}, W={w.value}, H={h.value}")
    apply_btn.on_click(apply_roi)
    display(widgets.VBox([x, y, w, h, apply_btn, output]))
    return stats

class LiveRoiStatsPlot(CallbackBase):
    def __init__(self, stats_signal, label="ROI Live Stats"):
        self.xs, self.ys = [], []
        self.stats_signal = stats_signal
        self.fig, self.ax = plt.subplots()
        self.line, = self.ax.plot([], [], 'o-')
        self.ax.set_title(label)
        self.ax.set_xlabel("Point")
        self.ax.set_ylabel(stats_signal.name)
        plt.ion()
        plt.show()
    def event(self, doc):
        if self.stats_signal.name in doc['data']:
            self.xs.append(len(self.xs))
            self.ys.append(doc['data'][self.stats_signal.name])
            self.line.set_data(self.xs, self.ys)
            self.ax.relim()
            self.ax.autoscale_view()
            plt.pause(0.01)