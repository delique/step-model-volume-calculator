# Run with python main.py <step_file> <height_mm>

import FreeCAD
import Part
import argparse
from pathlib import Path
import sys

# Tank coordinate assumptions:
# Y = vertical height direction
# bottom of tank is at the model's minimum Y
# units are mm

def load_shape(step_file):
    if not step_file.exists():
        raise FileNotFoundError(f"STEP file not found: {step_file}")

    shape = Part.Shape()
    shape.read(str(step_file))

    if shape.isNull():
        raise ValueError(f"Failed to read STEP geometry from: {step_file}")

    return shape

def volume_at_height(shape, height_mm):
    bbox = shape.BoundBox

    margin = 1000
    fill_box = Part.makeBox(
        bbox.XLength + 2 * margin,
        height_mm + margin,
        bbox.ZLength + 2 * margin,
        FreeCAD.Vector(
            bbox.XMin - margin,
            bbox.YMin - margin,
            bbox.ZMin - margin,
        )
    )

    filled_shape = shape.common(fill_box)

    volume_mm3 = filled_shape.Volume
    volume_litres = volume_mm3 / 1_000_000

    return volume_litres


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Compute the volume of a STEP model up to a given fill height (mm)."
    )
    parser.add_argument("step_file", type=Path, help="Path to the STEP file")
    parser.add_argument("height_mm", type=float, help="Fill height in mm")
    return parser.parse_args(argv)

if __name__ == "__main__":
    args = parse_args(sys.argv[1:])

    if args.height_mm < 0:
        raise ValueError("height_mm must be non-negative")

    step_shape = load_shape(args.step_file)

    litres = volume_at_height(step_shape, args.height_mm)

    print(f"STEP: {args.step_file}")
    print(f"Height: {args.height_mm:.2f} mm")
    print(f"Volume: {litres:.3f} L")