import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from server import connections


class ConnectionTests(unittest.TestCase):
    def test_identity_persists(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(connections, "IDENTITY_PATH", Path(folder) / "identity.json"):
                first = connections.get_server_id()
                second = connections.get_server_id()
                self.assertEqual(first, second)
                info = connections.server_info()
                self.assertEqual(info["server_id"], first)
                self.assertFalse(info["capabilities"]["remote_access"])
                self.assertFalse(info["capabilities"]["streaming"])

    def test_malformed_identity_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "identity.json"
            path.write_text("not json")
            with patch.object(connections, "IDENTITY_PATH", path):
                with self.assertRaises(RuntimeError):
                    connections.get_server_id()
            self.assertEqual(path.read_text(), "not json")


if __name__ == "__main__":
    unittest.main()
