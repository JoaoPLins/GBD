import random

class PeopleManager:
    def __init__(self):
        #self.people = {} # dictionary to store people objects with their id think it might be useful? not sure yet. crossed out cuz it might just be a waste of space.
        self.people_list = [0] # list to store people objects for easy access and iteration
        self.counter = 1
        
        self.Active_rolling = 1

        self.people_alive = 0
        self.important_people = [] # list with important ppl ID's 
        self.people_1 = []
        self.people_2 = []
        self.people_3 = []
        self.people_4 = []
        self.people_5 = []
        self.people_6 = []
        self.people_7 = []
        self.people_8 = []
        self.people_9 = []
        self.people_10 = []
        self.people_11 = []
        self.people_12 = []
        #might need to add a insert in this part sadly... 
        self.current_year = 1904
        self.current_month = 1

    def generate_people(self, location, ammount, nation=None):
        for i in range(ammount):
            person_id = self.counter
            name = person_id # for now just use the id as the name, will take a random name from a list later
            familyName = person_id # for now just use the id as the family name, will take a random name from a list later
            birthday = random.randint(1860, 1903)
            month = random.randint(1, 12) # for now just use a random month, it will depend on the starting date
            alive = True
            person_nation = nation if nation is not None else location
            home = location
            party = random.randint(1, 3) # 1 for party 1, 2 for party 2, etc.
            type = random.randint(0, 5) # 0 spy | 1 Army | 2 Engineer | 3 Politician | 4 Revo | 5 NEPO 
            if type == 0: # spy
                loyalty = random.randint(0, 50) # spies are less loyal on average
                influence = random.randint(0, 10) # spies have less influence on average
            elif type == 1: # army
                loyalty = random.randint(50, 100) # army are more loyal on average
                influence = random.randint(10, 70) # army have more influence on average
            elif type == 2: # engineer
                loyalty = random.randint(30, 80) # engineers have a wide range of loyalty
                influence = random.randint(20, 60) # engineers have a moderate influence on average
            elif type == 3: # politician
                loyalty = random.randint(20, 80) # politicians have a wide range of loyalty
                influence = random.randint(30, 100) # politicians have a high influence on average
            elif type == 4: # revolutionary
                loyalty = random.randint(0, 20) # revolutionaries can be very loyal or not at all
                influence = random.randint(0, 10) # revolutionaries can have a wide range of influence
            else: # NEPO
                loyalty = random.randint(40, 90) # NEPO can be quite loyal but also have a wide range,
                influence = random.randint(20, 80) # NEPO can have a wide range of influence
            
            Personality = random.randint(1, 4) # 1 for aggressive, 2 for defensive, 3 for balanced, 4 for opportunistic 
            
            person = People(person_id,name,familyName,birthday,month,alive,person_nation,home,party,loyalty,influence,type,Personality)
            self.people_list.append(person)
            
            
            getattr(self, f"people_{month}").append(person)
            self.counter += 1
            self.people_alive += 1
            person.calculate_age_start(self.current_year)       

    def load_important_people(self, important_people_file):
        # this will load important people from a file, for now it's just a placeholder, but we can add more complex logic later.
        pass
    
    def create_player(self, name, familyName, birthday, month, nation, home, party, loyalty, influence, type, Personality):
        person_id = self.counter
        alive = True
        person_nation = nation
        person = People(person_id,name,familyName,birthday,month,alive,person_nation,home,party,loyalty,influence,type,Personality)
        self.people_list.append(person)
        getattr(self, f"people_{month}").append(person)
        self.counter += 1
        self.people_alive += 1
        person.calculate_age_start(self.current_year) 
        person.give_job(1) #for now this is the only option 

    def give_player_job(self,unit_id,job):
        
        #this will give the player the job.
        person = self.get_person(1) # player is always person 1
        if person is not None:
            person.give_job(job)
            person.Unit = unit_id    

    def starter_jobs (self):

        pass

    def update_month(self):
        gettingOlder=getattr(self, f"people_{self.current_month}")
        for person in gettingOlder:
            person.age += 1



        self.current_month += 1
        if self.current_month > 12:
            self.current_month = 1
            self.current_year += 1    
    
    def simulate_people(self):
        Rolling=getattr(self, f"people_{self.Active_rolling}")
        peoplesimulated = 0
        #important people roll every month. and if they have a active roll they do it twice. 
        if self.Active_rolling < 13:
            
            self.Active_rolling += 1
            for person in Rolling:
                #simulate the person here, they will do actions based on their type, personality, loyalty, influence, and other factors. for now just print their name and age
                if person.age <12:
                    continue # skip simulating children for now, they will just age up and maybe do some actions when they are older, but for now they will just be there and age up.   
                else:
                    peoplesimulated += 1
                    if person.age <18:
                        roll = self.roll() # for teenagers we will just do a simple roll to determine if they do something or not, and what they do, for now it's just a placeholder, but we can add more complex logic later.
                        if person.type == 1: # army
                            if roll > 50 and person.get_job_label() == "None": # if the roll is less than 50 and the person doesn't have a job, they will join the army, for now it's just a placeholder, but we can add more complex logic later.
                                person.skill_army += 1
                            
                        elif person.type == 2: 
                            if roll > 50 and person.get_job_label() == "None": # if the roll is less than 50 and the person doesn't have a job, they will join the army, for now it's just a placeholder, but we can add more complex logic later.
                                person.skill_engineer += 1# engineer
                            # engineers will do some actions based on their loyalty and influence, for now just print their name and age
                        elif person.type == 3: 
                            if roll > 50 and person.get_job_label() == "None": # if the roll is less than 50 and the person doesn't have a job, they will join the army, for now it's just a placeholder, but we can add more complex logic later.
                                person.skill_politician += 1# politician
                                if roll > 90:
                                    person.skill_admin += 1
                                    person.skill_politics += 1
                            # politicians will do some actions based on their loyalty and influence, for now just print their name and age
                        elif person.type == 4:
                            if roll > 50 and person.get_job_label() == "None": # if the roll is less than 50 and the person doesn't have a job, they will join the army, for now it's just a placeholder, but we can add more complex logic later.
                                person.skill_politician += 1# politician
                                if roll > 90:
                                    person.skill_army += 1
                                    person.skill_politics += 1# revolutionary
                            # revolutionaries will do some actions based on their loyalty and influence, for now just print their name and age
                        elif person.type == 5:
                            if roll > 50 and person.get_job_label() == "None": # if the roll is less than 50 and the person doesn't have a job, they will join the army, for now it's just a placeholder, but we can add more complex logic later.
                                person.skill_politician += 1# politician
                                if roll > 95:
                                    person.skill_admin += 1
                                    person.skill_politics += 1
                                    person.influence += 1 # NEPO
                            # NEPO will do some actions based on their loyalty and influence, for now just print their name and age
                        else:
                             if roll > 50 and person.get_job_label() == "None": # if the roll is less than 50 and the person doesn't have a job, they will join the army, for now it's just a placeholder, but we can add more complex logic later.
                                person.skill_politician += 1# politician
                                if roll > 90:
                                    person.skill_engineer += 1
                                    person.skill_politics += 1 # type 0, spy
                            # spies will do some actions based on their loyalty and influence, for now just print their name and age
                    elif person.age < 60:
                        
                        # for adults we will do a more complex simulation based on their type, personality, loyalty, influence, and other factors, for now it's just a placeholder, but we can add more complex logic later.
                        pass
                        
                
                
            print(f"Simulated {peoplesimulated} people in list {self.Active_rolling}.")
           
        else:
            self.Active_rolling = 1

        
    def born_new_person_(self, location):
        self.people_list.append(person)
        self.people_alive += 1
        self.counter = max(self.counter, person.id + 1)

    def get_person(self, id):
        if id <= 0 or id >= len(self.people_list):
            return None
        return self.people_list[id]

    def get_people_in_province(self, province_id):
        return [
            person
            for person in self.people_list[1:]
            if person is not None and getattr(person, "home", None) == province_id and getattr(person, "alive", False)
        ]
    
    def roll(self):
        # this will be called every month to simulate the people, for now it just calls the simulate_people method, but we can add more logic here later if needed.
        return random.randint(1, 100) # for now just return a random number, this will be used to determine the outcome of certain actions and events in the game, based on the person's skills, loyalty, influence, and other factors.

