import os
import subprocess
import sys
from pathlib import Path


root = Path(__file__).resolve().parents[1]
logs = root / "storage" / "logs"
logs.mkdir(parents=True, exist_ok=True)

python = root / ".venv" / "Scripts" / "python.exe"
node = Path(
    r"C:\Users\talit\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
)
next_cli = root / "apps" / "web" / "node_modules" / "next" / "dist" / "bin" / "next"
flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS


def launch(
    name: str, command: list[str], cwd: Path, env: dict[str, str] | None = None
) -> int:
    output = (logs / f"{name}.log").open("ab")
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=output,
        stderr=subprocess.STDOUT,
        creationflags=flags,
        close_fds=True,
        env=env,
    )
    (logs / f"{name}.pid").write_text(str(process.pid), encoding="ascii")
    return process.pid


local_api_env = os.environ.copy()
local_api_env["PILOT_EDUCATION_ONLY"] = "false"
local_web_env = os.environ.copy()
local_web_env["NEXT_PUBLIC_PILOT_EDUCATION_ONLY"] = "false"

api_pid = launch(
    "api",
    [
        str(python),
        "-m",
        "uvicorn",
        "loa_api.main:app",
        "--app-dir",
        "apps/api",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
    ],
    root,
    local_api_env,
)
web_pid = launch(
    "web",
    [str(node), str(next_cli), "dev", "--hostname", "127.0.0.1", "--port", "3000"],
    root / "apps" / "web",
    local_web_env,
)
print(f"api={api_pid} web={web_pid}")
