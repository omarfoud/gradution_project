import argparse
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT_DIR / "frontend" / "Graduation_Project"
HOST = "127.0.0.1"


def npm_command() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def port_is_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def wait_for_port(name: str, host: str, port: int, timeout: int) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_is_open(host, port):
            print(f"{name} is listening on http://{host}:{port}")
            return True
        time.sleep(1)
    print(f"{name} did not open port {port} within {timeout}s")
    return False


def request_url(url: str, timeout: int = 10) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return True, f"HTTP {response.status}"
    except urllib.error.HTTPError as exc:
        return True, f"HTTP {exc.code}"
    except Exception as exc:
        return False, str(exc)


def stream_output(name: str, process: subprocess.Popen) -> None:
    assert process.stdout is not None
    for line in process.stdout:
        print(f"[{name}] {line.rstrip()}")


def start_process(
    name: str,
    command: list[str],
    cwd: Path,
    env: dict[str, str],
) -> subprocess.Popen:
    print(f"Starting {name}...")
    print(f"  cwd: {cwd}")
    print(f"  cmd: {' '.join(command)}")
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    thread = threading.Thread(target=stream_output, args=(name, process), daemon=True)
    thread.start()
    return process


def run_command(name: str, command: list[str], cwd: Path, env: dict[str, str]) -> int:
    print(f"Running {name}...")
    print(f"  cwd: {cwd}")
    print(f"  cmd: {' '.join(command)}")
    completed = subprocess.run(command, cwd=str(cwd), env=env)
    return completed.returncode


def stop_process(name: str, process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    print(f"Stopping {name}...")
    if os.name == "nt":
        process.terminate()
    else:
        process.send_signal(signal.SIGTERM)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start the local AI backend and Next.js frontend.")
    parser.add_argument("--backend-port", type=int, default=8000)
    parser.add_argument("--frontend-port", type=int, default=3000)
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--backend-timeout", type=int, default=180)
    parser.add_argument("--frontend-timeout", type=int, default=180)
    parser.add_argument("--dev", action="store_true", help="Run the frontend with next dev instead of production.")
    parser.add_argument("--build", action="store_true", help="Run npm run build before starting the production frontend.")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the frontend in a browser.")
    return parser.parse_args()


def frontend_build_exists() -> bool:
    return (FRONTEND_DIR / ".next" / "BUILD_ID").exists()


def main() -> int:
    args = parse_args()

    if not (ROOT_DIR / "main.py").exists():
        print(f"Could not find main.py in {ROOT_DIR}")
        return 1
    if not FRONTEND_DIR.exists():
        print(f"Could not find frontend directory: {FRONTEND_DIR}")
        return 1

    backend_url = f"http://{args.host}:{args.backend_port}"
    frontend_url = f"http://{args.host}:{args.frontend_port}"
    employee_chat_url = f"{frontend_url}/dashboard/employee/ai-chat"
    company_chat_url = f"{frontend_url}/dashboard/company/ai-chat"

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["AI_BACKEND_URL"] = backend_url
    env["NEXT_PUBLIC_FRONTEND_URL"] = frontend_url

    processes: list[tuple[str, subprocess.Popen]] = []

    try:
        if port_is_open(args.host, args.backend_port):
            print(f"Backend port {args.backend_port} is already in use. Reusing {backend_url}.")
        else:
            backend_process = start_process(
                "backend",
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "main:app",
                    "--host",
                    args.host,
                    "--port",
                    str(args.backend_port),
                ],
                ROOT_DIR,
                env,
            )
            processes.append(("backend", backend_process))

        if port_is_open(args.host, args.frontend_port):
            print(f"Frontend port {args.frontend_port} is already in use. Reusing {frontend_url}.")
        else:
            if not args.dev and (args.build or not frontend_build_exists()):
                build_code = run_command(
                    "frontend production build",
                    [npm_command(), "run", "build"],
                    FRONTEND_DIR,
                    env,
                )
                if build_code != 0:
                    return build_code

            frontend_script = "dev" if args.dev else "start"
            frontend_process = start_process(
                "frontend",
                [
                    npm_command(),
                    "run",
                    frontend_script,
                    "--",
                    "--hostname",
                    args.host,
                    "--port",
                    str(args.frontend_port),
                ],
                FRONTEND_DIR,
                env,
            )
            processes.append(("frontend", frontend_process))

        backend_ready = wait_for_port("Backend", args.host, args.backend_port, args.backend_timeout)
        frontend_ready = wait_for_port("Frontend", args.host, args.frontend_port, args.frontend_timeout)

        if backend_ready:
            ok, message = request_url(f"{backend_url}/health", timeout=20)
            print(f"Backend health: {message}")
            if not ok:
                print("Backend is listening, but /health did not respond cleanly yet.")

        if frontend_ready:
            print()
            print("Project is running:")
            print(f"  Frontend:         {frontend_url}")
            print(f"  Employee AI Chat: {employee_chat_url}")
            print(f"  Company AI Chat:  {company_chat_url}")
            print(f"  Backend health:   {backend_url}/health")
            print()
            print("Keep this window open. Press Ctrl+C to stop services started by this script.")

            if not args.no_browser:
                try:
                    import webbrowser

                    webbrowser.open(frontend_url)
                except Exception:
                    pass

        while True:
            for name, process in processes:
                code = process.poll()
                if code is not None:
                    print(f"{name} exited with code {code}")
                    return code or 0
            time.sleep(1)

    except KeyboardInterrupt:
        print()
        print("Stopping local project...")
        return 0
    finally:
        for name, process in reversed(processes):
            stop_process(name, process)


if __name__ == "__main__":
    raise SystemExit(main())
