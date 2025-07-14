# plans/alignment.py

from bluesky.plans import scan, rel_scan
from bluesky.plan_stubs import mv, sleep
from bluesky.preprocessors import run_decorator
from bluesky import RunEngine
from config.runengine import setup_runengine_with_databroker, LiveStatsPlot
from utils.logger import append_metadata_to_csv
from time import strftime
from databroker import catalog
import numpy as np
import matplotlib.pyplot as plt
from lmfit.models import GaussianModel, PseudoVoigtModel
from ophyd import Device
from bluesky.utils import short_uid

cat = catalog['my_catalog']


@run_decorator()
def scan_monitor_vs_motor(
    motor: Device,
    start: float,
    stop: float,
    steps: int,
    *,
    monitor: Device,
    count_time: float = 0.1,
    relative: bool = False,
    fit: bool = True,
    move_to: str = "peak",  # "peak", "com", or None
    label: str = None,
    model_type: str = "gaussian",
):
    """Scan monitor vs motor with stats, fit, and optional move-to-peak/com"""
    RE, _ = setup_runengine_with_databroker()
    x_field, y_field = motor.name, monitor.name
    label = label or f"{y_field} vs {x_field}"

    # Set counting time
    if hasattr(monitor, "count_time"):
        monitor.count_time.put(count_time)
    elif hasattr(monitor, "integration_time"):
        monitor.integration_time.put(count_time)

    # Live plot
    stats_plot = LiveStatsPlot(y_field=y_field, x_field=x_field, label=label)
    RE.subscribe(stats_plot)

    # Metadata
    timestamp = strftime("%Y%m%d_%H%M%S")
    uid = short_uid()
    metadata = {
        "plan": "alignment_scan",
        "monitor": y_field,
        "motor": x_field,
        "count_time": count_time,
        "timestamp": timestamp,
        "uid": uid,
        "fit_model": model_type,
    }

    # Run scan
    plan = rel_scan if relative else scan
    RE(plan([monitor], motor, start, stop, steps), metadata)

    # Post-scan: analyze
    fit_result = None
    if fit:
        xs = np.array(stats_plot.xs)
        ys = np.array(stats_plot.ys)
        if len(xs) > 5:
            model = GaussianModel() if model_type == "gaussian" else PseudoVoigtModel()
            params = model.guess(ys, x=xs)
            fit_result = model.fit(ys, params, x=xs)

            fit_x = np.linspace(xs.min(), xs.max(), 300)
            fit_y = fit_result.eval(x=fit_x)
            stats_plot.ax.plot(fit_x, fit_y, '--', label=f"{model_type} fit")
            stats_plot.ax.legend()
            plt.draw()

            peak_pos = fit_result.params["center"].value
            peak_amp = fit_result.params["amplitude"].value
            fwhm = fit_result.params.get("fwhm", None)
            fwhm_val = fwhm.value if fwhm else np.nan
            com = np.sum(xs * ys) / np.sum(ys)

            metadata.update({
                "fit_center": peak_pos,
                "fit_amplitude": peak_amp,
                "fit_fwhm": fwhm_val,
                "fit_com": com,
            })

            print(f"\n📊 Fit summary for {x_field}:")
            print(f"  Peak: {peak_pos:.4f}")
            print(f"  COM:  {com:.4f}")
            print(f"  FWHM: {fwhm_val:.4f}")

            # Optional move
            if move_to == "peak":
                RE(mv(motor, peak_pos))
            elif move_to == "com":
                RE(mv(motor, com))

    # Save metadata and results
    latest = cat[-1]
    latest.export(f"align_{x_field}_{timestamp}.h5", fmt="hdf5")
    append_metadata_to_csv("alignment_log.csv", metadata)

    return stats_plot, fit_result