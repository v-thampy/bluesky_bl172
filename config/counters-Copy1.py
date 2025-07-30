from ophyd import EpicsSignalRO, EpicsSignal
from ophyd import Device
from ophyd import Component as Cpt

#i0 = EpicsSignalRO("I0:PV", name="i0")
#i1 = EpicsSignalRO("I1:PV", name="i1")
#monitor = EpicsSignalRO("MON:PV", name="monitor")
#temp = EpicsSignalRO("TEMP:PV", name="temperature")

#counters = [i0, i1, monitor, temp]

class BeamlineCounters(Device):
    """
    Beamline analog input device including:

    - i0, i1, i2: from analog input PVs (e.g., ion chambers or diodes)
    - bs: photodiode signal embedded in the beamstop

    All signals are read-only.
    """
    i0 = Cpt(EpicsSignalRO, 'RIO1:GalilAi0_MON.VAL', name='i0')
    i1 = Cpt(EpicsSignalRO, 'RIO1:GalilAi1_MON.VAL', name='i1')
    i2 = Cpt(EpicsSignalRO, 'RIO1:GalilAi2_MON.VAL', name='i2')
    bs = Cpt(EpicsSignalRO, 'RIO1:GalilAi3_MON.VAL', name='bs')

    # Control signals (read-write)
    # count_time = Cpt(EpicsSignal, "IntegrationTime", name="count_time")
    
    def __init__(self, prefix='BL17-2:', **kwargs):
        super().__init__(prefix, **kwargs)

        # configure read_attrs 
        self.read_attrs = ['i0', 'i1', 'i2', 'bs']
        self.i0.kind = 'hinted'
        self.i1.kind = 'hinted'
        self.i2.kind = 'hinted'
        self.bs.kind = 'hinted'


def init_BL172_counters(counters_prefix='BL17-2:'):

    # Instantiate and configure Counters and Photodiode
    beamline_counters = BeamlineCounters(prefix=counters_prefix, name='beamline_counters')

    print(f"bs    ", beamline_counters.bs.get())
    print(f"i0    ", beamline_counters.i0.get())
    print(f"i1    ", beamline_counters.i1.get())
    print(f"i2    ", beamline_counters.i2.get())

    print(f"Counters and Photodiode initialized successfully.")
    return beamline_counters 


counters = init_BL172_counters()
i0, i1, i2, bs = counters.i0, counters.i1, counters.i2, counters.bs

#i0 = Cpt(EpicsSignalRO, 'RIO1:GalilAi0_MON.VAL', name='i0')
#i1 = Cpt(EpicsSignalRO, 'RIO1:GalilAi1_MON.VAL', name='i1')
#i2 = Cpt(EpicsSignalRO, 'RIO1:GalilAi2_MON.VAL', name='i2')
#bs = Cpt(EpicsSignalRO, 'RIO1:GalilAi3_MON.VAL', name='bs')