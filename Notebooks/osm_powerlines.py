# ============================================================
# Imports
# ============================================================

from __future__ import annotations

import html
import json
import math
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


# ============================================================
# User Settings
# ============================================================

ROOT_DIR = Path.home() / "Desktop" / "OSM_Texas_Powerlines"

DATA_DIR = ROOT_DIR / "data"
OUTPUT_DIR = ROOT_DIR / "outputs"

RAW_OSM_PBF_PATH = DATA_DIR / "texas-latest.osm.pbf"

POWERLINES_PBF_PATH = OUTPUT_DIR / "texas_powerlines.osm.pbf"
SUBSTATIONS_PBF_PATH = OUTPUT_DIR / "texas_substations.osm.pbf"

RAW_KML_PATH = OUTPUT_DIR / "texas_powerlines_raw.kml"
SUBSTATIONS_GEOJSON_PATH = OUTPUT_DIR / "texas_substations.geojson"

ORGANIZED_KML_PATH = OUTPUT_DIR / "texas_powerlines_by_voltage_with_substations.kml"
ORGANIZED_KMZ_PATH = OUTPUT_DIR / "texas_powerlines_by_voltage_with_substations.kmz"

CREATE_KMZ = True

INCLUDE_UNDERGROUND_CABLES = False
INCLUDE_PLANNED_OR_CONSTRUCTION = False

INCLUDE_UNNAMED_SUBSTATIONS = True
DEDUPLICATE_SUBSTATIONS_BY_NAME = True
DEDUPLICATE_SUBSTATIONS_BY_DISTANCE = True

# Distance-only duplicate check.
# Increase to 1500 if Google Earth still shows repeated nearby pins.
SUBSTATION_DEDUPE_DISTANCE_FT = 150

# Same-name duplicate check.
# Same normalized name within this distance is treated as duplicate.
SUBSTATION_SAME_NAME_DEDUPE_DISTANCE_FT = 5280.0

VOLTAGE_FOLDERS = [
    "<100 V",
    "100-161",
    "220-287",
    "345",
    "500",
    ">=735",
    "Unknown",
]

SUBSTATION_FOLDER_NAME = "Substations"


# ============================================================
# Helper Functions
# ============================================================

def make_directories(
        *,
        directories: list[Path],
) -> None:
    """
    Create required project directories.

    Parameters
    ----------
    directories : list[Path]
        Directories to create.

    Returns
    -------
    None
    """

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)


def check_command_exists(
        *,
        command_name: str,
) -> None:
    """
    Check that a command-line tool is available.

    Parameters
    ----------
    command_name : str
        Command-line executable name.

    Returns
    -------
    None

    Raises
    ------
    RuntimeError
        If the command-line tool is not available.
    """

    if shutil.which(command_name) is None:
        raise RuntimeError(
            f"Required command not found: {command_name!r}. "
            f"Install it before running this script."
        )


def check_input_file_exists(
        *,
        input_pbf_path: Path,
) -> None:
    """
    Check that the downloaded OSM PBF file exists.

    Parameters
    ----------
    input_pbf_path : Path
        Input OSM PBF path.

    Returns
    -------
    None

    Raises
    ------
    FileNotFoundError
        If the input OSM PBF file does not exist.
    """

    if not input_pbf_path.exists():
        raise FileNotFoundError(
            f"OSM PBF file was not found:\n"
            f"{input_pbf_path}\n\n"
            f"Move your downloaded texas-latest.osm.pbf file to this location, "
            f"or update RAW_OSM_PBF_PATH in the settings section."
        )

    print(f"Using existing OSM PBF file: {input_pbf_path}")


def build_powerline_filters(
        *,
        include_underground_cables: bool,
        include_planned_or_construction: bool,
) -> list[str]:
    """
    Build Osmium filter expressions for OSM powerline features.

    Parameters
    ----------
    include_underground_cables : bool
        Whether to include ``power=cable`` ways.
    include_planned_or_construction : bool
        Whether to include proposed or construction powerline features.

    Returns
    -------
    list[str]
        Osmium tag filter expressions.
    """

    filters = [
        "w/power=line",
        "w/power=minor_line",
    ]

    if include_underground_cables:
        filters.append("w/power=cable")

    if include_planned_or_construction:
        filters.extend(
            [
                "w/construction:power=line",
                "w/construction:power=minor_line",
                "w/construction:power=cable",
                "w/proposed:power=line",
                "w/proposed:power=minor_line",
                "w/proposed:power=cable",
            ]
        )

    return filters


