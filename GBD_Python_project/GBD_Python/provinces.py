import random



class building:
    def __init__(self,building_id,building_type,province_id):
        self.building_id = building_id
        self.building_type = building_type
        self.province_id = province_id
        self.health = 100
        self.production = random.randint(50,100) #this is the production effitiency of the building, it will be used to calculate productionlevel of the buidling will depend on the charcter but for now it is not implemented.
        self.charcter_id = 0 #this will be the id of the one managing this building, they will influence the production of the building and the province,and the loyalty as well. but for now it is not implemented.
        self.building_level = 1 #this is the level of the building, it will influence the production of the building and the province, but for now it is not implemented.
        
        self.soldier_capacity = 0
        self.storage_capacity = 0

        self.soldiers = 0 #this is the ammount of soldiers in the building, it will be used to calculate the recruitment and the defence of the province, but for now it is not implemented.
        self.ammo_storage = 0
        self.suply_storage = 0

        if self.building_type == 5 : 
            self.soldier_capacity= 1000 * self.building_level
            self.storage_capacity = 1000 * self.building_level

        elif self.building_type == 9:
            self.soldier_capacity = 500 * self.building_level
            self.storage_capacity = 1000 * self.building_level

        if self.building_type == 10:
            self.storage_capacity = 1000 * self.building_level
        
    def production_update(self):
        # Keep production as a multiplier in [0.5, 1.0] with current random setup.
        production_factor = self.building_level * (self.production / 100)

        produced_food = 0
        produced_fuel = 0
        produced_suply = 0
        

        if self.building_type == 3:
            # civil industry produces province supply that is stored in this building
            produced_suply = int(8000 * production_factor)
        elif self.building_type == 4:
            # farm produces food directly
            produced_food = int(50 * production_factor)
        elif self.building_type == 7:
            # military industry produces ammo that is stored in this building
            self.ammo_storage += int(15000 * production_factor)
        elif self.building_type == 8:
            # fuel industry produces fuel directly
            produced_fuel = int(500 * production_factor)


        return produced_food, produced_fuel, produced_suply

    def recruitment(self):
        #this might change. 
        production_factor = self.building_level * (self.production / 100)
        if self.building_type == 5:
            # army base provides daily recruit capacity
            produced_recruits = int(100 * production_factor)
            return produced_recruits
        return 0
    
    def return_building_type(self):
        '''
        this is where we calculate the effects of the building on the province.
        it will be expanded after the first alpha but currently it is this: 
        0  → NONE (this place is empty.)
        1  → PORT (size of ships/ammount of ships that you have)
        2  → SHIPYARD (to be implemented later)
        3  → INDUSTRY
        4  → FARM
        5  → ARMYBASE (size of possible units in this place + allow creation of units. does not take in consideration reserve units, although units with no quarters will suffer penalties to ORG.)
        6  → AIRBASE (will be there but not yet implemented)
        7  → M.INDUSTRY
        8  → F.INDUSTRY
        9  → Fort (costs money but gives defences and quarter space.)
        10 → warehouse (stores stuff)
        11 → city center
        12 → mine (gives fuel)
        '''
        if self.building_type == 1:
            #port
            pass
        elif self.building_type == 2:
            #shipyard
            pass
        elif self.building_type == 3:
            #civil industry
            pass
        elif self.building_type == 4:
            #farm
            pass
        elif self.building_type == 5:
            #armybase
            pass
        elif self.building_type == 6:
            #airbase
            pass
        elif self.building_type == 7:
            #military industry
            pass
        elif self.building_type == 8:
            #fuel industry
            pass
        elif self.building_type == 9:
            #fort
            pass
        elif self.building_type == 10:
            #warehouse 
            pass
        elif self.building_type == 11:
            #city center 
            pass
        elif self.building_type == 12:
            #mine 
            pass

