"""The dist publish path is scripts/publish_dist.sh.

``.github/workflows/deploy.yml`` checked out the package repository with a
token and was removed. Do not restore it.
"""

from pathlib import Path


def test_actions_dist_deploy_workflow_is_absent() -> None:
    assert not Path(".github/workflows/deploy.yml").exists()
