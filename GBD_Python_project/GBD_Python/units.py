from ast import Pass
import json
from pathlib import Path

#totalUnits = 0

class Unit:
    """Represents a single military unit."""
    
    def __init__(self, unit_id, name, nation, location, home, army, soldiers, type_of_unit, leader_id, reserve, logistics, suply, status):
        """
        Initialize a Unit.

        attack defense and speed will be calculated by the class, the spots used will be used for other systems. I don't remeber right now what they were
        
        Args:
            unit_id: Unique identifier for the unit
            name: Name of the unit
            nation: Nation code the unit belongs to
            location: Province ID where the unit is located
            home: Home province ID
            army: Army/Unit group ID the unit belongs to
            soldiers: Number of soldiers in the unit
            type: Type of unit (1 for infantry, 2 for cavalry, etc.)
            logistics: Logistics stat
            suply: Supply value
            status: Status of the unit
        """
        self.id = unit_id
        self.name = name
        self.nation = nation
        self.location = location  # Province ID
        self.home = home  # Home province ID
        self.army = army  # Unit group ID
        self.soldiers = soldiers
        self.type = type_of_unit # 1 for infantry, 2 for cavalary, 3 for artilihary, 4 for logistics, 5 for HQ, 6 for milita/police 7 for engineers, 8 for mountaineers(TBI)
        self.reserve = reserve
        self.targetsize = soldiers
        self.leader_id = leader_id
        self.attack = 0
        self.defense = 0
        self.speed = 0
        self.transport_V = 0 #amount of trucks
        self.transport_H = logistics #amount of horses
        self.logistics_value = 0 # ammount of suply + ammo + equipment + fuel.  
        self.suply = suply # this is basically food; could consider basic necesseties... 
        self.unit_full_suply = False
        self.unit_full_ammo = False
        self.ammo = 0
        self.officers = 0
        self.guns = 0
        self.fuel_horse = 0
        self.fuel = 0
        self.status = status
        self.unit_spotting = [0,0]
        self.unit_dectectability = 0
        self.counter = 0
        self.fatigue = 0
        self.morale = 100
        self.organization = 100
        self.experience = 0
        self.units_spoted = []
        self.spotting_quality = []
        self.spoted_by = []
        self.visibility = 0
        self.unitCurrentSpoting = 0
        self.suply_consumption = 0
        #to be implemented on units battles
        self.ammo_consumption = 0
        #to be implement on after the first demo.
        self.suply_fuel_consumption = 0
        self.suply_math = 0 
        #totalUnits += 1
        self.subordinate_units_ids = []
        self.logistics_role = False

        self.update_dectectability()
        self.update_spotting()
        self.calculate_visibility()
        self.calculate_logistics_value()


    def return_status(self):
        #refractor this in the future. maybe using @proprety for it and dictionaries. to study
        """
        Return what the unit is doing 
        0 - reserve
        1 - Depoloyed
        2 - Quartered
        3 - moving
        4 - resting
        5 - defending
        6 - improving defenses
        7 - securing province
        8 - disorganized
        9 - Guerrila/Recon
        10 - Attacking
        11 - mobilizing
        12 - strategic redeployment
        13 - forming up (creating a new unit)
        14 - training (not implemented yet)
        15 - logistics work
        """
        if self.status == 0:
            return "Reserve"
        elif self.status == 1:
            return "Deployed"
        elif self.status == 2:
            return "Quartered"
        elif self.status == 3:
            return "Moving"
        elif self.status == 4:
            return "Resting"
        elif self.status == 5:
            return "Defending"
        elif self.status == 6:
            return "Improving Defenses"
        elif self.status == 7:
            return "Securing Province"
        elif self.status == 8:
            return "Disorganized"
        elif self.status == 9:
            return "Guerrilla/Recon"
        elif self.status == 10:
            return "Attacking"
        elif self.status == 11:
            return "Mobilizing"
        elif self.status == 12:
            return "Strategic Redeployment"
        elif self.status == 13:
            return "Forming Up"
        elif self.status == 14:
            return "Training"  
        elif self.status == 15:
            return "Logistics Work"
        else:
            return "Unknown Status"
        
    def update_status(self, new_status):
        """
        Update the unit's status.
        
        Args:
            new_status: New status code to set for the unit
        """
        self.status = new_status
        if new_status == 0:
            self.demobilize()
        if new_status == 11:
            self.organization = 10
        if self.logistics_role and new_status == 1:
            self.status = 15  # Set to logistics work if the unit has a logistics role should work as such when on logistic duties( after moviment it sets to  that.)
        self.update_dectectability()
        self.update_spotting()
        self.calculate_visibility()

    def update_counter(self, new_counter):
        """
        Update the unit's counter (used for movement or action timing).
        
        Args:
            new_counter: New counter value to set for the unit
        """
        self.counter = new_counter

    def update_spotting(self):
        #refractor this in the future. maybe using @proprety for it and dictionaries. to study
        #                        [provinces near , the current province]
        if self.status == 0:
            self.unit_spotting = [0,1]
        elif self.status == 1:
            self.unit_spotting = [50,50]
        elif self.status == 2:
            self.unit_spotting = [5,25]
        elif self.status == 3:
            self.unit_spotting = [7,35]
        elif self.status == 4:
            self.unit_spotting = [0,35]
        elif self.status == 5:
            self.unit_spotting = [25,70]
        elif self.status == 6:
            self.unit_spotting = [20,60]
        elif self.status == 7:
            self.unit_spotting = [30,95]
        elif self.status == 8:
            self.unit_spotting = [0,0]
        elif self.status == 9:
            self.unit_spotting = [15,95]
        elif self.status == 10:
            self.unit_spotting = [50,50]
        elif self.status == 11:
            self.unit_spotting = [0,1]
        elif self.status == 12:
            self.unit_spotting = [0,1]
        elif self.status == 13:
            self.unit_spotting = [0,1]


    def update_dectectability(self):
        #refractor this in the future. maybe using @proprety for it and dictionaries. to study
        if self.status == 0:
            self.unit_dectectability = 1
        elif self.status == 1:
            self.unit_dectectability = 100
        elif self.status == 2:
            self.unit_dectectability = 100
        elif self.status == 3:
            self.unit_dectectability = 50
        elif self.status == 4:
            self.unit_dectectability = 50
        elif self.status == 5:
            self.unit_dectectability = 75
        elif self.status == 6:
            self.unit_dectectability = 75
        elif self.status == 7:
            self.unit_dectectability = 100
        elif self.status == 8:
            self.unit_dectectability = 30
        elif self.status == 9:
            self.unit_dectectability = 10
        elif self.status == 10:
            self.unit_dectectability = 200
        elif self.status == 11:
            self.unit_dectectability = 50
        elif self.status == 12:
            self.unit_dectectability = 100
        elif self.status == 13:
            self.unit_dectectability = 100

    def return_home(self):
        #returns true if the unit is in its home province, false otherwise.
        return self.home

    def calculate_visibility(self):
        #calculates the visibility on the unit instead of doing everytime in the simulation. future update will add this value with other simulated situations like terrain weather.
        self.visibility = (self.unit_dectectability * (self.soldiers))//1000
    
    def return_spotting(self, where):
        #calculates the spotting hability of a unit on other units
        self.unitCurrentSpoting = (self.unit_spotting[where] * (self.soldiers // 100))//200
        return self.unitCurrentSpoting
    
    def demobilize(self):
        #demobilizes the unit, setting soldiers to 0 and status to reserve
        self.reserve = self.soldiers 
        if self.targetsize - self.soldiers > self.soldiers * 10:
            self.soldiers = 0
        else:
            self.soldiers = self.soldiers // 10
            self.reserve = self.reserve - self.soldiers
        
        #self.update_status(0)  OOOPS
    
    def mobilize(self,soldiers_delta):
        #mobilizes the unit, setting soldiers to targetsize and status to deployed
        if self.reserve > 0:
            #it will take in consideration later the value of the infrastructure of the province. 
            #soldiersdelta =  100 * 1  #+ infrastructure value of the province 
            if soldiers_delta > self.reserve:
                soldiers_delta = self.reserve
                self.update_status(1)

            self.soldiers += soldiers_delta
            self.reserve -= soldiers_delta
            if self.organization < 100:
                self.organization += 1
            


        else:
            self.status = 1

    def possible_status(self):
        #returns a list of possible status for the unit to be set by the player.
        possiblestatus = []
        if self.status != 0 and self.status != 11:
            possiblestatus.append(5) #defending is always an option
            if self.location == self.home:
                possiblestatus.append(0) #reserve
                possiblestatus.append(2) #quartered
                possiblestatus.append(4) #resting
            if self.organization > 10:
                possiblestatus.append(3) #moving
                possiblestatus.append(4) #resting
            if self.organization > 25:
                possiblestatus.append(7) #securing province
                possiblestatus.append(10) #attacking
            if self.organization > 50:
                possiblestatus.append(1) #deployed
                possiblestatus.append(6) #improving defenses
            if self.organization > 75:
                possiblestatus.append(9) #guerrila/recon
        else: 
            if self.reserve > 0:
                possiblestatus.append(11) #mobilizing


        return possiblestatus

    def return_soldiers_target_delta(self):
        #returns the target size of the unit, which is the number of soldiers it should have when fully mobilized.
        delta = self.targetsize - (self.soldiers + self.reserve)
        return delta

    def add_soldiers(self, number):
        #adds soldiers to the unit, up to the target size.
        self.soldiers += number

    def set_target_size(self, number):
        #sets the target size of the unit, which is the number of soldiers it should have when fully mobilized.
        if self.home == self.location:
            self.targetsize = number 

    def is_spotted(self):
        #returns true if the unit is spotted by any other unit, false otherwise.
        if len(self.spoted_by) > 0:
            return True
        else:
            return False
        
    def return_spoted_by(self):
        #returns a list of unit ids that have spotted this unit.
        return self.spoted_by
    
    def return_spotQuality_from_unit_id(self,unit_id):
        dx = self.units_spoted.index(unit_id)
        return self.spotting_quality[dx]

    def edit_spotQuality_from_unit_id(self,unit_id,new_value):
        dx = self.units_spoted.index(unit_id)
        if self.spotting_quality[dx] <101:
            self.spotting_quality[dx] += new_value
            print(f"Updated spotting quality for unit {unit_id} to {self.spotting_quality[dx]}")
        else:
            print(f"Spotting quality for unit {unit_id} is already at maximum (100). No update applied.")
            self.spotting_quality[dx] = 100

    def pop_the_unit_from_unit_spoted(self, unit_id):
        #removes a unit id from the list of units that have spotted this unit.
        try:
            idx = self.units_spoted.index(unit_id)
            del self.units_spoted[idx]
            del self.spotting_quality[idx]
            self.unitCurrentSpoting -= 1
            return True
        except ValueError:
            return False

    def add_soldiers(self,number):  
        #adds soldiers to the unit, up to the target size.
        self.soldiers += number


    def add_suply(self, amount):
        #adds suply to the unit, up to the logistics capacity.
        self.suply += amount

    def calculate_logistics_value(self):
        #calculates the logistics value of the unit, or the max suply they can cary without penalties (logistics units will be implemented later)
        #print(f"calculating logistics value of unit {self.id}")
        Soldier_suply = 5
        if self.type == 2:
            Soldier_suply = 10 #infantry
        self.logistics_value = (self.transport_V*100) + (self.transport_H*20) + (self.soldiers * Soldier_suply)
        #print(f"Unit {self.id} logistics value calculated: {self.logistics_value}, Soldiers: {self.soldiers}, Transport_V: {self.transport_V}, Transport_H: {self.transport_H}")
    
    def calculate_logistic_consumption(self):
        #calculates the logistics consumption of the unit, which is the amount of suply they consume per turn.
        #print(f"calculating logistics consumption of unit {self.id}")
        self.suply_consumption = self.soldiers 

    def calculate_logistic_request(self):
        #will require to call ammo as well. and if it loses equipment. 
        self.suply_request = self.suply_consumption + 50 
        print(f"Unit {self.id} supply request calculated: {self.suply_request}, Supply Consumption: {self.suply_consumption}")
        if self.suply >= self.logistics_value:
            #might change this depending on how it goes. I don't want suply to get too high and not being able to take amo into the unit. 
            self.suply_request = 0
            #print(f"Unit {self.id} supply request adjusted to consumption: {self.suply_request}, Supply Consumption: {self.suply_consumption}")

    def calculate_logistic_request_nextProvince(self):
        if self.suply < self.logistics_value:
            max_vaule = (self.transport_V*100) + (self.transport_H*20)
        else:
            max_vaule = 0
        
        return max_vaule


    #this might be useful? 
    #def is_unit_full_suply(self):
    #    #returns true if the unit has full suply, false otherwise.
    #    if self.suply >= self.logistics_value:
    #        return True
    #    else:
    #        return False

    def use_suply(self):
        #uses the suply of the unit, reducing it by the amount of suply consumption.
        if self.suply >= self.suply_consumption:
            self.suply = self.suply - self.suply_consumption
            print(f"Unit {self.id} used supply: {self.suply_consumption}, Remaining Supply: {self.suply}")
        else:
            self.suply = 0
            print(f"Unit {self.id} used supply: {self.suply_consumption}, Remaining Supply: {self.suply}")

    def has_logistics_capacity(self):
        #returns true if the unit has logistics capacity, false otherwise.
        if self.transport_V > 0 or self.transport_H > 0:
            return True
        else:
            return False

    def set_unit_leader(self, leader_id):
        #sets the leader of the unit, which will be used for combat purposes.
        self.leader_id = leader_id
        print(f"Unit {self.id} leader set to: {leader_id}")

    def create_suply_subordinate_unit(self, subunit_id):
        #creates a subordinate unit for the unit, which will be used for logistics purposes.
        self.subordinate_units_ids.append(subunit_id)
        
        print(f"Unit {self.id} created subordinate unit: {subunit_id}")

    def load_suply(self, amount):
        #loads suply into the unit, up to the logistics capacity.( should not do more then capacity never)
        if self.suply + amount <= self.logistics_value:
            self.suply += amount
            print(f"Unit {self.id} loaded supply: {amount}, Total Supply: {self.suply}")
        else:
            self.suply = self.logistics_value
            print(f"Unit {self.id} loaded supply: {amount}, Total Supply: {self.suply} (max capacity reached)")

    def last_moviment_suply_estimate(self):
        #this is mostly for the logistic units so they have enough suply to go back where they came from if needed( disreguard if it is not a logi unit)
        if self.type == 4:  # Assuming type 4 is logistics
            self.suply_math = self.logistics_value + self.suply_consumption - self.suply 

    def unload_suply(self, amount):
        #unloads suply from the unit, down to 0.
        if self.suply_math < self.suply-amount:
            self.suply -= amount
            print(f"Unit {self.id} unloaded supply: {amount}, Remaining Supply: {self.suply}")
            return amount
        else:
            new_amount = self.suply - self.suply_math
            self.suply = self.suply_math
            return new_amount
        
class MergedUnit:
    
    def __init__(self,id):
        self.id = id
        self.units = []

    def add_unit(self, unit):
        self.units.append(unit)
    
    def detatch_unit(self, unit_id):
        self.units = [unit for unit in self.units if unit.id != unit_id]


class NavyUnits:
    def __init__(self, id, class_name, ShipName, nation, location, homedock, crew, guns, speed, suply, status, systemsHealth, HullHealth,HaulCapacity,):
        self.id = id
        self.unitClass = class_name
        self.ShipName = ShipName
        self.nation = nation
        self.location = location
        self.homedock = homedock
        self.crew = crew
        self.guns = guns
        self.speed = speed
        self.suply = suply
        self.status = status
        self.systemsHealth = systemsHealth
        self.HullHealth = HullHealth
        self.HaulCapacity = HaulCapacity
        self.EngineHealth = 100
        self.fireValue = 0
        self.onShipyard = False
        self.docked = True
        self.counter = 0
    
    
class trainUnits:

    def __init__(self, id, health, speed, lvl, location, nation, status=0, loaded_units=None):
        self.id = id
        self.health = health
        self.speed = speed
        self.lvl = lvl
        self.fuel = 100 #not implemented yet
        self.suplyCapacity = 4000 #not implemented yet (lvl)
        self.ammoCapacity = 4000 #not implemented yet (lvl)
        self.troopsCapacity = 700 #not implemented yet (lvl)

        self.suply = 0
        self.ammo = 0
        self.troops = 0

        self.location = location
        self.nation = nation
        self.status = status # 0 for idle, 1 for moving, 2 for stopped, 3 for loading_cargo, 4 for unloading_cargo, 5 maintenance, 6 damaged, 7 disabled 8 loading/unloading troops
        self.loaded_units = [str(unit_id) for unit_id in (loaded_units or [])]
        self.route = []
        self.next_step_time = 0
        
        self.counter = 0

    def update_status(self, new_status):
        """
        Update the train's status. note that if the train is moving, damaged or disabled it will not change   
        
        Args:
            new_status: New status code to set for the train
        """
        #this might be checked on the simulation loop, but for now it will be checked here.? afraid it might cause problems. 
        if self.status not in [1, 6, 7]:  # 1: moving, 6: damaged, 7: disabled
            self.status = new_status
    
    def loading_suply(self,suply_amount):
        #this will be implemented later, for now it will just set the status to loading. 
        if self.suply >= self.suplyCapacity:
            self.status = 0
        if self.status == 3:
            self.suply += suply_amount


    def unloading_suply(self,suply_amount):
        #this will be implemented later, for now it will just set the status to unloading. 
        if self.status == 4:
            self.suply -= suply_amount
        if self.suply == 0:
            self.status = 0 #idle

    def train_usage(self):
        
        self.health -= 1
    
    def move(self, new_location):
        #this will be implemented later, for now it will just set the status to moving. 
        if self.status == 1:
            self.location = new_location
            self.train_usage()
    
    def repair(self):
        #this will be implemented later, for now it will just set the status to maintenance. 
        if self.status == 5:
            if self.counter > 5:
                self.health += 10
                if self.health > 100:
                    self.health = 100
                    self.status = 0
                self.counter = 0
            self.counter += 1

    def get_status(self):
        #returns the status of the train as a string. 
        if self.status == 0:
            return "Idle"
        elif self.status == 1:
            return "Moving"
        elif self.status == 2:
            return "Stopped"
        elif self.status == 3:
            return "Loading"
        elif self.status == 4:
            return "Unloading"
        elif self.status == 5:
            return "Maintenance"
        elif self.status == 6:
            return "Damaged"
        elif self.status == 7:
            return "Disabled"
        elif self.status == 8:
            return "Loading/Unloading Troops"
        else:
            return "Unknown Status"
        
    def return_possible_status(self):

        if self.status == 0:
            return [3,4,5,8]
        if self.status == 1:
            return [2,5]
        if self.status == 2:
            return [1,5]
        if self.status == 3:
            return [1,5,4]
        if self.status == 4:
            return [1,5,3]
        if self.status == 5:
            return [0,1,3,4,8]
    
    def get_location(self):
        #returns the location of the train as a province ID. 
        return self.location
    
    def get_supply_capacity(self):
        #returns the supply capacity of the train. 
        return self.suplyCapacity
    
    def get_ammo_capacity(self):
        #returns the ammo capacity of the train. 
        return self.ammoCapacity
    
    def get_troops_capacity(self):
        #returns the troops capacity of the train. 
        return self.troopsCapacity
    

class UnitGroup:
    """Represents a group/army of units that can be managed together."""
    
    def __init__(self, group_id, nation):
        """
        Initialize a UnitGroup.
        
        Args:
            group_id: Unique identifier for the unit group
            nation: Nation code the group belongs to
        """
        self.id = group_id
        self.nation = nation
        self.units = {}  # Dictionary of Unit objects by unit_id
    
    def add_unit(self, unit):
        """
        Add a unit to this group.
        
        Args:
            unit: Unit object to add
        """
        self.units[unit.id] = unit
    
    def remove_unit(self, unit_id):
        """
        Remove a unit from this group by its ID.
        
        Args:
            unit_id: ID of the unit to remove
        """
        if unit_id in self.units:
            del self.units[unit_id]
    
    def get_unit(self, unit_id):
        """
        Get a specific unit from this group.
        
        Args:
            unit_id: ID of the unit to retrieve
            
        Returns:
            Unit object or None if not found
        """
        return self.units.get(unit_id)
    
    def get_all_units(self):
        """
        Get all units in this group.
        
        Returns:
            List of Unit objects
        """
        return list(self.units.values())


def _extract_unit_id_number(unit_id, prefix="unit"):
    """Return the trailing numeric part of a unit id, or None if it cannot be parsed."""
    text = str(unit_id).strip()
    if not text:
        return None

    if text.startswith(prefix):
        suffix = text[len(prefix):]
        if suffix.isdigit():
            return int(suffix)

    digits = "".join(ch for ch in text if ch.isdigit())
    if digits:
        return int(digits)

    return None


def get_next_unit_id(armies, prefix="unit"):
    """Generate the next available unit id by scanning all existing armies."""
    highest_number = 0

    for army in armies.values():
        unit_map = getattr(army, "units", {})
        for unit_id in unit_map.keys():
            unit_number = _extract_unit_id_number(unit_id, prefix=prefix)
            if unit_number is not None and unit_number > highest_number:
                highest_number = unit_number

    return f"{prefix}{highest_number + 1}"


def create_unit(
    armies,
    *,
    name,
    nation,
    location,
    home,
    army,
    soldiers,
    type_of_unit,
    leader_id,
    reserve,
    logistics,
    suply,
    status=1,
    unit_id=None,
):
    """Create a unit, assign a unique id, and store it in the target army."""
    if unit_id is None:
        unit_id = get_next_unit_id(armies)

    unit = Unit(
        unit_id=unit_id,
        name=name,
        nation=nation,
        location=location,
        home=home,
        army=army,
        soldiers=soldiers,
        type_of_unit=type_of_unit,
        leader_id=leader_id,
        reserve=reserve,
        logistics=logistics,
        suply=suply,
        status=status,
    )

    if army not in armies:
        armies[army] = UnitGroup(army, nation)

    armies[army].add_unit(unit)
    return unit


def create_logistics_unit(
    armies,
    *,
    nation,
    location,
    home,
    army,
    name="Logistics Unit",
    soldiers=0,
    leader_id=0,
    reserve=0,
    logistics=10,
    suply=0,
    status=1,
    unit_id=None,
):
    """Create a logistics-focused unit using the normal unit storage flow."""
    return create_unit(
        armies,
        name=name,
        nation=nation,
        location=location,
        home=home,
        army=army,
        soldiers=soldiers,
        type_of_unit=4,
        leader_id=leader_id,
        reserve=reserve,
        logistics=logistics,
        suply=suply,
        status=status,
        unit_id=unit_id,
    )

def load_starting_units():
    """
    Load starting units from starting_units.json and organize them into armies (UnitGroup).
    
    Returns:
        dict: Dictionary of UnitGroup objects organized by army ID, where:
              - Key: army ID (numeric)
              - Value: UnitGroup object containing all units in that army
    """
    # Get the path to starting_units.json relative to this file
    current_dir = Path(__file__).parent.parent
    units_file = current_dir / "QgizFiles" / "starting_units.json"
    
    with open(units_file, 'r') as f:
        data = json.load(f)
    
    # Create a dictionary to organize units by army
    armies = {}
    
    for unit_id, unit_data in data.get("starting_units", {}).items():
        # Create Unit object
        unit = Unit(
            unit_id=unit_id,
            name=unit_data['name'],
            nation=unit_data['nation'],
            location=unit_data['location'],  # Province ID
            home=unit_data['home'],
            army=unit_data['army'],
            soldiers=unit_data['soldiers'],
            type_of_unit=unit_data['type'],
            leader_id=unit_data['leader_id'],
            reserve=unit_data['reserve'],
            logistics=unit_data['logistics'],
            suply=unit_data['suply'],
            status=unit_data.get('status', 1)
        )
        
        # Get or create the army (UnitGroup)
        army_id = unit_data['army']
        if army_id not in armies:
            armies[army_id] = UnitGroup(army_id, unit_data['nation'])
        
        # Add unit to its army
        armies[army_id].add_unit(unit)
    
    return armies

def load_starting_trains():
    """
    Load starting trains from starting_trains.json and organize them into train groups.
    
    Returns:
        dict: Dictionary of train units organized by train ID, where:
              - Key: train ID (numeric)
              - Value: trainUnits object containing all attributes of the train
    """
    # Get the path to starting_trains.json relative to this file
    current_dir = Path(__file__).parent.parent
    trains_file = current_dir / "QgizFiles" / "starting_trains.json"
    
    with open(trains_file, 'r') as f:
        data = json.load(f)
    
    # Create a dictionary to organize trains by their ID
    trains = {}
    
    for train_id, train_data in data.get("starting_trains", {}).items():
        # Create trainUnits object
        train = trainUnits(
            id=train_id,
            health=train_data['health'],
            speed=train_data['speed'],
            lvl=train_data['lvl'],
            location=train_data['location'],  # Province ID
            nation=train_data['nation'],
            status=train_data.get('status', 0),
            loaded_units=train_data.get('loaded_units', []),
        )
        
        # Add train to the dictionary
        trains[train_id] = train
    
    return trains