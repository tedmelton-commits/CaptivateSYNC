"""
PMC Attachment Sync
--------------------
Streamlit app that pulls images from a Google Drive folder and attaches
each one to the matching row in a Smartsheet, matched on a configurable
"ID" column (matched against the image's file name, minus extension).

Built to support multiple PMC company connections. Right now the demo
ships with a single connection ("pmc_demo") wired up in
.streamlit/secrets.toml -- add more entries under [connections.*] to
support additional companies/sheets/folders without touching this file.
"""
import os
import time
import datetime as dt

import streamlit as st

from utils import gdrive
from utils import smartsheet_client as ss

# --------------------------------------------------------------------------
# Page setup
# --------------------------------------------------------------------------
st.set_page_config(
    page_title="PMC Attachment Sync",
    page_icon="🔗",
    layout="wide",
)

CSS = """
<style>
:root {
    --navy: #171335;
    --navy-2: #1f1a44;
    --purple: #6c5ce7;
    --purple-light: #9b8afb;
    --orange: #f5a623;
    --green: #1fbf75;
    --red: #ef5a5a;
    --ink: #24243d;
    --muted: #8b87a8;
}
.block-container { padding-top: 1.5rem; max-width: 1300px; }
#MainMenu, footer, header {visibility: hidden;}

.hero {
    background: radial-gradient(circle at 80% 0%, #241f52 0%, var(--navy) 55%);
    border-radius: 20px;
    padding: 34px 40px;
    color: white;
    position: relative;
    overflow: hidden;
    margin-bottom: 22px;
}
.hero-pill {
    display: inline-block;
    background: rgba(255,255,255,0.10);
    color: #c9c6ee;
    padding: 5px 14px;
    border-radius: 999px;
    font-size: 12px;
    letter-spacing: 0.06em;
    font-weight: 600;
    margin-bottom: 14px;
}
.hero h1 { font-size: 2.1rem; font-weight: 800; margin: 0 0 10px 0; }
.hero p { color: #c3c0e2; max-width: 640px; font-size: 0.95rem; line-height: 1.5; }
.hero-meta { margin-top: 18px; font-size: 0.85rem; color: #b5b2da; }
.hero-meta b { color: #fff; }
.status-progress { color: var(--orange); font-weight: 700; }
.status-done { color: var(--green); font-weight: 700; }

.donut-wrap { display:flex; align-items:center; gap:18px; }
.donut {
    width: 108px; height: 108px; border-radius: 50%;
    display:flex; align-items:center; justify-content:center;
    background: conic-gradient(var(--purple-light) calc(var(--pct) * 1%), rgba(255,255,255,0.12) 0);
}
.donut-inner {
    width: 80px; height: 80px; border-radius: 50%;
    background: #241f52;
    display:flex; align-items:center; justify-content:center;
    font-weight: 800; font-size: 1.15rem; color: white;
}
.donut-label { font-size: 12px; letter-spacing: 0.05em; color: #b5b2da; font-weight: 700; }
.donut-value { font-size: 1.6rem; font-weight: 800; color: white; margin: 2px 0; }
.donut-sub { font-size: 12px; color: var(--purple-light); }

.card {
    background: white;
    border-radius: 16px;
    padding: 22px 26px;
    border: 1px solid #ececf5;
    margin-bottom: 18px;
}
.card h3 { margin-top: 0; }
.card-sub { color: var(--muted); font-size: 0.85rem; margin-top: -8px; }

.row-item {
    display:flex; align-items:center; justify-content: space-between;
    padding: 14px 4px; border-bottom: 1px solid #f0f0f7;
}
.row-item:last-child { border-bottom: none; }
.row-left { display:flex; align-items:center; gap:12px; }
.dot { width: 11px; height: 11px; border-radius: 50%; flex-shrink:0; }
.dot-green { background: var(--green); }
.dot-orange { background: var(--orange); }
.dot-red { background: var(--red); }
.row-name { font-weight: 700; color: var(--ink); }
.row-badge {
    font-size: 12px; font-weight: 700; padding: 3px 10px; border-radius: 999px;
}
.badge-green { background: rgba(31,191,117,0.12); color: var(--green); }
.badge-orange { background: rgba(245,166,35,0.14); color: #b9770e; }
.badge-red { background: rgba(239,90,90,0.12); color: var(--red); }
.row-file { color: var(--muted); font-size: 0.82rem; }

.stream-card {
    background: var(--navy);
    border-radius: 16px;
    padding: 20px 22px;
    color: white;
    max-height: 640px;
    overflow-y: auto;
}
.stream-title { font-size: 0.78rem; letter-spacing: 0.08em; color: #b5b2da; font-weight: 700; margin-bottom: 14px; }
.stream-item { padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.08); }
.stream-item:last-child { border-bottom: none; }
.stream-tag {
    display:inline-block; font-size: 11px; font-weight: 700; padding: 2px 8px;
    border-radius: 6px; margin-right: 8px;
}
tag-ok { }
.tag-ok { background: rgba(31,191,117,0.18); color: #5be8a8; }
.tag-skip { background: rgba(245,166,35,0.18); color: #ffcd7c; }
.tag-err { background: rgba(239,90,90,0.2); color: #ff9d9d; }
.stream-time { color: #7d7aa0; font-size: 11px; float: right; }
.stream-text { color: #d9d7f0; font-size: 0.85rem; margin-top: 4px; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# --------------------------------------------------------------------------
# Load connection configs from secrets
# --------------------------------------------------------------------------
def load_connections():
    connections = {}
    raw = st.secrets.get("connections", {})
    for key in raw:
        cfg = raw[key]
        connections[key] = {
            "name": cfg.get("name", key),
            "smartsheet_api_token": cfg.get("smartsheet_api_token"),
            "smartsheet_sheet_id": cfg.get("smartsheet_sheet_id"),
            "match_column_name": cfg.get("match_column_name", "ID 2"),
            "gdrive_folder_id": cfg.get("gdrive_folder_id"),
            "gdrive_api_key": cfg.get("gdrive_api_key"),
        }
    return connections


CONNECTIONS = load_connections()

if "sync_log" not in st.session_state:
    st.session_state.sync_log = []
if "sync_results" not in st.session_state:
    st.session_state.sync_results = []
if "last_sync" not in st.session_state:
    st.session_state.last_sync = None


def log(tag, message):
    st.session_state.sync_log.insert(
        0,
        {
            "tag": tag,
            "message": message,
            "time": dt.datetime.now().strftime("%b %d %I:%M %p"),
        },
    )


# --------------------------------------------------------------------------
# Core sync logic
# --------------------------------------------------------------------------
def run_sync(cfg, dry_run=False):
    results = []
    missing = [k for k in ("smartsheet_api_token", "smartsheet_sheet_id", "gdrive_folder_id", "gdrive_api_key")
               if not cfg.get(k)]
    if missing:
        log("err", f"Connection is missing required config: {', '.join(missing)}")
        return results

    client = ss.get_client(cfg["smartsheet_api_token"])
    sheet = ss.get_sheet_with_attachments(client, cfg["smartsheet_sheet_id"])
    col_id = ss.find_column_id(sheet, cfg["match_column_name"])
    if col_id is None:
        log("err", f"Column '{cfg['match_column_name']}' not found on the sheet.")
        return results

    drive_service = gdrive.get_drive_service(cfg["gdrive_api_key"])
    images = gdrive.list_images_in_folder(drive_service, cfg["gdrive_folder_id"])
    if not images:
        log("skip", "No images found in the Drive folder — check that the folder "
                     "and its images are shared as 'Anyone with the link can view'.")

    # Map: match-key (filename without extension, lowercased) -> image metadata
    image_by_key = {}
    for img in images:
        key = os.path.splitext(img["name"])[0].strip().lower()
        image_by_key[key] = img

    matched_keys = set()

    for row in sheet.rows:
        row_key_raw = ss.get_cell_value(row, col_id)
        if not row_key_raw:
            continue
        row_key = row_key_raw.strip().lower()

        if row_key not in image_by_key:
            results.append({
                "id_value": row_key_raw, "row_id": row.id,
                "status": "no_image", "file_name": None,
            })
            continue

        img = image_by_key[row_key]
        matched_keys.add(row_key)
        existing = ss.existing_attachment_names(client, cfg["smartsheet_sheet_id"], row)

        if img["name"].strip().lower() in existing:
            results.append({
                "id_value": row_key_raw, "row_id": row.id,
                "status": "already_synced", "file_name": img["name"],
            })
            log("skip", f"{img['name']} already attached to row '{row_key_raw}' — skipped.")
            continue

        if dry_run:
            results.append({
                "id_value": row_key_raw, "row_id": row.id,
                "status": "would_sync", "file_name": img["name"],
            })
            log("ok", f"[Dry run] Would attach {img['name']} to row '{row_key_raw}'.")
            continue

        try:
            file_bytes = gdrive.download_file(drive_service, img["id"])
            ss.attach_file_to_row(client, cfg["smartsheet_sheet_id"], row.id, img["name"], file_bytes, img.get("mimeType"))
            results.append({
                "id_value": row_key_raw, "row_id": row.id,
                "status": "synced", "file_name": img["name"],
            })
            log("ok", f"Attached {img['name']} to row '{row_key_raw}'.")
        except Exception as exc:  # noqa: BLE001
            results.append({
                "id_value": row_key_raw, "row_id": row.id,
                "status": "error", "file_name": img["name"], "error": str(exc),
            })
            log("err", f"Failed to attach {img['name']} to row '{row_key_raw}': {exc}")

    unmatched_images = [name for key, name in
                        ((k, v["name"]) for k, v in image_by_key.items()) if key not in matched_keys]
    for name in unmatched_images:
        results.append({"id_value": None, "row_id": None, "status": "orphan_image", "file_name": name})
        log("skip", f"{name} in Drive has no matching row ID.")

    return results


# --------------------------------------------------------------------------
# Header / hero
# --------------------------------------------------------------------------
if not CONNECTIONS:
    st.error(
        "No connections configured yet. Add one under `[connections.your_key]` in "
        "`.streamlit/secrets.toml` — see the README for the exact fields needed."
    )
    st.stop()

conn_key = st.selectbox(
    "Connection",
    options=list(CONNECTIONS.keys()),
    format_func=lambda k: CONNECTIONS[k]["name"],
    label_visibility="collapsed",
)
cfg = CONNECTIONS[conn_key]

results = st.session_state.sync_results
synced = sum(1 for r in results if r["status"] in ("synced", "already_synced", "would_sync"))
total_rows_with_id = sum(1 for r in results if r["status"] != "orphan_image")
pct = int(round((synced / total_rows_with_id) * 100)) if total_rows_with_id else 0

last_sync_label = st.session_state.last_sync or "Never"

st.markdown(f"""
<div class="hero">
  <span class="hero-pill">GOOGLE DRIVE → SMARTSHEET</span>
  <h1>{cfg['name']}</h1>
  <p>Pulls image attachments from a Google Drive folder and matches each one to
  its Smartsheet row using the <b>{cfg['match_column_name']}</b> column. Run a sync any
  time new images land in the folder.</p>
  <div class="hero-meta">Last synced: <b>{last_sync_label}</b> &nbsp;·&nbsp; Match column:
  <b>{cfg['match_column_name']}</b></div>
