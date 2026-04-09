import threading
import time
import heapq
import random


class Simulation(threading.Thread):
	"""Background simulation loop running independently from render framerate."""

	def __init__(self, nation_manager, game_map, armies, tick_seconds: float = 1.0, speed_multiplier: float = 1.0):
		super().__init__(daemon=True)
		self.nation_manager = nation_manager
		self.game_map = game_map
		self.armies = armies

		# One simulation tick represents one in-game hour.
		self.tick_seconds = max(0.01, float(tick_seconds))
		self.speed_multiplier = max(0.0, float(speed_multiplier))

		self.tick_count = 0
		self.current_hour = 0
		self.current_day = 0
		self.current_month = 0
		self.current_year = 0 
		self.start_date = (1904, 1, 1)  # (year, month, day)
		
		self.moviment_list = []
		self.moviment_time = []
		self.combat_list = []
		# [unit_id, ticks_remaining] — units waiting to enter Moving status
		self.mobilization_queue = []

		self._stop_event = threading.Event()
		self._pause_event = threading.Event()
		self._state_lock = threading.Lock()

	def run(self) -> None:
		"""Main simulation loop based on monotonic time."""
		next_tick_time = time.monotonic()

		while not self._stop_event.is_set():
			if self._pause_event.is_set() or self.speed_multiplier <= 0.0:
				time.sleep(0.02)
				next_tick_time = time.monotonic()
				continue

			tick_interval = self.tick_seconds / self.speed_multiplier
			now = time.monotonic()

			if now >= next_tick_time:
				self._advance_one_tick()
				next_tick_time += tick_interval

				# If delayed, recover smoothly without executing an excessive burst.
				if now - next_tick_time > tick_interval:
					next_tick_time = now + tick_interval
			else:
				time.sleep(min(0.01, next_tick_time - now))

	def _advance_one_tick(self) -> None:
		"""Advance simulation by one in-game hour."""
		with self._state_lock:
			self.tick_count += 1

			# Time representation
			self.current_hour += 1
			if self.current_hour >= 24:
				self.current_hour = 0
				self.current_day += 1
				if self.current_day > 30:
					self.current_day = 1
					self.current_month += 1
					if self.current_month > 12:
						self.current_month = 1
						self.current_year += 1

			# - self.game_map
			# - self.nation_manager
			# - self.armies

		self._process_mobilization()
		self._process_movements()
		self.Unit_spotting()
		#self.combat()

	def _process_mobilization(self) -> None:
		"""Tick down mobilization delays and promote units to Moving status when ready."""
		with self._state_lock:
			unit_ids = [entry[0] for entry in self.mobilization_queue if entry]

		for unit_id in unit_ids:
			with self._state_lock:
				idx = next((i for i, e in enumerate(self.mobilization_queue) if e and e[0] == unit_id), None)
				if idx is None:
					continue
				self.mobilization_queue[idx][1] -= 1
				if self.mobilization_queue[idx][1] <= 0:
					del self.mobilization_queue[idx]
					unit = self._find_unit_by_id(unit_id)
					if unit is not None:
						unit.status = 3
						unit.counter = 0

	def _find_unit_by_id(self, unit_id):
		"""Find a unit object across all armies by unit ID."""
		for army in self.armies.values():
			unit = army.get_unit(unit_id)
			if unit is not None:
				return unit
		return None

	def _movement_ticks_for_unit(self, unit) -> int:
		"""Return ticks required for one movement step."""
		speed_value = getattr(unit, "speed", 1)
		try:
			speed_value = float(speed_value)
		except (TypeError, ValueError):
			speed_value = 1.0
		if speed_value <= 0:
			return 16
		return max(1, int(round(16.0 / speed_value)))

	def _find_movement_index(self, unit_id):
		for idx, movement in enumerate(self.moviment_list):
			if movement and movement[0] == unit_id:
				return idx
		return None

	def _find_timer_index(self, unit_id):
		for idx, timer_entry in enumerate(self.moviment_time):
			if timer_entry and timer_entry[0] == unit_id:
				return idx
		return None

	def _process_movements(self) -> None:
		"""Tick movement countdowns for all queued units."""
		with self._state_lock:
			unit_ids = [entry[0] for entry in self.moviment_time if entry]

		for unit_id in unit_ids:
			self.moveunit(unit_id)


	def set_speed(self, multiplier: float) -> None:
		"""Set simulation speed multiplier (0 pauses progression)."""
		with self._state_lock:
			self.speed_multiplier = max(0.0, float(multiplier))

	def get_speed(self) -> float:
		with self._state_lock:
			return self.speed_multiplier

	def pause(self) -> None:
		self._pause_event.set()

	def resume(self) -> None:
		self._pause_event.clear()

	def toggle_pause(self) -> bool:
		"""Toggle pause state. Returns True if paused after toggle."""
		if self._pause_event.is_set():
			self._pause_event.clear()
			return False
		self._pause_event.set()
		return True

	def is_paused(self) -> bool:
		return self._pause_event.is_set()

	def stop(self) -> None:
		self._stop_event.set()

	def get_state_snapshot(self) -> dict:
		"""Return thread-safe counters for UI/debug display."""
		with self._state_lock:
			return {
				"tick_count": self.tick_count,
				"current_hour": self.current_hour,
				"current_day": self.current_day,
				"current_month": self.current_month,
				"current_year": self.current_year,
				"speed_multiplier": self.speed_multiplier,
				"paused": self._pause_event.is_set(),
			}

	def moveunit(self, unit_id):
		"""Advance one queued movement step for a unit when timer reaches zero."""
		with self._state_lock:
			timer_idx = self._find_timer_index(unit_id)
			movement_idx = self._find_movement_index(unit_id)

			if timer_idx is None or movement_idx is None:
				return False

			unit = self._find_unit_by_id(unit_id)
			if unit is None:
				del self.moviment_list[movement_idx]
				del self.moviment_time[timer_idx]
				return False

			# Resting phase (status 4): count 6 ticks then resume moving
			if unit.status == 4:
				unit.counter += 1
				if unit.counter >= 6:
					unit.counter = 0
					unit.status = 3
				return False

			# Only process movement when status is Moving (3)
			if unit.status != 3:
				return False

			# Count moving ticks; after 8, force a rest
			unit.counter += 1
			if unit.counter >= 8:
				unit.counter = 0
				unit.status = 4
				return False

			# Decrement per-province-step timer
			self.moviment_time[timer_idx][1] -= 1
			if self.moviment_time[timer_idx][1] > 0:
				return False

			# Step to next province
			movement = self.moviment_list[movement_idx]
			if len(movement) <= 1:
				del self.moviment_list[movement_idx]
				del self.moviment_time[timer_idx]
				unit.status = 1
				unit.counter = 0
				return False

			next_province_id = movement[1]
			unit.location = next_province_id
			del movement[1]

			if len(movement) == 1:
				del self.moviment_list[movement_idx]
				del self.moviment_time[timer_idx]
				unit.status = 1
				unit.counter = 0
			else:
				self.moviment_time[timer_idx][1] = self._movement_ticks_for_unit(unit)

			return True
	
	def get_unit_by_location(self, province_id):
		"""Return list of units currently located in the specified province."""
		units_in_province = []
		for army in self.armies.values():
			for unit in army.units.values():
				if unit.location == province_id:
					units_in_province.append(unit)
		return units_in_province

	def _get_root_nation_tag(self, nation_tag):
		"""Return the top-level nation tag for a nation/substate chain."""
		if not nation_tag or self.nation_manager is None:
			return nation_tag

		current_tag = nation_tag
		visited = set()
		while current_tag and current_tag not in visited:
			visited.add(current_tag)
			nation = self.nation_manager.get_nation(current_tag)
			if nation is None or not nation.parent:
				return current_tag
			current_tag = nation.parent

		return nation_tag

	def _same_side(self, unit_a, unit_b):
		return self._get_root_nation_tag(unit_a.nation) == self._get_root_nation_tag(unit_b.nation)

	def _spot_units_in_province(self, spotter, province_id, spotting_index):
		#spotting_index: 0 for nearby provinces, 1 for same province (higher chance)
		units_in_province = self.get_unit_by_location(province_id)
		for unit in units_in_province:
			if unit.id == spotter.id or self._same_side(unit, spotter) or unit.id in spotter.units_spoted:
				continue
			print(f"{spotter.name} is attempting to spot {unit.name} in province {province_id}...")	
			spotting_power = spotter.unit_spotting[spotting_index] + (spotter.soldiers // 100)
			spot_chance = (spotting_power // max(1, unit.visibility)) + 1
			if random.randint(0, 100) < spot_chance:
				spotter.units_spoted.append(unit.id)
				spotter.unitCurrentSpoting += 1
				print(f"{spotter.name} spotted {unit.name} in province {province_id}! (chance {spot_chance}%)")
				

	def spotting(self, spotter, province_id):
		# First check for units in the same province.
		self._spot_units_in_province(spotter, province_id, 1)

		# Now check for units in nearby provinces.
		province = self.game_map.get_province_by_id(province_id)
		if not province:
			return

		for nearby_province_id in province.get("nearby_provinces", []):
			self._spot_units_in_province(spotter, nearby_province_id, 0)

	def Unit_spotting(self):
		for army in self.armies.values():
			for unit in army.units.values():
				unit.update_spotting()
				self.spotting(unit, unit.location)

	def combat(self, province_id):
		pass
	
	def activeCombat(self, unit_ida, unit_idb, province_id):
		pass

	def _is_water_province(self, province) -> bool:
		"""Return True when the province is considered water for pathing."""
		if not province:
			return False

		is_water = province.get("is_water")
		if isinstance(is_water, bool):
			return is_water
		if isinstance(is_water, (int, float)):
			return bool(is_water)
		if isinstance(is_water, str):
			return is_water.strip().lower() in {"1", "true", "t", "yes", "y", "water"}

		terrain = province.get("terrain")
		if isinstance(terrain, str):
			return terrain.strip().lower() == "water"

		return False
	
	def pathing(self, unit_id, destination_province_id):
		"""Queue shortest path movement using A* over already-loaded nearby provinces."""
		with self._state_lock:
			unit = self._find_unit_by_id(unit_id)
			if unit is None:
				return []

			start_province_id = unit.location
			if start_province_id == destination_province_id:
				return [start_province_id]

			destination_province = self.game_map.get_province_by_id(destination_province_id)
			if destination_province is None or self._is_water_province(destination_province):
				return []

			open_heap = []
			heapq.heappush(open_heap, (0, start_province_id))

			came_from = {}
			g_cost = {start_province_id: 0}

			while open_heap:
				_, current = heapq.heappop(open_heap)

				if current == destination_province_id:
					break

				province = self.game_map.get_province_by_id(current)
				if province is None:
					continue

				for neighbor in province.get("nearby_provinces", []):
					neighbor_province = self.game_map.get_province_by_id(neighbor)
					if neighbor_province is None or self._is_water_province(neighbor_province):
						continue

					tentative_cost = g_cost[current] + 1
					if tentative_cost < g_cost.get(neighbor, float("inf")):
						came_from[neighbor] = current
						g_cost[neighbor] = tentative_cost
						# Heuristic is 0 for now -> Dijkstra behavior (shortest hops).
						heapq.heappush(open_heap, (tentative_cost, neighbor))

			if destination_province_id not in g_cost:
				return []

			path = [destination_province_id]
			while path[-1] != start_province_id:
				path.append(came_from[path[-1]])
			path.reverse()

			# Store movement queue as requested: [unit_id, next_province, ..., objective]
			route_entry = [unit_id] + path[1:]

			# Determine when the unit can start moving based on current status
			if unit.status == 1:  # Active -> start moving immediately
				unit.status = 3
				unit.counter = 0
			elif unit.status != 3:  # Not already moving -> apply mobilization delay
				delay = 72 if unit.status == 0 else 12
				# Replace any existing mobilization entry for this unit
				mob_idx = next((i for i, e in enumerate(self.mobilization_queue) if e and e[0] == unit_id), None)
				if mob_idx is not None:
					self.mobilization_queue[mob_idx][1] = delay
				else:
					self.mobilization_queue.append([unit_id, delay])

			existing_movement_idx = self._find_movement_index(unit_id)
			existing_timer_idx = self._find_timer_index(unit_id)

			if existing_movement_idx is not None:
				self.moviment_list[existing_movement_idx] = route_entry
			else:
				self.moviment_list.append(route_entry)

			ticks_for_step = self._movement_ticks_for_unit(unit)
			timer_entry = [unit_id, ticks_for_step]

			if existing_timer_idx is not None:
				self.moviment_time[existing_timer_idx] = timer_entry
			else:
				self.moviment_time.append(timer_entry)

			return path
	
    



