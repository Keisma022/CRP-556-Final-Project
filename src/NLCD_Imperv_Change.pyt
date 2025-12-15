#==================================================================================================
# NLCD IMPERVIOUS SURFACE CHANGE TOOLBOX
#
# Author: Kolton Eisma
# Email:  Keisma@iastate.edu
# Date:   11/20/2025
#
# OVERVIEW:
# This Python Toolbox automates the processing of NLCD Impervious Surface Data to measure, summarize, 
# and map urban development change acrross multiple time periods using a consistant ArcGIS Pro Template Project
#  
# WORKFLOW
# 1. Read configuration (AOI, years, raster paths, outputs)
# 2. Filter the AOI feature class to a single city (Currently only for the cities within the State of Iowa)
# 3. Clip NLCD impervious rasters to the city AOI for each year
# 4. Compute impervious % change for each consecutive year pair
# 5. Classify change into 5 categories (large decrease → large increase)
# 6. Summarize change values to CSVs and pairwise summary table
# 7. Export map PNGs using a standard layout and color scheme
# 8. Compute and export a net change map forr the entire period 2001-2021
#
#==================================================================================================
from pathlib import Path
import csv
import arcpy
import numpy as np
from arcpy.sa import Reclassify, RemapRange, ExtractByMask

arcpy.CheckOutExtension("Spatial")
Project_Root = Path(__file__).resolve().parents[1]
# Default AOI feature class (State Of Iowa Shapefile named City)
Default_AOI = Project_Root / "data" / "boundaries" / "City.shp"

#--------------------------------------------------------------------------------------------------
# LOGGING HELPERS
# Helpers to wrap ArcGIS messaging functions to clean up code
#--------------------------------------------------------------------------------------------------
def log(msg: str) -> None:
    arcpy.AddMessage(msg)

def log_warn(msg: str) -> None:
    arcpy.AddWarning(msg)

def log_err(msg: str) -> None:
    arcpy.AddError(msg)

#--------------------------------------------------------------------------------------------------
# UTILITY & WORKFLOW FUNCTIONS
#--------------------------------------------------------------------------------------------------
def ensure_outputs(project_root: Path, cfg: dict) -> Path:
    out_cfg = cfg["output"]

    # --- Ensure output folders exist (CSV + logs) ---
    if out_cfg.get("create_folders_if_missing", True):
        (project_root / out_cfg["csv_folder"]).mkdir(parents=True, exist_ok=True)
        (project_root / out_cfg["log_folder"]).mkdir(parents=True, exist_ok=True)

    # --- Ensure output GDB exists ---
    gdb_path = project_root / out_cfg["gdb"]
    gdb_folder = gdb_path.parent
    gdb_name = gdb_path.name

    if out_cfg.get("create_gdb_if_missing", True) and not arcpy.Exists(str(gdb_path)):
        log(f"Creating output geodatabase at: {gdb_path}")
        result_gdb = arcpy.management.CreateFileGDB(str(gdb_folder), gdb_name)
        log(f"  GDB created: {result_gdb[0]}")

    return gdb_path

def clip_imperv_year(pattern: str, year: int, aoi_fc: str, out_gdb: Path) -> str:
    """
    Clip a single NLCD Imperviouus Raster for a given year to the AOI using "ExtractByMask"
    
    Parameters:
    Pattern: str ->  String pattern for raster paths with a {year} placeholder
    year: int ->     Year to Clip (e.g., 2001)
    aoi_fc : str ->  Feature Class Path for AOI (City Polygon)
    out_gdb: Path -> Geodatabse in which to store clipped raster
    
    This in all returns a Full Path to the clipped raster inside the GDB
    """
    in_raster_path = pattern.format(year=year)
    out_name = f"Imperv_{year}_clipped"
    out_path = out_gdb / out_name

    log(f"  Clipping {in_raster_path} to AOI -> {out_name} (ExtractByMask)")
    try:
        clipped = ExtractByMask(in_raster_path, aoi_fc)
        clipped.save(str(out_path))
    except arcpy.ExecuteError:
        log_err("ExtractByMask (clip) failed with messages:")
        log_err(arcpy.GetMessages(2))
        raise

    return str(out_path)

