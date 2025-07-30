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
from IPython import display

# Import the real i0 counter from config
try:
    from config.counters import i0, i1, i2, bs, set_count_time
    REAL_COUNTERS_AVAILABLE = True
    print("Real counters imported successfully")
except ImportError as e:
    print(f"Warning: Could not import real counters: {e}")
    print("Falling back to simulated counters")
    from ophyd.sim import SynSignal
    REAL_COUNTERS_AVAILABLE = False

# Interval between stats panel refreshes in seconds
STATS_REFRESH_INTERVAL = 1

DATA_DIR = Path('data')
DATA_DIR.mkdir(exist_ok=True)
print(f"Data directory created/confirmed: {DATA_DIR.absolute()}")

# Configure matplotlib for Jupyter notebook compatibility
try:
    # Try to use widget backend for interactive plots
    get_ipython().run_line_magic('matplotlib', 'widget')
    print("Using matplotlib widget backend for interactive plots")
    INTERACTIVE_MODE = True
except:
    # Fallback to inline if widget is not available
    matplotlib.use('inline')
    print("Using matplotlib inline backend")
    INTERACTIVE_MODE = False

plt.ioff()  # Turn off interactive mode initially

class LiveCounterPlot:
    def __init__(self, counter_name='i0', integration_time=1.0):
        self.counter_name = counter_name
        self.integration_time = integration_time
        
        # Set up the counter
        if REAL_COUNTERS_AVAILABLE:
            self.counter = {'i0': i0, 'i1': i1, 'i2': i2, 'bs': bs}[counter_name]
            set_count_time(integration_time)
            print(f"Using real counter: {counter_name}")
        else:
            # Fallback to simulated counter
            self.counter = SynSignal(name=counter_name, func=lambda: np.random.normal(100, 10))
            print(f"Using simulated counter: {counter_name}")
        
        self.fit_type = 'Gaussian'
        self.x_data = []  # timestamps
        self.y_data = []  # counter values
        self.latest_com = None
        self.latest_center = None
        self.start_time = None
        
        # Stats for display
        self.current_stats = {
            'current_val': None,
            'mean_val': None,
            'std_val': None,
            'peak': None,
            'center': None,
            'com': None,
            'auc': None,
            'fwhm': None,
            'fit_params': None
        }
        
        # Setup the plot
        self._create_figure()

    def _create_figure(self):
        """Create or recreate the figure"""
        plt.close('all')  # Close any existing figures
        
        self.fig, axes = plt.subplots(1, 3, figsize=(15, 5), 
                                     gridspec_kw={'width_ratios': [1, 2, 1]})
        
        # Stats panel (left)
        self.stats_ax = axes[0]
        self.stats_ax.set_xlim(0, 1)
        self.stats_ax.set_ylim(0, 1)
        self.stats_ax.axis('off')
        self.stats_ax.set_title('Live Statistics', fontsize=11, fontweight='bold')
        
        # Main plot (center)
        self.ax = axes[1]
        self.ax.set_xlabel('Time (s)')
        self.ax.set_ylabel(f'{self.counter_name} Integrated Value')
        self.ax.set_title(f'Live {self.counter_name} Data Stream')
        self.ax.grid(True, alpha=0.3)
        
        # Controls panel (right)
        self.controls_ax = axes[2]
        self.controls_ax.set_xlim(0, 1)
        self.controls_ax.set_ylim(0, 1)
        self.controls_ax.axis('off')
        self.controls_ax.set_title('Info', fontsize=11, fontweight='bold')
        
        plt.tight_layout()

    def _update_plot(self):
        """Update the plot with current data"""
        if not self.x_data or not self.y_data:
            return
            
        # Clear and replot the main data
        self.ax.clear()
        self.ax.set_xlabel('Time (s)')
        self.ax.set_ylabel(f'{self.counter_name} Integrated Value')
        self.ax.set_title(f'Live {self.counter_name} Data Stream (n={len(self.x_data)})')
        self.ax.grid(True, alpha=0.3)
        
        # Plot the data
        self.ax.plot(self.x_data, self.y_data, 'b-o', label='Live Data', 
                    linewidth=2, markersize=4, alpha=0.8)
        
        # Add fit line if we have fit parameters
        if (self.current_stats['fit_params'] is not None and 
            len(self.x_data) > 5):
            x_fit = np.linspace(min(self.x_data), max(self.x_data), 100)
            try:
                if self.fit_type == 'Gaussian':
                    y_fit = gaussian(x_fit, *self.current_stats['fit_params'])
                elif self.fit_type == 'Lorentzian':
                    y_fit = lorentzian(x_fit, *self.current_stats['fit_params'])
                elif self.fit_type == 'Linear':
                    y_fit = linear(x_fit, *self.current_stats['fit_params'])
                
                self.ax.plot(x_fit, y_fit, 'r-', label=f'{self.fit_type} Fit', 
                           linewidth=2, alpha=0.7)
            except:
                pass  # Fit failed, skip plotting
        
        self.ax.legend()
        
        # Update stats panel
        self._update_stats_display()
        
        # Update info panel
        self._update_info_display()

    def _update_stats_display(self):
        """Update the statistics display panel"""
        self.stats_ax.clear()
        self.stats_ax.set_xlim(0, 1)
        self.stats_ax.set_ylim(0, 1)
        self.stats_ax.axis('off')
        self.stats_ax.set_title('Live Statistics', fontsize=11, fontweight='bold')
        
        # Build stats text
        stats_lines = [f"Counter: {self.counter_name}"]
        
        if self.current_stats['current_val'] is not None:
            stats_lines.append(f"Current: {self.current_stats['current_val']:.4f}")
        if self.current_stats['mean_val'] is not None:
            stats_lines.append(f"Mean: {self.current_stats['mean_val']:.4f}")
        if self.current_stats['std_val'] is not None:
            stats_lines.append(f"Std: {self.current_stats['std_val']:.4f}")
        if self.current_stats['peak'] is not None:
            stats_lines.append(f"Peak: {self.current_stats['peak']:.4f}")
        if self.current_stats['com'] is not None:
            stats_lines.append(f"COM: {self.current_stats['com']:.2f}s")
        if self.current_stats['auc'] is not None:
            stats_lines.append(f"AUC: {self.current_stats['auc']:.3f}")
        
        stats_text = "\n".join(stats_lines)
        self.stats_ax.text(0.05, 0.95, stats_text, transform=self.stats_ax.transAxes,
                          verticalalignment='top', horizontalalignment='left', fontsize=9,
                          bbox=dict(facecolor='lightblue', alpha=0.8, pad=5))

    def _update_info_display(self):
        """Update the info display panel"""
        self.controls_ax.clear()
        self.controls_ax.set_xlim(0, 1)
        self.controls_ax.set_ylim(0, 1)
        self.controls_ax.axis('off')
        self.controls_ax.set_title('Info', fontsize=11, fontweight='bold')
        
        # Show fit information
        info_lines = [f"Fit Type: {self.fit_type}"]
        info_lines.append(f"Integration: {self.integration_time}s")
        info_lines.append(f"Data Points: {len(self.x_data)}")
        
        if self.current_stats['fit_params'] is not None:
            if self.fit_type == 'Gaussian':
                labels = ['A', 'μ', 'σ']
            elif self.fit_type == 'Lorentzian':
                labels = ['A', 'x₀', 'γ']
            else:  # Linear
                labels = ['slope', 'intercept']
            
            info_lines.append("\nFit Parameters:")
            for label, param in zip(labels, self.current_stats['fit_params']):
                info_lines.append(f"{label}: {param:.4f}")
        
        info_text = "\n".join(info_lines)
        self.controls_ax.text(0.05, 0.95, info_text, transform=self.controls_ax.transAxes,
                             verticalalignment='top', horizontalalignment='left', fontsize=8,
                             bbox=dict(facecolor='lightyellow', alpha=0.8, pad=5))

    def add_data_point(self):
        """Add a new data point from the counter"""
        if self.start_time is None:
            self.start_time = time.time()
        
        current_time = time.time()
        relative_time = current_time - self.start_time
        
        if REAL_COUNTERS_AVAILABLE:
            # Trigger the real counter
            status = self.counter.trigger()
            while not status.done:
                time.sleep(0.01)  # Small sleep to avoid busy waiting
            value = self.counter.read()[self.counter.name]['value']
        else:
            # Use simulated data
            value = self.counter.get()
        
        self.x_data.append(relative_time)
        self.y_data.append(value)
        
        return relative_time, value

    def calculate_and_update_stats(self):
        """Calculate statistics and update the stats dictionary"""
        if len(self.x_data) < 2:
            return
            
        x, y = np.array(self.x_data), np.array(self.y_data)
        
        # Basic statistics
        self.current_stats['current_val'] = y[-1]
        self.current_stats['mean_val'] = np.mean(y)
        self.current_stats['std_val'] = np.std(y)
        self.current_stats['peak'] = np.max(y)
        self.current_stats['center'] = x[np.argmax(y)]
        self.current_stats['com'] = np.sum(x * y) / np.sum(y)
        self.current_stats['auc'] = np.trapz(y, x)
        
        # Try to fit the data
        if len(x) > 5:
            try:
                if self.fit_type == 'Gaussian':
                    model = Model(gaussian)
                    params = model.make_params(a=self.current_stats['peak'], 
                                             mu=self.current_stats['center'], 
                                             sigma=self.current_stats['std_val'])
                elif self.fit_type == 'Lorentzian':
                    model = Model(lorentzian)
                    params = model.make_params(a=self.current_stats['peak'], 
                                             x0=self.current_stats['center'], 
                                             gamma=self.current_stats['std_val'])
                elif self.fit_type == 'Linear':
                    model = Model(linear)
                    slope_guess = (y[-1] - y[0]) / (x[-1] - x[0]) if len(x) > 1 else 0
                    params = model.make_params(slope=slope_guess, intercept=y[0])
                
                fit_result = model.fit(y, params, x=x)
                self.current_stats['fit_params'] = list(fit_result.best_values.values())
                
            except Exception as e:
                print(f"Fit failed: {e}")
                self.current_stats['fit_params'] = None

    def run_live_monitoring(self, num_points=100, delay=0.5):
        """Run live monitoring for a specified number of points"""
        print(f"Starting live monitoring of {self.counter_name} for {num_points} points...")
        print("Note: Plot updates every few points to improve performance")
        
        last_analysis_time = time.time()
        last_plot_update = time.time()
        
        for i in range(num_points):
            # Add new data point
            rel_time, value = self.add_data_point()
            
            # Calculate stats periodically
            if time.time() - last_analysis_time >= STATS_REFRESH_INTERVAL:
                self.calculate_and_update_stats()
                last_analysis_time = time.time()
            
            # Update plot less frequently to improve performance
            if (time.time() - last_plot_update >= 2.0 or i == num_points - 1):
                self.calculate_and_update_stats()  # Ensure stats are current
                self._update_plot()
                
                # Display the updated plot
                display.clear_output(wait=True)
                display.display(self.fig)
                
                last_plot_update = time.time()
            
            print(f"Point {i+1}/{num_points}: t={rel_time:.1f}s, {self.counter_name}={value:.4f}")
            
            # Delay between measurements
            if delay > 0:
                time.sleep(delay)
        
        # Final update
        self.calculate_and_update_stats()
        self._update_plot()
        display.clear_output(wait=True)
        display.display(self.fig)
        
        print("Live monitoring completed!")
        return self.x_data, self.y_data

    def save_data(self, filename=None):
        """Save the collected data to a CSV file"""
        if not self.x_data or not self.y_data:
            print("No data to save")
            return
        
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = DATA_DIR / f'{self.counter_name}_live_data_{timestamp}.csv'
        
        data = np.column_stack((self.x_data, self.y_data))
        np.savetxt(filename, data, delimiter=',', 
                   header=f'time_s,{self.counter_name}_integrated', comments='')
        print(f'Saved data to {filename}')
        
        # Also save the plot
        plot_filename = str(filename).replace('.csv', '.png')
        self.fig.savefig(plot_filename, dpi=150, bbox_inches='tight')
        print(f'Saved plot to {plot_filename}')

    def set_fit_type(self, fit_type):
        """Change the fit type and recalculate"""
        if fit_type in ['Gaussian', 'Lorentzian', 'Linear']:
            self.fit_type = fit_type
            self.calculate_and_update_stats()
            self._update_plot()
            display.clear_output(wait=True)
            display.display(self.fig)