def build_substation_filters() -> list[str]:
    """
    Build Osmium filter expressions for OSM substations.

    Returns
    -------
    list[str]
        Osmium tag filter expressions.
    """

    return [
        "n/power=substation",
        "w/power=substation",
        "r/power=substation",
    ]


def filter_osm_with_osmium(
        *,
        input_pbf_path: Path,
        output_pbf_path: Path,
        filter_expressions: list[str],
        description: str,
) -> None:
    """
    Filter OSM PBF data using Osmium.

    Parameters
    ----------
    input_pbf_path : Path
        Input OSM PBF file.
    output_pbf_path : Path
        Filtered output OSM PBF file.
    filter_expressions : list[str]
        Osmium tag filter expressions.
    description : str
        Description printed to terminal.

    Returns
    -------
    None
    """

    output_pbf_path.parent.mkdir(parents=True, exist_ok=True)

    if output_pbf_path.exists():
        output_pbf_path.unlink()

    command = [
        "osmium",
        "tags-filter",
        "--overwrite",
        "-o",
        str(output_pbf_path),
        str(input_pbf_path),
        *filter_expressions,
    ]

    print(f"Running Osmium filter for {description}:")
    print(" ".join(command))

    subprocess.run(command, check=True)

    print(f"Filtered PBF created: {output_pbf_path}")


def convert_pbf_to_raw_kml(
        *,
        input_pbf_path: Path,
        output_kml_path: Path,
) -> None:
    """
    Convert filtered OSM PBF line features to raw KML.

    Parameters
    ----------
    input_pbf_path : Path
        Filtered OSM PBF file.
    output_kml_path : Path
        Output raw KML path.

    Returns
    -------
    None
    """

    if output_kml_path.exists():
        output_kml_path.unlink()

    command = [
        "ogr2ogr",
        "-f",
        "KML",
        str(output_kml_path),
        str(input_pbf_path),
        "lines",
        "-t_srs",
        "EPSG:4326",
        "-nln",
        "Powerlines",
    ]

    print("Converting filtered powerline PBF to raw KML:")
    print(" ".join(command))

    subprocess.run(command, check=True)

    print(f"Raw KML created: {output_kml_path}")


def export_pbf_to_geojson_with_osmium(
        *,
        input_pbf_path: Path,
        output_geojson_path: Path,
        description: str,
) -> None:
    """
    Export filtered OSM PBF data to GeoJSON using Osmium.

    Parameters
    ----------
    input_pbf_path : Path
        Input OSM PBF file.
    output_geojson_path : Path
        Output GeoJSON path.
    description : str
        Description printed to terminal.

    Returns
    -------
    None
    """

    if output_geojson_path.exists():
        output_geojson_path.unlink()

    command = [
        "osmium",
        "export",
        str(input_pbf_path),
        "-o",
        str(output_geojson_path),
        "-f",
        "geojson",
        "-O",
    ]

    print(f"Exporting {description} to GeoJSON:")
    print(" ".join(command))

    subprocess.run(command, check=True)

    print(f"GeoJSON created: {output_geojson_path}")


def get_xml_local_name(
        *,
        element: ET.Element,
) -> str:
    """
    Return XML tag name without namespace.

    Parameters
    ----------
    element : ET.Element
        XML element.

    Returns
    -------
    str
        Local XML tag name.
    """

    return element.tag.split("}", 1)[-1]


