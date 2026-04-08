import subprocess
import sys
import time
import threading
from itertools import product
from pathlib import Path


# =========================================================
# USER SETTINGS
# =========================================================
TIME_RECORD = 10

NUM_FIN_LIST = ["DualL", "DualF"]          # Example: ["SinL"], ["SinF"], ["DualL", "DualF"]
FIN_TYPE_LIST = ["Jiatype1"]
MOTOR_AMP_LIST = [10]
MOTOR_FRE_LIST = [0.5]
FLOW_SP_LIST = [0.15]
LOC_X_LIST = [10, 20]
LOC_Y_LIST = [0]
ITER_LIST = [1]

# Dual mode phases
DUAL_PHASE_LIST = [45]

# Start position of follower stage
START_POS = [0, 0]

# Ports / files
PYTHON_EXE = sys.executable
SENSOR_SCRIPT = r".\Sensor_Single_FT.py"
FLOW_SCRIPT = r".\Motor_Flow.py"
STEP_SCRIPT = r".\Motor_Step.py"
FIN_SCRIPT = r".\Motor_Fin.py"
SIGNAL_SCRIPT = r".\Signal_pulse.py"

SIGNAL_PORT = "COM14"
LEFT_PORT = "COM17"
FRONT_PORT = "COM16"

# Folder for data files (kept for compatibility / visibility)
DATA_DIR = Path("./data")
DATA_DIR.mkdir(parents=True, exist_ok=True)


# =========================================================
# HELPERS
# =========================================================
def contains_warning_or_error(text: str) -> bool:
    if not text:
        return False
    lower = text.lower()
    return ("traceback" in lower) or ("fatal" in lower) or ("[fatal]" in lower) or (" error" in lower)


class OutputPump(threading.Thread):
    def __init__(self, proc: subprocess.Popen):
        super().__init__(daemon=True)
        self.proc = proc
        self.all_lines = []
        self.lock = threading.Lock()

    def run(self):
        try:
            while True:
                line = self.proc.stdout.readline()
                if line == "":
                    break
                with self.lock:
                    self.all_lines.append(line)
                print(line, end="")
        finally:
            try:
                remaining = self.proc.stdout.read() if self.proc.stdout else ""
            except Exception:
                remaining = ""
            if remaining:
                for line in remaining.splitlines(True):
                    with self.lock:
                        self.all_lines.append(line)
                    print(line, end="")

    def snapshot_from(self, start_index: int) -> str:
        with self.lock:
            return "".join(self.all_lines[start_index:])

    def current_index(self) -> int:
        with self.lock:
            return len(self.all_lines)


class SensorSession:
    def __init__(self, port: str, do_zero: bool):
        self.port = port
        self.do_zero = do_zero
        self.proc = None
        self.pump = None
        self.cmd = None

    def start(self):
        cmd = [PYTHON_EXE, SENSOR_SCRIPT, "--port", self.port]
        if self.do_zero:
            cmd.append("--zero")
        self.cmd = cmd
        print("\n[START]", " ".join(str(x) for x in cmd))
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self.pump = OutputPump(self.proc)
        self.pump.start()
        self.wait_for_marker("[READY]", timeout=20, context=f"Sensor startup {self.port}", start_index=0)

    def send(self, message: str):
        if self.proc is None or self.proc.poll() is not None:
            raise RuntimeError(f"Sensor process on {self.port} is not running")
        print(f"[SENSOR_CMD] {self.port}: {message}")
        assert self.proc.stdin is not None
        self.proc.stdin.write(message + "\n")
        self.proc.stdin.flush()

    def _current_output_index(self) -> int:
        return self.pump.current_index() if self.pump is not None else 0

    def wait_for_marker(self, marker: str, timeout: float, context: str = "", start_index: int = 0) -> str:
        start_time = time.time()

        while time.time() - start_time < timeout:
            if self.pump is None:
                raise RuntimeError(f"{context or self.port}: output pump not initialized")

            text = self.pump.snapshot_from(start_index)
            if marker in text:
                return text

            if contains_warning_or_error(text):
                raise RuntimeError(f"{context or self.port} produced error output:\n{text}")

            if self.proc is not None and self.proc.poll() is not None:
                raise RuntimeError(
                    f"{context or self.port} exited before sending {marker}.\n"
                    f"Output:\n{text}"
                )

            time.sleep(0.05)

        text = self.pump.snapshot_from(start_index) if self.pump is not None else ""
        raise RuntimeError(
            f"{context or self.port} did not send {marker} within {timeout} seconds.\n"
            f"Output so far:\n{text}"
        )

    def request_file(self, file_stem: str):
        start_idx = self._current_output_index()
        self.send(f"FILE {file_stem}")
        self.wait_for_marker("[ARMED]", timeout=10, context=f"Arm sensor {self.port}", start_index=start_idx)

    def start_recording(self):
        start_idx = self._current_output_index()
        self.send("START")
        self.wait_for_marker("[STARTED]", timeout=10, context=f"Start recording {self.port}", start_index=start_idx)

    def save_recording(self):
        start_idx = self._current_output_index()
        self.send("SAVE")
        self.wait_for_marker(
            "[FILE_SAVED]",
            timeout=max(20, TIME_RECORD + 10),
            context=f"Save recording {self.port}",
            start_index=start_idx,
        )

    def stop(self):
        if self.proc is None:
            return
        if self.proc.poll() is not None:
            return
        try:
            start_idx = self._current_output_index()
            self.send("STOP")
            self.wait_for_marker("[STOPPED]", timeout=10, context=f"Sensor shutdown {self.port}", start_index=start_idx)
        finally:
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    self.proc.wait(timeout=3)


