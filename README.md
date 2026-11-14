# Protolab

A research workbench that takes a question through one full round of a research
**protocol** — question → literature → hypothesis → design → predict → analyse —
with one agent per step and a single shared project record that every step reads
and writes.

Built for the Imperial AI Hackathon (Nov 2026).

## The idea in one line

It doesn't answer a question. It walks you through a round of research and leaves
a record where every conclusion can be traced back to the data and the step it
came from.

## Why it is not "six chat boxes"

Three things carry the product, and all three are ours to build:

1. **Protocol as config.** A protocol is a JSON file listing each step's role,
   what it reads, what it writes, and which tools it may call. The app renders the
   step bar and drives the agents straight from that file. A new research
   direction is a new config, not new code. See [`protocols/`](protocols/) and
   [`schema/protocol.schema.json`](schema/protocol.schema.json).
2. **A shared project record.** Each step writes a structured entry; later steps
   read it. Change an upstream entry and the downstream steps are marked stale.
   See [`backend/protolab/record.py`](backend/protolab/record.py).
3. **Per-step output views.** A hypothesis card, a plan table, a 3D structure, a
   ranked result — each step's main panel is its output, not a transcript.
   (Frontend; the clickable prototype lives as a Claude artifact — see
   [`frontend/README.md`](frontend/README.md).)

## Architecture

```
            ┌─────────────── one Adaption inference stack ───────────────┐
 user ⟷ step agent (role + shared record + allowed tools)  →  writes entry
            └────────────────────────────────────────────────────────────┘
                     │ file_search            │ function tools
                     ▼                        ▼
              your datasets            Boltz (predict), literature search
```

- **Reasoning + data search + memory:** Adaption inference stacks. One stack,
  six roles — each step call passes a different `instructions` (its role) plus the
  shared record. `file_search` lets any step cite rows from imported data.
- **Prediction:** Boltz, wired in as a function tool on the Predict step.
- **Literature search:** an external tool (e.g. Tavily / Linkup), wired in as a
  function tool or MCP server.
- **Everything else — the protocol engine, the project record, the per-step
  views — is in this repo.**

## Sponsor fit

Protolab is a workbench **on top of** Adaption, not a copy of it. Adaption's
AutoScientist produces a trained model; Protolab's protocol produces a research
conclusion. Reasoning, data search and memory all run on Adaption inference
stacks.

## Layout

| Path | What |
|------|------|
| `protocols/` | Protocol templates (the core concept, as JSON) |
| `schema/protocol.schema.json` | What a protocol file must contain |
| `backend/protolab/` | Protocol engine, project record, step agents, tools |
| `backend/tests/` | Tests that run with no network |
| `frontend/` | UI (prototype currently a Claude artifact) |

## Quickstart (backend)

```bash
cd backend
python -m pip install -r requirements.txt
python -m pytest            # runs offline
```

Running a real step needs an Adaption API key and a stack configured in the
Adaption app (the API can call a stack but not create one):

```bash
export ADAPTION_API_KEY=...        # from the Adaption app
export PROTOLAB_STACK=stack:your-slug
python -m protolab.demo            # one step against the live model
```

## Status

Early scaffold. The protocol engine, record and tool interfaces are in place;
step roles and the prediction wiring are stubbed and marked `TODO`.
