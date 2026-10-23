# ROI Calibration Tool (`tools/calibrate_rois.py`)

Utility to configure parking spot polygons (ROIs) for cameras, automatically from PKLot `.xml` datasets, interactively via an OpenCV GUI window, or to preview and snapshot calibrated cuts.

---

## Command Examples

### 1. View Cuts in a Pop-up Window & Save Snapshot
Opens an interactive window displaying the photo with all spot polygons. **Press any key or ESC to close it and make the window disappear.** It also saves a high-res snapshot to `tests/output/<camera_id>_cuts.jpg`:
```bash
.venv/bin/python tools/calibrate_rois.py cam_02 --preview
```

### 2. Generate Cuts Snapshot (Headless / Without Window)
Renders all spot cuts and saves the snapshot directly to `tests/output/<camera_id>_cuts.jpg` without popping up a window:
```bash
.venv/bin/python tools/calibrate_rois.py cam_02 --preview --no-gui
```

### 3. Auto-Extract Polygons from an XML Folder (No GUI)
Extracts all 4-corner spot polygons from XML ground-truth files directly into `config/cameras/<camera_id>.json`:
```bash
.venv/bin/python tools/calibrate_rois.py test-samples/cam_02
```

### 4. Auto-Extract from a Specific XML File
Imports spot polygons from a single XML file into the camera's configuration:
```bash
.venv/bin/python tools/calibrate_rois.py test-samples/cam_02/2013-03-03_06_45_00.xml
```

### 5. Auto-Extract with Custom Camera ID Override
Specifies the target camera ID explicitly if the directory name does not start with `cam_`:
```bash
.venv/bin/python tools/calibrate_rois.py path/to/dataset_folder -c cam_custom
```

### 6. Interactive GUI Drawing on a Reference Photo
Opens an OpenCV window to manually click the 4 corners of each parking spot:
```bash
.venv/bin/python tools/calibrate_rois.py test-samples/cam_01/2013-01-18_13_55_10.jpg -c cam_01
```

### 7. Interactive GUI with a Blank Canvas
Clears any pre-existing spots and starts fresh:
```bash
.venv/bin/python tools/calibrate_rois.py test-samples/cam_01/2013-01-18_13_55_10.jpg -c cam_01 --clean
```

### 8. Dry-Run Setup Validation
Validates image loading or XML parsing without launching the GUI or modifying files:
```bash
.venv/bin/python tools/calibrate_rois.py test-samples/cam_02 --dry-run
```

---

## Interactive GUI Keybindings

When running in GUI mode (`calibrate_rois.py <image>`):
- **Left Click:** Click the 4 corners of a parking stall (clockwise or counter-clockwise).
- **`S`:** Save defined spots to `config/cameras/<camera_id>.json`.
- **`U`:** Undo the last clicked vertex or last completed spot.
- **`C`:** Cancel current in-progress spot vertices.
- **`R`:** Reset all spots on screen.
- **`Q` / `ESC`:** Quit calibration tool.