def extract_kml_text_property(
        *,
        placemark: ET.Element,
        property_name: str,
) -> str | None:
    """
    Extract a text property from a KML Placemark.

    Parameters
    ----------
    placemark : ET.Element
        KML Placemark element.
    property_name : str
        Property name to extract.

    Returns
    -------
    str | None
        Extracted property value, if found.
    """

    for element in placemark.iter():
        element_name = get_xml_local_name(
            element=element,
        )

        data_name = element.attrib.get("name")

        if data_name != property_name:
            continue

        if element_name == "SimpleData" and element.text:
            return element.text.strip()

        if element_name == "Data":
            for child_element in element:
                child_name = get_xml_local_name(
                    element=child_element,
                )

                if child_name == "value" and child_element.text:
                    return child_element.text.strip()

    text_parts = []

    for element in placemark.iter():
        if element.text:
            text_parts.append(element.text)

        if element.tail:
            text_parts.append(element.tail)

        for attribute_value in element.attrib.values():
            if attribute_value:
                text_parts.append(attribute_value)

    placemark_text = html.unescape(" ".join(text_parts))

    placemark_text = (
        placemark_text
        .replace("&quot;", '"')
        .replace("&apos;", "'")
        .replace("&gt;", ">")
        .replace("&lt;", "<")
        .replace("\n", " ")
        .replace("\r", " ")
    )

    other_tags_patterns = [
        rf'"{re.escape(property_name)}"\s*=>\s*"([^"]+)"',
        rf"'{re.escape(property_name)}'\s*=>\s*'([^']+)'",
        rf'"{re.escape(property_name)}"\s*=>\s*' + r"'([^']+)'",
        rf"'{re.escape(property_name)}'\s*=>\s*" + r'"([^"]+)"',
    ]

    for pattern in other_tags_patterns:
        match = re.search(pattern, placemark_text, flags=re.IGNORECASE)

        if match:
            return match.group(1).strip()

    html_table_patterns = [
        rf"<td[^>]*>\s*{re.escape(property_name)}\s*</td>\s*<td[^>]*>\s*([^<]+)\s*</td>",
        rf"<th[^>]*>\s*{re.escape(property_name)}\s*</th>\s*<td[^>]*>\s*([^<]+)\s*</td>",
    ]

    for pattern in html_table_patterns:
        match = re.search(pattern, placemark_text, flags=re.IGNORECASE)

        if match:
            return match.group(1).strip()

    plain_text_patterns = [
        rf"\b{re.escape(property_name)}\b\s*[:=]\s*([0-9][0-9.,;/\s]*(?:kv|kV|KV|v|V)?)",
        rf"\b{re.escape(property_name)}\b\s+([0-9][0-9.,;/\s]*(?:kv|kV|KV|v|V)?)",
    ]

    for pattern in plain_text_patterns:
        match = re.search(pattern, placemark_text, flags=re.IGNORECASE)

        if match:
            return match.group(1).strip()

    return None


def parse_voltage_to_max_kv(
        *,
        voltage_text: str | None,
) -> float | None:
    """
    Parse an OSM voltage tag and return the maximum voltage in kV.

    Parameters
    ----------
    voltage_text : str | None
        OSM voltage text.

    Returns
    -------
    float | None
        Maximum voltage in kV.
    """

    if not voltage_text:
        return None

    voltage_text_clean = voltage_text.lower().replace(",", "")

    number_matches = re.findall(r"\d+(?:\.\d+)?", voltage_text_clean)

    if not number_matches:
        return None

    voltage_values_kv = []

    for number_text in number_matches:
        voltage_value = float(number_text)

        if voltage_value <= 0:
            continue

        if voltage_value >= 1000:
            voltage_value_kv = voltage_value / 1000
        else:
            voltage_value_kv = voltage_value

        voltage_values_kv.append(voltage_value_kv)

    if not voltage_values_kv:
        return None

    return max(voltage_values_kv)


def assign_voltage_folder(
        *,
        voltage_kv: float | None,
) -> str:
    """
    Assign a voltage value to a folder name.

    Parameters
    ----------
    voltage_kv : float | None
        Voltage in kV.

    Returns
    -------
    str
        Voltage folder name.
    """

    if voltage_kv is None:
        return "Unknown"

    if voltage_kv < 100:
        return "<100 V"

    if 100 <= voltage_kv <= 161:
        return "100-161"

    if 220 <= voltage_kv <= 287:
        return "220-287"

    if 300 <= voltage_kv < 400:
        return "345"

    if 400 <= voltage_kv < 600:
        return "500"

    if voltage_kv >= 735:
        return ">=735"

    return "Unknown"


def get_geojson_property_value(
        *,
        properties: dict,
        property_name: str,
) -> str | None:
    """
    Get a property value from GeoJSON properties.

    Parameters
    ----------
    properties : dict
        GeoJSON feature properties.
    property_name : str
        Property name to retrieve.

    Returns
    -------
    str | None
        Property value.
    """

    if property_name in properties and properties[property_name] is not None:
        return str(properties[property_name]).strip()

    tags = properties.get("tags")

    if isinstance(tags, dict):
        value = tags.get(property_name)

        if value is not None:
            return str(value).strip()

    return None


