import hmac
import streamlit as st
from supabase import create_client, Client

st.set_page_config(page_title="StreamlitTube Pro", page_icon="🎬", layout="wide")

# --- 1. CONNECTION ---
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)
    BUCKET_NAME = "videos"
except Exception:
    st.error("Storage credentials missing. Please set SUPABASE_URL and SUPABASE_KEY.")
    st.stop()

# --- 2. LOGIN GATE ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False


def check_credentials(username: str, password: str) -> bool:
    try:
        correct_user = st.secrets["ADMIN_USERNAME"]
        correct_pass = st.secrets["ADMIN_PASSWORD"]
    except KeyError:
        st.error("Admin credentials are not set in secrets.")
        return False

    user_ok = hmac.compare_digest(username.encode(), correct_user.encode())
    pass_ok = hmac.compare_digest(password.encode(), correct_pass.encode())
    return user_ok and pass_ok


if not st.session_state.authenticated:
    st.title("🔐 Private Site")
    col, _ = st.columns([1, 2])
    with col:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log in")

        if submitted:
            if check_credentials(username, password):
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Invalid username or password.")
    st.stop()

# --- 3. APP (only reachable after login) ---
st.title("🎬 StreamlitTube: Permanent Edition")
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Watch Gallery", "Upload Video"])

st.sidebar.divider()
if st.sidebar.button("Log out"):
    st.session_state.authenticated = False
    st.rerun()

# --- UPLOAD ---
if page == "Upload Video":
    st.header("📤 Upload to Permanent Cloud")
    uploaded_file = st.file_uploader("Choose video", type=["mp4", "mov", "avi"])

    if st.button("Start Upload") and uploaded_file is not None:
        with st.spinner("Uploading to cloud storage..."):
            file_bytes = uploaded_file.getvalue()
            file_name = uploaded_file.name

            supabase.storage.from_(BUCKET_NAME).upload(
                path=file_name,
                file=file_bytes,
                file_options={"content-type": "video/mp4"},
            )

            st.success(f"Successfully pinned {file_name} to the cloud!")
            st.balloons()

# --- GALLERY ---
# --- GALLERY ---

else:
st.header("🎥 Private Gallery")

```
# 1) List files
try:
    files = supabase.storage.from_(BUCKET_NAME).list()
except Exception as e:
    st.error(f"Could not list videos: {e}")
    st.info("Check that SUPABASE_KEY is the service_role key, not the anon key.")
    st.stop()

# Only keep actual video files
video_extensions = (
    ".mp4",
    ".webm",
    ".mov",
    ".m4v",
    ".ogg",
    ".ogv",
    ".avi",
    ".mkv",
)

video_names = [
    f["name"]
    for f in (files or [])
    if f.get("name")
    and f["name"] != ".emptyFolderPlaceholder"
    and f["name"].lower().endswith(video_extensions)
]

if not video_names:
    st.info(
        "No videos found. If you know you uploaded some, "
        "your key may be the anon key or the bucket may be empty."
    )
else:
    # 2) Select video
    selected_video = st.selectbox(
        "Select a video to watch",
        video_names,
        key="selected_video",
    )

    if selected_video:

        # 3) Generate a fresh signed URL
        #
        # Supabase returns the complete signed URL.
        # Do NOT manually prepend /storage/v1 or the project URL.
        video_url = None

        try:
            signed = (
                supabase.storage
                .from_(BUCKET_NAME)
                .create_signed_url(
                    selected_video,
                    3600,  # 1 hour
                )
            )

            # supabase-py versions can expose slightly different
            # capitalization for this field.
            if isinstance(signed, dict):
                video_url = (
                    signed.get("signedURL")
                    or signed.get("signedUrl")
                    or signed.get("signed_url")
                )

            if not video_url:
                raise ValueError(
                    f"Supabase did not return a signed URL. "
                    f"Response: {signed}"
                )

            # A browser video element needs a real absolute URL.
            if not video_url.startswith(("http://", "https://")):
                raise ValueError(
                    f"Supabase returned an invalid video URL: {video_url}"
                )

        except Exception as e:
            st.error(f"Could not create video link: {e}")
            st.stop()

        # 4) Determine MIME type
        extension = selected_video.rsplit(".", 1)[-1].lower()

        mime_types = {
            "mp4": "video/mp4",
            "webm": "video/webm",
            "mov": "video/quicktime",
            "m4v": "video/mp4",
            "ogg": "video/ogg",
            "ogv": "video/ogg",
            "avi": "video/x-msvideo",
            "mkv": "video/x-matroska",
        }

        video_format = mime_types.get(
            extension,
            "video/mp4",
        )

        # 5) Stream directly from Supabase
        #
        # The browser fetches the signed URL directly instead of
        # downloading the entire file through Streamlit.
        st.video(
            video_url,
            format=video_format,
            width="stretch",
        )

        st.caption(f"▶️ Watching: {selected_video}")

        # 6) Delete permanently
        if st.button(
            "🗑️ Delete Permanently",
            type="secondary",
            key=f"delete_{selected_video}",
        ):
            try:
                result = (
                    supabase.storage
                    .from_(BUCKET_NAME)
                    .remove([selected_video])
                )

                st.success("Video deleted permanently.")
                st.rerun()

            except Exception as e:
                st.error(f"Could not delete video: {e}")
```
