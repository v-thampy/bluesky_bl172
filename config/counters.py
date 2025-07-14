from ophyd import EpicsSignalRO

i0 = EpicsSignalRO("I0:PV", name="i0")
i1 = EpicsSignalRO("I1:PV", name="i1")
monitor = EpicsSignalRO("MON:PV", name="monitor")
temp = EpicsSignalRO("TEMP:PV", name="temperature")

counters = [i0, i1, monitor, temp]