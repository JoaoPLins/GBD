import threading
import time
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from GBD_Python.gameMap import Map
from GBD_Python.nations import NationManager
from GBD_Python.simulation import Simulation
from GBD_Python.units import load_starting_units


def build_game_data():
    """Load map, nations, and units for simulation testing."""
    root = PROJECT_ROOT

    game_map = Map(0, 0)
    geojson_path = root / "QgizFiles" / "provinces.geojson"
    nearby_csv_path = root / "QgizFiles" / "nearby_provinces.csv"
    game_map.load_provinces(str(geojson_path), str(nearby_csv_path))

    nation_manager = NationManager()
    nations_json_path = root / "QgizFiles" / "nations.json"
    nation_manager.load_from_json(str(nations_json_path))

    armies = load_starting_units()
    return nation_manager, game_map, armies


def print_loop(simulation: Simulation, stop_event: threading.Event) -> None:
    """Print simulation state once per second."""
    while not stop_event.is_set():
        state = simulation.get_state_snapshot()
        print(
            f"STATE | ticks={state['tick_count']} "
            f"hour={state['current_hour']} "
            f"speed={state['speed_multiplier']:.2f}x "
            f"paused={state['paused']}"
        )
        time.sleep(1.0)


def main() -> None:
    nation_manager, game_map, armies = build_game_data()

    simulation = Simulation(
        nation_manager=nation_manager,
        game_map=game_map,
        armies=armies,
        tick_seconds=1.0,
        speed_multiplier=1.0,
    )

    # Match game behavior: start paused.
    simulation.pause()
    simulation.start()

    stop_print = threading.Event()
    printer = threading.Thread(target=print_loop, args=(simulation, stop_print), daemon=True)
    printer.start()

    print("Simulation test started.")
    print("Commands: status, speed <num>, faster, slower, pause, resume, toggle, stop, help")

    try:
        while True:
            command = input("> ").strip().lower()

            if command == "status":
                print(simulation.get_state_snapshot())
            elif command.startswith("speed "):
                value_str = command.split(" ", 1)[1].strip()
                try:
                    value = float(value_str)
                except ValueError:
                    print("Invalid speed value.")
                    continue
                simulation.set_speed(value)
                print(f"Speed set to {simulation.get_speed():.2f}x")
            elif command == "faster":
                new_speed = simulation.get_speed() + 0.5
                simulation.set_speed(new_speed)
                print(f"Speed set to {simulation.get_speed():.2f}x")
            elif command == "slower":
                new_speed = max(0.0, simulation.get_speed() - 0.5)
                simulation.set_speed(new_speed)
                print(f"Speed set to {simulation.get_speed():.2f}x")
            elif command == "pause":
                simulation.pause()
                print("Simulation paused.")
            elif command == "resume":
                simulation.resume()
                print("Simulation resumed.")
            elif command == "toggle":
                paused = simulation.toggle_pause()
                print(f"Simulation {'paused' if paused else 'resumed'}.")
            elif command in {"stop", "quit", "exit"}:
                print("Stopping simulation...")
                break
            elif command == "help":
                print("Commands: status, speed <num>, faster, slower, pause, resume, toggle, stop")
            elif command == "":
                continue
            else:
                print("Unknown command. Type 'help'.")
    finally:
        stop_print.set()
        simulation.stop()
        simulation.join(timeout=2.0)


if __name__ == "__main__":
    main()
