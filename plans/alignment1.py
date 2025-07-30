# plans/alignment.py

from bluesky.plans import scan, rel_scan
from bluesky.plan_stubs import mv
from bluesky.preprocessors import run_decorator
from config.runengine import setup_runengine_with_databroker, LiveStatsPlot
from utils.logger import append_metadata_to_csv
from time import strftime
import numpy as np
import matplotlib.pyplot as plt
from lmfit.models import GaussianModel, PseudoVoigtModel
from ophyd import Device
from bluesky.utils import short_uid


def scan_monitor_vs_motor(
    motor: Device,
    start: float,
    stop: float,
    steps: int,
    monitor: Device,
    count_time: float = 0.1,
    relative: bool = False,
    fit: bool = True,
    move_to: str = None,  # "peak", "com", or None
    model_type: str = "gaussian",
    label: str = None,
):
    """
    Scan monitor vs motor with optional fitting and movement.
    
    Parameters:
        motor : Device
            Motor to scan
        start, stop : float
            Scan range
        steps : int
            Number of steps
        monitor : Device
            Monitor/detector to read
        count_time : float
            Integration time per point
        relative : bool
            If True, use relative scan
        fit : bool
            If True, fit the data
        move_to : str or None
            Move to "peak", "com", or None
        model_type : str
            "gaussian" or "pvoigt"
        label : str
            Plot label (auto-generated if None)
    
    Returns:
        dict: Results including fit parameters and plot
    """
    
    # Setup
    RE, cat = setup_runengine_with_databroker()
    x_field, y_field = motor.name, monitor.name
    label = label or f"{y_field} vs {x_field}"
    
    # Configure monitor timing
    _configure_monitor_timing(monitor, count_time)
    
    # Setup live plotting
    live_plot = LiveStatsPlot(y_field=y_field, x_field=x_field, label=label)
    RE.subscribe(live_plot)
    
    # Prepare metadata
    timestamp = strftime("%Y%m%d_%H%M%S")
    metadata = {
        "plan_name": "alignment_scan",
        "monitor": y_field,
        "motor": x_field,
        "count_time": count_time,
        "relative": relative,
        "model_type": model_type,
        "timestamp": timestamp,
        "uid": short_uid(),
    }
    
    # Execute scan
    plan_func = rel_scan if relative else scan
    
    @run_decorator(md=metadata)
    def _alignment_scan():
        return plan_func([monitor], motor, start, stop, steps)
    
    RE(_alignment_scan())
    
    # Analyze results
    results = _analyze_alignment_data(
        live_plot, motor, fit, model_type, move_to, RE
    )
    
    # Update metadata with results
    metadata.update(results.get("fit_params", {}))
    
    # Save results
    _save_alignment_results(cat, x_field, timestamp, metadata)
    
    # Print summary
    _print_alignment_summary(x_field, results)
    
    return {
        "live_plot": live_plot,
        "fit_result": results.get("fit_result"),
        "metadata": metadata,
        "peak_position": results.get("peak_position"),
        "com_position": results.get("com_position")
    }


def _configure_monitor_timing(monitor, count_time):
    """Configure monitor integration time."""
    timing_fields = ['count_time', 'integration_time', 'preset_time', 'dwell_time']
    
    for field in timing_fields:
        if hasattr(monitor, field):
            try:
                getattr(monitor, field).put(count_time)
                print(f"✅ Set {field} = {count_time}s on {monitor.name}")
                return
            except Exception as e:
                print(f"⚠️ Failed to set {field} on {monitor.name}: {e}")
    
    print(f"⚠️ No timing field found on {monitor.name}")


def _analyze_alignment_data(live_plot, motor, fit, model_type, move_to, RE):
    """Analyze the alignment scan data."""
    results = {}
    
    if not fit or len(live_plot.xs) < 5:
        return results
    
    xs = np.array(live_plot.xs)
    ys = np.array(live_plot.ys)
    
    try:
        # Perform fit
        model = GaussianModel() if model_type == "gaussian" else PseudoVoigtModel()
        params = model.guess(ys, x=xs)
        fit_result = model.fit(ys, params, x=xs)
        
        # Plot fit
        fit_x = np.linspace(xs.min(), xs.max(), 300)
        fit_y = fit_result.eval(x=fit_x)
        live_plot.ax.plot(fit_x, fit_y, '--', color='red', label=f"{model_type} fit")
        live_plot.ax.legend()
        plt.draw()
        
        # Extract fit parameters
        peak_pos = fit_result.params["center"].value
        peak_amp = fit_result.params["amplitude"].value
        fwhm = fit_result.params.get("fwhm")
        fwhm_val = fwhm.value if fwhm else np.nan
        
        # Calculate center of mass
        com_pos = np.sum(xs * ys) / np.sum(ys)
        
        results.update({
            "fit_result": fit_result,
            "peak_position": peak_pos,
            "com_position": com_pos,
            "fit_params": {
                "fit_center": peak_pos,
                "fit_amplitude": peak_amp,
                "fit_fwhm": fwhm_val,
                "fit_com": com_pos,
                "fit_r_squared": 1 - fit_result.residual.var() / np.var(ys)
            }
        })
        
        # Optional movement
        if move_to == "peak":
            print(f"🔧 Moving {motor.name} to peak: {peak_pos:.4f}")
            RE(mv(motor, peak_pos))
        elif move_to == "com":
            print(f"🔧 Moving {motor.name} to COM: {com_pos:.4f}")
            RE(mv(motor, com_pos))
        
    except Exception as e:
        print(f"⚠️ Fitting failed: {e}")
        results["fit_error"] = str(e)
    
    return results


def _save_alignment_results(cat, x_field, timestamp, metadata):
    """Save alignment results to file and CSV log."""
    try:
        if len(cat) > 0:
            latest = cat[-1]
            h5name = f"align_{x_field}_{timestamp}.h5"
            latest.export(h5name, fmt="hdf5")
            print(f"📁 Exported alignment data to {h5name}")
    except Exception as e:
        print(f"⚠️ Could not export HDF5: {e}")
    
    # Always save metadata to CSV
    append_metadata_to_csv("alignment_log.csv", metadata)


def _print_alignment_summary(x_field, results):
    """Print a summary of alignment results."""
    if "fit_params" in results:
        params = results["fit_params"]
        print(f"\n📊 Alignment summary for {x_field}:")
        print(f"  Peak:     {params['fit_center']:.4f}")
        print(f"  COM:      {params['fit_com']:.4f}")
        print(f"  FWHM:     {params['fit_fwhm']:.4f}")
        print(f"  R²:       {params['fit_r_squared']:.3f}")
    else:
        print(f"\n📊 Alignment scan for {x_field} completed (no fit)")


# Convenience functions for common alignment tasks
def align_motor_to_peak(motor, monitor, scan_range=2.0, steps=21, **kwargs):
    """Quick alignment to peak with sensible defaults."""
    center = motor.position
    start = center - scan_range/2
    stop = center + scan_range/2
    
    return scan_monitor_vs_motor(
        motor=motor,
        start=start,
        stop=stop,
        steps=steps,
        monitor=monitor,
        move_to="peak",
        **kwargs
    )


def fine_align_motor(motor, monitor, scan_range=0.5, steps=21, **kwargs):
    """Fine alignment with small range."""
    return align_motor_to_peak(
        motor=motor,
        monitor=monitor,
        scan_range=scan_range,
        steps=steps,
        count_time=0.2,  # Longer integration for precision
        **kwargs
    )