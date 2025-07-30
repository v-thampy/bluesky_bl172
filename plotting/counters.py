#pip install numpy matplotlib bluesky ophyd pyqt6 lmfit
from pathlib import Path
import time
from datetime import datetime
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.widgets import Button, RadioButtons
from lmfit import Model
from bluesky import RunEngine, Msg
from bluesky.callbacks import LivePlot
import bluesky.plan_stubs as bps
from ophyd.sim import SynSignal, SynAxis

# Interval between stats panel refreshes in seconds
STATS_REFRESH_INTERVAL = 1
A, mu, sigma = 100, 50, 10  # Gaussian defaults

DATA_DIR = Path('data')
DATA_DIR.mkdir(exist_ok=True)
print(f"Data directory created/confirmed: {DATA_DIR.absolute()}")

matplotlib.use('QtAgg')
plt.ion()

class OverlayedLivePlot(LivePlot):
    def __init__(self, y, x):
        self.y = y
        self.x = x
        self.text = None
        self.eq_text = None
        self.fit_line = None
        self.button = None
        self.radio = None
        self.dropdown = None
        self.fit_type = 'Gaussian'
        self.detector_type = 'i0'
        self.x_data = []
        self.y_data = []
        self.dummy_motor = SynAxis(name='dummy_motor')
        self.latest_com = None
        self.latest_center = None

        self.fig = plt.figure(figsize=(14, 8))
        gs = self.fig.add_gridspec(1, 3, width_ratios=[1, 3, 1], hspace=0.05, wspace=0.02)
        self.stats_ax = self.fig.add_subplot(gs[0, 0])
        self.stats_ax.set_xlim(0, 1)
        self.stats_ax.set_ylim(0, 1)
        self.stats_ax.axis('off')
        self.stats_ax.set_title('Statistics', fontsize=12, fontweight='bold', ha='left')
        self.ax = self.fig.add_subplot(gs[0, 1])
        self.controls_ax = self.fig.add_subplot(gs[0, 2])
        self.controls_ax.set_xlim(0, 1)
        self.controls_ax.set_ylim(0, 1)
        self.controls_ax.axis('off')
        self.controls_ax.set_title('Controls', fontsize=12, fontweight='bold', ha='right')
        self.ax.set_xlabel(x)
        self.ax.set_ylabel(y)
        self.ax.set_title('XRD Data')
        self.line = None

        self._setup_stats_panel()
        self._setup_controls_panel()

    def _setup_stats_panel(self):
        self.instructions_text = self.stats_ax.text(
            0.0, 0.95, "Instructions here",
            transform=self.stats_ax.transAxes, verticalalignment='top',
            horizontalalignment='left', fontsize=10, 
            bbox=dict(facecolor='beige', alpha=0.9, pad=8))

        self.stats_text = self.stats_ax.text(
            0.0, 0.7, 'Waiting for data...',
            transform=self.stats_ax.transAxes, verticalalignment='top',
            horizontalalignment='left', fontsize=10, 
            bbox=dict(facecolor='lightblue', alpha=0.7, pad=10))

        self.eq_text = self.stats_ax.text(
            0.0, 0.3, '', transform=self.stats_ax.transAxes,
            verticalalignment='top', horizontalalignment='left', fontsize=8,
            bbox=dict(facecolor='lightgreen', alpha=0.7, pad=8), wrap=True)

    def _setup_controls_panel(self):
        radio_ax = self.controls_ax.inset_axes([0.02, 0.7, 0.96, 0.25])
        self.radio = RadioButtons(radio_ax, ('Gaussian', 'Lorentzian', 'Pseudo-Voigt'), active=0)
        self.radio.on_clicked(self._on_fit_type_changed)

        dropdown_ax = self.controls_ax.inset_axes([0.02, 0.55, 0.96, 0.1])
        self.dropdown = RadioButtons(dropdown_ax, ('i0', 'i1'), active=0)
        self.dropdown.on_clicked(lambda label: setattr(self, 'detector_type', label))

        button_ax = self.controls_ax.inset_axes([0.02, 0.4, 0.96, 0.1])
        self.button = Button(button_ax, 'Toggle Fit Line')
        self.button.on_clicked(lambda e: self._toggle_fit_line())

        self.controls_ax.text(0.02, 0.25, 'Select fit type and\ndetector above, then\ntoggle fit line visibility',
                              transform=self.controls_ax.transAxes, verticalalignment='top',
                              horizontalalignment='left', fontsize=9, 
                              bbox=dict(facecolor='lightyellow', alpha=0.7, pad=5))

        self.controls_ax.text(0.02, 0.15, "Move motor to", transform=self.controls_ax.transAxes,
                              verticalalignment='top', horizontalalignment='left', fontsize=10, fontweight='bold',
                              bbox=dict(facecolor='lightgray', alpha=0.8, pad=6))

        move_peak_ax = self.controls_ax.inset_axes([0.02, 0.02, 0.46, 0.08])
        move_com_ax = self.controls_ax.inset_axes([0.52, 0.02, 0.46, 0.08])
        self.move_peak_btn = Button(move_peak_ax, "peak")
        self.move_com_btn = Button(move_com_ax, "COM")
        self.move_peak_btn.on_clicked(lambda e: self.dummy_motor.move(self.latest_center).wait() if self.latest_center is not None else print("Center position not available yet."))
        self.move_com_btn.on_clicked(lambda e: self.dummy_motor.move(self.latest_com).wait() if self.latest_com is not None else print("COM position not available yet."))

    def _on_fit_type_changed(self, label):
        self.fit_type = label
        if self.fit_line is not None:
            self.fit_line.set_label(f"{self.fit_type} Fit")
            self.fit_line.set_data([], [])
            self._update_legend()
            self.fig.canvas.draw_idle()
        self.refit_current_data()

    def _toggle_fit_line(self):
        if self.fit_line is not None:
            visible = self.fit_line.get_visible()
            self.fit_line.set_visible(not visible)
            self.fig.canvas.draw_idle()

    def update_stats(self, peak, center, fwhm, popt=None, com=None, auc=None):
        self.latest_com = com
        self.latest_center = center
        com_text = f"\nCOM: {com:.2f}" if com is not None else ""
        auc_text = f"\nAUC: {auc:.2f}" if auc is not None else ""
        stats_content = f"Peak: {peak:.1f}\nCenter: {center:.1f}{com_text}{auc_text}\nFWHM: {fwhm:.1f}"
        self.stats_text.set_text(stats_content)

        if popt is not None:
            labels = ['A', 'μ', 'σ'] if self.fit_type == 'Gaussian' else ['A', 'x₀', 'γ']
            if self.fit_type == 'Pseudo-Voigt':
                labels = ['A', 'x₀', 'σ', 'γ', 'η']
            param_str = "\n".join(f"{k} = {v:.3f}" for k, v in zip(labels, popt))
            if self.fit_type == 'Gaussian':
                eq_str = r"y = A × e^(−(x − μ)²/(2σ²))"
            elif self.fit_type == 'Lorentzian':
                eq_str = r"y = A × γ²/((x − x₀)² + γ²)"
            else:
                eq_str = r"y = A × [(1 − η) × e^(−(x − x₀)²/(2σ²)) + η × γ²/((x − x₀)² + γ²)]"
            full_eq_text = f"{self.fit_type} Fit Parameters:\n{param_str}\n\nEquation:\n{eq_str}"
            self.eq_text.set_text(full_eq_text)
        else:
            self.eq_text.set_text('')
        self.fig.canvas.draw_idle()

    def __call__(self, name, doc):
        if name == 'event':
            if self.y in doc['data'] and self.x in doc['data']:
                y_val = doc['data'][self.y]
                x_val = doc['data'][self.x]
                if self.line is None:
                    self.line, = self.ax.plot([], [], 'b-', label='Raw Data')
                    self.fit_line, = self.ax.plot([], [], 'r-', label=f'{self.fit_type} Fit')
                    self._update_legend()
                x_data = list(self.line.get_xdata())
                y_data = list(self.line.get_ydata())
                x_data.append(x_val)
                y_data.append(y_val)
                self.line.set_data(x_data, y_data)
                self.ax.relim()
                self.ax.autoscale_view()
                self.fig.canvas.draw_idle()

    def _update_legend(self):
        self.ax.legend(*self.ax.get_legend_handles_labels(), loc='upper right')
        self.fig.canvas.draw_idle()

    def refit_current_data(self):
        if len(self.x_data) > 10 and len(self.x_data) == len(self.y_data):
            calculate_stats(self, self.x_data, self.y_data)

