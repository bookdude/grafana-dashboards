# Grafana Dashboards — `/etc/grafana/dashboards`

## Business Domain

Programmatic advertising / ad-tech platform. Dashboards track publisher revenue, distributor (Dist) performance, AI-driven insights, and infrastructure health.

---

## Primary Data Source

**ClickHouse** — datasource UID `aep99bsdau1a8f`, type `grafana-clickhouse-datasource`.

Most dashboards hardcode this UID. Some use the template variable `${datasource}` (bound to the same ClickHouse instance via a datasource variable).

---

## ClickHouse Schema

### Core analytics tables

| Table | Grain | Key columns |
|---|---|---|
| `analytics.publisher_daily` | publisher × date | `publisher_id`, `publisher_name`, `date`, `net_revenue`, `impressions`, `inventory`, `bids_won` |
| `analytics.v_grafana_overall_latest` | summary view | `time`, `net_revenue` |
| `default.25_ss_dist_reporting` | dist × timestamp | `Dist`, `Impressions`, `Requests`, `timestamp` |
| `default.dist_perf_hourly` | dist × hour | `Dist`, `Requests`, `Impressions`, `hour_bucket` |
| `default.hourly_last_72h_sums` | hourly rollup | `hour_bucket` |

### AI model output tables

| Table | Purpose |
|---|---|
| `podcast_ai_driver_importance` | Feature importance per AI run; `run_time`, `target`, `feature`, `importance` |
| `podcast_ai_hod_ecpm_eff` | Hour-of-day eCPM/efficiency from AI model; `run_time`, `hod`, `avg_ecpm` |
| `podcast_ai_driver_importance` (target=`impr_per_inv`) | Efficiency drivers |
| `2025_daily_media_v2` (media AI) | Feature importance for media KPIs |

Always filter AI tables with `WHERE run_time = (SELECT max(run_time) FROM <table>)` to get the latest model run.

### Key derived metrics

```sql
win_rate    = sum(Impressions) / nullIf(sum(Requests), 0)
fill_rate   = sum(impressions) * 100 / nullIf(sum(inventory), 0)
ecpm        = sum(net_revenue) * 1000 / nullIf(sum(impressions), 0)
efficiency  = sum(impressions) / nullIf(sum(inventory), 0)
```

---

## Known Publishers

| Publisher | ID | Revenue share rate |
|---|---|---|
| Brightcom / Brightcom Stations | 2800 | 22.70% above $204,000 threshold |
| (publisher_2948) | 2948 | — |
| eSpot / iEmerge | 2947 | 24.50% above $5,394 threshold |

Revenue share thresholds are set as template variables in `troubleshoot_and_test_dashboard.json`.

---

## Dashboard Inventory

### Publisher Monetization
| File | Notes |
|---|---|
| `publisher_monetization_overview_45.json` | Current version — revenue, fill, eCPM, per-publisher trends, anomaly table |
| `publisher_monetization_overview_42.json` | Older revision (version 42) — nearly identical structure |
| `publisher_monetization_overview_-_financial_commas.json` | Formatting variant with comma-separated revenue figures and SL Rev breakdowns |

Tags: `clickhouse`, `publishers`, `revenue`

### Distributor (Dist) Performance
| File | Notes |
|---|---|
| `dist_productivity__outlier_intelligence.json` | Outlier detection — productivity score, elite/strong/low outliers, dynamic thresholds |
| `dist_ai__market_pressure__demand_health.json` | Market pressure — win rate drivers, pressure knee by hour, best/worst dist-hours |
| `wip_new_dashboard.json` | WIP — top/bottom performers, biggest movers, ranked WinRate views |
| `new_dashboard.json` | Stub — two panels, DIST Revenues table |
| `ip_rx___tx.json` | Network RX/TX per unit |
| `hourly_performance.json` | Last 24h / 7d / YTD bar charts |

