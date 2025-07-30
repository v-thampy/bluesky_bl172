from bluesky import RunEngine, plan_stubs as bps
from bluesky.preprocessors import run_decorator
import time

RE = RunEngine({})

exec(open('/home/yuanhu/anaconda3/ssrl_test/BL172_detectors_init.py').read())
exec(open('/home/yuanhu/anaconda3/ssrl_test/BL172_motors_init.py').read())
# exec(open('/home/yuanhu/anaconda3/ssrl_test/BL172_counters_init.py').read())
exec(open('/home/yuanhu/anaconda3/ssrl_test/BL172_RunPlan_module.py').read())
print('read script')

eiger = init_BL172_detectors()
motor = init_BL172_motor()
stepper = init_BL172_stepper()
beamstop = init_BL172_beamstop()

get_eiger_config(eiger)

print(f"\nstepper_readback = {stepper.rdbd.get()}")

# Importing LiveTable etc
from bluesky.callbacks import LiveTable, LivePlot
from bluesky.callbacks.broker import LiveImage
