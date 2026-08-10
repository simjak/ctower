"""GH-C07 admission through the unchanged shared connector harness."""

from modules.integrations.connector_conformance import run_outcome_conformance
from modules.integrations.github_conformance_fixture import GitHubOutcomeFixture


def test_github_connector_passes_shared_conformance() -> None:
    run_outcome_conformance(GitHubOutcomeFixture())
