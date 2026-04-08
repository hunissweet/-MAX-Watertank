# python .\Motor_Fin.py --fre 0 --amp 10 --phase 45
import argparse
import serial
import time

def get_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fre", type=float, required=True)
    parser.add_argument("--amp", type=float, required=True)
    parser.add_argument("--phase", type=float, required=True)
    parser.add_argument("--port", type=str, default="COM18")
    parser.add_argument("--baud", type=int, default=9600)
    args = parser.parse_args()

    frequency = args.fre
    amplitude = args.amp
    phase_lag = args.phase

    return frequency,amplitude,phase_lag

def control(frequency,amplitude,phase_lag,port="COM18",baud="9600"):
    data_packet = f"MOVE {frequency:.2f} {amplitude:.2f} {phase_lag:.2f} 255\n"

    ser = serial.Serial(
        port=port,
        baudrate=baud,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=1,
        xonxoff=False,
        rtscts=False,
        dsrdtr=False,
    )

    time.sleep(2)
    ser.reset_input_buffer()
    ser.reset_output_buffer()

    print("Sending:", repr(data_packet))
    ser.write(data_packet.encode("ascii"))
    ser.flush()

    time.sleep(0.2)

    if ser.in_waiting > 0:
        reply = ser.readline().decode("ascii", errors="ignore")
        print("Reply:", repr(reply))

    ser.close()

def main():
    frequency,amplitude,phase_lag = get_parser()
    control(frequency,amplitude,phase_lag)

if __name__ == "__main__":
    main()