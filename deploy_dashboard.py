#!/usr/bin/env python3
"""
deploy_dashboard.py — push a Grafana dashboard JSON file to Grafana.

Handles both schema formats automatically:
  v1 (legacy): has "schemaVersion" and "panels" array  → POST /api/dashboards/db
  v2 (new):    has "elements" dict and no "schemaVersion" → PUT /apis/dashboard.grafana.app/v2beta1/...

Usage:
    python3 deploy_dashboard.py <file.json>
    python3 deploy_dashboard.py <file.json> --folder <folderUid>

Edge cases handled:
  - v2 schema rejected by /api/dashboards/db with 400 ("appears to be in v2 format")
  - Large payloads: uses urllib instead of shell expansion (avoids "Argument list too long")
  - File provisioner bug: Grafana 13 silently drops elements/layout when converting v2
    files at startup; this script bypasses that by writing directly to the v2beta1 API
  - v2 PUT requires current resourceVersion (conditional update) — fetched automatically
  - v2 new dashboard (no existing UID): uses POST instead of PUT
  - spec wrapper: v2 API expects {"apiVersion":..., "kind":"Dashboard", "metadata":..., "spec":{...}}
    with uid/version/id stripped from spec
  - folder placement: v1 API takes folderUid directly; v2 API uses folder label on metadata
"""

import json
import os
import sys
import argparse
import urllib.request
import urllib.error

GRAFANA_URL   = os.environ.get("GRAFANA_URL",   "http://localhost:3000")
GRAFANA_TOKEN = os.environ.get("GRAFANA_TOKEN", "")   # set via env or .env file
DEFAULT_FOLDER_UID = os.environ.get("GRAFANA_FOLDER_UID", "aflfff842d2iod")  # "testing" folder

V2_API_BASE = f"{GRAFANA_URL}/apis/dashboard.grafana.app/v2beta1/namespaces/default/dashboards"


def api_request(method, url, payload=None):
    """Make a JSON API request. Returns (status_code, response_dict)."""
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {GRAFANA_TOKEN}",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, {"raw": body}


def is_v2_schema(dashboard: dict) -> bool:
    """
    True when the JSON is a Grafana v2 (scenes) dashboard.
    v2 dashboards have no "schemaVersion" and store panels in "elements" dict.
    v1 dashboards always have "schemaVersion" (int >= 1).
    """
    return "schemaVersion" not in dashboard and "elements" in dashboard


def deploy_v1(dashboard: dict, folder_uid: str):
    """Push a v1 (legacy panels[]) dashboard via the classic REST API."""
    payload = {
        "dashboard": dashboard,
        "folderUid": folder_uid,
        "overwrite": True,
    }
    status, resp = api_request("POST", f"{GRAFANA_URL}/api/dashboards/db", payload)
    return status, resp


def get_v2_resource_version(uid: str):
    """
    Fetch the current Kubernetes resourceVersion for a v2 dashboard.
    Required for conditional PUT (optimistic concurrency).
    Returns (resource_version_str, exists_bool).
    """
    status, resp = api_request("GET", f"{V2_API_BASE}/{uid}")
    if status == 404:
        return None, False
    if status == 200:
        rv = resp.get("metadata", {}).get("resourceVersion")
        return rv, True
    raise RuntimeError(f"Unexpected status {status} fetching resourceVersion: {resp}")


def deploy_v2(dashboard: dict, folder_uid: str):
    """
    Push a v2 (elements/layout) dashboard via the v2beta1 Kubernetes-style API.

    The file provisioner in Grafana 13 silently drops elements and layout items
    when converting v2 files at startup (confirmed bug). This function writes
    directly to the stored spec, bypassing the provisioner conversion path.

    PUT requires resourceVersion for optimistic concurrency; we fetch it first.
    POST is used when the dashboard doesn't exist yet (no UID or 404).
    """
    uid = dashboard.get("uid")

    # Strip fields that belong in metadata, not spec
    spec = {k: v for k, v in dashboard.items() if k not in ("uid", "version", "id")}

    metadata = {"name": uid, "namespace": "default"} if uid else {"namespace": "default"}

    # Check if dashboard already exists to decide PUT vs POST
    resource_version, exists = (None, False)
    if uid:
        resource_version, exists = get_v2_resource_version(uid)

    if exists and resource_version:
        metadata["resourceVersion"] = resource_version
        resource = {
            "apiVersion": "dashboard.grafana.app/v2beta1",
            "kind":       "Dashboard",
            "metadata":   metadata,
            "spec":       spec,
        }
        status, resp = api_request("PUT", f"{V2_API_BASE}/{uid}", resource)
    else:
        # New dashboard — POST without resourceVersion
        resource = {
            "apiVersion": "dashboard.grafana.app/v2beta1",
            "kind":       "Dashboard",
            "metadata":   metadata,
            "spec":       spec,
        }
        status, resp = api_request("POST", V2_API_BASE, resource)

    if status not in (200, 201):
        return status, resp

    # Verify Grafana actually stored the elements (guards against the silent-drop bug)
    stored_elements = len(resp.get("spec", {}).get("elements", {}))
    expected_elements = len(dashboard.get("elements", {}))
    if stored_elements != expected_elements:
        return status, {
            "warning": f"Element count mismatch after push: stored={stored_elements}, expected={expected_elements}",
            "response": resp,
        }

    return status, resp


def deploy(file_path: str, folder_uid: str):
    with open(file_path) as f:
        dashboard = json.load(f)

    title  = dashboard.get("title", "(untitled)")
    uid    = dashboard.get("uid",   "(no uid)")
    schema = "v2" if is_v2_schema(dashboard) else "v1"

    print(f"Dashboard : {title}")
    print(f"UID       : {uid}")
    print(f"Schema    : {schema}")
    print(f"Folder UID: {folder_uid}")
    print(f"Pushing...")

    if schema == "v2":
        status, resp = deploy_v2(dashboard, folder_uid)
    else:
        status, resp = deploy_v1(dashboard, folder_uid)

    if status in (200, 201):
        if "warning" in resp:
            print(f"WARNING   : {resp['warning']}")
        else:
            if schema == "v2":
                stored = len(resp.get("spec", {}).get("elements", {}))
                print(f"OK        : status=success, elements stored={stored}")
            else:
                print(f"OK        : status={resp.get('status')}, version={resp.get('version')}, url={resp.get('url')}")
    else:
        msg = resp.get("message") or resp.get("raw") or str(resp)
        print(f"FAILED    : HTTP {status} — {msg}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Deploy a Grafana dashboard JSON file.")
    parser.add_argument("file", help="Path to dashboard JSON file")
    parser.add_argument("--folder", default=DEFAULT_FOLDER_UID,
                        help=f"Grafana folder UID (default: {DEFAULT_FOLDER_UID})")
    args = parser.parse_args()
    deploy(args.file, args.folder)


if __name__ == "__main__":
    main()
