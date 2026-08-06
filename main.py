# Run with python main.py [step_file] [--increment-mm 0.1] [--max-height-mm 749] [--output-csv out.csv]
# Defaults: tankVolumeCalculator.STEP, increment 0.1 mm, max height 749 mm

import FreeCAD
import Part
import argparse
import csv
import math
from pathlib import Path
import sys

# Tank coordinate assumptions:
# height is measured from the minimum coordinate on the selected axis
# units are mm

AXIS_TO_BOUNDS = {
    "x": ("XMin", "XLength"),
    "y": ("YMin", "YLength"),
    "z": ("ZMin", "ZLength"),
}

def load_shape(step_file):
    if not step_file.exists():
        raise FileNotFoundError(f"STEP file not found: {step_file}")

    shape = Part.Shape()
    shape.read(str(step_file))

    if shape.isNull():
        raise ValueError(f"Failed to read STEP geometry from: {step_file}")

    return shape


def extract_volume_shape(shape):
    solids = list(shape.Solids)
    if solids:
        if len(solids) == 1:
            return solids[0]
        return Part.makeCompound(solids)

    if shape.Volume > 0:
        return shape

    raise ValueError(
        "STEP contains no closed solids with volume. "
        "Export a solid body or a watertight volume for tank calculations."
    )


def get_axis_bounds(shape, axis):
    axis_key = axis.lower()
    if axis_key not in AXIS_TO_BOUNDS:
        raise ValueError(f"Unsupported axis '{axis}'. Use one of: x, y, z")

    min_attr, length_attr = AXIS_TO_BOUNDS[axis_key]
    bbox = shape.BoundBox
    axis_min = getattr(bbox, min_attr)
    axis_length = getattr(bbox, length_attr)
    return axis_min, axis_length


def get_axis_top(axis_min, height_mm, origin_mode):
    if origin_mode == "model-min":
        return axis_min + height_mm
    if origin_mode == "world-zero":
        return height_mm
    raise ValueError(f"Unsupported height origin mode: {origin_mode}")

def volume_at_height(shape, height_mm, axis="z", origin_mode="model-min"):
    bbox = shape.BoundBox
    axis_min, _ = get_axis_bounds(shape, axis)
    axis_top = get_axis_top(axis_min, height_mm, origin_mode)

    margin = 1000
    axis_low = min(axis_min, 0.0) - margin
    axis_length = axis_top - axis_low
    if axis_length <= 0:
        return 0.0

    if axis == "x":
        fill_box = Part.makeBox(
            axis_length,
            bbox.YLength + 2 * margin,
            bbox.ZLength + 2 * margin,
            FreeCAD.Vector(
                axis_low,
                bbox.YMin - margin,
                bbox.ZMin - margin,
            ),
        )
    elif axis == "y":
        fill_box = Part.makeBox(
            bbox.XLength + 2 * margin,
            axis_length,
            bbox.ZLength + 2 * margin,
            FreeCAD.Vector(
                bbox.XMin - margin,
                axis_low,
                bbox.ZMin - margin,
            ),
        )
    else:
        fill_box = Part.makeBox(
            bbox.XLength + 2 * margin,
            bbox.YLength + 2 * margin,
            axis_length,
            FreeCAD.Vector(
                bbox.XMin - margin,
                bbox.YMin - margin,
                axis_low,
            ),
        )

    filled_shape = shape.common(fill_box)

    volume_mm3 = filled_shape.Volume
    volume_litres = volume_mm3 / 1_000_000

    return volume_litres


def find_first_nonzero_height(shape, increment_mm, max_height_mm, axis="z", origin_mode="model-min"):
    step_count = int(math.floor(max_height_mm / increment_mm))
    for i in range(step_count + 1):
        h = i * increment_mm
        if volume_at_height(shape, h, axis=axis, origin_mode=origin_mode) > 0:
            return h
    return None

def generate_height_volume_rows(shape, increment_mm, max_height_mm=None, axis="z", origin_mode="model-min"):
    if increment_mm <= 0:
        raise ValueError("increment_mm must be greater than 0")

    if max_height_mm is None:
        _, axis_length = get_axis_bounds(shape, axis)
        max_height_mm = axis_length

    if max_height_mm < 0:
        raise ValueError("max_height_mm must be non-negative")

    step_count = int(math.floor(max_height_mm / increment_mm))
    heights = [i * increment_mm for i in range(step_count + 1)]

    # Ensure the very top is included even when max height is not a perfect multiple.
    if not heights or not math.isclose(heights[-1], max_height_mm, rel_tol=0.0, abs_tol=1e-9):
        heights.append(max_height_mm)

    rows = []
    for height_mm in heights:
        litres = volume_at_height(shape, height_mm, axis=axis, origin_mode=origin_mode)
        rows.append((height_mm, litres))

    return rows


