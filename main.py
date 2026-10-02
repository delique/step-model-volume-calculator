import FreeCAD
import Part
import argparse
import csv
import math
from pathlib import Path
import sys

try:
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
except ImportError:
    plt = None
    Poly3DCollection = None

AXIS_TO_BOUNDS = {
    "x": ("XMin", "XLength"),
    "y": ("YMin", "YLength"),
    "z": ("ZMin", "ZLength"),
}


def make_axis_plane_vertices(bbox, axis, axis_value_mm):
    if axis == "x":
        return [
            (axis_value_mm, bbox.YMin, bbox.ZMin),
            (axis_value_mm, bbox.YMax, bbox.ZMin),
            (axis_value_mm, bbox.YMax, bbox.ZMax),
            (axis_value_mm, bbox.YMin, bbox.ZMax),
        ]
    if axis == "y":
        return [
            (bbox.XMin, axis_value_mm, bbox.ZMin),
            (bbox.XMax, axis_value_mm, bbox.ZMin),
            (bbox.XMax, axis_value_mm, bbox.ZMax),
            (bbox.XMin, axis_value_mm, bbox.ZMax),
        ]
    return [
        (bbox.XMin, bbox.YMin, axis_value_mm),
        (bbox.XMax, bbox.YMin, axis_value_mm),
        (bbox.XMax, bbox.YMax, axis_value_mm),
        (bbox.XMin, bbox.YMax, axis_value_mm),
    ]

def load_volume(step_file):
    if not step_file.exists():
        raise FileNotFoundError(f"STEP file not found: {step_file}")

    shape = Part.Shape()
    shape.read(str(step_file))

    if shape.isNull():
        raise ValueError(f"Failed to read STEP geometry from: {step_file}")

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


def visualize_shape(shape, axis="z", origin_mode="model-min", preview_height_mm=None, output_image=None, show_window=False):
    if plt is None or Poly3DCollection is None:
        raise RuntimeError(
            "Matplotlib is required for preview mode. Install it with: pip install matplotlib"
        )

    bbox = shape.BoundBox
    diag = max(bbox.DiagonalLength, 1.0)
    deflection = max(diag * 0.006, 0.2)

    vertices, triangles = shape.tessellate(deflection)
    mesh_faces = []
    for i0, i1, i2 in triangles:
        p0 = vertices[i0]
        p1 = vertices[i1]
        p2 = vertices[i2]
        mesh_faces.append(
            [
                (p0.x, p0.y, p0.z),
                (p1.x, p1.y, p1.z),
                (p2.x, p2.y, p2.z),
            ]
        )

    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection="3d")

    mesh = Poly3DCollection(mesh_faces, facecolor="#7aa6c2", edgecolor="none", alpha=0.35)
    ax.add_collection3d(mesh)

    center = shape.CenterOfMass
    axis_style = {
        "x": ("#d62728", "X"),
        "y": ("#2ca02c", "Y"),
        "z": ("#1f77b4", "Z"),
    }
    for axis_key, (color, label) in axis_style.items():
        start = FreeCAD.Vector(center)
        end = FreeCAD.Vector(center)
        if axis_key == "x":
            start.x = bbox.XMin
            end.x = bbox.XMax
        elif axis_key == "y":
            start.y = bbox.YMin
            end.y = bbox.YMax
        else:
            start.z = bbox.ZMin
            end.z = bbox.ZMax
        width = 3.0 if axis_key == axis else 1.8
        alpha = 1.0 if axis_key == axis else 0.8
        ax.plot(
            [start.x, end.x],
            [start.y, end.y],
            [start.z, end.z],
            color=color,
            linewidth=width,
            alpha=alpha,
        )
        ax.text(end.x, end.y, end.z, label, color=color, fontsize=11)

    if preview_height_mm is not None:
        axis_min, axis_length = get_axis_bounds(shape, axis)
        axis_top = get_axis_top(axis_min, preview_height_mm, origin_mode)
        clamped_axis_top = max(axis_min, min(axis_min + axis_length, axis_top))
        plane_vertices = make_axis_plane_vertices(bbox, axis, clamped_axis_top)
        plane = Poly3DCollection([plane_vertices], facecolor="#f4a261", alpha=0.35, edgecolor="#f4a261")
        ax.add_collection3d(plane)

    pad = max(diag * 0.05, 5.0)
    ax.set_xlim(bbox.XMin - pad, bbox.XMax + pad)
    ax.set_ylim(bbox.YMin - pad, bbox.YMax + pad)
    ax.set_zlim(bbox.ZMin - pad, bbox.ZMax + pad)
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")
    ax.set_zlabel("Z (mm)")
    ax.set_title(f"STEP Preview | Height Axis: {axis.upper()} | Origin: {origin_mode}")
    ax.set_box_aspect((
        max(bbox.XLength, 1.0),
        max(bbox.YLength, 1.0),
        max(bbox.ZLength, 1.0),
    ))

    if output_image is not None:
        output_image.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_image, dpi=180, bbox_inches="tight")

    if show_window:
        plt.show()
    else:
        plt.close(fig)


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
        help="Reference for height=0. model-min starts at the solid bbox minimum; world-zero uses global origin (default: world-zero)",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=None,
        help="Output CSV path. Defaults to <step_file_stem>_height_volume.csv",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Open a 3D preview window to verify geometry import and axis orientation.",
    )
    parser.add_argument(
        "--preview-image",
        type=Path,
        default=None,
        help="Save a preview image (PNG/JPG) of the imported model and selected axis.",
    )
    parser.add_argument(
        "--preview-height-mm",
        type=float,
        default=None,
        help="Optional height for drawing a translucent fill plane in preview mode.",
    )
    return parser.parse_args(argv)

if __name__ == "__main__":
    args = parse_args(sys.argv[1:])

    volume_shape = load_volume(args.step_file)

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

    if args.preview or args.preview_image is not None:
        visualize_shape(
            volume_shape,
            axis=args.height_axis,
            origin_mode=args.height_origin,
            preview_height_mm=args.preview_height_mm,
            output_image=args.preview_image,
            show_window=args.preview,
        )

    max_height_written = rows[-1][0] if rows else 0.0
    axis_min, axis_length = get_axis_bounds(volume_shape, args.height_axis)
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
    if args.preview_image is not None:
        print(f"Preview image: {args.preview_image}")
    print(f"CSV: {output_csv}")