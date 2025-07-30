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

x_vals_list = [[] for _ in range(4)]
y_vals_list = [[] for _ in range(4)]
intensity_signals = []
theta_signals = []
last_analysis_time = time.time()

class OverlayedLivePlot(LivePlot):
    shared_fig = None
    
    def __init__(self, y, x, counter_name, subplot_position, counter_idx):
        self.y = y
        self.x = x
        self.counter_name = counter_name
        self.subplot_position = subplot_position
        self.counter_idx = counter_idx
        self.text = None
        self.eq_text = None
        self.fit_line = None
        self.button = None
        self.radio = None
        self.fit_type = 'Gaussian'
        self.x_data = []
        self.y_data = []
        self.dummy_motor = SynAxis(name=f'dummy_motor_{counter_name}')
        self.latest_com = None
        self.latest_center = None

        # Create shared figure for all 4 counters
        if OverlayedLivePlot.shared_fig is None:
            OverlayedLivePlot.shared_fig = plt.figure(figsize=(20, 12))
        
        self.fig = OverlayedLivePlot.shared_fig
        
        # Create individual subplot with stats and controls
        row, col = subplot_position
        gs_main = self.fig.add_gridspec(2, 2, hspace=0.3, wspace=0.3)
        self.sub_gs = gs_main[row, col].subgridspec(1, 3, width_ratios=[1, 3, 1], hspace=0.05, wspace=0.02)
        
        self.stats_ax = self.fig.add_subplot(self.sub_gs[0, 0])
        self.stats_ax.set_xlim(0, 1)
        self.stats_ax.set_ylim(0, 1)
        self.stats_ax.axis('off')
        self.stats_ax.set_title(f'{counter_name} Statistics', fontsize=10, fontweight='bold', ha='left')
        
        self.ax = self.fig.add_subplot(self.sub_gs[0, 1])
        self.controls_ax = self.fig.add_subplot(self.sub_gs[0, 2])
        self.controls_ax.set_xlim(0, 1)
        self.controls_ax.set_ylim(0, 1)
        self.controls_ax.axis('off')
        self.controls_ax.set_title(f'{counter_name} Controls', fontsize=10, fontweight='bold', ha='right')
        
        self.ax.set_xlabel(x)
        self.ax.set_ylabel(y)
        self.ax.set_title(f'{counter_name} XRD Data')
        self.line = None

        self._setup_stats_panel()
        self._setup_controls_panel()

    def _setup_stats_panel(self):
        self.instructions_text = self.stats_ax.text(
            0.0, 0.95, "Instructions here",
            transform=self.stats_ax.transAxes, verticalalignment='top',
            horizontalalignment='left', fontsize=8, 
            bbox=dict(facecolor='beige', alpha=0.9, pad=6))

        self.stats_text = self.stats_ax.text(
            0.0, 0.7, 'Waiting for data...',
            transform=self.stats_ax.transAxes, verticalalignment='top',
            horizontalalignment='left', fontsize=8, 
            bbox=dict(facecolor='lightblue', alpha=0.7, pad=8))

        self.eq_text = self.stats_ax.text(
            0.0, 0.3, '', transform=self.stats_ax.transAxes,
            verticalalignment='top', horizontalalignment='left', fontsize=7,
            bbox=dict(facecolor='lightgreen', alpha=0.7, pad=6), wrap=True)

    def _setup_controls_panel(self):
        radio_ax = self.controls_ax.inset_axes([0.02, 0.7, 0.96, 0.25])
        self.radio = RadioButtons(radio_ax, ('Gaussian', 'Lorentzian', 'Pseudo-Voigt'), active=0)
        self.radio.on_clicked(self._on_fit_type_changed)

        button_ax = self.controls_ax.inset_axes([0.02, 0.4, 0.96, 0.1])
        self.button = Button(button_ax, 'Toggle Fit Line')
        self.button.on_clicked(lambda e: self._toggle_fit_line())

        self.controls_ax.text(0.02, 0.25, 'Select fit type above,\nthen toggle fit line\nvisibility',
                              transform=self.controls_ax.transAxes, verticalalignment='top',
                              horizontalalignment='left', fontsize=7, 
                              bbox=dict(facecolor='lightyellow', alpha=0.7, pad=4))

        self.controls_ax.text(0.02, 0.15, "Move motor to", transform=self.controls_ax.transAxes,
                              verticalalignment='top', horizontalalignment='left', fontsize=8, fontweight='bold',
                              bbox=dict(facecolor='lightgray', alpha=0.8, pad=5))

        move_peak_ax = self.controls_ax.inset_axes([0.02, 0.02, 0.46, 0.08])
        move_com_ax = self.controls_ax.inset_axes([0.52, 0.02, 0.46, 0.08])
        self.move_peak_btn = Button(move_peak_ax, "peak")
        self.move_com_btn = Button(move_com_ax, "COM")
        self.move_peak_btn.on_clicked(lambda e: self.dummy_motor.move(self.latest_center).wait() if self.latest_center is not None else print(f"{self.counter_name} Center position not available yet."))
        self.move_com_btn.on_clicked(lambda e: self.dummy_motor.move(self.latest_com).wait() if self.latest_com is not None else print(f"{self.counter_name} COM position not available yet."))

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

