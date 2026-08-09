"""Install the frozen legacy import names for pytest collection only."""

from __future__ import annotations

import sys
from types import ModuleType

import ctower_api
import ctower_kernel.integrations.postgres as integration_postgres
from ctower_kernel import integrations
from modules.integrations._legacy_gitlab_shims import adapter, postgres, runtime, service, values

__all__ = ["install"]


def install() -> None:
    """Redirect legacy imports to tests-only shape maps over the real seams."""

    _alias_module("ctower_api.gitlab_adapter", adapter, parent=ctower_api)
    _alias_module("ctower_api.gitlab_loop", runtime, parent=ctower_api)
    _alias_module("ctower_kernel.integrations.gitlab", values, parent=integrations)
    _alias_module("ctower_kernel.integrations.gitlab_service", service, parent=integrations)

    integration_names = {name: getattr(values, name) for name in values.__all__}
    integration_names["GitLabIssueSync"] = service.GitLabIssueSync
    vars(integrations).update(integration_names)
    vars(integration_postgres)["PostgresGitLabIntegrationStore"] = (
        postgres.PostgresGitLabIntegrationStore
    )


def _alias_module(name: str, module: ModuleType, *, parent: ModuleType) -> None:
    sys.modules[name] = module
    vars(parent)[name.rsplit(".", maxsplit=1)[-1]] = module
