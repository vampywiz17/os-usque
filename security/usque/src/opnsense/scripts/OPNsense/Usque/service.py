#!/usr/local/bin/python3

"""Manage independent usque tunnel processes using FreeBSD daemon(8)."""

import json
import os
import re
import shlex
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

BINARY = Path("/usr/local/bin/usque-nativetun")
DAEMON = Path("/usr/sbin/daemon")
MANIFEST = Path("/usr/local/etc/usque/instances.json")
CONFIG_DIR = Path("/usr/local/etc/usque/instances")
RUN_DIR = Path("/var/run/usque")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
INTERFACE_RE = re.compile(r"^tun[0-9]{1,3}$")


def secure_json(path: Path, maximum: int, require_private: bool) -> dict:
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_uid != 0:
            raise PermissionError(f"unsafe metadata for {path}")
        if require_private and metadata.st_mode & 0o077:
            raise PermissionError(f"private configuration {path} is accessible by other users")
        if metadata.st_size < 2 or metadata.st_size > maximum:
            raise ValueError(f"invalid size for {path}")
        raw = os.read(descriptor, maximum + 1)
        if len(raw) != metadata.st_size:
            raise ValueError(f"{path} changed while reading")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError(f"{path} must contain a JSON object")
        return value
    finally:
        os.close(descriptor)


def load_instances() -> list[dict]:
    manifest = secure_json(MANIFEST, 1048576, False)
    if not manifest.get("enabled", False):
        return []
    result = []
    seen_interfaces = set()
    for item in manifest.get("instances", []):
        if not isinstance(item, dict) or not item.get("enabled", False):
            continue
        tunnel_id = str(item.get("id", "")).lower()
        interface = str(item.get("interface", ""))
        role = str(item.get("role", ""))
        if not UUID_RE.fullmatch(tunnel_id) or not INTERFACE_RE.fullmatch(interface):
            raise ValueError("manifest contains an invalid tunnel identity or interface")
        if role not in {"client", "mesh-node"}:
            raise ValueError("manifest contains an invalid tunnel role")
        if interface in seen_interfaces:
            raise ValueError(f"duplicate TUN interface: {interface}")
        seen_interfaces.add(interface)
        config = CONFIG_DIR / f"{tunnel_id}.json"
        try:
            registered = secure_json(config, 1048576, True)
        except (FileNotFoundError, PermissionError, ValueError, OSError) as error:
            print(f"{interface}: skipped: {error}", file=sys.stderr)
            continue
        if registered.get("role", "client") != role:
            raise ValueError(f"role mismatch in {config}")
        result.append({"id": tunnel_id, "interface": interface, "role": role, "config": config})
    return result


def paths(tunnel_id: str) -> tuple[Path, Path]:
    return (
        RUN_DIR / f"{tunnel_id}.supervisor.pid",
        RUN_DIR / f"{tunnel_id}.child.pid",
    )


def read_pid(path: Path, marker: str) -> int | None:
    try:
        value = int(path.read_text(encoding="ascii").strip())
        os.kill(value, 0)
        command = (["/usr/bin/procstat", "-f", str(value)] if marker.endswith(".pid") else
                   ["/bin/ps", "-ww", "-o", "command=", "-p", str(value)])
        process = subprocess.run(
            command,
            capture_output=True, text=True, check=False,
        )
        if process.returncode != 0 or marker not in process.stdout:
            return None
        return value
    except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
        return None


def interface_exists(name: str) -> bool:
    return subprocess.run(
        ["/sbin/ifconfig", name], stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, check=False,
    ).returncode == 0
def state_path(tunnel_id: str) -> Path:
    if not UUID_RE.fullmatch(tunnel_id):
        raise ValueError("invalid tunnel UUID")
    return RUN_DIR / f"{tunnel_id}.state.json"


def read_interface_state(tunnel_id: str) -> str | None:
    try:
        state = secure_json(state_path(tunnel_id), 1024, True)
    except (FileNotFoundError, PermissionError, ValueError, OSError):
        return None
    interface = str(state.get("interface", ""))
    return interface if INTERFACE_RE.fullmatch(interface) else None


def write_interface_state(tunnel_id: str, interface: str) -> None:
    if not INTERFACE_RE.fullmatch(interface):
        raise ValueError("invalid managed TUN interface")
    destination = state_path(tunnel_id)
    temporary = RUN_DIR / f".{tunnel_id}.{os.getpid()}.tmp"
    payload = json.dumps({"interface": interface}, separators=(",", ":")).encode()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    try:
        descriptor = os.open(temporary, flags, 0o600)
        try:
            view = memoryview(payload)
            while view:
                written = os.write(descriptor, view)
                if written == 0:
                    raise OSError("short write while recording managed interface")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def recover_interface_state(tunnel_id: str, child: Path) -> None:
    if read_interface_state(tunnel_id) is not None:
        return
    child_pid = read_pid(child, str(BINARY))
    if child_pid is None:
        return
    process = subprocess.run(
        ["/bin/ps", "-ww", "-o", "command=", "-p", str(child_pid)],
        capture_output=True, text=True, check=False,
    )
    if process.returncode != 0:
        return
    try:
        arguments = shlex.split(process.stdout.strip())
        position = arguments.index("--interface-name")
        interface = arguments[position + 1]
    except (ValueError, IndexError):
        return
    if INTERFACE_RE.fullmatch(interface):
        write_interface_state(tunnel_id, interface)


