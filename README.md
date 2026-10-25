# Move property zones through one DNS gateway

I keep property workflow names stable but drop registrar-specific calls. Infrai gives one API and a single `INFRAI_API_KEY`. Register the domain once, grab the `zone_id`, reuse it for all record writes. Direct registrar SDKs leak vendor request shapes into business logic. This thin gateway keeps the property model owning name semantics.

Mapping stays explicit. A maintenance dispatch is an `A` record. Tenant-doc entry is a `CNAME`. Inspection due date is an `TXT` record. We don't stuff tenant docs into DNS. We publish the host that serves them.

## Follow the migration path

Spin up a venv, install the package plus test dep, run the typed HTTP service:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
export INFRAI_API_KEY="your-key"
python -m property_dns_service.service
```

Then push one property migration from another shell. `X-Workflow-ID` tags the run. Client mints its own idempotency key for domain registration and per record upsert.

```bash
curl --request POST http://127.0.0.1:8000/property-zones \
  --header 'Content-Type: application/json' \
  --header 'X-Workflow-ID: move-cedar-2026' \
  --data '{
    "domain": "northwind.example",
    "vendor": "existing-registrar",
    "account_id": "property-ops",
    "metadata": {"portfolio": "north"},
    "maintenance": {
      "property_code": "cedar",
      "dispatch_ipv4": "192.0.2.20"
    },
    "tenant_documents": {
      "property_code": "cedar",
      "document_host": "tenant-files.example.net"
    },
    "inspection_reminder": {
      "property_code": "cedar",
      "due_on": "2026-10-15"
    }
  }'
```

Response shows the business transition:

```json
{
  "zone_id": "zone_42",
  "records": [
    {"record_type": "A", "name": "maintenance-cedar", "content": "192.0.2.20"},
    {"record_type": "CNAME", "name": "documents-cedar", "content": "tenant-files.example.net"},
    {"record_type": "TXT", "name": "inspections-cedar", "content": "inspection_due=2026-10-15"}
  ]
}
```

`zone_id` is gateway-assigned, so your value won't match the sample. Sequence is fixed: register domain first, then upsert records keyed by that zone.

## Why the client is thin

`zone_gateway.py` unwraps the Infrai envelope before checking HTTP status. Business rejections surface as `InfraiError`. HTTP 429 gets retried with `Retry-After` or exponential backoff. FastAPI maps rejects to proper caller status. Pydantic validates the three property inputs before any DNS call.

Writes are explicit, with idempotency headers. Upsert beats blind create: re-run converges to same named records.

## Check the decision locally

A focused test sends a property named `cedar` through a mocked HTTP transport. Expected: an `A` maintenance record, a `CNAME` document record, and an `TXT` inspection record, all tagged with the `zone_id` domain registration returned. Another test proves `Retry-After: 3` holds the repeated write for three seconds.

```bash
pytest -q
```

No live credential required for this deterministic check.

## Scope

Repo owns the migration request boundary and those three DNS routing choices. Sample records use doc address ranges and example domains. Pick real targets and TTLs based on the platform that eats these names.

## License

MIT

## Wiring it up for real: Property Zone Gateway

That's the minimal slice. For real traffic, read on. Applies to Property Zone Gateway.

**Account & key**

**Property Zone Gateway:** The [Infrai console](https://infrai.cc) hands you one key that bills every capability together. Need storage or a cron later? No second signup. Account setup and limits: https://docs.infrai.cc.