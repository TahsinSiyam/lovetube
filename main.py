import streamlit as st
from supabase import create_client, Client
import os

# --- 1. CONNECTION (Use Streamlit Secrets for Security) ---
# In your local .streamlit/secrets.toml or Streamlit Cloud Secrets:
# SUPABASE_URL = "your_url"
# SUPABASE_KEY = "your_key"

try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)
    BUCKET_NAME = "videos"
except Exception as e:
    st.error("Storage credentials missing. Please set SUPABASE_URL and SUPABASE_KEY.")
    st.stop()

st.set_page_config(page_title="StreamlitTube Pro", page_icon="🎬", layout="wide")

# --- UI LOGIC ---
st.title("🎬 StreamlitTube: Permanent Edition")
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Watch Gallery", "Upload Video"])

# --- UPLOAD LOGIC (Saves to Cloud, Not Disk) ---
if page == "Upload Video":
    st.header("📤 Upload to Permanent Cloud")
    uploaded_file = st.file_uploader("Choose video", type=["mp4", "mov", "avi"])
    
    if st.button("Start Upload") and uploaded_file is not None:
        with st.spinner("Uploading to cloud storage..."):
            # Convert file to bytes
            file_bytes = uploaded_file.getvalue()
            file_name = uploaded_file.name
            
            # Upload to Supabase Storage Bucket
            res = supabase.storage.from_(BUCKET_NAME).upload(
                path=file_name,
                file=file_bytes,
                file_options={"content-type": "video/mp4"}
            )
            
            st.success(f"Successfully pinned {file_name} to the cloud!")
            st.balloons()

# --- GALLERY LOGIC (Fetches from Cloud) ---
else:
    st.header("🎥 Global Gallery")
    
    # List files from Supabase Bucket
    files = supabase.storage.from_(BUCKET_NAME).list()
    
    if not files:
        st.info("The cloud is empty. Upload something!")
    else:
        # Filter out any non-video placeholders
        video_names = [f['name'] for f in files if f['name'] != '.emptyFolderPlaceholder']
        
        selected_video = st.selectbox("Select a video to stream", video_names)
        
        if selected_video:
            # Generate a Signed URL or Public URL
            # Note: For public buckets, use get_public_url
            response = supabase.storage.from_(BUCKET_NAME).get_public_url(selected_video)
            
            st.video(response)
            st.caption(f"Streaming: {selected_video}")
            
            if st.button("🗑️ Delete Permanently"):
                supabase.storage.from_(BUCKET_NAME).remove([selected_video])
                st.rerun()