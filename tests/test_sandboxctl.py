import pathlib
import tempfile
import unittest
import json

from sandboxctl import (
    build_session_id,
    build_network_xml,
    build_domain_xml,
    safe_child,
)
from ui import load_session_rows


class SandboxControllerTests(unittest.TestCase):
    def test_ui_lists_only_valid_session_metadata(self):
        with tempfile.TemporaryDirectory() as root:
            evidence = pathlib.Path(root)
            valid = evidence / "s-20261107T120000Z-abcdef12"
            valid.mkdir(parents=True)
            (valid / "session.json").write_text(json.dumps({
                "session_id": "s-20261107T120000Z-abcdef12",
                "vm_name": "win11-s-20261107T120000Z-abcdef12",
            }), encoding="utf-8")
            invalid = evidence / "not-a-session"
            invalid.mkdir(parents=True)
            (invalid / "session.json").write_text("{}", encoding="utf-8")

            rows = load_session_rows(evidence)

            self.assertEqual(rows, [(
                "s-20261107T120000Z-abcdef12",
                "win11-s-20261107T120000Z-abcdef12",
            )])

    def test_session_id_is_safe_and_unique_shape(self):
        value = build_session_id()
        self.assertRegex(value, r"^s-\d{8}T\d{6}Z-[0-9a-f]{8}$")

    def test_safe_child_rejects_escape(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                safe_child(pathlib.Path(root), pathlib.Path(root) / ".." / "outside")

    def test_network_is_isolated(self):
        xml = build_network_xml({
            "name": "test-net",
            "bridge": "virbr-test",
            "ipv4": "192.0.2.1/24",
            "dhcp_start": "192.0.2.100",
            "dhcp_end": "192.0.2.199",
            "forward": False,
        })
        self.assertIn("<forward mode='none'/>", xml)
        self.assertNotIn("<forward mode='nat'/>", xml)

    def test_domain_has_no_host_sharing_and_has_tpm(self):
        xml = build_domain_xml(
            name="s-test",
            memory_mib=12288,
            vcpus=8,
            machine="q35",
            overlay="/safe/session.qcow2",
            nvram="/safe/nvram.fd",
            network="test-net",
        )
        for forbidden in ("<filesystem", "<redirdev", "<hostdev", "clipboard", "<channel"):
            self.assertNotIn(forbidden, xml)
        self.assertIn("<tpm model='tpm-crb'>", xml)
        self.assertIn("<interface type='network'>", xml)
        self.assertIn("<driver name='qemu' type='qcow2'/>", xml)

    def test_domain_can_pin_a_stable_uuid(self):
        xml = build_domain_xml(
            name="s-test",
            memory_mib=12288,
            vcpus=8,
            machine="q35",
            overlay="/safe/session.qcow2",
            nvram="/safe/nvram.fd",
            network="test-net",
            domain_uuid="11111111-2222-3333-4444-555555555555",
        )
        self.assertIn("<uuid>11111111-2222-3333-4444-555555555555</uuid>", xml)


if __name__ == "__main__":
    unittest.main()
