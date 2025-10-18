#!/usr/bin/env python3
"""Quick validation script for skills - minimal version."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

try:  # pragma: no cover - PyYAML is optional
    import yaml  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - fallback when PyYAML isn't installed
    yaml = None


FRONTMATTER_BOUNDARY = '---'
ALLOWED_FRONTMATTER_KEYS = {'name', 'description', 'license', 'allowed-tools', 'metadata'}
REQUIRED_FRONTMATTER_KEYS = ('name', 'description')


def _extract_frontmatter(content: str) -> str | None:
    """Return the raw YAML frontmatter block from SKILL.md."""

    if not content.startswith(FRONTMATTER_BOUNDARY):
        return None

    lines = content.splitlines()
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == FRONTMATTER_BOUNDARY:
            return '\n'.join(lines[1:index])
    return None


def _clean_scalar(value: str) -> Any:
    """Normalize scalar values parsed from frontmatter."""

    value = value.strip()
    if value.startswith('[') and value.endswith(']'):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_clean_scalar(part.strip()) for part in inner.split(',')]
    if value.startswith('{') and value.endswith('}'):
        inner = value[1:-1].strip()
        if not inner:
            return {}
        mapping: dict[str, Any] = {}
        for item in inner.split(','):
            if ':' not in item:
                raise ValueError(f'Invalid inline mapping entry in frontmatter: {item}')
            key, raw_value = item.split(':', 1)
            mapping[key.strip()] = _clean_scalar(raw_value.strip())
        return mapping
    if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
        return value[1:-1].strip()
    return value


def _parse_frontmatter_without_yaml(frontmatter_raw: str) -> dict[str, Any]:
    """Minimal YAML parsing fallback for environments without PyYAML."""

    def next_nonempty_line(start_index: int) -> tuple[int, str] | tuple[None, None]:
        for offset in range(start_index, len(lines)):
            candidate = lines[offset]
            if candidate.strip():
                return offset, candidate
        return None, None

    lines = frontmatter_raw.splitlines()
    data: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any] | list[Any]]] = [(0, data)]
    index = 0

    while index < len(lines):
        raw_line = lines[index]
        index += 1
        stripped_line = raw_line.strip()

        if not stripped_line:
            continue

        if '\t' in raw_line:
            raise ValueError('Frontmatter cannot contain tab characters for indentation')

        indent = len(raw_line) - len(raw_line.lstrip(' '))

        while stack and indent < stack[-1][0]:
            stack.pop()

        if not stack:
            raise ValueError('Invalid indentation structure in frontmatter')

        container = stack[-1][1]

        if stripped_line.startswith('- '):
            if not isinstance(container, list):
                raise ValueError('List item found outside of a list context in frontmatter')

            item_content = stripped_line[2:].strip()

            if not item_content:
                lookahead_index, lookahead_line = next_nonempty_line(index)
                if lookahead_index is None:
                    container.append('')
                    continue

                next_indent = len(lookahead_line) - len(lookahead_line.lstrip(' '))
                if next_indent <= indent:
                    container.append('')
                    continue

                nested_container: dict[str, Any] | list[Any]
                if lookahead_line.strip().startswith('- '):
                    nested_container = []
                else:
                    nested_container = {}

                container.append(nested_container)
                stack.append((next_indent, nested_container))
                continue

            if (
                item_content[0] not in "'\"[{"
                and re.search(r':(\s|$)', item_content)
            ):
                key, value = item_content.split(':', 1)
                key = key.strip()
                if not key:
                    raise ValueError('List item contains an empty mapping key')

                value = value.strip()
                item_mapping: dict[str, Any] = {}
                pending_stack_entries: list[tuple[int, dict[str, Any] | list[Any]]] = []

                if value:
                    item_mapping[key] = _clean_scalar(value)
                else:
                    lookahead_index, lookahead_line = next_nonempty_line(index)
                    if lookahead_index is None:
                        item_mapping[key] = ''
                    else:
                        next_indent = len(lookahead_line) - len(lookahead_line.lstrip(' '))
                        if next_indent <= indent:
                            item_mapping[key] = ''
                        else:
                            nested_container: dict[str, Any] | list[Any]
                            if lookahead_line.strip().startswith('- '):
                                nested_container = []
                            else:
                                nested_container = {}
                            item_mapping[key] = nested_container
                            pending_stack_entries.append((next_indent, nested_container))

                container.append(item_mapping)
                stack.append((indent + 2, item_mapping))
                stack.extend(pending_stack_entries)
                continue

            container.append(_clean_scalar(item_content))
            continue

        if ':' not in stripped_line:
            raise ValueError(f'Invalid frontmatter line: {stripped_line}')

        key, value = stripped_line.split(':', 1)
        key = key.strip()
        value = value.strip()

        if not isinstance(container, dict):
            raise ValueError('Invalid nesting in frontmatter structure')

        if value:
            container[key] = _clean_scalar(value)
            continue

        lookahead_index, lookahead_line = next_nonempty_line(index)
        if lookahead_index is None:
            container[key] = ''
            continue

        next_indent = len(lookahead_line) - len(lookahead_line.lstrip(' '))
        if next_indent <= indent:
            container[key] = ''
            continue

        nested_container: dict[str, Any] | list[Any]
        if lookahead_line.strip().startswith('- '):
            nested_container = []
        else:
            nested_container = {}

        container[key] = nested_container
        stack.append((next_indent, nested_container))

    return data


def _load_frontmatter(frontmatter_raw: str) -> dict[str, Any]:
    """Load frontmatter using PyYAML when available, else fallback parser."""

    if yaml is not None:
        try:
            loaded = yaml.safe_load(frontmatter_raw) or {}
        except Exception as exc:  # pragma: no cover - PyYAML provides detailed error
            raise ValueError(f'Invalid YAML frontmatter: {exc}') from exc

        if not isinstance(loaded, dict):
            raise ValueError('Frontmatter must be a mapping of key/value pairs')

        return loaded

    return _parse_frontmatter_without_yaml(frontmatter_raw)


def _validate_metadata(metadata: dict[str, Any]) -> tuple[bool, str | None]:
    for key, value in metadata.items():
        if not isinstance(key, str) or not key.strip():
            return False, "Metadata keys must be non-empty strings"
        if isinstance(value, (dict, list)):
            continue
        if value is None:
            continue
        if not isinstance(value, (str, int, float, bool)):
            return False, f"Unsupported metadata value type for key '{key}'"
    return True, None


def validate_skill(skill_path: str | Path) -> tuple[bool, str]:
    """Basic validation of a skill."""

    skill_path = Path(skill_path)

    skill_md = skill_path / 'SKILL.md'
    if not skill_md.exists():
        return False, 'SKILL.md not found'

    content = skill_md.read_text(encoding='utf-8')
    frontmatter_raw = _extract_frontmatter(content)
    if frontmatter_raw is None:
        return False, 'No YAML frontmatter found'

    try:
        frontmatter = _load_frontmatter(frontmatter_raw)
    except ValueError as exc:
        return False, str(exc)

    unexpected_keys = [key for key in frontmatter if key not in ALLOWED_FRONTMATTER_KEYS]
    if unexpected_keys:
        allowed_keys_display = ', '.join(sorted(ALLOWED_FRONTMATTER_KEYS))
        unexpected_display = ', '.join(sorted(unexpected_keys))
        return (
            False,
            "Unexpected key(s) in SKILL.md frontmatter: "
            f"{unexpected_display}. Allowed keys: {allowed_keys_display}. Move extras into 'metadata'.",
        )

    missing_required = [key for key in REQUIRED_FRONTMATTER_KEYS if not str(frontmatter.get(key, '')).strip()]
    if missing_required:
        missing_display = ', '.join(missing_required)
        return False, f"Missing required frontmatter field(s): {missing_display}"

    name = str(frontmatter.get('name', '')).strip()
    if not re.fullmatch(r'[a-z0-9-]+', name):
        return False, 'Name must be hyphen-case (lowercase letters, digits, and hyphens only)'
    if name.startswith('-') or name.endswith('-') or '--' in name:
        return False, 'Name cannot start/end with a hyphen or contain consecutive hyphens'

    description = str(frontmatter.get('description', '')).strip()
    if '<' in description or '>' in description:
        return False, 'Description cannot contain angle brackets (< or >)'

    license_value = frontmatter.get('license')
    if license_value is not None and not str(license_value).strip():
        return False, "'license' value cannot be empty if provided"

    allowed_tools = frontmatter.get('allowed-tools')
    if allowed_tools is not None:
        if not isinstance(allowed_tools, list):
            return False, "'allowed-tools' must be a list of tool names"
        if any(not isinstance(tool, str) or not tool.strip() for tool in allowed_tools):
            return False, "Each entry in 'allowed-tools' must be a non-empty string"

    metadata = frontmatter.get('metadata')
    if metadata is not None:
        if not isinstance(metadata, dict):
            return False, "'metadata' must be a mapping of additional properties"
        metadata_valid, metadata_error = _validate_metadata(metadata)
        if not metadata_valid:
            return False, metadata_error or 'Invalid metadata values'

    return True, 'Skill is valid!'


def _main(argv: list[str]) -> int:
    if len(argv) != 2:
        print('Usage: python quick_validate.py <skill_directory>')
        return 1

    valid, message = validate_skill(argv[1])
    print(message)
    return 0 if valid else 1


if __name__ == '__main__':
    sys.exit(_main(sys.argv))