def write_volume_csv(rows, output_csv):
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["height_mm", "volume_litres"])
        for height_mm, volume_litres in rows:
            writer.writerow([f"{height_mm:.3f}", f"{volume_litres:.6f}"])


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Generate a height-to-volume CSV from a STEP model."
    )
    default_step = Path.cwd() / "tankVolumeCalculator.STEP"
    parser.add_argument(
        "step_file",
        type=Path,
        nargs="?",
        default=default_step,
        help=f"Path to the STEP file (default: {default_step.name})",
    )
    parser.add_argument(
        "--increment-mm",
        type=float,
        default=0.1,
        help="Height increment in mm for each CSV row (default: 0.1)",
    )
    parser.add_argument(
        "--max-height-mm",
        type=float,
        default=749,
        help="Max fill height in mm (default: 749)",
    )
    parser.add_argument(
        "--height-axis",
        choices=["x", "y", "z"],
        default="z",
        help="Axis used as fill height direction (default: z)",
    )
    parser.add_argument(
        "--height-origin",
        choices=["model-min", "world-zero"],
        default="world-zero",
        help="Height zero reference: model minimum or global zero plane (default: world-zero)",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=None,
        help="Output CSV path. Defaults to <step_file_stem>_height_volume.csv",
    )
    return parser.parse_args(argv)

if __name__ == "__main__":
    args = parse_args(sys.argv[1:])

    step_shape = load_shape(args.step_file)
    volume_shape = extract_volume_shape(step_shape)

    output_csv = args.output_csv
    if output_csv is None:
        output_csv = args.step_file.with_name(f"{args.step_file.stem}_height_volume.csv")

    rows = generate_height_volume_rows(
        volume_shape,
        increment_mm=args.increment_mm,
        max_height_mm=args.max_height_mm,
        axis=args.height_axis,
        origin_mode=args.height_origin,
    )
    write_volume_csv(rows, output_csv)

    first_nonzero = find_first_nonzero_height(
        volume_shape,
        increment_mm=args.increment_mm,
        max_height_mm=args.max_height_mm,
        axis=args.height_axis,
        origin_mode=args.height_origin,
    )

    max_height_written = rows[-1][0] if rows else 0.0
    axis_min, axis_length = get_axis_bounds(volume_shape, args.height_axis)
    raw_axis_min, raw_axis_length = get_axis_bounds(step_shape, args.height_axis)
    print(f"STEP: {args.step_file}")
    print(f"Rows written: {len(rows)}")
    print(f"Height range: 0.000 mm to {max_height_written:.3f} mm")
    print(f"Increment: {args.increment_mm:.3f} mm")
    print(f"Height axis: {args.height_axis.upper()}")
    print(f"Height origin: {args.height_origin}")
    print(f"Axis minimum (solid bbox): {axis_min:.3f} mm")
    print(f"Axis length (solid bbox): {axis_length:.3f} mm")
    if rows and args.height_origin == "world-zero" and rows[0][1] > 0:
        print(
            f"Note: volume at height 0 is {rows[0][1]:.6f} L because global zero intersects the model volume "
            f"on axis {args.height_axis.upper()}. Use --height-origin model-min to force 0 L at height 0."
        )
    if not math.isclose(raw_axis_min, axis_min, rel_tol=0.0, abs_tol=1e-9):
        print(
            f"Note: full-shape axis minimum is {raw_axis_min:.3f} mm (solids start higher)."
        )
    if not math.isclose(raw_axis_length, axis_length, rel_tol=0.0, abs_tol=1e-9):
        print(
            f"Note: full-shape axis length is {raw_axis_length:.3f} mm (includes non-solid geometry)."
        )
    if first_nonzero is not None:
        print(f"First non-zero volume at height: {first_nonzero:.3f} mm")
        if first_nonzero > args.increment_mm * 2:
            print(
                "Warning: volume remains zero for an initial region. "
                "This often means the selected height axis does not match the model's vertical direction, "
                "or the shape has no enclosed volume near the base on that axis."
            )
    else:
        print("Warning: no non-zero volume found in the requested height range.")
    print(f"CSV: {output_csv}")