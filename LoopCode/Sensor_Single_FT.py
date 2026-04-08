import argparse
import csv
import os
import queue
import sys
import threading
import time
from datetime import datetime

from gsv86lib import gsv86


parser = argparse.ArgumentParser(description="Force/torque sensor recorder")
parser.add_argument("--port", required=True, help="COM port, e.g. COM16 or COM17")
parser.add_argument("--zero", action="store_true", help="Run zero calibration once at startup")
args = parser.parse_args()

COM_PORT_1 = args.port
BAUD_RATE = 115200
SAVE_DRAIN_SEC = 0.6
LOOP_SLEEP_SEC = 0.001


def create_new_file(filename_base: str):
    today_str = datetime.now().strftime("%Y%m%d")
    directory = os.path.join("DATA", today_str)
    os.makedirs(directory, exist_ok=True)

    filename = os.path.join(directory, f"{filename_base}.csv")
    f = open(filename, "w", newline="")
    writer = csv.writer(f)
    writer.writerow([
        "DeviceTime",
        "S1_Ch1", "S1_Ch2", "S1_Ch3", "S1_Ch4", "S1_Ch5", "S1_Ch6",
    ])
    print(f"[FILE_CREATED] {filename}", flush=True)
    return f, writer, filename


def command_reader(cmd_queue: queue.Queue):
    while True:
        line = sys.stdin.readline()
        if line == "":
            time.sleep(0.01)
            continue
        cmd_queue.put(line.strip())


cmd_queue = queue.Queue()
threading.Thread(target=command_reader, args=(cmd_queue,), daemon=True).start()


# ----------------------------
# Open Device
# ----------------------------
dev1 = gsv86(COM_PORT_1, BAUD_RATE)

if args.zero:
    print(f"[INFO] Running zero calibration on {COM_PORT_1}...", flush=True)
    dev1.SetZero(0)
    time.sleep(0.5)
    print(f"[ZEROED] {COM_PORT_1}", flush=True)

dev1.StartTransmission()
print(f"[READY] Sensor on {COM_PORT_1} is ready", flush=True)


armed_filename = None
current_filename = None
f = None
writer = None
rows_written = 0
recording = False
last_ts1 = None
save_requested = False
save_request_time = None
stop_requested = False


def finalize_file():
    global f, writer, current_filename, rows_written, recording
    global armed_filename, last_ts1, save_requested, save_request_time

    if f is not None:
        f.flush()
        f.close()
        print(f"[FILE_SAVED] {current_filename} rows={rows_written}", flush=True)

    f = None
    writer = None
    current_filename = None
    rows_written = 0
    recording = False
    armed_filename = None
    last_ts1 = None
    save_requested = False
    save_request_time = None


try:
    while True:
        while not cmd_queue.empty():
            cmd = cmd_queue.get()

            if cmd.startswith("FILE "):
                filename_base = cmd[5:].strip()
                if filename_base:
                    armed_filename = filename_base
                    save_requested = False
                    save_request_time = None
                    print(f"[ARMED] {COM_PORT_1} -> {armed_filename}", flush=True)
                else:
                    print(f"[IGNORED] Empty FILE command on {COM_PORT_1}", flush=True)

            elif cmd == "START":
                if recording:
                    print(f"[STARTED] {COM_PORT_1} -> {current_filename}", flush=True)
                elif armed_filename is None:
                    print(f"[IGNORED] START before FILE on {COM_PORT_1}", flush=True)
                else:
                    f, writer, current_filename = create_new_file(armed_filename)
                    rows_written = 0
                    last_ts1 = None
                    recording = True
                    save_requested = False
                    save_request_time = None
                    print(f"[STARTED] {COM_PORT_1} -> {current_filename}", flush=True)

            elif cmd == "SAVE":
                if recording:
                    save_requested = True
                    save_request_time = time.time()
                    print(f"[SAVE_REQUESTED] {COM_PORT_1}", flush=True)
                elif f is not None:
                    finalize_file()
                elif armed_filename is not None:
                    f, writer, current_filename = create_new_file(armed_filename)
                    finalize_file()
                else:
                    print(f"[FILE_SAVED] none rows=0", flush=True)

            elif cmd == "STOP":
                stop_requested = True

            elif cmd:
                print(f"[IGNORED] Unknown command on {COM_PORT_1}: {cmd}", flush=True)

        m1 = dev1.ReadValue()
        if recording and m1 and getattr(m1, "data", None):
            ts1 = m1.getTimestamp()
            if ts1 != last_ts1:
                row = [
                    ts1,
                    m1.getChannel1(),
                    m1.getChannel2(),
                    m1.getChannel3(),
                    m1.getChannel4(),
                    m1.getChannel5(),
                    m1.getChannel6(),
                ]
                writer.writerow(row)
                f.flush()
                rows_written += 1
                last_ts1 = ts1

        if recording and save_requested and save_request_time is not None:
            if time.time() - save_request_time >= SAVE_DRAIN_SEC:
                finalize_file()

        if stop_requested:
            if recording:
                if not save_requested:
                    save_requested = True
                    save_request_time = time.time()
                elif save_request_time is not None and (time.time() - save_request_time >= SAVE_DRAIN_SEC):
                    finalize_file()
                    break
            else:
                if f is not None:
                    finalize_file()
                break

        time.sleep(LOOP_SLEEP_SEC)

except KeyboardInterrupt:
    pass
finally:
    try:
        if recording or f is not None:
            finalize_file()
    except Exception:
        pass

    try:
        dev1.StopTransmission()
    except Exception:
        pass

    print(f"[STOPPED] {COM_PORT_1}", flush=True)