def gaussian(x, a=1, mu=0, sigma=1):
    return a * np.exp(-((x - mu)**2) / (2 * sigma**2))

def lorentzian(x, a=1, x0=0, gamma=1):
    return a * (gamma**2) / ((x - x0)**2 + gamma**2)

def pseudo_voigt(x, a=1, x0=0, sigma=1, gamma=1, eta=0.5):
    g = np.exp(-((x - x0)**2) / (2 * sigma**2))
    l = (gamma**2) / ((x - x0)**2 + gamma**2)
    return a * ((1 - eta) * g + eta * l)

def gaussian_data_generator():
    x_range = np.linspace(0, 100, 200)
    for x in x_range:
        dummy_signal = gaussian(x, A, mu, sigma)
        noisy_signal = np.random.poisson(dummy_signal)
        yield x, noisy_signal

def calculate_stats(plot, x, y):
    x, y = np.array(x), np.array(y)
    if len(x) < 10 or len(x) != len(y): return
    sort_idx = np.argsort(x)
    x, y = x[sort_idx], y[sort_idx]
    peak = np.max(y)
    center = x[np.argmax(y)]
    com = np.sum(x * y) / np.sum(y)
    auc = np.trapezoid(y, x)
    try:
        if plot.fit_type == 'Gaussian':
            model = Model(gaussian)
            params = model.make_params(a=peak, mu=center, sigma=sigma)
        elif plot.fit_type == 'Lorentzian':
            model = Model(lorentzian)
            params = model.make_params(a=peak, x0=center, gamma=sigma)
        elif plot.fit_type == 'Pseudo-Voigt':
            model = Model(pseudo_voigt)
            params = model.make_params(a=peak, x0=center, sigma=sigma, gamma=sigma, eta=0.5)
            params['eta'].min, params['eta'].max = 0, 1
        fit_result = model.fit(y, params, x=x)
        y_fit = model.eval(fit_result.params, x=np.linspace(x.min(), x.max(), 500))
        plot.fit_line.set_data(np.linspace(x.min(), x.max(), 500), y_fit)
        plot.ax.relim()
        plot.ax.autoscale_view()
        popt = list(fit_result.best_values.values())
    except Exception as e:
        print(f"Fit failed: {e}")
        popt = None
    half_max = peak / 2
    indices = np.where(y >= half_max)[0]
    fwhm = float('nan') if len(indices) < 2 else x[indices[-1]] - x[indices[0]]
    plot.update_stats(peak, center, fwhm, popt, com, auc)

