# python Motor_Flow.py stop
import sys
import numpy as np
import nidaqmx

# ==============================
# HARDWARE SETTINGS
# ==============================
AO_CHAN = "Dev2/ao0"
AO_MIN = 0.0
AO_MAX = 5.0

# ==============================
# Calibration Data (MATLAB same)
# ==============================
V = np.arange(0.24, 0.72, 0.02)

S_test = np.array([
    0.08, 0.10, 0.11, 0.13, 0.14, 0.15, 0.17, 0.18,
    0.19, 0.20, 0.21, 0.22, 0.24, 0.25, 0.26, 0.28,
    0.29, 0.31, 0.32, 0.34, 0.35, 0.36, 0.37, 0.39
])

# Linear calibration (same as polyfit in MATLAB)
P = np.polyfit(S_test, V, 1)


def write_voltage(voltage: float):
    with nidaqmx.Task() as task:
        task.ao_channels.add_ao_voltage_chan(
            AO_CHAN,
            min_val=AO_MIN,
            max_val=AO_MAX
        )
        task.write(float(voltage), auto_start=True)


def set_flow(speed: float):
    voltage = float(np.polyval(P, speed))

    # Clamp for safety
    voltage = max(AO_MIN, min(AO_MAX, voltage))

    print(f"Requested flow: {speed}")
    print(f"Output voltage: {voltage:.4f} V")

    write_voltage(voltage)
    print("Flow set successfully.")


def stop_flow():
    write_voltage(0.0)
    print("Flow stopped (0 V output).")


if __name__ == "__main__":

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python flowcon.py flow <speed>")
        print("  python flowcon.py stop")
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == "--flow":
        if len(sys.argv) != 3:
            print("Usage: python flowcon.py flow <speed>")
            sys.exit(1)

        speed = float(sys.argv[2])
        set_flow(speed)

    elif cmd == "stop":
        stop_flow()

    else:
        print("Unknown command.")