### VCASA Performance
| File | Notes |
|---|---|
| `vcasa_performance.json` | Full dashboard — win rate, impressions, requests, hourly and monthly comparisons |
| `vcasa_searchable.json` | Searchable time series table view |
| `vcasa_performance_v2.json` | Empty — in progress |

VCASA queries against `default.25_ss_dist_reporting` and `default.hourly_last_72h_sums`.

### AI / ML Insights
| File | Notes |
|---|---|
| `podcast_ai_drivers__ecpm__efficiency.json` | eCPM and efficiency model drivers, PDP shape curves, hour-of-day bars |
| `podcast_ai_drivers__ecpm__efficiency_exec-ready.json` | Executive-facing version — same data, cleaner panels, timeseries with rolling/yesterday overlays |
| `media_ai_drivers_2025_daily_media_v2.json` | Feature importance + PDP for media targets; datasource variable `DS_CLICKHOUSE` |
| `media_ai_drivers__insight_view.json` | Insight-oriented view — top drivers, publisher×hour ranking, best/worst hours action list |

Tags: `ai`, `clickhouse`, `podcast`/`media`

### Infrastructure
| File | Notes |
|---|---|
| `node_exporter_full_copy.json` | Full Node Exporter dashboard (142 panels) — CPU, memory, disk, network |
| `proxmux_deep_dive.json` | Deep-dive Proxmox node stats (138 panels) — mirrors node exporter layout |
| `proxmux.json` | Compact Proxmox overview — CPU, RX/TX, traffic ratios, network drops |
| `prometheus_20_stats.json` | Prometheus internals — WAL, head chunks, compaction, query durations |
| `grafana_metrics.json` | Grafana self-monitoring — instance count, dashboards, users, HTTP status, alerts |
| `up-down.json` | Table of inaccessible IPs |

### Diagnostics / Reconciliation
| File | Notes |
|---|---|
| `troubleshoot_and_test_dashboard.json` | Revenue reconciliation against manual invoices — March/April data, publisher scope checks, revenue share math |

---

## Template Variable Conventions

| Variable | Type | Usage |
|---|---|---|
| `${datasource}` | Datasource | ClickHouse datasource picker |
| `${publisher:singlequote}` | Multi-value | SQL `IN` clause: `publisher_name IN (${publisher:singlequote})` |
| `$__timeFilter(date)` | Grafana macro | Time range filter on `date` column |
| `$__timeFilter(timestamp)` | Grafana macro | Time range filter on `timestamp` column |
| `${dist:regex}` | Regex | Dist name regex match in `match(Dist, '${dist:regex}')` |
| `run_time` | Single value | Selects AI model run; always query `max(run_time)` as default |

---

## File Status

- **Active / production**: `publisher_monetization_overview_45`, `vcasa_performance`, `dist_productivity__outlier_intelligence`, `podcast_ai_drivers__ecpm__efficiency_exec-ready`, infra dashboards
- **Older revisions**: `publisher_monetization_overview_42` (superseded by _45), `podcast_ai_drivers__ecpm__efficiency` (superseded by exec-ready)
- **WIP / draft**: `wip_new_dashboard`, `new_dashboard`, `vcasa_performance_v2` (empty)
- **One-off / diagnostic**: `troubleshoot_and_test_dashboard`

---

### VCASA Monitoring
| File | Notes |
|---|---|
| `vcasa_system_status.json` | **Primary up/down monitor** — YTD universe vs latest-hour online; green/red table + summary stats |
| `vcasa_up_down.json` | Earlier prototype using `Vcasa_to_info_seen.last_seen`; superseded by `vcasa_system_status` |

---

## ClickHouse Views (created in this project)

| View | Purpose |
|---|---|
| `default.v_vcasa_to_dist` | Maps every VCASA name ↔ Dist ↔ IP. One row per (vcasa_name, dist, ip). Use this instead of raw joins to `Vcasa_to_info`. |