def stream(plot):
    global last_analysis_time
    yield Msg('open_run')
    try:
        for x, y in data_gen:
            intensity_signal.put(y)
            theta_signal.put(x)
            x_vals.append(x)
            y_vals.append(y)
            plot.x_data = x_vals
            plot.y_data = y_vals
            yield Msg('create', name='primary')
            yield Msg('read', intensity_signal)
            yield Msg('read', theta_signal)
            yield Msg('save')
            if time.time() - last_analysis_time >= STATS_REFRESH_INTERVAL:
                calculate_stats(plot, x_vals, y_vals)
                last_analysis_time = time.time()
            yield from bps.sleep(0.05)
    finally:
        yield Msg('close_run')


# --- Execution setup ---
last_analysis_time = time.time()
x_vals, y_vals = [], []
data_gen = gaussian_data_generator()
intensity_signal = SynSignal(name='intensity', func=lambda: 0)
theta_signal = SynSignal(name='theta', func=lambda: 0)

plot = OverlayedLivePlot('intensity', 'theta')
RE = RunEngine({})
RE.subscribe(plot)

RE(stream(plot))

timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
data_filename = DATA_DIR / f'xrd_raw_data_{timestamp}.csv'
plot_filename = DATA_DIR / f'xrd_plot_{timestamp}.png'

np.savetxt(data_filename, np.column_stack((x_vals, y_vals)), delimiter=',', header='theta,intensity', comments='')
print(f'Saved data to {data_filename}')

plot.ax.figure.savefig(plot_filename)
print(f'Saved plot to {plot_filename}')

plt.show(block=True)


