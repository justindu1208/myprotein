# Molecular Evidence setup

## Current status and scientific boundary

ChimeraX 1.12 is installed locally at `/Applications/ChimeraX.app`; its version and real PNG graphics probes passed. The existing Tamarind run is rendered with generated `.cxc` scripts (960×720, 30 fps; monomer rotation 6 s, illustrative assembly 17 s). SAMSON remains optional and unconfigured because no SAMSON account/published documents are available. The frontend falls back to actual ChimeraX videos automatically; it never substitutes an unrelated example document.

The main workflow now resolves the entered target through UniProt, submits a real target-specific Tamarind design job, screens actual model outputs, and renders matching structures. See [LIVE_RESEARCH.md](LIVE_RESEARCH.md) for the workflow and limitations. Historical runs are not loaded into the current target view.

For human EGFR, the live workflow uses P00533 extracellular residues 25–645. Imported monomers are extracted bound conformations, not independent monomer predictions. Geometric contacts within 4.5 Å are not automatically hydrogen bonds. Assembly movies are illustrative, not MD trajectories.

## Run locally

From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
cd backend
../.venv/bin/python -m protolab.web --port 8877
```

Open http://127.0.0.1:8877. Build the brief, confirm the resolved target/domain, then start the real Tamarind computation. The viewer displays only structures belonging to that task.

## Register structures

Run these from `backend/`:

```sh
../.venv/bin/python -m protolab.visualizations resolve-target P00533 --species 'Homo sapiens'
../.venv/bin/python -m protolab.visualizations import-tamarind /absolute/path/to/results.json
../.venv/bin/python -m protolab.visualizations check
```

The Tamarind importer accepts the existing cached results schema (`jobName`, `target_sequence`, `candidates`, `structures`). It validates sequences and chain mappings before writing normalized mmCIF/PDB files. It does not submit new paid jobs. Registry data lives in `runs/visualizations/<run>/manifest.json`; preserve source job IDs and hashes.

Each manifest has `target` and `candidates[id]`. Candidate entries contain separate `monomer`, `complex`, `target_chains`, `binder_chains`, and optional geometric `interface` data. Asset entries include `role`, `sha256`, source/provenance, predicted flag, and PDB/mmCIF URLs. Every displayed candidate must be backed by matching real outputs.

## SAMSON publication

Official workflow: import the matching structures in SAMSON, prepare the view, then use Home → Publish. Choose the visibility appropriate to the data. Do not publish private structures without authorization. See [publication documentation](https://documentation.samson-connect.net/users/latest/share-documents/) and [documents](https://documentation.samson-connect.net/users/latest/documents/).

There is no assumed upload REST API. After publishing the exact scientific object, register its official document URL:

```sh
../.venv/bin/python -m protolab.visualizations link-samson RUN CANDIDATE monomer 'https://www.samson-connect.net/documents/DOCUMENT-UUID' --preset cartoon
```

Repeat for `complex`, and for candidate `target` with role `target`. Supported presets: `cartoon`, `surface`, `interface`, `target_only`, `binder_only`, `full_complex`. Each preset may point to a separately prepared published view. Representation controls choose published views; they cannot manipulate cross-origin iframe internals. Registration does not prove the document contents match the structure: the publisher must verify this. Access errors can occur despite iframe load firing; use Show fallback if blocked.

## ChimeraX worker

Install from the [official UCSF download page](https://www.rbvi.ucsf.edu/chimerax/download.html) under the appropriate license. Configure the executable before starting the server:

```sh
export CHIMERAX_EXECUTABLE='/Applications/ChimeraX.app/Contents/MacOS/ChimeraX'
../.venv/bin/python -m protolab.visualizations check
../.venv/bin/python -m protolab.web --port 8877
```

macOS uses desktop graphics; a GUI may appear. `--offscreen` is Linux-only and still needs working EGL/OpenGL. A version probe and real PNG graphics probe must succeed. See [command-line options](https://www.cgl.ucsf.edu/chimerax/docs/user/options.html) and [movie commands](https://www.cgl.ucsf.edu/chimerax/docs/user/commands/movie.html).

Click Render with ChimeraX. One worker processes at most four admitted jobs, with a 300-second job timeout. Cache identity includes structure bytes, parameters, script version and ChimeraX version. Outputs include PNG, MP4, `.cxc`, metadata, input/output hashes and source job ID. Failed jobs can be retried; unchanged successful jobs are reused. No ChimeraX REST service is exposed.

## API

- `GET /api/visualizations`: archived runs and worker capability
- `POST /api/visualizations/resolve`: accession/species → verified target manifest
- `GET /api/visualizations/{run}/manifest`
- `GET /api/visualizations/{run}/{candidate}/status?preset=cartoon`
- `POST /api/visualizations/{run}/{candidate}/render`: JSON preset
- `GET /api/visualizations/{run}/{candidate}/{role}.cif` (or `.pdb`)
- `GET /api/visualizations/{run}/{candidate}/renders/{cache_key}/{artifact}`
- `POST /api/visualizations/check`: refresh installed-renderer capability

Treat this server as localhost-only. It is not a production multiuser/authenticated job service. Identifiers, paths, roles, chains, residues and preset names are validated; no arbitrary shell commands or external structure URLs are accepted by these routes.

## Validation

```sh
cd backend
../.venv/bin/python -m pytest -q
# From repository root, with Node installed:
node frontend/tests/molecular-evidence.test.cjs
```

Python coverage includes role separation, structure/hash validation, path traversal and command injection rejection, cache identity, retries and queue idempotency. JS tests cover duplicate category winners, unpublished documents and iframe failure/timeout fallback. Browser checks cover target resolution, winner tabs, real monomer/complex download switching, independent sliders and responsive layout. ChimeraX 1.12 has executed the real structure rendering scripts successfully. Published SAMSON interaction remains pending an account and document publication.


## Sharing and another computer

There are two separate use cases:

1. **Watch existing results:** copy the source and `runs/visualizations/<run>` with its manifests, structures, metadata and media. Install Python requirements and start the local server. No Tamarind key, ChimeraX installation or SAMSON account is needed for existing videos. Cache lookup validates inputs, presets and checksums before using media rendered on another machine. The recorded ChimeraX version remains in provenance.
2. **Generate new media:** install ChimeraX under its license, configure `CHIMERAX_EXECUTABLE` if not autodetected, and pass the graphics probe. Use the render button or the batch command below. New Tamarind computations additionally require that user's own API key/account.

From the repository root:

```sh
sh scripts/start-local.sh
# Package only code and this run's verified media; excludes .env and raw API caches:
.venv/bin/python scripts/export-viewer.py RUN /absolute/path/protolab-viewer.zip
```

On Windows, run `scripts/start-local.cmd` after installing Python 3, or use the equivalent Python venv/pip commands above and `python -m protolab.web --port 8877` from `backend/`. The shell launcher is for macOS/Linux. The web page is served locally, not by double-clicking index.html.

Batch rendering from `backend/`:

```sh
../.venv/bin/python -m protolab.visualizations render-run RUN
# Or one candidate:
../.venv/bin/python -m protolab.visualizations render-run RUN --candidate design-1
```

The root page resolves the default mature IL-2 brief and reattaches its matching saved task. Changing the target clears the previous view immediately. Archived URL query parameters are not used to substitute unrelated results.

The local address `127.0.0.1` is not remotely accessible. To let others browse without running anything, host the app/media on a server. Production hosting, authentication and shared compute quotas are separate deployment work; this local server is not exposed publicly. SAMSON document access must separately be granted to the viewers. Do not redistribute the ChimeraX application inside the viewer ZIP.