def normalize_substation_name(
        *,
        name: str,
) -> str:
    """
    Normalize substation name for duplicate checking.

    Parameters
    ----------
    name : str
        Raw substation name.

    Returns
    -------
    str
        Normalized substation name.
    """

    normalized_name = name.lower().strip()

    normalized_name = re.sub(r"\bsubstation\b", "", normalized_name)
    normalized_name = re.sub(r"\bswitching station\b", "", normalized_name)
    normalized_name = re.sub(r"\bswitchyard\b", "", normalized_name)
    normalized_name = re.sub(r"\bstation\b", "", normalized_name)
    normalized_name = re.sub(r"[^a-z0-9]+", " ", normalized_name)
    normalized_name = re.sub(r"\s+", " ", normalized_name).strip()

    return normalized_name


def flatten_coordinates(
        *,
        coordinates,
) -> list[list[float]]:
    """
    Flatten nested GeoJSON coordinates into coordinate pairs.

    Parameters
    ----------
    coordinates
        GeoJSON coordinates.

    Returns
    -------
    list[list[float]]
        Flattened coordinate list.
    """

    if not isinstance(coordinates, list):
        return []

    if len(coordinates) >= 2 and all(isinstance(value, (int, float)) for value in coordinates[:2]):
        return [coordinates]

    flattened_coordinates = []

    for item in coordinates:
        flattened_coordinates.extend(
            flatten_coordinates(
                coordinates=item,
            )
        )

    return flattened_coordinates


def polygon_ring_area_and_centroid(
        *,
        ring: list[list[float]],
) -> tuple[float, float, float]:
    """
    Calculate approximate planar area and centroid of a polygon ring.

    Parameters
    ----------
    ring : list[list[float]]
        Polygon ring coordinates.

    Returns
    -------
    tuple[float, float, float]
        Area, centroid longitude, centroid latitude.
    """

    if len(ring) < 3:
        return 0.0, 0.0, 0.0

    area_sum = 0.0
    centroid_lon_sum = 0.0
    centroid_lat_sum = 0.0

    for index in range(len(ring) - 1):
        lon_1 = ring[index][0]
        lat_1 = ring[index][1]
        lon_2 = ring[index + 1][0]
        lat_2 = ring[index + 1][1]

        cross_product = lon_1 * lat_2 - lon_2 * lat_1

        area_sum += cross_product
        centroid_lon_sum += (lon_1 + lon_2) * cross_product
        centroid_lat_sum += (lat_1 + lat_2) * cross_product

    area = area_sum / 2.0

    if math.isclose(area, 0.0):
        return 0.0, 0.0, 0.0

    centroid_lon = centroid_lon_sum / (6.0 * area)
    centroid_lat = centroid_lat_sum / (6.0 * area)

    return abs(area), centroid_lon, centroid_lat


def get_geometry_label_point(
        *,
        geometry: dict,
) -> tuple[float, float] | None:
    """
    Get a representative point for a GeoJSON geometry.

    Parameters
    ----------
    geometry : dict
        GeoJSON geometry.

    Returns
    -------
    tuple[float, float] | None
        Longitude and latitude.
    """

    if not geometry:
        return None

    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")

    if geometry_type == "Point" and coordinates:
        return coordinates[0], coordinates[1]

    if geometry_type == "Polygon" and coordinates:
        outer_ring = coordinates[0]
        area, centroid_lon, centroid_lat = polygon_ring_area_and_centroid(
            ring=outer_ring,
        )

        if area > 0:
            return centroid_lon, centroid_lat

    if geometry_type == "MultiPolygon" and coordinates:
        weighted_lon_sum = 0.0
        weighted_lat_sum = 0.0
        total_area = 0.0

        for polygon in coordinates:
            if not polygon:
                continue

            outer_ring = polygon[0]
            area, centroid_lon, centroid_lat = polygon_ring_area_and_centroid(
                ring=outer_ring,
            )

            if area <= 0:
                continue

            weighted_lon_sum += centroid_lon * area
            weighted_lat_sum += centroid_lat * area
            total_area += area

        if total_area > 0:
            return weighted_lon_sum / total_area, weighted_lat_sum / total_area

    flattened_coordinates = flatten_coordinates(
        coordinates=coordinates,
    )

    if not flattened_coordinates:
        return None

    lon_values = [
        coordinate[0]
        for coordinate in flattened_coordinates
        if len(coordinate) >= 2
    ]

    lat_values = [
        coordinate[1]
        for coordinate in flattened_coordinates
        if len(coordinate) >= 2
    ]

    if not lon_values or not lat_values:
        return None

    return sum(lon_values) / len(lon_values), sum(lat_values) / len(lat_values)


