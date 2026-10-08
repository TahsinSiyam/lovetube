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
