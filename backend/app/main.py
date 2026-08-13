from fastapi import FastAPI, HTTPException

from backend.app.collectors.provo import (
    collect_provo_records_dict,
)


app = FastAPI(
    title="PermitSignal API",
    description="Government approval intelligence platform",
    version="1.0.0",
)


@app.get("/")
def root():
    return {
        "service": "PermitSignal",
        "status": "online",
        "version": "1.0.0",
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "permitsignal-api",
        "version": "1.0.0",
    }


@app.get("/scrape/provo")
def scrape_provo():
    try:
        records = collect_provo_records_dict()

        return {
            "status": "success",
            "municipality": "Provo",
            "state": "Utah",
            "count": len(records),
            "records": records,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )