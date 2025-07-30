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

    def stage(self):
        self.cam.stage_sigs["num_images"] = 1
        self.cam.stage_sigs["trigger_mode"] = 0
        self.cam.stage_sigs["FWNImagesPerFile"] = 1
  
        self.stage_sigs["array_callbacks"] = 1

        self.hdf5.stage_sigs["enable"] = 1
        self.hdf5.stage_sigs["file_write_mode"] = "Single"
        self.hdf5.stage_sigs["num_capture"] = 1
        self.hdf5.stage_sigs["auto_increment"] = 1
        self.hdf5.stage_sigs["auto_save"] = 1
        self.hdf5.stage_sigs["file_template"] = "%s%s_%6.6d.h5"
 
        self.read_attrs = ["hdf5"]

        self.configuration_attrs += ["cam.trigger_mode", "cam.num_images"]
    
eiger = MyEiger(prefix="BL172:eiger4M:", name="eiger", labels={'detectors', 'area_detectors'})
eiger.stage()
