# Smart-Home Demonstrator (Aufgabe 1b)

A prototypical, **local-first, event-driven** smart-home infrastructure that
implements the reference architecture derived in the research report
[`../HC_1.pdf`](../HC_1.pdf). Several independent components communicate over an
MQTT pub/sub backbone; devices are simulated software mock-ups that behave
realistically and interact over defined interfaces.

The full requirements derivation (A-01…A-23) and the architecture-to-requirement
mapping are in [`Ergebnisbericht.md`](Ergebnisbericht.md).

## Architecture

```
                     ┌──────────────────────────────────────────────┐
                     │             MQTT broker (amqtt)               │   pub/sub backbone
                     │               127.0.0.1:1883                  │   = loose coupling (A-10)
                     └─────▲─────────▲──────────▲──────────▲─────────┘
  retained: descriptor /   │         │          │          │
  state / availability /   │         │          │          │
  announce                 │         │          │          │
   ┌─────────────────┐ ┌───┴────┐ ┌──┴───────┐ ┌┴────────┐ ┌┴─────────────┐
   │ Devices (sim)   │ │Registry│ │Controller│ │  Agent  │ │  Dashboard   │
   │ light · thermo  │ │ SQLite │ │ rule     │ │ Ollama  │ │ FastAPI + WS │
   │ motion · lock   │ │ source │ │ engine + │ │  ·rules │ │ live browser │
   │ plug · zigbee↯  │ │of truth│ │ failover │ │ +guard  │ │      UI      │
   └─────────────────┘ └────────┘ └──────────┘ └─────────┘ └──────────────┘
   persistent identity   persists   local-first  NL → tools   observability
   + idempotent cmds     bindings   automations  + audit
```

Each box is a **separate OS process** (started by the launcher) — there is no
central point of control. Everyone is decoupled through the broker and a shared,
versioned [semantic model](src/smarthome/core/model.py) (Matter-cluster-inspired:
`type` + `capabilities` + a flat `attrs` map).

| Component | Module | Role |
|-----------|--------|------|
| Broker | `smarthome.broker` | Embedded pure-Python MQTT broker (amqtt) |
| Devices | `smarthome.devices.*` | Simulated digital twins; persistent identity, idempotent commands, LWT, auto-reconnect |
| Zigbee bridge | `smarthome.devices.zigbee_bridge` | Normalises a "legacy" cluster-based device onto the common model |
| Registry | `smarthome.services.registry` | Persistent (SQLite) source of truth; re-binds devices **without re-pairing** |
| Controller | `smarthome.services.controller` | Local-first automation engine, auto-discovered rule plugins, leader-election failover |
| Agent | `smarthome.services.agent` | On-device LLM (Ollama) or rule fallback; NL → device commands with guardrails + audit |
| Dashboard | `smarthome.dashboard.app` | FastAPI + WebSocket live UI |

## Quickstart

Requires **Python 3.11+**. From this `demonstrator/` directory:

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (source .venv/bin/activate on Linux/macOS)
pip install -e .                  # installs the package + dependencies

python run.py up                  # starts broker + registry + controller + agent + 10 devices + dashboard
```

Then open **http://127.0.0.1:8000** — you'll see live device tiles, the registry
inventory, an event log, and a text box to talk to the agent.

Press **Ctrl+C** in the terminal to stop everything.

### Guided demo

```bash
python run.py scenario
```

A narrated, reproducible walk-through of: discovery & persistent registration →
local-first automation (motion + dark → light on) → on-device agent
orchestration ("good night") → device reboot & re-bind without re-pairing →
broker outage & auto-reconnect.

## Things to try live

* **Automation** — wait for a motion sensor to fire in a dark room (the day/night
  cycle is ~60 s); the room's light switches on, then off after a quiet period.
* **Natural language** (dashboard input box): `good night`, `make it cozy`,
  `it's cold`, `unlock the front door`, `lights off`, `status`.
* **Persistent registration** — kill one device process and start it again:

  ```bash
  python run.py device light bedroom_light bedroom
  ```
  The registry logs *"device returned, re-bound without re-pairing"* and the
  inventory count stays the same — no duplicate, no re-pairing.
* **Fault tolerance** — stop the broker process; devices go `offline` and keep
  retrying; restart it and everything auto-reconnects. The registry reloads its
  inventory from SQLite, so nothing is forgotten.
* **Controller failover** — run `python run.py up --controllers 2`; kill the
  active controller and watch the standby take over the leader lease.

## On-device AI (optional)

The agent uses a local LLM if [Ollama](https://ollama.com) is reachable, otherwise
it falls back to a deterministic intent parser (so the demo always works):

```bash
ollama serve
ollama pull llama3.1          # model named in the research report (§3.2)
```

Configure via env: `SH_OLLAMA_MODEL` (default `llama3.1:latest`),
`SH_AGENT_BACKEND` = `auto` (default) | `ollama` | `rules`.

## Architecture benchmark

Compare smart-home **architecture variants** by *where AI inference runs* —
**edge** (on-device), **cloud**, or **hybrid** (cloud with on-device fallback). A
fixed suite of natural-language requests is run through each variant and scored on
**latency**, **action correctness**, **success rate** and **robustness during a
cloud/uplink outage**, so the results depend on the chosen architecture.

* **In the dashboard:** click *📊 Architecture benchmark* (top right) or open
  http://127.0.0.1:8000/benchmark — pick the architectures, **size the simulated
  home (rooms & devices)**, and run.
* **Standalone report (no broker/components needed):**

  ```bash
  python run.py benchmark                 # writes benchmark_report.html + a console table
  python run.py benchmark --open          # …and open it in the browser
  python run.py benchmark -a edge -a cloud --seed 7
  python run.py benchmark --rooms 8 --devices 24   # larger simulated home
  ```

The four rooms the suite addresses (`living_room`, `kitchen`, `bedroom`,
`hallway`) are always present, so action correctness stays comparable across home
sizes while latency grows with the device count — the architecture comparison is
about model capability, not home size.

The **edge** model is the deterministic on-device parser; the **cloud** model is a
*simulated* more-capable model (a strict superset of the on-device one). Latency is
a reproducible, seeded model; correctness is measured against gold intents. Plug a
real local model into the cloud role with `SH_BENCH_CLOUD_MODEL=<ollama-model>` and a
running Ollama. The takeaway mirrors the research report: cloud is most capable but
fails during an outage and sends data off-device; edge is private and always
available but more limited; hybrid keeps cloud capability with a local safety net.

## Configuration

All settings have env overrides (see [`core/config.py`](src/smarthome/core/config.py)):
`SH_BROKER_HOST/PORT`, `SH_TOPIC_PREFIX`, `SH_STATE_DIR`, `SH_DASHBOARD_HOST/PORT`,
`SH_OLLAMA_MODEL`, `SH_AGENT_BACKEND`, `SH_LOG_LEVEL`.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

## Broker fallback (Plan B)

The default broker is the embedded pure-Python amqtt. If you prefer the
industry-standard Mosquitto (Docker), run it instead — nothing else changes,
because every component speaks plain MQTT:

```bash
docker run -it --rm -p 1883:1883 eclipse-mosquitto:2 mosquitto -c /mosquitto-no-auth.conf
# then start the components without `broker`, e.g. python run.py registry, etc.
```

## Tech stack

paho-mqtt · amqtt · pydantic v2 · FastAPI + uvicorn · ollama · typer · rich ·
pytest. See [`pyproject.toml`](pyproject.toml).
