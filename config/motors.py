import sys
import time
from ophyd import EpicsMotor
from ophyd_devices.StepperMotor import StepperEpicsMotor
from ophyd import Component as Cpt
from ophyd import EpicsSignal, Signal
from ophyd.status import Status
import threading

def init_motor(motor_prefix, motor_name, motor_type='mdrive', precision=4, tolerance=0.001, labels={'motors', 'scan_motors'}):
    # Connect to motor
    if motor_type == 'mdrive':
        motor = EpicsMotor(motor_prefix, name=motor_name, labels=labels)
    elif motor_type == 'stepper':
        motor = StepperEpicsMotor(motor_prefix, name=motor_name, labels=labels)
    # motor.wait_for_connection(timeout=1)
    print(f"Motor {motor_name} initialized successfully.")
    
    # motor.precision = precision
    motor.tolerance = tolerance
    
    return motor

sx   = init_motor("BL172:MDrive:m1", "sx", labels={'motors', 'scan_motors'})
#th = init_motor('BL172:MDrive:m4', "th", labels={'motors', 'scan_motors'}, motor_type='stepper')
#sfpx = init_motor('BL172:SAX_MC2:MOTOR3', "sfpx", labels={'motors', 'scan_motors'}, motor_type='stepper')

#motor_list = [sx, sfpx, th]
motor_list = [sx]

def init_BL172_motor(motor_prefix='BL172:MDrive:m1'):

    # Connect to motor
    m1 = EpicsMotor(motor_prefix, name='m1')
    m1.wait_for_connection(timeout=1)

    print(f"MDriver motor m1 initialized successfully.")
    return m1


def init_BL172_stepper(stepper_prefix='BL172:SAX_MC2:'):

    # Connect to stpper motor
    sfpx = StepperEpicsMotor(stepper_prefix+'MOTOR3', name='sfpx', labels={'motors', 'scan_motors'})
    sfpx.wait_for_connection(timeout=1)


    #  the PV 'direction_of_travel' seems not implemented in customized controller developed by Dehong
    if 'direction_of_travel' in sfpx.read_attrs:
        sfpx.read_attrs.remove('direction_of_travel')

    print(f"Stepper motors sfpx initialized successfully.")
    return sfpx

    
#th = EpicsMotor("SAMPLE:TH:PV", name="th", labels={'motors', 'scan_motors'})
#sfpx = init_BL172_stepper()
