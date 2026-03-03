# mapa_rabia_deploy

Proyecto base para visualizar capas geográficas de Hidalgo:

- Capa 1: contorno estatal.
- Capa 2: cobertura de vacunación antirrábica por municipio.
- Capa 3: puntos de casos de rabia 2025.

## Requisitos

- Python 3.11+
- Entorno virtual ya creado en `venv`

## Instalación

```bash
venv/bin/pip install -r requirements.txt
```

## Generar capas GeoJSON

```bash
venv/bin/python scripts/prepare_layers.py
```

Se generan estos archivos:

- `app/static/data/hidalgo_contorno.geojson`
- `app/static/data/municipios_hidalgo.geojson`
- `app/static/data/municipios_hidalgo_cobertura_2025.geojson`
- `app/static/data/casos_rabia_2025.geojson`

## Ejecutar aplicación

```bash
venv/bin/uvicorn app.main:app --reload
```

Abrir en navegador:

- `http://127.0.0.1:8000`
