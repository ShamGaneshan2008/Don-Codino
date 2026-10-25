"""Clean wheel installation and actual loopback factory/asset smoke test."""

import argparse
import json
import os
import subprocess
import time
import urllib.request
import venv
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    target = args.destination.resolve()
    if target.exists():
        parser.error("Destination must be new; existing environments are never overwritten")
    target.mkdir(parents=True)
    venv.EnvBuilder(with_pip=True).create(target / "venv")
    python = target / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    installed = subprocess.run(  # noqa: S603 -- trusted built artifact, fresh explicitly named environment
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            str(args.wheel.resolve()),
        ],
        timeout=180,
        check=False,
    )
    if installed.returncode:
        return installed.returncode
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    env["DON_DATABASE"] = str(target / "smoke.sqlite3")
    env["DON_WORKSPACE_ROOT"] = str(target / "workspaces")
    launcher = (
        "import socket,uvicorn; s=socket.socket(); s.bind(('127.0.0.1',0)); "
        "print(s.getsockname()[1],flush=True); "
        "uvicorn.Server(uvicorn.Config('app.main:create_app',factory=True,"
        "host='127.0.0.1',log_level='warning')).run(sockets=[s])"
    )
    with (target / "server.log").open("wb") as log:
        process = subprocess.Popen(  # noqa: S603 -- fixed factory launch from freshly installed wheel
            [str(python), "-c", launcher],
            cwd=target,
            env=env,
            stdout=subprocess.PIPE,
            stderr=log,
            **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}),
        )
        try:
            port = int(process.stdout.readline().decode().strip())
            result = None
            for _ in range(50):
                try:
                    with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/health", timeout=1
                    ) as response:  # noqa: S310 -- fixed loopback HTTP
                        result = json.load(response)
                    break
                except OSError:
                    time.sleep(0.2)
            if result != {"status": "ok", "application": "Don Codino"}:
                raise ValueError("Installed factory health check failed")
            for route in ("/", "/static/app.js", "/openapi.json", "/api/workspaces"):
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}{route}", timeout=3
                ) as response:  # noqa: S310 -- fixed loopback HTTP
                    if response.status != 200:
                        raise ValueError(f"Installed asset/route failed: {route}")
            print(
                json.dumps(
                    {
                        "status": "PASS",
                        "factory": "app.main:create_app",
                        "health": result,
                        "assets": "HTTP 200",
                        "port": port,
                        "environment": str(target),
                    }
                )
            )
        finally:
            process.terminate()
            process.wait(timeout=15)
            process.stdout.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
