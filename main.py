import hmac
import os
import shutil
import subprocess
import tempfile

import streamlit as st
from supabase import create_client, Client


# ============================================================
# CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="StreamlitTube Pro",
    page_icon="🎬",
    layout="wide",
)


# ============================================================
# 1. SUPABASE CONNECTION
# ============================================================

try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]

    supabase: Client = create_client(url, key)

    BUCKET_NAME = "videos"

except Exception:
    st.error(
        "Storage credentials missing. "
        "Please set SUPABASE_URL and SUPABASE_KEY."
    )
    st.stop()


# ============================================================
# 2. LOGIN GATE
# ============================================================

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False


def check_credentials(username: str, password: str) -> bool:
    try:
        correct_user = st.secrets["ADMIN_USERNAME"]
        correct_pass = st.secrets["ADMIN_PASSWORD"]

    except KeyError:
        st.error("Admin credentials are not set in secrets.")
        return False

    user_ok = hmac.compare_digest(
        username.encode("utf-8"),
        correct_user.encode("utf-8"),
    )

    pass_ok = hmac.compare_digest(
        password.encode("utf-8"),
        correct_pass.encode("utf-8"),
    )

    return user_ok and pass_ok


# ============================================================
# LOGIN PAGE
# ============================================================

if not st.session_state.authenticated:

    st.title("🔐 Private Site")

    col, _ = st.columns([1, 2])

    with col:

        with st.form("login_form"):

            username = st.text_input("Username")

            password = st.text_input(
                "Password",
                type="password",
            )

            submitted = st.form_submit_button("Log in")

        if submitted:

            if check_credentials(username, password):

                st.session_state.authenticated = True

                st.rerun()

            else:

                st.error("Invalid username or password.")

    st.stop()


# ============================================================
# 3. MAIN APPLICATION
# ============================================================

st.title("🎬 StreamlitTube: Permanent Edition")

st.sidebar.title("Navigation")

page = st.sidebar.radio(
    "Go to",
    ["Watch Gallery", "Upload Video"],
)


# ============================================================
# LOGOUT
# ============================================================

st.sidebar.divider()

if st.sidebar.button("Log out"):

    st.session_state.authenticated = False

    st.rerun()


# ============================================================
# VIDEO CONVERSION
# ============================================================

def convert_to_h264(input_bytes: bytes, original_name: str):
    """
    Convert an uploaded video to a browser-friendly MP4.

    Output:
        Video: H.264
        Audio: AAC
        Container: MP4
        Pixel format: yuv420p
        Fast start: enabled

    Returns:
        tuple[bytes, str]
    """

    # Check that FFmpeg exists.
    ffmpeg_path = shutil.which("ffmpeg")

    if ffmpeg_path is None:
        raise RuntimeError(
            "FFmpeg is not installed on this server. "
            "Install FFmpeg before uploading videos."
        )

    input_extension = os.path.splitext(original_name)[1]

    if not input_extension:
        input_extension = ".bin"

    input_file = None
    output_file = None

    try:

        # Create temporary input/output files.
        input_temp = tempfile.NamedTemporaryFile(
            suffix=input_extension,
            delete=False,
        )

        input_file = input_temp.name

        input_temp.write(input_bytes)
        input_temp.close()

        output_temp = tempfile.NamedTemporaryFile(
            suffix=".mp4",
            delete=False,
        )

        output_file = output_temp.name
        output_temp.close()

        # ----------------------------------------------------
        # FFMPEG COMMAND
        # ----------------------------------------------------

        command = [
            ffmpeg_path,

            # Input
            "-i",
            input_file,

            # Video
            "-c:v",
            "libx264",

            # Good compatibility with browsers
            "-pix_fmt",
            "yuv420p",

            # Quality
            "-preset",
            "veryfast",

            "-crf",
            "23",

            # Audio
            "-c:a",
            "aac",

            "-b:a",
            "128k",

            # Make MP4 streamable immediately
            "-movflags",
            "+faststart",

            # Output
            "-y",
            output_file,
        ]

        # Run FFmpeg.
        process = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # FFmpeg failed.
        if process.returncode != 0:

            raise RuntimeError(
                "FFmpeg failed to convert the video.\n\n"
                + process.stderr[-4000:]
            )

        # Make sure the output exists.
        if not os.path.exists(output_file):

            raise RuntimeError(
                "FFmpeg completed but no output video was created."
            )

        # Read converted video.
        with open(output_file, "rb") as f:
            converted_bytes = f.read()

        # Generate safe filename.
        original_base = os.path.splitext(
            os.path.basename(original_name)
        )[0]

        output_name = (
            original_base
            + ".mp4"
        )

        return converted_bytes, output_name

    finally:

        # Cleanup temporary files.
        if input_file and os.path.exists(input_file):

            try:
                os.remove(input_file)
            except OSError:
                pass

        if output_file and os.path.exists(output_file):

            try:
                os.remove(output_file)
            except OSError:
                pass


