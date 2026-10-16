# Presence Dashboard

A LAN-only digital signage dashboard showing which employees are currently
onsite, built on Flask + HTMX and backed by the MRI OnLocation API.

```bash
uv sync
uv run flask --app app run --host 0.0.0.0 --port 5000
```

See [MAINTAINERS.md](MAINTAINERS.md) for architecture, configuration, API
reference, and deployment notes.