def compute_change_pair(imperv_before_path: str,
                        imperv_after_path: str,
                        out_gdb: Path,
                        year1: int,
                        year2: int) -> str:
    """
    Compute % Impervious Change for year pair: Change = after - before

    Parameters:
    imperv_before_path : str -> Path to clipped impervious raster for the earlier year.
    imperv_after_path : str ->  Path to clipped impervious raster for the later year.
    out_gdb : Path ->  Output geodatabase.
    year1, year2 : int -> Year pair identifiers for naming outputs.

    This in all returns a Path to the change raster stored in the gdb.
    """
    log(f"  Computing change raster: {year1} -> {year2}")
    before_ras = arcpy.Raster(imperv_before_path)
    after_ras = arcpy.Raster(imperv_after_path)

    # Simple raster subtraction: assuming rasters are already aligned and in percent units (0–100).
    change_ras = after_ras - before_ras

    out_name = f"chg_{year1}_{year2}"
    out_path = out_gdb / out_name
    change_ras.save(str(out_path))

    return str(out_path)

def classify_change(change_raster_path: str,
                    out_gdb: Path,
                    year1: int,
                    year2: int) -> str:
    """
    Reclassify continuous change into five discrete categories (1–5) based on magnitude:

      1 = Large Decrease (-100% to -50% Negative Change in Impervious Surfaces)
      2 = Moderate Decrease (-50% to -10% Negative Change in Impervious Surfaces)
      3 = No Change (-10% to +10% Change in Impervious Surfaces)
      4 = Moderate Increase (+10 to +50% Positive Change in Impervious Surfaces)
      5 = Large Increase (+50% to +100% Positive Change in Impervious Surfaces)

    Thresholds are defined in the RemapRange below.

    Returns the path to the classified raster.

    """
    log(f"  Classifying change raster: chg_{year1}_{year2}")
    change_raster = arcpy.Raster(change_raster_path)
    # Define change ranges (in percentage points) mapped to integer classes
    remap = RemapRange([
        [-100, -50, 1],  # Large Decrease
        [-50,  -10, 2],   # Moderate Decrease
        [-10,    10, 3],   # No Change
        [10,    50, 4],   # Moderate Increase 
        [50,  100, 5]    # Large Increase
    ])

    chg_class = Reclassify(change_raster, "Value", remap, "NODATA")
    out_name = f"chg_class_{year1}_{year2}"
    out_path = out_gdb / out_name
    chg_class.save(str(out_path))

    return str(out_path)

def summarize_change_hist(change_raster: arcpy.Raster, out_csv_path: Path) -> None:
    """
    Create a histogram of raw change values and save it to CSV.

    Bins are aligned to your classification scheme:
      [-100, -50), [-50, -10), [-10, 10), [10, 50), [50, 100]
    """
    log(f"  Summarizing change values to CSV: {out_csv_path.name}")

    arr = arcpy.RasterToNumPyArray(change_raster, nodata_to_value=-9999)
    flat = arr.flatten()
    valid = flat[flat != -9999]

    # Match classify_change thresholds:
    bins = [-100, -50, -10, 10, 50, 100]
    hist, edges = np.histogram(valid, bins=bins)

    out_csv_path.parent.mkdir(parents=True, exist_ok=True)

    with out_csv_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["bin_min", "bin_max", "pixel_count"])
        for i in range(len(hist)):
            writer.writerow([edges[i], edges[i + 1], int(hist[i])])

