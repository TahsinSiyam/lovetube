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
else:
    st.header("🎥 Private Gallery")

    # 1) List files (show the real error if it fails)
    try:
        files = supabase.storage.from_(BUCKET_NAME).list()
    except Exception as e:
        st.error(f"Could not list videos: {e}")
        st.info("Check that SUPABASE_KEY is the service_role key, not the anon key.")
        st.stop()

    video_names = [f["name"] for f in (files or []) if f["name"] != ".emptyFolderPlaceholder"]

    if not video_names:
        st.info("No videos found. If you know you uploaded some, your key is probably the anon key.")
    else:
        selected_video = st.selectbox("Select a video to stream", video_names)

        if selected_video:
            # 2) Create a signed URL and make sure it's a full URL
            video_url = None
            try:
                signed = supabase.storage.from_(BUCKET_NAME).create_signed_url(selected_video, 3600)
                video_url = signed.get("signedURL") or signed.get("signedUrl")

                if video_url and not video_url.startswith("http"):
                    base = url.rstrip("/")
                    path = video_url if video_url.startswith("/") else "/" + video_url
                    if not path.startswith("/storage/v1"):
                        path = "/storage/v1" + path
                    video_url = base + path
            except Exception as e:
                st.error(f"Could not create video link: {e}")

            # 3) Play it, with a fallback that downloads the bytes directly
            if video_url:
                st.video(video_url)
            else:
                with st.spinner("Loading video..."):
                    try:
                        data = supabase.storage.from_(BUCKET_NAME).download(selected_video)
                        st.video(data)
                    except Exception as e:
                        st.error(f"Could not load video: {e}")

            st.caption(f"Streaming: {selected_video}")

            if st.button("🗑️ Delete Permanently"):
                supabase.storage.from_(BUCKET_NAME).remove([selected_video])
                st.rerun()