</div>
""", unsafe_allow_html=True)

col_metric, _ = st.columns([1, 2])
with col_metric:
    st.markdown(f"""
    <div class="donut-wrap">
      <div class="donut" style="--pct:{pct};">
        <div class="donut-inner">{pct}%</div>
      </div>
      <div>
        <div class="donut-label">ROWS SYNCED</div>
        <div class="donut-value">{synced}/{total_rows_with_id if total_rows_with_id else 0}</div>
        <div class="donut-sub">{max(total_rows_with_id - synced, 0)} rows still need an image</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

st.write("")

tab_sync, tab_settings, tab_logs = st.tabs(["🔄 Sync Dashboard", "⚙️ Connection Settings", "🧾 Full Sync Log"])

# --------------------------------------------------------------------------
# Sync tab
# --------------------------------------------------------------------------
with tab_sync:
    left, right = st.columns([2, 1])

    with left:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        top1, top2, top3 = st.columns([2, 1, 1])
        with top1:
            st.markdown("### Attachment Match Tracker")
            st.markdown(f'<div class="card-sub">Matching Drive images to rows by <b>{cfg["match_column_name"]}</b></div>', unsafe_allow_html=True)
        with top2:
            dry_run = st.checkbox("Dry run", value=False, help="Preview matches without uploading anything.")
        with top3:
            if st.button("🔄  Sync Now", use_container_width=True, type="primary"):
                with st.spinner("Pulling images from Drive and matching to Smartsheet rows…"):
                    st.session_state.sync_results = run_sync(cfg, dry_run=dry_run)
                    st.session_state.last_sync = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
                st.rerun()

        if not results:
            st.info("No sync has run yet for this connection. Click **Sync Now** to get started.")
        else:
            status_map = {
                "synced": ("dot-green", "badge-green", "Attached"),
                "would_sync": ("dot-green", "badge-green", "Would attach (dry run)"),
                "already_synced": ("dot-green", "badge-green", "Already synced"),
                "no_image": ("dot-orange", "badge-orange", "No image found"),
                "orphan_image": ("dot-orange", "badge-orange", "No matching row"),
                "error": ("dot-red", "badge-red", "Failed"),
            }
            rows_html = ""
            for r in results:
                dot_cls, badge_cls, label = status_map[r["status"]]
                title = r["id_value"] if r["id_value"] else r["file_name"]
                sub = r["file_name"] if r["status"] != "orphan_image" else "orphaned Drive image"
                rows_html += f"""
                <div class="row-item">
                  <div class="row-left">
                    <span class="dot {dot_cls}"></span>
                    <div>
                      <div class="row-name">{title}</div>
                      <div class="row-file">{sub or '—'}</div>
                    </div>
                  </div>
                  <span class="row-badge {badge_cls}">{label}</span>
                </div>
                """
            st.markdown(rows_html, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with right:
        st.markdown('<div class="stream-card">', unsafe_allow_html=True)
        st.markdown('<div class="stream-title">SYNC ACTIVITY STREAM</div>', unsafe_allow_html=True)
        if not st.session_state.sync_log:
            st.markdown('<div class="stream-text">Activity will appear here once you run a sync.</div>', unsafe_allow_html=True)
        else:
            tag_map = {"ok": ("tag-ok", "SYNCED"), "skip": ("tag-skip", "SKIPPED"), "err": ("tag-err", "ERROR")}
            items_html = ""
            for entry in st.session_state.sync_log[:40]:
                cls, label = tag_map[entry["tag"]]
                items_html += f"""
                <div class="stream-item">
                  <span class="stream-tag {cls}">{label}</span>
                  <span class="stream-time">{entry['time']}</span>
                  <div class="stream-text">{entry['message']}</div>
                </div>
                """
            st.markdown(items_html, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

# --------------------------------------------------------------------------
# Settings tab
# --------------------------------------------------------------------------
with tab_settings:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("### Connection details")
    st.markdown('<div class="card-sub">Read from <code>.streamlit/secrets.toml</code>. Add more entries under <code>[connections.*]</code> to wire up additional PMC companies.</div>', unsafe_allow_html=True)
    st.write("")
    st.write(f"**Connection name:** {cfg['name']}")
    st.write(f"**Smartsheet sheet ID:** {cfg['smartsheet_sheet_id'] or '_not set_'}")
    st.write(f"**Match column:** {cfg['match_column_name']}")
    st.write(f"**Google Drive folder ID:** {cfg['gdrive_folder_id'] or '_not set_'}")
    st.write(f"**Drive API key configured:** {'Yes' if cfg['gdrive_api_key'] else 'No'}")
    st.caption(
        "Using a plain API key means the Drive folder (and every image in it) must be "
        "shared as **Anyone with the link can view** — API keys can't access private files."
    )
    st.markdown('</div>', unsafe_allow_html=True)

# --------------------------------------------------------------------------
# Logs tab
# --------------------------------------------------------------------------
with tab_logs:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("### Full sync log")
    if not st.session_state.sync_log:
        st.info("Nothing logged yet.")
    else:
        for entry in st.session_state.sync_log:
            st.write(f"`{entry['time']}` **[{entry['tag'].upper()}]** {entry['message']}")
    st.markdown('</div>', unsafe_allow_html=True)
