import threading
import time
import heapq
import random
from collections import deque
from dataclasses import dataclass, field

from people import PeopleManager


PRIORITY_CRITICAL = 5
PRIORITY_HIGH = 4
PRIORITY_NORMAL = 3
PRIORITY_LOW = 2
PRIORITY_RESERVE = 1


@dataclass
class LogisticsRequest:
	request_id: str
	unit_id: str
	nation: str
	location: int
	supply_needed: int
	ammo_needed: int
	priority: int


@dataclass
class LogisticsAssignment:
	assignment_id: str
	assignment_type: str  # train or logistics_unit
	commodity: str  # supply or ammo
	amount: int
	source_province_id: int
	destination_province_id: int
	priority: int
	assigned_asset_id: str = ""
	target_unit_id: str = ""
	status: str = "planned"
	phase: str = "to_source"
	loaded_amount: int = 0
	delivered_amount: int = 0
	manual: bool = False
	reason: str = ""
	metadata: dict = field(default_factory=dict)

class Simulation(threading.Thread):
	"""Background simulation loop running independently from render framerate."""

	def __init__(self, nation_manager, game_map, armies, trains=None, tick_seconds: float = 1.0, speed_multiplier: float = 1.0):
		super().__init__(daemon=True)
		self.nation_manager = nation_manager
		self.game_map = game_map
		self.armies = armies
		self.trains = trains or {}
		self.logistic_man = []
		self.logistic_get = {}

		# One simulation tick represents one in-game hour.
		self.tick_seconds = max(0.01, float(tick_seconds))
		self.speed_multiplier = max(0.0, float(speed_multiplier))

		self.tick_count = 0
		self.current_hour = 0
		self.current_day = 1
		self.current_month = 1
		self.current_year = 1904 #this gonna be changed to be loaded from the simulation 
		self.start_date = (1904, 1, 1)  # (year, month, day)
		
		self.moviment_list = []
		self.moviment_time = []
		self.train_moviment_list = []
		self.train_moviment_time = []
		self.combat_list = []
		# [unit_id, ticks_remaining] — units waiting to enter Moving status
		self.mobilization_queue = []
		self.suply_list = []

		#load player
		self.player_nation = "URU"
		self.player_home = 1 #this will be relevant after.  

		self.people_manager = PeopleManager()
		self.people_manager.create_player("PlayerName", "PlayerFamilyName", 1886, 12, self.player_nation, self.player_home, 1, 100, 100, 1, 0)
		self._people_generated = False
		self.generate_people()
		self.set_player_job()
		self.starter_jobs()
		self.starting_oob()
		self.start_logistics()

		self.debug_logistics()


		self.Suply_tick = False #daily supply ticks happen at 6
		self._last_logistics_planning_day = None

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
		run_daily_province_tick = False
		with self._state_lock:
			self.tick_count += 1
			# Time representation
			self.current_hour += 1
			if self.current_hour >= 24:
				self.current_hour = 0
				self.current_day += 1
				run_daily_province_tick = True
				if self.current_day > 30:
					self.people_manager.update_month()
					self.current_day = 1
					self.current_month += 1
					if self.current_month > 12:
						self.current_month = 1
						self.current_year += 1

			# Daily supply tick happens once per day at 06:00.
			self.Suply_tick = (self.current_hour == 6)

			# - self.game_map
			# - self.nation_manager
			# - self.armies

		if run_daily_province_tick:
			self.game_map.run_daily_province_simulation()

		self._process_mobilization()
		self._process_movements()
		self._process_train_movements()
		self.Unit_spotting()
		self.Unit_tick()
		self.train_tick()
		self.Autonumous_logi()

		#self.combat()

	#this might require a name change
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
						unit.use_suply()  
						unit.counter = 0

	def _get_capital_province_ids(self):
		"""Collect all valid capital province IDs from loaded nations."""
		capital_ids = set()
		if self.nation_manager is None:
			return capital_ids
 
		for nation in self.nation_manager.get_all_nations():
			capital_id = nation.return_capital_id_int()
			if capital_id is not None:
				capital_ids.add(capital_id)

		return capital_ids

	def _get_province_owner_tag(self, province_id):
		"""Return province owner tag for nation assignment, or None when unavailable."""
		province = self.game_map.get_province_by_id(province_id)
		if province is not None:
			owner = province.get("owner")
			if owner:
				return owner

		province_obj = self.game_map.get_province_object_by_id(province_id)
		if province_obj is not None:
			owner = getattr(province_obj, "owner", None)
			if owner:
				return owner

		return None

	def generate_people(self):
		"""Startup seeding: 100 in capitals, then 1% of each province population."""
		if self._people_generated:
			return

		capital_ids = self._get_capital_province_ids()

		for capital_id in capital_ids:
			if self.game_map.get_province_object_by_id(capital_id) is None:
				continue
			nation_tag = self._get_province_owner_tag(capital_id)
			self.people_manager.generate_people(location=capital_id, nation=nation_tag, ammount=100)

		for province in getattr(self.game_map, "provinceObjects", []):
			population = getattr(province, "population", 0) or 0
			try:
				population = int(population)
			except (TypeError, ValueError):
				population = 0

			ammount = population // 1000
			if ammount > 0:
				nation_tag = getattr(province, "owner", None) or self._get_province_owner_tag(province.province_id)
				self.people_manager.generate_people(location=province.province_id, nation=nation_tag, ammount=ammount)

		self._people_generated = True

	def _find_unit_by_id(self, unit_id):
		"""Find a unit object across all armies by unit ID."""
		for army in self.armies.values():
			unit = army.get_unit(unit_id)
			if unit is not None:
				return unit
		return None

	def _find_main_hq_unit_for_nation(self, nation_tag):
		"""Return the first Main HQ unit found for a specific nation tag."""
		if not nation_tag:
			return None

		for army in self.armies.values():
			for unit in army.units.values():
				if getattr(unit, "nation", None) != nation_tag:
					continue
				if str(getattr(unit, "name", "")).strip().lower() == "main hq":
					return unit

		return None

	def _find_train_by_id(self, train_id):
		if train_id is None:
			return None
		return self.trains.get(str(train_id))

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

	def _train_movement_ticks_for_train(self, train) -> int:
		speed_value = getattr(train, "speed", 1)
		#gonna have to touch on this later
		try:
			speed_value = float(speed_value)
		except (TypeError, ValueError):
			speed_value = 1.0
		if speed_value <= 0:
			return 16
		return max(1, int(round(16.0 / speed_value)))

	def _find_train_movement_index(self, train_id):
		for idx, movement in enumerate(self.train_moviment_list):
			if movement and movement[0] == str(train_id):
				return idx
		return None

	def _find_train_timer_index(self, train_id):
		for idx, timer_entry in enumerate(self.train_moviment_time):
			if timer_entry and timer_entry[0] == str(train_id):
				return idx
		return None

	def _process_movements(self) -> None:
		"""Tick movement countdowns for all queued units."""
		with self._state_lock:
			unit_ids = [entry[0] for entry in self.moviment_time if entry]

		for unit_id in unit_ids:
			self.moveunit(unit_id)

	def _process_train_movements(self) -> None:
		"""Tick movement countdowns for all queued trains."""
		with self._state_lock:
			train_ids = [entry[0] for entry in self.train_moviment_time if entry]

		for train_id in train_ids:
			self.movetrain(train_id)


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
				# Consume supply while resting
				if unit.suply >= unit.suply_consumption:
					unit.use_suply()
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
			if unit.is_spotted():
				for spotter_id in list(unit.return_spoted_by()):
					unit_looking = self._find_unit_by_id(spotter_id)
					if unit_looking is None:
						if spotter_id in unit.spoted_by:
							unit.spoted_by.remove(spotter_id)
						continue
					if unit_looking.location == next_province_id:
						#maybe fire battle, lets see for now 
						print("hi, battle may occur to be implemented")
					elif unit.location == unit_looking.location:
						print("unit see the other unit running away")
					else:
						unit_looking.pop_the_unit_from_unit_spoted(unit.id)
						if unit_looking.id in unit.spoted_by:
							unit.spoted_by.remove(unit_looking.id)
						print(f"{unit_looking.name} no longer spots {unit.name} after it moved to province {next_province_id}.")
				for aspoted in unit.units_spoted:
					theUnit = self._find_unit_by_id(aspoted)
					if theUnit.location == next_province_id:
						print("wow a battle might start! cool.")
					elif theUnit.location == unit.location:
						print(f"{unit.name} is still spotting {theUnit.name} after it moved to province {next_province_id} running away.")
					else:
						unit.pop_the_unit_from_unit_spoted(aspoted)
						if unit.id in theUnit.spoted_by:
							theUnit.spoted_by.remove(unit.id)
						print(f"{unit.name} no longer spots {theUnit.name} after it moved to province {next_province_id}.")

			unit.location = next_province_id
			del movement[1]

			# Consume supply when completing a movement step
			if unit.suply >= unit.suply_consumption:
				unit.use_suply()

			if len(movement) == 1:
				del self.moviment_list[movement_idx]
				del self.moviment_time[timer_idx]
				unit.status = 1
				unit.counter = 0
			else:
				self.moviment_time[timer_idx][1] = self._movement_ticks_for_unit(unit)

			return True

	def movetrain(self, train_id):
		"""Advance one queued movement step for a train when timer reaches zero."""
		with self._state_lock:
			timer_idx = self._find_train_timer_index(train_id)
			movement_idx = self._find_train_movement_index(train_id)

			if timer_idx is None or movement_idx is None:
				return False

			train = self._find_train_by_id(train_id)
			if train is None:
				del self.train_moviment_list[movement_idx]
				del self.train_moviment_time[timer_idx]
				return False

			if getattr(train, "status", 0) != 1:
				return False

			self.train_moviment_time[timer_idx][1] -= 1
			if self.train_moviment_time[timer_idx][1] > 0:
				return False

			movement = self.train_moviment_list[movement_idx]
			if len(movement) <= 1:
				del self.train_moviment_list[movement_idx]
				del self.train_moviment_time[timer_idx]
				train.status = 0
				train.route = []
				return False

			next_province_id = movement[1]
			train.location = next_province_id
			del movement[1]

			# Train-unit coupling intentionally disabled for now.

			if len(movement) == 1:
				del self.train_moviment_list[movement_idx]
				del self.train_moviment_time[timer_idx]
				train.status = 0
				train.route = []
			else:
				train.route = movement[1:]
				self.train_moviment_time[timer_idx][1] = self._train_movement_ticks_for_train(train)

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
				if unit.id in spotter.units_spoted:
					roll = random.randint(0,100)
					add = (spotter.return_spotting(spotting_index)+roll) // 10 
					spotter.edit_spotQuality_from_unit_id(unit.id, add)
				continue
			print(f"{spotter.name} is attempting to spot {unit.name} in province {province_id}...")	
			spotting_power = spotter.return_spotting(spotting_index)
			spot_chance = (spotting_power + unit.visibility)//2
			if random.randint(0, 100) < spot_chance:
				spotter.units_spoted.append(unit.id)
				spotter.unitCurrentSpoting += 1
				spotter.spotting_quality.append(1)
				unit.spoted_by.append(spotter.id)
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

	def _get_nearby_province_objects(self, province_id):
		"""Return nearby provinces as Province objects for the given province id."""
		province_data = self.game_map.get_province_by_id(province_id)
		if not province_data:
			return []

		nearby_objects = []
		for nearby_id in province_data.get("nearby_provinces", []):
			province_obj = self.game_map.get_province_object_by_id(nearby_id)
			if province_obj is not None:
				nearby_objects.append(province_obj)

		return nearby_objects

	def _get_richest_supply_province(self, province_objects):
		"""Return the province object with the highest available supply."""
		richest = None
		highest_supply = -1
		for province_obj in province_objects:
			if province_obj is None:
				continue
			suply_amount = province_obj.return_suply()
			if suply_amount > highest_supply:
				highest_supply = suply_amount
				richest = province_obj
		return richest

	def Unit_spotting(self):
		for army in self.armies.values():
			for unit in army.units.values():
				unit.update_spotting()
				self.spotting(unit, unit.location)

	def Unit_tick(self):
		for army in self.armies.values():
			for unit in army.units.values():
				self.unit_simulation(unit.id)

	def train_tick(self):
		for train in self.trains.values():
			self.train_simulation(train.id)

	def unit_simulation(self, unit_id):
		unit = self._find_unit_by_id(unit_id)
		if unit is None:
			return
		province = self.game_map.get_province_object_by_id(unit.location)
		if province is None:
			return
		# Keep logistics capacity current as soldier count and transport assets change.
		unit.calculate_logistics_value()
		nearby_provinces = self._get_nearby_province_objects(unit.location)
		nearby_has_supply = any(p.return_suply() > 0 for p in nearby_provinces)
		unit_home = unit.return_home()
		if unit_home == unit.location:
			if unit.soldiers < unit.targetsize:
				if unit.status == 2 or unit.status == 13:
					if province.province_recruits > 100:
						unit.add_soldiers(100)
						province.add_soldiers(100)
		
		unit.calculate_logistic_consumption()

		if province.return_suply() > 0:
			unit.calculate_logistic_request()
			if unit.suply_request > province.suply:
				#for now it won't take into account other units in the same province... to change this to let the player set prioririties or home priority.
				unit.add_suply(province.suply)
				province.transfer_suply(province.suply)
				if unit.status == 4 or unit.status == 3 and province.return_suply() > unit.suply_request:
					unit.add_suply(province.suply)
					province.transfer_suply(province.suply)
					
			else:
				unit.add_suply(unit.suply_request)
				province.transfer_suply(unit.suply_request)
		
		elif unit.has_logistics_capacity() and nearby_has_supply:
			
			max_delivery = unit.calculate_logistic_request_nextProvince()
			unit.calculate_logistic_request()
			source_province = self._get_richest_supply_province(nearby_provinces)

			if source_province is not None and unit.suply_request > 0 and max_delivery > 0:
				delivery_amount = min(max_delivery, source_province.return_suply(), unit.suply_request)
				if delivery_amount > 0 and self.Suply_tick:
					print(f"Unit {unit.name} is requesting {delivery_amount} supply from nearby province {source_province.province_id}.")
					unit.add_suply(delivery_amount)
					source_province.transfer_suply(delivery_amount)
		

		if self.Suply_tick:
			unit.use_suply()

		if unit.status == 11:
			if  unit.suply > unit.suply_consumption:
				unit.use_suply()
				unit.mobilize(10*province.infrastructure)
		#think this is it for now correct?

	

	def train_simulation(self, train_id):
		train = self._find_train_by_id(train_id)
		if train is None:
			return
		province = self.game_map.get_province_object_by_id(train.location)
		if province is None:
			return

		if train.status == 3 :
			if province.return_suply() > 0:
				
				if 1000 < province.suply:
					train.loading_suply(1000)
					province.transfer_suply(1000)
				else:
					train.loading_suply(province.suply)
					province.transfer_suply(province.suply)
		
		if train.status == 4:
			if train.suply > 0:
				train.unloading_suply(1000)
				province.add_suply(1000)

		if train.status == 0:
			if train.health < 80:
				train.update_status(5)

		if train.status == 5:
			train.repair()

		if self.Suply_tick:
			train.train_usage()
		

				
		
		

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

	def train_pathing(self, train_id, destination_province_id):
		"""Queue shortest rail-only movement path for a train."""
		with self._state_lock:
			train = self._find_train_by_id(train_id)
			if train is None:
				return []

			start_province_id = getattr(train, "location", None)
			if start_province_id is None:
				return []

			if start_province_id == destination_province_id:
				return [start_province_id]

			destination_province = self.game_map.get_province_by_id(destination_province_id)
			if destination_province is None:
				return []

			path = self.game_map.find_rail_path(start_province_id, destination_province_id)
			if len(path) < 2:
				return []

			route_entry = [str(train_id)] + path[1:]
			train.status = 1
			train.route = path[1:]

			existing_movement_idx = self._find_train_movement_index(train_id)
			existing_timer_idx = self._find_train_timer_index(train_id)

			if existing_movement_idx is not None:
				self.train_moviment_list[existing_movement_idx] = route_entry
			else:
				self.train_moviment_list.append(route_entry)

			ticks_for_step = self._train_movement_ticks_for_train(train)
			timer_entry = [str(train_id), ticks_for_step]

			if existing_timer_idx is not None:
				self.train_moviment_time[existing_timer_idx] = timer_entry
			else:
				self.train_moviment_time.append(timer_entry)

			return path

	def update_suply_list(self):
		self.suply_list = []
		self.logistics_units = []
		for army in self.armies.values():
			for unit in army.units.values():
				self.add_suply_request(unit)
					
	def set_player_job(self):
		"""Assign the player person to the nation's Main HQ and set that unit's leader."""
		player = self.people_manager.get_person(1)  # Player is created first.
		if player is None:
			return False

		main_hq_unit = self._find_main_hq_unit_for_nation(self.player_nation)
		if main_hq_unit is None:
			print(f"No Main HQ unit found for nation {self.player_nation}.")
			return False

		# Keep both systems in sync: people job assignment and unit leader assignment.
		self.people_manager.give_player_job(main_hq_unit.id, 1)
		main_hq_unit.set_unit_leader(player.id)
		return True
	
	def starter_jobs(self):
		"""Assign startup unit leaders/officers from Army-type people in each unit home province.

		Rules:
		- Skip units that already have a leader.
		- Only people with type == 1 (Army) are eligible.
		- A person can only be assigned to one unit (via person.Unit).
		- Leader is assigned first; officers are then filled from remaining local candidates.
		"""
		def _is_unassigned(person):
			return getattr(person, "Unit", 0) in (0, None, "")

		def _province_army_candidates(province_id):
			candidates = []
			for person in self.people_manager.get_people_in_province(province_id):
				if getattr(person, "type", 0) != 1:
					continue
				if not _is_unassigned(person):
					continue
				candidates.append(person)
			candidates.sort(key=lambda p: getattr(p, "id", 0))
			return candidates

		all_units = []
		for army in self.armies.values():
			all_units.extend(list(army.units.values()))

		# Deterministic assignment order improves repeatability.
		all_units.sort(key=lambda u: str(getattr(u, "id", "")))

		leaders_assigned = 0
		officers_assigned = 0

		for unit in all_units:
			current_leader = getattr(unit, "leader_id", 0)
			if current_leader not in (0, None, ""):
				continue

			home_province = getattr(unit, "home", None)
			if home_province is None:
				continue

			candidates = _province_army_candidates(home_province)
			if not candidates:
				continue

			leader = candidates[0]
			unit.set_unit_leader(leader.id)
			leader.give_job(1)
			leader.Unit = unit.id
			leaders_assigned += 1

			# Keep officers at least 1 when a leader exists.
			current_officers = int(getattr(unit, "officers", 0) or 0)
			if current_officers < 1:
				unit.officers = 1
				current_officers = 1

			# Fill additional officers from remaining local Army candidates.
			# Baseline target: 1 officer per 500 soldiers (minimum 1 total).
			soldiers = int(getattr(unit, "soldiers", 0) or 0)
			desired_officers_total = max(1, soldiers // 500)
			needed = max(0, desired_officers_total - current_officers)

			if needed > 0:
				remaining_candidates = _province_army_candidates(home_province)
				for person in remaining_candidates:
					if needed <= 0:
						break
					person.give_job(1)
					person.Unit = unit.id
					unit.officers = int(getattr(unit, "officers", 0) or 0) + 1
					officers_assigned += 1
					needed -= 1

		print(f"Starter jobs complete: leaders assigned={leaders_assigned}, officers assigned={officers_assigned}")

	def starting_oob(self):
		"""Build initial OOB: each nation's Main HQ gets all same-nation units as subordinates."""
		units_by_nation = {}
		main_hq_by_nation = {}

		for army in self.armies.values():
			for unit in army.units.values():
				nation = getattr(unit, "nation", None)
				if not nation:
					continue

				if nation not in units_by_nation:
					units_by_nation[nation] = []
				units_by_nation[nation].append(unit)

				if str(getattr(unit, "name", "")).strip().lower() == "main hq" and nation not in main_hq_by_nation:
					main_hq_by_nation[nation] = unit

		for nation, hq_unit in main_hq_by_nation.items():
			# Rebuild from scratch to avoid duplicates/stale references.
			hq_unit.subordinate_units_ids = []

			for unit in units_by_nation.get(nation, []):
				if unit.id == hq_unit.id:
					continue
				hq_unit.subordinate_units_ids.append(unit.id)

		print(f"Starting OOB complete: {len(main_hq_by_nation)} Main HQ units wired.")

	#will require to see if this is working as it should... it probably will need to be changed 

	def start_logistics(self):
		identifier = 0
		for nation in self.nation_manager.get_all_nations():
			print(f"Initializing logistics for nation {nation.tag}...")
			logistics_manager = logisticsManager(nation.tag, simulation=self)
			print(f"Logistics manager created for nation {nation.tag}.")
			self.logistic_get[nation.tag] = identifier
			print(f"Logistics manager ID {identifier} assigned to nation {nation.tag}.")
			print(f"the current logistics manager dict: {self.logistic_get}")
			self.logistic_man.append(logistics_manager)
			print(f"Logistics manager for nation {nation.tag} stored in simulation.")
			identifier += 1

		self.initialize_logistics()

	def _get_logistics_manager(self, nation_tag):
		if not nation_tag:
			return None
		index = self.logistic_get.get(nation_tag)
		if index is None:
			return None
		if index < 0 or index >= len(self.logistic_man):
			return None
		return self.logistic_man[index]

	def _get_logistics_managers_for_nation(self, nation_tag):
		"""Return nation and root-nation logistics managers for shared logistics assets."""
		managers = []
		seen_tags = set()

		for tag in (nation_tag, self._get_root_nation_tag(nation_tag)):
			if not tag or tag in seen_tags:
				continue
			seen_tags.add(tag)
			manager = self._get_logistics_manager(tag)
			if manager is not None:
				managers.append(manager)

		return managers
		
	def initialize_logistics(self):
		"""Populate nation logistics from map control, rail lines, and trains."""
		#this might not be necessary... 
		for manager in self.logistic_man:
			manager.bind_context(self)
			manager.reset_runtime_lists()

		for province in getattr(self.game_map, "provinceObjects", []):
			nation_tag = getattr(province, "controller", None)
			managers = self._get_logistics_managers_for_nation(nation_tag)
			if not managers:
				continue

			if province.iswater:
				continue

			for manager in managers:
				manager.add_province(province.province_id)

			if getattr(province, "logistic_hub", False):
				for manager in managers:
					manager.add_logistics_hub(province.province_id)

			for rail_id in getattr(province, "railid", []):
				for manager in managers:
					manager.add_rail(rail_id)

			for built in getattr(province, "buildings", []):
				building_type = getattr(built, "building_type", None)
				for manager in managers:
					if building_type == 3:
						manager.add_production_suply(province.province_id)
					elif building_type == 7:
						manager.add_production_ammo(province.province_id)

		for train in self.trains.values():
			nation_tag = getattr(train, "nation", None)
			managers = self._get_logistics_managers_for_nation(nation_tag)
			if not managers:
				continue
			for manager in managers:
				manager.add_train(getattr(train, "id", None), getattr(train, "location", None))

		for army in self.armies.values():
			for unit in army.units.values():
				manager = self._get_logistics_manager(getattr(unit, "nation", None))
				if manager is None:
					continue
				manager.add_suply_request(unit)
				manager.update_logistics_unit_registration(unit)

	def debug_logistics(self):
		for manager in self.logistic_man:
			manager.debug_print()

	def set_logistics_hub(self, nation_tag, province_id, enabled=True):
		manager = self._get_logistics_manager(nation_tag)
		if manager is None:
			print(f"No logistics manager found for nation {nation_tag}.")
			return False
		if enabled:
			manager.add_logistics_hub(province_id)
			print(f"Logistics hub set for nation {nation_tag} in province {province_id}.")
		else:
			manager.remove_logistics_hub(province_id)
			print(f"Logistics hub cleared for nation {nation_tag} in province {province_id}.")
		return True

	def request_logistics_replan(self, reason="manual"):
		"""Force a logistics replanning pass without changing manual player orders."""
		self.initialize_logistics()
		for manager in self.logistic_man:
			manager.request_replan(reason=reason)
		return True


	def Autonumous_logi(self):
		should_plan_daily = False
		if self.Suply_tick and self._last_logistics_planning_day != self.current_day:
			self._last_logistics_planning_day = self.current_day
			should_plan_daily = True

		for manager in self.logistic_man:
			manager.routine(force_plan=should_plan_daily)

class logisticsManager:

	def __init__(self, nation, simulation=None):
		self.nation = nation
		self.simulation = simulation
		self.provinces = []
		self.suply_list = []
		self.ammo_list = []

		self.logistics_units = []

		self.suply_production = []
		self.ammo_production = []
		self.logistics_hubs = []
		self.rails = []
		self.trains = []
		self.train_locations = {}

		self._request_counter = 0
		self._assignment_counter = 0
		self._replan_requested = True
		self._last_plan_reason = "startup"

		self.current_requests = []
		self.train_assignments = []
		self.logistics_assignments = []
		self.completed_assignments = []
		self.failed_assignments = []

		self._province_stockpiles = {}
		self._province_ammo = {}

	def bind_context(self, simulation):
		self.simulation = simulation

	def request_replan(self, reason="manual"):
		self._replan_requested = True
		self._last_plan_reason = reason

	def reset_runtime_lists(self):
		self.provinces = []
		self.suply_list = []
		self.ammo_list = []
		self.suply_production = []
		self.ammo_production = []
		self.logistics_hubs = []
		self.rails = []
		self.trains = []
		self.train_locations = {}

	def debug_print(self):
		print(f"Logistics Manager for nation {self.nation}:")
		print(f"  Provinces: {self.provinces}")
		print(f"  Supply Requests: {self.suply_list}")
		print(f"  Ammo Requests: {self.ammo_list}")
		print(f"  Supply Production: {self.suply_production}")
		print(f"  Ammo Production: {self.ammo_production}")
		print(f"  Logistics Hubs: {self.logistics_hubs}")
		print(f"  Rails: {self.rails}")
		print(f"  Trains: {self.trains}")
		print(f"  Train Locations: {self.train_locations}")
		print(f"  Logistics Units: {self.logistics_units}")
		print(f"  Active train assignments: {len(self.train_assignments)}")
		print(f"  Active logistics assignments: {len(self.logistics_assignments)}")

	def add_province(self, province_id, current_suply=0, current_ammo=0):
		for entry in self.provinces:
			if entry[0] == province_id:
				entry[1] = current_suply
				entry[2] = current_ammo
				return
		self.provinces.append([province_id, current_suply, current_ammo])

	def _build_supply_entry(self, unit):
		return [
			getattr(unit, "id", None),
			getattr(unit, "location", None),
			getattr(unit, "suply", 0),
			getattr(unit, "suply_consumption", 0),
		]

	def _build_ammo_entry(self, unit):
		return [
			getattr(unit, "id", None),
			getattr(unit, "location", None),
			getattr(unit, "ammo", 0),
			getattr(unit, "ammo_consumption", 0),
		]

	def routine(self, force_plan=False):
		self.refresh_network_snapshot()
		self.execute_assignments_tick()

		if force_plan or self._replan_requested:
			reason = self._last_plan_reason if self._replan_requested else "daily"
			self.run_daily_planning_cycle(reason=reason)
			self._replan_requested = False
			self._last_plan_reason = "daily"

		total_suply_needed = self.suply_cost()
		print(f"Nation {self.nation} requires a total of {total_suply_needed} supply units.")

	def suply_cost(self):
		suply_needed = 0
		for unit_entry in self.suply_list:
			if not unit_entry:
				continue
			if len(unit_entry) >= 4:
				suply_needed += unit_entry[3]
		return suply_needed

	def update_logistics_unit_registration(self, unit):
		if getattr(unit, "type", None) == 4 and getattr(unit, "id", None) not in self.logistics_units:
			self.logistics_units.append(unit.id)

	def add_suply_request(self, unit_or_id):
		if hasattr(unit_or_id, "id"):
			unit_entry = self._build_supply_entry(unit_or_id)
			if unit_entry[0] is None:
				return
			for idx, existing in enumerate(self.suply_list):
				if existing and existing[0] == unit_entry[0]:
					self.suply_list[idx] = unit_entry
					break
			else:
				self.suply_list.append(unit_entry)

			ammo_entry = self._build_ammo_entry(unit_or_id)
			for idx, existing in enumerate(self.ammo_list):
				if existing and existing[0] == ammo_entry[0]:
					self.ammo_list[idx] = ammo_entry
					break
			else:
				self.ammo_list.append(ammo_entry)

			self.update_logistics_unit_registration(unit_or_id)
			return

		unit_id = unit_or_id
		if unit_id not in [entry[0] for entry in self.suply_list if entry]:
			self.suply_list.append([unit_id, None, 0, 0])

	def add_production_suply(self, province_id):
		if province_id not in self.suply_production:
			self.suply_production.append(province_id)

	def add_production_ammo(self, province_id):
		if province_id not in self.ammo_production:
			self.ammo_production.append(province_id)

	def add_logistics_hub(self, province_id):
		if province_id not in self.logistics_hubs:
			self.logistics_hubs.append(province_id)
			print(f"Logistics hub added on the manager for nation {self.nation} in province {province_id}.")
		self.request_replan(reason="hub-change")

	def remove_logistics_hub(self, province_id):
		if province_id in self.logistics_hubs:
			self.logistics_hubs.remove(province_id)
			print(f"Logistics hub removed from the manager for nation {self.nation} in province {province_id}.")
		self.request_replan(reason="hub-change")

	def add_rail(self, rail_id):
		if rail_id not in self.rails:
			self.rails.append(rail_id)

	def add_train(self, train_id, location=None):
		if train_id is None:
			return
		if train_id not in self.trains:
			self.trains.append(train_id)
		if location is not None:
			self.train_locations[train_id] = location

	def update_train_location(self, train_id, new_location):
		if train_id in self.train_locations:
			self.train_locations[train_id] = new_location

	def update_province_suply(self, province_id, new_suply):
		for entry in self.provinces:
			if entry[0] == province_id:
				entry[1] = new_suply
				return
		self.provinces.append([province_id, new_suply, 0])

	def update_province_ammo(self, province_id, new_ammo):
		for entry in self.provinces:
			if entry[0] == province_id:
				entry[2] = new_ammo
				return
		self.provinces.append([province_id, 0, new_ammo])

	def _next_request_id(self):
		self._request_counter += 1
		return f"{self.nation}-REQ-{self._request_counter}"

	def _next_assignment_id(self):
		self._assignment_counter += 1
		return f"{self.nation}-ASG-{self._assignment_counter}"

	def _get_province_object(self, province_id):
		if self.simulation is None:
			return None
		return self.simulation.game_map.get_province_object_by_id(province_id)

	def _get_train(self, train_id):
		if self.simulation is None:
			return None
		return self.simulation.trains.get(str(train_id))

	def _get_unit(self, unit_id):
		if self.simulation is None:
			return None
		return self.simulation._find_unit_by_id(unit_id)

	def _iter_nation_units(self):
		if self.simulation is None:
			return
		for army in self.simulation.armies.values():
			for unit in army.units.values():
				if getattr(unit, "nation", None) == self.nation:
					yield unit

	def _iter_nation_trains(self):
		if self.simulation is None:
			return
		for train in self.simulation.trains.values():
			if getattr(train, "nation", None) == self.nation:
				yield train

	def _is_train_automatic(self, train):
		if train is None:
			return False
		if not getattr(train, "automatic", True):
			return False
		if getattr(train, "manual_order", False):
			return False
		if getattr(train, "manual_assignment", None):
			return False
		if getattr(train, "automation_locked", False):
			return False
		return True

	def _is_logistics_unit_automatic(self, unit):
		if unit is None:
			return False
		if getattr(unit, "type", None) != 4:
			return False
		if getattr(unit, "logistics_automatic", True) is False:
			return False
		if getattr(unit, "manual_order", False):
			return False
		if getattr(unit, "manual_assignment", None):
			return False
		if getattr(unit, "automation_locked", False):
			return False
		return True

	def _priority_for_unit(self, unit):
		current_supply = max(0, int(getattr(unit, "suply", 0) or 0))
		daily_need = max(1, int(getattr(unit, "suply_consumption", 1) or 1))
		ratio = current_supply / daily_need

		if ratio < 1.0:
			return PRIORITY_CRITICAL
		if ratio < 2.0:
			return PRIORITY_HIGH
		if ratio < 4.0:
			return PRIORITY_NORMAL
		if ratio < 7.0:
			return PRIORITY_LOW
		return PRIORITY_RESERVE

	def _province_available_supply(self, province_id):
		province = self._get_province_object(province_id)
		if province is None:
			return 0
		return max(0, int(getattr(province, "suply", 0) or 0))

	def _province_available_ammo(self, province_id):
		province = self._get_province_object(province_id)
		if province is None:
			return 0
		return max(0, int(getattr(province, "ammo", 0) or 0))

	def _map_neighbors(self, province_id):
		if self.simulation is None:
			return []
		province = self.simulation.game_map.get_province_by_id(province_id)
		if not province:
			return []
		return list(province.get("nearby_provinces", []))

	def _distance_hops(self, start_id, goal_id):
		if start_id == goal_id:
			return 0
		if start_id is None or goal_id is None:
			return float("inf")

		visited = {start_id}
		queue = deque([(start_id, 0)])

		while queue:
			current, dist = queue.popleft()
			for neighbor in self._map_neighbors(current):
				if neighbor in visited:
					continue
				if neighbor == goal_id:
					return dist + 1
				visited.add(neighbor)
				queue.append((neighbor, dist + 1))

		return float("inf")

	def _rail_distance_hops(self, start_id, goal_id):
		if start_id == goal_id:
			return 0
		if self.simulation is None:
			return float("inf")
		path = self.simulation.game_map.find_rail_path(start_id, goal_id)
		if not path:
			return float("inf")
		return max(0, len(path) - 1)

	def _nearest_location(self, origin, candidates, rail_only=False):
		best_id = None
		best_dist = float("inf")
		for candidate in candidates:
			if rail_only:
				distance = self._rail_distance_hops(origin, candidate)
			else:
				distance = self._distance_hops(origin, candidate)
			if distance < best_dist:
				best_dist = distance
				best_id = candidate
		if best_id is None:
			return None, float("inf")
		return best_id, best_dist

	def refresh_network_snapshot(self):
		if self.simulation is None:
			return

		self._province_stockpiles = {}
		self._province_ammo = {}

		for entry in self.provinces:
			province_id = entry[0]
			supply = self._province_available_supply(province_id)
			ammo = self._province_available_ammo(province_id)
			entry[1] = supply
			entry[2] = ammo
			self._province_stockpiles[province_id] = supply
			self._province_ammo[province_id] = ammo

		for train in self._iter_nation_trains() or []:
			self.add_train(getattr(train, "id", None), getattr(train, "location", None))

		for unit in self._iter_nation_units() or []:
			self.add_suply_request(unit)

	def _update_production_step(self):
		# Production is already added by the province daily tick; planner only snapshots sources.
		for province_id in self.suply_production:
			self._province_stockpiles[province_id] = self._province_available_supply(province_id)
		for province_id in self.ammo_production:
			self._province_ammo[province_id] = self._province_available_ammo(province_id)

	def _update_stockpiles_step(self):
		for entry in self.provinces:
			province_id = entry[0]
			entry[1] = self._province_available_supply(province_id)
			entry[2] = self._province_available_ammo(province_id)

	def _collect_requests_step(self):
		requests = []
		self.suply_list = []
		self.ammo_list = []

		for unit in self._iter_nation_units() or []:
			unit.calculate_logistics_value()
			unit.calculate_logistic_consumption()
			unit.calculate_logistic_request()

			supply_needed = max(0, int(getattr(unit, "suply_request", 0) or 0))
			ammo_consumption = max(0, int(getattr(unit, "ammo_consumption", 0) or 0))
			current_ammo = max(0, int(getattr(unit, "ammo", 0) or 0))
			ammo_needed = max(0, ammo_consumption + 20 - current_ammo)

			self.add_suply_request(unit)

			if supply_needed <= 0 and ammo_needed <= 0:
				continue

			request = LogisticsRequest(
				request_id=self._next_request_id(),
				unit_id=str(unit.id),
				nation=self.nation,
				location=int(getattr(unit, "location", 0) or 0),
				supply_needed=supply_needed,
				ammo_needed=ammo_needed,
				priority=self._priority_for_unit(unit),
			)
			requests.append(request)

		requests.sort(key=lambda req: (-req.priority, -(req.supply_needed + req.ammo_needed)))
		self.current_requests = requests
		return requests

	def _evaluate_network_step(self):
		hubs = list(self.logistics_hubs)
		stocked_hubs = [hub for hub in hubs if self._province_available_supply(hub) > 0]
		stocked_provinces = [entry[0] for entry in self.provinces if self._province_available_supply(entry[0]) > 0]

		auto_trains = []
		for train in self._iter_nation_trains() or []:
			if self._is_train_automatic(train):
				auto_trains.append(str(train.id))

		auto_logistics_units = []
		for unit_id in self.logistics_units:
			unit = self._get_unit(unit_id)
			if unit is not None and self._is_logistics_unit_automatic(unit):
				auto_logistics_units.append(str(unit.id))

		return {
			"hubs": hubs,
			"stocked_hubs": stocked_hubs,
			"stocked_provinces": stocked_provinces,
			"auto_trains": auto_trains,
			"auto_logistics_units": auto_logistics_units,
		}

	def _reserve_from_stockpile(self, province_id, amount):
		if amount <= 0:
			return 0
		current = self._province_stockpiles.get(province_id, self._province_available_supply(province_id))
		reserved = min(current, amount)
		self._province_stockpiles[province_id] = max(0, current - reserved)
		return reserved

	def _best_train_for_route(self, source_hub, train_ids):
		best_train = None
		best_dist = float("inf")

		for train_id in train_ids:
			train = self._get_train(train_id)
			if train is None or not self._is_train_automatic(train):
				continue
			if getattr(train, "status", 0) not in (0, 2):
				continue
			if self.simulation._find_train_movement_index(train.id) is not None:
				continue

			distance = self._rail_distance_hops(getattr(train, "location", None), source_hub)
			if distance < best_dist:
				best_dist = distance
				best_train = str(train.id)

		return best_train

	def _best_logistics_unit_for_delivery(self, source_province, unit_ids):
		best_unit = None
		best_dist = float("inf")

		for unit_id in unit_ids:
			unit = self._get_unit(unit_id)
			if unit is None or not self._is_logistics_unit_automatic(unit):
				continue
			if getattr(unit, "status", 0) in (3, 4):
				continue
			if self.simulation._find_movement_index(unit.id) is not None:
				continue

			distance = self._distance_hops(getattr(unit, "location", None), source_province)
			if distance < best_dist:
				best_dist = distance
				best_unit = str(unit.id)

		return best_unit

	def _create_train_assignment(self, source_hub, destination_hub, amount, priority, train_id, reason=""):
		assignment = LogisticsAssignment(
			assignment_id=self._next_assignment_id(),
			assignment_type="train",
			commodity="supply",
			amount=int(amount),
			source_province_id=int(source_hub),
			destination_province_id=int(destination_hub),
			priority=int(priority),
			assigned_asset_id=str(train_id),
			reason=reason,
		)
		self.train_assignments.append(assignment)
		return assignment

	def _create_logistics_assignment(self, source_province, destination_province, amount, priority, unit_id, target_unit_id="", reason=""):
		assignment = LogisticsAssignment(
			assignment_id=self._next_assignment_id(),
			assignment_type="logistics_unit",
			commodity="supply",
			amount=int(amount),
			source_province_id=int(source_province),
			destination_province_id=int(destination_province),
			priority=int(priority),
			assigned_asset_id=str(unit_id),
			target_unit_id=str(target_unit_id or ""),
			reason=reason,
		)
		self.logistics_assignments.append(assignment)
		return assignment

	def _clear_auto_assignments(self):
		for assignment in self.train_assignments + self.logistics_assignments:
			if assignment.manual or assignment.status in ("completed", "failed", "cancelled"):
				continue
			assignment.status = "cancelled"

		self.train_assignments = [a for a in self.train_assignments if a.manual]
		self.logistics_assignments = [a for a in self.logistics_assignments if a.manual]

	def _create_transport_assignments_step(self, requests, network):
		auto_trains = list(network.get("auto_trains", []))
		auto_logistics_units = list(network.get("auto_logistics_units", []))
		stocked_hubs = list(network.get("stocked_hubs", []))
		stocked_provinces = list(network.get("stocked_provinces", []))

		for request in requests:
			remaining = int(request.supply_needed)
			if remaining <= 0:
				continue

			target_unit = self._get_unit(request.unit_id)
			if target_unit is None:
				continue

			front_hub = None
			if stocked_hubs:
				front_hub, _ = self._nearest_location(int(target_unit.location), stocked_hubs, rail_only=False)

			if front_hub is not None and auto_trains:
				source_hub, _ = self._nearest_location(front_hub, stocked_hubs, rail_only=True)
				if source_hub is not None:
					train_id = self._best_train_for_route(source_hub, auto_trains)
					if train_id is not None:
						train_obj = self._get_train(train_id)
						capacity = max(1000, int(getattr(train_obj, "suplyCapacity", 4000) or 4000))
						reserved = self._reserve_from_stockpile(source_hub, min(remaining, capacity))
						if reserved > 0:
							self._create_train_assignment(
								source_hub=source_hub,
								destination_hub=front_hub,
								amount=reserved,
								priority=request.priority,
								train_id=train_id,
								reason=f"request:{request.request_id}",
							)
							remaining -= reserved

			if remaining <= 0:
				continue

			source_candidates = []
			if front_hub is not None:
				source_candidates.append(front_hub)
			source_candidates.extend(stocked_provinces)

			source_province, _ = self._nearest_location(int(target_unit.location), source_candidates, rail_only=False)
			if source_province is None:
				continue

			logi_unit_id = self._best_logistics_unit_for_delivery(source_province, auto_logistics_units)
			if logi_unit_id is None:
				continue

			logi_unit = self._get_unit(logi_unit_id)
			logi_unit.calculate_logistics_value()
			transport_capacity = max(100, int(getattr(logi_unit, "logistics_value", 0) or 0))
			reserved = self._reserve_from_stockpile(source_province, min(remaining, transport_capacity))
			if reserved <= 0:
				continue

			self._create_logistics_assignment(
				source_province=source_province,
				destination_province=int(target_unit.location),
				amount=reserved,
				priority=request.priority,
				unit_id=logi_unit_id,
				target_unit_id=request.unit_id,
				reason=f"request:{request.request_id}",
			)

	def run_daily_planning_cycle(self, reason="daily"):
		self.refresh_network_snapshot()
		self._update_production_step()
		self._update_stockpiles_step()
		requests = self._collect_requests_step()
		network = self._evaluate_network_step()

		self._clear_auto_assignments()
		self._create_transport_assignments_step(requests, network)

		print(
			f"[{self.nation}] logistics plan ({reason}) -> requests={len(requests)} "
			f"train_assignments={len(self.train_assignments)} "
			f"logi_assignments={len(self.logistics_assignments)}"
		)

	def _mark_assignment_complete(self, assignment):
		assignment.status = "completed"
		self.completed_assignments.append(assignment)

	def _mark_assignment_failed(self, assignment, reason):
		assignment.status = "failed"
		assignment.reason = reason
		self.failed_assignments.append(assignment)

	def _execute_train_assignment_tick(self, assignment):
		train = self._get_train(assignment.assigned_asset_id)
		if train is None:
			self._mark_assignment_failed(assignment, "train-missing")
			return
		if not self._is_train_automatic(train):
			self._mark_assignment_failed(assignment, "manual-train")
			return

		current_location = getattr(train, "location", None)
		source = assignment.source_province_id
		destination = assignment.destination_province_id

		if assignment.phase == "to_source":
			if current_location != source:
				if self.simulation._find_train_movement_index(train.id) is None:
					self.simulation.train_pathing(train.id, source)
				return
			assignment.phase = "loading"
			train.status = 3
			return

		if assignment.phase == "loading":
			province = self._get_province_object(source)
			if province is None:
				self._mark_assignment_failed(assignment, "source-missing")
				return

			remaining_to_load = max(0, assignment.amount - assignment.loaded_amount)
			if remaining_to_load <= 0:
				assignment.phase = "to_destination"
				if current_location != destination and self.simulation._find_train_movement_index(train.id) is None:
					self.simulation.train_pathing(train.id, destination)
				return

			free_capacity = max(0, int(getattr(train, "suplyCapacity", 4000) - getattr(train, "suply", 0)))
			load_amount = min(1000, remaining_to_load, province.return_suply(), free_capacity)
			if load_amount <= 0:
				assignment.phase = "to_destination"
				if current_location != destination and self.simulation._find_train_movement_index(train.id) is None:
					self.simulation.train_pathing(train.id, destination)
				return

			train.status = 3
			train.loading_suply(load_amount)
			province.transfer_suply(load_amount)
			assignment.loaded_amount += load_amount
			if assignment.loaded_amount >= assignment.amount:
				assignment.phase = "to_destination"
			return

		if assignment.phase == "to_destination":
			if current_location != destination:
				if self.simulation._find_train_movement_index(train.id) is None:
					self.simulation.train_pathing(train.id, destination)
				return
			assignment.phase = "unloading"
			train.status = 4
			return

		if assignment.phase == "unloading":
			province = self._get_province_object(destination)
			if province is None:
				self._mark_assignment_failed(assignment, "destination-missing")
				return

			remaining_to_deliver = max(0, assignment.amount - assignment.delivered_amount)
			if remaining_to_deliver <= 0:
				self._mark_assignment_complete(assignment)
				train.status = 0
				return

			unload_amount = min(1000, remaining_to_deliver, max(0, int(getattr(train, "suply", 0))))
			if unload_amount <= 0:
				self._mark_assignment_complete(assignment)
				train.status = 0
				return

			train.status = 4
			train.unloading_suply(unload_amount)
			province.add_suply(unload_amount)
			assignment.delivered_amount += unload_amount

			if assignment.delivered_amount >= assignment.amount:
				self._mark_assignment_complete(assignment)
				train.status = 0

	def _execute_logistics_assignment_tick(self, assignment):
		unit = self._get_unit(assignment.assigned_asset_id)
		if unit is None:
			self._mark_assignment_failed(assignment, "logistics-unit-missing")
			return
		if not self._is_logistics_unit_automatic(unit):
			self._mark_assignment_failed(assignment, "manual-logistics-unit")
			return

		target_unit = self._get_unit(assignment.target_unit_id) if assignment.target_unit_id else None
		if target_unit is not None:
			assignment.destination_province_id = int(target_unit.location)

		current_location = int(getattr(unit, "location", 0) or 0)
		source = assignment.source_province_id
		destination = assignment.destination_province_id

		if assignment.phase == "to_source":
			if current_location != source:
				if self.simulation._find_movement_index(unit.id) is None:
					self.simulation.pathing(unit.id, source)
				return
			assignment.phase = "loading"
			return

		if assignment.phase == "loading":
			province = self._get_province_object(source)
			if province is None:
				self._mark_assignment_failed(assignment, "source-missing")
				return

			unit.calculate_logistics_value()
			remaining_to_load = max(0, assignment.amount - assignment.loaded_amount)
			free_capacity = max(0, int(getattr(unit, "logistics_value", 0) - getattr(unit, "suply", 0)))
			load_amount = min(remaining_to_load, province.return_suply(), free_capacity)

			if load_amount <= 0:
				assignment.phase = "to_destination"
				if current_location != destination and self.simulation._find_movement_index(unit.id) is None:
					self.simulation.pathing(unit.id, destination)
				return

			unit.load_suply(load_amount)
			province.transfer_suply(load_amount)
			assignment.loaded_amount += load_amount
			if assignment.loaded_amount >= assignment.amount:
				assignment.phase = "to_destination"
			return

		if assignment.phase == "to_destination":
			if current_location != destination:
				if self.simulation._find_movement_index(unit.id) is None:
					self.simulation.pathing(unit.id, destination)
				return
			assignment.phase = "delivering"
			return

		if assignment.phase == "delivering":
			remaining_to_deliver = max(0, assignment.amount - assignment.delivered_amount)
			if remaining_to_deliver <= 0:
				assignment.phase = "returning"
				return

			deliverable = min(remaining_to_deliver, max(0, int(getattr(unit, "suply", 0))))
			if deliverable <= 0:
				assignment.phase = "returning"
				return

			if target_unit is not None:
				target_unit.add_suply(deliverable)
			else:
				province = self._get_province_object(destination)
				if province is not None:
					province.add_suply(deliverable)

			unit.suply = max(0, int(getattr(unit, "suply", 0) - deliverable))
			assignment.delivered_amount += deliverable

			if assignment.delivered_amount >= assignment.amount:
				assignment.phase = "returning"
			return

		if assignment.phase == "returning":
			if current_location != source:
				if self.simulation._find_movement_index(unit.id) is None:
					self.simulation.pathing(unit.id, source)
				return
			self._mark_assignment_complete(assignment)

	def execute_assignments_tick(self):
		for assignment in list(self.train_assignments):
			if assignment.status in ("completed", "failed", "cancelled"):
				continue
			assignment.status = "active"
			self._execute_train_assignment_tick(assignment)

		for assignment in list(self.logistics_assignments):
			if assignment.status in ("completed", "failed", "cancelled"):
				continue
			assignment.status = "active"
			self._execute_logistics_assignment_tick(assignment)

		self.train_assignments = [a for a in self.train_assignments if a.status not in ("completed", "failed", "cancelled")]
		self.logistics_assignments = [a for a in self.logistics_assignments if a.status not in ("completed", "failed", "cancelled")]
	
	



	

	
