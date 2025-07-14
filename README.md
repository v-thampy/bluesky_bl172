# bluesky_bl172

# Bluesky GIXRD Automation Toolkit

This project provides a modular, extensible Bluesky-based framework for automating grazing incidence X-ray diffraction (GIXRD) experiments — including alignment, burst-mode flash measurements, and post-processing.

---

## 🔧 Features

- Modular configuration of detectors, motors, and counters
- Alignment scans using beam monitors or Eiger ROI stats
- Real-time plotting with peak fitting (COM, FWHM, peak position)
- Burst-mode image acquisition triggered by external devices (e.g. delay generator)
- Post-burst analysis with ROI time series plotting and peak detection
- Full summary logging to CSV
- Ready-to-use `FlashGIXRDSequence` automation class

---

## 📁 Project Structure

config/       # Detector, motor, counter, and RunEngine configuration
plans/        # Scans, alignment, and automation plans
utils/        # Logging, plotting, ROI GUI tools
docs/         # Usage examples and setup instructions
notebooks/    # Jupyter workflow templates

---

## ▶️ Quick Start

```bash
# Clone the repo
git clone https://github.com/yourname/bluesky_bl172.git
cd bluesky_bl172

# Set up environment
conda create -n bluesky_env python=3.11 -c conda-forge
conda activate bluesky_env
pip install -r requirements.txt
```

Start IPython:

from plans.sequence import FlashGIXRDSequence
seq = FlashGIXRDSequence(nframes=500, frame_time=0.002)
seq.run()


📊 Example Outputs
	•	gixrd_flash_summary.csv: alignment positions, scan metadata
	•	roi_stats_burst_YYYYMMDD.csv: burst-mode ROI signal over time
	•	PNG plots of flash-induced transients

⸻

📚 Documentation

See docs/USAGE.md for examples of:
	•	Manual alignment scans
	•	Running burst and post-burst scans
	•	Plotting and interpreting ROI data

⸻

🧠 Requirements
	•	Python 3.8–3.11
	•	Bluesky
	•	Ophyd, Databroker, Matplotlib, SciPy, Pandas

⸻

🧪 Tested On
	•	Simulated EPICS motors and detectors
	•	NSLS-II–style Eiger setup with areaDetector

⸻

📬 License

MIT License. Open to contributions and adaptation for other beamlines.
