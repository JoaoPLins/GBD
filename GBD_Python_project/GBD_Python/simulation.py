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

		for manager in self.logistic_man:
			manager.refresh_province_stockpiles()

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
			manager.execute_manual_train_assignments_tick()
			manager.execute_manual_logistics_assignments_tick()

		if not self.Suply_tick:
			return

		if self._last_logistics_planning_day == self.current_day:
			return

		self._last_logistics_planning_day = self.current_day

		for manager in self.logistic_man:
			manager.routine()

class logisticsManager:
	
	def __init__(self, nation, simulation=None):
		self.nation = nation
		self.simulation = simulation
		self.provinces = []
		self.suply_list = []
		self.ammo_list = []
		self.pending_supply_requests = []
		self._request_counter = 0
		
		self.logistics_units = []

		
		self.suply_production = []
		self.ammo_production = []
		self.logistics_hubs = []
		self.rails = [] #the rail ids that the nation has control. 
		self.trains = []#the train ids that the nation has control.
		self.train_locations = {}
		self.manual_train_assignments = []
		self._train_assignment_counter = 0
		self.manual_logistics_assignments = []
		self._logistics_assignment_counter = 0

	def bind_context(self, simulation):
		self.simulation = simulation

	def reset_runtime_lists(self):
		self.provinces = []
		self.suply_list = []
		self.ammo_list = []
		self.pending_supply_requests = []
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
		print(f"  Pending Supply Requests: {self.pending_supply_requests}")
		print(f"  Manual Train Assignments: {self.manual_train_assignments}")
		print(f"  Manual Logistics Assignments: {self.manual_logistics_assignments}")

	def add_province(self, province_id,current_suply=0, current_ammo=0):
		for entry in self.provinces:
			if entry[0] == province_id:
				entry[1] = current_suply
				entry[2] = current_ammo
				return
		self.provinces.append([province_id,current_suply, current_ammo])

	def _get_province_object(self, province_id):
		if self.simulation is None:
			return None
		return self.simulation.game_map.get_province_object_by_id(province_id)

	def _get_train(self, train_id):
		if self.simulation is None:
			return None
		return self.simulation.trains.get(str(train_id))

	def _next_train_assignment_id(self):
		self._train_assignment_counter += 1
		return f"{self.nation}-TRN-{self._train_assignment_counter}"

	def _next_logistics_assignment_id(self):
		self._logistics_assignment_counter += 1
		return f"{self.nation}-LOGI-{self._logistics_assignment_counter}"

	def _rail_path_exists(self, source_province_id, destination_province_id):
		if self.simulation is None:
			return False
		path = self.simulation.game_map.find_rail_path(source_province_id, destination_province_id)
		return len(path) > 1

	def _is_train_automatic(self, train):
		if train is None:
			return False
		if getattr(train, "automatic", True) is False:
			return False
		if getattr(train, "manual_order", False):
			return False
		if getattr(train, "manual_assignment", None):
			return False
		if getattr(train, "automation_locked", False):
			return False
		return True

	def _get_unit(self, unit_id):
		if self.simulation is None:
			return None
		return self.simulation._find_unit_by_id(unit_id)

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

	def _source_is_train_eligible(self, source_province_id):
		if source_province_id in self.logistics_hubs:
			return True
		province = self._get_province_object(source_province_id)
		if province is None:
			return False
		return self._province_suply_value(province) >= 1000

	def _source_is_logistics_eligible(self, source_province_id):
		# Logistics companies load from hubs in this phase.
		if source_province_id not in self.logistics_hubs:
			return False
		province = self._get_province_object(source_province_id)
		if province is None:
			return False
		return self._province_suply_value(province) > 0

	def _assignment_is_open(self, assignment):
		return assignment.get("status") not in ("completed", "failed", "cancelled")

	def _distance_hops(self, start_id, goal_id):
		if start_id == goal_id:
			return 0
		if self.simulation is None or start_id is None or goal_id is None:
			return float("inf")

		visited = {start_id}
		queue = [(start_id, 0)]

		while queue:
			current, distance = queue.pop(0)
			province = self.simulation.game_map.get_province_by_id(current)
			if not province:
				continue
			for neighbor in province.get("nearby_provinces", []):
				if neighbor in visited:
					continue
				if neighbor == goal_id:
					return distance + 1
				visited.add(neighbor)
				queue.append((neighbor, distance + 1))

		return float("inf")

	def _nearest_hub(self, province_id, candidate_hubs):
		best_hub = None
		best_distance = float("inf")
		for hub_id in candidate_hubs:
			distance = self._distance_hops(province_id, hub_id)
			if distance < best_distance:
				best_distance = distance
				best_hub = hub_id
		return best_hub, best_distance

	def _train_busy(self, train_id):
		for assignment in self.manual_train_assignments:
			if not self._assignment_is_open(assignment):
				continue
			if assignment.get("train_id") == str(train_id):
				return True
		return False

	def _logistics_unit_busy(self, unit_id):
		for assignment in self.manual_logistics_assignments:
			if not self._assignment_is_open(assignment):
				continue
			if assignment.get("logistics_unit_id") == str(unit_id):
				return True
		return False

	def _has_open_delivery_for_unit(self, destination_unit_id):
		for assignment in self.manual_logistics_assignments:
			if not self._assignment_is_open(assignment):
				continue
			if assignment.get("destination_unit_id") == str(destination_unit_id):
				return True
		return False

	def _available_trains_for_planning(self):
		trains = []
		for train_id in self.trains:
			train = self._get_train(train_id)
			if train is None:
				continue
			if not self._is_train_automatic(train):
				continue
			if getattr(train, "status", 0) in (1, 6, 7):
				continue
			if self._train_busy(train.id):
				continue
			trains.append(train)
		return trains

	def _available_logistics_units_for_planning(self):
		units = []
		for unit in self._iter_nation_units() or []:
			if getattr(unit, "type", None) != 4:
				continue
			if not self._is_logistics_unit_automatic(unit):
				continue
			if getattr(unit, "status", 0) in (3, 4):
				continue
			if self._logistics_unit_busy(unit.id):
				continue
			units.append(unit)
		return units

	def _available_hub_stockpiles_for_planning(self):
		stock_by_hub = {}
		for province_id, current_suply, _ in self.provinces:
			if province_id not in self.logistics_hubs:
				continue
			stock_by_hub[province_id] = max(0, int(current_suply or 0))
		return stock_by_hub

	def _create_train_assignment_for_plan(self, train, source_hub, destination_hub, amount):
		assignment = self.create_manual_train_supply_assignment(
			train_id=train.id,
			source_province_id=source_hub,
			destination_province_id=destination_hub,
			amount=amount,
		)
		if assignment is not None:
			assignment["created_by"] = "planner"
		return assignment

	def _create_logistics_assignment_for_plan(self, logistics_unit, source_hub, destination_unit_id, amount):
		assignment = self.create_manual_logistics_supply_assignment(
			logistics_unit_id=logistics_unit.id,
			source_hub_province_id=source_hub,
			destination_unit_id=destination_unit_id,
			amount=amount,
		)
		if assignment is not None:
			assignment["created_by"] = "planner"
		return assignment

	def _run_daily_logistics_planner(self):
		"""Create daily transport assignments from requests without moving inventories."""
		if not self.pending_supply_requests:
			return {"train_assignments": 0, "logistics_assignments": 0}

		available_trains = self._available_trains_for_planning()
		available_logistics_units = self._available_logistics_units_for_planning()
		available_hubs = list(self.logistics_hubs)
		if not available_hubs:
			return {"train_assignments": 0, "logistics_assignments": 0}

		reserved_stock = self._available_hub_stockpiles_for_planning()
		train_created = 0
		logistics_created = 0

		requests = sorted(self.pending_supply_requests, key=lambda req: (-int(req.get("daily_consumption", 0)), -int(req.get("requested_suply", 0))))

		for request in requests:
			unit_id = request.get("unit_id")
			unit_location = request.get("location")
			requested_suply = max(0, int(request.get("requested_suply", 0) or 0))
			if requested_suply <= 0:
				continue
			if self._has_open_delivery_for_unit(unit_id):
				continue

			front_hub, _ = self._nearest_hub(unit_location, available_hubs)
			if front_hub is None:
				continue

			if reserved_stock.get(front_hub, 0) <= 0 and available_trains:
				candidate_source = None
				candidate_amount = 0
				for hub_id in available_hubs:
					if hub_id == front_hub:
						continue
					if reserved_stock.get(hub_id, 0) <= 0:
						continue
					if not self._rail_path_exists(hub_id, front_hub):
						continue
					available_amount = min(requested_suply, reserved_stock.get(hub_id, 0))
					if available_amount > candidate_amount:
						candidate_source = hub_id
						candidate_amount = available_amount

				if candidate_source is not None and candidate_amount > 0:
					train = available_trains.pop(0)
					assignment = self._create_train_assignment_for_plan(train, candidate_source, front_hub, candidate_amount)
					if assignment is not None:
						reserved_stock[candidate_source] = max(0, reserved_stock.get(candidate_source, 0) - candidate_amount)
						reserved_stock[front_hub] = reserved_stock.get(front_hub, 0) + candidate_amount
						train_created += 1

			if reserved_stock.get(front_hub, 0) <= 0:
				continue
			if not available_logistics_units:
				continue

			available_amount = min(requested_suply, reserved_stock.get(front_hub, 0))
			if available_amount <= 0:
				continue

			best_idx = None
			best_dist = float("inf")
			for idx, logi_unit in enumerate(available_logistics_units):
				distance = self._distance_hops(getattr(logi_unit, "location", None), front_hub)
				if distance < best_dist:
					best_dist = distance
					best_idx = idx

			if best_idx is None:
				continue

			logistics_unit = available_logistics_units.pop(best_idx)
			assignment = self._create_logistics_assignment_for_plan(logistics_unit, front_hub, unit_id, available_amount)
			if assignment is None:
				continue

			reserved_stock[front_hub] = max(0, reserved_stock.get(front_hub, 0) - available_amount)
			logistics_created += 1

		return {
			"train_assignments": train_created,
			"logistics_assignments": logistics_created,
		}

	def create_manual_train_supply_assignment(self, train_id, source_province_id, destination_province_id, amount):
		"""Create a manual train supply transfer assignment for test/debug workflows."""
		train = self._get_train(train_id)
		if train is None:
			return None
		if not self._is_train_automatic(train):
			return None

		source = int(source_province_id)
		destination = int(destination_province_id)
		amount = max(0, int(amount or 0))
		if amount <= 0:
			return None
		if source == destination:
			return None
		if destination not in self.logistics_hubs:
			return None
		if not self._source_is_train_eligible(source):
			return None
		if not self._rail_path_exists(source, destination):
			return None

		assignment = {
			"assignment_id": self._next_train_assignment_id(),
			"assignment_type": "manual_train_supply",
			"train_id": str(train.id),
			"source_province_id": source,
			"destination_province_id": destination,
			"target_amount": amount,
			"loaded_amount": 0,
			"delivered_amount": 0,
			"phase": "to_source",
			"status": "planned",
		}

		self.manual_train_assignments.append(assignment)
		return assignment

	def create_manual_logistics_supply_assignment(self, logistics_unit_id, source_hub_province_id, destination_unit_id, amount):
		"""Create a manual logistics-company supply assignment for test/debug workflows."""
		logistics_unit = self._get_unit(logistics_unit_id)
		if logistics_unit is None:
			return None
		if not self._is_logistics_unit_automatic(logistics_unit):
			return None

		source = int(source_hub_province_id)
		destination_unit = self._get_unit(destination_unit_id)
		if destination_unit is None:
			return None
		if getattr(destination_unit, "nation", None) != self.nation:
			return None
		if getattr(destination_unit, "type", None) == 4:
			return None

		amount = max(0, int(amount or 0))
		if amount <= 0:
			return None
		if not self._source_is_logistics_eligible(source):
			return None

		assignment = {
			"assignment_id": self._next_logistics_assignment_id(),
			"assignment_type": "manual_logistics_supply",
			"logistics_unit_id": str(logistics_unit.id),
			"source_province_id": source,
			"destination_unit_id": str(destination_unit.id),
			"target_amount": amount,
			"loaded_amount": 0,
			"delivered_amount": 0,
			"phase": "to_source",
			"status": "planned",
		}

		self.manual_logistics_assignments.append(assignment)
		return assignment

	def _execute_single_train_assignment_tick(self, assignment):
		if self.simulation is None:
			assignment["status"] = "failed"
			assignment["reason"] = "no-simulation"
			return

		train = self._get_train(assignment["train_id"])
		if train is None:
			assignment["status"] = "failed"
			assignment["reason"] = "train-missing"
			return
		if not self._is_train_automatic(train):
			assignment["status"] = "failed"
			assignment["reason"] = "train-not-automatic"
			return

		source = assignment["source_province_id"]
		destination = assignment["destination_province_id"]

		if assignment["phase"] == "to_source":
			if int(getattr(train, "location", 0)) != source:
				if self.simulation._find_train_movement_index(train.id) is None:
					self.simulation.train_pathing(train.id, source)
				assignment["status"] = "active"
				return
			assignment["phase"] = "loading"
			assignment["status"] = "active"

		if assignment["phase"] == "loading":
			province = self._get_province_object(source)
			if province is None:
				assignment["status"] = "failed"
				assignment["reason"] = "source-missing"
				return

			remaining_to_load = max(0, int(assignment["target_amount"] - assignment["loaded_amount"]))
			if remaining_to_load <= 0:
				assignment["phase"] = "to_destination"
				return

			current_suply = max(0, int(getattr(train, "suply", 0) or 0))
			capacity = max(0, int(getattr(train, "suplyCapacity", 0) or 0))
			free_capacity = max(0, capacity - current_suply)
			source_available = self._province_suply_value(province)

			load_amount = min(1000, remaining_to_load, free_capacity, source_available)
			if load_amount <= 0:
				# If full or source is temporarily dry, move on with what is loaded.
				assignment["phase"] = "to_destination"
				return

			province.transfer_suply(load_amount)
			train.suply = current_suply + load_amount
			assignment["loaded_amount"] += load_amount
			assignment["status"] = "active"

			remaining_to_load = max(0, int(assignment["target_amount"] - assignment["loaded_amount"]))
			current_suply = max(0, int(getattr(train, "suply", 0) or 0))
			free_capacity = max(0, capacity - current_suply)
			if remaining_to_load <= 0 or free_capacity <= 0:
				assignment["phase"] = "to_destination"
			return

		if assignment["phase"] == "to_destination":
			if int(getattr(train, "location", 0)) != destination:
				if self.simulation._find_train_movement_index(train.id) is None:
					self.simulation.train_pathing(train.id, destination)
				assignment["status"] = "active"
				return
			assignment["phase"] = "unloading"
			assignment["status"] = "active"

		if assignment["phase"] == "unloading":
			province = self._get_province_object(destination)
			if province is None:
				assignment["status"] = "failed"
				assignment["reason"] = "destination-missing"
				return

			remaining_to_deliver = max(0, int(assignment["loaded_amount"] - assignment["delivered_amount"]))
			train_suply = max(0, int(getattr(train, "suply", 0) or 0))
			unload_amount = min(1000, remaining_to_deliver, train_suply)

			if unload_amount <= 0:
				assignment["status"] = "completed"
				return

			train.suply = train_suply - unload_amount
			province.add_suply(unload_amount)
			assignment["delivered_amount"] += unload_amount
			assignment["status"] = "active"

			remaining_to_deliver = max(0, int(assignment["loaded_amount"] - assignment["delivered_amount"]))
			if remaining_to_deliver <= 0:
				assignment["status"] = "completed"

	def execute_manual_train_assignments_tick(self):
		"""Execute existing manual train assignments without creating new plans."""
		for assignment in self.manual_train_assignments:
			if assignment.get("status") in ("completed", "failed", "cancelled"):
				continue
			self._execute_single_train_assignment_tick(assignment)

	def _execute_single_logistics_assignment_tick(self, assignment):
		if self.simulation is None:
			assignment["status"] = "failed"
			assignment["reason"] = "no-simulation"
			return

		logistics_unit = self._get_unit(assignment["logistics_unit_id"])
		if logistics_unit is None:
			assignment["status"] = "failed"
			assignment["reason"] = "logistics-unit-missing"
			return
		if not self._is_logistics_unit_automatic(logistics_unit):
			assignment["status"] = "failed"
			assignment["reason"] = "unit-not-automatic"
			return

		destination_unit = self._get_unit(assignment["destination_unit_id"])
		if destination_unit is None:
			assignment["status"] = "failed"
			assignment["reason"] = "destination-unit-missing"
			return

		source = assignment["source_province_id"]
		destination = int(getattr(destination_unit, "location", 0) or 0)

		if assignment["phase"] == "to_source":
			if int(getattr(logistics_unit, "location", 0) or 0) != source:
				if self.simulation._find_movement_index(logistics_unit.id) is None:
					self.simulation.pathing(logistics_unit.id, source)
				assignment["status"] = "active"
				return
			assignment["phase"] = "loading"
			assignment["status"] = "active"

		if assignment["phase"] == "loading":
			province = self._get_province_object(source)
			if province is None:
				assignment["status"] = "failed"
				assignment["reason"] = "source-missing"
				return

			if not self._source_is_logistics_eligible(source):
				assignment["status"] = "failed"
				assignment["reason"] = "source-not-eligible"
				return

			logistics_unit.calculate_logistics_value()
			current_suply = max(0, int(getattr(logistics_unit, "suply", 0) or 0))
			capacity = max(0, int(getattr(logistics_unit, "logistics_value", 0) or 0))
			free_capacity = max(0, capacity - current_suply)
			remaining_to_load = max(0, int(assignment["target_amount"] - assignment["loaded_amount"]))
			source_available = self._province_suply_value(province)

			load_amount = min(1000, remaining_to_load, free_capacity, source_available)
			if load_amount <= 0:
				if assignment["loaded_amount"] <= 0:
					assignment["status"] = "failed"
					assignment["reason"] = "nothing-loaded"
					return
				assignment["phase"] = "to_destination"
				return

			province.transfer_suply(load_amount)
			logistics_unit.load_suply(load_amount)
			assignment["loaded_amount"] += load_amount
			assignment["status"] = "active"

			remaining_to_load = max(0, int(assignment["target_amount"] - assignment["loaded_amount"]))
			current_suply = max(0, int(getattr(logistics_unit, "suply", 0) or 0))
			free_capacity = max(0, capacity - current_suply)
			if remaining_to_load <= 0 or free_capacity <= 0:
				assignment["phase"] = "to_destination"
			return

		if assignment["phase"] == "to_destination":
			current_location = int(getattr(logistics_unit, "location", 0) or 0)
			if current_location != destination:
				if self.simulation._find_movement_index(logistics_unit.id) is None:
					self.simulation.pathing(logistics_unit.id, destination)
				assignment["status"] = "active"
				return
			assignment["phase"] = "unloading"
			assignment["status"] = "active"

		if assignment["phase"] == "unloading":
			remaining_to_deliver = max(0, int(assignment["loaded_amount"] - assignment["delivered_amount"]))
			carrier_suply = max(0, int(getattr(logistics_unit, "suply", 0) or 0))
			unload_amount = min(1000, remaining_to_deliver, carrier_suply)

			if unload_amount <= 0:
				assignment["status"] = "completed"
				return

			actual_unloaded = logistics_unit.unload_suply(unload_amount)
			actual_unloaded = max(0, int(actual_unloaded or 0))
			if actual_unloaded <= 0:
				assignment["status"] = "completed"
				return

			destination_unit.add_suply(actual_unloaded)
			assignment["delivered_amount"] += actual_unloaded
			assignment["status"] = "active"

			remaining_to_deliver = max(0, int(assignment["loaded_amount"] - assignment["delivered_amount"]))
			if remaining_to_deliver <= 0:
				assignment["status"] = "completed"

	def execute_manual_logistics_assignments_tick(self):
		"""Execute existing manual logistics-company assignments without auto planning."""
		for assignment in self.manual_logistics_assignments:
			if assignment.get("status") in ("completed", "failed", "cancelled"):
				continue
			self._execute_single_logistics_assignment_tick(assignment)

	def _province_ammo_value(self, province):
		if province is None:
			return 0
		return max(0, int(getattr(province, "ammo", 0) or 0))

	def _province_suply_value(self, province):
		if province is None:
			return 0
		return max(0, int(getattr(province, "suply", 0) or 0))

	def refresh_province_stockpiles(self):
		"""Snapshot current province supply/ammo from game state into planner cache."""
		for entry in self.provinces:
			province_id = entry[0]
			province = self._get_province_object(province_id)
			entry[1] = self._province_suply_value(province)
			entry[2] = self._province_ammo_value(province)

	def _daily_factory_output(self):
		"""Return total daily supply output from factories (building type 3)."""
		total_suply = 0
		for province_id in self.suply_production:
			province = self._get_province_object(province_id)
			if province is None:
				continue
			for built in getattr(province, "buildings", []):
				if getattr(built, "building_type", None) == 3:
					production_factor = getattr(built, "building_level", 1) * (getattr(built, "production", 100) / 100)
					total_suply += int(8000 * production_factor)
		return total_suply

	def _daily_arsenal_output(self):
		"""Return total daily ammo output from arsenals (building type 7)."""
		total_ammo = 0
		for province_id in self.ammo_production:
			province = self._get_province_object(province_id)
			if province is None:
				continue
			for built in getattr(province, "buildings", []):
				if getattr(built, "building_type", None) == 7:
					production_factor = getattr(built, "building_level", 1) * (getattr(built, "production", 100) / 100)
					total_ammo += int(15000 * production_factor)
		return total_ammo

	def _build_supply_entry(self, unit):
		current_suply = max(0, int(getattr(unit, "suply", 0) or 0))
		daily_consumption = max(0, int(getattr(unit, "suply_consumption", 0) or 0))
		projected_after_daily = max(0, current_suply - daily_consumption)
		return [
			getattr(unit, "id", None),
			getattr(unit, "location", None),
			current_suply,
			daily_consumption,
			projected_after_daily,
		]

	def _iter_nation_units(self):
		if self.simulation is None:
			return
		for army in self.simulation.armies.values():
			for unit in army.units.values():
				if getattr(unit, "nation", None) == self.nation:
					yield unit

	def _next_request_id(self):
		self._request_counter += 1
		return f"{self.nation}-SUPREQ-{self._request_counter}"

	def _collect_unit_supply_cycle(self):
		"""Refresh manager-side unit supply state for this logistics cycle."""
		self.suply_list = []
		for unit in self._iter_nation_units() or []:
			self.add_suply_request(unit)

	def _is_low_supply(self, current_suply, daily_consumption, projected_after_daily):
		if daily_consumption <= 0:
			return False
		if projected_after_daily <= 0:
			return True
		return projected_after_daily < (daily_consumption * 2)

	def _generate_supply_requests(self):
		"""Create daily supply requests for units projected to run low."""
		self.pending_supply_requests = []

		for entry in self.suply_list:
			if not entry or len(entry) < 5:
				continue

			unit_id = entry[0]
			location = entry[1]
			current_suply = max(0, int(entry[2] or 0))
			daily_consumption = max(0, int(entry[3] or 0))
			projected_after_daily = max(0, int(entry[4] or 0))

			if not self._is_low_supply(current_suply, daily_consumption, projected_after_daily):
				continue

			target_buffer = daily_consumption * 3
			requested_amount = max(0, target_buffer - projected_after_daily)
			if requested_amount <= 0:
				continue

			self.pending_supply_requests.append({
				"request_id": self._next_request_id(),
				"unit_id": str(unit_id),
				"nation": self.nation,
				"location": location,
				"current_suply": current_suply,
				"daily_consumption": daily_consumption,
				"projected_after_daily": projected_after_daily,
				"requested_suply": requested_amount,
			})

	def routine(self):
		self.refresh_province_stockpiles()
		self._collect_unit_supply_cycle()
		self._generate_supply_requests()
		planner_result = self._run_daily_logistics_planner()
		total_suply = sum(entry[1] for entry in self.provinces)
		total_ammo = sum(entry[2] for entry in self.provinces)
		factory_output = self._daily_factory_output()
		arsenal_output = self._daily_arsenal_output()
		total_suply_needed = self.suply_cost()
		print(
			f"Nation {self.nation} stockpiles -> supply={total_suply}, ammo={total_ammo}, "
			f"daily_factory_supply={factory_output}, daily_arsenal_ammo={arsenal_output}, "
			f"daily_unit_consumption={total_suply_needed}, generated_supply_requests={len(self.pending_supply_requests)}, "
			f"planner_train_assignments={planner_result['train_assignments']}, "
			f"planner_logistics_assignments={planner_result['logistics_assignments']}"
		)

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
	
	



	

	
