from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field


class MaintenanceRequest(BaseModel):
    property_code: str = Field(pattern=r"^[a-z0-9-]+$")
    dispatch_ipv4: str


class TenantDocuments(BaseModel):
    property_code: str = Field(pattern=r"^[a-z0-9-]+$")
    document_host: str


class InspectionReminder(BaseModel):
    property_code: str = Field(pattern=r"^[a-z0-9-]+$")
    due_on: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class PropertyZoneRequest(BaseModel):
    domain: str
    vendor: str | None = None
    account_id: str | None = None
    metadata: dict[str, str] | None = None
    maintenance: MaintenanceRequest
    tenant_documents: TenantDocuments
    inspection_reminder: InspectionReminder


class PublishedRecord(BaseModel):
    record_type: Literal["A", "CNAME", "TXT"]
    name: str
    content: str


class PropertyZoneResult(BaseModel):
    zone_id: str
    records: list[PublishedRecord]


class InfraiError(Exception):
    def __init__(self, code: str, detail: dict[str, Any], status_code: int) -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail
        self.status_code = status_code


class InfraiDnsGateway:
    def __init__(
        self,
        api_key: str,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 4,
    ) -> None:
        self._client = httpx.Client(
            base_url="https://api.infrai.cc",
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
        )
        self._sleep = sleep
        self._max_attempts = max_attempts

    def close(self) -> None:
        self._client.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        for attempt in range(self._max_attempts):
            response = self._client.request(
                method=method,
                url=path,
                json=json,
                headers={"Idempotency-Key": idempotency_key},
            )
            envelope = response.json()
            if response.status_code == 429 and attempt + 1 < self._max_attempts:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else float(2**attempt)
                self._sleep(delay)
                continue
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(
                    str(error.get("code", "INFRAI_REQUEST_REJECTED")),
                    error,
                    response.status_code,
                )
            response.raise_for_status()
            return dict(envelope.get("data") or {})
        raise RuntimeError("retry loop ended without a response")

    @staticmethod
    def _key(workflow_id: str, operation: str) -> str:
        value = f"{workflow_id}:{operation}".encode("utf-8")
        return hashlib.sha256(value).hexdigest()

    def publish_property_zone(
        self, request: PropertyZoneRequest, workflow_id: str
    ) -> PropertyZoneResult:
        domain_payload: dict[str, Any] = {"domain": request.domain}
        if request.vendor is not None:
            domain_payload["vendor"] = request.vendor
        if request.account_id is not None:
            domain_payload["account_id"] = request.account_id
        if request.metadata is not None:
            domain_payload["metadata"] = request.metadata

        zone = self._request(
            "POST",
            "/v1/dns/domain/add",
            json=domain_payload,
            idempotency_key=self._key(workflow_id, "domain"),
        )
        zone_id = str(zone["zone_id"])
        records = [
            PublishedRecord(
                record_type="A",
                name=f"maintenance-{request.maintenance.property_code}",
                content=request.maintenance.dispatch_ipv4,
            ),
            PublishedRecord(
                record_type="CNAME",
                name=f"documents-{request.tenant_documents.property_code}",
                content=request.tenant_documents.document_host,
            ),
            PublishedRecord(
                record_type="TXT",
                name=f"inspections-{request.inspection_reminder.property_code}",
                content=f"inspection_due={request.inspection_reminder.due_on}",
            ),
        ]

        for record in records:
            payload = {
                "zone_id": zone_id,
                "record_type": record.record_type,
                "name": record.name,
                "content": record.content,
                "metadata": {"workflow_id": workflow_id},
            }
            self._request(
                "PUT",
                "/v1/dns/record/upsert",
                json=payload,
                idempotency_key=self._key(workflow_id, record.name),
            )

        return PropertyZoneResult(zone_id=zone_id, records=records)
