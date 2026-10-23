# Memory Systems Lab

A local web dashboard for exploring demand paging and TLB address translation, alongside live memory statistics from your own computer. Built with Python, Flask, psutil, and plain HTML/CSS/JavaScript. There is no frontend build step, external CDN, or database.

## Run on Windows

Double-click **Start.bat**. It creates a local `.venv` if needed, installs the two dependencies, starts the server, and opens your browser at **http://127.0.0.1:5000**. The environment in this project is already prepared on this machine.

Keep the terminal window open while using the dashboard. Press **Ctrl+C** to stop it. If port 5000 is occupied:

```powershell
.\Start.ps1 -Port 5001
```

To start without opening a browser:

```powershell
.\Start.ps1 -NoBrowser
```

The launcher requires Python 3.10 or newer. It also recognizes the bundled Codex Python runtime when available.

## Manual setup / Linux / macOS

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py --open
```

Use `python3` instead of `python` if required by your system. To use the existing Windows environment directly:

```powershell
.\.venv\Scripts\python.exe app.py
```

## Explore the simulator

1. Click **Step** to translate the next address, or **Run sequence** to play the trace. Pause and change playback speed at any time between accesses.
2. Try **Locality** for repeated page access, **Thrashing** for a working set that exceeds physical capacity, or **Random**. Loading a pattern resets memory and counters.
3. Translate a single decimal or `0x` hexadecimal address, or load a **Custom** sequence of up to 128 addresses. Manual accesses add to the same simulation without advancing the trace cursor.
4. Follow the translation diagram, exact address bit split, and explanation of every lookup and allocation. Inspect the TLB, full page table, and physical frames.
5. Use **Edit** to change page size, virtual pages, frames, TLB capacity, both replacement policies, and timing. Applying changes starts a cold run. The trace is preserved when page size and address range allow it, so comparisons can use the same input.
6. Export the complete run as CSV. The dashboard displays the latest 60 accesses; export contains all of them (up to 10,000 per run).

Default configuration: 16 virtual pages × 1,024 bytes, 4 physical frames, 4 TLB entries, and LRU for both replacement policies. TLB lookup is 10 ns, memory access 100 ns, and page-fault service 1,000,000 ns (1 ms).

The simulator starts with empty memory. A TLB miss does not always mean a page fault. A page fault occurs only when the page is not resident. Page eviction invalidates its cached mapping; TLB eviction does not evict the physical page. LRU uses the most recent access, including TLB hits, while FIFO uses original insertion order.

## Timing model

For TLB lookup **t**, one memory access **m**, and fixed page-fault service **p**:

| Result | Cost |
| --- | --- |
| TLB hit | t + m |
| TLB miss, page resident | t + 2m |
| TLB miss, page fault | t + 2m + p |

Effective access time is the arithmetic mean of all actual simulated access costs. The translation-only average excludes fault service. Overall speedup is the no-TLB average (**2m**, plus identical fault costs) divided by the simulated average. Large fault costs can mask TLB benefits; set fault service to zero to study translation alone. All times are modeled, not measured hardware latencies. Page loading is included in the fixed fault penalty, without an additional retry lookup.

The model uses a single process, a single-level page table, read accesses, and a single TLB. It omits writes, dirty bits, hardware caches, permissions, actual I/O, and multilevel paging. It never allocates the simulated RAM on your computer.

## Live system monitor

The monitor samples RAM, swap/page file, and visible processes every two seconds. It includes a rolling two-minute RAM chart, allocation summary, pause/resume, process search by name or PID, sorting, and pagination. Monitoring waits while the browser tab is hidden. A shared one-second backend cache avoids redundant process scans across clients.

- Used RAM is **total − available**. Available includes reclaimable memory; it is different from completely free memory.
- Process memory is RSS (resident physical memory), with virtual memory reported separately. Shared pages can be counted by more than one process, so summing RSS does not reproduce system usage.
- Protected or rapidly exiting processes may be skipped. Swap and virtual-memory semantics vary by operating system, following psutil.
- If Windows swap performance counters are unavailable, swap is labeled unavailable while RAM and process monitoring continue.
- Units use powers of 1,024 (KB, MB, GB labels).

## Tests

Tests use Python's standard library; no additional test package is needed.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Coverage includes exact address arithmetic and timings, LRU/FIFO page and TLB replacement, stale-entry invalidation, randomized mapping invariants, validation, separate browser sessions, reset behavior, CSV export, real psutil snapshots, and API failure paths.

## Project layout

```text
app.py                  Flask routes, session isolation, local API protection
simulator.py            Deterministic paging and TLB model
monitor.py              Read-only psutil sampling
templates/index.html    Simulator, monitor, and dialogs
static/app.js           Interactions, playback, polling, chart, process explorer
static/styles.css       Responsive interface and reduced-motion support
tests/                  Simulator and API tests
Start.bat / Start.ps1    Windows launcher and environment setup
requirements.txt        Runtime dependencies
```

## API

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/api/simulator` | GET | State and recent access history |
| `/api/simulator/translate` | POST | Translate `{"address": 1048}` |
| `/api/simulator/config` | POST | Apply configuration and reset; omitted fields use defaults |
| `/api/simulator/reset` | POST | Clear memory and statistics, retaining configuration |
| `/api/simulator/export` | GET | Complete chronological CSV trace |
| `/api/system` | GET | Live machine memory and process snapshot |
| `/api/health` | GET | Server health |

Simulation state is stored in server memory, isolated by a signed browser-session cookie, and reset when the server restarts. Idle sessions expire after two hours; at most 128 are retained. Browsers sharing a cookie share a simulation. No monitoring history or process data is written to disk. CSV is downloaded only when requested.

The server binds to loopback, rejects foreign hosts and origins, and runs with the debugger disabled. It is intended for local learning. A remote deployment would report the remote host's RAM, not the visitor's PC.

## References

- [Flask documentation](https://flask.palletsprojects.com/en/stable/)
- [psutil memory and process documentation](https://psutil.readthedocs.io/en/latest/)
- [Operating Systems: Three Easy Pieces — free textbook](https://pages.cs.wisc.edu/~remzi/OSTEP/)