### v_vcasa_to_dist details
- **IP source**: `default.serial_ip` (most current, updated daily; supports multiple IPs per VCASA)
- **Fallback**: `Vcasa_to_info.ip` for ~276 VCASAs not yet in `serial_ip`
- **Both Dist prefix forms included**: `w_C_TX_...` and `C_TX_...` — joins correctly from any table regardless of prefix convention
- **Coverage**: 97.7% of named Dists in `26_ss_dist_reporting` map to a VCASA name. The remaining 2.3% are Canadian postal codes and malformed entries. The 14,612 `generated_*` hashes are unregistered devices with no mapping anywhere.

```sql
-- Standard usage
SELECT v.vcasa_name, v.ip, sum(r.Impressions) AS impressions
FROM default.`26_ss_dist_reporting` r
JOIN default.v_vcasa_to_dist v ON r.Dist = v.dist
WHERE r.timestamp >= now() - INTERVAL 1 HOUR
GROUP BY v.vcasa_name, v.ip
```

### Key VCASA tables
| Table | Purpose |
|---|---|
| `default.26_ss_dist_reporting` | Live dist reporting — `timestamp`, `Dist`, `Impressions`, `Requests`, `WinRate` |
| `default.Vcasa_to_info` | Static VCASA registry — `Name`, `Dist`, `ip`, `city`, `state`, `provider` (FixedString, use `trim()`) |
| `default.Vcasa_to_info_seen` | Same as above + `last_seen` DateTime |
| `default.serial_ip` | Current public IPs — `host` (Vcasa name), `public_ip`, `loaded_at`; one row per IP |
| `default.v_vcasa_dist_activity_complete` | Activity summary — `vcasa_host`, `proposed_dist`, `public_ips` (Array), `last_seen_90d`, `requests_90d` |

---

## Deployment Workflow

**Every dashboard create or update must be pushed to Grafana via API** so changes appear immediately in the web UI.

```bash
GRAFANA_TOKEN="<service-account-token>"   # stored in memory, do not commit
FOLDER_UID="aflfff842d2iod"   # "testing" folder
DASHBOARD=$(cat /etc/grafana/dashboards/<filename>.json)

curl -s -X POST \
  -H "Authorization: Bearer $GRAFANA_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"dashboard\": $DASHBOARD, \"folderUid\": \"$FOLDER_UID\", \"overwrite\": true}" \
  http://localhost:3000/api/dashboards/db
```

Grafana instance: `http://localhost:3000`
Service account: `claude` (sa-1-claude)
Folders: `testing` = `aflfff842d2iod` | `Revenue` = `cfj72hwwwhwqoa` | `Revenue-GK` = `efjrkl235jx8gc`

**Always test all panel SQL queries in ClickHouse before pushing.** Verify the push returns `"status": "success"`.

---

## Adding or Modifying Dashboards

1. Use datasource UID `aep99bsdau1a8f` for ClickHouse queries, or add a `${datasource}` datasource variable if the dashboard needs to be portable.
2. Wrap time filters with `$__timeFilter(<column>)` — use `date` for date columns, `timestamp` for datetime.
3. For publisher filtering, use `publisher_name IN (${publisher:singlequote})` — the `:singlequote` format handles multi-select.
4. Always use `nullIf(sum(x), 0)` in denominators to avoid division-by-zero.
5. AI model panels must pin to `max(run_time)` — never query all runs.
6. Tag new dashboards with relevant terms from the existing tag set: `clickhouse`, `ai`, `dist`, `publishers`, `revenue`, `podcast`, `media`, `prometheus`, `linux`.
7. **`"format"` in query targets must be a number**: `1` = table, `0` = time series. Never use `"format": "table"` (string) — the ClickHouse plugin rejects it with a Go unmarshal error.
8. For up/down status logic, anchor to `toStartOfHour(max(timestamp))` from the reporting table rather than `now()` — data ingests hourly so `now()` will falsely show everything offline between batches.