def resolve_city_aoi(aoi_fc: str, city_name: str) -> str:
    """
    Given an AOI feature class (e.g., all Iowa cities) and an optional city name,
    select the matching city polygon and write it to an in-memory feature class.

    If city_name is None or empty, the original AOI is returned unchanged.
    
    Parameters
    aoi_fc : str -> Path to the AOI feature class containing one or more city features.
    city_name : str -> Name of the city to select (e.g., "Ames").

    Returns a Path to a temporary AOI Feature Class for the selected city
    """
    if not city_name:
        return aoi_fc

    # Find field to use city names
    log(f"Filtering AOI to city: {city_name}")
    layer_name = "city_aoi_layer"
    arcpy.management.MakeFeatureLayer(aoi_fc, layer_name)

    # Determine name field
    fields = [f.name for f in arcpy.ListFields(layer_name) if f.type not in ("OID", "Geometry")]
    name_field = None

    if "CITY_NAME" in fields:
        name_field = "CITY_NAME"
    else:
        for cand in ["NAME", "CITY", "TOWN"]:
            if cand in fields:
                name_field = cand
                break

    if name_field is None:
        msg = ("Could not find a usable city name field in AOI. "
               "Expected CITY_NAME, NAME, CITY, or TOWN.")
        log_err(msg)
        raise RuntimeError(msg)

    log(f"  Using name field: {name_field}")
    city_escaped = city_name.replace("'", "''")
    fld = arcpy.AddFieldDelimiters(layer_name, name_field)
    where = f"{fld} = '{city_escaped}'"

    arcpy.management.SelectLayerByAttribute(layer_name, "NEW_SELECTION", where)
    count = int(arcpy.management.GetCount(layer_name)[0])
    if count == 0:
        msg = (f"No features found in AOI for {name_field} = '{city_name}'. "
               "Check spelling or attribute values.")
        log_err(msg)   
        raise RuntimeError(msg)   
   
    log(f"  Selected {count} feature(s) for city '{city_name}'.")
    # Copy selected city to an in-memory feature class for fast processing
    out_fc = arcpy.management.CopyFeatures(layer_name, r"in_memory/city_aoi_selected").getOutput(0)
    log(f"  Using temporary AOI: {out_fc}")

    return out_fc

def get_template_map_and_layout(project_root: Path) -> tuple:
    """
    Open the Imperv_Template APRX and return:
      - ArcGISProject
      - Template Map
      - Template Layout
      - Template MapFrame (BOUND to the map)

    This guarantees all exports use the Imperv_Template layout.
    """
    aprx_path = project_root / "maps" / "Imperv_Template.aprx"
    log(f"  [MAP] Using Imperv Template APRX: {aprx_path}")

    if not aprx_path.exists():
        raise RuntimeError(f"Imperv_Template.aprx not found at: {aprx_path}")

    # --- OPEN TEMPLATE PROJECT ---
    aprx = arcpy.mp.ArcGISProject(str(aprx_path))

    # --- GET TEMPLATE MAP ---
    maps = aprx.listMaps()
    if not maps:
        raise RuntimeError("Imperv_Template.aprx contains no maps.")
    m = maps[0]
    log(f"  [MAP] Using Template Map: {m.name}")

    # --- GET TEMPLATE LAYOUT ---
    layouts = aprx.listLayouts()
    if not layouts:
        raise RuntimeError("Imperv_Template.aprx contains no layouts.")

    preferred_names = {"Rate of Change", "Imperv_Template", "Imperv_Change Template"}

    layout = None
    for layout_obj in layouts:
        if layout_obj.name in preferred_names:
            layout = layout_obj
            break
    if layout is None:
        layout = layouts[0]

    log(f"  [MAP] Using Template Layout: {layout.name}")

    # --- GET TEMPLATE MAP FRAME ---
    map_frames = layout.listElements("MAPFRAME_ELEMENT")
    if not map_frames:
        raise RuntimeError("Template layout contains no MapFrame.")
    mf = map_frames[0]

    # --- HARD BIND MAPFRAME -> TEMPLATE MAP ---
    try:
        mf.map = m
        log(f"  [MAP] MapFrame '{mf.name}' bound to Template Map '{m.name}'")
    except Exception as e:
        raise RuntimeError(
            f"FAILED to bind MapFrame '{mf.name}' to Template Map '{m.name}'. "
            f"Export would not reflect template edits. Error: {e}"
        )

    return aprx, m, layout, mf