class People:
    def __init__(self, id,name,familyName,birthday,month,alive,nation,home,party,loyalty,influence,type,Personality):
        '''
        Args
        id: unique identifier for the person
        name: first name of the person
        familyName: last name of the person
        birthday: birth year of the person
        month: birth month of the person
        alive: boolean indicating if the person is alive
        nation: the nation the person belongs to
        home: the province the person is from
        party: the political party the person belongs to
        loyalty: the loyalty of the person to their nation (0-100)
        influence: the influence of the person in their nation (0-100)
        type: the type of person (0 spy | 1 Army | 2 Engineer | 3 Politician | 4 Revo | 5 NEPO)
        Personality: the personality of the person (1 for aggressive, 2 for defensive, 3 for balanced, 4 for opportunistic)
        
        Other atributes:
        age: calculates base on the current year and birthday
        skill_army: calculates base on the type of class.
        skill_engineer: calculates base on the type of class.
        skill_politics: calculates base on the type of class.
        skill_admin: calculates base on the type of class.
        playerInfo: starts at 0 goes up to 100
        AIinfo: starts at 0 goes up to 100(TBI)
        location: current location of the person, starts at home province

        '''
        self.id = id
        self.name = name
        self.familyName = familyName
        self.birthdayyear = birthday
        self.birthdayMonth = month
        self.alive = alive
        self.age = 0 #calculates base on the current year and birthday
        self.nation = nation
        self.home = home
        self.party = party
        self.loyalty = loyalty
        self.influence = influence
        self.type = type # 0 spy | 1 Army | 2 Engineer | 3 Politician | 4 Revo | 5 NEPO 
        self.skill_army = 0 # calculates base on the type of class. 
        self.skill_engineer = 0 # calculates base on the type of class.
        self.skill_politics = 0 # calculates base on the type of class.
        self.skill_admin = 0 # calculates base on the type of class.
        self.Personality = Personality # 1 for aggressive, 2 for defensive, 3 for balanced, 4 for opportunistic 0 for player
        self.playerInfo = 0 #starts at 0 goes up to 100
        self.AIinfo = 0 #starts at 0 goes up to 100(TBI)
        self.location = home # current location of the person, starts at home province
        self.job = 0 # 0 for none,
        self.Unit = 0 #unit_id 
        self.friends = []

        self.calculate_skills()
    
    def calculate_age_start(self, current_year):
        self.age = current_year - self.birthdayyear

    def calculate_skills(self):
        # for now just assign random skills based on the type, will add more complex logic later
        if self.type == 0: # spy
            self.skill_army = random.randint(0, 30)
            self.skill_engineer = random.randint(0, 50)
            self.skill_politics = random.randint(0, 80)
            self.skill_admin = random.randint(0, 50)
        elif self.type == 1: # army
            self.skill_army = random.randint(50, 100)
            self.skill_engineer = random.randint(0, 50)
            self.skill_politics = random.randint(0, 50)
            self.skill_admin = random.randint(0, 50)
        elif self.type == 2: # engineer
            self.skill_army = random.randint(0, 50)
            self.skill_engineer = random.randint(50, 100)
            self.skill_politics = random.randint(0, 50)
            self.skill_admin = random.randint(0, 50)
        elif self.type == 3: # politician
            self.skill_army = random.randint(0, 50)
            self.skill_engineer = random.randint(0, 50)
            self.skill_politics = random.randint(50, 100)
            self.skill_admin = random.randint(0, 50)
        elif self.type == 4: # revolutionary
            self.skill_army = random.randint(20, 100)
            self.skill_engineer = random.randint(20, 100)
            self.skill_politics = random.randint(20, 100)
            self.skill_admin = random.randint(20, 100)
        else: # NEPO
            self.skill_army = random.randint(0, 80)
            self.skill_engineer = random.randint(0, 80)
            self.skill_politics = random.randint(0, 80)
            self.skill_admin = random.randint(0, 80)

    def give_job(self, job):

        self.job = job

    def get_job_label(self):
        labels = {
            0: "None",
            1: "Army",
            2: "Engineer",
            3: "Politician",
            4: "Revolutionary",
            5: "Nepo",
        }
        return labels.get(self.job, str(self.job))

    def get_age(self):
        return max(0, int(getattr(self, "age", 0)))
    
