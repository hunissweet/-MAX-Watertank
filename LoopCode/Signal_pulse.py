# python .\Sensor_Single_FT.py --port COM14 --freq 10 --pulse_us 500 --sec 2
import argparse
import time
import serial


def open_serial(port: str, baud: int = 115200, timeout: float = 0.5) -> serial.Serial:
    ser = serial.Serial(port=port, baudrate=baud, timeout=timeout)

    # Arduino reset delay
    time.sleep(2.0)
    ser.reset_input_buffer()

    return ser


def send_cmd(ser: serial.Serial, cmd: str) -> str:
    ser.write((cmd.strip() + "\n").encode("ascii", errors="ignore"))
    ser.flush()

    try:
        line = ser.readline().decode("utf-8", errors="replace").strip()
    except Exception:
        line = ""

    return line


def build_cmd(freq, pulse_us):
    if pulse_us is None:
        return f"{freq:.6g}"
    else:
        return f"F {freq:.6g} P {pulse_us}"


def main():

    ap = argparse.ArgumentParser(description="Set RF2040 trigger frequency via serial.")
    ap.add_argument("--port", required=True)
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--freq", type=float, required=True)
    ap.add_argument("--pulse_us", type=int, default=None)

    # NEW argument
    ap.add_argument("--sec", type=float, default=None,
                    help="Run for N seconds then stop (freq=0)")

    args = ap.parse_args()

    ser = open_serial(args.port, args.baud)

    # send ON command
    cmd = build_cmd(args.freq, args.pulse_us)
    resp = send_cmd(ser, cmd)

    print("Sent:", cmd)
    print("Recv:", resp if resp else "(no response)")

    # if sec specified → wait then stop
    if args.sec is not None:

        time.sleep(args.sec)

        stop_cmd = build_cmd(0, args.pulse_us)
        resp = send_cmd(ser, stop_cmd)

        print("Sent:", stop_cmd)
        print("Recv:", resp if resp else "(no response)")

    ser.close()


if __name__ == "__main__":
    main()