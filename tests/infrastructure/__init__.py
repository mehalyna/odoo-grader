"""Tests for the shared package of the same name.

This directory has the same name as a production package. Under `unittest discover -s tests`,
tests/ is first on sys.path and would shadow it, so the package path is extended to include
the production directory (standard pkgutil mechanism).
"""

from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)
