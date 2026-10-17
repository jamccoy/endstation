"""Shared scaffolding for desktop scientific applications.

Not a science library. Everything here is the apparatus that surrounds an
analysis: guarding optional dependencies, reporting and cancelling slow work,
collecting form errors, locating research data that is deliberately not in the
checkout, running work off the UI thread, embedding a figure, rendering a
documentation page, and building a macOS bundle.

**The core imports nothing.** ``endstation``, ``endstation.optional``,
``endstation.progress``, ``endstation.forms`` and ``endstation.paths`` have no
third-party dependencies at all, so a package that declares
``dependencies = []`` can adopt them without giving that up. numpy, matplotlib
and a Qt binding live behind extras and are imported inside the functions that
need them:

========================  ===========  ====================================
Subpackage                Extra        Needs
========================  ===========  ====================================
``endstation.qt``         ``qt``       PySide6, matplotlib
``endstation.docs``       ``docs``     matplotlib, for math only
``endstation.testing``    ``testing``  pytest
``endstation.tools``      --           macOS ``sips``/``iconutil`` at runtime
========================  ===========  ====================================

Importing this module must therefore stay cheap and toolkit-free; the names
re-exported below are from the dependency-free core only. Reach into the
subpackages explicitly for anything else.
"""

from __future__ import annotations

from .forms import ErrorCollector, FieldError, FormErrors
from .optional import MissingExtra, optional_module, require_extra
from .paths import MissingData, data_root, find_data, find_project_root, require_dir
from .progress import Cancelled, cancelling, report, throttled

__version__ = "0.2.0"

__all__ = [
    "__version__",
    # optional dependencies
    "MissingExtra",
    "optional_module",
    "require_extra",
    # progress and cancellation
    "Cancelled",
    "cancelling",
    "report",
    "throttled",
    # form validation
    "ErrorCollector",
    "FieldError",
    "FormErrors",
    # paths
    "MissingData",
    "data_root",
    "find_data",
    "find_project_root",
    "require_dir",
]
