#pip install numpy matplotlib bluesky ophyd pyqt6 lmfit
from dataclasses import dataclass
from pathlib import Path
import time
import csv
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.widgets import RadioButtons, Slider, CheckButtons, Button
from lmfit.models import GaussianModel, LorentzianModel, PseudoVoigtModel
from bluesky import RunEngine
from bluesky.plans import scan
from bluesky.callbacks import CallbackBase
from ophyd import Device, Component as Cpt
from ophyd.sim import SynSignal, SynAxis



matplotlib.use('QtAgg')
plt.ion()

DUMMY_DATA = True
SEPARATE_CONTROLS = False
IMAGE_SIZE = 100
DETECTOR_SHAPE = (IMAGE_SIZE, IMAGE_SIZE)
DEFAULT_FILENAME = 'detector_data.csv'
FIT_MODES = ['gaussian', 'lorentzian', 'pseudo_voigt']
SLICE_MODES = ['row', 'col']
MAX_STORED_IMAGES = 1000
MIN_UPDATE_INTERVAL = .5 #seconds 


@dataclass
class ImageData:
    """Data class for storing image information"""
    timestamp: float
    image: np.ndarray
    motor_position: float = None
    
@dataclass
class FitResult:
    """Data class for storing fit results"""
    best_fit: np.ndarray
    best_values: dict
    r_squared: float
    model_name: str

def save_image_data(image_array: np.ndarray, timestamp: float, filename: str = DEFAULT_FILENAME) -> bool:
    """Save image data to CSV with timestamp"""
    try:
        # Validate input
        if not isinstance(image_array, np.ndarray):
            raise ValueError("image_array must be a numpy array")
        if image_array.shape != DETECTOR_SHAPE:
            image_array = np.resize(image_array, DETECTOR_SHAPE)
        
        # Flatten the 2D array and add timestamp as first column
        flat_data = image_array.flatten()
        row = [timestamp] + flat_data.tolist()
        
        # Ensure directory exists
        filepath = Path(filename)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        # Check if file exists to determine if we need headers
        file_exists = filepath.exists()
        
        with open(filename, 'a', newline='') as f:
            writer = csv.writer(f)
            if not file_exists:
                # Write header: timestamp + pixel indices
                header = ['timestamp'] + [f'pixel_{i}' for i in range(len(flat_data))]
                writer.writerow(header)
            writer.writerow(row)
        
        return True
        
    except Exception as e:
        return False

def load_image_data(filename: str = DEFAULT_FILENAME):
    """Load all image data from CSV with proper error handling"""
    try:
        filepath = Path(filename)
        if not filepath.exists():
            return [], []
        
        timestamps = []
        images = []
        
        with open(filename, 'r') as f:
            reader = csv.reader(f)
            try:
                # Skip header
                header = next(reader)
            except StopIteration:
                return [], []
            
            for row_num, row in enumerate(reader, start=2):
                try:
                    if len(row) < 2:
                        continue
                    
                    timestamp = float(row[0])
                    image_data = np.array([float(x) for x in row[1:]], dtype=np.float32)
                    
                    if len(image_data) != IMAGE_SIZE * IMAGE_SIZE:
                        continue
                    
                    timestamps.append(timestamp)
                    # Reshape back to detector shape
                    images.append(image_data.reshape(DETECTOR_SHAPE))
                    
                except (ValueError, IndexError) as e:
                    continue
        
        return timestamps, images
        
    except Exception as e:
        return [], []

def dummy_2D_data(motor_pos: float = None) -> np.ndarray:
    """Simulated 2D detector image generator that mimics scanner behavior"""
    if motor_pos is None:
        motor_pos = 0.0
    
    x, y = np.meshgrid(np.linspace(-3, 3, IMAGE_SIZE), np.linspace(-3, 3, IMAGE_SIZE))
    
    # Peak position depends on motor position (simulating sample translation)
    center_x = motor_pos * 0.5 + 0.1 * np.sin(motor_pos * 2.0) + 0.05 * np.random.normal()
    center_y = motor_pos * 0.3 + 0.08 * np.cos(motor_pos * 1.5) + 0.04 * np.random.normal()
    
    # Width changes slightly with position
    width = 0.8 + 0.1 * np.sin(motor_pos * 0.8) + 0.03 * np.random.exponential(0.5)
    
    # Intensity varies with position (simulating sample thickness/absorption)
    intensity = 0.7 + 0.2 * np.exp(-0.1 * motor_pos**2) + 0.05 * np.random.uniform(0, 1)
    
    # Slight rotation with position
    angle = motor_pos * 0.02 + np.random.uniform(-0.05, 0.05)
    x_rot = x * np.cos(angle) - y * np.sin(angle)
    y_rot = x * np.sin(angle) + y * np.cos(angle)
    
    # Main peak
    z = intensity * np.exp(-((x_rot - center_x)**2 + (y_rot - center_y)**2) / width)
    
    # Position-dependent secondary features
    if abs(motor_pos - 1.0) < 0.5:
        # Feature appears near motor position 1.0
        feature_x = motor_pos - 1.0
        feature_y = 0.5 * np.sin(motor_pos * 3.0)
        feature_intensity = 0.3 * np.exp(-2 * (motor_pos - 1.0)**2)
        z += feature_intensity * np.exp(-((x - feature_x)**2 + (y - feature_y)**2) / 0.5)
    
    # Reduced noise
    noise = np.random.normal(0, 0.02, z.shape)
    
    # Position-dependent background
    background = 0.02 * (1 + 0.3 * np.sin(motor_pos)) + 0.01 * np.random.uniform(0, 1)
    
    return (z + noise + background).astype(np.float32)