def apply_classmap_symbology(new_layer, map_obj, layout):
    """
    Force the classified raster layer to use a discrete 5-class color scheme
    and overwrite the legend entries in the layout.

    This uses the RasterClassifyColorizer, which is appropriate for integer rasters
    with discrete class values (1-5 in this toolbox).
    """
    sym = new_layer.symbology

    # Switch to RasterClassifyColorizer if needed
    try:
        if sym.colorizer.type != "RasterClassifyColorizer":
            sym.updateColorizer("RasterClassifyColorizer")
    except Exception as e:
        log_warn(f"  [MAP] Could not update to RasterClassifyColorizer: {e}")
        return

    clr = sym.colorizer
    clr.classificationField = "Value"
    clr.breakCount = 5  

    # Desired class labels and RGBA colors for classes 1–5
    class_list = [
        ("Large Decrease (-100 to -50%)",   [33, 102, 172, 255]),   # dark blue
        ("Moderate Decrease (-50 to -10%)", [103, 169, 207, 255]), # light blue
        ("No Change (-10 to +10%)",         [255, 255, 191, 255]), # neutral yellow
        ("Moderate Increase (+10 to +50%)", [253, 174, 97, 255]),  # light orange
        ("Large Increase (+50 to +100%)",   [215, 25, 28, 255]),   # strong red
    ]

    # Ensuring colorizer actually has 5 classBreaks to configure
    if len(clr.classBreaks) < 5:
        log_warn(f"  [MAP] Colorizer only has {len(clr.classBreaks)} breaks; cannot apply 5-class scheme.")
    else:
        # Assign label + color to each class break in order
        for idx, (label, rgba) in enumerate(class_list):
            brk = clr.classBreaks[idx]
            brk.label = label
            brk.color = {"RGB": rgba}

    # Apply modified symbology back to the layer
    new_layer.symbology = sym

    # Legend overwrite template legend items completely
    legends = layout.listElements("LEGEND_ELEMENT")
    if not legends:
        return
    legend = legends[0]

    # Add the new layer so legend matches the raster's discrete scheme
    legend.addItem(new_layer)
def refresh_legend(layout, keep_layer, keyword="Imperv Change"):
    """Remove prior legend items matching keyword, then add keep_layer."""
    legends = layout.listElements("LEGEND_ELEMENT")
    if not legends:
        log_warn("  [MAP] No legend element found.")
        return

    legend = legends[0]

    # Best-effort removal of prior legend items
    try:
        for item in list(legend.items):
            lyr = getattr(item, "layer", None)
            if lyr and keyword in (lyr.name or ""):
                legend.removeItem(item)
    except Exception as e:
        log_warn(f"  [MAP] Could not clear legend items: {e}")

    try:
        legend.addItem(keep_layer)
    except Exception as e:
        log_warn(f"  [MAP] Could not add layer to legend: {e}")

def export_change_map(class_raster_path: str,
                      aoi_fc: str,
                      year1: int,
                      year2: int,
                      project_root: Path,
                      city_name: str) -> None:
    """
    Export a classified change map for a year pair using the template APRX.
    Includes:
      - robust layer cleanup
      - discrete symbology
      - legend refresh (no duplicates)
      - dynamic title + font size
      - APRX released in finally (reduces lock/COM surrogate issues)
    """
    aprx = None
    try:
        log(f"  [MAP] Starting map export for {year1}-{year2}...")

        aoi_desc = arcpy.Describe(aoi_fc)
        aoi_sr = aoi_desc.spatialReference
        aoi_extent = aoi_desc.extent
        log(f"  [MAP] AOI spatial reference: {aoi_sr.name}")

        # --- OPEN TEMPLATE PROJECT / MAP / LAYOUT ---
        aprx, m, layout, mf = get_template_map_and_layout(project_root)

        # --- SAFETY: ensure mapframe bound to template map ---
        mf.map = m

        for lyr in list(m.listLayers()):
            nm = (lyr.name or "")
            if ("Imperv Change" in nm) or nm.startswith("chg_") or nm.startswith("chg_class_"):
                try:
                    m.removeLayer(lyr)
                except Exception as e:
                    log_warn(f"  [MAP] Could not remove old layer '{nm}': {e}")

        # Add classified raster
        new_layer = m.addDataFromPath(class_raster_path)
        new_layer.name = f"Imperv Change {year1}-{year2}"

        # Apply discrete symbology (no legend updates inside)
        apply_classmap_symbology(new_layer, m, layout)

        # Refresh legend to match current layer (prevents duplicates)
        refresh_legend(layout, new_layer, keyword="Imperv Change")

        # Dynamic title + font size
        for elm in layout.listElements("TEXT_ELEMENT"):
            if elm.name == "TitleText":
                elm.text = f"{city_name} {year1}–{year2} Impervious Surface Change"
                try:
                    elm.textSize = 24
                except Exception:
                    pass

        # Zoom to AOI
        try:
            mf.camera.spatialReference = aoi_sr
            mf.camera.setExtent(aoi_extent)
            log("  [MAP] Map frame extent and spatial reference set to AOI.")
        except Exception as e:
            log_warn(f"  [MAP] Could not set map frame extent/SR: {e}")

        # Output folder
        out_dir = project_root / "outputs" / "maps"
        out_dir.mkdir(parents=True, exist_ok=True)

        out_png = out_dir / f"chg_class_{year1}_{year2}.png"
        log(f"  [MAP] Exporting PNG to: {out_png}")

        if out_png.exists():
            try:
                out_png.unlink()
            except Exception as e:
                log_warn(f"  [MAP] Could not delete existing PNG: {e}")

        layout.exportToPNG(str(out_png), resolution=300)
        log(f"  [MAP] Exported map PNG successfully: {out_png}")

    except Exception as e:
        log_warn(f"  [MAP] Failed to export map for {year1}-{year2}: {e}")

    finally:
        try:
            if aprx is not None:
                del aprx
        except Exception:
            pass

