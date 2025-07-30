import bluesky.plan_stubs as bps
from config.detectors import MyEiger
import time

def view_only(det):
    # ensure no files are written
    print("Viewing Eiger detector in view-only mode...")
    # disable saving
    det.hdf5.warmup()
    det.hdf5.enable.put(0)
    det.hdf5.capture.put(0)
    det.hdf5.write_file.put(0)

    # configure streaming
    det.cam.num_images.put(0)
    det.cam.trigger_mode.put('Internal')
    det.cam.acquire_time.put(0.01)

    # kick off
    det.cam.acquire.put(1)
    yield from bps.sleep(10)    # view for 10 s
    det.cam.acquire.put(0)

# Run it
# RE(view_only(eiger))


def configure_eiger_for_burst(eiger, num_images=100, frame_time=0.001, file_path="/data/", base_filename="scan"):
    print("Configuring Eiger detector for burst acquisition...")
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


def get_eiger_config(eiger):
    # print(f"\nname_pattern = {eiger.cam.FWNamePattern.get()}")
    print(f"\nname_pattern = {''.join(chr(c) for c in eiger.cam.FWNamePattern.get() if c != 0)}")
    #print(f"\nname_pattern = {eiger.cam.fw_name_pattern.get()}")
    print(f"data_directory = {eiger.hdf1.file_path.get()}")

    print(f"\nacquire_time = {eiger.cam.acquire_time.get()}")
    print(f"frame_time = {eiger.cam.acquire_period.get()}")

    print(f"\nimages = {eiger.cam.num_images.get()}")
    # print(f"images_per_file = {eiger.cam.fw_num_images_per_file.get()}")
    print(f"images_per_file = {eiger.cam.FWNImagesPerFile.get()}")

    print(f"\ntrigger = {eiger.cam.trigger_mode.get()}")
    print(f"ntriggers = {eiger.cam.num_triggers.get()}")


def eiger_set_fname(eiger, fname):
    eiger.cam.FWNamePattern.put(fname)
    return fname


def eiger_set_dir(eiger, dir_path):
    if dir_path is None:
        dir_path = eiger.hdf5.file_path.get()
    eiger.hdf5.file_path.put(dir_path)
    return dir_path

def eiger_set_frametime(eiger, frametime):
    eiger.cam.acquire_period.put(frametime)
    return frametime


def eiger_set_acqtime(eiger, acqtime):
    if acqtime is None or acqtime == 0:
        acqtime = eiger.cam.acquire_time.get()
    eiger.cam.acquire_time.put(acqtime)
    return acqtime

def eiger_set_nimages(eiger, nimages):
    if nimages is None or nimages == 0:
        nimages = eiger.cam.num_images.get()
    eiger.cam.num_images.put(nimages)
    return nimages

def eiger_set_nimages_per_file(eiger, nimages_per_file):
    if nimages_per_file is None or nimages_per_file == 0:
        nimages_per_file = 1000
    eiger.cam.FWNImagesPerFile.put(nimages_per_file)
    return nimages_per_file


def eiger_set_trigger_mode(eiger, trigger_mode):
    eiger.cam.trigger_mode.put(trigger_mode)
    print(f"Trigger mode set to: {trigger_mode}")


def eiger_set_ntriggers(eiger, ntriggers):
    if ntriggers is None or ntriggers == 0:
        ntriggers = 1
    eiger.cam.num_triggers.put(ntriggers)
    print(f"Number of triggers set to: {ntriggers}")


def eiger_set_image_mode(eiger, image_mode):
    eiger.cam.image_mode.put(image_mode)
    print(f"Image mode set to: {image_mode}")


def ready_detector(
    eiger: MyEiger,
    fname: str,
    dir_path: str,
    acqtime: float,
    frametime: float,
    nimages: int,
    trigger_mode: str,
    ntriggers: int,
    savemode: int = None,
):
    
    # Set file name and data directory
    eiger_set_fname(eiger, fname)
    eiger_set_dir(eiger, dir_path)

    # Set acquisition parameters
    eiger_set_acqtime(eiger, acqtime)
    eiger_set_frametime(eiger, frametime)
    eiger_set_nimages(eiger, nimages)
    eiger_set_trigger_mode(eiger, trigger_mode)
    eiger_set_ntriggers(eiger, ntriggers)

    # Set save mode
    if savemode is not None:
        eiger.hdf5.auto_save.put(savemode)
    get_eiger_config()