def raise_if_bad_output(result, cmd):
    stdout = result.stdout or ""
    stderr = result.stderr or ""

    if stdout.strip():
        print(stdout, end="" if stdout.endswith("\n") else "\n")
    if stderr.strip():
        print(stderr, end="" if stderr.endswith("\n") else "\n")

    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed with return code {result.returncode}:\n"
            f"{' '.join(str(x) for x in cmd)}"
        )

    if contains_warning_or_error(stdout) or contains_warning_or_error(stderr):
        raise RuntimeError(
            f"Warning/Error detected in command output:\n"
            f"{' '.join(str(x) for x in cmd)}"
        )


def run_cmd(cmd):
    print("\n[RUN]", " ".join(str(x) for x in cmd))
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    raise_if_bad_output(result, cmd)
    return result


def flow_tag(flow_value: float):
    return flow_value


def normalize_fin_modes(fin_modes):
    normalized = []
    dual_added = False
    for mode in fin_modes:
        if mode in ("DualL", "DualF", "Dual"):
            if not dual_added:
                normalized.append("Dual")
                dual_added = True
        elif mode in ("SinL", "SinF"):
            normalized.append(mode)
        else:
            raise ValueError(f"Unknown Num_fin: {mode}")
    return normalized


def fin_label(num_fin: str) -> str:
    mapping = {
        "SinL": "SingL",
        "SinF": "SingF",
        "Dual": "Dual",
    }
    return mapping[num_fin]


def make_filename(num_fin, fin_type, amp, fre, phase, flow, x, y, iteration):
    return (
        f"{fin_label(num_fin)}_{fin_type}"
        f"_Amp{amp}"
        f"_freq{fre}"
        f"_phase{phase}"
        f"_flow{flow_tag(flow)}"
        f"_x{x}"
        f"_y{y}"
        f"_iter{iteration}"
    )


def sensor_targets_for_mode(num_fin: str):
    if num_fin == "SinL":
        return [(LEFT_PORT, "SingL")]
    if num_fin == "SinF":
        return [(FRONT_PORT, "SingF")]
    if num_fin == "Dual":
        return [(LEFT_PORT, "DualL"), (FRONT_PORT, "DualF")]
    raise ValueError(f"Unsupported Num_fin: {num_fin}")


def move_stage(agent: str, direction: str, dist: int):
    if dist == 0:
        return
    cmd = [
        PYTHON_EXE, STEP_SCRIPT,
        "--agent", agent,
        "--dir", direction,
        "--dist", str(int(dist)),
    ]
    run_cmd(cmd)
    wait_sec = round(abs(dist / 10)) + 2
    print(f"[INFO] Waiting {wait_sec} s after {direction}-move")
    time.sleep(wait_sec)


def move_to_position(current_pos, target_pos):
    move_dx = int(target_pos[0] - current_pos[0])
    move_dy = int(target_pos[1] - current_pos[1])

    if move_dx == 0 and move_dy == 0:
        return current_pos

    print(f"\n>>> Moving to position ({target_pos[0]}, {target_pos[1]})")
    time.sleep(2)

    if move_dx != 0:
        move_stage("follower", "x", move_dx)
        print("[INFO] X-axis moved")

    if move_dy != 0:
        move_stage("follower", "y", move_dy)
        print("[INFO] Y-axis moved")

    return [target_pos[0], target_pos[1]]


def return_to_start(current_pos, start_pos):
    move_dx = int(start_pos[0] - current_pos[0])
    move_dy = int(start_pos[1] - current_pos[1])

    if move_dx == 0 and move_dy == 0:
        print("[INFO] Already at start position")
        return

    print("\nReturning to start position...")

    if move_dx != 0:
        move_stage("follower", "x", move_dx)
    if move_dy != 0:
        move_stage("follower", "y", move_dy)

    print("[INFO] Returned to start")


