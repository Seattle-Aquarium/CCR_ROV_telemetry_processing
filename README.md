# CCR ROV telemetry processing

## Overview

This repository contains code and files to organize information regarding the analysis and visualization of ROV telemetry information. 
Our overarching objective here is to provide an open-source location in which we store code and resources necessary for other entities or individuals to reproduce our ROV telemetry and sensor file management and AI image analyses. 


### Other CCR GitHub repositories
```mermaid

graph TD

A["<a href='https://github.com/Seattle-Aquarium/Coastal_Climate_Resilience' target='_blank' style='font-size: 16px; font-weight: bold;'>Coastal_Climate_Resilience</a><br><font color='darkgray' style='text-decoration: none;'> the main landing pad for the CCR research program</font>"]

A --> B["<a href='https://github.com/Seattle-Aquarium/CCR_analytical_resources' target='_blank' style='font-size: 16px; font-weight: bold;'>CCR_ROV_telemetry_processing</a><br><font color='darkgray' style='text-decoration: none;'> (this page) contains code, analytical tools, and data</font>"]

A --> C["<a href='https://github.com/Seattle-Aquarium/CCR_benthic_analyses' target='_blank' style='font-size: 16px; font-weight: bold;'>CCR_benthic_analyses</a><br><font color='darkgray' style='text-decoration: none;'>code to analyze ROV survey data</font>"]

A --> D["<a href='https://github.com/Seattle-Aquarium/CCR_development' target='_blank' style='font-size: 16px; font-weight: bold;'>CCR_development</a><br><font color='darkgray' style='text-decoration: none;'>repo for active software projects and Issues</font>"]

A --> E["<a href='https://github.com/Seattle-Aquarium/CCR_benthic_taxa_simulation' target='_blank' style='font-size: 16px; font-weight: bold;'>CCR_benthic_taxa_simulation</a><br><font color='darkgray' style='text-decoration: none;'>code to simulate ROV survey data</font>"]

style B stroke:#00B2EE,stroke-width:4px

```


## Telemetry processing

### Code 
* `tlog_csv_no_EKF.py`: This script processes telemetry `.tlog` files from BlueOS when there is no fusion between the GPS and Doppler Velocity Log (DVL). It extracts relevant fields (e.g., time, date, GPS latitude/longitude, DVLx, DVLy (`LOCAL_POSITION_NED`), altitude, depth, heading) and averages values per second. Additionally, it calculates DVL-based latitude and longitude (`DVLlat`, `DVLlon`) from DVLx and DVLy movements and estimates the width (m) and area (m²) captured by GoPro images based on the ROV's altitude. If the survey start and end times are known, they can be specified when running the script; otherwise, the entire `.tlog` file will be processed.

* `tlog_to_csv_EKF.py`: This script processes `.tlog` files when GPS and DVL data are fused via an Extended Kalman Filter (EKF), producing more accurate tracks than using GPS or DVL alone. Instead of calculating `DVLlat`/`DVLlon`, this script incorporates the fused position data (`GLOBAL_POSITION_INT`) for improved accuracy.
<p align="center">
  <img src="figures/survey_params.png" width="600", height="200" /> 
</p>

* `transect_map.py`: This script generates a Leaflet map displaying the ROV tracks as measured by different navigation sources: GPS (black), DVL (blue), and EKF (red), which can then be incorporated into broader maps, as depicted below for the Urban Kelp Research Project with the Port of Seattle 
<p align="center">
  <img src="figures/GPS_EKF_tracks.jpg" width="300", height="300" /> 
</p>

<p align="center">
  <img src="figures/Port_2425_map.png" width="450", height="600"/>
</p>

---

### Get Involved! 
More information about our desired future functionality can be found at [Seattle_Aquarium_CCR_development](https://github.com/Seattle-Aquarium/CCR_development/tree/main), specifically at the 1-page project descriptions [KelpNet](https://github.com/Seattle-Aquarium/CCR_development/blob/main/1-pagers/KelpNet.md) and [bull_kelp_tracking](https://github.com/Seattle-Aquarium/CCR_development/blob/main/1-pagers/bull_kelp_tracking.md)