def eiger_arm(eiger):
    print("Arming Eiger detector...")
    eiger.cam.acquire.put(1, wait=True)
    print(f"Armed (Trigger Mode - {eiger.cam.trigger_mode.get()})")

def eiger_trigger(eiger, wait_for_input=False, wait_till_finished=True):
    acqtime = eiger.cam.acquire_time.get()
    nimages = eiger.cam.num_images.get()
    ntriggers = eiger.cam.num_triggers.get()

    if wait_for_input:
        input("Hit ENTER to trigger...")

    print(f"\nTriggering: {nimages} images, {acqtime:.3f}s/frame, {ntriggers} triggers")

    # if eiger.cam.trigger_mode.get().lower() == "exts":
    if eiger.cam.trigger_mode.get() == 1:
        print("External trigger ON")
    else:
    # eiger.cam.trigger_signal.put(1)
        eiger.cam.trigger_mode.put(1)

    if wait_till_finished:
        total_time = acqtime * nimages + 1
        print(f"Waiting {total_time:.2f}s for acquisition to complete...")
        time.sleep(total_time)
    #   _eiger_wait_ready()
        print("Acquisition finished.\n")

def eiger_disarm(eiger):
    print("Disarming Eiger detector ...")
    eiger.cam.acquire.put(0)
    print("Eiger Disarmed.\n")

def eiger_transfer_last(eiger):
    print("Transferring last dataset...")
    print("Transferring last dataset...")
    # _eiger_wait_ready()
    time.sleep(2)
    print("Transfer complete.\n")

# High-Level Acquisition Plans
def arm_and_trigger(eiger, wait_for_input=False, wait_till_finished=True):
    print("Arming and triggering Eiger detector...")
    eiger_arm()
    eiger_trigger(wait_for_input, wait_till_finished)
    eiger_disarm()
    eiger_transfer_last()


def eiger_acquire(eiger, fname, dir_path, acqtime, frametime, nimages, trigger_mode, ntriggers, savemode, wait_for_input=False):
    ready_detector(
        eiger,
        fname,
        dir_path,
        acqtime,
        frametime,
        nimages,
        trigger_mode,
        ntriggers,
        savemode
    )
    arm_and_trigger(eiger, wait_for_input)

def estart(eiger, cnt_time: float = 0.5):
    print("Starting continuous acquisition (streaming)...")

    # Save current values 
    saved_config = {
        'acqtime': eiger.cam.acquire_time.get(),
        'nimages': eiger.cam.num_images.get(),
        'trigger_mode': eiger.cam.trigger_mode.get(),
        'ntriggers': eiger.cam.num_triggers.get(),
    }

    # Disable saving (if applicable)
    if hasattr('savemode'):
        eiger.hdf5.auto_save.put(0)

    # Set new values
    eiger_set_acqtime(cnt_time)
    eiger_set_nimages(100)
#    eiger_set_trigger_mode(eiger, "ints")
    eiger_set_trigger_mode(eiger, 0)
    eiger_set_ntriggers(eiger, 1)

    eiger_arm(eiger)
    eiger_trigger(eiger, wait_for_input=False, wait_till_finished=True)

    return saved_config  # For use in estop

def estop(eiger, saved_config=None):
    print("Stopping streaming acquisition...")
    eiger_disarm()

    # Restore previous settings if available
    if saved_config:
        eiger_set_acqtime(saved_config.get('acqtime', 0.1))
        eiger_set_nimages(1)
        eiger_set_trigger_mode(saved_config.get('trigger_mode', 0))
        eiger_set_ntriggers(saved_config.get('ntriggers', 1))

    get_eiger_config()

def eigerburst_ext(
    eiger: MyEiger,
    fname: str,
    dir_path: str,
    acqtime: float,
    frametime: float,
    delay: float,
    nimages: int,
    trigger_mode: str,
    ntriggers: int,
    savemode: int
):
    ready_detector(
        eiger,
        fname,
        dir_path,
        acqtime,
        frametime,
        nimages,
        trigger_mode,
        ntriggers,
        savemode
    )

    time.sleep(1)
    eiger_arm()
    time.sleep(4)

    # Simulated delay generator trigger
    print(f"Setting delay generator delay to {delay:.5f} s")

    input("Press ENTER to trigger...")

    # Simulate motor move and shutter open
    print("Trigger ON")
    time.sleep(nimages * frametime + 2)

    eiger_disarm()
    time.sleep(2)
    eiger_transfer_last()

