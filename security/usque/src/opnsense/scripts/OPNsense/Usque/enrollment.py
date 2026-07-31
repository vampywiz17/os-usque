#!/usr/local/bin/python3

"""Privilege-separated browser enrollment worker for os-usque."""

import json
import os
import pwd
import re
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

BINARY = Path("/usr/local/bin/usque-nativetun")
CONFIG_DIR = Path("/usr/local/etc/usque/instances")
STATE_DIR = Path("/var/run/usque/enrollment")
SPOOL_DIR = Path("/var/tmp")
JOB_RE = re.compile(r"^[0-9a-f]{32}$")
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
MAX_TOKEN_BYTES = 65536
TOKEN_TTL_SECONDS = 300


def validate_job_id(value: str) -> str:
    if not JOB_RE.fullmatch(value):
        raise ValueError("invalid enrollment job ID")
    return value


def validate_tunnel_id(value: str) -> str:
    value = value.lower()
    if not UUID_RE.fullmatch(value):
        raise ValueError("invalid tunnel UUID")
    return value


def ensure_private_directory(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)


def write_state(job_id: str, state: str, message: str, tunnel_id: str = "") -> None:
    ensure_private_directory(STATE_DIR)
    payload = {
        "state": state,
        "message": message[:4096],
        "tunnel_id": tunnel_id,
        "updated_at": int(time.time()),
    }
    temporary = STATE_DIR / f".{job_id}.{os.getpid()}.tmp"
    temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, STATE_DIR / f"{job_id}.json")


def allowed_spool_owners() -> set[int]:
    owners = {0}
    try:
        owners.add(pwd.getpwnam("www").pw_uid)
    except KeyError:
        pass
    return owners


def claim_browser_token(job_id: str, allowed_owners: set[int] | None = None) -> bytes:
    path = SPOOL_DIR / f"usque-enroll-{validate_job_id(job_id)}.jwt"
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    try:
        descriptor = os.open(path, flags)
    except OSError:
        path.unlink(missing_ok=True)
        raise

    try:
        metadata = os.fstat(descriptor)
        owners = allowed_spool_owners() if allowed_owners is None else allowed_owners
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise PermissionError("enrollment handoff is not a single regular file")
        if metadata.st_uid not in owners or metadata.st_mode & 0o077:
            raise PermissionError("enrollment handoff has unsafe ownership or permissions")
        if metadata.st_size < 1 or metadata.st_size > MAX_TOKEN_BYTES:
            raise ValueError("enrollment handoff has an invalid size")
        if time.time() - metadata.st_mtime > TOKEN_TTL_SECONDS:
            raise ValueError("enrollment handoff has expired")
        token = os.read(descriptor, MAX_TOKEN_BYTES + 1)
        if len(token) != metadata.st_size or any(byte in token for byte in (0, 10, 13)):
            raise ValueError("enrollment token must contain exactly one non-empty line")
        return token
    finally:
        os.close(descriptor)
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def root_token_file(token: bytes) -> Path:
    ensure_private_directory(STATE_DIR)
    descriptor, name = tempfile.mkstemp(prefix=".jwt-", dir=STATE_DIR)
    try:
        os.fchmod(descriptor, 0o600)
        view = memoryview(token)
        while view:
            written = os.write(descriptor, view)
            if written == 0:
                raise OSError("short write while securing enrollment token")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return Path(name)


def register(job_id: str, tunnel_id: str) -> int:
    job_id = validate_job_id(job_id)
    tunnel_id = validate_tunnel_id(tunnel_id)
    write_state(job_id, "claiming_token", "Claiming one-time enrollment token.", tunnel_id)
    private_token = None
    try:
        token = claim_browser_token(job_id)
        private_token = root_token_file(token)
        del token

        ensure_private_directory(CONFIG_DIR)
        config_path = CONFIG_DIR / f"{tunnel_id}.json"
        if config_path.exists():
            raise FileExistsError("a registration configuration already exists for this tunnel")

        write_state(job_id, "registering", "Registering device and enrolling its MASQUE key.", tunnel_id)
        command = [
            str(BINARY),
            "--config",
            str(config_path),
            "register",
            "--jwt-file",
            str(private_token),
            "--accept-tos",
        ]
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=120,
            check=False,
            env={**os.environ, "RUST_LOG": "info"},
        )
        if result.returncode != 0:
            diagnostic = result.stdout.strip()[-3000:]
            raise RuntimeError(diagnostic or f"registration exited with status {result.returncode}")

        os.chmod(config_path, 0o600)
        decoded = json.loads(config_path.read_text(encoding="utf-8"))
        if decoded.get("role", "client") != "client":
            raise RuntimeError("registration produced a non-client configuration")
        write_state(job_id, "completed", "Client registration completed.", tunnel_id)
        return 0
    except Exception as error:
        write_state(job_id, "failed", str(error), tunnel_id)
        return 1
    finally:
        if private_token is not None:
            try:
                private_token.unlink()
            except FileNotFoundError:
                pass


def status(job_id: str) -> int:
    job_id = validate_job_id(job_id)
    path = STATE_DIR / f"{job_id}.json"
    if not path.is_file():
        print(json.dumps({"state": "waiting", "message": "Enrollment job has not reported yet."}))
        return 0
    print(path.read_text(encoding="utf-8"))
    return 0


def main(argv: list[str]) -> int:
    if os.geteuid() != 0:
        print("usque enrollment worker must run as root", file=sys.stderr)
        return 77
    if len(argv) == 4 and argv[1] == "register":
        return register(argv[2], argv[3])
    if len(argv) == 3 and argv[1] == "status":
        return status(argv[2])
    print("usage: enrollment.py register JOB_ID TUNNEL_UUID | status JOB_ID", file=sys.stderr)
    return 64


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
