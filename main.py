import FreeCAD
import Part
import sys

STEP_FILE = "tankVolumeCalculator.STEP"

def load_shape(step_file):
    shape = Part.Shape()
    shape.read(step_file)
    return shape

def volume_at_height(shape, height_mm):
    bbox = shape.BoundBox

    margin = 1000
    fill_box = Part.makeBox(
        bbox.XLength + 2 * margin,
        bbox.YLength + 2 * margin,
        height_mm + margin,
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

if __name__ == "__main__":
    step_shape = load_shape(STEP_FILE)

    h = float(sys.argv[1])
    litres = volume_at_height(step_shape, h)

    print(f"Height: {h:.2f} mm")
    print(f"Volume: {litres:.3f} L")