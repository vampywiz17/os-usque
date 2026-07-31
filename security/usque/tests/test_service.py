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

    def test_start_uses_mesh_node_subcommand_without_redundant_reconnect_flag(self):
        instance = dict(self.instance)
        instance["role"] = "mesh-node"
        instance["interface"] = "tun1"
        completed = SimpleNamespace(returncode=0, stdout="", stderr="")
        with patch.object(service, "read_pid", side_effect=[None, 101, 202]), \
                patch.object(service, "interface_exists", side_effect=[False, True]), \
                patch.object(service.subprocess, "run", return_value=completed) as run:
            message = service.start(instance)

        command = next(
            call.args[0] for call in run.call_args_list if call.args[0][0] == str(service.DAEMON)
        )
        binary_index = command.index(str(service.BINARY))
        self.assertEqual(command[binary_index + 1], "mesh-node")
        self.assertNotIn("nativetun", command[binary_index + 1:])
        self.assertNotIn("--always-reconnect", command)
        self.assertIn("--interface-name", command)
        self.assertEqual(message, "tun1: started")


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


    def test_mesh_start_installs_mesh_routes_after_tun_is_ready(self):
        instance = dict(self.instance)
        instance["role"] = "mesh-node"
        instance["interface"] = "tun1"
        completed = SimpleNamespace(returncode=0, stdout="", stderr="")
        with patch.object(service, "read_pid", side_effect=[None, 101, 202]),                 patch.object(service, "interface_exists", side_effect=[False, True]),                 patch.object(service.subprocess, "run", return_value=completed),                 patch.object(service, "install_mesh_return_routes") as install:
            service.start(instance)
        install.assert_called_once_with(instance)

    def test_client_start_does_not_change_mesh_routes(self):
        completed = SimpleNamespace(returncode=0, stdout="", stderr="")
        with patch.object(service, "read_pid", side_effect=[None, 101, 202]),                 patch.object(service, "interface_exists", side_effect=[False, True]),                 patch.object(service.subprocess, "run", return_value=completed),                 patch.object(service, "install_mesh_return_routes") as install:
            service.start(self.instance)
        install.assert_called_once_with(self.instance)
        self.assertEqual(install.call_args.args[0]["role"], "client")

    def test_mesh_routes_use_native_freebsd_interface_routes(self):
        self.assertEqual(
            service.route_command("add", "inet", "100.96.0.0/12", "tun1"),
            ["/sbin/route", "-n", "-4", "add", "-net", "100.96.0.0/12", "-interface", "tun1"],
        )
        self.assertEqual(
            service.route_command("add", "inet6", "2606:4700:cf1:1000::/64", "tun1"),
            ["/sbin/route", "-n", "-6", "add", "-net", "2606:4700:cf1:1000::/64", "-interface", "tun1"],
        )

    def test_mesh_route_install_records_each_successful_route(self):
        instance = dict(self.instance)
        instance["role"] = "mesh-node"
        instance["interface"] = "tun1"
        completed = SimpleNamespace(returncode=0, stdout="", stderr="")
        with patch.object(service.subprocess, "run", return_value=completed) as run,                 patch.object(service, "write_interface_state") as write:
            service.install_mesh_return_routes(instance)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(write.call_args_list[0].args, (
            self.tunnel_id, "tun1", [("inet", "100.96.0.0/12")],
        ))
        self.assertEqual(write.call_args_list[1].args, (
            self.tunnel_id, "tun1", [
                ("inet", "100.96.0.0/12"),
                ("inet6", "2606:4700:cf1:1000::/64"),
            ],
        ))

    def test_route_cleanup_does_not_delete_externally_replaced_route(self):
        state = {
            "interface": "tun1",
            "mesh_return_routes": [{
                "family": "inet",
                "destination": "100.96.0.0/12",
                "interface": "tun1",
            }],
        }
        with patch.object(service, "owned_mesh_routes", return_value=("tun1", [("inet", "100.96.0.0/12")])),                 patch.object(service, "route_matches_owner", return_value=False),                 patch.object(service, "write_interface_state") as write,                 patch.object(service.subprocess, "run") as run:
            service.remove_owned_mesh_return_routes(self.tunnel_id)
        run.assert_not_called()
        write.assert_called_once_with(self.tunnel_id, "tun1", [])
    def test_route_cleanup_requires_exact_network_mask_and_interface(self):
        matching = SimpleNamespace(
            returncode=0,
            stdout=(
                "   route to: 100.96.0.1\n"
                "destination: 100.96.0.0\n"
                "       mask: 255.240.0.0\n"
                "  interface: tun1\n"
            ),
            stderr="",
        )
        replaced = SimpleNamespace(
            returncode=0,
            stdout=(
                "   route to: 100.96.0.1\n"
                "destination: 100.96.0.0\n"
                "       mask: 255.255.255.0\n"
                "  interface: tun1\n"
            ),
            stderr="",
        )
        with patch.object(service.subprocess, "run", return_value=matching):
            self.assertTrue(
                service.route_matches_owner("inet", "100.96.0.0/12", "100.96.0.1", "tun1")
            )
        with patch.object(service.subprocess, "run", return_value=replaced):
            self.assertFalse(
                service.route_matches_owner("inet", "100.96.0.0/12", "100.96.0.1", "tun1")
            )




if __name__ == "__main__":
    unittest.main()
