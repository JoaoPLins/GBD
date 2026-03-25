import threading
import time
import heapq


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

		self._process_movements()

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
			return 1
		return max(1, int(round(1.0 / speed_value)))

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

			self.moviment_time[timer_idx][1] -= 1
			if self.moviment_time[timer_idx][1] > 0:
				return False

			movement = self.moviment_list[movement_idx]
			if len(movement) <= 1:
				del self.moviment_list[movement_idx]
				del self.moviment_time[timer_idx]
				return False

			next_province_id = movement[1]
			unit = self._find_unit_by_id(unit_id)
			if unit is None:
				del self.moviment_list[movement_idx]
				del self.moviment_time[timer_idx]
				return False

			unit.location = next_province_id
			del movement[1]

			if len(movement) == 1:
				del self.moviment_list[movement_idx]
				del self.moviment_time[timer_idx]
			else:
				self.moviment_time[timer_idx][1] = self._movement_ticks_for_unit(unit)

			return True
	

	def combat(self, province_id):
		pass
	
	def pathing(self, unit_id, destination_province_id):
		"""Queue shortest path movement using A* over already-loaded nearby provinces."""
		with self._state_lock:
			unit = self._find_unit_by_id(unit_id)
			if unit is None:
				return []

			start_province_id = unit.location
			if start_province_id == destination_province_id:
				return [start_province_id]

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
	
    



