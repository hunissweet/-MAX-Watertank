import argparse
import math
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


DEFAULT_PYTHON = r"C:/Users/liang/anaconda3/envs/flowtank/python.exe"
DEFAULT_NEW_STEP = r"d:/Liang Li/RobotRepeatRealFish/python/new_step_ctr.py"
DEFAULT_TRIGGER_PORT = "COM10"


def build_distance_vector(direction: str, distance_mm: int):
    v = int(math.ceil(abs(distance_mm) / 10.0))
    if v < 1:
        v = 1

    x = y = z = 0
    direction = direction.lower()

    if direction == "x":
        x = distance_mm
    elif direction == "y":
        y = distance_mm
    elif direction == "z":
        z = distance_mm
    else:
        raise ValueError("direction must be x, y, or z")

    return [v, x, y, z]


def build_matlab_like_env(python_exe: str):
    """
    Replicate StepCtr.initEnv() from MATLAB.
    """
    py_root = str(Path(python_exe).resolve().parent)

    add_to_path = [
        py_root,
        os.path.join(py_root, "Library", "mingw-w64", "bin"),
        os.path.join(py_root, "Library", "usr", "bin"),
        os.path.join(py_root, "Library", "bin"),
        os.path.join(py_root, "Scripts"),
        os.path.join(py_root, "bin"),
    ]

    old_path = os.environ.get("PATH", "")
    parts = add_to_path + old_path.split(";")

    # keep order, remove duplicates, skip empties
    seen = set()
    cleaned = []
    for p in parts:
        if p and p not in seen:
            cleaned.append(p)
            seen.add(p)

    env = os.environ.copy()
    env["PATH"] = ";".join(cleaned)
    return env


def make_filename(new_step_script: str) -> str:
    script_path = Path(new_step_script)
    try:
        repo_root = script_path.resolve().parents[1]
        data_dir = repo_root / "data"
    except Exception:
        data_dir = Path.cwd() / "data"

    data_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return str(data_dir / f"StepCtr_move_{ts}.csv")


def run_new_step(python_exe: str, new_step_script: str, agent: str, vec, filename: str, dry_run: bool):
    cmd = [
        python_exe,
        new_step_script,
        "--filename", filename,
        "--mode", "distance",
        "--distance",
        str(vec[0]), str(vec[1]), str(vec[2]), str(vec[3]),
    ]

    if agent.lower() == "leader":
        cmd.append("--leader")
    elif agent.lower() == "follower":
        cmd.append("--follower")
    else:
        raise ValueError("agent must be leader or follower")

    pretty = " ".join(f'"{c}"' if " " in c else c for c in cmd)
    print("[Step command]")
    print(pretty)

    if dry_run:
        return

    env = build_matlab_like_env(python_exe)
    subprocess.run(cmd, check=True, env=env)


def fire_trigger(python_exe: str, trigger_port: str, trigger_format: str, dry_run: bool):
    if trigger_format == "byte":
        payload_expr = "bytes([1])"
        label = "byte 0x01"
    elif trigger_format == "int16":
        payload_expr = "(1).to_bytes(2, byteorder='little', signed=False)"
        label = "int16 little-endian"
    else:
        raise ValueError("trigger_format must be 'byte' or 'int16'")

    code = (
        "import serial,time;"
        f"ser=serial.Serial({trigger_port!r},9600,timeout=1);"
        "time.sleep(2.0);"
        f"ser.write({payload_expr});"
        "ser.flush();"
        "time.sleep(0.2);"
        "ser.close()"
    )

    print("[Trigger]")
    print(f"Port={trigger_port}, format={label}")

    if dry_run:
        return

    env = build_matlab_like_env(python_exe)
    subprocess.run([python_exe, "-c", code], check=True, env=env)


def main():
    parser = argparse.ArgumentParser(description="Wrapper for MATLAB-style StepCtr control")
    parser.add_argument("--agent", required=True, choices=["leader", "follower"])
    parser.add_argument("--dir", required=True, choices=["x", "y", "z"])
    parser.add_argument("--dist", required=True, type=int)

    parser.add_argument("--python-exe", default=DEFAULT_PYTHON)
    parser.add_argument("--new-step-script", default=DEFAULT_NEW_STEP)
    parser.add_argument("--trigger-port", default=DEFAULT_TRIGGER_PORT)

    parser.add_argument("--pre-fire-delay", type=float, default=0.5)
    parser.add_argument("--trigger-format", choices=["byte", "int16"], default="byte")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-fire", action="store_true")

    args = parser.parse_args()

    vec = build_distance_vector(args.dir, args.dist)
    filename = make_filename(args.new_step_script)

    print("=" * 60)
    print(f"agent           : {args.agent}")
    print(f"direction       : {args.dir}")
    print(f"distance        : {args.dist} mm")
    print(f"raw MATLAB vec  : {vec}")
    print(f"python exe      : {args.python_exe}")
    print(f"new_step_ctr.py : {args.new_step_script}")
    print(f"trigger port    : {args.trigger_port}")
    print(f"trigger format  : {args.trigger_format}")
    print("=" * 60)

    run_new_step(
        python_exe=args.python_exe,
        new_step_script=args.new_step_script,
        agent=args.agent,
        vec=vec,
        filename=filename,
        dry_run=args.dry_run,
    )

    print(f"[Pause] {args.pre_fire_delay} s")
    if not args.dry_run:
        time.sleep(args.pre_fire_delay)

    if not args.no_fire:
        fire_trigger(
            python_exe=args.python_exe,
            trigger_port=args.trigger_port,
            trigger_format=args.trigger_format,
            dry_run=args.dry_run,
        )
    else:
        print("[Trigger] skipped (--no-fire)")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(f"\nSubprocess failed with exit code {e.returncode}", file=sys.stderr)
        sys.exit(e.returncode)
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)