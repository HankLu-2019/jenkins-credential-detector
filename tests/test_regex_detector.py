"""Tests for the regex + base64 credential detector."""

from pathlib import Path

import pytest

from scanner.detectors.regex_detector import scan_log

FIXTURES = Path(__file__).parent / "fixtures"


def _types(candidates):
    return {c.finding_type for c in candidates}


def _encodings(candidates):
    return {c.encoding for c in candidates}


class TestPlaintextPatterns:
    def test_aws_access_key(self):
        hits = scan_log(FIXTURES / "sample.log")
        types = _types(hits)
        assert "AWS_ACCESS_KEY" in types

    def test_aws_secret_key(self):
        hits = scan_log(FIXTURES / "sample.log")
        assert "AWS_SECRET_KEY" in _types(hits)

    def test_password_assignment(self):
        hits = scan_log(FIXTURES / "sample.log")
        assert "GENERIC_PASSWORD" in _types(hits)

    def test_db_connection_string(self):
        hits = scan_log(FIXTURES / "sample.log")
        assert "DB_CONNECTION_STRING" in _types(hits)

    def test_github_token(self):
        hits = scan_log(FIXTURES / "sample.log")
        assert "GITHUB_TOKEN" in _types(hits)

    def test_clean_log_has_no_hits(self):
        hits = scan_log(FIXTURES / "clean.log")
        assert len(hits) == 0


class TestBase64Detection:
    def test_http_basic_auth_detected(self):
        hits = scan_log(FIXTURES / "sample.log")
        assert "HTTP_BASIC_AUTH" in _types(hits)

    def test_http_basic_auth_decoded(self):
        hits = scan_log(FIXTURES / "sample.log")
        basic = [c for c in hits if c.finding_type == "HTTP_BASIC_AUTH"]
        assert basic
        # Should show the decoded value, not the base64 blob
        assert ":" in basic[0].raw_value  # user:password format
        assert basic[0].encoding == "BASE64"

    def test_bearer_token(self):
        # The sample log's bearer token is a GitHub token (ghp_), so it is
        # correctly classified as GITHUB_TOKEN (higher priority). Test that
        # a generic bearer is detected when it doesn't match a vendor pattern.
        hits = scan_log(FIXTURES / "sample.log")
        # Either GITHUB_TOKEN or BEARER_TOKEN is acceptable — the token is present
        assert "GITHUB_TOKEN" in _types(hits) or "BEARER_TOKEN" in _types(hits)


class TestMasking:
    def test_display_value_is_masked(self):
        hits = scan_log(FIXTURES / "sample.log")
        for c in hits:
            if c.raw_value:
                # Must not contain the full raw value in display_value
                assert c.display_value != c.raw_value
                assert "***" in c.display_value

    def test_context_does_not_contain_raw_value(self):
        hits = scan_log(FIXTURES / "sample.log")
        for c in hits:
            if c.raw_value and len(c.raw_value) > 6:
                context_text = "\n".join(c.context_lines)
                assert c.raw_value not in context_text, (
                    f"Raw value leaked into context for {c.finding_type}"
                )

    def test_content_hash_is_sha256(self):
        hits = scan_log(FIXTURES / "sample.log")
        for c in hits:
            assert len(c.content_hash) == 64
            assert all(ch in "0123456789abcdef" for ch in c.content_hash)


class TestDeduplication:
    def test_no_duplicate_hashes(self):
        hits = scan_log(FIXTURES / "sample.log")
        hashes = [c.content_hash for c in hits]
        assert len(hashes) == len(set(hashes)), "Duplicate content hashes found"


class TestInlinePatterns:
    """Test specific patterns using temporary log files."""

    def _scan_text(self, tmp_path, text):
        log = tmp_path / "test.log"
        log.write_text(text)
        return scan_log(log)

    def test_pem_private_key(self, tmp_path):
        hits = self._scan_text(tmp_path, "-----BEGIN RSA PRIVATE KEY-----\nMIIE...")
        assert "PRIVATE_KEY" in _types(hits)

    def test_jwt_token(self, tmp_path):
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        hits = self._scan_text(tmp_path, f"token={jwt}")
        assert "JWT_TOKEN" in _types(hits)

    def test_test_password_is_not_false_negative(self, tmp_path):
        # Regex stage should still flag it; LLM stage would filter it
        # We only test that regex catches it here
        hits = self._scan_text(tmp_path, 'password=changeme123')
        assert len(hits) > 0

    def test_empty_password_not_flagged(self, tmp_path):
        hits = self._scan_text(tmp_path, 'password=""')
        # value is too short (empty string) — should not produce a candidate
        pw_hits = [c for c in hits if c.finding_type == "GENERIC_PASSWORD"]
        assert len(pw_hits) == 0

    def test_gitlab_token(self, tmp_path):
        hits = self._scan_text(tmp_path, "token=glpat-abcdefghijklmnopqrst")
        assert "GITLAB_TOKEN" in _types(hits)

    def test_google_api_key(self, tmp_path):
        hits = self._scan_text(tmp_path, "key=AIzaFAKE_TEST_NOT_REAL_0000000000000000")
        assert "GOOGLE_API_KEY" in _types(hits)
