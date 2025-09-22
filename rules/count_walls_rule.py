# -*- coding: utf-8 -*-
"""
Created on Mon Sep  8 14:15:28 2025

@author: johan
"""

import ifcopenshell as ifc

## Exercise "Hello IFC world"

# Copy path of file as a string
# Remember file name at last
# Insert "r" at the start of the string (backslashes messes with the string)
model = ifc.open(r'C:\Users\johan\Desktop\Dokumenter\DTU\9. semester\41934 Advanced BIM\Assignment1\25-08-D-STR.ifc')

walls = model.by_type('IfcWall')
print(f'Walls in model: {len(walls)}')

# Get the different wall types and their counts
wall_properties = {}
for wall in walls:
    wall_type = wall.IsTypedBy[0].RelatingType
    wall_name = wall_type.Name
    if wall_name not in wall_properties:
        wall_properties[wall_name] = 0
    wall_properties[wall_name] += 1
print("Wall types and counts:", wall_properties)

# Define the wall type name you want to keep
# We only want to keep "Basic Wall:Wall_200Concrete" since the others are not real walls (ie. footings)
target_wall_type_name = "Basic Wall:Wall_200Concrete"

# Filter walls to only include the target type
filtered_walls = []
for wall in walls:
    wall_type = wall.IsTypedBy[0].RelatingType
    if wall_type.Name == target_wall_type_name:
        filtered_walls.append(wall)

print(f'Filtered walls ({target_wall_type_name}): {len(filtered_walls)}')

# Count filtered walls per floor
walls_per_floor = {}
for wall in filtered_walls:
    for rel in wall.ContainedInStructure:
        floor = rel.RelatingStructure
        if floor not in walls_per_floor:
            walls_per_floor[floor] = 0
        walls_per_floor[floor] += 1



for floor, count in walls_per_floor.items():
    print(f'Floor: {floor.Name}, wall count: {count}')



def get_wall_info(wall):
    info = {}
    info['GlobalId'] = wall.GlobalId
    info['Name'] = getattr(wall, 'Name', None)
    info['TypeName'] = wall.IsTypedBy[0].RelatingType.Name if wall.IsTypedBy else None
    info['OverallWidth'] = getattr(wall.IsTypedBy[0].RelatingType, 'OverallWidth', None) if wall.IsTypedBy else None
    # Gather property sets
    info['PropertySets'] = {}
    for definition in wall.IsDefinedBy:
        if definition.is_a('IfcRelDefinesByProperties'):
            prop_set = definition.RelatingPropertyDefinition
            if hasattr(prop_set, 'HasProperties'):
                props = {p.Name: getattr(p, 'NominalValue', None) for p in prop_set.HasProperties}
                info['PropertySets'][prop_set.Name] = props
    return info

# Print detailed info for each filtered wall
for wall in filtered_walls:
    print(f"\nWall GlobalId: {wall.GlobalId}")
    for definition in wall.IsDefinedBy:
        if definition.is_a('IfcRelDefinesByProperties'):
            prop_set = definition.RelatingPropertyDefinition
            if hasattr(prop_set, 'HasProperties'):
                print(f"  Property Set: {prop_set.Name}")
                for p in prop_set.HasProperties:
                    value = getattr(p, 'NominalValue', None)
                    # If value is a data type object, get its value
                    if hasattr(value, 'wrappedValue'):
                        value = value.wrappedValue
                    print(f"    Property: {p.Name} = {value}")
