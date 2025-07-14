from ophyd.areadetector.detectors import EigerDetector
from ophyd.areadetector.plugins import HDF5Plugin, ImagePlugin, StatsPlugin, ROIPlugin
from ophyd import Component as Cpt

class MyEiger(EigerDetector):
    hdf5 = Cpt(HDF5Plugin, "HDF1:")
    image = Cpt(ImagePlugin, "IMAGE1:")
    stats1 = Cpt(StatsPlugin, "Stats1:")
    stats2 = Cpt(StatsPlugin, "Stats2:")
    roi1 = Cpt(ROIPlugin, "ROI1:")
    roi2 = Cpt(ROIPlugin, "ROI2:")

eiger = MyEiger("EIGER:DET:", name="eiger4M")

def configure_eiger_for_burst(num_images=100, frame_time=0.001, file_path="/data/", base_filename="scan"):
    eiger.hdf5.warmup()
    eiger.hdf5.enable.put(1)
    eiger.hdf5.create_directory.put(-1)
    eiger.hdf5.file_write_mode.put(2)
    eiger.hdf5.auto_increment.put(1)
    eiger.hdf5.auto_save.put(1)
    eiger.hdf5.file_path.put(file_path)
    eiger.hdf5.write_path_template.put(file_path)
    eiger.hdf5.file_name.put(base_filename)
    eiger.hdf5.file_number.put(0)
    eiger.cam.acquire_time.put(frame_time)
    eiger.cam.acquire_period.put(frame_time + 0.0002)
    eiger.cam.num_images.put(num_images)
    eiger.cam.trigger_mode.put(1)
    eiger.cam.image_mode.put(1)
    eiger.stats1.enable.put(1)
    eiger.stats2.enable.put(1)
    return eiger