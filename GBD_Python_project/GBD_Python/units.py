from ast import Pass
import json
from pathlib import Path

#totalUnits = 0

class Unit:
    """Represents a single military unit."""
    
    def __init__(self, unit_id, name, nation, location, home, army, soldiers, attack, defense, speed, logistics, suply, status):
        """
        Initialize a Unit.
        
        Args:
            unit_id: Unique identifier for the unit
            name: Name of the unit
            nation: Nation code the unit belongs to
            location: Province ID where the unit is located
            home: Home province ID
            army: Army/Unit group ID the unit belongs to
            soldiers: Number of soldiers in the unit
            attack: Attack stat
            defense: Defense stat
            speed: Movement speed stat
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
        self.attack = attack
        self.defense = defense
        self.speed = speed
        self.logistics = logistics
        self.suply = suply
        self.status = status
        self.unit_spotting = [0,0]
        self.unit_dectectability = 0
        self.counter = 0
        self.fatigue = 0
        self.morale = 100
        self.experience = 0
        self.units_spoted = []
        self.visibility = 0
        self.unitCurrentSpoting = 0
        #totalUnits += 1

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
        else:
            return "Unknown Status"
        
    def update_status(self, new_status):
        """
        Update the unit's status.
        
        Args:
            new_status: New status code to set for the unit
        """
        self.status = new_status
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
            self.unit_spotting = [10,50]
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

    def update_dectectability(self):
        #refractor this in the future. maybe using @proprety for it and dictionaries. to study
        if self.status == 0:
            self.unit_dectectability = 0
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

    def calculate_visibility(self):
        #calculates the visibility on the unit instead of doing everytime in the simulation. future update will add this value with other simulated situations like terrain weather.
        self.visibility = self.unit_dectectability + (self.soldiers // 100)
    
    def return_spotting(self, where):
        #calculates the spotting hability of a unit on other units
        self.unitCurrentSpoting = self.unit_spotting[where] + (self.soldiers // 100)
        
        
        
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
            attack=unit_data['attack'],
            defense=unit_data['defense'],
            speed=unit_data['speed'],
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
