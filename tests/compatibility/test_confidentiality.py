from __future__ import annotations

import unittest

from tools.compatibility import CompatibilityError
from tools.compatibility.confidentiality import validate_public_report_bytes


class ExactByteConfidentialityTests(unittest.TestCase):
    def test_credentials_pii_urls_and_private_paths_fail_closed(self) -> None:
        cases = {
            "uppercase credential label": b'{"TOKEN": "synthetic-secret"}',
            "mixed credential label": b'{"Api_Key": "synthetic-secret"}',
            "mixed password label": b'{"PaSsWoRd": "synthetic-secret"}',
            "uppercase secret label": b'{"SECRET": "synthetic-secret"}',
            "email": b'{"value": "alice@example.invalid"}',
            "international phone": b'{"value": "+370 612 34567"}',
            "parenthesized phone": b'{"value": "(415) 555-1212"}',
            "url": b'{"value": "https://example.invalid/private"}',
            "posix path": b'{"value": "/Users/alice/private"}',
            "windows path": b'{"value": "C:\\\\Users\\\\alice\\\\private"}',
        }
        for label, encoded in cases.items():
            with self.subTest(label=label), self.assertRaises(CompatibilityError):
                validate_public_report_bytes(encoded)

    def test_closed_identifiers_and_digests_are_publishable(self) -> None:
        validate_public_report_bytes(
            b'{"actor":"ctower.compatibility-validator","digest":"sha256:' + (b"a" * 64) + b'"}'
        )


if __name__ == "__main__":
    unittest.main()