# Fitting functions
def gaussian(x, a=1, mu=0, sigma=1):
    return a * np.exp(-((x - mu)**2) / (2 * sigma**2))

def lorentzian(x, a=1, x0=0, gamma=1):
    return a * (gamma**2) / ((x - x0)**2 + gamma**2)

def linear(x, slope=1, intercept=0):
    return slope * x + intercept


# Convenience functions for easy use
def start_live_monitoring(counter_name='i0', integration_time=1.0, num_points=100, delay=0.5):
    """Start live monitoring with specified parameters"""
    plot = LiveCounterPlot(counter_name=counter_name, integration_time=integration_time)
    x_data, y_data = plot.run_live_monitoring(num_points=num_points, delay=delay)
    plot.save_data()
    return plot, x_data, y_data

def quick_monitoring(counter_name='i0', num_points=20, delay=1.0):
    """Quick monitoring for testing"""
    plot = LiveCounterPlot(counter_name=counter_name, integration_time=0.5)
    x_data, y_data = plot.run_live_monitoring(num_points=num_points, delay=delay)
    return plot, x_data, y_data


if __name__ == "__main__":
    # Example usage
    print("Starting live counter monitoring...")
    plot, x_data, y_data = start_live_monitoring(counter_name='i0', num_points=50, delay=1.0)
    plt.show()