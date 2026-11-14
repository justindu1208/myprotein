"""Protolab: a protocol-driven research workbench.

Public surface:
    load_protocol / load_protocols  - read protocol config files
    Protocol, Step                  - the config, as objects
    ProjectRecord                   - the shared context every step reads/writes
    run_step                        - one step agent call
    TOOLS                           - the tool registry
"""

from .protocols import Protocol, Step, load_protocol, load_protocols
from .record import ProjectRecord, StepEntry
from .agents import run_step, build_instructions
from .tools import TOOLS, tool_schemas_for

__all__ = [
    "Protocol",
    "Step",
    "load_protocol",
    "load_protocols",
    "ProjectRecord",
    "StepEntry",
    "run_step",
    "build_instructions",
    "TOOLS",
    "tool_schemas_for",
]