# ============================================================
# 4. UPLOAD PAGE
# ============================================================

if page == "Upload Video":

    st.header("📤 Upload to Permanent Cloud")

    st.write(
        "Videos are automatically converted to "
        "**H.264 + AAC MP4** for browser compatibility."
    )

    uploaded_file = st.file_uploader(
        "Choose video",
        type=[
            "mp4",
            "mov",
            "avi",
            "webm",
            "m4v",
            "ogg",
            "ogv",
            "mkv",
        ],
    )

    if st.button(
        "🚀 Start Upload",
        type="primary",
    ) and uploaded_file is not None:

        try:

            # ------------------------------------------------
            # READ ORIGINAL FILE
            # ------------------------------------------------

            with st.spinner(
                "Reading uploaded video..."
            ):

                original_bytes = uploaded_file.getvalue()

                original_name = uploaded_file.name


            # ------------------------------------------------
            # CONVERT VIDEO
            # ------------------------------------------------

            with st.spinner(
                "🎞️ Converting to browser-compatible H.264..."
            ):

                converted_bytes, file_name = convert_to_h264(
                    original_bytes,
                    original_name,
                )


            # ------------------------------------------------
            # UPLOAD TO SUPABASE
            # ------------------------------------------------

            with st.spinner(
                "☁️ Uploading converted video to cloud..."
            ):

                supabase.storage.from_(
                    BUCKET_NAME
                ).upload(
                    path=file_name,
                    file=converted_bytes,
                    file_options={
                        "content-type": "video/mp4",
                        "cache-control": "3600",
                        "upsert": "true",
                    },
                )


            # ------------------------------------------------
            # SUCCESS
            # ------------------------------------------------

            st.success(
                f"Successfully uploaded {file_name}!"
            )

            st.info(
                "The uploaded copy is H.264/AAC MP4 "
                "and should be browser-compatible."
            )

            st.balloons()


        except Exception as e:

            st.error(
                f"Upload failed: {e}"
            )


# ============================================================
# 5. PRIVATE VIDEO GALLERY
# ============================================================

else:

    st.header("🎥 Private Gallery")


    # --------------------------------------------------------
    # LIST STORAGE FILES
    # --------------------------------------------------------

    try:

        files = (
            supabase
            .storage
            .from_(BUCKET_NAME)
            .list()
        )

    except Exception as e:

        st.error(
            f"Could not list videos: {e}"
        )

        st.info(
            "Check your Supabase credentials and "
            "storage bucket permissions."
        )

        st.stop()


    # --------------------------------------------------------
    # FIND MP4 VIDEOS
    # --------------------------------------------------------

    video_names = [
        f["name"]
        for f in (files or [])
        if f.get("name")
        and f["name"] != ".emptyFolderPlaceholder"
        and f["name"].lower().endswith(".mp4")
    ]


    # --------------------------------------------------------
    # EMPTY GALLERY
    # --------------------------------------------------------

    if not video_names:

        st.info(
            "No videos found."
        )


    # --------------------------------------------------------
    # VIDEO GALLERY
    # --------------------------------------------------------

    else:

        selected_video = st.selectbox(
            "Select a video to watch",
            video_names,
            key="selected_video",
        )


        if selected_video:

            video_url = None


            # ------------------------------------------------
            # CREATE SIGNED URL
            # ------------------------------------------------

            try:

                signed = (
                    supabase
                    .storage
                    .from_(BUCKET_NAME)
                    .create_signed_url(
                        selected_video,
                        3600,
                    )
                )


                # Handle different supabase-py response
                # formats.
                if isinstance(signed, dict):

                    video_url = (
                        signed.get("signedURL")
                        or signed.get("signedUrl")
                        or signed.get("signed_url")
                    )


                if not video_url:

                    raise ValueError(
                        "Supabase did not return a signed URL.\n"
                        f"Response: {signed}"
                    )


                if not video_url.startswith(
                    ("http://", "https://")
                ):

                    raise ValueError(
                        "Supabase returned an invalid signed URL."
                    )


            except Exception as e:

                st.error(
                    f"Could not create video link: {e}"
                )

                st.stop()


            # ------------------------------------------------
            # PLAY VIDEO
            # ------------------------------------------------

            st.video(
                video_url,
                format="video/mp4",
                width="stretch",
            )


            st.caption(
                f"▶️ Watching: {selected_video}"
            )


            # ------------------------------------------------
            # DELETE VIDEO
            # ------------------------------------------------

            if st.button(
                "🗑️ Delete Permanently",
                type="secondary",
                key=f"delete_{selected_video}",
            ):

                try:

                    supabase.storage.from_(
                        BUCKET_NAME
                    ).remove(
                        [selected_video]
                    )

                    st.success(
                        "Video deleted permanently."
                    )

                    st.rerun()

                except Exception as e:

                    st.error(
                        f"Could not delete video: {e}"
                    )
