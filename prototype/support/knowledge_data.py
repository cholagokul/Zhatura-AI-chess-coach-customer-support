"""Knowledge data parser and exporter for Zhatura Support Portal.

Reads verified knowledge documents from prototype/knowledge/sources/*.md,
extracts YAML frontmatter and structured markdown sections, and produces
sanitized JSON for the support website and search index.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

SOURCES_DIR = Path(__file__).resolve().parent.parent / "knowledge" / "sources"

# Category mappings for UX navigation
CATEGORY_MAP = {
    "overview": {
        "id": "getting-started",
        "title": "Getting Started",
        "icon": "compass",
        "description": "Introduction to Zhatura and the AI chess learning platform.",
    },
    "ai_coach": {
        "id": "ai-chess-coach",
        "title": "AI Chess Coach",
        "icon": "cpu",
        "description": "How the AI Chess Coach helps students learn and improve.",
    },
    "features": {
        "id": "dashboards-roles",
        "title": "Dashboards & Roles",
        "icon": "users",
        "description": "Features for Students, Parents, Coaches, and Academies.",
    },
    "lessons": {
        "id": "lessons-sessions",
        "title": "Lessons & Sessions",
        "icon": "book-open",
        "description": "Understanding lesson flow, practice sessions, and access.",
    },
    "game_analysis": {
        "id": "game-analysis",
        "title": "Game Analysis",
        "icon": "activity",
        "description": "Move review, mistake identification, and AI suggestions.",
    },
    "progress": {
        "id": "progress-tracking",
        "title": "Progress Tracking",
        "icon": "trending-up",
        "description": "Tracking learning milestones in student and parent dashboards.",
    },
    "puzzles": {
        "id": "puzzles-training",
        "title": "Puzzles & Training",
        "icon": "target",
        "description": "Chess puzzles and tactical training exercises.",
    },
    "plans": {
        "id": "plans-billing",
        "title": "Plans & Billing",
        "icon": "credit-card",
        "description": "Subscription info, packages, and custom organization inquiries.",
    },
    "account_help": {
        "id": "account-login",
        "title": "Account & Login",
        "icon": "key",
        "description": "Dashboard sign-in, login troubleshooting, and role access.",
    },
    "support": {
        "id": "technical-support",
        "title": "Technical & General Support",
        "icon": "help-circle",
        "description": "Troubleshooting, platforms, privacy, and support contact.",
    },
    "faq": {
        "id": "faqs",
        "title": "Frequently Asked Questions",
        "icon": "message-circle",
        "description": "Answers to the most common questions from players and parents.",
    },
}

AUDIENCE_DISPLAY = {
    "student": "Students & Children",
    "child": "Students & Children",
    "parent": "Parents & Guardians",
    "coach": "Chess Coaches",
    "academy": "Chess Academies",
    "organization": "Organizations",
    "general": "All Audiences",
}


def parse_frontmatter(text: str) -> tuple[Dict[str, Any], str]:
    """Extract YAML frontmatter and body from markdown."""
    frontmatter: Dict[str, Any] = {}
    body = text.strip()
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            fm_text = parts[1].strip()
            body = parts[2].strip()
            for line in fm_text.splitlines():
                if ":" in line:
                    key, val = line.split(":", 1)
                    key = key.strip()
                    val = val.strip()
                    if val.lower() == "true":
                        frontmatter[key] = True
                    elif val.lower() == "false":
                        frontmatter[key] = False
                    elif "," in val:
                        frontmatter[key] = [v.strip() for v in val.split(",")]
                    else:
                        frontmatter[key] = val
    return frontmatter, body


def sanitize_for_client(text: str) -> str:
    """Sanitize customer-facing text to remove internal vendor names or implementation specifics."""
    cleaned = text
    cleaned = re.sub(r"\bSarvam\s+STT\b", "Zhatura Speech Recognition", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bSarvam\s+Bulbul\s+v3\s+model\b", "Zhatura Voice Engine", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bSarvam\b", "Zhatura", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bElevenLabs\b", "Zhatura Voice", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bExotel\b", "Telephony Network", cleaned, flags=re.IGNORECASE)
    return cleaned


def parse_sections(body: str) -> List[Dict[str, str]]:
    """Split markdown body into heading-level sections."""
    sections = []
    # Split by ## headers
    raw_sections = re.split(r"\n(?=## )", body)
    for raw in raw_sections:
        raw = raw.strip()
        if not raw:
            continue
        lines = raw.splitlines()
        heading = lines[0].lstrip("#").strip()
        content = "\n".join(lines[1:]).strip()
        if heading:
            # Check if this section notes CONTENT_REQUIRED or unverified items
            is_gap = (
                "not yet documented" in content.lower()
                or "no verified" in content.lower()
                or "not available yet" in content.lower()
                or "content_required" in content.lower()
            )
            sections.append({
                "title": heading,
                "content": sanitize_for_client(content),
                "is_content_required": is_gap,
            })
    return sections


def load_all_knowledge() -> List[Dict[str, Any]]:
    """Read all markdown sources and return structured list of articles."""
    articles = []
    if not SOURCES_DIR.exists():
        return articles

    for md_file in sorted(SOURCES_DIR.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(text)

        # Extract primary title from first # Header
        title = md_file.stem.replace("_", " ").title()
        title_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip()

        topic = fm.get("topic", "overview")
        category_meta = CATEGORY_MAP.get(topic, {
            "id": topic,
            "title": topic.replace("_", " ").title(),
            "icon": "file-text",
            "description": f"Information regarding {topic}.",
        })

        raw_audiences = fm.get("audience", ["general"])
        if isinstance(raw_audiences, str):
            raw_audiences = [raw_audiences]

        sections = parse_sections(body)

        # Determine verified status and gap indicators
        has_gaps = any(s["is_content_required"] for s in sections) or (fm.get("status") == "unavailable")

        articles.append({
            "id": fm.get("id", md_file.stem),
            "file_name": md_file.name,
            "title": title,
            "topic": topic,
            "category_id": category_meta["id"],
            "category_title": category_meta["title"],
            "category_icon": category_meta["icon"],
            "audiences": raw_audiences,
            "audience_labels": [AUDIENCE_DISPLAY.get(a, a.title()) for a in raw_audiences],
            "verified": fm.get("verified", True),
            "status": fm.get("status", "available"),
            "has_content_gaps": has_gaps,
            "provenance": "Zhatura Verified Knowledge Base",
            "sections": sections,
            "summary": sections[0]["content"] if sections else "",
        })

    return articles


def get_support_knowledge_payload() -> Dict[str, Any]:
    """Build full support data payload including categories, articles, company info, and FAQs."""
    articles = load_all_knowledge()

    # Extract FAQs specifically
    faqs = []
    faq_article = next((a for a in articles if a["id"] == "faq"), None)
    if faq_article:
        for sec in faq_article["sections"]:
            faqs.append({
                "question": sec["title"],
                "answer": sec["content"],
                "category": "General",
            })

    # Add other top high-frequency questions extracted from knowledge
    top_qa = [
        {
            "question": "What is the Zhatura AI Chess Coach?",
            "answer": "The Zhatura AI Chess Coach is Zhatura's AI coach for learning chess. It explains chess concepts, points out mistakes, and recommends better ideas during practice and game review.",
            "category": "AI Coach",
        },
        {
            "question": "How do students log into Zhatura?",
            "answer": "Students sign in directly through the Student Dashboard. For individual account access issues, please reach out to Zhatura Customer Support.",
            "category": "Account & Login",
        },
        {
            "question": "Can parents track their child's chess learning progress?",
            "answer": "Yes. Zhatura includes a dedicated Parent Dashboard where parents can follow their child's chess learning journey.",
            "category": "Parents",
        },
        {
            "question": "What features are available for Chess Coaches and Academies?",
            "answer": "Coaches manage student batches through the Coach Dashboard. Zhatura also offers solutions for chess academies and educational organizations under Zhatura Chess Academy.",
            "category": "Coaches & Academies",
        },
        {
            "question": "Where can I find current pricing and subscription plan details?",
            "answer": "For current plan or pricing information, please contact Zhatura Customer Support directly at 095-138-86363. Our team will provide up-to-date plan details and answer any questions.",
            "category": "Plans & Billing",
        },
        {
            "question": "Which languages does Zhatura Customer Support speak?",
            "answer": "Our customer support line can converse in English, Hindi, Bengali, Tamil, Telugu, Kannada, Malayalam, Marathi, Gujarati, Punjabi, and Odia.",
            "category": "Support",
        },
        {
            "question": "Can customer support modify or view my private password?",
            "answer": "No. Zhatura customer support never asks for passwords, OTPs, or sensitive payment credentials on calls or via support messages.",
            "category": "Privacy & Security",
        },
    ]

    # Deduplicate FAQs
    seen_q = set()
    all_faqs = []
    for item in top_qa + faqs:
        norm_q = item["question"].strip().lower()
        if norm_q not in seen_q:
            seen_q.add(norm_q)
            all_faqs.append(item)

    # Categories list
    unique_cat_ids = []
    categories = []
    for art in articles:
        cid = art["category_id"]
        if cid not in unique_cat_ids:
            unique_cat_ids.append(cid)
            categories.append({
                "id": cid,
                "title": art["category_title"],
                "icon": art["category_icon"],
                "article_count": sum(1 for a in articles if a["category_id"] == cid),
            })

    return {
        "company": {
            "name": "Namali Innovations Private Limited",
            "date_of_incorporation": "July 23, 2025",
            "status": "Active",
            "registered_address": "6/124, Golden City, Nochiodaipatty, Koovanuthu, Dindigul, Tamil Nadu 624003, India",
            "support_phone": "095-138-86363",
            "support_phone_tel": "+919513886363",
            "support_languages": [
                "English", "Hindi", "Bengali", "Tamil", "Telugu",
                "Kannada", "Malayalam", "Marathi", "Gujarati", "Punjabi", "Odia"
            ],
        },
        "categories": categories,
        "articles": articles,
        "faqs": all_faqs,
        "audiences": [
            {"id": "all", "label": "All Audiences"},
            {"id": "student", "label": "Students & Children"},
            {"id": "parent", "label": "Parents"},
            {"id": "coach", "label": "Chess Coaches"},
            {"id": "academy", "label": "Academies & Orgs"},
        ],
    }


if __name__ == "__main__":
    payload = get_support_knowledge_payload()
    print(f"Loaded {len(payload['articles'])} articles, {len(payload['categories'])} categories, {len(payload['faqs'])} FAQs.")
    out_file = Path(__file__).resolve().parent / "static" / "data.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    json_str = json.dumps(payload, indent=2)
    out_file.write_text(json_str, encoding="utf-8")
    print(f"Saved payload to {out_file} ({out_file.stat().st_size} bytes)")

    out_js = Path(__file__).resolve().parent / "static" / "data.js"
    out_js.write_text(f"window.ZHATURA_SUPPORT_DATA = {json_str};\n", encoding="utf-8")
    print(f"Saved JS payload to {out_js} ({out_js.stat().st_size} bytes)")
