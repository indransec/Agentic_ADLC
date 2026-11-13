"""014: the demo script run once in --auto over the fake pilot, for the demo-moment scenarios."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from adlc.demo.driver import DemoReport
from tests.integration.demo.test_demo_auto import TestIo, demo
from tests.support.orchestration import Harness
from tests.support.pg import PlatformDatabase


@dataclass
class DemoRun:
    h: Harness
    report: DemoReport
    io: TestIo

    @property
    def main(self) -> str:
        return self.report.usecases["main"]


@contextmanager
def demo_run(orch_template: PlatformDatabase, tmp_path: Path) -> Iterator[DemoRun]:
    with demo(orch_template, tmp_path) as (h, driver, io):
        report = driver.run()
        assert report.ok, [(s.number, s.outcome) for s in report.steps if s.outcome != "ok"]
        yield DemoRun(h, report, io)
