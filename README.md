# BIManalyst group 22

Focus area:
Structural analysis of walls in the model 25-08-D-STR.ifc

Claim:
The consultant report states, that there are 23 walls in the building used for structural load-bearing.
The given scripts verifies the actual number of walls in each floor interpreted via. the model.

Report and page number:
The given claim is found in the report: D_Report_Team08_STR on page 16.

Description of script:
The script is called "count_walls_rule" and is written in python and uses the ifcopenshell package for analysis of an ifc-model.
Every property for the walls are loaded for eventual further analysis.
The walls are then counted on each floor excluding the footings which have wall properties as well.



