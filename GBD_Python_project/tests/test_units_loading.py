#!/usr/bin/env python3
"""Quick test to verify units loading functionality."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from GBD_Python.units import load_starting_units

def main() -> None:
    armies = load_starting_units()

    print("=" * 60)
    print("ARMIES LOADED")
    print("=" * 60)

    for army_id, army in armies.items():
        print(f"\nArmy {army_id} (Nation: {army.nation})")
        print("-" * 40)

        for unit in army.get_all_units():
            print(f"  Unit ID: {unit.id}")
            print(f"    Name: {unit.name}")
            print(f"    Location (Province): {unit.location}")
            print(f"    Home Province: {unit.home}")
            print(f"    Soldiers: {unit.soldiers}")
            print(f"    Stats - Attack: {unit.attack}, Defense: {unit.defense}")
            print(f"    Speed: {unit.speed}, Logistics: {unit.logistics}")
            print(f"    Supply: {unit.suply}")
            print()

    print("=" * 60)


if __name__ == "__main__":
    main()
