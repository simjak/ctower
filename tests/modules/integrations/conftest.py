"""Install frozen GitLab trace names for Integrations Module tests."""

from modules.integrations._legacy_gitlab_shims.install import install

__all__: tuple[str, ...] = ()

install()
