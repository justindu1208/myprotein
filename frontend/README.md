# Frontend

The clickable prototype currently lives as a Claude design artifact (platform
shell + protocol workspace + shared project record + per-step output views).
It is the reference for what the real UI should render from the protocol config
and the project record.

When the hackathon frontend is built here, it should:

1. Read a protocol config (`../protocols/*.json`) and render the step bar from it.
2. Keep the shared project record in view (the side panel), updating as each step
   writes.
3. Give each step its own output view (hypothesis card, plan table, 3D structure,
   ranked results) rather than a bare chat transcript.
4. Mark downstream steps stale when an upstream entry changes.

Framework is undecided — pick on the day. The backend exposes the engine; the
frontend calls it per step.