def summarize_change_classes(chg_class_raster_path: str,
                             year1: int,
                             year2: int,
                             out_summary_rows: list) -> None:
    """
    Summarize classified change raster into pixel counts and area by class,
    and append a summary dict to out_summary_rows.

    The function reports:
      - pixel counts and areas by decrease / stable / increase
      - fractions of AOI area (0–1)
      - percents of AOI area (0–100) for each category

    NOTE:
      pct_* fields are already expressed as percentages (0–100).
      Do NOT re-format them as "Percent" in Excel or you will get 100× inflation.
    """
    log(f"  Summarizing change classes for {year1}-{year2}...")
    ras = arcpy.Raster(chg_class_raster_path)

    # Get cell size (assumed square) to compute area
    desc = arcpy.Describe(ras)
    cell_area = desc.meanCellWidth * desc.meanCellHeight

    # Convert to NumPy; treat 0 as nodata placeholder
    arr = arcpy.RasterToNumPyArray(ras, nodata_to_value=0)
    flat = arr.flatten()

    # Count pixels in each class 1–5
    class_counts = {cls: int(np.sum(flat == cls)) for cls in (1, 2, 3, 4, 5)}
    total_pixels = sum(class_counts.values())
    if total_pixels == 0:
        log_warn("  No valid pixels found in change class raster.")
        return

    # Aggregate to decrease / stable / increase
    dec_pixels  = class_counts[1] + class_counts[2]
    stab_pixels = class_counts[3]
    inc_pixels  = class_counts[4] + class_counts[5]

    # Areas (in map units squared, e.g. m²)
    dec_area   = dec_pixels  * cell_area
    stab_area  = stab_pixels * cell_area
    inc_area   = inc_pixels  * cell_area
    total_area = total_pixels * cell_area

    # Fractions of AOI area (0–1)
    frac_decrease = dec_area / total_area
    frac_stable   = stab_area / total_area
    frac_increase = inc_area / total_area

    # Percent of AOI area (0–100)
    pct_decrease = round(frac_decrease * 100.0, 4)
    pct_stable   = round(frac_stable   * 100.0, 4)
    pct_increase = round(frac_increase * 100.0, 4)

    summary = {
        "pair": f"{year1}_{year2}",
        "year1": year1,
        "year2": year2,

        # raw counts / areas
        "total_pixels": total_pixels,
        "total_area": total_area,
        "dec_pixels": dec_pixels,
        "dec_area": dec_area,
        "stab_pixels": stab_pixels,
        "stab_area": stab_area,
        "inc_pixels": inc_pixels,
        "inc_area": inc_area,

        # fractions of AOI (0–1)
        "frac_decrease": frac_decrease,
        "frac_stable": frac_stable,
        "frac_increase": frac_increase,

        # percents of AOI (0–100) – ready for plotting as-is
        "pct_decrease": pct_decrease,
        "pct_stable": pct_stable,
        "pct_increase": pct_increase,

        # individual class counts (for extra detail)
        "class1_big_dec_pixels": class_counts[1],
        "class2_small_dec_pixels": class_counts[2],
        "class3_stable_pixels": class_counts[3],
        "class4_small_inc_pixels": class_counts[4],
        "class5_big_inc_pixels": class_counts[5],
    }

    out_summary_rows.append(summary)

