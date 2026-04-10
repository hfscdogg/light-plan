"""DXF/DWG file parsing for floor plan import.

TODO: Phase 2 implementation. This module will handle:
- DXF file reading using ezdxf library
- Layer extraction for walls, doors, windows
- Room boundary detection
- Dimension extraction from annotation layers
- Conversion to the same RoomData format that plan_parser.py produces
"""


class DXFParser:
    def parse(self, file_path: str) -> dict:
        raise NotImplementedError(
            "DXF parsing is not yet implemented. "
            "Upload a PDF or image file instead."
        )
