#!/usr/local/bin/python3

"""Privilege-separated browser enrollment worker for os-usque."""

import json
import fcntl
import os
import pwd
import re
import stat
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

BINARY = Path("/usr/local/bin/usque-nativetun")
CONFIG_DIR = Path("/usr/local/etc/usque/instances")
MANIFEST = Path("/usr/local/etc/usque/instances.json")
RUN_DIR = Path("/var/run/usque")
ROLES = {"client", "mesh-node"}
STATE_DIR = Path("/var/run/usque/enrollment")
SPOOL_DIR = Path("/var/tmp")
JOB_RE = re.compile(r"^[0-9a-f]{32}$")
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
MAX_TOKEN_BYTES = 65536
MAX_SERVICE_TOKEN_BYTES = 8192
MAX_ACCESS_CLIENT_ID_BYTES = 512
MAX_ACCESS_CLIENT_SECRET_BYTES = 4096
TOKEN_TTL_SECONDS = 300
MAX_CONFIG_BYTES = 1048576
TEAM_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def validate_job_id(value: str) -> str:
    if not JOB_RE.fullmatch(value):
        raise ValueError("invalid enrollment job ID")
    return value


def validate_tunnel_id(value: str) -> str:
    value = value.lower()
    if not UUID_RE.fullmatch(value):
        raise ValueError("invalid tunnel UUID")
    return value


def validate_role(value: str) -> str:
    if value not in ROLES:
        raise ValueError("invalid tunnel role")
    return value


def inspect_registration(tunnel_id: str, role: str = "client", expected_owner: int = 0) -> dict:
    role = validate_role(role)
    label = "Mesh node" if role == "mesh-node" else "Client"
    tunnel_id = validate_tunnel_id(tunnel_id)
    path = CONFIG_DIR / f"{tunnel_id}.json"
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        return {
            "status": "ok",
            "registered": False,
            "can_register": True,
            "message": f"{label} is not registered.",
        }
    except OSError:
        return {
            "status": "blocked",
            "registered": False,
            "can_register": False,
            "message": "The registration configuration cannot be opened safely.",
        }

    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid != expected_owner
            or metadata.st_mode & 0o077
            or metadata.st_size < 2
            or metadata.st_size > MAX_CONFIG_BYTES
        ):
            raise PermissionError("registration configuration has unsafe metadata")
        raw = os.read(descriptor, MAX_CONFIG_BYTES + 1)
        if len(raw) != metadata.st_size:
            raise ValueError("registration configuration changed while reading")
        decoded = json.loads(raw)
        if not isinstance(decoded, dict) or decoded.get("role", "client") != role:
            raise ValueError("registration configuration role does not match the tunnel")
    except (OSError, ValueError):
        return {
            "status": "blocked",
            "registered": False,
            "can_register": False,
            "message": "A registration configuration exists but is invalid or unsafe.",
        }
    finally:
        os.close(descriptor)

    return {
        "status": "ok",
        "registered": True,
        "can_register": False,
        "message": f"{label} is already registered.",
    }


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


def claim_handoff(job_id: str, suffix: str, maximum_size: int, allowed_owners: set[int] | None = None) -> bytes:
    path = SPOOL_DIR / f"usque-enroll-{validate_job_id(job_id)}.{suffix}"
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
        if metadata.st_size < 1 or metadata.st_size > maximum_size:
            raise ValueError("enrollment handoff has an invalid size")
        if time.time() - metadata.st_mtime > TOKEN_TTL_SECONDS:
            raise ValueError("enrollment handoff has expired")
        payload = os.read(descriptor, maximum_size + 1)
        if len(payload) != metadata.st_size:
            raise ValueError("enrollment handoff changed while reading")
        return payload
    finally:
        os.close(descriptor)
        path.unlink(missing_ok=True)


def claim_browser_token(job_id: str, allowed_owners: set[int] | None = None) -> bytes:
    token = claim_handoff(job_id, "jwt", MAX_TOKEN_BYTES, allowed_owners)
    if any(byte in token for byte in (0, 10, 13)):
        raise ValueError("enrollment token must contain exactly one non-empty line")
    return token


def validate_service_token_fields(payload: object) -> dict[str, str]:
    expected = {"organization", "auth_client_id", "auth_client_secret"}
    if not isinstance(payload, dict) or set(payload) != expected:
        raise ValueError("service-token handoff has invalid fields")
    values = {}
    for field in expected:
        value = payload.get(field)
        if not isinstance(value, str) or not value:
            raise ValueError("service-token handoff contains an invalid value")
        if any(ord(character) in (0, 10, 13) for character in value):
            raise ValueError("service-token values must each contain exactly one line")
        values[field] = value
    organization = values["organization"].lower()
    if not TEAM_RE.fullmatch(organization):
        raise ValueError("service-token organization is not a valid team name")
    if len(values["auth_client_id"].encode()) > MAX_ACCESS_CLIENT_ID_BYTES:
        raise ValueError("service-token Client ID is too long")
    if not values["auth_client_id"].endswith(".access"):
        raise ValueError("service-token Client ID must end with .access")
    if len(values["auth_client_secret"].encode()) > MAX_ACCESS_CLIENT_SECRET_BYTES:
        raise ValueError("service-token Client Secret is too long")
    values["organization"] = organization
    return values