def run_change_analysis(cfg: dict, project_root: Path) -> None:
    """
    The Main driver for the NLCD impervious change Toolbox.

    Steps:
      • Resolve AOI path and optionally filter it to a single city.
      • Ensure output folders and File GDB exist.
      • For each consecutive pair of years:
          - Clip impervious rasters.
          - Compute change.
          - Classify change.
          - Summarize raw change (histogram CSV).
          - Summarize class counts/areas (summary CSV).
          - Export map PNG with template layout.
      • Compute net change from first to last year and export map/CSVs.
      • Print a short text summary of outputs to the Geoprocessing Messages.
    """
    # Resolve AOI path: allow for relative path under project_root
    city_aoi = cfg["city_aoi"]
    city_aoi_path = Path(city_aoi)
    aoi_fc = str(city_aoi_path if city_aoi_path.is_absolute()
                 else (project_root / city_aoi_path).resolve())

    # Filter AOI to one city if provided
    city_name = cfg.get("city_name", None)
    aoi_fc = resolve_city_aoi(aoi_fc, city_name)

    # Prepares outputs
    out_gdb = ensure_outputs(project_root, cfg)
    arcpy.env.workspace = str(out_gdb)
    arcpy.env.overwriteOutput = cfg.get("overwrite", True)

    years = cfg["years"]

    # Resolve NLCD raster path pattern
    raw_pattern = cfg["nlcd_imperv_pattern"]
    pattern = str(raw_pattern if Path(raw_pattern).is_absolute()
                  else (project_root / raw_pattern).resolve())

    csv_folder = project_root / cfg["output"]["csv_folder"]
    change_summaries = []

    # Process each consecutive pair of years
    if len(years) >= 2:
        for y1, y2 in zip(years[:-1], years[1:]):
            try:
                log(f"\nProcessing year pair {y1}–{y2}...")
                im1_path = clip_imperv_year(pattern, y1, aoi_fc, out_gdb)
                im2_path = clip_imperv_year(pattern, y2, aoi_fc, out_gdb)
                chg_path = compute_change_pair(im1_path, im2_path, out_gdb, y1, y2)
                chg_class_path = classify_change(chg_path, out_gdb, y1, y2)

                # Export CSV histogram of raw change values
                out_csv = csv_folder / f"chg_{y1}_{y2}.csv"
                summarize_change_hist(arcpy.Raster(chg_path), out_csv)

                # Summarize classified change for summary output
                summarize_change_classes(chg_class_path, y1, y2, change_summaries)

                # Export map PNG for this pair (uses discrete color scheme)
                export_change_map(chg_class_path, aoi_fc, y1, y2, project_root, cfg.get("city_name"))

            # Keep going even if one pair fails; log the error
            except Exception as e:
                log_warn(f"Error during {y1}-{y2}: {e}")

    # Writes a summary CSV of all pairs
    if change_summaries:
        summary_csv = csv_folder / "imperv_change_pair_summary.csv"
        log(f"\nWriting pairwise change summary CSV: {summary_csv}")
        fieldnames = [
            "pair", "year1", "year2",
            "total_pixels", "total_area",
            "dec_pixels", "dec_area",
            "stab_pixels", "stab_area",
            "inc_pixels", "inc_area",
            "pct_decrease", "pct_stable", "pct_increase",
            "class1_big_dec_pixels",
            "class2_small_dec_pixels",
            "class3_stable_pixels",
            "class4_small_inc_pixels",
            "class5_big_inc_pixels",
            "frac_decrease",
            "frac_stable",
            "frac_increase"
        ]
        summary_csv.parent.mkdir(parents=True, exist_ok=True)
        with summary_csv.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in change_summaries:
                writer.writerow(row)

    # Net change for full period (first year to last year)
    if len(years) >= 2:
        start_year = years[0]
        end_year = years[-1]

        # If only two years, net change == the same single pair you already processed
        if len(years) == 2:
            log(f"\nSkipping net-change export: only two years provided ({start_year}–{end_year}) "
                "so it duplicates the single year-pair output.")
        else:
            log(f"\nComputing net impervious change for full period {start_year}–{end_year}...")

            start_imperv = out_gdb / f"Imperv_{start_year}_clipped"
            end_imperv   = out_gdb / f"Imperv_{end_year}_clipped"

            if not arcpy.Exists(str(start_imperv)):
                log_warn(f"  Cannot compute net change: clipped raster not found for start year {start_year}.")
            elif not arcpy.Exists(str(end_imperv)):
                log_warn(f"  Cannot compute net change: clipped raster not found for end year {end_year}.")
            else:
                net_chg_path = compute_change_pair(str(start_imperv), str(end_imperv),
                                                out_gdb, start_year, end_year)
                net_class_path = classify_change(net_chg_path, out_gdb, start_year, end_year)
                net_csv = csv_folder / f"chg_{start_year}_{end_year}.csv"
                summarize_change_hist(arcpy.Raster(net_chg_path), net_csv)

                export_change_map(net_class_path, aoi_fc, start_year, end_year, project_root, cfg.get("city_name"))
                log(f"Finished net impervious change computation for {start_year}–{end_year}.")

