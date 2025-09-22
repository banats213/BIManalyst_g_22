# -*- coding: utf-8 -*-
"""
Created on Mon Sep  8 14:15:28 2025

"""

import ifcopenshell as ifc

# Copy path of model-file as a string
# Remember file name at last
# Insert "r" at the start of the string (backslashes messes with the string)
model = ifc.open(r'C:\Users\johan\Desktop\Dokumenter\DTU\9. semester\41934 Advanced BIM\Assignment1\25-08-D-STR.ifc')

# Define walls from the model
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

# Print wall counts per floor
for floor, count in walls_per_floor.items():
    print(f'Floor: {floor.Name}, wall count: {count}')

# Collect detailed info for each filtered wall (no printing)
# Can be used for further analysis if needed
walls_detailed_info = []

for wall in filtered_walls:
    wall_info = {"GlobalId": wall.GlobalId, "PropertySets": {}}
    for definition in wall.IsDefinedBy:
        if definition.is_a('IfcRelDefinesByProperties'):
            prop_set = definition.RelatingPropertyDefinition
            if hasattr(prop_set, 'HasProperties'):
                props = {}
                for p in prop_set.HasProperties:
                    value = getattr(p, 'NominalValue', None)
                    if hasattr(value, 'wrappedValue'):
                        value = value.wrappedValue
                    props[p.Name] = value
                wall_info["PropertySets"][prop_set.Name] = props
    walls_detailed_info.append(wall_info)

