"""Launcher / process supervisor (Typer).

``python run.py up`` starts the whole distributed system as separate processes —
broker, registry, controller(s), agent, dashboard and a default device topology —
mirroring a real multi-node deployment (A-01 Verteilung). Every component can
also be started on its own for manual experiments.
"""
from __future__ import annotations

import subprocess
import sys
import time

import typer

from .core import config

app = typer.Typer(add_completion=False, help="Smart-home demonstrator launcher")

PY = sys.executable

DEVICE_MODULES = {
    "light": "smarthome.devices.light",
    "thermostat": "smarthome.devices.thermostat",
    "motion_sensor": "smarthome.devices.motion_sensor",
    "door_lock": "smarthome.devices.door_lock",
    "smart_plug": "smarthome.devices.smart_plug",
    "zigbee_light": "smarthome.devices.zigbee_bridge",
}

# (type, logical_name, area, display_name)
DEFAULT_TOPOLOGY = [
    ("light",         "living_room_light",      "living_room", "Floor Lamp"),
    ("motion_sensor", "living_room_motion",     "living_room", "Living Room PIR"),
    ("thermostat",    "living_room_thermostat", "living_room", "Living Room Thermostat"),
    ("smart_plug",    "living_room_tv_plug",    "living_room", "TV Plug"),
    ("zigbee_light",  "kitchen_zigbee_light",   "kitchen",     "Kitchen Light (Zigbee)"),
    ("motion_sensor", "kitchen_motion",         "kitchen",     "Kitchen PIR"),
    ("light",         "bedroom_light",          "bedroom",     "Bedroom Light"),
    ("thermostat",    "bedroom_thermostat",     "bedroom",     "Bedroom Thermostat"),
    ("door_lock",     "front_door_lock",        "hallway",     "Front Door"),
    ("motion_sensor", "hallway_motion",         "hallway",     "Hallway PIR"),
]


def _spawn(args: list[str]) -> subprocess.Popen:
    return subprocess.Popen([PY, "-m", *args])


@app.command()
def up(controllers: int = typer.Option(1, help="number of controller instances (>=2 demos failover)")):
    """Start broker + services + dashboard + the default device topology."""
    procs: list[subprocess.Popen] = []
    try:
        typer.echo("• starting MQTT broker…")
        procs.append(_spawn(["smarthome.broker"]))
        time.sleep(1.5)

        typer.echo("• starting registry, controller(s), agent…")
        procs.append(_spawn(["smarthome.services.registry"]))
        for i in range(max(1, controllers)):
            procs.append(_spawn(["smarthome.services.controller", "--id", chr(ord('a') + i)]))
        procs.append(_spawn(["smarthome.services.agent"]))
        time.sleep(0.5)

        typer.echo(f"• starting {len(DEFAULT_TOPOLOGY)} simulated devices…")
        for dtype, name, area, disp in DEFAULT_TOPOLOGY:
            procs.append(_spawn([DEVICE_MODULES[dtype], "--name", name,
                                 "--area", area, "--display-name", disp]))

        time.sleep(0.5)
        typer.echo("• starting dashboard…")
        procs.append(_spawn(["smarthome.dashboard.app"]))

        url = f"http://{config.DASHBOARD_HOST}:{config.DASHBOARD_PORT}"
        typer.secho(f"\n  Dashboard ready at {url}   (Ctrl+C to stop)\n", fg="green", bold=True)

        while True:                       # supervise until Ctrl+C
            time.sleep(1.0)
    except KeyboardInterrupt:
        typer.echo("\n• shutting down…")
    finally:
        for p in reversed(procs):
            if p.poll() is None:
                p.terminate()
        time.sleep(1.0)
        for p in procs:
            if p.poll() is None:
                p.kill()


@app.command()
def broker():
    """Run only the MQTT broker."""
    from .broker import main
    main()


@app.command()
def registry():
    """Run only the device registry."""
    from .services.registry import main
    main()


@app.command()
def controller(id: str = typer.Option("a")):
    """Run only an automation controller."""
    from .services.controller import Controller
    Controller(controller_id=id).run()


@app.command()
def agent():
    """Run only the orchestration agent."""
    from .services.agent import main
    main()


@app.command()
def dashboard():
    """Run only the web dashboard."""
    from .dashboard.app import main
    main()


@app.command()
def device(type: str, name: str, area: str, display_name: str = typer.Option(None)):
    """Run a single simulated device, e.g. `device light kitchen_light kitchen`."""
    if type not in DEVICE_MODULES:
        raise typer.BadParameter(f"unknown type; choose from {list(DEVICE_MODULES)}")
    args = [DEVICE_MODULES[type], "--name", name, "--area", area]
    if display_name:
        args += ["--display-name", display_name]
    p = _spawn(args)
    try:
        p.wait()
    except KeyboardInterrupt:
        p.terminate()


@app.command()
def scenario():
    """Run the guided, narrated end-to-end demo."""
    from .scenario import main
    main()


@app.command()
def benchmark(
    out: str = typer.Option("benchmark_report.html", help="HTML report output path"),
    seed: int = typer.Option(42, help="RNG seed for the reproducible latency model"),
    arch: list[str] = typer.Option(None, "--arch", "-a",
                                   help="subset of architectures (edge/cloud/hybrid); repeatable"),
    rooms: int = typer.Option(4, help="number of rooms in the simulated home (4-12)"),
    devices: int = typer.Option(10, help="number of devices in the simulated home (10-40)"),
    open_report: bool = typer.Option(False, "--open", help="open the report in a browser"),
):
    """Benchmark the smart-home architectures (edge/cloud/hybrid) and write a report.

    Runs a fixed natural-language test suite through each architecture over a
    configurable simulated home and reports latency, action correctness, success
    rate and outage robustness — no broker or running components required.
    """
    import webbrowser
    from pathlib import Path

    from .benchmark.report import print_console_summary, render_report_html
    from .benchmark.runner import run_benchmark

    report = run_benchmark(arch_keys=arch or None, seed=seed, rooms=rooms, devices=devices)
    print_console_summary(report)

    path = Path(out)
    path.write_text(render_report_html(report, full_page=True), encoding="utf-8")
    typer.secho(f"\n  HTML report written to {path.resolve()}", fg="green", bold=True)
    if open_report:
        webbrowser.open(path.resolve().as_uri())


if __name__ == "__main__":
    app()
