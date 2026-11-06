"""Unit test suite for cover-prepress skill conformance.

Validates:
- Valid YAML frontmatter (name, description)
- Completeness of 5-step deterministic workflow
- Accuracy of CLI command examples and options
- Multi-publisher coverage (KDP, IngramSpark, Lulu)
- Mirror file presence and parity across harnesses (.agent/, .claude/)
- Absence of unsafe path traversal patterns
"""

from __future__ import annotations

from pathlib import Path
import pytest
import yaml

# Resolve project root relative to this test file
TEST_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TEST_DIR.parent

PRIMARY_SKILL = PROJECT_ROOT / "skills" / "cover-prepress" / "SKILL.md"
AGENT_SKILL = PROJECT_ROOT / ".agent" / "skills" / "cover-prepress" / "SKILL.md"
CLAUDE_SKILL = PROJECT_ROOT / ".claude" / "skills" / "cover-prepress" / "SKILL.md"


def _extract_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter enclosed in leading --- markers."""
    if not content.startswith("---"):
        raise ValueError("Document does not begin with frontmatter delimiter '---'")
    parts = content.split("---", 2)
    if len(parts) < 3:
        raise ValueError("Document lacks closing frontmatter delimiter '---'")
    metadata = yaml.safe_load(parts[1])
    body = parts[2]
    return metadata, body


class TestSkillFrontmatter:
    """Validate YAML frontmatter conforms to Antigravity and Agent Skill spec."""

    def test_primary_skill_file_exists(self):
        assert PRIMARY_SKILL.exists(), f"Primary skill missing at {PRIMARY_SKILL}"
        assert PRIMARY_SKILL.is_file()
        assert PRIMARY_SKILL.stat().st_size > 500

    def test_yaml_frontmatter_parseable(self):
        text = PRIMARY_SKILL.read_text(encoding="utf-8")
        meta, body = _extract_frontmatter(text)
        assert isinstance(meta, dict)
        assert meta.get("name") == "cover-prepress"
        desc = meta.get("description", "")
        assert "prepress" in desc.lower()
        assert "wrap calculation" in desc.lower()
        assert "Amazon KDP" in desc
        assert "IngramSpark" in desc
        assert "Lulu" in desc

    def test_frontmatter_format_strict(self):
        text = PRIMARY_SKILL.read_text(encoding="utf-8")
        lines = text.strip().splitlines()
        assert lines[0] == "---"
        assert any(l.startswith("name: cover-prepress") for l in lines[:10])
        closing_idx = [i for i, l in enumerate(lines[1:], 1) if l == "---"]
        assert len(closing_idx) >= 1, "Frontmatter must be cleanly closed"


class TestSkillWorkflowSteps:
    """Validate that all 5 deterministic prepress workflow steps are documented."""

    @pytest.fixture(scope="class")
    @classmethod
    def skill_body(cls) -> str:
        text = PRIMARY_SKILL.read_text(encoding="utf-8")
        _, body = _extract_frontmatter(text)
        return body

    def test_step_1_intake_and_specs(self, skill_body: str):
        assert "Step 1" in skill_body
        assert "Intake" in skill_body or "Specification Calculation" in skill_body
        assert "mbooks calculate" in skill_body or "calculate_prepress_spec" in skill_body
        assert "--publisher" in skill_body
        assert "--trim" in skill_body
        assert "--pages" in skill_body

    def test_step_2_diagnostic_proof(self, skill_body: str):
        assert "Step 2" in skill_body
        assert "Diagnostic Proof" in skill_body
        assert "cover-proof" in skill_body
        assert "zoomed spine" in skill_body.lower() or "clearance" in skill_body.lower()

    def test_step_3_boundary_and_centering(self, skill_body: str):
        assert "Step 3" in skill_body
        assert "Boundary" in skill_body or "Centering Refinement" in skill_body
        assert "--spine-bounds" in skill_body
        assert "--spine-shift-px" in skill_body
        assert "--safe-buffer" in skill_body
        assert "optical centering" in skill_body.lower()

    def test_step_4_print_ready_pdf_export(self, skill_body: str):
        assert "Step 4" in skill_body
        assert "PDF" in skill_body
        assert "--export-pdf" in skill_body
        assert "MediaBox" in skill_body
        assert "TrimBox" in skill_body
        assert "BleedBox" in skill_body

    def test_step_5_interactive_web_studio(self, skill_body: str):
        assert "Step 5" in skill_body
        assert "Studio" in skill_body
        assert "cover-studio" in skill_body
        assert "Canvas" in skill_body or "FastAPI" in skill_body


class TestSkillCliAndOptions:
    """Validate documentation of CLI tools, commands, and arguments."""

    @pytest.fixture(scope="class")
    @classmethod
    def skill_text(cls) -> str:
        return PRIMARY_SKILL.read_text(encoding="utf-8")

    def test_subcommands_documented(self, skill_text: str):
        assert "cover-resize" in skill_text
        assert "cover-proof" in skill_text
        assert "cover-studio" in skill_text
        assert "calculate" in skill_text

    def test_essential_flags_documented(self, skill_text: str):
        required_flags = [
            "--publisher",
            "--binding",
            "--trim",
            "--pages",
            "--paper",
            "--ink",
            "--dpi",
            "--spine-bounds",
            "--spine-shift-px",
            "--safe-buffer",
            "--export-pdf",
            "--json",
            "--input",
            "--output",
        ]
        for flag in required_flags:
            assert flag in skill_text, f"Missing CLI flag documentation for {flag}"

    def test_multi_publisher_rules(self, skill_text: str):
        assert "Amazon KDP" in skill_text or "kdp" in skill_text.lower()
        assert "IngramSpark" in skill_text or "ingram" in skill_text.lower()
        assert "Lulu" in skill_text or "lulu" in skill_text.lower()
        assert "casewrap" in skill_text.lower()
        assert "paperback" in skill_text.lower()


class TestCrossHarnessPackaging:
    """Validate cross-harness availability across Antigravity, Claude Code, and Codex."""

    def test_agent_harness_mirror_present(self):
        assert AGENT_SKILL.exists(), f"Antigravity mirror missing at {AGENT_SKILL}"
        assert AGENT_SKILL.is_file()

    def test_claude_harness_mirror_present(self):
        assert CLAUDE_SKILL.exists(), f"Claude mirror missing at {CLAUDE_SKILL}"
        assert CLAUDE_SKILL.is_file()

    def test_mirrors_identical_content(self):
        primary_content = PRIMARY_SKILL.read_text(encoding="utf-8")
        agent_content = AGENT_SKILL.read_text(encoding="utf-8")
        claude_content = CLAUDE_SKILL.read_text(encoding="utf-8")

        assert agent_content == primary_content, "Antigravity mirror deviates from primary skill"
        assert claude_content == primary_content, "Claude mirror deviates from primary skill"

    def test_harness_instructions_included(self):
        text = PRIMARY_SKILL.read_text(encoding="utf-8")
        assert "Antigravity" in text
        assert "Claude Code" in text
        assert "Codex" in text


class TestSkillSafetyAndIntegrity:
    """Ensure skill avoids insecure path traversal or external dependencies."""

    def test_no_unsafe_path_traversal(self):
        text = PRIMARY_SKILL.read_text(encoding="utf-8")
        assert "../../../../../" not in text
        assert "../../.." not in text

    def test_zero_cloud_dependency_declaration(self):
        text = PRIMARY_SKILL.read_text(encoding="utf-8")
        assert "zero" in text.lower() and "cloud" in text.lower()

    def test_install_skill_cli_command(self, tmp_path: Path):
        from mbooks.cli import main

        main(["install-skill", "--no-global", "--workspace", str(tmp_path)])
        assert (tmp_path / ".agent" / "skills" / "cover-prepress" / "SKILL.md").exists()
        assert (tmp_path / ".claude" / "skills" / "cover-prepress" / "SKILL.md").exists()
        assert (tmp_path / "skills" / "cover-prepress" / "SKILL.md").exists()
