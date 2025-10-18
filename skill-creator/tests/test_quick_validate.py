import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "quick_validate.py"
_SPEC = importlib.util.spec_from_file_location("skill_quick_validate", MODULE_PATH)
if _SPEC is None or _SPEC.loader is None:  # pragma: no cover - defensive
    raise ImportError("Unable to load quick_validate module for testing")

quick_validate = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("skill_quick_validate", quick_validate)
_SPEC.loader.exec_module(quick_validate)

_parse_frontmatter_without_yaml = quick_validate._parse_frontmatter_without_yaml
validate_skill = quick_validate.validate_skill


@pytest.fixture
def skill_dir(tmp_path: Path) -> Path:
    path = tmp_path / "skill"
    path.mkdir()
    return path


def write_skill(skill_path: Path, frontmatter: str, body: str = "") -> None:
    content = textwrap.dedent(frontmatter)
    if not content.startswith("---"):
        raise ValueError("Frontmatter must begin with '---' in tests")
    skill_md = skill_path / "SKILL.md"
    skill_md.write_text(f"{content}\n---\n{body}", encoding="utf-8")


def test_parse_frontmatter_without_yaml_supports_nested_structures() -> None:
    frontmatter = textwrap.dedent(
        """\
        allowed-tools:
          - name: tool-alpha
            config:
              nested: value
          - list:
              - one
              - two
        metadata:
          tags:
            - sample
        """
    )

    parsed = _parse_frontmatter_without_yaml(frontmatter)

    assert parsed == {
        "allowed-tools": [
            {"name": "tool-alpha", "config": {"nested": "value"}},
            {"list": ["one", "two"]},
        ],
        "metadata": {"tags": ["sample"]},
    }


def test_validate_skill_success(skill_dir: Path) -> None:
    frontmatter = """\
    ---
    name: skill-creator
    description: Helpful description
    license: MIT
    allowed-tools:
      - slack
    metadata:
      complexity: medium
    """

    write_skill(skill_dir, frontmatter, body="# Skill content")

    is_valid, message = validate_skill(skill_dir)

    assert is_valid
    assert message == "Skill is valid!"


def test_validate_skill_rejects_unexpected_keys(skill_dir: Path) -> None:
    frontmatter = """\
    ---
    name: skill-creator
    description: Sample
    version: 1.0
    """

    write_skill(skill_dir, frontmatter)

    is_valid, message = validate_skill(skill_dir)

    assert not is_valid
    assert "Unexpected key(s)" in message
    assert "version" in message


def test_validate_skill_requires_description(skill_dir: Path) -> None:
    frontmatter = """\
    ---
    name: skill-creator
    description:
    """

    write_skill(skill_dir, frontmatter)

    is_valid, message = validate_skill(skill_dir)

    assert not is_valid
    assert "Missing required frontmatter field(s): description" == message


def test_validate_skill_requires_hyphen_case_name(skill_dir: Path) -> None:
    frontmatter = """\
    ---
    name: SkillCreator
    description: Sample description
    """

    write_skill(skill_dir, frontmatter)

    is_valid, message = validate_skill(skill_dir)

    assert not is_valid
    assert "hyphen-case" in message


def test_validate_skill_validates_allowed_tools_list(skill_dir: Path) -> None:
    frontmatter = """\
    ---
    name: skill-creator
    description: Sample description
    allowed-tools: slack
    """

    write_skill(skill_dir, frontmatter)

    is_valid, message = validate_skill(skill_dir)

    assert not is_valid
    assert "'allowed-tools' must be a list" in message


def test_validate_skill_requires_metadata_mapping(skill_dir: Path) -> None:
    frontmatter = """\
    ---
    name: skill-creator
    description: Sample description
    metadata:
      - entry
    """

    write_skill(skill_dir, frontmatter)

    is_valid, message = validate_skill(skill_dir)

    assert not is_valid
    assert "'metadata' must be a mapping" in message
