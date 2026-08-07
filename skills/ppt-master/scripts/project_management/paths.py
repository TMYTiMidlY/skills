#!/usr/bin/env python3
"""
PPT Master - Project Management Paths

Own the Skill resource roots used by project-management modules.

Usage:
    Import the required path constants or lazy user-path helpers from
    project_management.paths.

Examples:
    from project_management.paths import get_projects_root, SCHEMA_DIR

Dependencies:
    Standard library plus scripts/config.py for the user projects root
"""

from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = PACKAGE_DIR.parent
SKILL_DIR = SCRIPTS_DIR.parent
REPO_ROOT = SKILL_DIR.parent.parent
SOURCE_TO_MD_DIR = SCRIPTS_DIR / "source_to_md"
CHARTS_DIR = SKILL_DIR / "templates" / "charts"
SCHEMA_DIR = SKILL_DIR / "templates" / "schemas"
SCAFFOLD_DIR = SKILL_DIR / "templates" / "scaffolds"


def get_projects_root() -> Path:
    """Resolve the user-owned projects root lazily."""
    from config import require_user_projects_dir

    return require_user_projects_dir()
