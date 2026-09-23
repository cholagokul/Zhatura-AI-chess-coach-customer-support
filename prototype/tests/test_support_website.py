"""Tests for Zhatura Customer Support Website (/support).

Verifies:
- HTTP 200 on /support and /support/
- Valid semantic HTML structure, SEO metadata, Schema.org JSON-LD
- Knowledge data payload (/support/data.json) with all 20 verified articles
- Static assets (/support/static/styles.css, app.js) serve correctly
- Security scan: NO telephony PINs, API keys, or internal vendor names leaked
- Verified company information and public support phone 095-138-86363
- Support form honesty: local reference disclosure, no fake submission claims
- WCAG AA accessibility markers and modal focus trapping semantics
- Telephony /health endpoint remains unaffected
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from phase4_exotel_server import create_app


def _mock_config():
    cfg = MagicMock()
    cfg.sarvam_api_key = "test-sarvam-key-not-real"
    cfg.elevenlabs_api_key = "test-eleven-key-not-real"
    cfg.exotel_ws_host = "127.0.0.1"
    cfg.exotel_ws_port = 8000
    cfg.exotel_ws_path = "/ws"
    cfg.exotel_audio_sample_rate = 16000
    cfg.provider_health_cooldown_seconds = 300
    cfg.voice_primary_provider = "sarvam"
    cfg.voice_secondary_provider = "elevenlabs"
    cfg.support_backend_mode = "mock"
    return cfg


@pytest.fixture
def client():
    app = create_app(_mock_config())
    return TestClient(app, raise_server_exceptions=False)


def test_support_page_returns_200_html(client):
    resp = client.get("/support")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    text = resp.text
    assert "<title>Zhatura AI Chess Coach — Customer Support & Help Center</title>" in text
    assert "095-138-86363" in text
    assert "Namali Innovations Private Limited" in text
    assert "July 23, 2025" in text
    assert "Dindigul" in text
    assert "Student Dashboard" in text
    assert "Parent Dashboard" in text
    assert "Coach Dashboard" in text


def test_support_page_trailing_slash(client):
    resp = client.get("/support/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Zhatura" in resp.text


def test_support_data_json_structure(client):
    resp = client.get("/support/data.json")
    assert resp.status_code == 200
    assert "application/json" in resp.headers["content-type"]
    data = resp.json()

    # Check top-level keys
    assert "company" in data
    assert "categories" in data
    assert "articles" in data
    assert "faqs" in data
    assert "audiences" in data

    # Verify company details
    comp = data["company"]
    assert comp["name"] == "Namali Innovations Private Limited"
    assert comp["date_of_incorporation"] == "July 23, 2025"
    assert comp["status"] == "Active"
    assert "Dindigul" in comp["registered_address"]
    assert comp["support_phone"] == "095-138-86363"
    assert len(comp["support_languages"]) >= 11

    # Verify all verified articles are present (20 spec + 3 knowledge
    # expansion documents: online chess, game history, future roadmap)
    assert len(data["articles"]) == 23
    article_ids = {a["id"] for a in data["articles"]}
    assert "zhatura_overview" in article_ids
    assert "ai_chess_coach" in article_ids
    assert "student_features" in article_ids
    assert "parent_features" in article_ids
    assert "coach_features" in article_ids
    assert "academy_features" in article_ids
    assert "lessons_sessions" in article_ids
    assert "plans_pricing" in article_ids
    assert "faq" in article_ids
    assert "online_chess" in article_ids
    assert "game_history" in article_ids
    assert "future_roadmap" in article_ids

    # Knowledge expansion topics are searchable for customers
    blob = json.dumps(data).lower()
    for term in ("matchmaking", "player ratings", "my zhatura coach",
                 "game history", "guardian controls", "android", "ios",
                 "tournament", "smart-board", "video coaching"):
        assert term in blob, f"support search missing topic: {term}"

    # Verify FAQs count
    assert len(data["faqs"]) >= 10


def test_static_assets_serving(client):
    # CSS
    resp_css = client.get("/support/static/styles.css")
    assert resp_css.status_code == 200
    assert "text/css" in resp_css.headers["content-type"]
    assert "--bg-dark" in resp_css.text

    # JS
    resp_js = client.get("/support/static/app.js")
    assert resp_js.status_code == 200
    assert "javascript" in resp_js.headers["content-type"]
    assert "095-138-86363" in resp_js.text


def test_security_audit_zero_secrets_and_no_vendor_leakage(client):
    """Ensure no API keys, telephony PINs, or internal vendor names are in served static/data."""
    endpoints_to_check = [
        "/support",
        "/support/data.json",
        "/support/static/styles.css",
        "/support/static/app.js",
    ]

    forbidden_patterns = [
        r"SARVAM_API_KEY",
        r"ELEVENLABS_API_KEY",
        r"EXOTEL_API_KEY",
        r"sk-[a-zA-Z0-9]{20,}",
        r"\bPIN\b\s*[:=]\s*\d+",
        r"auth_token",
        r"secret_key",
    ]

    for ep in endpoints_to_check:
        resp = client.get(ep)
        assert resp.status_code == 200, f"Endpoint {ep} failed"
        body = resp.text

        for pat in forbidden_patterns:
            matches = re.findall(pat, body, flags=re.IGNORECASE)
            assert not matches, f"Security violation: found {matches} matching {pat} in {ep}"

    # Specifically verify data.json does not leak internal telephony vendor names
    data_resp = client.get("/support/data.json")
    data_text = data_resp.text
    assert "sarvam" not in data_text.lower(), "Internal vendor 'Sarvam' leaked in data.json"
    assert "elevenlabs" not in data_text.lower(), "Internal vendor 'ElevenLabs' leaked in data.json"
    assert "exotel" not in data_text.lower(), "Internal vendor 'Exotel' leaked in data.json"


def test_seo_and_accessibility_markup(client):
    resp = client.get("/support")
    html = resp.text

    # Semantic & Accessibility
    assert 'class="skip-link"' in html
    assert 'role="banner"' in html
    assert 'role="main"' in html
    assert 'role="contentinfo"' in html
    assert 'role="search"' in html
    assert 'aria-labelledby' in html
    assert 'aria-expanded' in html
    assert 'role="tablist"' in html
    assert 'role="tab"' in html

    # Structured Data JSON-LD
    assert 'application/ld+json' in html
    assert '"@type": "WebSite"' in html
    assert '"@type": "Organization"' in html
    assert '"@type": "FAQPage"' in html

    # Canonical link
    assert '<link rel="canonical" href="https://zhatura.com/support">' in html


def test_support_form_honesty_and_disclaimer(client):
    """Ensure the support form honestly communicates that submission is a local reference without faking ticket creation."""
    resp = client.get("/support")
    html = resp.text
    assert "Online submission backend is not connected" in html
    assert "local tracking reference" in html
    assert "Generate Local Inquiry Reference" in html

    resp_js = client.get("/support/static/app.js")
    js = resp_js.text
    assert "Reference generated locally" in js
    assert "Backend submission is not connected" in js
    # Must NOT claim that an actual ticket was recorded or our team will follow up
    assert "Inquiry recorded! Ticket Ref:" not in js


def test_brand_spelling_integrity(client):
    """Verify that Zhatura is never misspelled as Zathura anywhere in public support pages."""
    resp = client.get("/support")
    assert "zathura" not in resp.text.lower()
    resp_data = client.get("/support/data.json")
    assert "zathura" not in resp_data.text.lower()


def test_health_endpoint_remains_unaffected(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["phase"] == 7
    assert data["phase_version"] == "7.1"
    assert "providers" in data
