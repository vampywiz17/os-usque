import importlib.util
import os
import stat
import tempfile
import unittest
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "src/opnsense/scripts/OPNsense/Usque/enrollment.py"
)
SPEC = importlib.util.spec_from_file_location("usque_enrollment", SCRIPT)
enrollment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(enrollment)


class EnrollmentSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.spool = root / "spool"
        self.state = root / "state"
        self.config = root / "config"
        self.spool.mkdir()
        enrollment.SPOOL_DIR = self.spool
        enrollment.STATE_DIR = self.state
        enrollment.CONFIG_DIR = self.config

    def tearDown(self):
        self.temporary.cleanup()

    def token_path(self, job_id):
        return self.spool / f"usque-enroll-{job_id}.jwt"

    def test_claim_is_owner_only_one_use_and_never_logs_token(self):
        job_id = "a" * 32
        token = b"header.payload.signature"
        path = self.token_path(job_id)
        path.write_bytes(token)
        path.chmod(0o600)

        claimed = enrollment.claim_browser_token(job_id, {os.getuid()})
        self.assertEqual(claimed, token)
        self.assertFalse(path.exists())

    def test_claim_rejects_group_readable_handoff(self):
        job_id = "b" * 32
        path = self.token_path(job_id)
        path.write_bytes(b"header.payload.signature")
        path.chmod(0o640)

        with self.assertRaises(PermissionError):
            enrollment.claim_browser_token(job_id, {os.getuid()})
        self.assertFalse(path.exists())

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "O_NOFOLLOW is unavailable")
    def test_claim_rejects_symlink_handoff(self):
        job_id = "c" * 32
        target = self.spool / "target.jwt"
        target.write_bytes(b"header.payload.signature")
        target.chmod(0o600)
        path = self.token_path(job_id)
        path.symlink_to(target)

        with self.assertRaises(OSError):
            enrollment.claim_browser_token(job_id, {os.getuid()})
        self.assertTrue(target.exists())

    def test_root_token_file_is_mode_0600(self):
        path = enrollment.root_token_file(b"header.payload.signature")
        try:
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        finally:
            path.unlink()

    def test_identifiers_are_strict(self):
        self.assertEqual(enrollment.validate_job_id("d" * 32), "d" * 32)
        self.assertEqual(
            enrollment.validate_tunnel_id("12345678-1234-4234-8234-123456789abc"),
            "12345678-1234-4234-8234-123456789abc",
        )
        with self.assertRaises(ValueError):
            enrollment.validate_job_id("../token")
        with self.assertRaises(ValueError):
            enrollment.validate_tunnel_id("../../etc/passwd")


if __name__ == "__main__":
    unittest.main()
