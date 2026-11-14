"""The tool registry.

A step may call only the tools named in its protocol config. Each tool has a
JSON schema (what the model sees when deciding to call it) and a local
implementation (what runs when it does). The Predict step calls
``boltz_predict``; the Literature step calls ``literature_search``; data-aware
steps call ``data_search``.

The implementations here are STUBS returning placeholder data so the engine runs
end to end offline. Replace the bodies marked TODO with real calls during the
hackathon.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict  # JSON schema for the function arguments
    run: Callable[..., dict]

    def schema(self) -> dict:
        """The function-tool schema to pass to the model."""
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


# --- implementations (stubs) ---------------------------------------------

def _boltz_predict(sequence: str, ligand: str | None = None, **_: object) -> dict:
    """TODO: call Boltz with the sequence (and optional ligand) and return the
    predicted structure handle plus a binding score. Placeholder for now."""
    return {
        "status": "not_configured",
        "structure": None,
        "binding_score": None,
        "note": "stub: wire to Boltz on the Predict step",
    }


def _literature_search(query: str, max_results: int = 5, **_: object) -> dict:
    """TODO: call the literature search provider (Tavily / Linkup / MCP) and
    return papers with links. Placeholder for now."""
    return {
        "query": query,
        "results": [],
        "note": "stub: wire to a literature search tool on the Literature step",
    }


def _data_search(query: str, dataset_ids: list[str] | None = None, **_: object) -> dict:
    """TODO: on the live path this is Adaption's hosted ``file_search`` rather
    than a function tool; this stub stands in for offline runs."""
    return {
        "query": query,
        "rows": [],
        "note": "stub: on the live path, use Adaption file_search",
    }


# --- registry -------------------------------------------------------------

TOOLS: dict[str, Tool] = {
    "boltz_predict": Tool(
        name="boltz_predict",
        description="Predict a complex structure. Not molecular dynamics; protein-protein interface confidence is not affinity. This adapter is not configured yet.",
        parameters={
            "type": "object",
            "properties": {
                "sequence": {"type": "string", "description": "Protein sequence."},
                "ligand": {"type": "string", "description": "Optional ligand / substrate."},
            },
            "required": ["sequence"],
        },
        run=_boltz_predict,
    ),
    "literature_search": Tool(
        name="literature_search",
        description="Find papers relevant to a query and return them with links.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
        run=_literature_search,
    ),
    "data_search": Tool(
        name="data_search",
        description="Search the project's imported datasets and cite the rows used.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "dataset_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["query"],
        },
        run=_data_search,
    ),
}


def tool_schemas_for(tool_names: list[str]) -> list[dict]:
    """The schemas for the named tools, to pass as a step's ``tools`` array.

    Raises if a protocol names a tool that is not registered, so a bad config
    fails loudly rather than silently dropping a tool.
    """
    schemas = []
    for name in tool_names:
        if name not in TOOLS:
            raise KeyError(f"unknown tool {name!r}; registered: {sorted(TOOLS)}")
        schemas.append(TOOLS[name].schema())
    return schemas