def gaussian_data_generator(peak_shift=0, amplitude_factor=1, sigma_factor=1, noise_level=1):
    x_range = np.linspace(0, 100, 200)
    for x in x_range:
        dummy_signal = gaussian(x, A * amplitude_factor, mu + peak_shift, sigma * sigma_factor)
        noisy_signal = np.random.poisson(dummy_signal * noise_level)
        yield x, noisy_signal

def lorentzian_data_generator(peak_shift=0, amplitude_factor=1, gamma_factor=1, noise_level=1):
    x_range = np.linspace(0, 100, 200)
    for x in x_range:
        dummy_signal = lorentzian(x, A * amplitude_factor, mu + peak_shift, sigma * gamma_factor)
        noisy_signal = np.random.poisson(dummy_signal * noise_level)
        yield x, noisy_signal

def double_peak_data_generator(peak_shift=0, amplitude_factor=1, separation=15, noise_level=1):
    x_range = np.linspace(0, 100, 200)
    for x in x_range:
        peak1 = gaussian(x, A * amplitude_factor * 0.7, mu + peak_shift - separation/2, sigma * 0.8)
        peak2 = gaussian(x, A * amplitude_factor * 0.9, mu + peak_shift + separation/2, sigma * 1.2)
        dummy_signal = peak1 + peak2
        noisy_signal = np.random.poisson(dummy_signal * noise_level)
        yield x, noisy_signal

def sine_wave_data_generator(peak_shift=0, amplitude_factor=1, frequency=0.2, noise_level=1):
    x_range = np.linspace(0, 100, 200)
    for x in x_range:
        base_signal = gaussian(x, A * amplitude_factor, mu + peak_shift, sigma)
        sine_modulation = 1 + 0.3 * np.sin(2 * np.pi * frequency * x)
        dummy_signal = base_signal * sine_modulation
        noisy_signal = np.random.poisson(dummy_signal * noise_level)
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

def stream_counter(plot, data_gen, counter_idx):
    global last_analysis_time
    yield Msg('open_run')
    try:
        for x, y in data_gen:
            intensity_signals[counter_idx].put(y)
            theta_signals[counter_idx].put(x)
            x_vals_list[counter_idx].append(x)
            y_vals_list[counter_idx].append(y)
            plot.x_data = x_vals_list[counter_idx]
            plot.y_data = y_vals_list[counter_idx]
            yield Msg('create', name='primary')
            yield Msg('read', intensity_signals[counter_idx])
            yield Msg('read', theta_signals[counter_idx])
            yield Msg('save')
            if time.time() - last_analysis_time >= STATS_REFRESH_INTERVAL:
                calculate_stats(plot, x_vals_list[counter_idx], y_vals_list[counter_idx])
                last_analysis_time = time.time()
            yield from bps.sleep(0.05)
    finally:
        yield Msg('close_run')

# --- Execution setup ---

# Create 4 different data generators with distinct characteristics
data_generators = [
    gaussian_data_generator(peak_shift=0, amplitude_factor=1, sigma_factor=1, noise_level=1),      # Counter 1: Standard Gaussian
    lorentzian_data_generator(peak_shift=5, amplitude_factor=0.8, gamma_factor=1.5, noise_level=1.2),    # Counter 2: Lorentzian peak
    double_peak_data_generator(peak_shift=-3, amplitude_factor=1.2, separation=20, noise_level=0.8),   # Counter 3: Double peak
    sine_wave_data_generator(peak_shift=8, amplitude_factor=0.9, frequency=0.15, noise_level=1.1)     # Counter 4: Sine-modulated peak
]

# Create signals for each counter
intensity_signals = [SynSignal(name=f'intensity_{i}', func=lambda: 0) for i in range(4)]
theta_signals = [SynSignal(name=f'theta_{i}', func=lambda: 0) for i in range(4)]

# Create 4 plot instances with descriptive names
counter_names = ['Gaussian Peak', 'Lorentzian Peak', 'Double Peak', 'Sine Modulated']
subplot_positions = [(0, 0), (0, 1), (1, 0), (1, 1)]

plots = []
for i, (counter_name, pos) in enumerate(zip(counter_names, subplot_positions)):
    plot = OverlayedLivePlot(f'intensity_{i}', f'theta_{i}', counter_name, pos, i)
    plots.append(plot)

# Create and configure RunEngine
RE = RunEngine({})
for plot in plots:
    RE.subscribe(plot)

# Run streams for each counter sequentially
for i, (plot, data_gen) in enumerate(zip(plots, data_generators)):
    print(f"Running Counter {i+1}...")
    RE(stream_counter(plot, data_gen, i))

# Save data for each counter
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
for i, (x_vals, y_vals) in enumerate(zip(x_vals_list, y_vals_list)):
    if x_vals and y_vals:  # Only save if we have data
        data_filename = DATA_DIR / f'xrd_raw_data_counter_{i+1}_{timestamp}.csv'
        np.savetxt(data_filename, np.column_stack((x_vals, y_vals)), delimiter=',', header='theta,intensity', comments='')
        print(f'Saved Counter {i+1} data to {data_filename}')

# Save the combined plot
if OverlayedLivePlot.shared_fig is not None:
    plot_filename = DATA_DIR / f'xrd_plot_4counters_{timestamp}.png'
    OverlayedLivePlot.shared_fig.savefig(plot_filename, dpi=300, bbox_inches='tight')
    print(f'Saved plot to {plot_filename}')

plt.show(block=True)