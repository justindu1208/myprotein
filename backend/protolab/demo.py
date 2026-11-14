"""Minimal live demo: run one step against the configured Adaption stack.

    export ADAPTION_API_KEY=...
    export PROTOLAB_STACK=stack:your-slug
    python -m protolab.demo

Kept tiny on purpose: it shows the single-stack / per-step-role pattern end to
end. The hackathon build drives the same ``run_step`` from the UI.
"""

from __future__ import annotations

import os
from pathlib import Path

from .protocols import load_protocol
from .record import ProjectRecord
from .agents import run_step

PROTOCOLS = Path(__file__).resolve().parents[2] / "protocols"


def main() -> None:
    stack = os.environ.get("PROTOLAB_STACK")
    if not stack or not os.environ.get("ADAPTION_API_KEY"):
        raise SystemExit(
            "Set ADAPTION_API_KEY and PROTOLAB_STACK (e.g. stack:your-slug)."
        )

    try:
        from adaption import Adaption  # imported lazily so offline tests don't need it
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("Install the Adaption SDK: pip install adaption") from exc

    protocol = load_protocol(PROTOCOLS / "variant-screening.json")
    record = ProjectRecord.from_protocol(protocol)
    record.write(
        "question",
        {"question": "Can the enzyme hold its substrate better at higher temperature?"},
    )

    client = Adaption()
    response = run_step(
        client,
        stack,
        protocol,
        "hypothesis",
        record,
        user_message="Propose a hypothesis for the question above.",
    )
    print(getattr(response, "output_text", response))


if __name__ == "__main__":  # pragma: no cover
    main()