def cleanup_interface(tunnel_id: str) -> bool:
    interface = read_interface_state(tunnel_id)
    if interface is None:
        return False
    for _ in range(20):
        if not interface_exists(interface):
            state_path(tunnel_id).unlink(missing_ok=True)
            return True
        subprocess.run(
            ["/sbin/ifconfig", interface, "destroy"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
        time.sleep(0.1)
    raise RuntimeError(f"{interface}: managed interface could not be destroyed")



def start(instance: dict) -> str:
    supervisor, child = paths(instance["id"])
    if read_pid(supervisor, str(supervisor)) is not None:
        return f'{instance["interface"]}: already running'
    if interface_exists(instance["interface"]):
        raise RuntimeError(f'{instance["interface"]}: interface already exists outside plugin control')
    supervisor.unlink(missing_ok=True)
    child.unlink(missing_ok=True)
    write_interface_state(instance["id"], instance["interface"])
    command = [
        str(DAEMON), "-c", "-f", "-r", "-R", "5", "-S", "-l", "daemon", "-s", "info",
        "-P", str(supervisor), "-p", str(child),
        "-T", f'usque-{instance["interface"]}', str(BINARY), "nativetun",
        "--config", str(instance["config"]), "--interface-name", instance["interface"],
        "--always-reconnect",
    ]
    result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        cleanup_interface(instance["id"])
        raise RuntimeError(f'{instance["interface"]}: daemon start failed: {detail or result.returncode}')
    for _ in range(100):
        if read_pid(supervisor, str(supervisor)) is not None and \
                read_pid(child, str(BINARY)) is not None and interface_exists(instance["interface"]):
            return f'{instance["interface"]}: started'
        time.sleep(0.1)
    stop_id(instance["id"])
    raise RuntimeError(f'{instance["interface"]}: tunnel did not become ready within 10 seconds')


def stop_id(tunnel_id: str) -> str:
    supervisor, child = paths(tunnel_id)
    recover_interface_state(tunnel_id, child)
    pid = read_pid(supervisor, str(supervisor))
    if pid is None:
        if read_pid(child, str(BINARY)) is not None:
            raise RuntimeError(f"{tunnel_id}: child is running without a validated supervisor")
        supervisor.unlink(missing_ok=True)
        cleaned = cleanup_interface(tunnel_id)
        return f"{tunnel_id}: stopped" if cleaned else f"{tunnel_id}: not running"
    os.kill(pid, signal.SIGTERM)
    for _ in range(100):
        if read_pid(supervisor, str(supervisor)) is None and read_pid(child, str(BINARY)) is None:
            cleanup_interface(tunnel_id)
            return f"{tunnel_id}: stopped"
        time.sleep(0.1)
    raise RuntimeError(f"{tunnel_id}: did not stop within 10 seconds")


def known_ids() -> set[str]:
    result = {path.name.removesuffix(".supervisor.pid") for path in RUN_DIR.glob("*.supervisor.pid")}
    result.update(
        path.name.removesuffix(".state.json")
        for path in RUN_DIR.glob("*.state.json")
    )
    return {tunnel_id for tunnel_id in result if UUID_RE.fullmatch(tunnel_id)}


def status(instances: list[dict]) -> int:
    values = []
    for instance in instances:
        supervisor, child = paths(instance["id"])
        values.append({
            "id": instance["id"],
            "interface": instance["interface"],
            "role": instance["role"],
            "running": read_pid(supervisor, str(supervisor)) is not None,
            "pid": read_pid(child, str(BINARY)),
        })
    print(json.dumps({"status": "ok", "instances": values}, separators=(",", ":")))
    return 0


def main(argv: list[str]) -> int:
    if os.geteuid() != 0:
        print("usque service manager must run as root", file=sys.stderr)
        return 77
    if len(argv) != 2 or argv[1] not in {"start", "stop", "restart", "status"}:
        print("usage: service.py start|stop|restart|status", file=sys.stderr)
        return 64
    RUN_DIR.mkdir(mode=0o755, parents=True, exist_ok=True)
    messages = []
    if argv[1] in {"stop", "restart"}:
        for tunnel_id in sorted(known_ids()):
            messages.append(stop_id(tunnel_id))
        if argv[1] == "stop":
            print("\n".join(messages))
            return 0
    instances = load_instances()
    desired = {item["id"] for item in instances}
    if argv[1] == "status":
        return status(instances)
    for tunnel_id in sorted(known_ids() - desired):
        messages.append(stop_id(tunnel_id))
    for instance in instances:
        messages.append(start(instance))
    print("\n".join(messages))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except Exception as error:
        print(f"usque service error: {error}", file=sys.stderr)
        raise SystemExit(1)
