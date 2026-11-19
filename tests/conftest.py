"""Shared pytest setup.

- `node` marker: the test runs the real Node analyzer (~1.2 s each, no cost).
  Skipped automatically when Node.js is missing; `pytest --no-node` deselects them
  for a fast loop during development.
- Shared code samples live in `samples.py`, pipeline fakes in `fakes.py`.
"""
from __future__ import annotations

import pytest

from a11y_investigator.tools.static_analysis import StaticAnalysisError, find_node

try:
    find_node()
    HAS_NODE = True
except StaticAnalysisError:
    HAS_NODE = False


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--no-node", action="store_true", default=False,
        help="deselect tests that run the real Node analyzer (fast loop)",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    node_items = [item for item in items if item.get_closest_marker("node")]
    if config.getoption("--no-node"):
        config.hook.pytest_deselected(items=node_items)
        items[:] = [item for item in items if not item.get_closest_marker("node")]
    elif not HAS_NODE:
        skip = pytest.mark.skip(reason="Node.js not installed")
        for item in node_items:
            item.add_marker(skip)