class SimulatedEigerDevice(Device):
    image = Cpt(SynSignal, kind='hinted')

    def trigger(self):
        # Generate new data on each trigger, using motor position if available
        motor_pos = getattr(self, '_motor_pos', 0.0)
        new_data = dummy_2D_data(motor_pos)
        self.image.put(new_data)
        return super().trigger()
    
    def set_motor_position(self, pos):
        self._motor_pos = pos

image = SimulatedEigerDevice(name='eiger_image')

# Create a fake motor for scanning
fake_motor = SynAxis(name='fake_motor')

# Component classes for better organization
class ImageDisplayComponent:
    """Handles the main image display and visualization"""
    
    def __init__(self, ax, colormap='inferno'):
        self.ax = ax
        self.colormap = colormap
        self.img_obj = self.ax.imshow(np.zeros(DETECTOR_SHAPE), cmap=colormap, origin='lower',
                                     extent=[0, IMAGE_SIZE-1, 0, IMAGE_SIZE-1],
                                     vmin=0.0, vmax=1.0)
        self.ax.set_title("Live Eiger4M Image")
        self.ax.set_xlabel("X (pixels)")
        self.ax.set_ylabel("Y (pixels)")
        self.colorbar = None
        self.slice_line = None
        self.com_dot = None
        self.peak_dot = None
        self.roi_selector = None
        self.zoom_factory = None
        self.pan_factory = None
        self._setup_markers()
        self._setup_zoom_pan()
        
    def _setup_markers(self):
        """Initialize markers for slice, COM, and peak positions"""
        self.slice_line = self.ax.axhline(IMAGE_SIZE//2, color='red', linestyle='--', alpha=0.8, label='Slice')
        self.com_dot, = self.ax.plot([], [], 'o', color='cyan', markersize=8, label='COM')
        self.peak_dot, = self.ax.plot([], [], 'o', color='magenta', markersize=8, label='Peak')
        
    def update_image(self, image_data):
        """Update the displayed image"""
        self.img_obj.set_data(image_data)
        self.img_obj.set_clim(vmin=0.0, vmax=1.0)
        self.img_obj.set_extent([0, IMAGE_SIZE-1, 0, IMAGE_SIZE-1])
        
    def set_colormap(self, colormap):
        """Change the colormap"""
        self.colormap = colormap
        self.img_obj.set_cmap(colormap)
        
    def update_slice_markers(self, slice_mode, slice_index, com_pos, peak_pos, show_markers):
        """Update slice line and position markers"""
        if self.slice_line:
            self.slice_line.remove()
        
        if slice_mode == 'row':
            self.slice_line = self.ax.axhline(slice_index, color='red', linestyle='--', alpha=0.8, label='Slice')
            self.com_dot.set_data([com_pos], [slice_index])
            self.peak_dot.set_data([peak_pos], [slice_index])
        else:
            self.slice_line = self.ax.axvline(slice_index, color='red', linestyle='--', alpha=0.8, label='Slice')
            self.com_dot.set_data([slice_index], [com_pos])
            self.peak_dot.set_data([slice_index], [peak_pos])
        
        self.slice_line.set_visible(show_markers)
        self.com_dot.set_visible(show_markers)
        self.peak_dot.set_visible(show_markers)
        
        self.ax.legend(loc='upper right')
        
    def _setup_zoom_pan(self):
        """Setup zoom and pan functionality"""
        def zoom_fun(event):
            base_scale = 1.1
            if event.inaxes != self.ax:
                return
                
            cur_xlim = self.ax.get_xlim()
            cur_ylim = self.ax.get_ylim()
            xdata = event.xdata
            ydata = event.ydata
            
            if event.button == 'up':
                scale_factor = 1 / base_scale
            elif event.button == 'down':
                scale_factor = base_scale
            else:
                return
                
            new_width = (cur_xlim[1] - cur_xlim[0]) * scale_factor
            new_height = (cur_ylim[1] - cur_ylim[0]) * scale_factor
            
            relx = (cur_xlim[1] - xdata) / (cur_xlim[1] - cur_xlim[0])
            rely = (cur_ylim[1] - ydata) / (cur_ylim[1] - cur_ylim[0])
            
            self.ax.set_xlim([xdata - new_width * (1 - relx), xdata + new_width * relx])
            self.ax.set_ylim([ydata - new_height * (1 - rely), ydata + new_height * rely])
            
        def pan_fun(event):
            if event.inaxes != self.ax:
                return
            if event.button == 2:
                self.ax.pan = True
                
        self.ax.figure.canvas.mpl_connect('scroll_event', zoom_fun)
        self.ax.figure.canvas.mpl_connect('button_press_event', pan_fun)
        
    def setup_roi_selection(self, callback):
        """Setup ROI selection tool"""
        from matplotlib.widgets import RectangleSelector
        
        def onselect(eclick, erelease):
            x1, y1 = int(eclick.xdata), int(eclick.ydata)
            x2, y2 = int(erelease.xdata), int(erelease.ydata)
            callback(x1, y1, x2, y2)
            
        self.roi_selector = RectangleSelector(self.ax, onselect, 
                                            useblit=True, 
                                            button=[1], 
                                            minspanx=5, minspany=5,
                                            spancoords='pixels',
                                            interactive=True)
        
    def enable_roi_selection(self, enable=True):
        """Enable or disable ROI selection"""
        if self.roi_selector:
            self.roi_selector.set_active(enable)
            if not enable:
                self.roi_selector.set_visible(False)
            else:
                self.roi_selector.set_visible(True)
    
    def set_roi_rectangle(self, x1, y1, x2, y2):
        """Programmatically set the ROI rectangle"""
        if self.roi_selector:
            self.roi_selector.extents = (x1, x2, y1, y2)
            self.roi_selector.set_visible(True)
            self.roi_selector.update()

class FitDisplayComponent:
    """Handles the slice fitting display and analysis"""
    
    def __init__(self, ax):
        self.ax = ax
        self.line_data, = self.ax.plot([], [], label='Data', linewidth=2)
        self.line_fit, = self.ax.plot([], [], label='Fit', linewidth=2, linestyle='--')
        self.fit_text = self.ax.text(0.05, 0.95, '', transform=self.ax.transAxes,
                                    verticalalignment='top', fontsize=9,
                                    bbox=dict(facecolor='white', alpha=0.8, edgecolor='gray'))
        self.ax.set_title("Slice Fit Analysis")
        self.ax.legend()
        self.ax.grid(True, alpha=0.3)
        
    def update_fit(self, x_data, y_data, fit_result: FitResult = None, show_fit=True):
        """Update the fit display"""
        self.line_data.set_data(x_data, y_data)
        
        if fit_result:
            if show_fit:
                self.line_fit.set_data(x_data, fit_result.best_fit)
                self.line_fit.set_visible(True)
            else:
                self.line_fit.set_visible(False)
            
            clean_model_name = fit_result.model_name.replace("Model(", "").replace(")", "").lower()
            eqn = f"Model: {clean_model_name}\n"
            for name, val in fit_result.best_values.items():
                eqn += f"{name}: {val:.3f}\n"
            eqn += f"R²: {fit_result.r_squared:.3f}"
            self.fit_text.set_text(eqn)
            self.fit_text.set_visible(True)
        else:
            self.line_fit.set_visible(False)
            self.fit_text.set_visible(False)
        
        self.ax.relim()
        self.ax.autoscale_view()

class ControlsComponent:
    """Handles all UI controls and user interaction"""
    
    def __init__(self, ax, callbacks, separate_controls=False):
        self.ax = ax
        self.callbacks = callbacks
        self.separate_controls = separate_controls
        self.ax.axis('off')
        
        self.slice_index = IMAGE_SIZE // 2
        self.slice_mode = 'row'
        self.fit_mode = 'gaussian'
        self.show_markers = True
        self.show_fit = True
        
        self._setup_controls()
        
    def _setup_controls(self):
        """Create all control widgets with better spacing"""
        y_pos = 0.95
        control_height = 0.06
        spacing = 0.02
        
        self.ax.text(0.05, y_pos + 0.02, "Slice Index", fontsize=10, weight='bold')
        y_pos -= 0.03
        slider_ax = self.ax.inset_axes([0.05, y_pos, 0.9, control_height])
        self.slider = Slider(slider_ax, '', 0, IMAGE_SIZE-1, valinit=IMAGE_SIZE//2, valstep=1)
        self.slider.on_changed(self._on_slider_changed)
        y_pos -= control_height + spacing * 2
        
        self.ax.text(0.05, y_pos, "Slice Direction", fontsize=10, weight='bold')
        y_pos -= control_height * 2.0
        radio_ax = self.ax.inset_axes([0.05, y_pos, 0.9, control_height * 1.8])
        self.radio = RadioButtons(radio_ax, SLICE_MODES)
        self.radio.on_clicked(self._on_mode_changed)
        y_pos -= spacing * 2
        
        self.ax.text(0.05, y_pos, "Fit Function", fontsize=10, weight='bold')
        y_pos -= control_height * 2.5
        fit_ax = self.ax.inset_axes([0.05, y_pos, 0.9, control_height * 2.2])
        self.fit_radio = RadioButtons(fit_ax, FIT_MODES)
        self.fit_radio.on_clicked(self._on_fit_changed)
        y_pos -= spacing * 2
        
        check_y_pos = y_pos - control_height * 2.0
        check_ax = self.ax.inset_axes([0.05, check_y_pos, 0.9, control_height * 1.8])
        self.check = CheckButtons(check_ax, ['Show Markers', 'Show Fit'], [True, True])
        self.check.on_clicked(self._on_check_toggle)
        y_pos = check_y_pos - control_height * 0.5
        
        roi_ax = self.ax.inset_axes([0.05, y_pos - control_height, 0.9, control_height])
        self.roi_button = Button(roi_ax, 'ROI Select')
        self.roi_button.on_clicked(self._on_roi_button_clicked)
        self.roi_active = False
        
        if not self.separate_controls:
            stats_y_pos = y_pos - control_height * 1.6 + 0.01
            self.ax.text(0.05, stats_y_pos, "Statistics", fontsize=10, weight='bold')
            stats_y_pos -= control_height * 0.3
            stats_height = stats_y_pos - 0.04
            stats_rect = plt.Rectangle((0.05, 0.05), 0.9, stats_height, 
                                     facecolor='lightblue', alpha=0.8, edgecolor='gray',
                                     transform=self.ax.transAxes)
            self.ax.add_patch(stats_rect)
            self.stats_text = self.ax.text(0.07, stats_y_pos, '', transform=self.ax.transAxes,
                                          verticalalignment='top', fontsize=9,
                                          bbox=dict(facecolor='none', alpha=0))
            
    def update_statistics(self, image_data):
        """Update statistics display when controls are integrated"""
        if not self.separate_controls and hasattr(self, 'stats_text'):
            if image_data is None or image_data.size == 0:
                self.stats_text.set_text('No data')
                return
                
            stats = {
                'Mean': np.mean(image_data),
                'Std': np.std(image_data),
                'Min': np.min(image_data),
                'Max': np.max(image_data),
                'Sum': np.sum(image_data)
            }
            
            stats_str = "\n".join([f"{k}: {v:.3f}" for k, v in stats.items()])
            self.stats_text.set_text(stats_str)
        
    def _on_slider_changed(self, val):
        self.slice_index = int(val)
        self.callbacks['slice_changed'](self.slice_index)
        
    def _on_mode_changed(self, label):
        self.slice_mode = label
        self.callbacks['mode_changed'](label)
        
    def _on_fit_changed(self, label):
        self.fit_mode = label
        self.callbacks['fit_changed'](label)
        
    def _on_check_toggle(self, label):
        if label == 'Show Markers':
            self.show_markers = not self.show_markers
        elif label == 'Show Fit':
            self.show_fit = not self.show_fit
        self.callbacks['checkbox_changed'](label, self.show_markers, self.show_fit)
        
    def _on_roi_button_clicked(self, event):
        """Handle ROI button click"""
        self.roi_active = not self.roi_active
        if self.roi_active:
            self.roi_button.label.set_text('ROI: ON')
            self.roi_button.color = 'lightgreen'
        else:
            self.roi_button.label.set_text('ROI: OFF')
            self.roi_button.color = 'lightgray'
        
        self.ax.figure.canvas.draw_idle()
        
        self.callbacks['roi_toggled'](self.roi_active)

class StatisticsComponent:
    """Handles real-time statistics display"""
    
    def __init__(self, ax):
        self.ax = ax
        self.ax.axis('off')
        self.ax.set_title("Image Statistics", fontsize=10, weight='bold')
        
        self.stats_text = self.ax.text(0.05, 0.9, '', transform=self.ax.transAxes,
                                      verticalalignment='top', fontsize=9,
                                      bbox=dict(facecolor='lightblue', alpha=0.8, edgecolor='gray'))
        
    def update_statistics(self, image_data):
        """Update displayed statistics"""
        if image_data is None or image_data.size == 0:
            self.stats_text.set_text('No data')
            return
            
        stats = {
            'Mean': np.mean(image_data),
            'Std': np.std(image_data),
            'Min': np.min(image_data),
            'Max': np.max(image_data),
            'Sum': np.sum(image_data)
        }
        
        stats_str = "\n".join([f"{k}: {v:.3f}" if isinstance(v, (int, float)) else f"{k}: {v}" 
                              for k, v in stats.items()])
        self.stats_text.set_text(stats_str)

class TimeNavigationComponent:
    """Handles time-based navigation through stored images"""
    
    def __init__(self, slider_ax, button_ax, callbacks):
        self.slider_ax = slider_ax
        self.button_ax = button_ax
        self.callbacks = callbacks
        
        self.slider_ax.set_title('Time Navigation', fontsize=10)
        self.time_slider = Slider(self.slider_ax, '', 0, 1, valinit=1, valstep=1)
        self.time_slider.on_changed(self._on_time_slider_changed)
        self.time_slider.vline.set_visible(False)
        self.time_slider.valtext.set_visible(False)
        
        self.button_ax.axis('off')
        button_ax = self.button_ax.inset_axes([0.1, 0.3, 0.8, 0.4])
        self.live_button = Button(button_ax, 'LIVE')
        self.live_button.on_clicked(self._on_live_button_clicked)
        self.is_live_mode = True
        self._update_live_button_color()
        
    def _on_time_slider_changed(self, val):
        self.callbacks['time_changed'](int(val))
        
    def _on_live_button_clicked(self, event):
        self.callbacks['live_clicked']()
        
    def update_slider_range(self, max_index):
        """Update time slider range"""
        self.time_slider.valmin = 0
        self.time_slider.valmax = max(max_index, 1)
        self.time_slider.ax.set_xlim(0, max(max_index, 1))
        
        if self.is_live_mode:
            self.time_slider.set_val(max_index)
            
    def set_live_mode(self, is_live):
        """Set live mode state"""
        self.is_live_mode = is_live
        self._update_live_button_color()
        
    def _update_live_button_color(self):
        """Update live button appearance"""
        if self.is_live_mode:
            self.live_button.color = 'red'
            self.live_button.hovercolor = 'darkred'
        else:
            self.live_button.color = 'lightgray'
            self.live_button.hovercolor = 'gray'

class LiveImagePanel(CallbackBase):
    def __init__(self, colormap='inferno', separate_controls=False):
        """
        colormap : str, optional
            Colormap to use for image display. Default: 'inferno'
            Available options: 'viridis', 'plasma', 'inferno', 'magma', 'hot', 'cool', 
            'spring', 'summer', 'autumn', 'winter', 'jet', 'rainbow', 'seismic', 
            'RdYlBu', 'coolwarm', 'bwr', 'gray', 'bone', 'copper'
        separate_controls : bool, optional
        """
        self.colormap = colormap
        self.separate_controls = separate_controls
        
        self.fig = plt.figure(figsize=(12, 7))
        if separate_controls:
            gs = self.fig.add_gridspec(2, 2, width_ratios=[3, 1.5], height_ratios=[6, 1])
        else:
            gs = self.fig.add_gridspec(2, 3, width_ratios=[3, 1.5, 1], height_ratios=[6, 1])
        
        self.stored_timestamps = []
        self.stored_images = []
        self.is_live_mode = True
        self.current_index = -1

        self.ax_img = self.fig.add_subplot(gs[0, 0])
        self.image_display = ImageDisplayComponent(self.ax_img, self.colormap)
        self.colorbar = self.fig.colorbar(self.image_display.img_obj, ax=self.ax_img)
        self.colorbar.set_label('Intensity', rotation=270, labelpad=20)
        self.colorbar.mappable.set_clim(0.0, 1.0)

        self.ax_fit = self.fig.add_subplot(gs[0, 1])
        self.fit_display = FitDisplayComponent(self.ax_fit)
        
        if separate_controls:
            self.controls_fig = plt.figure(figsize=(3, 8))
            self.controls_ax = self.controls_fig.add_subplot(111)
        else:
            self.ax_controls = self.fig.add_subplot(gs[0, 2])
            self.controls_ax = self.ax_controls
            
        if separate_controls:
            self.ax_stats = self.fig.add_subplot(gs[0, 1])
            self.stats_display = StatisticsComponent(self.ax_stats)
        else:
            self.stats_display = None

        if separate_controls:
            self.ax_time_slider = self.fig.add_subplot(gs[1, 0:2])
            self.ax_live_button = self.fig.add_subplot(gs[1, 1])
        else:
            self.ax_time_slider = self.fig.add_subplot(gs[1, 0:2])
            self.ax_live_button = self.fig.add_subplot(gs[1, 2])

        self.img_data = np.zeros(DETECTOR_SHAPE, dtype=np.float32)
        self.update_pending = False
        self.last_update_time = 0
        
        control_callbacks = {
            'slice_changed': self._on_slice_changed,
            'mode_changed': self._on_mode_changed,
            'fit_changed': self._on_fit_changed,
            'checkbox_changed': self._on_checkbox_changed,
            'roi_toggled': self._on_roi_toggled
        }
        
        self.roi_data = None
        self.roi_stats = None
        
        self.controls = ControlsComponent(self.controls_ax, control_callbacks, separate_controls)
        
        time_callbacks = {
            'time_changed': self._on_time_changed,
            'live_clicked': self._on_live_clicked
        }
        self.time_nav = TimeNavigationComponent(self.ax_time_slider, self.ax_live_button, time_callbacks)
        
        self.timestamp_text = self.ax_time_slider.text(1.02, 0.5, 't=--', ha='left', va='center', fontsize=12, transform=self.ax_time_slider.transAxes)
        self.image_timestamp = None
        
        self.progress_text = self.fig.text(0.02, 0.02, '', ha='left', va='bottom', fontsize=10, 
                                          bbox=dict(facecolor='yellow', alpha=0.7))
        self.progress_text.set_visible(False)
        self.scan_progress = 0
        self.scan_total = 0
        
        self._update_slice_fit()

        plt.tight_layout()
        self.fig.subplots_adjust(bottom=0.15)
        
        self._setup_export_functionality()
        
        self._setup_keyboard_shortcuts()
        
        self._setup_info_icon()
        
        self.image_display.setup_roi_selection(self._on_roi_selected)

    def _setup_export_functionality(self):
        """Add export functionality for plots and data"""
        self.export_options = {
            'image': self._export_image,
            'data': self._export_data,
            'plot': self._export_plot
        }
        
    def _setup_keyboard_shortcuts(self):
        """Setup keyboard shortcuts for common operations"""
        def on_key_press(event):
            if event.key == 'left':
                self._navigate_time(-1)
            elif event.key == 'right':
                self._navigate_time(1)
            elif event.key == 'l':
                self._toggle_live_mode()
            elif event.key == 'r':
                self._toggle_roi_selection()
            elif event.key == 'e':
                self._export_current_data()
            elif event.key == 'z':
                self._reset_zoom()
            elif event.key == 'p':
                self._toggle_progress_indicator()
                
        self.fig.canvas.mpl_connect('key_press_event', on_key_press)
        
    def _setup_info_icon(self):
        """Add info icon with keyboard shortcuts tooltip"""
        self.info_icon = self.fig.text(0.02, 0.98, 'i', ha='center', va='center', fontsize=12, 
                                      color='white', weight='bold', family='monospace',
                                      bbox=dict(boxstyle="circle,pad=0.3", facecolor='blue', alpha=0.7))
        
        shortcuts_text = """Keyboard Shortcuts:

                            ← / →   Navigate through time data
                            L       Toggle live mode
                            R       Toggle ROI selection
                            Z       Reset zoom
                            E       Export current data
                            P       Toggle progress indicator"""
        
        self.tooltip_text = self.fig.text(0.02, 0.85, shortcuts_text, ha='left', va='top', fontsize=9,
                                         bbox=dict(facecolor='lightyellow', alpha=0.95, edgecolor='gray', pad=10))
        self.tooltip_text.set_visible(False)
        
        def on_hover(event):
            if event is None:
                return
            
            if hasattr(event, 'x') and hasattr(event, 'y'):
                fig_x = event.x / self.fig.bbox.width if self.fig.bbox.width > 0 else 0
                fig_y = event.y / self.fig.bbox.height if self.fig.bbox.height > 0 else 0
                
                if (0.005 <= fig_x <= 0.05 and 0.96 <= fig_y <= 1.0):
                    if not self.tooltip_text.get_visible():
                        self.tooltip_text.set_visible(True)
                        self.fig.canvas.draw_idle()
                else:
                    if self.tooltip_text.get_visible():
                        self.tooltip_text.set_visible(False)
                        self.fig.canvas.draw_idle()
        
        self.fig.canvas.mpl_connect('motion_notify_event', on_hover)
        
    def _navigate_time(self, direction):
        """Navigate through time data"""
        if not self.stored_images:
            return
            
        current_val = self.time_nav.time_slider.val
        new_val = max(0, min(len(self.stored_images) - 1, current_val + direction))
        self.time_nav.time_slider.set_val(new_val)
        
    def _toggle_live_mode(self):
        """Toggle live mode on/off"""
        was_live = self.is_live_mode
        self.is_live_mode = not self.is_live_mode
        self.time_nav.set_live_mode(self.is_live_mode)
        
        if self.is_live_mode and not was_live and self.stored_images:
            self.time_nav.time_slider.set_val(len(self.stored_images) - 1)
            
    def _reset_zoom(self):
        """Reset zoom to show full image"""
        self.ax_img.set_xlim(0, IMAGE_SIZE-1)
        self.ax_img.set_ylim(0, IMAGE_SIZE-1)
        self.colorbar.mappable.set_clim(0.0, 1.0)
        self.fig.canvas.draw_idle()
        
    def _toggle_roi_selection(self):
        """Toggle ROI selection mode"""
        if hasattr(self.controls, 'roi_button'):
            self.controls._on_roi_button_clicked(None)
            self.fig.canvas.draw_idle()
        
    def _toggle_progress_indicator(self):
        """Toggle progress indicator visibility"""
        self.progress_text.set_visible(not self.progress_text.get_visible())
        self.fig.canvas.draw_idle()
        
    def _export_current_data(self):
        """Export current image and analysis data"""
        if self.img_data is None:
            return
            
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        np.savetxt(f'image_data_{timestamp}.txt', self.img_data, fmt='%.6f')
        
    def _export_image(self, filename=None):
        """Export current image as PNG"""
        if filename is None:
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            filename = f'detector_image_{timestamp}.png'
        self.fig.savefig(filename, dpi=300, bbox_inches='tight')
        
    def _export_data(self, filename=None):
        """Export current data as CSV"""
        if filename is None:
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            filename = f'detector_data_{timestamp}.csv'
        save_image_data(self.img_data, time.time(), filename)
        
    def _export_plot(self, filename=None):
        """Export current plot as PDF"""
        if filename is None:
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            filename = f'detector_plot_{timestamp}.pdf'
        self.fig.savefig(filename, format='pdf', bbox_inches='tight')

    def _on_slice_changed(self, slice_index):
        """Handle slice index change"""
        self.controls.slice_index = slice_index
        self._update_slice_fit()

    def _on_mode_changed(self, mode):
        """Handle slice mode change"""
        self.controls.slice_mode = mode
        self._update_slice_fit()

    def _on_fit_changed(self, fit_mode):
        """Handle fit mode change"""
        self.controls.fit_mode = fit_mode
        self._update_slice_fit()
        
    def _on_checkbox_changed(self, label, show_markers, show_fit):
        """Handle checkbox changes"""
        self.controls.show_markers = show_markers
        self.controls.show_fit = show_fit
        self._update_slice_fit()
        
    def _on_time_changed(self, index):
        """Handle time navigation changes"""
        if not self.stored_images:
            return
            
        max_index = len(self.stored_images) - 1
        
        if index >= max_index:
            self.is_live_mode = True
            self.current_index = -1
            if self.stored_images:
                self._display_image_at_index(max_index)
        else:
            self.is_live_mode = False
            self.current_index = index
            self._display_image_at_index(index)
        
        self.time_nav.set_live_mode(self.is_live_mode)
    
    def _on_live_clicked(self):
        """Handle live button click"""
        self.is_live_mode = not self.is_live_mode
        
        if self.is_live_mode:
            self.current_index = -1
            if self.stored_images:
                max_index = len(self.stored_images) - 1
                self.time_nav.time_slider.set_val(max_index)
                self._display_image_at_index(max_index)
        
        self.time_nav.set_live_mode(self.is_live_mode)
        
    def _on_roi_toggled(self, roi_active):
        """Handle ROI toggle"""
        self.image_display.enable_roi_selection(roi_active)
        if not roi_active:
            self._roi_stats_backup = self.roi_stats
            self.roi_stats = None
            self._update_roi_statistics()
        else:
            if hasattr(self, '_roi_stats_backup') and self._roi_stats_backup is not None:
                self.roi_stats = self._roi_stats_backup
                self._update_roi_statistics()
            else:
                self._create_default_roi()
    
    def _create_default_roi(self):
        """Create a default 50x50 centered ROI"""
        center_x = IMAGE_SIZE // 2
        center_y = IMAGE_SIZE // 2
        
        roi_size = 50
        half_size = roi_size // 2
        
        x1 = max(0, center_x - half_size)
        y1 = max(0, center_y - half_size)
        x2 = min(IMAGE_SIZE - 1, center_x + half_size)
        y2 = min(IMAGE_SIZE - 1, center_y + half_size)
        
        self.image_display.set_roi_rectangle(x1, y1, x2, y2)
        
        self._on_roi_selected(x1, y1, x2, y2)
    
    def _on_roi_selected(self, x1, y1, x2, y2):
        """Handle ROI selection"""
        x1, x2 = max(0, min(x1, x2)), min(IMAGE_SIZE-1, max(x1, x2))
        y1, y2 = max(0, min(y1, y2)), min(IMAGE_SIZE-1, max(y1, y2))
        
        if self.img_data is not None:
            self.roi_data = self.img_data[y1:y2+1, x1:x2+1]
            
            self.roi_stats = {
                'bounds': (x1, y1, x2, y2),
                'mean': np.mean(self.roi_data),
                'std': np.std(self.roi_data),
                'min': np.min(self.roi_data),
                'max': np.max(self.roi_data),
                'sum': np.sum(self.roi_data)
            }
            
            self._update_roi_statistics()
            
    def _update_roi_statistics(self):
        """Update statistics display to show ROI information"""
        if self.roi_stats is not None:
            roi_text = f"ROI ({self.roi_stats['bounds'][0]},{self.roi_stats['bounds'][1]}) to ({self.roi_stats['bounds'][2]},{self.roi_stats['bounds'][3]}):\n"
            roi_text += f"Mean: {self.roi_stats['mean']:.3f}\n"
            roi_text += f"Std: {self.roi_stats['std']:.3f}\n"
            roi_text += f"Min: {self.roi_stats['min']:.3f}\n"
            roi_text += f"Max: {self.roi_stats['max']:.3f}\n"
            roi_text += f"Sum: {self.roi_stats['sum']:.3f}"
            
            if self.separate_controls and self.stats_display:
                current_stats = self.stats_display.stats_text.get_text()
                combined_stats = current_stats + "\n\n" + roi_text
                self.stats_display.stats_text.set_text(combined_stats)
            else:
                if not hasattr(self.controls, 'roi_text'):
                    roi_text_y = -0.15
                    
                    self.controls.roi_text = self.controls.ax.text(0.07, roi_text_y, '', 
                                                                 transform=self.controls.ax.transAxes,
                                                                 verticalalignment='bottom', fontsize=9,
                                                                 bbox=dict(facecolor='none', alpha=0))
                
                self.controls.roi_text.set_text(roi_text)
                self.controls.roi_text.set_visible(True)
        else:
            if hasattr(self.controls, 'roi_text'):
                self.controls.roi_text.set_visible(False)
    
    def _update_live_roi_stats(self):
        """Update ROI statistics with current image data if ROI is active"""
        if self.roi_stats is not None and self.img_data is not None:
            x1, y1, x2, y2 = self.roi_stats['bounds']
            
            if (0 <= x1 < self.img_data.shape[1] and 0 <= x2 < self.img_data.shape[1] and
                0 <= y1 < self.img_data.shape[0] and 0 <= y2 < self.img_data.shape[0]):
                
                self.roi_data = self.img_data[y1:y2+1, x1:x2+1]
                
                self.roi_stats.update({
                    'mean': np.mean(self.roi_data),
                    'std': np.std(self.roi_data),
                    'min': np.min(self.roi_data),
                    'max': np.max(self.roi_data),
                    'sum': np.sum(self.roi_data)
                })
                
                self._update_roi_statistics()
                
                self._roi_stats_backup = self.roi_stats.copy()
            
    def _update_progress_indicator(self):
        """Update progress indicator during scanning"""
        if self.scan_total > 0:
            progress_pct = (self.scan_progress / self.scan_total) * 100
            self.progress_text.set_text(f'Scan Progress: {self.scan_progress}/{self.scan_total} ({progress_pct:.1f}%)')
            
            if progress_pct < 50:
                self.progress_text.set_bbox(dict(facecolor='orange', alpha=0.7))
            elif progress_pct < 90:
                self.progress_text.set_bbox(dict(facecolor='yellow', alpha=0.7))
            else:
                self.progress_text.set_bbox(dict(facecolor='lightgreen', alpha=0.7))
        
    def _schedule_update(self):
        """Schedule a batched update with FPS limiting"""
        current_time = time.time()
        time_since_last_update = current_time - self.last_update_time
        
        if not self.update_pending and time_since_last_update >= MIN_UPDATE_INTERVAL:
            self.update_pending = True
            self.fig.canvas.draw_idle()
            self.last_update_time = current_time
            self.fig.canvas.mpl_connect('draw_event', lambda evt: setattr(self, 'update_pending', False))
        

    def _update_slice_fit(self):
        try:
            if self.img_data.shape != DETECTOR_SHAPE:
                return
            
            if self.controls.slice_mode == 'row':
                data = self.img_data[self.controls.slice_index, :]
            else:
                data = self.img_data[:, self.controls.slice_index]

            data = np.asarray(data, dtype=np.float64).flatten()
            
            if len(data) == 0:
                raise ValueError("Slice data is empty")
            
            if not np.isfinite(data).all():
                data = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)
            
            x = np.arange(len(data), dtype=np.float64)
            

            if np.std(data) < 1e-10:
                raise ValueError("Data has insufficient variation for fitting")

            if self.controls.fit_mode == 'gaussian':
                model = GaussianModel()
            elif self.controls.fit_mode == 'lorentzian':
                model = LorentzianModel()
            else:
                model = PseudoVoigtModel()

            params = model.guess(data, x=x)
            
            result = model.fit(data, params, x=x)

            fit_result = FitResult(
                best_fit=result.best_fit,
                best_values=result.best_values,
                r_squared=1 - result.residual.var() / np.var(data),
                model_name=result.model.name
            )
            
            self.fit_display.update_fit(x, data, fit_result, self.controls.show_fit)

            com = np.average(x, weights=data)
            peak = x[np.argmax(data)]
            
            self.image_display.update_slice_markers(
                self.controls.slice_mode, 
                self.controls.slice_index, 
                com, peak, 
                self.controls.show_markers
            )
            
            if self.separate_controls and self.stats_display:
                self.stats_display.update_statistics(self.img_data)
            else:
                self.controls.update_statistics(self.img_data)
            
            self._update_live_roi_stats()

        except Exception as e:
            self.fit_display.update_fit(x, data, None, self.controls.show_fit)
            self.fit_display.fit_text.set_text(f'Fit failed: {str(e)}')

        self._schedule_update()
    
    
    def _display_image_at_index(self, index):
        """Display image data at specific index"""
        if 0 <= index < len(self.stored_images):
            img = self.stored_images[index]
            timestamp = self.stored_timestamps[index]
            
            self.img_data = img
            self.image_display.update_image(img)
            self.colorbar.mappable.set_clim(0.0, 1.0)
            
            timestamp_str = time.strftime('%H:%M:%S', time.localtime(timestamp))
            self.timestamp_text.set_text(f't={timestamp_str}')
            
            self._update_slice_fit()
    
    def _update_time_slider_range(self):
        """Update time slider range when new data arrives"""
        if self.stored_images:
            max_index = len(self.stored_images) - 1
            self.time_nav.update_slider_range(max_index)
    

    def __call__(self, name, doc):
        """Bluesky callback for receiving detector data"""
        if name != 'event':
            return
        if 'eiger_image_image' in doc['data']:
            img = doc['data']['eiger_image_image']
            img = np.asarray(img, dtype=np.float32)
            
            if img.ndim == 1:
                img = img.reshape(DETECTOR_SHAPE)
            elif img.ndim > 2:
                img = img[:, :, 0] if img.shape[2] == 1 else img.reshape(DETECTOR_SHAPE)
            
            self.image_timestamp = time.time()
            self.stored_timestamps.append(self.image_timestamp)
            self.stored_images.append(img.copy())
            
            save_image_data(img, self.image_timestamp)
            
            self._update_progress_indicator()
            
            self._update_time_slider_range()
            
  
            if len(self.stored_images) > MAX_STORED_IMAGES:
                self.stored_images.pop(0)
                self.stored_timestamps.pop(0)
            
            if self.is_live_mode:
                self.img_data = img
                self.image_display.update_image(img)
                self.colorbar.mappable.set_clim(0.0, 1.0)
                timestamp_str = time.strftime('%H:%M:%S', time.localtime(self.image_timestamp))
                self.timestamp_text.set_text(f't={timestamp_str}')
                self._update_slice_fit()

RE = RunEngine({})

live_panel = LiveImagePanel(colormap='inferno', separate_controls=SEPARATE_CONTROLS) 

RE.subscribe(live_panel)

if DUMMY_DATA:
    print("Using Dummy data")
    def scan_with_detector():
        positions = np.linspace(-2, 2, 100)
        live_panel.scan_total = len(positions)
        live_panel.scan_progress = 0
        live_panel.progress_text.set_visible(True)
        
        for i, pos in enumerate(positions):
            live_panel.scan_progress = i + 1
            image.set_motor_position(pos)
            yield from scan([image], fake_motor, pos, pos, 1)
            time.sleep(0.1)
            
        live_panel.progress_text.set_visible(False)
    
    RE(scan_with_detector())
else:
    print("real detector")   
    RE(scan([image], fake_motor, 0, 1, 20))

plt.show(block=True)