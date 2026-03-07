A -> make a map of south america and provinces (OK)
B-> inport to QGIZ and make a shapefile with the provinces with
  b.1 id
  b.2 owner
  b.3 controler
  b.4 is ocean
  b.5 terrain(value changing from zero to 5 corresponding to a type of terrain, at the start we have:
    b.5.1  ocean -> 0
    b.5.2  flatlands -> 1
    b.5.3  hills ->2
    b.5.4  mountain ->3
  b.6 is the ALT (for height sickness developing in the future) 
  b.7 may add more stuff here to be considered.
C-> after that work on the first prototype, load map, create the colisions.
D-> create units and buildings and make them move on the map 
------------------------------------------------------------------------------------------------- first test
