"""FastAPI application: the simulated banking service.

Run:  uvicorn api.main:app --port 8000
"""
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.routes import router

logger = logging.getLogger("bankmate.api")

app = FastAPI(
    title="BankMate Simulated Banking API",
    description="Synthetic, educational banking API. Not connected to any real bank.",
    version="1.0.0",
)
app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok", "data": "synthetic"}


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    # Log details server-side, return a safe generic message to the client.
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})
