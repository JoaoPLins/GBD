# Strategy Game Prototype Plan

## A. Create Base Map
- Create a map of **South America** with provinces. ✅

## B. Import Map into QGIS
Create a **shapefile layer for provinces** with the following attributes:

| Field | Description |
|------|-------------|
| `id` | Unique province ID |
| `owner` | Nation that owns the province |
| `controller` | Nation currently controlling the province |
| `is_ocean` | Boolean value indicating if the province is ocean |
| `terrain` | Terrain type (integer value) |
| `alt` | Altitude value (used later for altitude sickness mechanics) |

### Terrain Values
| Value | Terrain Type |
|------|--------------|
| 0 | Ocean |
| 1 | Flatlands |
| 2 | Hills |
| 3 | Mountain |

Additional attributes may be added later if needed.

## C. First Prototype
- Load the map into the game.
- Implement **province collision detection**.

## D. Gameplay Prototype
- Create **units**.
- Create **buildings**.
- Implement **movement across provinces**.

---

# First Test Goal

The first test should demonstrate:

1. Map loading.
2. Province detection (click / collision).
3. Units moving between provinces.
