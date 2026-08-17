"""Shared fixtures for the agent-team tool tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from test_team_adopt import ASSET_CONTENT


@pytest.fixture()
def asset(tmp_path: Path) -> Path:
    path = tmp_path / "canonical" / "TEAM.md"
    path.parent.mkdir()
    path.write_bytes(ASSET_CONTENT)
    return path
