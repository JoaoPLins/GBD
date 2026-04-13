import json
from pathlib import Path
from typing import List, Dict, Optional, Any


class Nation:
    """Represents a nation or state in the game."""
    
    def __init__(
        self,
        tag: str,
        name: str,
        nation_type: str,
        capital: Optional[str] = None,
        capital_id: Optional[str] = None,
        government: Optional[str] = None,
        parties: Optional[List[str]] = None,
        substates: Optional[List[str]] = None,
        parent: Optional[str] = None,
        flag: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize a Nation object.
        
        Args:
            tag: Short tag/code identifier (e.g., 'BRA', 'ARG')
            name: Full name of the nation
            nation_type: Type of entity ('nation', 'province', 'state', etc.)
            capital: Capital city name
            government: Government type
            parties: List of political parties
            substates: List of substates/provinces under this nation
            parent: Parent nation tag if this is a substate
            flag: Path to flag image
            **kwargs: Additional properties
        """
        self.tag = tag
        self.name = name
        self.type = nation_type
        self.capital = capital
        self.capital_id = capital_id# Optional field for capital city ID
        self.government = government
        self.parties = parties or []
        self.substates = substates or []
        self.parent = parent
        self.flag = flag
        self.extra = kwargs
    
    def __repr__(self) -> str:
        return f"Nation(tag='{self.tag}', name='{self.name}', type='{self.type}')"
    
    def __str__(self) -> str:
        return f"{self.name} ({self.tag})"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert nation to dictionary."""
        data = {
            "tag": self.tag,
            "name": self.name,
            "type": self.type,
        }
        if self.capital:
            data["capital"] = self.capital
        if self.government:
            data["government"] = self.government
        if self.parties:
            data["parties"] = self.parties
        if self.substates:
            data["substates"] = self.substates
        if self.parent:
            data["parent"] = self.parent
        if self.flag:
            data["flag"] = self.flag
        data.update(self.extra)
        return data

    def return_capital_id_int(self):
        """Return the capital_id as an integer, or None if not set."""
        if self.capital_id is not None:
            try:
                return int(self.capital_id)
            except ValueError:
                print(f"Warning: capital_id '{self.capital_id}' for nation '{self.tag}' is not a valid integer.")
                return None
        return None

class NationManager:
    """Manages loading and accessing nations from JSON data."""
    
    def __init__(self):
        """Initialize the nation manager."""
        self.nations: Dict[str, Nation] = {}
    
    def load_from_json(self, filepath: str) -> None:
        """
        Load nations from a JSON file.
        
        Args:
            filepath: Path to the JSON file containing nations data
        """
        path = Path(filepath)
        
        if not path.exists():
            raise FileNotFoundError(f"Nations file not found: {filepath}")
        
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        nations_data = data.get('nations', [])
        
        for nation_data in nations_data:
            nation = self._create_nation_from_dict(nation_data)
            self.nations[nation.tag] = nation
    
    @staticmethod
    def _create_nation_from_dict(data: Dict[str, Any]) -> Nation:
        """Create a Nation object from dictionary data."""
        # Extract known fields
        tag = data.get('tag')
        name = data.get('name')
        nation_type = data.get('type')
        capital = data.get('capital')
        capital_id = data.get('capital_id')  # Optional field for capital city ID
        government = data.get('government')
        parties = data.get('parties')
        substates = data.get('substates')
        parent = data.get('parent')
        flag = data.get('flag')
        
        # Collect any extra fields
        known_keys = {'tag', 'name', 'type', 'capital', 'capital_id', 'government', 
                     'parties', 'substates', 'parent', 'flag'}
        extra = {k: v for k, v in data.items() if k not in known_keys}
        
        return Nation(
            tag=tag,
            name=name,
            nation_type=nation_type,
            capital=capital,
            capital_id=capital_id,
            government=government,
            parties=parties,
            substates=substates,
            parent=parent,
            flag=flag,
            **extra
        )
    
    def get_nation(self, tag: str) -> Optional[Nation]:
        """Get a nation by its tag."""
        return self.nations.get(tag)
    
    def get_all_nations(self) -> List[Nation]:
        """Get all nations."""
        return list(self.nations.values())
    
    def get_by_type(self, nation_type: str) -> List[Nation]:
        """Get all nations of a specific type."""
        return [n for n in self.nations.values() if n.type == nation_type]
    
    def get_substates(self, nation_tag: str) -> List[Nation]:
        """Get all substates of a nation."""
        nation = self.get_nation(nation_tag)
        if not nation:
            return []
        return [self.get_nation(tag) for tag in nation.substates 
                if self.get_nation(tag)]
    



# Example usage
if __name__ == "__main__":
    # Create manager and load nations
    manager = NationManager()
    manager.load_from_json(Path(__file__).resolve().parent.parent / "QgizFiles" / "nations.json")
    
    # Print all nations
    for nation in manager.get_all_nations():
        print(nation)
    
    # Get specific nation
    brazil = manager.get_nation("BRA")
    if brazil:
        print(f"\nBrazil substates: {[str(s) for s in manager.get_substates('BRA')]}")
