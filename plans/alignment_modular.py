# plans/alignment_modular.py

import numpy as np
from bluesky.plans import scan, rel_scan
from bluesky.plan_stubs import mv
from bluesky import RunEngine
from bluesky.utils import short_uid
from config.runengine import setup_runengine_with_databroker, LiveStatsPlot
from utils.logger import append_metadata_to_csv
from time import strftime
from databroker import catalog
from lmfit.models import GaussianModel, PseudoVoigtModel
import matplotlib.pyplot as plt

cat = catalog['my_catalog']

# -------------------------------
# 1. Configure monitor
# -------------------------------
def configure_monitor(monitor, count_time=0.1):
    if hasattr(monitor, "count_time"):
        monitor.count_time.put(count_time)
    elif hasattr(monitor, "integration_time"):
        monitor.integration_time.put(count_time)

def configure_monitor(monitor, count_time=0.1):
    """Try to set the count/integration/dwell time for a monitor, if supported."""
    fields = ['count_time', 'integration_time', 'preset_time', 'dwell_time', 'delay_time']
    for field in fields:
        if hasattr(monitor, field):
            try:
                getattr(monitor, field).put(count_time)
                print(f"✅ Set {field} = {count_time} on {monitor.name}")
                return
            except Exception as e:
                print(f"⚠️ Failed to set {field} on {monitor.name}: {e}")
    print(f"⚠️ No known timing field found on {monitor.name}")

# -------------------------------
# 2. Run scan (returns live plot)
# -------------------------------
def run_monitor_scan(
    motor, start, stop, steps, monitor, count_time=0.1,
    relative=False, label=None, metadata=None
):
    RE, _ = setup_runengine_with_databroker()
    x_field, y_field = motor.name, monitor.name
    label = label or f"{y_field} vs {x_field}"

    configure_monitor(monitor, count_time)

    # Live plot
    live_plot = LiveStatsPlot(y_field=y_field, x_field=x_field, label=label)
    RE.subscribe(live_plot)

    md = metadata or {}
    md.update({
        "plan": "alignment_scan",
        "monitor": y_field,
        "motor": x_field,
        "count_time": count_time,
        "timestamp": strftime("%Y%m%d_%H%M%S"),
        "uid": short_uid(),
    })

    plan = rel_scan if relative else scan
    RE(plan([monitor], motor, start, stop, steps), md)

    return live_plot


# -------------------------------
# 3. Fit data (Gaussian or PVoigt)
# -------------------------------
def fit_data(xs, ys, model_type="gaussian"):
    if model_type == "gaussian":
        model = GaussianModel()
    elif model_type == "pvoigt":
        model = PseudoVoigtModel()
    else:
        raise ValueError("Invalid model_type")

    params = model.guess(ys, x=xs)
    result = model.fit(ys, params, x=xs)
    return model, result


def plot_fit(xs, ys, model, result, ax=None, label="fit"):
    if ax is None:
        _, ax = plt.subplots()

    fit_x = np.linspace(xs.min(), xs.max(), 300)
    fit_y = result.eval(x=fit_x)
    ax.plot(fit_x, fit_y, "--", label=label)
    ax.legend()
    plt.draw()


# -------------------------------
# 4. Move motor to peak/COM/fit
# -------------------------------
def move_to_statistic(motor, xs, ys, mode="com", fit_result=None):
    RE, _ = setup_runengine_with_databroker()

    if mode == "peak":
        idx = np.argmax(ys)
        target = xs[idx]
    elif mode == "com":
        target = np.sum(xs * ys) / np.sum(ys)
    elif mode == "fit" and fit_result:
        target = fit_result.params["center"].value
    else:
        raise ValueError("Invalid move mode or missing fit_result")

    print(f"🔧 Moving {motor.name} to {target:.4f} ({mode})")
    RE(mv(motor, target))


# -------------------------------
# 5. Save metadata
# -------------------------------
def save_alignment_metadata(x_field, metadata):
    timestamp = metadata.get("timestamp", strftime("%Y%m%d_%H%M%S"))
    h5name = f"align_{x_field}_{timestamp}.h5"
    cat[-1].export(h5name, fmt="hdf5")
    append_metadata_to_csv("alignment_log.csv", metadata)