from ophyd import EpicsMotor

sample_y = EpicsMotor("SAMPLE:Y:PV", name="sample_y")
th = EpicsMotor("SAMPLE:TH:PV", name="th")
motor_list = [sample_y, th]