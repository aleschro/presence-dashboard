# Flask Presence Dashboard - IIS Deployment Record

## 1. Architectural Overview
This application is deployed on a Windows Server VM using **IIS (Internet Information Services)** acting as a reverse proxy via the **HttpPlatformHandler v1.2** module.



* **Reverse Proxy Model:** IIS listens on Port **5001** and forwards traffic to the Flask development server running on `127.0.0.1`.
* **Process Management:** The **HttpPlatformHandler** manages the lifecycle of the Python process, automatically spawning it and monitoring its health.
* **Persistence:** The app is configured to auto-start on system boot without requiring a user login or an initial web request.

---

## 2. Environment Specifications
* **Application Root:** `C:\OnLocation\presence-dashboard\`
* **Python Path:** `C:\Program Files\Python314\python.exe`
* **IIS Site Name:** `PresenceDashboard`
* **App Pool:** `PresenceDashboardPool`
* **Identity:** `ApplicationPoolIdentity`
    * *Note: Requires "Modify" permissions on the application root to write logs.*

---

## 3. Critical IIS Settings
To achieve the "Auto-Start on Boot" requirement, the following settings are active:

| Feature | Setting | Purpose |
| :--- | :--- | :--- |
| **App Pool Start Mode** | `AlwaysRunning` | Ensures the worker process starts when IIS service starts. |
| **Site Preload Enabled** | `True` | Triggers the handler to spawn Python immediately on boot. |
| **Idle Time-out** | `0` | Prevents the app from spinning down during inactivity. |

---

## 4. Key Configuration (web.config)
The `web.config` file injects these critical environment variables into the Python process:
* `FLASK_APP`: `app.py`
* `ONLOCATION_API_KEY`: {key}
* `VERBOSE`: `1` (Ensures application logic streams to stdout/flask.log)

---

## 5. Logging Strategy
The system generates two logs for distinct purposes:

1.  **`flask.log` (Stdout):** Captures the IIS-to-Python handshake and any startup Tracebacks.
2.  **`app.log` (Internal):** Captures the background poller thread activity and API response status.