def calculate_distance_ft(
        *,
        lon_1: float,
        lat_1: float,
        lon_2: float,
        lat_2: float,
) -> float:
    """
    Calculate approximate horizontal distance between two lon/lat points in feet.

    Parameters
    ----------
    lon_1 : float
        First longitude.
    lat_1 : float
        First latitude.
    lon_2 : float
        Second longitude.
    lat_2 : float
        Second latitude.

    Returns
    -------
    float
        Approximate distance in feet.
    """

    feet_per_degree_lat = 364000.0
    average_lat_rad = math.radians((lat_1 + lat_2) / 2.0)
    feet_per_degree_lon = feet_per_degree_lat * math.cos(average_lat_rad)

    delta_lon_ft = (lon_2 - lon_1) * feet_per_degree_lon
    delta_lat_ft = (lat_2 - lat_1) * feet_per_degree_lat

    return math.hypot(delta_lon_ft, delta_lat_ft)


def build_substation_label(
        *,
        properties: dict,
) -> tuple[str | None, bool]:
    """
    Build substation label text.

    Parameters
    ----------
    properties : dict
        GeoJSON feature properties.

    Returns
    -------
    tuple[str | None, bool]
        Substation label and whether it has a real OSM name.
    """

    name = get_geojson_property_value(
        properties=properties,
        property_name="name",
    )

    if name:
        return name, True

    if INCLUDE_UNNAMED_SUBSTATIONS:
        return "Unnamed Substation", False

    return None, False


def create_kml_text_element(
        *,
        parent: ET.Element,
        tag_name: str,
        text_value: str,
) -> ET.Element:
    """
    Create a KML text element.

    Parameters
    ----------
    parent : ET.Element
        Parent XML element.
    tag_name : str
        KML tag name.
    text_value : str
        Text value.

    Returns
    -------
    ET.Element
        Created XML element.
    """

    element = ET.SubElement(parent, f"{{http://www.opengis.net/kml/2.2}}{tag_name}")
    element.text = text_value

    return element


def add_substation_style(
        *,
        document_element: ET.Element,
) -> None:
    """
    Add substation pin style to KML document.

    Parameters
    ----------
    document_element : ET.Element
        KML Document element.

    Returns
    -------
    None
    """

    style_element = ET.SubElement(
        document_element,
        "{http://www.opengis.net/kml/2.2}Style",
        id="substation_pin_style",
    )

    icon_style_element = ET.SubElement(
        style_element,
        "{http://www.opengis.net/kml/2.2}IconStyle",
    )

    create_kml_text_element(
        parent=icon_style_element,
        tag_name="scale",
        text_value="1.0",
    )

    icon_element = ET.SubElement(
        icon_style_element,
        "{http://www.opengis.net/kml/2.2}Icon",
    )

    create_kml_text_element(
        parent=icon_element,
        tag_name="href",
        text_value="http://maps.google.com/mapfiles/kml/pushpin/ylw-pushpin.png",
    )

    label_style_element = ET.SubElement(
        style_element,
        "{http://www.opengis.net/kml/2.2}LabelStyle",
    )

    create_kml_text_element(
        parent=label_style_element,
        tag_name="scale",
        text_value="0.85",
    )


def add_extended_data_to_placemark(
        *,
        placemark_element: ET.Element,
        properties: dict,
) -> None:
    """
    Add properties to KML placemark ExtendedData.

    Parameters
    ----------
    placemark_element : ET.Element
        KML Placemark element.
    properties : dict
        Feature properties.

    Returns
    -------
    None
    """

    if not properties:
        return

    extended_data_element = ET.SubElement(
        placemark_element,
        "{http://www.opengis.net/kml/2.2}ExtendedData",
    )

    for property_name, property_value in sorted(properties.items()):
        if property_value is None:
            continue

        data_element = ET.SubElement(
            extended_data_element,
            "{http://www.opengis.net/kml/2.2}Data",
            name=str(property_name),
        )

        value_element = ET.SubElement(
            data_element,
            "{http://www.opengis.net/kml/2.2}value",
        )

        value_element.text = str(property_value)


