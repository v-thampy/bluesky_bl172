import sys
import time
from ophyd import EpicsMotor
from ophyd import Component as Cpt
from ophyd import EpicsSignal, Signal
from ophyd.status import Status
import threading


class StepperEpicsMotor(EpicsMotor):
    pos = Cpt(EpicsSignal, '.VAL')        # target position
    readback = Cpt(EpicsSignal, '.RBV')   # actual position
    movn = Cpt(EpicsSignal, '.MOVN')      # is moving
    stopm = Cpt(EpicsSignal, '.STOP')     # stop motor
    velo = Cpt(EpicsSignal, '.VELO')
    dval = Cpt(EpicsSignal, '.DVAL')      # dial value
    accl = Cpt(EpicsSignal, '.ACCL')      # acceleration time
    dmov = Cpt(EpicsSignal, '.DMOV')      # done moving
    stat = Cpt(EpicsSignal, '.STAT')      # alarm status
    sevr = Cpt(EpicsSignal, '.SEVR')      # alarm severity
    rdbd = Cpt(EpicsSignal, '.RDBD')      # readback deadband
    hlm = Cpt(EpicsSignal, '.HLM')        # high limit
    llm = Cpt(EpicsSignal, '.LLM')        # low limit
    hls = Cpt(EpicsSignal, '.HLS')        # high limit switch
    lls = Cpt(EpicsSignal, '.LLS')        # low limit switch

    direction_of_travel = Cpt(Signal, value='pos')   # faked
    motor_done_move = Cpt(Signal, value=1)          # faked .DMOV

#    def _move_changed(self, *args, **kwargs):
#        # Skip direction check entirely (seems not implemented in customized controller developed by Dehong)
#        pass

    def move(self, position, wait=True, timeout=10, **kwargs):
        # Remove unsupported kwarg from bluesky
        kwargs.pop('moved_cb', None)

        # Start move
        self.user_setpoint.put(position, **kwargs)

        status = Status()

        def watch_position():
            start = time.time()
            _timeout = timeout or  10  # Ensure timeout is a float
            while True:
                current = self.readback.get()
                if abs(current - position) < 0.01:
                    status.set_finished()
                    break
                if time.time() - start > _timeout:
                    status.set_exception(TimeoutError(
                        f"Stepper failed to reach {position} in {timeout}s. RBV={current}"
                    ))
                    break
                time.sleep(0.1)

        threading.Thread(target=watch_position, daemon=True).start()

        if wait:
            status.wait(timeout=timeout)
        return status