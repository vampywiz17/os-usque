import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "src/opnsense/scripts/OPNsense/Usque/service.py"
)
SPEC = importlib.util.spec_from_file_location("usque_service", SCRIPT)
service = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(service)


class ServiceLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        service.RUN_DIR = root / "run"
        service.LOG_DIR = root / "log"
        service.CONFIG_DIR = root / "config"
        service.MANIFEST = root / "instances.json"
        service.RUN_DIR.mkdir()
        service.LOG_DIR.mkdir()
        service.CONFIG_DIR.mkdir()
        self.tunnel_id = "12345678-1234-4234-8234-123456789abc"
        self.instance = {
            "id": self.tunnel_id,
            "interface": "tun0",
            "role": "client",
            "config": service.CONFIG_DIR / f"{self.tunnel_id}.json",
        }

    def tearDown(self):
        self.temporary.cleanup()

    def test_manifest_role_and_interface_are_validated(self):
        manifest = {
            "enabled": True,
            "instances": [{
                "id": self.tunnel_id,
                "enabled": True,
                "interface": "tun0",
                "role": "client",
            }],
        }

        def fake_secure(path, maximum, private):
            return {"role": "client"} if private else manifest

        with patch.object(service, "secure_json", side_effect=fake_secure):
            loaded = service.load_instances()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["interface"], "tun0")

    def test_unregistered_instance_does_not_block_registered_instances(self):
        second_id = "22345678-1234-4234-8234-123456789abc"
        manifest = {
            "enabled": True,
            "instances": [
                {"id": self.tunnel_id, "enabled": True, "interface": "tun0", "role": "client"},
                {"id": second_id, "enabled": True, "interface": "tun1", "role": "mesh-node"},
            ],
        }

        def fake_secure(path, maximum, private):
            if not private:
                return manifest
            if path.name.startswith(second_id):
                raise FileNotFoundError(path)
            return {"role": "client"}

        with patch.object(service, "secure_json", side_effect=fake_secure):
            loaded = service.load_instances()
        self.assertEqual([item["interface"] for item in loaded], ["tun0"])

    def test_start_uses_freebsd_daemon_supervision(self):
        completed = SimpleNamespace(returncode=0, stdout="", stderr="")
        with patch.object(service, "read_pid", side_effect=[None, 101, 202]), \
                patch.object(service, "interface_exists", side_effect=[False, True]), \
                patch.object(service.subprocess, "run", return_value=completed) as run:
            message = service.start(self.instance)
        command = run.call_args.args[0]
        self.assertEqual(command[0], "/usr/sbin/daemon")
        self.assertIn("-P", command)
        self.assertIn("-p", command)
        self.assertIn("--always-reconnect", command)
        self.assertEqual(message, "tun0: started")

    def test_start_rejects_unmanaged_existing_interface(self):
        with patch.object(service, "read_pid", return_value=None), \
                patch.object(service, "interface_exists", return_value=True), \
                patch.object(service.subprocess, "run") as run:
            with self.assertRaisesRegex(RuntimeError, "outside plugin control"):
                service.start(self.instance)
        run.assert_not_called()

    def test_read_pid_rejects_unrelated_process(self):
        pidfile = service.RUN_DIR / "test.pid"
        pidfile.write_text("123", encoding="ascii")
        completed = SimpleNamespace(returncode=0, stdout="/usr/sbin/daemon unrelated", stderr="")
        with patch.object(service.os, "kill"), \
                patch.object(service.subprocess, "run", return_value=completed):
            self.assertIsNone(service.read_pid(pidfile, "/expected/pidfile"))


    def test_read_pid_accepts_process_holding_expected_pidfile(self):
        pidfile = service.RUN_DIR / "test.supervisor.pid"
        pidfile.write_text("321", encoding="ascii")
        completed = SimpleNamespace(returncode=0, stdout=f"321 daemon 6 {pidfile}\n", stderr="")
        with patch.object(service.os, "kill"), \
                patch.object(service.subprocess, "run", return_value=completed) as run:
            self.assertEqual(service.read_pid(pidfile, str(pidfile)), 321)
        self.assertEqual(run.call_args.args[0][0:2], ["/usr/bin/procstat", "-f"])

    def test_cleanup_destroys_only_interface_recorded_in_private_state(self):
        completed = SimpleNamespace(returncode=0, stdout="", stderr="")
        with patch.object(service, "read_interface_state", return_value="tun7"), \
                patch.object(service, "interface_exists", side_effect=[True, False]), \
                patch.object(service.subprocess, "run", return_value=completed) as run, \
                patch.object(service.time, "sleep"):
            self.assertTrue(service.cleanup_interface(self.tunnel_id))
        run.assert_called_once_with(
            ["/sbin/ifconfig", "tun7", "destroy"],
            stdout=service.subprocess.DEVNULL,
            stderr=service.subprocess.DEVNULL,
            check=False,
        )

    def test_cleanup_without_owned_state_never_destroys_an_interface(self):
        with patch.object(service, "read_interface_state", return_value=None), \
                patch.object(service.subprocess, "run") as run:
            self.assertFalse(service.cleanup_interface(self.tunnel_id))
        run.assert_not_called()

    def test_recover_state_from_validated_running_child_for_upgrade(self):
        child = service.RUN_DIR / f"{self.tunnel_id}.child.pid"
        completed = SimpleNamespace(
            returncode=0,
            stdout=(
                "/usr/local/bin/usque-nativetun nativetun "
                "--config /tmp/config.json --interface-name tun4 --always-reconnect\n"
            ),
            stderr="",
        )
        with patch.object(service, "read_interface_state", return_value=None), \
                patch.object(service, "read_pid", return_value=202), \
                patch.object(service.subprocess, "run", return_value=completed), \
                patch.object(service, "write_interface_state") as write:
            service.recover_interface_state(self.tunnel_id, child)
        write.assert_called_once_with(self.tunnel_id, "tun4")

    def test_stop_cleans_owned_stale_interface_when_process_is_absent(self):
        with patch.object(service, "recover_interface_state"), \
                patch.object(service, "read_pid", return_value=None), \
                patch.object(service, "cleanup_interface", return_value=True) as cleanup:
            message = service.stop_id(self.tunnel_id)
        cleanup.assert_called_once_with(self.tunnel_id)
        self.assertEqual(message, f"{self.tunnel_id}: stopped")

    def test_known_ids_include_owned_interface_state(self):
        (service.RUN_DIR / f"{self.tunnel_id}.state.json").write_text(
            '{"interface":"tun0"}', encoding="ascii"
        )
        (service.RUN_DIR / "not-a-uuid.state.json").write_text(
            '{"interface":"tun1"}', encoding="ascii"
        )
        self.assertEqual(service.known_ids(), {self.tunnel_id})

    def test_stop_does_not_depend_on_runtime_manifest(self):
        with patch.object(service.os, "geteuid", return_value=0), \
                patch.object(service, "known_ids", return_value={self.tunnel_id}), \
                patch.object(service, "stop_id", return_value="stopped") as stop, \
                patch.object(service, "load_instances") as load, \
                patch("builtins.print"):
            self.assertEqual(service.main(["service.py", "stop"]), 0)
        stop.assert_called_once_with(self.tunnel_id)
        load.assert_not_called()


if __name__ == "__main__":
    unittest.main()