def is_duplicate_by_distance(
        *,
        lon: float,
        lat: float,
        accepted_substations: list[dict],
        dedupe_distance_ft: float,
) -> bool:
    """
    Check whether a substation is a duplicate by distance.

    Parameters
    ----------
    lon : float
        Candidate longitude.
    lat : float
        Candidate latitude.
    accepted_substations : list[dict]
        Accepted substation records.
    dedupe_distance_ft : float
        Duplicate distance threshold in feet.

    Returns
    -------
    bool
        True if duplicate.
    """

    for accepted_substation in accepted_substations:
        distance_ft = calculate_distance_ft(
            lon_1=lon,
            lat_1=lat,
            lon_2=accepted_substation["lon"],
            lat_2=accepted_substation["lat"],
        )

        if distance_ft <= dedupe_distance_ft:
            return True

    return False


def is_duplicate_by_name(
        *,
        normalized_name: str,
        lon: float,
        lat: float,
        accepted_substations: list[dict],
        dedupe_distance_ft: float,
) -> bool:
    """
    Check whether a substation is a duplicate by normalized name and distance.

    Parameters
    ----------
    normalized_name : str
        Candidate normalized name.
    lon : float
        Candidate longitude.
    lat : float
        Candidate latitude.
    accepted_substations : list[dict]
        Accepted substation records.
    dedupe_distance_ft : float
        Duplicate distance threshold in feet.

    Returns
    -------
    bool
        True if duplicate.
    """

    for accepted_substation in accepted_substations:
        if accepted_substation["normalized_name"] != normalized_name:
            continue

        distance_ft = calculate_distance_ft(
            lon_1=lon,
            lat_1=lat,
            lon_2=accepted_substation["lon"],
            lat_2=accepted_substation["lat"],
        )

        if distance_ft <= dedupe_distance_ft:
            return True

    return False


def add_substations_folder(
        *,
        document_element: ET.Element,
        substation_geojson_path: Path,
) -> None:
    """
    Add substations folder with labeled pin placemarks.

    Named substations are prioritized over unnamed substations during duplicate
    removal. If a named and unnamed substation are within the dedupe distance,
    the named substation is kept and the unnamed one is skipped.

    Parameters
    ----------
    document_element : ET.Element
        KML Document element.
    substation_geojson_path : Path
        Substations GeoJSON path.

    Returns
    -------
    None
    """

    folder_element = ET.SubElement(
        document_element,
        "{http://www.opengis.net/kml/2.2}Folder",
    )

    create_kml_text_element(
        parent=folder_element,
        tag_name="name",
        text_value=SUBSTATION_FOLDER_NAME,
    )

    if not substation_geojson_path.exists():
        print("Substation GeoJSON was not found. Skipping substation folder.")
        return

    with substation_geojson_path.open("r", encoding="utf-8") as file:
        geojson_data = json.load(file)

    features = geojson_data.get("features", [])

    substation_candidates = []

    skipped_unnamed_count = 0
    skipped_geometry_count = 0

    for feature in features:
        properties = feature.get("properties", {})
        geometry = feature.get("geometry", {})

        substation_label, has_real_name = build_substation_label(
            properties=properties,
        )

        if substation_label is None:
            skipped_unnamed_count += 1
            continue

        label_point = get_geometry_label_point(
            geometry=geometry,
        )

        if label_point is None:
            skipped_geometry_count += 1
            continue

        lon, lat = label_point

        normalized_name = normalize_substation_name(
            name=substation_label,
        )

        substation_candidates.append(
            {
                "feature": feature,
                "properties": properties,
                "geometry": geometry,
                "label": substation_label,
                "has_real_name": has_real_name,
                "normalized_name": normalized_name,
                "lon": lon,
                "lat": lat,
            }
        )

    # Named substations are processed first.
    # This means unnamed substations get trimmed first when they are near named ones.
    substation_candidates.sort(
        key=lambda candidate: (
            not candidate["has_real_name"],
            candidate["label"],
        )
    )

    accepted_substations: list[dict] = []

    added_count = 0
    skipped_duplicate_name_count = 0
    skipped_duplicate_distance_count = 0

    for candidate in substation_candidates:
        substation_label = candidate["label"]
        has_real_name = candidate["has_real_name"]
        normalized_name = candidate["normalized_name"]
        lon = candidate["lon"]
        lat = candidate["lat"]
        properties = candidate["properties"]

        if DEDUPLICATE_SUBSTATIONS_BY_NAME and has_real_name:
            duplicate_by_name = is_duplicate_by_name(
                normalized_name=normalized_name,
                lon=lon,
                lat=lat,
                accepted_substations=accepted_substations,
                dedupe_distance_ft=SUBSTATION_SAME_NAME_DEDUPE_DISTANCE_FT,
            )

            if duplicate_by_name:
                skipped_duplicate_name_count += 1
                continue

        if DEDUPLICATE_SUBSTATIONS_BY_DISTANCE:
            duplicate_by_distance = is_duplicate_by_distance(
                lon=lon,
                lat=lat,
                accepted_substations=accepted_substations,
                dedupe_distance_ft=SUBSTATION_DEDUPE_DISTANCE_FT,
            )

            if duplicate_by_distance:
                skipped_duplicate_distance_count += 1
                continue

        accepted_substations.append(
            {
                "name": substation_label,
                "has_real_name": has_real_name,
                "normalized_name": normalized_name,
                "lon": lon,
                "lat": lat,
            }
        )

        placemark_element = ET.SubElement(
            folder_element,
            "{http://www.opengis.net/kml/2.2}Placemark",
        )

        create_kml_text_element(
            parent=placemark_element,
            tag_name="name",
            text_value=substation_label,
        )

        create_kml_text_element(
            parent=placemark_element,
            tag_name="styleUrl",
            text_value="#substation_pin_style",
        )

        add_extended_data_to_placemark(
            placemark_element=placemark_element,
            properties=properties,
        )

        point_element = ET.SubElement(
            placemark_element,
            "{http://www.opengis.net/kml/2.2}Point",
        )

        create_kml_text_element(
            parent=point_element,
            tag_name="coordinates",
            text_value=f"{lon},{lat},0",
        )

        added_count += 1

    print(f"  {SUBSTATION_FOLDER_NAME}: {added_count:,}")
    print(f"  Skipped unnamed substations: {skipped_unnamed_count:,}")
    print(f"  Skipped duplicate substations by name: {skipped_duplicate_name_count:,}")
    print(f"  Skipped duplicate substations by distance: {skipped_duplicate_distance_count:,}")
    print(f"  Skipped substations with invalid geometry: {skipped_geometry_count:,}")


