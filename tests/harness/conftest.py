"""pytest --live selects qwen2.5:7b. The default tier uses recorded fixtures."""

from __future__ import annotations

import pytest

from harness import report


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--live",
        action="store_true",
        default=False,
        help="Run the harness against Ollama qwen2.5:7b instead of recorded fixtures.",
    )


@pytest.fixture(scope="session")
def live(request: pytest.FixtureRequest) -> bool:
    flag = bool(request.config.getoption("live"))
    report.TIER = "live" if flag else "fixture"
    return flag


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    _ = (session, exitstatus)
    report.write_reports()


def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter,
    exitstatus: int,
    config: pytest.Config,
) -> None:
    _ = (exitstatus, config)
    text = report.TERMINAL_TEXT or report.render_terminal()
    terminalreporter.write_line("")
    for line in text.splitlines():
        terminalreporter.write_line(line)