#--------------------------------------------------------------------------------------------------
# SUMMARY MESSAGES
#--------------------------------------------------------------------------------------------------
    years_used = years
    out_gdb_full = project_root / Path(cfg["output"]["gdb"])
    csv_full = project_root / Path(cfg["output"]["csv_folder"])

    log("\n---------------------------")
    log("   IMPERVIOUS CHANGE SUMMARY")
    log("---------------------------")
    log(f"Processed Years: {years_used}")
    log(f"Output Geodatabase:\n  {out_gdb_full}")
    log(f"CSV Summary Files:\n  {csv_full}")
    log("\nRaster Outputs Created:")
    for (y1, y2) in zip(years_used[:-1], years_used[1:]):
        log(f"  • Imperv_{y1}_clipped")
        log(f"  • Imperv_{y2}_clipped")
        log(f"  • chg_{y1}_{y2}")
        log(f"  • chg_class_{y1}_{y2}")
        log(f"    → CSV: chg_{y1}_{y2}.csv")

    if len(years_used) >= 2:
        start_year = years_used[0]
        end_year = years_used[-1]
        log("\nNet Change (Full Period):")
        log(f"  • chg_{start_year}_{end_year}")
        log(f"  • chg_class_{start_year}_{end_year}")
        log(f"    → CSV: chg_{start_year}_{end_year}.csv")

    log("\nNLCD impervious surface change analysis completed successfully.\n")

def export_maps_with_layout(aprx_path: str, layout_name: str = "Imperv_Template") -> None:
    """
    This function demonstrates how to export multiple maps from a single
    ArcGIS Pro project by swapping map frames in a specified layout.

    It looks for maps whose names contain the year pair (e.g., "2001_2006")
    and exports PNGs for a fixed list of year pairs.

    """
    import os
    # Hard-coded example year pairs to export
    year_pairs = [(2001, 2006), (2006, 2011), (2011, 2016), (2016, 2021), (2001, 2021)]

    try:
        aprx = arcpy.mp.ArcGISProject(aprx_path)
    except Exception as e:
        log_err(f"Could not open project: {e}")
        return

    layouts = aprx.listLayouts(layout_name)
    if not layouts:
        log_err(f"Layout '{layout_name}' not found in project.")
        return
    layout = layouts[0]

    map_frames = layout.listElements("MAPFRAME_ELEMENT")
    if not map_frames:
        log_err("No map frame found in layout.")
        return
    map_frame = map_frames[0]

    output_dir = os.path.join(aprx.homeFolder, "Outputs")
    os.makedirs(output_dir, exist_ok=True)

    for year1, year2 in year_pairs:
        try:
            map_name_fragment = f"{year1}_{year2}"
            candidate_maps = [m for m in aprx.listMaps() if map_name_fragment in m.name]
            if not candidate_maps:
                log_warn(f"No map found for {year1}-{year2}")
                continue

            m = candidate_maps[0]
            map_frame.map = m

            output_path = os.path.join(output_dir, f"chg_class_{year1}_{year2}.png")
            layout.exportToPNG(output_path, resolution=300)
            log(f"Exported PNG for {year1}-{year2}: {output_path}")
        except Exception as e:
            log_warn(f"Failed to export map for {year1}-{year2}: {e}")