class Province:
    def __init__(self,province_id,name,owner,controller,iswater,iscoastal,terrain):
        
        #comes from mapdata 
        self.province_id = province_id
        self.name = name
        self.owner = owner
        self.controller = controller
        self.iswater = iswater
        self.iscoastal = iscoastal
        self.terrain = terrain
        #-------------------------------#

        #comes from population.csv
        self.population = 0
        
        #comes from nations.py
        self.iscapital = 0

        #means the ammount of buildings it fits, currently it takes a set value from the terrain type, with the exception that capitals that are 6. 0->0 1 -> 4 2 -> 3  3 -> 2 4 -> 1 
        self.size = 0
        #stores the buildings in this, and uses to run operations on them. 
        self.buildings = []

        #THIS WILL BE DONE LATER 
        self.hasRailroad = False

        #currently if it is a costal one it is considered to have a port. will work on it later.
        self.hasPort = False

        #store the future id of the railroad that goes through this province, if it has one.
        self.railid = []

        #thie first time this value is calculated its after the province adds buildings... then it will be set to the ammount of buildings. after that the player will be able to improve this and then be able to improve buildings( also this value is taken to calculate the desirable population and give a future bonus for the speed)
        self.infrastructure = 0

        #this value is calculated by the level the buildings (warehouse + Mindustry + port + armybase + fort )
        self.maxsuply = 0
        self.suply = 0
        self.target_suply = 0

        #self explanatory; 
        self.fuel = 0
        self.food = 0
        self.ammo = 0

        #here its just for calculating the recruitment ammount; this is broken, gonna implement differently. 
        self.units_in_here = []
        self.units_from_here = []
        self.units_recrinting_here = []

        #ammount of possible recuits 
        self.province_recrutable = 0
        self.province_recruits = 100
        
        #number of soldiers in the province( active and reserve)
        self.province_soldiers = 0
        
        #number of deaths by war. this will be used to calculate the population loyalty. and statistics.
        self.province_deaths = []

        self.logistic_hub = False

    def sim_update(self):
        #this is where we will update the province day tick, it will calculate the the new suply, the new fuel and food, and so on. 
        #first check the production of the buildings.
        produced_food = 0
        produced_fuel = 0
        produced_suply = 0
        recruits = 0

        for building in self.buildings:
            food_gain, fuel_gain, suply_gain  = building.production_update()
            produced_food += food_gain
            produced_fuel += fuel_gain
            produced_suply += suply_gain

            recruits += building.recruitment()

            #this didn't work. 
            #for unit in self.units_recrinting_here:
            #    if unit.return_soldiers_target_delta() > 0:
            #        # If the unit still needs soldiers, try to recruit.
            #        building_recruits = building.recruitment()
            #        #this is not working but uh maybe I gonna end up with that twice?
            #        unit.add_soldiers(building_recruits)
            #        self.province_soldiers += building_recruits
            #        self.province_recrutable -= building_recruits
            
        
            

        self.food += produced_food
        self.fuel += produced_fuel
        if self.province_recrutable >= self.province_recruits + recruits:
            self.province_recruits += recruits
        

        # Province totals are derived from building storage.
        self.ammo = sum(b.ammo_storage for b in self.buildings)
        self.suply += produced_suply
            

    def define_population(self,population):
        self.population = population    

    def load_extra_data(self):
        #this is where the we get the extra data from the province and calculate the new values. for loading a new map
        self.calculate_size()
        self.Generate_starting_buildings()
        self.infrastructure = self.size
        self.calculate_max_suply()
        self.set_starting_recruitable()

    def set_starting_recruitable(self):
        self.province_recrutable = self.population // 100

    def add_soldiers(self, soldiers):
        self.province_soldiers += soldiers
        self.province_recruits -= soldiers

    def kill_soldiers(self, soldiers):
        self.province_soldiers -= soldiers
    
    def transfer_suply(self, suply):
        self.suply -= suply        

    def calculate_max_suply(self):
        #this is where we calculate the max suply of the province based on the buildings it has. (lvls will mutiply the value by the level)
        self.maxsuply = 0
        for building in self.buildings:
            if building.building_type == 1:
                #port
                self.maxsuply += 1000
            elif building.building_type == 2:
                #shipyard
                self.maxsuply += 500
            elif building.building_type == 3:
                #civil industry
                self.maxsuply += 300
            elif building.building_type == 4:
                #farm
                self.maxsuply += 200
            elif building.building_type == 5:
                #armybase
                self.maxsuply += 400
            elif building.building_type == 6:
                #airbase
                self.maxsuply += 300
            elif building.building_type == 7:
                #military industry
                self.maxsuply += 500
            elif building.building_type == 8:
                #fuel industry
                self.maxsuply += 400
            elif building.building_type == 9:
                #fort
                self.maxsuply += 200
            elif building.building_type == 10:
                #warehouse 
                self.maxsuply += 3000
            elif building.building_type == 11:
                #city center 
                self.maxsuply += 1000
            elif building.building_type == 12:
                #mine 
                self.maxsuply += 500

    def Generate_starting_buildings(self):
        
        if self.iscapital == 1:
            self.add_building(0,11)
            self.add_building(1,5)
            self.add_building(2,3)
            self.add_building(3,7)
            #lmao this is wrong
            if self.iscoastal == 1:
                self.add_building(4,1)
                #self.add_building(5,2) # this is the shipyard, but it is not implemented yet.
        else:
            # Generate random buildings for non-capital provinces based on population
            if self.population > 35000:
                self.add_building(0,11)  # City Center
                self.add_building(1,3)  # Civil Industry
                if self.iscoastal == 1:
                    self.add_building(2,1)  # Port
                if self.size > 3:
                    for size in range(self.size -3 ):
                        self.add_building(2 + size, random.choice([3, 4, 5, 7, 8, 10]))
            else:
                for size in range(self.size):
                    self.add_building(size, random.choice([ 4, 5, 9, 10]))  # Random building

    def add_building(self,building_slot,building_type):
        #add the new building to the province.
        self.buildings.append(building(building_slot,building_type,self.province_id))
    

    def set_capital(self):
        self.iscapital = 1
    
    def calculate_size(self):
        #I remember thisnow but I'm not sure yet what this was for max building slots 
        #capital has the max
        if self.iscapital == 1:
            self.size = 6
        #nothing on water    
        elif self.iswater == 1:
            self.size = 0
        #plains is 5
        elif self.terrain == 1:
            self.size = 5
        #hills is 4
        elif self.terrain == 2:
            self.size = 4
        #mountains is 3
        elif self.terrain == 3:
            self.size = 3
        else:
            self.size = 3

    def return_target_suply(self):
        return self.target_suply
    
    def set_target_suply(self, target_suply):
        self.target_suply = target_suply

    def return_buildings(self):
        return self.buildings
    
    def return_suply(self):
        return self.suply
    
    def add_suply(self,suply_amount):
        
        self.suply += suply_amount

    def set_logistic_hub(self, enabled=True):
        self.logistic_hub = bool(enabled)

    def clear_logistic_hub(self):
        self.logistic_hub = False

    def is_logistic_hub(self):
        return self.logistic_hub

    