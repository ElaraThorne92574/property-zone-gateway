from __future__ import annotations

import os

import httpx
from fastapi import FastAPI, Header, HTTPException

from .zone_gateway import InfraiDnsGateway, InfraiError, PropertyZoneRequest, PropertyZoneResult


app = FastAPI(title="Property zone gateway")


@app.post("/property-zones", response_model=PropertyZoneResult)
def publish_property_zone(
    request: PropertyZoneRequest,
    x_workflow_id: str = Header(min_length=1),
) -> PropertyZoneResult:
    api_key = os.environ.get("INFRAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="INFRAI_API_KEY is required")

    gateway = InfraiDnsGateway(api_key)
    try:
        return gateway.publish_property_zone(request, x_workflow_id)
    except InfraiError as exc:
        caller_status = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(
            status_code=caller_status,
            detail={"code": exc.code, "error": exc.detail},
        ) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="DNS gateway request did not complete") from exc
    finally:
        gateway.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("property_dns_service.service:app", host="127.0.0.1", port=8000)
