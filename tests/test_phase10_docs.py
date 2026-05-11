"""Phase 10 — verify operator-facing docs exist, are non-empty, and have
the expected lead headings. These are simple file-shape checks; the
content itself is reviewed manually."""

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"


PHASE_10_DOCS: list[tuple[str, str]] = [
    ("operator-guide.md", "# RasaPi — Operator Guide"),
    ("configuration.md", "# RasaPi — Configuration Reference"),
    ("maintenance.md", "# RasaPi — Maintenance Guide"),
    ("troubleshooting.md", "# RasaPi — Troubleshooting"),
    ("security-hardening-checklist.md", "# RasaPi — Security Hardening Checklist"),
    ("final-architecture.md", "# RasaPi — Final Architecture (Phases 1–10)"),
    ("phase-11-roadmap.md", "# RasaPi — Phase 11+ Roadmap"),
    ("use-cases.md", "# RasaPi — Use Cases"),
    ("command-reference.md", "# RasaPi — Command Reference"),
    ("readiness-checklist.md", "# RasaPi — Readiness Checklist"),
]


@pytest.mark.parametrize("filename,heading", PHASE_10_DOCS)
def test_phase10_doc_exists_and_starts_with_heading(filename, heading):
    path = DOCS_DIR / filename
    assert path.is_file(), f"missing: {path}"
    body = path.read_text(encoding="utf-8")
    assert len(body) > 500, f"{filename} is suspiciously small ({len(body)} bytes)"
    # First non-blank line should be the expected H1.
    first_line = body.lstrip().splitlines()[0]
    assert first_line.strip() == heading, (
        f"{filename} starts with {first_line!r}, expected {heading!r}"
    )


def test_readme_links_to_operator_guide():
    body = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/operator-guide.md" in body


def test_readme_links_to_phase_11_roadmap():
    body = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/phase-11-roadmap.md" in body


def test_roadmap_links_to_phase_11_roadmap():
    body = (REPO_ROOT / "docs" / "roadmap.md").read_text(encoding="utf-8")
    assert "phase-11-roadmap.md" in body


def test_security_model_links_to_hardening_checklist():
    body = (REPO_ROOT / "docs" / "security-model.md").read_text(encoding="utf-8")
    assert "security-hardening-checklist.md" in body


def test_architecture_links_to_final_architecture():
    body = (REPO_ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
    assert "final-architecture.md" in body


# ─── Phase 10 polish: docs explain the no-wrapper/no-symlink story ─────────


def test_audio_setup_says_no_wrapper_needed():
    body = (REPO_ROOT / "deployment" / "raspberry-pi" / "audio-setup.md").read_text(
        encoding="utf-8"
    )
    assert "No wrapper script is needed" in body
    assert "No symlink under" in body


def test_troubleshooting_documents_model_path_errors():
    body = (REPO_ROOT / "docs" / "troubleshooting.md").read_text(encoding="utf-8")
    assert "VOICE_WHISPER_MODEL_PATH" in body
    assert "VOICE_PIPER_MODEL_PATH" in body
    assert "VOICE_TTS_PLAYBACK_COMMAND" in body


def test_configuration_documents_new_voice_keys():
    body = (REPO_ROOT / "docs" / "configuration.md").read_text(encoding="utf-8")
    for key in (
        "VOICE_WHISPER_MODEL_PATH",
        "VOICE_PIPER_MODEL_PATH",
        "VOICE_PIPER_CONFIG_PATH",
        "VOICE_TTS_PLAYBACK_COMMAND",
    ):
        assert key in body, f"configuration.md missing {key}"
