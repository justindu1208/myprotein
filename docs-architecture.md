# Architecture notes

## The three layers

1. **Protocol (config).** `protocols/*.json`. Each step declares its role, what it
   reads, what it writes, and which tools it may call. The engine and UI are
   driven by this file, so a new research direction is a new config.
2. **Project record (state).** `backend/protolab/record.py`. One structured entry
   per step. Steps read the entries in their `reads`. Changing an upstream entry
   marks dependents stale (cascading). This is how "shared context" is made
   visible and how the loop (analyse → next hypothesis) is supported.
3. **Step agents (compute).** `backend/protolab/agents.py`. One Adaption inference
   stack; each step is one call whose `instructions` = role + the record it reads,
   and whose `tools` = the schemas for the tools it may call.

## How a protocol is generated (planned)

The user describes a task; the model returns a protocol config assembled from the
known step types and registered tools (not invented from scratch), which the user
can edit before starting. Preset templates give the most polished experience;
generated protocols are usable but plainer.

## Adaption specifics (from the docs)

- A stack is called with `model="stack:<slug>"`; it bundles model, tools,
  datasets and memory. Stacks are created in the app; the API only calls them.
- Per-request `instructions` is supported — this is what carries each step's role.
- `file_search` (hosted) searches imported datasets and cites rows.
- Function tools run our code (Boltz prediction, literature search); remote MCP
  servers are also supported (`server_label` + `server_url`, approval by default).
- Agentic memory is built after a response completes, so it is a bonus, not the
  mechanism for passing context between steps — the project record is.
