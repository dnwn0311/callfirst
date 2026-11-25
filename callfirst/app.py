"""CallFirst demo server.

    python -m callfirst.app            # http://127.0.0.1:8000
"""
from __future__ import annotations

import json
import os
from functools import lru_cache

import joblib
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import careplan, config, data, lace
from .explain import contributions
from .model import fill_defaults

STATIC = config.ROOT / "static"

DISCLAIMER = (
    "Research demo on public, de-identified 1999-2008 US data; not a medical device. "
    "It ranks who to phone first. It never decides who does not need care."
)

app = FastAPI(title="CallFirst", docs_url="/api/docs")


@app.middleware("http")
async def no_stale_assets(request, call_next):
    """Always revalidate the page and its assets so edits show up on reload."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@lru_cache(maxsize=1)
def bundle():
    path = config.ARTIFACTS / "bundle.joblib"
    if not path.exists():
        raise RuntimeError("Model not trained yet. Run: python -m callfirst.train")
    return joblib.load(path)


@lru_cache(maxsize=1)
def worklist_raw():
    return json.loads((config.ARTIFACTS / "worklist.json").read_text())


@lru_cache(maxsize=1)
def evaluation():
    return json.loads((config.REPORTS / "metrics.json").read_text())


def lace_partial(f: dict) -> dict:
    """LACE without the comorbidity part (needs ICD-9 codes the form does not ask for)."""
    L = lace.los_points(f["time_in_hospital"])
    A = 3 if f["admission_type"] == "emergency" or f["admission_source"] == "emergency room" else 0
    E = int(min(f["number_emergency"], 4))
    return {"L": L, "A": A, "E": E}


def assess(features: dict, lace_info: dict | None = None) -> dict:
    b = bundle()
    row = fill_defaults(features, b.reference)
    full = {c: row.iloc[0][c] for c in data.FEATURES}
    full = {k: (float(v) if k in data.NUMERIC else str(v)) for k, v in full.items()}
    score = float(b.score(row)[0])
    risk = float(b.risk(row)[0])
    pct = float(b.percentile([score])[0])
    top10 = score >= b.top_fraction_cutoff(config.PRIMARY_CAPACITY)
    out = {
        "features": full,
        "score": score,
        "risk": risk,
        "percentile": pct,
        "in_top_10_percent": bool(top10),
        "factors": contributions(b, row),
        "checklist": careplan.checklist(full, in_call_list=True),
    }
    if lace_info is not None:
        out["lace"] = {**lace_info, "observed_risk": b.lace_risk.get(lace_info["lace"])}
    else:
        out["lace_partial"] = lace_partial(full)
    return out


@app.get("/api/meta")
def meta():
    b = bundle()
    ev = evaluation()
    return {
        "disclaimer": DISCLAIMER,
        "safety_note": careplan.SAFETY_NOTE,
        "sources": careplan.SOURCES,
        "resources": careplan.RESOURCES,
        "labels": data.FEATURE_LABELS,
        "options": b.options,
        "reference": b.reference,
        "model": {"name": b.name, "params": b.params},
        "primary_capacity": config.PRIMARY_CAPACITY,
        "headline": {
            name: ev["test"][name]["capacity"][str(config.PRIMARY_CAPACITY)]["per_100_calls"]
            for name in ev["test"]
        },
    }


@app.get("/api/worklist")
def worklist():
    rows = []
    for w in worklist_raw():
        a = assess(w["features"], w["lace"])
        rows.append({"id": w["id"], "encounter_id": w["encounter_id"], "readmitted_30d": w["readmitted_30d"], **a})
    return rows


class ScoreRequest(BaseModel):
    features: dict


@app.post("/api/score")
def score(req: ScoreRequest):
    unknown = set(req.features) - set(data.FEATURES)
    if unknown:
        raise HTTPException(422, f"unknown features: {sorted(unknown)}")
    b = bundle()
    for k, v in req.features.items():
        if k in data.CATEGORICAL and str(v) not in b.options[k]:
            raise HTTPException(422, f"{k}: '{v}' is not one of {b.options[k]}")
        if k in data.NUMERIC:
            try:
                x = float(v)
            except (TypeError, ValueError):
                raise HTTPException(422, f"{k} must be a number")
            if not 0 <= x <= 150:
                raise HTTPException(422, f"{k} out of range")
    return assess(req.features)


@app.get("/api/evaluation")
def get_evaluation():
    return evaluation()


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")


def main():
    import uvicorn

    host = os.environ.get("CALLFIRST_HOST", "127.0.0.1")
    port = int(os.environ.get("CALLFIRST_PORT", "8000"))
    bundle()  # fail fast with a clear message if not trained
    print(f"CallFirst running at http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
