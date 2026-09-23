"""Phase 1 tests — configuration and health checks.

External Sarvam API calls are mocked; these tests never consume
Sarvam API credits. The live connectivity test is run via
`python prototype/app.py`, not through pytest.
"""

import os
import sys
from pathlib import Path
from unittest import mock

import pytest

# Make `prototype/` importable regardless of pytest invocation directory.
PROTOTYPE_DIR = Path(__file__).resolve().parent.parent
if str(PROTOTYPE_DIR) not in sys.path:
    sys.path.insert(0, str(PROTOTYPE_DIR))

import config  # noqa: E402
import health  # noqa: E402
from sarvam_client import get_sarvam_client  # noqa: E402


DUMMY_KEY = "test-dummy-key-not-a-real-secret"


class TestConfiguration:
    def test_load_config_success(self, monkeypatch):
        monkeypatch.setenv("SARVAM_API_KEY", DUMMY_KEY)
        monkeypatch.setattr(config, "ENV_FILE", PROTOTYPE_DIR.parent / ".env")
        cfg = config.load_config()
        assert cfg.sarvam_api_key == DUMMY_KEY

    # Point the loader at a nonexistent .env so a real local key on this
    # machine can never affect the "missing key" test cases.
    NO_ENV = PROTOTYPE_DIR.parent / ".env.test-nonexistent"

    def test_missing_key_raises_clear_error(self, monkeypatch):
        monkeypatch.delenv("SARVAM_API_KEY", raising=False)
        monkeypatch.setattr(config, "ENV_FILE", self.NO_ENV)
        with pytest.raises(config.ConfigurationError) as excinfo:
            config.load_config()
        message = str(excinfo.value)
        assert "SARVAM_API_KEY is not configured" in message
        assert ".env" in message

    def test_empty_key_rejected(self, monkeypatch):
        monkeypatch.setenv("SARVAM_API_KEY", "   ")
        with pytest.raises(config.ConfigurationError):
            config.load_config()


class TestSarvamClient:
    def test_client_created_with_configured_key(self, monkeypatch):
        cfg = config.Config(sarvam_api_key=DUMMY_KEY, env_file_found=True)
        client = get_sarvam_client(cfg)
        assert client is not None

    def test_client_init_failure_is_safe(self, monkeypatch):
        cfg = config.Config(sarvam_api_key=DUMMY_KEY, env_file_found=True)
        with mock.patch(
            "sarvam_client.SarvamAI", side_effect=RuntimeError("boom")
        ):
            with pytest.raises(Exception) as excinfo:
                get_sarvam_client(cfg)
        assert DUMMY_KEY not in str(excinfo.value)


class TestHealthChecks:
    def test_python_check_passes(self):
        result = health.HealthResult()
        health._check_python(result)
        assert result.python_ok is True
        assert result.python_version.count(".") == 2

    def test_health_result_structure_unhealthy_by_default(self):
        result = health.HealthResult()
        assert result.healthy is False
        assert result.sarvam_api == "FAILED"

    def test_missing_key_marks_configuration_failed(self, monkeypatch):
        monkeypatch.delenv("SARVAM_API_KEY", raising=False)
        monkeypatch.setattr(
            config, "ENV_FILE", TestConfiguration.NO_ENV
        )  # never read a real local key
        result = health.run_health_checks()
        assert result.configuration == "FAIL"
        assert result.sarvam_key == "MISSING"
        assert result.sarvam_api == "SKIPPED"
        assert result.healthy is False

    def test_healthy_when_all_checks_pass(self, monkeypatch):
        monkeypatch.setenv("SARVAM_API_KEY", DUMMY_KEY)
        monkeypatch.setattr(config, "ENV_FILE", PROTOTYPE_DIR.parent / ".env")
        with mock.patch.object(
            health, "check_sarvam_api", return_value=(True, "")
        ):
            result = health.run_health_checks()
        assert result.configuration == "PASS"
        assert result.sarvam_key == "CONFIGURED"
        assert result.sarvam_client == "PASS"
        assert result.sarvam_api == "CONNECTED"
        assert result.healthy is True

    def test_api_check_reports_auth_failure_for_403(self):
        class FakeForbiddenError(Exception):
            status_code = 403

        failing_client = mock.Mock()
        failing_client.chat.completions.side_effect = FakeForbiddenError(
            "403 Forbidden"
        )
        ok, reason = health.check_sarvam_api(failing_client)
        assert ok is False
        assert "authentication failure" in reason
        assert DUMMY_KEY not in reason

    def test_api_check_reports_network_failure(self):
        failing_client = mock.Mock()
        failing_client.chat.completions.side_effect = ConnectionError(
            "connection refused"
        )
        ok, reason = health.check_sarvam_api(failing_client)
        assert ok is False
        assert "network" in reason or "connectivity" in reason

    def test_report_never_contains_secret(self):
        result = health.HealthResult(
            env_file_found=True,
            configuration="PASS",
            sarvam_key="CONFIGURED",
            sarvam_client="PASS",
            sarvam_api="FAILED",
            sarvam_api_reason="authentication failure",
            errors=["Sarvam API check failed: authentication failure"],
        )
        report = health.format_health_report(result)
        assert DUMMY_KEY not in report
        assert "Overall Status: UNHEALTHY" in report
