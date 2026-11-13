"""The rehearsed replies per agent for the demo script (feature 014, research R-02), in the order
the script calls them: T3 and T4 twice (the T4 defect sends the build back), the others once."""

from typing import Any

from demo.rehearsed.t3 import t3_build
from demo.rehearsed.t4 import Evaluation
from demo.rehearsed.t5 import Assurance
from demo.rehearsed.t6 import Readiness
from demo.rehearsed.t7 import Deployment
from demo.rehearsed.t8 import Operations
from demo.rehearsed.t9 import Evolution


def replies() -> dict[str, list[Any]]:
    evaluation = Evaluation()
    return {
        "t3-builder-agent": t3_build() + t3_build(),
        "t4-evaluation-agent": evaluation.script() + evaluation.script(),
        "t5-assurance-agent": Assurance().script(retries=3),
        "t6-readiness-agent": Readiness().script(),
        "t7-deployment-agent": Deployment().script(),
        "t8-operations-agent": Operations().script(),
        "t9-evolution-agent": Evolution().script(),
    }
