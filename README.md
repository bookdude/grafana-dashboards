# Grafana Dashboards

Grafana dashboard definitions and deployment tooling for an ad-tech / programmatic advertising platform. Dashboards run on Grafana 13 backed by ClickHouse.

---

## Quick Start

Set the Grafana token (stored in your environment, not committed):
```bash
export GRAFANA_TOKEN="<your-service-account-token>"
```

Deploy a single dashboard:
```bash
python3 deploy_dashboard.py vcasa_system_status.json
```

Deploy all dashboards in parallel:
```bash
python3 launch_deploy.py
```

Dry run (schema detection only, no push):
```bash
python3 launch_deploy.py --dry-run
```

---

## Dashboard Inventory

### VCASA Monitoring
| Dashboard | File | Description |
|---|---|---|
| VCASA System Status | `vcasa_system_status.json` | **Primary ops dashboard.** Red/green up/down for all VCASA units. YTD universe vs latest-hour online. Live ping (Loss %, RTT ms, RX packets). SSH link on unit name. |
| VCASA Up / Down Monitor | `vcasa_up_down.json` | Earlier prototype. Superseded by System Status. |
| Vcasa Performance | `vcasa_performance.json` | Win rate, impressions, requests — hourly and monthly comparisons. |
| Vcasa Searchable | `vcasa_searchable.json` | Searchable time series table. |
| Vcasa Performance v2 | `vcasa_performance_v2.json` | In progress. Uses Grafana v2 schema (elements/layout). |

### Publisher Revenue
| Dashboard | File | Description |
|---|---|---|
| Publisher Monetization Overview | `publisher_monetization_overview_45.json` | Revenue, fill rate, eCPM, per-publisher trends, anomaly table. Current production version. |
| Publisher Monetization (v42) | `publisher_monetization_overview_42.json` | Previous revision. Superseded by _45. |
| Publisher Monetization (Financial) | `publisher_monetization_overview_-_financial_commas.json` | Comma-formatted revenue, SL Rev breakdowns. |

### Distributor (Dist) Performance
| Dashboard | File | Description |
|---|---|---|
| Dist Productivity / Outlier Intelligence | `dist_productivity__outlier_intelligence.json` | Outlier detection — productivity score, elite/strong/low tiers, dynamic thresholds. |
| Dist AI — Market Pressure | `dist_ai__market_pressure__demand_health.json` | Win rate drivers, pressure knee by hour, best/worst dist-hours. |
| Hourly Performance | `hourly_performance.json` | Last 24h / 7d / YTD bar charts. |
| IP RX / TX | `ip_rx___tx.json` | Network RX/TX per unit. |

### AI / ML Insights
| Dashboard | File | Description |
|---|---|---|
| Podcast AI Drivers (exec) | `podcast_ai_drivers__ecpm__efficiency_exec-ready.json` | Executive-facing eCPM and efficiency drivers, rolling/yesterday overlays. |
| Podcast AI Drivers | `podcast_ai_drivers__ecpm__efficiency.json` | Detailed version with PDP shape curves. Superseded by exec-ready. |
| Media AI Drivers | `media_ai_drivers_2025_daily_media_v2.json` | Feature importance + PDP for media targets. |
| Media AI Insight View | `media_ai_drivers__insight_view.json` | Top drivers, publisher×hour ranking, best/worst hours action list. |

### Infrastructure
| Dashboard | File | Description |
|---|---|---|
| Node Exporter Full | `node_exporter_full_copy.json` | 142-panel CPU/memory/disk/network (Node Exporter). |
| Proxmox Deep Dive | `proxmux_deep_dive.json` | 138-panel Proxmox node stats. |
| Proxmox Overview | `proxmux.json` | Compact CPU, RX/TX, traffic ratios, network drops. |
| Prometheus Stats | `prometheus_20_stats.json` | WAL, head chunks, compaction, query durations. |
| Grafana Metrics | `grafana_metrics.json` | Self-monitoring — instances, dashboards, users, HTTP status, alerts. |
| Up / Down | `up-down.json` | Table of inaccessible IPs. |

### Diagnostics
| Dashboard | File | Description |
|---|---|---|
| Troubleshoot & Test | `troubleshoot_and_test_dashboard.json` | Revenue reconciliation vs manual invoices. Publisher scope, revenue share math. |

---

## Deployment Scripts

### `deploy_dashboard.py`

Deploys a single JSON file to Grafana. Handles both schema formats:

| Schema | Detected by | API used |
|---|---|---|
| v1 (legacy) | `"schemaVersion"` present + `"panels"` array | `POST /api/dashboards/db` |
| v2 (Grafana 12+) | No `"schemaVersion"`, `"elements"` dict present | `PUT /apis/dashboard.grafana.app/v2beta1/...` |

Known Grafana 13 issue: the file provisioner silently drops all panels from v2 dashboards on startup. This script bypasses the provisioner by writing directly to the v2beta1 API and verifies the stored element count matches the file.

### `launch_deploy.py`

Parallel launcher for bulk deployments.

- **Lock protection**: uses `flock(2)` on `/tmp/grafana_deploy.lock`. A second instance exits immediately with code `2` rather than running a conflicting deployment.
- **Parallelism**: `ThreadPoolExecutor`, default 8 workers.
- **Auto-discovery**: deploys every `*.json` in the directory unless specific files are given.
- **Exit codes**: `0` all passed · `1` one or more errors · `2` lock conflict

```
usage: python3 launch_deploy.py [files ...] [--folder UID] [--workers N] [--dry-run]
```

---

## ClickHouse Views

Two views are maintained in ClickHouse as part of this project:

### `default.v_vcasa_to_dist`
Maps VCASA name ↔ Dist ↔ IP. One row per (vcasa_name, dist, ip). Primary IP source is `serial_ip`; falls back to `Vcasa_to_info.ip`. Both `w_`-prefixed and non-prefixed Dist forms are included for join compatibility. Coverage: 97.7% of named Dists.

### `default.v_vcasa_system_status`
Live system status view — mirrors the VCASA System Status dashboard table exactly. Use this for programmatic access (e.g. the offline remediation script).

```sql
SELECT * FROM default.v_vcasa_system_status
WHERE status = 0       -- offline
  AND loss_pct < 100   -- but IP-reachable
ORDER BY up_pct DESC;
```

Columns: `status`, `vcasa_name`, `dist`, `city`, `state`, `ip`, `up_pct`, `up_hours`, `loss_pct`, `rtt_ms`, `rx`, `last_seen`

---

## Data Source

All dashboards connect to ClickHouse via the `grafana-clickhouse-datasource` plugin, datasource UID `aep99bsdau1a8f`.

Grafana instance: `http://localhost:3000`  
Folders: `testing` = `aflfff842d2iod` · `Revenue` = `cfj72hwwwhwqoa` · `Revenue-GK` = `efjrkl235jx8gc`