def set_flow(flow_value: float, previous_flow):
    if previous_flow is None or flow_value != previous_flow:
        run_cmd([PYTHON_EXE, FLOW_SCRIPT, "--flow", str(flow_value)])
        print("[INFO] Flow changed. Waiting 20 s...")
        time.sleep(20)
    else:
        print("[INFO] Flow unchanged. No 20 s wait.")
    return flow_value


def start_fin(fre: float, amp: float, phase: float):
    run_cmd([
        PYTHON_EXE, FIN_SCRIPT,
        "--fre", str(fre),
        "--amp", str(amp),
        "--phase", str(phase),
    ])


def stop_fin():
    run_cmd([
        PYTHON_EXE, FIN_SCRIPT,
        "--fre", "0",
        "--amp", "0",
        "--phase", "0",
    ])


def send_signal(sec: float):
    run_cmd([
        PYTHON_EXE, SIGNAL_SCRIPT,
        "--port", SIGNAL_PORT,
        "--freq", "10",
        "--pulse_us", "500",
        "--sec", str(sec),
    ])


def compute_total_cycles(normalized_modes):
    total = 0
    for num_fin in normalized_modes:
        phase_list = [0] if num_fin != "Dual" else DUAL_PHASE_LIST
        total += (
            len(FIN_TYPE_LIST)
            * len(MOTOR_AMP_LIST)
            * len(MOTOR_FRE_LIST)
            * len(phase_list)
            * len(FLOW_SP_LIST)
            * len(LOC_X_LIST)
            * len(LOC_Y_LIST)
            * len(ITER_LIST)
        )
    return total


# =========================================================
# MAIN
# =========================================================
def main():
    current_pos = START_POS.copy()
    previous_flow = None
    zeroed_ports = set()
    cycle_count = 0
    normalized_modes = normalize_fin_modes(NUM_FIN_LIST)
    total_cycles = compute_total_cycles(normalized_modes)
    sensor_sessions = {}

    try:
        needed_ports = set()
        for mode in normalized_modes:
            for port, _ in sensor_targets_for_mode(mode):
                needed_ports.add(port)

        for port in sorted(needed_ports):
            session = SensorSession(port=port, do_zero=(port not in zeroed_ports))
            session.start()
            zeroed_ports.add(port)
            sensor_sessions[port] = session

        for num_fin in normalized_modes:
            phase_list = [0] if num_fin != "Dual" else DUAL_PHASE_LIST

            for fin_type, amp, fre, phase, flow, x, y, iteration in product(
                FIN_TYPE_LIST,
                MOTOR_AMP_LIST,
                MOTOR_FRE_LIST,
                phase_list,
                FLOW_SP_LIST,
                LOC_X_LIST,
                LOC_Y_LIST,
                ITER_LIST,
            ):
                cycle_count += 1

                file_stem = make_filename(
                    num_fin=num_fin,
                    fin_type=fin_type,
                    amp=amp,
                    fre=fre,
                    phase=phase,
                    flow=flow,
                    x=x,
                    y=y,
                    iteration=iteration,
                )

                print("\n" + "=" * 70)
                print(f"[CYCLE {cycle_count}/{total_cycles}] {file_stem}")
                print("=" * 70)

                targets = sensor_targets_for_mode(num_fin)

                for port, suffix in targets:
                    sensor_sessions[port].request_file(f"{file_stem}_{suffix}")

                previous_flow = set_flow(flow, previous_flow)
                current_pos = move_to_position(current_pos, [x, y])
                start_fin(fre=fre, amp=amp, phase=phase)
                time.sleep(1.0)

                for port, _ in targets:
                    sensor_sessions[port].start_recording()

                send_signal(sec=TIME_RECORD)
                stop_fin()

                for port, _ in targets:
                    sensor_sessions[port].save_recording()

                print(f"[INFO] Cycle finished: {file_stem}")
                time.sleep(1.0)

    except Exception as e:
        print(f"\n[FATAL] {e}")
        raise

    finally:
        print("\n[INFO] All cycles finished or interrupted.")

        for session in sensor_sessions.values():
            try:
                session.stop()
            except Exception as e:
                print(f"[WARN] Sensor shutdown issue on {session.port}: {e}")

        try:
            run_cmd([PYTHON_EXE, FLOW_SCRIPT, "stop"])
        except Exception:
            try:
                run_cmd([PYTHON_EXE, FLOW_SCRIPT, "--flow", "0"])
            except Exception as e:
                print(f"[WARN] Failed to stop flow during cleanup: {e}")

        try:
            stop_fin()
        except Exception as e:
            print(f"[WARN] Failed to stop fin during cleanup: {e}")

        try:
            return_to_start(current_pos, START_POS)
        except Exception as e:
            print(f"[WARN] Failed to return to start during cleanup: {e}")


if __name__ == "__main__":
    main()
