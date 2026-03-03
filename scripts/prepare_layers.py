from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import pandas as pd
from pyproj import CRS, Transformer
import shapefile


BASE_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = BASE_DIR / "app" / "static" / "data"


def transform_coordinates(coords: object, transformer: Transformer) -> object:
    if isinstance(coords, (list, tuple)) and coords and isinstance(coords[0], (int, float)):
        x, y = coords[0], coords[1]
        lon, lat = transformer.transform(x, y)
        return [lon, lat]
    if isinstance(coords, (list, tuple)):
        return [transform_coordinates(item, transformer) for item in coords]
    return coords


def get_transformer_from_prj(input_shp: Path) -> Transformer | None:
    prj_path = input_shp.with_suffix(".prj")
    if not prj_path.exists():
        return None

    wkt = prj_path.read_text(encoding="utf-8", errors="ignore")
    source_crs = CRS.from_wkt(wkt)
    target_crs = CRS.from_epsg(4326)

    if source_crs.equals(target_crs):
        return None

    return Transformer.from_crs(source_crs, target_crs, always_xy=True)


def parse_coordinate(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None

    decimal_match = re.match(r"^[-+]?\d+(?:[\.,]\d+)?$", text)
    if decimal_match:
        return float(text.replace(",", "."))

    dms_match = re.search(
        r"(\d{1,3})\D+(\d{1,2})\D+([\d.]+)\D*([NSEW])",
        text,
        re.IGNORECASE,
    )
    if not dms_match:
        return None

    degrees = float(dms_match.group(1))
    minutes = float(dms_match.group(2))
    seconds = float(dms_match.group(3))
    hemisphere = dms_match.group(4).upper()

    decimal = degrees + (minutes / 60.0) + (seconds / 3600.0)
    if hemisphere in {"S", "W"}:
        decimal *= -1
    return decimal


def normalize_value(value: object) -> object:
    if pd.isna(value):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def normalize_name(value: object) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    text = text.upper().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def parse_percentage(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("%", "").replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def coverage_category(percentage: float | None) -> str:
    if percentage is None:
        return "Sin dato"
    if percentage >= 80:
        return "Sobresaliente"
    if percentage >= 70:
        return "Satisfactorio"
    if percentage >= 60:
        return "Mínimo"
    return "Precario"


def shp_to_geojson(input_shp: Path, output_geojson: Path) -> None:
    reader = shapefile.Reader(str(input_shp))
    fields = [field[0] for field in reader.fields[1:]]
    features = []
    transformer = get_transformer_from_prj(input_shp)

    for shape_record in reader.shapeRecords():
        properties = {
            field_name: value
            for field_name, value in zip(fields, shape_record.record)
        }
        geometry = shape_record.shape.__geo_interface__
        if transformer is not None:
            geometry = {
                "type": geometry["type"],
                "coordinates": transform_coordinates(geometry["coordinates"], transformer),
            }
        feature = {
            "type": "Feature",
            "properties": properties,
            "geometry": geometry,
        }
        features.append(feature)

    geojson = {
        "type": "FeatureCollection",
        "features": features,
    }

    output_geojson.parent.mkdir(parents=True, exist_ok=True)
    output_geojson.write_text(
        json.dumps(geojson, ensure_ascii=False),
        encoding="utf-8",
    )


def cases_xlsx_to_geojson(input_xlsx: Path, output_geojson: Path) -> None:
    df = pd.read_excel(input_xlsx)

    latitude_column = "latitud_raw"
    longitude_column = "longitud_raw"
    if latitude_column not in df.columns or longitude_column not in df.columns:
        raise ValueError(
            "No se encontraron columnas 'latitud_raw' y 'longitud_raw' en el archivo Excel."
        )

    features = []
    skipped = 0

    for _, row in df.iterrows():
        latitude = parse_coordinate(row[latitude_column])
        longitude = parse_coordinate(row[longitude_column])

        if latitude is None or longitude is None:
            skipped += 1
            continue

        if abs(latitude) > 90 or abs(longitude) > 180:
            latitude, longitude = longitude, latitude

        if not (14.0 <= latitude <= 33.0 and -120.0 <= longitude <= -80.0):
            if 14.0 <= longitude <= 33.0 and -120.0 <= latitude <= -80.0:
                latitude, longitude = longitude, latitude

        properties = {column: normalize_value(row[column]) for column in df.columns}

        feature = {
            "type": "Feature",
            "properties": properties,
            "geometry": {
                "type": "Point",
                "coordinates": [longitude, latitude],
            },
        }
        features.append(feature)

    geojson = {
        "type": "FeatureCollection",
        "features": features,
    }

    output_geojson.parent.mkdir(parents=True, exist_ok=True)
    output_geojson.write_text(
        json.dumps(geojson, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Casos convertidos: {len(features)}")
    print(f"Registros omitidos por coordenada inválida: {skipped}")


def municipalities_with_coverage(
    municipalities_geojson: Path,
    coverage_xlsx: Path,
    output_geojson: Path,
) -> None:
    source = json.loads(municipalities_geojson.read_text(encoding="utf-8"))

    coverage_df = pd.read_excel(coverage_xlsx, sheet_name="Vacunación 2025 por Municipio")
    coverage_df = coverage_df[["Municipios", "Porcentaje"]].dropna(subset=["Municipios"])

    coverage_lookup = {
        normalize_name(row["Municipios"]): parse_percentage(row["Porcentaje"])
        for _, row in coverage_df.iterrows()
    }

    matched = 0
    unmatched = []
    for feature in source["features"]:
        municipality_name = feature["properties"].get("NOM_MUN")
        normalized_name = normalize_name(municipality_name)
        percentage = coverage_lookup.get(normalized_name)
        if percentage is None:
            unmatched.append(municipality_name)
        else:
            matched += 1

        feature["properties"]["coverage_percentage"] = percentage
        feature["properties"]["coverage_category"] = coverage_category(percentage)

    output_geojson.parent.mkdir(parents=True, exist_ok=True)
    output_geojson.write_text(
        json.dumps(source, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Municipios con cobertura asignada: {matched}")
    print(f"Municipios sin cobertura: {len(unmatched)}")


def main() -> None:
    state_shp = BASE_DIR / "statics" / "hidalgo" / "13ent.shp"
    municipalities_shp = (
        BASE_DIR / "statics" / "municipios_hidalgo" / "muni_2018gw_hidalgo.shp"
    )

    state_geojson = OUTPUT_DIR / "hidalgo_contorno.geojson"
    municipalities_geojson = OUTPUT_DIR / "municipios_hidalgo.geojson"
    cases_xlsx = BASE_DIR / "statics" / "mapear_2025.xlsx"
    cases_geojson = OUTPUT_DIR / "casos_rabia_2025.geojson"
    coverage_xlsx = BASE_DIR / "statics" / "cierre_2025_vacunacion.xlsx"
    municipalities_coverage_geojson = OUTPUT_DIR / "municipios_hidalgo_cobertura_2025.geojson"

    shp_to_geojson(state_shp, state_geojson)
    shp_to_geojson(municipalities_shp, municipalities_geojson)
    cases_xlsx_to_geojson(cases_xlsx, cases_geojson)
    municipalities_with_coverage(
        municipalities_geojson,
        coverage_xlsx,
        municipalities_coverage_geojson,
    )

    print(f"Capa estatal generada: {state_geojson}")
    print(f"Capa municipal generada: {municipalities_geojson}")
    print(f"Capa de casos generada: {cases_geojson}")
    print(f"Capa de cobertura municipal generada: {municipalities_coverage_geojson}")


if __name__ == "__main__":
    main()
