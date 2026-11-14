"""The project record: the single shared context every step reads and writes.

This is the backbone of the product. Each step writes one structured entry;
later steps read the entries listed in their ``reads``. When an upstream entry
changes, the steps that depend on it are marked stale so the UI can prompt a
re-run.

The record is a plain, serialisable object (think: one JSON document per
project), so it is cheap to store and to attach to a model call.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class StepEntry:
    """What one step wrote into the record."""

    step_id: str
    fields: dict[str, object] = field(default_factory=dict)
    stale: bool = False
    updated_at: float = field(default_factory=time.time)


class ProjectRecord:
    """Shared, structured context for one research project.

    ``data`` holds project-level material (e.g. imported datasets) that any step
    may read. ``entries`` holds one :class:`StepEntry` per step that has run.

    ``downstream`` maps a step id to the ids of the steps that read it; writing a
    step marks those dependents stale. Build it from a protocol with
    :meth:`from_protocol`.
    """

    def __init__(
        self,
        protocol_id: str,
        downstream: dict[str, list[str]] | None = None,
        data: dict[str, object] | None = None,
    ):
        self.protocol_id = protocol_id
        self.downstream = downstream or {}
        self.data: dict[str, object] = dict(data or {})
        self.entries: dict[str, StepEntry] = {}

    @classmethod
    def from_protocol(cls, protocol, data=None) -> "ProjectRecord":
        """Create a record whose staleness tracking follows ``protocol``."""
        downstream: dict[str, list[str]] = {s.id: [] for s in protocol.steps}
        for step in protocol.steps:
            for upstream in step.reads:
                downstream.setdefault(upstream, []).append(step.id)
        return cls(protocol.id, downstream=downstream, data=data)

    # -- writing -----------------------------------------------------------
    def write(self, step_id: str, fields: dict[str, object]) -> StepEntry:
        """Write (or overwrite) a step's entry and mark its dependents stale."""
        entry = StepEntry(step_id=step_id, fields=dict(fields))
        self.entries[step_id] = entry
        self._mark_dependents_stale(step_id)
        return entry

    def _mark_dependents_stale(self, changed_step_id: str) -> None:
        for dependent_id in self.downstream.get(changed_step_id, []):
            dependent = self.entries.get(dependent_id)
            if dependent:
                dependent.stale = True
                # Staleness cascades: a stale step's own dependents are stale too.
                self._mark_dependents_stale(dependent_id)

    # -- reading -----------------------------------------------------------
    def read(self, step_id: str) -> StepEntry | None:
        return self.entries.get(step_id)

    def is_stale(self, step_id: str) -> bool:
        entry = self.entries.get(step_id)
        return bool(entry and entry.stale)

    def mark_fresh(self, step_id: str) -> None:
        entry = self.entries.get(step_id)
        if entry:
            entry.stale = False

    # -- serialisation -----------------------------------------------------
    def as_context(self, reads: list[str] | None = None) -> str:
        """Render the record as text to attach to a step agent call.

        If ``reads`` is given, only those steps' entries are included (plus the
        project data). This keeps the context to what a step actually needs.
        """
        lines: list[str] = []
        if self.data:
            lines.append("# Project data (available to all steps)")
            for key, value in self.data.items():
                lines.append(f"- {key}: {value}")
            lines.append("")

        step_ids = reads if reads is not None else list(self.entries)
        lines.append("# Project record")
        for step_id in step_ids:
            entry = self.entries.get(step_id)
            if not entry:
                continue
            flag = " (OUT OF DATE)" if entry.stale else ""
            lines.append(f"## {step_id}{flag}")
            for key, value in entry.fields.items():
                lines.append(f"- {key}: {value}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, object]:
        return {
            "protocol_id": self.protocol_id,
            "data": self.data,
            "entries": {
                sid: {
                    "step_id": e.step_id,
                    "fields": e.fields,
                    "stale": e.stale,
                    "updated_at": e.updated_at,
                }
                for sid, e in self.entries.items()
            },
        }
