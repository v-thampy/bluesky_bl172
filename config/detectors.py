from ophyd.areadetector.detectors import EigerDetector
from ophyd import EpicsMotor
from ophyd import Device, Component as Cpt, EpicsSignal
from ophyd.areadetector.cam import CamBase
from ophyd.areadetector.plugins import HDF5Plugin, ImagePlugin, StatsPlugin, ROIPlugin
from ophyd.areadetector.trigger_mixins import SingleTrigger
import warnings
import numpy as np

class MyEigerCam(CamBase):
    acquire = Cpt(EpicsSignal, 'Acquire')  # override default
    acquire_time = Cpt(EpicsSignal, 'AcquireTime')  # override default
    acquire_period = Cpt(EpicsSignal, 'AcquirePeriod')  # override default
    threshold_energy = Cpt(EpicsSignal, 'ThresholdEnergy')  # override default
    threshold_energy_RBV = Cpt(EpicsSignal, 'ThresholdEnergy_RBV')  # override default
    photon_energy = Cpt(EpicsSignal, 'PhotonEnergy')  # override default
    num_images = Cpt(EpicsSignal, 'NumImages')  # override default
    trigger_mode = Cpt(EpicsSignal, 'TriggerMode')  # override default
    trigger_exposure = Cpt(EpicsSignal, 'TriggerExposure')  # override default
    manual_trigger = Cpt(EpicsSignal, 'ManualTrigger')  # override default
#   trigger_v = Cpt(EpicsSignal, 'Trigger')  # override default
    num_triggers = Cpt(EpicsSignal, 'NumTriggers')  # override default
    num_queued_arrays = Cpt(EpicsSignal, 'NumQueuedArrays')  # override default
    wait_for_plugins = Cpt(EpicsSignal, 'WaitForPlugins')  # override default
    acquire_busy = Cpt(EpicsSignal, 'AcquireBusy')  # override default
    status_message = Cpt(EpicsSignal, 'StatusMessage_RBV')  # override default
    detector_state = Cpt(EpicsSignal, 'DetectorState_RBV')  # override default
    bit_depth_image = Cpt(EpicsSignal, 'BitDepthImage_RBV')  # override default
    dead_time = Cpt(EpicsSignal, 'DeadTime_RBV')  # override default
    count_cutoff = Cpt(EpicsSignal, 'CountCutoff_RBV')  # override default
    num_images_counter = Cpt(EpicsSignal, 'NumImagesCounter_RBV')  # override default
    array_counter = Cpt(EpicsSignal, 'ArrayCounter')  # override default
    array_rate = Cpt(EpicsSignal, 'ArrayRate_RBV')  # override default
    driver_version = Cpt(EpicsSignal, 'DriverVersion_RBV')  # override default
    roi_mode = Cpt(EpicsSignal, 'ROIMode')  # override default

    FWNamePattern = Cpt(EpicsSignal, "FWNamePattern")
    FWNImagesPerFile = Cpt(EpicsSignal, "FWNImagesPerFile")

    def variable_list(self, skip_lazy=True):
        print("Valid settings and current values:")
        valid_attrs = []

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=UserWarning)

            for attr in dir(self):
                try:
                    signal = getattr(self, attr)
                except Exception as outer_e:
                    if not skip_lazy:
                        print(f" - {attr}: <Error initializing: {outer_e}>")
                    continue

                if isinstance(signal, EpicsSignal):
                    try:
                        value = signal.get(timeout=1.0)
                    except Exception as e:
                        value = f"<Error reading: {e}>"

                    # Decode ASCII arrays to strings if possible
                    if isinstance(value, (list, np.ndarray)):
                        try:
                            value = ''.join(chr(int(v)) for v in value if 0 < int(v) < 128)
                        except Exception:
                            pass

                    print(f" - {attr}: {value}")
                    valid_attrs.append(attr)

        return valid_attrs

    def update_variables(self, **kwargs):
    ###    Update EPICS signal values for valid EpicsSignal attributes.
        for key, value in kwargs.items():
            try:
                signal = getattr(self, key)
                if isinstance(signal, EpicsSignal):
                    try:
                        signal.put(value)
                        print(f"Set {key} = {value}")
                    except Exception as e:
                        print(f"Failed to set {key}: {e}")
                else:
                    print(f"'{key}' is not an EpicsSignal; cannot set value.")
            except AttributeError:
                print(f"'{key}' is not a valid attribute of the camera.")
            except Exception as outer_e:
                print(f"Error accessing '{key}': {outer_e}")


class Eiger_SSRL(SingleTrigger, EigerDetector):
    cam = Cpt(MyEigerCam, 'cam1:')
    hdf1 = Cpt(HDF5Plugin, 'HDF1:')
    image = Cpt(ImagePlugin, "image1:")
    stats1 = Cpt(StatsPlugin, "Stats1:")
    stats2 = Cpt(StatsPlugin, "Stats2:")
    stats3 = Cpt(StatsPlugin, "Stats3:")
    stats4 = Cpt(StatsPlugin, "Stats4:")
    roi1 = Cpt(ROIPlugin, "ROI1:")
    roi2 = Cpt(ROIPlugin, "ROI2:")
    roi3 = Cpt(ROIPlugin, "ROI3:")
    roi4 = Cpt(ROIPlugin, "ROI4:")


def MyEiger(prefix="BL172:eiger4M:", *, name="eiger") -> Eiger_SSRL :
    det = Eiger_SSRL(prefix, name=name)

    det.cam.stage_sigs["num_images"] = 1
    det.cam.stage_sigs["trigger_mode"] = 0
    det.cam.stage_sigs["FWNImagesPerFile"] = 1
  
    det.cam.stage_sigs["array_callbacks"] = 1

    det.hdf1.stage_sigs["enable"] = 1
    det.hdf1.stage_sigs["file_write_mode"] = "Single"
    det.hdf1.stage_sigs["num_capture"] = 1
    det.hdf1.stage_sigs["auto_increment"] = 1
    det.hdf1.stage_sigs["auto_save"] = 1
    det.hdf1.stage_sigs["file_template"] = "%s%s_%6.6d.h5"
 
    det.read_attrs = ["hdf1"]
    det.image.read_attrs = ['shaped_image', 'array_data', 'ndimensions', 'dimensions', 'width', 'height', 'depth']
    # det.hdf1.read_attrs = []

    det.configuration_attrs += ["cam.trigger_mode", "cam.num_images"]
    return det


def init_BL172_detectors(eiger_prefix='BL172:eiger4M:'):
    # Instantiate and configure Eiger detector
    eiger = MyEiger(prefix=eiger_prefix, name='eiger')
    eiger.wait_for_connection(timeout=1)

    print(f"Eiger detector initialized successfully.")
    return eiger

eiger = init_BL172_detectors()

#eiger = MyEiger(prefix="BL172:eiger4M:", name="eiger", labels={'detectors', 'area_detectors'})
#eiger.stage()