def claim_service_token(job_id: str, allowed_owners: set[int] | None = None) -> dict[str, str]:
    raw = claim_handoff(job_id, "service-token", MAX_SERVICE_TOKEN_BYTES, allowed_owners)
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("service-token handoff is not valid UTF-8 JSON") from error
    finally:
        del raw
    return validate_service_token_fields(decoded)


def root_private_file(payload: bytes, prefix: str) -> Path:
    ensure_private_directory(STATE_DIR)
    descriptor, name = tempfile.mkstemp(prefix=prefix, dir=STATE_DIR)
    try:
        os.fchmod(descriptor, 0o600)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written == 0:
                raise OSError("short write while securing enrollment data")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return Path(name)


def root_token_file(token: bytes) -> Path:
    return root_private_file(token, ".jwt-")


def root_mdm_file(fields: dict[str, str]) -> Path:
    root = ET.Element("dict")
    for name in ("organization", "auth_client_id", "auth_client_secret"):
        ET.SubElement(root, "key").text = name
        ET.SubElement(root, "string").text = fields[name]
    return root_private_file(ET.tostring(root, encoding="utf-8"), ".mdm-")


def register(job_id: str, tunnel_id: str, role: str) -> int:
    job_id = validate_job_id(job_id)
    tunnel_id = validate_tunnel_id(tunnel_id)
    write_state(job_id, "claiming_token", "Claiming one-time enrollment token.", tunnel_id)
    role = validate_role(role)
    private_token = None
    try:
        token = claim_browser_token(job_id)
        private_token = root_token_file(token)
        del token

        ensure_private_directory(CONFIG_DIR)
        config_path = CONFIG_DIR / f"{tunnel_id}.json"
        if config_path.exists():
            raise FileExistsError("a registration configuration already exists for this tunnel")

        write_state(
            job_id,
            "registering",
            "Registering device and enrolling its MASQUE key.",
            tunnel_id,
        )
        command = [str(BINARY), "--config", str(config_path)]
        if role == "mesh-node":
            command.extend([
                "mesh-register",
                "--token-file",
                str(private_token),
                "--accept-tos",
                "--acknowledge-linux-platform-claim",
            ])
        else:
            command.extend([
                "register", "--jwt-file", str(private_token), "--accept-tos",
            ])
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
        if decoded.get("role", "client") != role:
            raise RuntimeError("registration produced a configuration with the wrong role")
        write_state(job_id, "completed", "Tunnel registration completed.", tunnel_id)
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


def register_service_token(job_id: str, tunnel_id: str) -> int:
    job_id = validate_job_id(job_id)
    tunnel_id = validate_tunnel_id(tunnel_id)
    write_state(job_id, "claiming_token", "Claiming one-time Cloudflare Access service-token parameters.", tunnel_id)
    private_mdm = None
    try:
        fields = claim_service_token(job_id)
        private_mdm = root_mdm_file(fields)
        for field in fields:
            fields[field] = ""
        del fields
        ensure_private_directory(CONFIG_DIR)
        config_path = CONFIG_DIR / f"{tunnel_id}.json"
        if config_path.exists():
            raise FileExistsError("a registration configuration already exists for this tunnel")
        write_state(job_id, "registering", "Registering device through Cloudflare Access Service Auth.", tunnel_id)
        command = [str(BINARY), "--config", str(config_path), "register", "--mdm-file", str(private_mdm), "--accept-tos"]
        result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120, check=False, env={**os.environ, "RUST_LOG": "info"})
        if result.returncode != 0:
            diagnostic = result.stdout.strip()[-3000:]
            raise RuntimeError(diagnostic or f"registration exited with status {result.returncode}")
        os.chmod(config_path, 0o600)
        decoded = json.loads(config_path.read_text(encoding="utf-8"))
        if decoded.get("role", "client") != "client":
            raise RuntimeError("registration produced a configuration with the wrong role")
        write_state(job_id, "completed", "Tunnel registration completed.", tunnel_id)
        return 0
    except Exception as error:
        write_state(job_id, "failed", str(error), tunnel_id)
        return 1
    finally:
        if private_mdm is not None:
            private_mdm.unlink(missing_ok=True)


