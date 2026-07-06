import threading
import time
import heapq
import random

from people import PeopleManager

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
			logistics_manager = logisticsManager(nation.tag)
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
		
	def initialize_logistics(self):
		"""Populate nation logistics from map control, rail lines, and trains."""
		#this might not be necessary... 
		for manager in self.logistic_man:
			manager.reset_runtime_lists()

		for province in getattr(self.game_map, "provinceObjects", []):
			nation_tag = getattr(province, "controller", None)
			manager = self._get_logistics_manager(nation_tag)
			if manager is None:
				continue

			if province.iswater:
				continue
			manager.add_province(province.province_id)

			if getattr(province, "logistic_hub", False):
				manager.add_logistics_hub(province.province_id)

			for rail_id in getattr(province, "railid", []):
				manager.add_rail(rail_id)

			for built in getattr(province, "buildings", []):
				building_type = getattr(built, "building_type", None)
				if building_type == 3:
					manager.add_production_suply(province.province_id)
				elif building_type == 7:
					manager.add_production_ammo(province.province_id)

		for train in self.trains.values():
			nation_tag = getattr(train, "nation", None)
			manager = self._get_logistics_manager(nation_tag)
			if manager is None:
				continue
			manager.add_train(getattr(train, "id", None), getattr(train, "location", None))

		for army in self.armies.values():
			for unit in army.units.values():
				manager = self._get_logistics_manager(getattr(unit, "nation", None))
				if manager is None:
					continue
				manager.add_suply_request(unit)

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


	def Autonumous_logi(self):
		
		for manager in self.logistic_man:
			manager.routine()
		
		
		pass

class logisticsManager:
	
	def __init__(self, nation):
		self.nation = nation
		self.provinces = []
		self.suply_list = []
		self.ammo_list = []
		
		self.logistics_units = []

		
		self.suply_production = []
		self.ammo_production = []
		self.logistics_hubs = []
		self.rails = [] #the rail ids that the nation has control. 
		self.trains = []#the train ids that the nation has control.
		self.train_locations = {}

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

	def add_province(self, province_id,current_suply=0, current_ammo=0):
		if province_id not in self.provinces:
			self.provinces.append([province_id,current_suply, current_ammo])

	def _build_supply_entry(self, unit):
		return [
			getattr(unit, "id", None),
			getattr(unit, "location", None),
			getattr(unit, "suply", 0),
			getattr(unit, "suply_consumption", 0),
		]

	def routine(self):
		total_suply_needed = self.suply_cost()
		print(f"Nation {self.nation} requires a total of {total_suply_needed} supply units.")

	def suply_cost(self):
		#this takes all the unit costs and adds them up to see how much supply is needed for the nation and provide that info for the player 
		suply_needed = 0
		for unit_entry in self.suply_list:
			if not unit_entry:
				continue
			if len(unit_entry) >= 4:
				suply_needed += unit_entry[3]
		return suply_needed
	
	
	
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
			if getattr(unit_or_id, "type", None) == 4 and unit_entry[0] not in self.logistics_units:
				self.logistics_units.append(unit_entry[0])
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
			print(f"Logistics hub added on the manager for nation {self.nation} in province {province_id}." )

	def remove_logistics_hub(self, province_id):
		if province_id in self.logistics_hubs:
			self.logistics_hubs.remove(province_id) 
			print(f"Logistics hub removed from the manager for nation {self.nation} in province {province_id}.")

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
	
	
	

	
