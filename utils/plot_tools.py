# utils/plot_tools.py

import matplotlib.pyplot as plt
import ipywidgets as widgets
from IPython.display import display
import numpy as np
from scipy.signal import find_peaks
import pandas as pd


def plot_multiple_signals(run, y_fields, x_field=None, title=None):
    data = run.primary.read()
    x_field = x_field or run.primary.metadata.get("motor", list(data.data_vars.keys())[0])

    x = data[x_field]

    fig, ax = plt.subplots()
    for y_field in y_fields:
        if y_field in data:
            y = data[y_field]
            ax.plot(x, y, label=y_field)

    ax.set_xlabel(x_field)
    ax.set_ylabel("Signal")
    ax.set_title(title or "Multiple Signal Plot")
    ax.legend()
    ax.grid(True)
    plt.show()


def interactive_signal_plot(run, signal_names, x_field=None):
    data = run.primary.read()
    x_field = x_field or run.primary.metadata.get("motor", list(data.data_vars.keys())[0])
    x = data[x_field]

    fig, ax = plt.subplots()
    lines = {}
    colors = plt.cm.tab10(np.linspace(0, 1, len(signal_names)))

    # Create initial lines
    for i, name in enumerate(signal_names):
        if name in data:
            y = data[name]
            line, = ax.plot(x, y, label=name, color=colors[i])
            lines[name] = line

    ax.set_xlabel(x_field)
    ax.set_ylabel("Signal")
    ax.set_title("Interactive Signal Plot")
    ax.legend()
    ax.grid(True)

    # Create checkboxes
    toggles = {name: widgets.Checkbox(value=True, description=name) for name in signal_names}

    def update_plot(change=None):
        for name, checkbox in toggles.items():
            line = lines.get(name)
            if line:
                line.set_visible(checkbox.value)
        plt.draw()

    for cb in toggles.values():
        cb.observe(update_plot, names='value')

    display(widgets.HBox(list(toggles.values())))
    update_plot()  # Initial
    plt.show()

    
def plot_roi_time_series(roi_csv, fit_peak=True, save=True):
    df = pd.read_csv(roi_csv)
    t = df["frame"]

    stats_fields = [col for col in df.columns if "stats1" in col]
    plt.figure(figsize=(10, 6))

    for col in stats_fields:
        y = df[col]
        plt.plot(t, y, label=col)

        if fit_peak and len(y) > 10:
            peaks, _ = find_peaks(y, prominence=np.max(y) * 0.1)
            if len(peaks):
                peak_idx = peaks[0]
                plt.axvline(t[peak_idx], color='k', linestyle='--', alpha=0.5)
                print(f"📍 Peak in {col} at frame {t[peak_idx]} with value {y[peak_idx]:.2f}")

    plt.title("Eiger ROI Stats During Burst")
    plt.xlabel("Frame")
    plt.ylabel("Intensity")
    plt.legend()
    plt.grid(True)

    if save:
        fname = roi_csv.replace(".csv", "_plot.png")
        plt.savefig(fname)
        print(f"🖼️ ROI stats plot saved to {fname}")
    plt.show()