def indent_xml(
        *,
        element: ET.Element,
        level: int = 0,
) -> None:
    """
    Apply readable indentation to XML elements.

    Parameters
    ----------
    element : ET.Element
        XML element.
    level : int, default=0
        Current indentation level.

    Returns
    -------
    None
    """

    indentation = "\n" + level * "  "

    if len(element):
        if not element.text or not element.text.strip():
            element.text = indentation + "  "

        for child_element in element:
            indent_xml(
                element=child_element,
                level=level + 1,
            )

        if not child_element.tail or not child_element.tail.strip():
            child_element.tail = indentation

    if level and (not element.tail or not element.tail.strip()):
        element.tail = indentation


def organize_kml_by_voltage_and_add_substations(
        *,
        input_kml_path: Path,
        substation_geojson_path: Path,
        output_kml_path: Path,
) -> None:
    """
    Organize KML powerline placemarks into voltage folders and add substations.

    Parameters
    ----------
    input_kml_path : Path
        Raw powerline KML path.
    substation_geojson_path : Path
        Substations GeoJSON path.
    output_kml_path : Path
        Organized KML path.

    Returns
    -------
    None
    """

    if output_kml_path.exists():
        output_kml_path.unlink()

    ET.register_namespace("", "http://www.opengis.net/kml/2.2")

    tree = ET.parse(input_kml_path)
    root = tree.getroot()

    placemarks = [
        element
        for element in root.iter()
        if get_xml_local_name(element=element) == "Placemark"
    ]

    folder_dict: dict[str, list[ET.Element]] = {
        folder_name: []
        for folder_name in VOLTAGE_FOLDERS
    }

    voltage_tag_count = 0
    sample_voltage_values = []

    print(f"Organizing {len(placemarks):,} powerline placemarks by voltage...")

    for placemark in placemarks:
        voltage_text = extract_kml_text_property(
            placemark=placemark,
            property_name="voltage",
        )

        if voltage_text:
            voltage_tag_count += 1

            if len(sample_voltage_values) < 10:
                sample_voltage_values.append(voltage_text)

        voltage_kv = parse_voltage_to_max_kv(
            voltage_text=voltage_text,
        )

        folder_name = assign_voltage_folder(
            voltage_kv=voltage_kv,
        )

        folder_dict[folder_name].append(placemark)

    print(f"Powerline placemarks with voltage tag: {voltage_tag_count:,}")

    if sample_voltage_values:
        print("Sample voltage values found:")

        for sample_voltage_value in sample_voltage_values:
            print(f"  {sample_voltage_value}")
    else:
        print("No voltage values were found in parsed KML placemarks.")

    kml_element = ET.Element("{http://www.opengis.net/kml/2.2}kml")
    document_element = ET.SubElement(kml_element, "{http://www.opengis.net/kml/2.2}Document")

    create_kml_text_element(
        parent=document_element,
        tag_name="name",
        text_value="Texas Powerlines by Voltage with Substations",
    )

    add_substation_style(
        document_element=document_element,
    )

    for folder_name in VOLTAGE_FOLDERS:
        folder_element = ET.SubElement(document_element, "{http://www.opengis.net/kml/2.2}Folder")

        create_kml_text_element(
            parent=folder_element,
            tag_name="name",
            text_value=folder_name,
        )

        for placemark in folder_dict[folder_name]:
            folder_element.append(placemark)

        print(f"  {folder_name}: {len(folder_dict[folder_name]):,}")

    add_substations_folder(
        document_element=document_element,
        substation_geojson_path=substation_geojson_path,
    )

    indent_xml(
        element=kml_element,
    )

    output_tree = ET.ElementTree(kml_element)
    output_tree.write(
        output_kml_path,
        encoding="utf-8",
        xml_declaration=True,
    )

    print(f"Organized KML created: {output_kml_path}")


