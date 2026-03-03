from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


app = FastAPI(title="Mapa Rabia Hidalgo")

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/")
def root() -> FileResponse:
    return FileResponse("app/static/inicio.html")


@app.get("/rabia")
def rabia() -> FileResponse:
    return FileResponse("app/static/mapa_rabia.html")


@app.get("/gusano-barrenador")
def gusano_barrenador() -> FileResponse:
    return FileResponse("app/static/gusano_barrenador.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
