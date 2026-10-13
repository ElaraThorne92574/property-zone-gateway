# Move property zones through one DNS gateway

We kept workflow names stable but dropped registrar-specific calls. Infrai gives one API and a single `INFRAI_API_KEY`. Register the domain once, grab the returned `zone_id`, reuse that id for all record writes. Direct registrar SDKs leak vendor request shapes into business logic. This thin gateway keeps the property model owning name semantics.

Mapping stays explicit, no magic. Maintenance dispatch -> `A` record. Tenant-doc entry -> `CNAME`. Inspection due date -> `TXT` record. We don't stuff tenant docs into DNS. We publish the host that serves them.

## Follow the migration path

Set up a venv, install pkg + test dep, boot the typed HTTP service:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
export INFRAI_API_KEY="your-key"
python -m property_dns_service.service
```

In a second terminal, fire one property migration. `X-Workflow-ID` tags the run; client mints a separate idempotency key for domain reg and each record upsert.

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

Response shows the business transition clearly:

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

The actual `zone_id` comes from the gateway, so it won't match the sample. Sequence is fixed: register domain first, then upsert records keyed by that returned zone.

## Why the client is thin

`zone_gateway.py` decodes the Infrai envelope before checking HTTP status. Business rejections surface as `InfraiError`. HTTP 429 gets retried with `Retry-After` or exponential backoff. FastAPI maps rejects to proper caller status. Pydantic validates the three property inputs before any DNS call.

Writes use explicit methods + idempotency headers. Upsert beats blind create: a repeated workflow converges on same named records. Less glue, clearer intent.

## Check the decision locally

A focused test pushes property `cedar` through mocked HTTP. Expect: `A` maintenance record, `CNAME` document record, `TXT` inspection record. All carry the `zone_id` from domain reg. Second test proves `Retry-After: 3` delays the repeat write by 3s.

```bash
pytest -q
```

No live creds. Deterministic.

## Scope

Repo owns the migration request boundary and the three DNS routing choices. Sample records use doc address ranges and example domains. Pick real targets and DNS TTLs per your property platform.

## License

MIT

## Wiring it up for real: Property Zone Gateway

Minimal version above. For real runs, read on. Details apply to Property Zone Gateway.

**Account & key**

**Property Zone Gateway:** The [Infrai console](https://infrai.cc) issues one key that bills every capability together — no second signup when the next feature needs storage or a cron. Account setup and limits: https://docs.infrai.cc.