def create_kmz_from_kml(
        *,
        input_kml_path: Path,
        output_kmz_path: Path,
) -> None:
    """
    Create a KMZ file from a KML file.

    Parameters
    ----------
    input_kml_path : Path
        Input KML path.
    output_kmz_path : Path
        Output KMZ path.

    Returns
    -------
    None
    """

    if output_kmz_path.exists():
        output_kmz_path.unlink()

    with zipfile.ZipFile(output_kmz_path, mode="w", compression=zipfile.ZIP_DEFLATED) as kmz:
        kmz.write(input_kml_path, arcname="doc.kml")

    print(f"KMZ created: {output_kmz_path}")


# ============================================================
# Main
# ============================================================

def main() -> None:
    """
    Extract and organize Texas OpenStreetMap powerlines and substations to KML/KMZ.

    Returns
    -------
    None
    """

    make_directories(
        directories=[
            DATA_DIR,
            OUTPUT_DIR,
        ]
    )

    check_command_exists(command_name="osmium")
    check_command_exists(command_name="ogr2ogr")

    check_input_file_exists(
        input_pbf_path=RAW_OSM_PBF_PATH,
    )

    powerline_filter_expressions = build_powerline_filters(
        include_underground_cables=INCLUDE_UNDERGROUND_CABLES,
        include_planned_or_construction=INCLUDE_PLANNED_OR_CONSTRUCTION,
    )

    substation_filter_expressions = build_substation_filters()

    filter_osm_with_osmium(
        input_pbf_path=RAW_OSM_PBF_PATH,
        output_pbf_path=POWERLINES_PBF_PATH,
        filter_expressions=powerline_filter_expressions,
        description="powerlines",
    )

    filter_osm_with_osmium(
        input_pbf_path=RAW_OSM_PBF_PATH,
        output_pbf_path=SUBSTATIONS_PBF_PATH,
        filter_expressions=substation_filter_expressions,
        description="substations",
    )

    convert_pbf_to_raw_kml(
        input_pbf_path=POWERLINES_PBF_PATH,
        output_kml_path=RAW_KML_PATH,
    )

    export_pbf_to_geojson_with_osmium(
        input_pbf_path=SUBSTATIONS_PBF_PATH,
        output_geojson_path=SUBSTATIONS_GEOJSON_PATH,
        description="substations",
    )

    organize_kml_by_voltage_and_add_substations(
        input_kml_path=RAW_KML_PATH,
        substation_geojson_path=SUBSTATIONS_GEOJSON_PATH,
        output_kml_path=ORGANIZED_KML_PATH,
    )

    if CREATE_KMZ:
        create_kmz_from_kml(
            input_kml_path=ORGANIZED_KML_PATH,
            output_kmz_path=ORGANIZED_KMZ_PATH,
        )

    print("Done.")


if __name__ == "__main__":
    main()