def runtime_is_disabled(expected_owner: int = 0) -> tuple[bool, str]:
    try:
        flags = os.O_RDONLY | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(MANIFEST, flags)
    except FileNotFoundError:
        descriptor = None
    except OSError:
        return False, "The generated service manifest cannot be opened safely."

    if descriptor is not None:
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_nlink != 1
                or metadata.st_uid != expected_owner
                or metadata.st_size < 2
                or metadata.st_size > MAX_CONFIG_BYTES
            ):
                return False, "The generated service manifest has unsafe metadata."
            raw = os.read(descriptor, MAX_CONFIG_BYTES + 1)
            manifest = json.loads(raw)
            if not isinstance(manifest, dict) or manifest.get("enabled", False):
                return False, "Disable and apply the usque service before deleting a tunnel."
        except (OSError, ValueError):
            return False, "The generated service manifest is invalid."
        finally:
            os.close(descriptor)

    for path in RUN_DIR.glob("*.pid"):
        try:
            pid = int(path.read_text(encoding="ascii").strip())
            os.kill(pid, 0)
            return False, "A managed usque process is still running."
        except (FileNotFoundError, ValueError, ProcessLookupError):
            continue
        except PermissionError:
            return False, "A managed usque process could not be verified as stopped."
    if next(RUN_DIR.glob("*.state.json"), None) is not None:
        return False, "A managed TUN interface still has runtime ownership state."
    return True, ""


def delete_registration(tunnel_id: str, role: str, expected_owner: int = 0) -> int:
    tunnel_id = validate_tunnel_id(tunnel_id)
    role = validate_role(role)
    RUN_DIR.mkdir(mode=0o755, parents=True, exist_ok=True)
    lock_path = RUN_DIR / "service.lock"
    with lock_path.open("a+", encoding="ascii") as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        disabled, message = runtime_is_disabled(expected_owner)
        if not disabled:
            print(json.dumps({"status": "blocked", "message": message}, separators=(",", ":")))
            return 1

        path = CONFIG_DIR / f"{tunnel_id}.json"
        flags = os.O_RDONLY | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags)
        except FileNotFoundError:
            print(json.dumps({"status": "ok", "removed": False}, separators=(",", ":")))
            return 0
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_nlink != 1
                or metadata.st_uid != expected_owner
                or metadata.st_mode & 0o077
                or metadata.st_size < 2
                or metadata.st_size > MAX_CONFIG_BYTES
            ):
                raise PermissionError("registration configuration has unsafe metadata")
            raw = os.read(descriptor, MAX_CONFIG_BYTES + 1)
            decoded = json.loads(raw)
            if not isinstance(decoded, dict) or decoded.get("role", "client") != role:
                raise ValueError("registration configuration role does not match the tunnel")
            current = path.stat(follow_symlinks=False)
            if current.st_dev != metadata.st_dev or current.st_ino != metadata.st_ino:
                raise PermissionError("registration configuration changed before deletion")
            path.unlink()
        finally:
            os.close(descriptor)
        print(json.dumps({"status": "ok", "removed": True}, separators=(",", ":")))
        return 0


def status(job_id: str) -> int:
    job_id = validate_job_id(job_id)
    path = STATE_DIR / f"{job_id}.json"
    if not path.is_file():
        print(json.dumps({"state": "waiting", "message": "Enrollment job has not reported yet."}))
        return 0
    print(path.read_text(encoding="utf-8"))
    return 0


def registration_status(tunnel_id: str, role: str) -> int:
    print(json.dumps(inspect_registration(tunnel_id, role), separators=(",", ":")))
    return 0


def main(argv: list[str]) -> int:
    if os.geteuid() != 0:
        print("usque enrollment worker must run as root", file=sys.stderr)
        return 77
    if len(argv) == 4 and argv[1] == "register-client":
        return register(argv[2], argv[3], "client")
    if len(argv) == 4 and argv[1] == "register-mesh":
        return register(argv[2], argv[3], "mesh-node")
    if len(argv) == 4 and argv[1] == "register-client-service-token":
        return register_service_token(argv[2], argv[3])
    if len(argv) == 3 and argv[1] == "status":
        return status(argv[2])
    if len(argv) == 4 and argv[1] == "registration-status":
        return registration_status(argv[2], argv[3])
    if len(argv) == 4 and argv[1] == "delete-registration":
        return delete_registration(argv[2], argv[3])
    print(
        "usage: enrollment.py register-client|register-client-service-token|register-mesh "
        "JOB_ID TUNNEL_UUID | "
        "status JOB_ID | registration-status|delete-registration TUNNEL_UUID ROLE",
        file=sys.stderr,
    )
    return 64


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
