NLCD Impervious Surface Change Analysis

CRP 556 Final Project
Kolton Eisma
Keisma@iastate.edu

--------------------------------------------------------------------------------------
Overview
--------------------------------------------------------------------------------------

This project is an ArcGIS Pro Python Toolbox that automates the analysis and mapping of impervious surface change for cities using NLCD Impervious Surface raster data.
The workflow clips NLCD rasters to a city boundary, computes change between years, classifies change magnitude, and exports maps and CSV summaries.

--------------------------------------------------------------------------------------
Folder Structure
--------------------------------------------------------------------------------------

CRP_556_Final/
├── src/
│   └── NLCD_Imperv_Change.pyt
├── data/
│   └── boundaries/
├── README.md
└── .gitignore

-------------------------------------------------------------------------------------
Data & ArcGIS Project Files (Hosted Externally 
-------------------------------------------------------------------------------------

The ArcGIS Pro project file and large supporting datasets are hosted on Box due to GitHub file size limits.

Box download link: https://iastate.box.com/s/3ep9e483br15tx05yr4i8el17fnv31iu

Instructions:
1. Download the Box folder (or access it via Box Drive).
2. Keep the folder structure intact.
3. Open `CRP_556_Final.aprx` in ArcGIS Pro.
4. Add the Python toolbox (`NLCD_Imperv_Change.pyt`) from the `src/` folder if it is not already loaded.
5. Run the tool **Run NLCD Impervious Change Analysis**.

NLCD Impervious Surface Data (Not included in GitHub)
NLCD impervious surface rasters are not stored in this GitHub repository due to file size.

They can be downloaded from the official MRLC/NLCD website: https://www.mrlc.gov/

The toolbox expects NLCD impervious rasters following this naming pattern:
Annual_NLCD_FctImp_{year}_CU_C1V1.tif

--------------------------------------------------------------------------------------
Programs and How to Run
--------------------------------------------------------------------------------------

Program: NLCD_Imperv_Change.pyt** (ArcGIS Pro Python Toolbox)

Tool to run: Run NLCD Impervious Change Analysis**

There is only one program and one tool. No other scripts need to be run before or after.


--------------------------------------------------------------------------------------
Tool Arguments (Parameters)
--------------------------------------------------------------------------------------

When running the tool in ArcGIS Pro, provide the following:

1. **City AOI (Feature Class)**  
   Boundary shapefile or feature class for the study area.

2. **Years (comma-separated)**  
   Example: "2001,2006,2011,2016,2021"

3. **City Name to Filter AOI (optional)**  
   Used only if the AOI contains multiple cities (e.g., “Ames”).

Outputs
- PNG maps of impervious surface change
- CSV summaries of pixel counts and percentages by change class

--------------------------------------------------------------------------------------
How to Run
--------------------------------------------------------------------------------------

1. Open CRP_556_Final.aprx in ArcGIS Pro
2. Add the toolbox (NLCD_Imperv_Change.pyt) if not already loaded
3. Select "Run NLCD Impervious Change Analysis"
	Provide required inputs (any combination of year pairs, 2001,2006 or 2001,2006,2011, or for all pairs 2001,2006,2011,2016,2021
	Outputs are generated automatically and put into outputs/maps

--------------------------------------------------------------------------------------
Runtime Notes
--------------------------------------------------------------------------------------

Typical runtime: 1–5 minutes per city, depending on raster size and number of years

Large AOIs or many year pairs may take longer

--------------------------------------------------------------------------------------
Notes for Grading
--------------------------------------------------------------------------------------

All code is contained in src/
Input data included (excluding large NLCD rasters if needed)
Project opens directly in ArcGIS Pro and runs without modification

--------------------------------------------------------------------------------------
Workflow:
--------------------------------------------------------------------------------------

1. Clip each NLCD raster to the City AOI
2. Compute impervious surface change (after - before)
3. Classify change into 5 categories
	(-100 to -50%) Large Decrease
	(-50 to -10%) Moderate Decrease
        (-10% to +10%) No Change
        (+10 to +50%) Moderate Increase 
        (+50 to 100%) Large Increase
• Export change histograms to CSV
• Export map PNGs for each pair and net 20-year change using a template APRX

--------------------------------------------------------------------------------------
Classification of Impervious Change
--------------------------------------------------------------------------------------

1. Large Decrease (−100 to −50%)
	This class captures substantial reductions in impervious surface, such as demolition of paved areas, 
removal of parking lots, redevelopment that introduces green space, or natural reforestation of previously developed land. 
A loss greater than 50 percentage points signals a significant shift toward more permeable land cover.

2. Moderate Decrease (−50 to −10%)
	Pixels in this range indicate smaller but still notable decreases in imperviousness—examples might include partial redevelopment, 
removal of structures, transitions to lower-density land uses, or improvements in vegetation cover around built environments. 
These changes may represent localized de-urbanization or land reclamation efforts.

3. No or Minimal Change (−10 to +10%)
	This category identifies areas that remained essentially stable across the time interval. 
Impervious percentages within ±10 percentage points are typically considered 
background noise associated with NLCD classification methods or natural minor variability. 
These pixels signify land uses where development intensity did not meaningfully change.

4. Moderate Increase (+10 to +50%)
	Pixels showing a moderate increase in imperviousness correspond to gradual or incremental development, 
such as new home construction within existing neighborhoods, expansion of streets or driveways, small commercial additions, or infill development. 
These areas indicate ongoing but not dramatic urban intensification.

5. Large Increase (+50 to +100%)
	This category identifies the most substantial urban growth, where pixels transitioned from largely pervious (e.g., farmland or grassland) 
to highly impervious surfaces, typically associated with new subdivisions, commercial centers, industrial sites, or major infrastructure installations. 
It is the clearest signature of land conversion and urban expansion.