#--------------------------------------------------------------------------------------------------
# PYTHON TOOLBOX CLASSES
# 
#--------------------------------------------------------------------------------------------------
class Toolbox(object):
    def __init__(self):
        self.label = "NLCD Impervious Change Toolbox"
        self.alias = "nlcd_imperv_change"
        self.tools = [NLCDImperviousChangeTool]

class NLCDImperviousChangeTool(object):
    """
    Single geoprocessing tool: NLCD Impervious Change Analysis.

    This tool reads user parameters (years and optional city name),
    sets up a configuration dictionary, and calls the main
    run_change_analysis() function defined above.
    """

    def __init__(self):
        self.label = "NLCD Impervious Change Analysis"
        self.description = ("Runs the NLCD impervious surface change workflow using an internal "
                            "configuration, with optional overrides for AOI, years, NLCD path pattern, and city name.")
        self.canRunInBackground = False

    def getParameterInfo(self):
        """
        Define ArcGIS Pro tool parameters (GUI inputs).
        
        Parameters:
          p0: City AOI (Feature Class) – pre-set and disabled, uses internal City.shp.
          param_years: String of comma-separated years.
          param_cityname: Optional city name used to filter AOI to a single city.
        """
        p0 = arcpy.Parameter(
            displayName="City AOI (Feature Class)",
            name="city_aoi",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input"
        )
        p0.value = str(Default_AOI)
        p0.parameterType = "Required"
        p0.enabled = False 
        
        # Comma-separated list of years to analyze
        param_years = arcpy.Parameter(
            displayName="Input Timeframe to Analyze (comma-separated, e.g. 2001,2006,2011,2016,2021)",
            name="years_csv",
            datatype="GPString",
            parameterType="Required",
            direction="Input"
        )

        # Optional city name to filter AOI
        param_cityname = arcpy.Parameter(
            displayName="City Name to Filter AOI, e.g. Ames, Ankeny",
            name="city_name",
            datatype="GPString",
            parameterType="Optional",
            direction="Input"
        )

        return [p0, param_years, param_cityname]

    def isLicensed(self):
        return True

    def execute(self, parameters, messages):
        """
        Entry point when the tool is run in ArcGIS Pro
        Reads GUI parameters, constructs the configuration dictionary,
        and calls run_change_analysis()
        """
        try:

            param_years    = parameters[1]   # "Input Timeframe to Analyze"
            param_cityname = parameters[2]   # "City Name to Filter AOI"

            # Project root is one level above this .pyt
            project_root = Path(__file__).resolve().parent.parent

            years_text = (param_years.valueAsText or "").strip()
            if not years_text:
                raise arcpy.ExecuteError("You must provide at least two years (e.g. 2001,2006).")

            years = [int(y.strip()) for y in years_text.split(",") if y.strip()]
            if len(years) < 2:
                raise arcpy.ExecuteError("Need at least two years to compute change (e.g. 2001,2006).")

            # Internal configuration used by the workflow
            cfg = {
                "city_aoi": "data/boundaries/City.shp",
                "years": years,
                # Path pattern for NLCD impervious rasters (0–100% impervious)
                "nlcd_imperv_pattern": (
                    r"data/NLCD_FctImp/Annual_NLCD_FctImp_{year}_CU_C1V1/"
                    r"Annual_NLCD_FctImp_{year}_CU_C1V1.tif"
                ),
                
                # Optional (not used yet) pattern for NLCD landcover rasters
                "nlcd_landcover_pattern": (
                    r"data/NLCD_LndCov/Annual_NLCD_LndCov_{year}_CU_C1V1.tif"
                ),
                "city_name": None,
                "overwrite": True,
                "output": {
                    "csv_folder": "outputs/csv",
                    "log_folder": "outputs/logs",
                    "gdb": "outputs/Imperv_change.gdb",
                    "create_folders_if_missing": True,
                    "create_gdb_if_missing": True
                }
            }
            log(f"Using internal config; years = {years}")

            # city name
            if param_cityname.value:
                cfg["city_name"] = param_cityname.valueAsText
                log(f"Filtering AOI to city: {cfg['city_name']}")
            else:
                cfg["city_name"] = None

            run_change_analysis(cfg, project_root)

        except Exception as e:
            
            # Log error and re-raise so ArcGIS flags the tool as failed
            log_err(f"Tool failed: {e}")
            raise