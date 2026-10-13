import json

import httpx

from property_dns_service.zone_gateway import InfraiDnsGateway, PropertyZoneRequest


def test_property_workloads_choose_distinct_dns_records_and_use_zone_id() -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/v1/dns/domain/add":
            return httpx.Response(200, json={"ok": True, "data": {"zone_id": "zone_42"}})
        return httpx.Response(200, json={"ok": True, "data": {"record_id": "record_1"}})

    gateway = InfraiDnsGateway(
        "test-key",
        transport=httpx.MockTransport(respond),
        sleep=lambda _: None,
    )
    request = PropertyZoneRequest.model_validate(
        {
            "domain": "northwind.example",
            "maintenance": {"property_code": "cedar", "dispatch_ipv4": "192.0.2.20"},
            "tenant_documents": {
                "property_code": "cedar",
                "document_host": "tenant-files.example.net",
            },
            "inspection_reminder": {"property_code": "cedar", "due_on": "2026-10-15"},
        }
    )

    result = gateway.publish_property_zone(request, "move-cedar-2026")
    gateway.close()

    writes = [json.loads(call.content) for call in calls[1:]]
    assert result.zone_id == "zone_42"
    assert [(item["record_type"], item["name"]) for item in writes] == [
        ("A", "maintenance-cedar"),
        ("CNAME", "documents-cedar"),
        ("TXT", "inspections-cedar"),
    ]
    assert all(item["zone_id"] == "zone_42" for item in writes)
    assert calls[0].method == "POST"
    assert all(call.method == "PUT" for call in calls[1:])
    assert all(call.headers.get("Idempotency-Key") for call in calls)


def test_rate_limit_honors_retry_after_before_repeating_write() -> None:
    attempts = 0
    delays: list[float] = []

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "3"},
                json={"ok": False, "error": {"code": "RATE_LIMITED"}},
            )
        if request.url.path == "/v1/dns/domain/add":
            return httpx.Response(200, json={"ok": True, "data": {"zone_id": "zone_7"}})
        return httpx.Response(200, json={"ok": True, "data": {}})

    gateway = InfraiDnsGateway(
        "test-key",
        transport=httpx.MockTransport(respond),
        sleep=delays.append,
    )
    request = PropertyZoneRequest.model_validate(
        {
            "domain": "contoso.example",
            "maintenance": {"property_code": "elm", "dispatch_ipv4": "192.0.2.30"},
            "tenant_documents": {
                "property_code": "elm",
                "document_host": "docs.example.net",
            },
            "inspection_reminder": {"property_code": "elm", "due_on": "2026-11-01"},
        }
    )

    result = gateway.publish_property_zone(request, "move-elm-2026")
    gateway.close()

    assert result.zone_id == "zone_7"
    assert delays == [3.0]
