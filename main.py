"""
StreamTube - private video site (Streamlit + Supabase Storage)

Secrets required: SUPABASE_URL, SUPABASE_KEY, ADMIN_USERNAME, ADMIN_PASSWORD
Bucket required : "videos" (auto-created as private if missing; needs service_role key)
"""
import hmac
import mimetypes
import re
import time
import uuid
from datetime import datetime

import httpx
import streamlit as st
from supabase import create_client

BUCKET = "videos"
ALLOWED = ["mp4", "webm", "mov", "m4v", "mkv", "ogv"]
MAX_ATTEMPTS, LOCK_SECONDS = 5, 60

st.set_page_config(page_title="StreamTube", page_icon="🎬", layout="wide")

st.markdown(
    """
    <style>
      #MainMenu, footer {visibility: hidden;}
      .block-container {padding-top: 2rem; max-width: 1200px;}
      .brand {font-size: 2rem; font-weight: 800; letter-spacing: -.5px;}
      .brand span {color: #ff4b4b;}
      .vtitle {font-weight: 600; font-size: 1rem; margin: .25rem 0 0;
               overflow: hidden; text-overflow: ellipsis; white-space: nowrap;}
      .vmeta {opacity: .6; font-size: .8rem; margin-bottom: .4rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- secrets / client ----------
REQUIRED = ["SUPABASE_URL", "SUPABASE_KEY", "ADMIN_USERNAME", "ADMIN_PASSWORD"]
missing = [k for k in REQUIRED if k not in st.secrets]
if missing:
    st.error(f"Missing Streamlit secrets: {', '.join(missing)}")
    st.stop()

SUPABASE_URL = str(st.secrets["SUPABASE_URL"]).rstrip("/")


@st.cache_resource(show_spinner=False)
def get_client():
    client = create_client(SUPABASE_URL, str(st.secrets["SUPABASE_KEY"]))
    try:
        client.storage.get_bucket(BUCKET)
    except Exception:
        try:
            client.storage.create_bucket(BUCKET, options={"public": False})
        except Exception:
            pass  # bucket may already exist / key lacks permission
    return client


# ---------- auth ----------
def secure_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def login_screen():
    st.session_state.setdefault("attempts", 0)
    st.session_state.setdefault("locked_until", 0.0)

    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        st.markdown('<div class="brand" style="text-align:center">Stream<span>Tube</span></div>',
                    unsafe_allow_html=True)
        st.caption("Private access only")
        remaining = int(st.session_state.locked_until - time.time())
        with st.form("login"):
            user = st.text_input("Username")
            pwd = st.text_input("Password", type="password")
            ok = st.form_submit_button("Sign in", use_container_width=True, type="primary")
        if ok:
            if remaining > 0:
                st.error(f"Too many attempts. Try again in {remaining}s.")
            elif secure_eq(user, str(st.secrets["ADMIN_USERNAME"])) and \
                    secure_eq(pwd, str(st.secrets["ADMIN_PASSWORD"])):
                st.session_state.auth = True
                st.session_state.attempts = 0
                st.rerun()
            else:
                st.session_state.attempts += 1
                if st.session_state.attempts >= MAX_ATTEMPTS:
                    st.session_state.locked_until = time.time() + LOCK_SECONDS
                    st.session_state.attempts = 0
                time.sleep(1)
                st.error("Invalid credentials.")


if not st.session_state.get("auth"):
    login_screen()
    st.stop()

# ---------- helpers ----------
def fmt_size(n):
    n = float(n or 0)
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} TB"


def title_from_name(name: str) -> str:
    base = name.rsplit(".", 1)[0]
    slug = base.split("__", 1)[1] if "__" in base else base
    return slug.replace("-", " ").replace("_", " ").strip().title() or "Untitled"


def fmt_date(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).strftime("%b %d, %Y")
    except Exception:
        return ""


@st.cache_data(ttl=60, show_spinner=False)
def list_videos():
    res = get_client().storage.from_(BUCKET).list(
        "", {"limit": 1000, "sortBy": {"column": "created_at", "order": "desc"}}
    )
    out = []
    for it in res or []:
        name = it.get("name", "")
        if not name or name.startswith(".") or not (it.get("id") or it.get("metadata")):
            continue
        out.append({
            "name": name,
            "title": title_from_name(name),
            "size": (it.get("metadata") or {}).get("size", 0),
            "date": fmt_date(it.get("created_at")),
        })
    return out


def api_headers():
    key = str(st.secrets["SUPABASE_KEY"])
    return {"apikey": key, "Authorization": f"Bearer {key}"}


def signed_url(name: str, ttl: int = 3600) -> str:
    r = httpx.post(
        f"{SUPABASE_URL}/storage/v1/object/sign/{BUCKET}/{name}",
        headers=api_headers(), json={"expiresIn": ttl}, timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    url = data.get("signedURL") or data.get("signedUrl") or ""
    if url.startswith("/"):
        url = f"{SUPABASE_URL}/storage/v1{url}"
    return url


def video_mime(name: str) -> str:
    ext = name.rsplit(".", 1)[-1].lower()
    return {"mp4": "video/mp4", "m4v": "video/mp4", "webm": "video/webm",
            "mov": "video/quicktime", "mkv": "video/x-matroska",
            "ogv": "video/ogg"}.get(ext, "video/mp4")


def remote_content_type(url: str) -> str:
    try:
        r = httpx.get(url, headers={"Range": "bytes=0-0"}, timeout=30, follow_redirects=True)
        return r.headers.get("content-type", "")
    except Exception:
        return ""


@st.cache_data(max_entries=2, ttl=3600, show_spinner=False)
def fetch_bytes(name: str) -> bytes:
    r = httpx.get(signed_url(name), timeout=900, follow_redirects=True)
    r.raise_for_status()
    return r.content


def render_player(name: str):
    url = signed_url(name)
    if remote_content_type(url).lower().startswith("video/"):
        st.video(url)
    else:  # file stored with a wrong content-type -> stream it through the server
        with st.spinner("Loading video…"):
            st.video(fetch_bytes(name), format=video_mime(name))
    st.link_button("Open direct link", url)


def upload_video(file, title: str):
    ext = "." + file.name.rsplit(".", 1)[-1].lower()
    slug = re.sub(r"[^A-Za-z0-9]+", "-", title or file.name.rsplit(".", 1)[0]).strip("-")[:60] or "video"
    path = f"{int(time.time())}-{uuid.uuid4().hex[:6]}__{slug}{ext}"
    mime = mimetypes.guess_type(file.name)[0] or file.type or video_mime(file.name)
    if not mime.startswith("video/"):
        mime = video_mime(file.name)
    r = httpx.post(
        f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{path}",
        headers={**api_headers(), "Content-Type": mime,
                 "x-upsert": "false", "cache-control": "max-age=3600"},
        content=file.getvalue(), timeout=1800,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"{r.status_code}: {r.text[:200]}")
    return path


# ---------- header ----------
h1, h2 = st.columns([6, 1])
h1.markdown('<div class="brand">Stream<span>Tube</span></div>', unsafe_allow_html=True)
if h2.button("Logout", use_container_width=True):
    st.session_state.clear()
    st.rerun()

tab_watch, tab_upload = st.tabs(["🎬 Watch", "⬆️ Upload"])

# ---------- watch ----------
with tab_watch:
    try:
        videos = list_videos()
    except Exception as e:
        st.error(f"Could not load videos: {e}")
        videos = []

    selected = st.session_state.get("selected")
    if selected and selected not in {v["name"] for v in videos}:
        selected = st.session_state.selected = None

    if selected:
        vid = next(v for v in videos if v["name"] == selected)
        try:
            render_player(selected)
        except Exception as e:
            st.error(f"Could not play video: {e}")
        st.subheader(vid["title"])
        st.caption(f'{vid["date"]} · {fmt_size(vid["size"])}')
        st.divider()

    c1, c2 = st.columns([4, 1])
    query = c1.text_input("Search", placeholder="Search videos…", label_visibility="collapsed")
    if c2.button("🔄 Refresh", use_container_width=True):
        list_videos.clear()
        st.rerun()

    shown = [v for v in videos if query.lower() in v["title"].lower()]
    if not shown:
        st.info("No videos yet. Head to the Upload tab." if not videos else "No matches.")
    cols = st.columns(3)
    for i, v in enumerate(shown):
        with cols[i % 3].container(border=True):
            st.markdown(f'<div class="vtitle">🎞️ {v["title"]}</div>'
                        f'<div class="vmeta">{v["date"]} · {fmt_size(v["size"])}</div>',
                        unsafe_allow_html=True)
            b1, b2 = st.columns([3, 1])
            if b1.button("▶ Play", key=f'p_{v["name"]}', use_container_width=True, type="primary"):
                st.session_state.selected = v["name"]
                st.rerun()
            with b2.popover("🗑️"):
                st.write("Delete permanently?")
                if st.button("Yes, delete", key=f'd_{v["name"]}'):
                    try:
                        get_client().storage.from_(BUCKET).remove([v["name"]])
                        if st.session_state.get("selected") == v["name"]:
                            st.session_state.selected = None
                        list_videos.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Delete failed: {e}")

# ---------- upload ----------
with tab_upload:
    with st.form("upload_form", clear_on_submit=True):
        title = st.text_input("Title", max_chars=60)
        files = st.file_uploader("Video files", type=ALLOWED, accept_multiple_files=True)
        go = st.form_submit_button("Upload", type="primary")
    if go:
        if not files:
            st.warning("Choose at least one video.")
        else:
            bar = st.progress(0.0)
            done = 0
            for i, f in enumerate(files):
                try:
                    t = title if (title and len(files) == 1) else f.name.rsplit(".", 1)[0]
                    upload_video(f, t)
                    done += 1
                except Exception as e:
                    st.error(f"{f.name}: {e}")
                bar.progress((i + 1) / len(files))
            list_videos.clear()
            if done:
                st.success(f"Uploaded {done} video(s).")
                st.toast("Upload complete 🎉")
