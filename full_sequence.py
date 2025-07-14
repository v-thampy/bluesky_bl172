# automated_gixrd_flash_sequence.py

from plans.alignment_modular import run_monitor_scan, fit_data, move_to_statistic, configure_monitor
from config.counters import i2
from config.detectors import eiger, configure_eiger_for_burst
from config.motors import sy, sx, th
from plans.wrapped_scan import run_scan_with_counters
from bluesky.plan_stubs import mv
from bluesky import RunEngine
from time import sleep, strftime
from utils.logger import append_metadata_to_csv
from databroker import catalog
import pandas as pd

RE, _ = setup_runengine_with_databroker()


def align_vertical_halfcut(count_time=0.1):
    print("🔧 Aligning vertically to half-cut beam...")
    configure_monitor(i2, count_time)
    RE(mv(sx, 0))  # center X to avoid clipping during Y scan
    run_monitor_scan(sy, -1.5, 1.5, 51, monitor=i2, count_time=count_time)
    sleep(0.2)


def find_sample_center(count_time=0.1):
    print("🔍 Scanning sx to find sample edges...")
    run = run_monitor_scan(sx, -7, 7, 141, monitor=i2, count_time=count_time)
    xs = run.xs
    ys = run.ys
    _, result = fit_data(xs, -np.array(ys), model_type="pvoigt")  # inverted plateau
    center = result.params["center"].value
    move_to_statistic(sx, xs, ys, mode="fit", fit_result=result)
    return center


def fine_align_flatten(count_time=0.1):
    print("🧪 Fine alignment: th and sy with COM...")
    run = run_monitor_scan(th, -0.5, 0.5, 51, monitor=i2, count_time=count_time, relative=True)
    move_to_statistic(th, run.xs, run.ys, mode="com")

    run = run_monitor_scan(sy, -0.3, 0.3, 41, monitor=i2, count_time=count_time, relative=True)
    move_to_statistic(sy, run.xs, run.ys, mode="com")


def trigger_flash_and_burst(nframes=500, frame_time=0.002):
    print("⚡ Triggering flash and burst imaging...")
    configure_eiger_for_burst(nframes, frame_time, base_filename="flashburst")
    RE(mv(th, 0.3))  # grazing incidence angle
    sleep(0.5)

    # 💡 Here you'd trigger the delay generator via EPICS or TTL PV
    print("⏱️ Sending trigger to delay generator...")
    # Example: RE(mv(delaygen.trigger, 1))

    # Start image burst
    RE(trigger_and_read([eiger]))

    # Save burst ROI stats
    run = catalog['my_catalog'][-1]
    df = run.primary.read()
    roi_cols = [col for col in df.data_vars if "stats1" in col]
    roi_data = {col: df[col].values for col in roi_cols}
    roi_data["frame"] = list(range(len(df["time"].values)))
    roi_df = pd.DataFrame(roi_data)
    csv_name = f"roi_stats_burst_{strftime('%Y%m%d_%H%M%S')}.csv"
    roi_df.to_csv(csv_name, index=False)
    print(f"🧾 Saved ROI stats table to {csv_name}")

    # Return info for summary
    return {
        "nframes": nframes,
        "frame_time": frame_time,
        "roi_stats_file": csv_name
    }


def post_flash_scan(step_size=0.2):
    print("📡 Scanning sample after flash to collect diffraction images...")
    n_steps = int(10 / step_size) + 1
    start = -5
    stop = 5
    RE(mv(th, 0.3))  # ensure correct angle
    run_scan_with_counters(
        detectors=[eiger],
        motor=sx,
        start=start,
        stop=stop,
        steps=n_steps,
        live_signals=[i2.name, eiger.stats1.mean.name],
        metadata={
            "scan_type": "post_flash_gixrd",
            "timestamp": strftime("%Y%m%d_%H%M%S"),
        }
    )


def run_gixrd_flash_sequence():
    print("🚀 Starting full GIXRD + flash automation sequence...")
    align_vertical_halfcut()
    find_sample_center()
    fine_align_flatten()
    trigger_flash_and_burst()
    post_flash_scan()
    print("✅ Sequence complete.")
    
    # Save final summary
    summary = {
        "timestamp": strftime("%Y-%m-%d %H:%M:%S"),
        "final_sy": sy.position,
        "final_sx": sx.position,
        "final_th": th.position,
        **burst_info
    }
    append_metadata_to_csv("gixrd_flash_summary.csv", summary)
    print("📝 Summary log saved.")


if __name__ == "__main__":
    run_gixrd_flash_sequence()