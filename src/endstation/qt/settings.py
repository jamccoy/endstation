"""The application's settings store, named once.

:func:`configure` names the store (``QSettings(organization, application)``)
and the environment variable that may redirect it to an INI file, and
:func:`settings` returns it. :mod:`endstation.qt.theming` and
:mod:`endstation.qt.recent` read and write through it, so one call at startup
decides where everything an application remembers is kept.

The environment variable is for test suites: point it at a temporary INI file
and a test run can never read or write the user's own settings.

Until :func:`configure` is called the store is named after the running
``QCoreApplication``'s organization and application names, and no variable
redirects it.
"""

from __future__ import annotations

import os

from PySide6.QtCore import QCoreApplication, QSettings

__all__ = ["configure", "settings"]

_CONFIG: dict[str, str | None] = {"organization": None, "application": None, "env": None}


def configure(organization: str, application: str | None = None, *, env: str | None = None) -> None:
    """Name the store. ``env`` names a variable holding an INI path to use instead."""
    _CONFIG.update(organization=organization, application=application or organization, env=env)


def settings() -> QSettings:
    """The configured store, or the INI file the configured variable names."""
    env = _CONFIG["env"]
    path = os.environ.get(env) if env else None
    if path:
        return QSettings(path, QSettings.Format.IniFormat)
    organization = _CONFIG["organization"] or QCoreApplication.organizationName() or "endstation"
    application = _CONFIG["application"] or QCoreApplication.applicationName() or organization
    return QSettings(organization, application)
