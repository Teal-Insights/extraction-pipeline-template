"""Contract tests for the local dist/ publish script.

Publishing clones the package repository and rsyncs the committed dist/
tree. It does not dispatch .github/workflows/deploy.yml.
"""

from pathlib import Path

SCRIPT_PATH = Path("scripts/publish_dist.sh")


def script_text() -> str:
    return SCRIPT_PATH.read_text(encoding="utf-8")


def test_publish_script_resolves_target_from_workbook_config() -> None:
    text = script_text()
    assert "repository_slug" in text
    assert "load_pipeline_config" in text
    assert "py-q-craft" not in text
    assert "Teal-Insights" not in text


def test_publish_script_records_owner_repo_without_remote_userinfo() -> None:
    text = script_text()
    assert "([^/@]*@)?" in text
    assert "Deploy generated package from ${origin_slug}@${sha}" in text


def test_publish_script_rsyncs_committed_dist_and_pushes_main() -> None:
    text = script_text()
    assert "git archive" in text
    assert 'rsync -a --delete --exclude ".git/"' in text
    assert "push origin HEAD:main" in text


def test_publish_script_refuses_missing_or_dirty_dist() -> None:
    text = script_text()
    assert "No committed dist/" in text
    assert "uncommitted" in text


def test_publish_script_does_not_use_github_actions() -> None:
    text = script_text()
    assert "workflow_dispatch" not in text
    assert "gh workflow" not in text
    assert "DEPLOY_TOKEN" not in text
    assert "actions/checkout" not in text
    assert "git config" not in text
    assert "extraction_pipeline" not in text
