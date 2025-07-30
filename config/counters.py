# integrated_detector.py
import time
import threading
from ophyd import Device, Component as Cpt, Signal, EpicsSignalRO, DeviceStatus

# integrated_detector.py
import time
import threading
from ophyd import Device, Component as Cpt, Signal, EpicsSignalRO, DeviceStatus

class IntegratedAnalog(Device):
    """
    Integrate an analog PV for 'integration_time' seconds
    and expose the sum as the detector's datum.
    """
    val = Cpt(EpicsSignalRO, '')  # Analog input PV

    integration_time = Cpt(Signal, value=1.0, kind='config')   # Integration window [s]
    sample_dt        = Cpt(Signal, value=0.01, kind='config')  # Sample interval [s]
    integrated       = Cpt(Signal, value=0.0)   # Integrated result

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.integrated.name = self.name 
        
    def trigger(self):
        status = DeviceStatus(self)

        def _acq():
            try:
                t_total = float(self.integration_time.get())
                dt = float(self.sample_dt.get())
            except Exception as e:
                print(f"[{self.name}] Error reading integration settings: {e}")
                status._finished(success=False)
                return

            start = time.time()
            acc = 0.0
            n_samples = 0

            try:
                while time.time() - start < t_total:
                    try:
                        value = float(self.val.get())
                    except Exception as e:
                        print(f"[{self.name}] Failed to read PV: {e}")
                        value = 0.0  # Optionally skip or abort here
                    acc += value * dt
                    n_samples += 1
                    time.sleep(dt)
                self.integrated.put(acc)
                # print(f"[{self.name}] Integrated over {n_samples} samples, result: {acc:.6f}")
                status._finished(success=True)
            except Exception as e:
                print(f"[{self.name}] Unexpected error during integration: {e}")
                status._finished(success=False)

        threading.Thread(target=_acq, daemon=True).start()
        return status

    def read(self):
        try:
            return {
                self.name: {
                    'value': self.integrated.get(),
                    'timestamp': time.time()
                }
            }
        except Exception as e:
            print(f"[{self.name}] Error reading integrated value: {e}")
            return {
                self.name: {
                    'value': float('nan'),
                    'timestamp': time.time()
                }
            }

    def describe(self):
        return {
            self.name: {
                'dtype': 'number',
                'shape': [],
                'units': 'V·s',
                'source': 'calculated'
            }
        }


def init_integrated_counters(integration_time=1.0):
    i0 = IntegratedAnalog('BL17-2:RIO1:GalilAi0_MON.VAL', name='i0')
    i1 = IntegratedAnalog('BL17-2:RIO1:GalilAi1_MON.VAL', name='i1')
    i2 = IntegratedAnalog('BL17-2:RIO1:GalilAi2_MON.VAL', name='i2')
    bs = IntegratedAnalog('BL17-2:RIO1:GalilAi3_MON.VAL', name='bs')

    for det in [i0, i1, i2, bs]:
        det.integration_time.put(integration_time)
        det.read_attrs = ['integrated']
        det.integrated.kind = 'hinted'

    return i0, i1, i2, bs


# beamline_integrated_counters.py
# from integrated_detector import IntegratedAnalog

i0, i1, i2, bs = init_integrated_counters(integration_time=1.0)
counters = [i0, i1, i2, bs]


def set_count_time(integration_time):
    """
    Set the integration time for all counters.
    """
    for det in counters:
        det.integration_time.put(integration_time)
    
    print(f"Count time: {integration_time} seconds")


def cnt(time=1.0, num=1, delay=None):
    """
    Count global beamline counters with integrated readout using BestEffortCallback.

    Parameters
    ----------
    time : float
        Integration time in seconds (applied to all counters).
    num : int
        Number of repetitions.
    delay : float or None
        Delay between repetitions (seconds).
    
    Returns
    -------
    RunEngine status object
    """
    try:
        global counters
    except NameError as e:
        raise RuntimeError("One or more of the global counters (i0, i1, i2, bs) are not defined.") from e

    set_count_time(time)
    return RE(count(counters, num=num, delay=delay))
