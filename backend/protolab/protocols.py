"""Load and represent protocol config files.

A protocol is data, not code: the engine renders the step bar and drives the
agents straight from one of these files, so a new research direction is a new
JSON file under ``protocols/`` rather than new code.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Step:
    """One step of a protocol."""

    id: str
    name: str
    role: str
    output: list[str] = field(default_factory=list)
    reads: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Protocol:
    """An ordered list of steps."""

    id: str
    name: str
    steps: list[Step]
    description: str = ""

    def step(self, step_id: str) -> Step:
        for s in self.steps:
            if s.id == step_id:
                return s
        raise KeyError(f"no step {step_id!r} in protocol {self.id!r}")

    @property
    def step_ids(self) -> list[str]:
        return [s.id for s in self.steps]


def _parse(data: dict) -> Protocol:
    try:
        steps = [
            Step(
                id=s["id"],
                name=s["name"],
                role=s["role"],
                output=list(s.get("output", [])),
                reads=list(s.get("reads", [])),
                tools=list(s.get("tools", [])),
            )
            for s in data["steps"]
        ]
        protocol = Protocol(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            steps=steps,
        )
    except KeyError as exc:
        raise ValueError(f"protocol is missing required key: {exc}") from exc

    _validate(protocol)
    return protocol


def _validate(protocol: Protocol) -> None:
    """Fail fast on references a step makes to steps that do not exist."""
    seen: set[str] = set()
    for step in protocol.steps:
        for upstream in step.reads:
            if upstream not in seen:
                raise ValueError(
                    f"step {step.id!r} reads {upstream!r}, "
                    "which is not an earlier step"
                )
        seen.add(step.id)


def load_protocol(path: str | Path) -> Protocol:
    """Load a single protocol file."""
    return _parse(json.loads(Path(path).read_text(encoding="utf-8")))


def load_protocols(directory: str | Path) -> dict[str, Protocol]:
    """Load every ``*.json`` protocol in a directory, keyed by protocol id."""
    out: dict[str, Protocol] = {}
    for file in sorted(Path(directory).glob("*.json")):
        protocol = load_protocol(file)
        out[protocol.id] = protocol
    return out
