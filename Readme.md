# Step Model Volume Calculator

This is a simple program designed to take a step model input and outputs the volume at incremental steps into a CSV file.

Run with python main.py [step_file] [--increment-mm 0.1] [--output-csv out.csv] [--height-axis xyz] [--height-origin world-zero|model-min]
Defaults: increment 0.1 mm, height axis z, height origin world-zero

Visualization options:
- --preview opens a 3D preview window with model mesh and XYZ axis lines (selected height axis is highlighted).
- --preview-image preview.png saves a preview image without opening a window.
- --preview-height-mm 300 draws a translucent plane at a chosen fill height to verify axis direction.

Note that you must have FreeCAD installed and in your PATH to be usable by python.
Note that all units are in millimeters.