import os
import base64
import streamlit as st
import requests

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.title("URL Shortener + Image Resizer")

tab1, tab2 = st.tabs(["🔗 Shorten URL", "🖼️ Resize Image"])

with tab1:
    st.subheader("Shorten a URL")
    url_input = st.text_input("Enter a URL")
    if st.button("Shorten"):
        if url_input:
            try:
                resp = requests.post(f"{BACKEND_URL}/shorten", json={"url": url_input}, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    st.success(f"Short code: {data['short_code']}")
                    st.code(f"{BACKEND_URL}{data['short_url']}")
                else:
                    st.error(f"Backend error: {resp.status_code}")
            except Exception as e:
                st.error(f"Could not reach backend: {e}")
        else:
            st.warning("Enter a URL first")

    st.divider()
    st.subheader("Look up a code")
    code_input = st.text_input("Enter short code")
    if st.button("Lookup"):
        if code_input:
            try:
                resp = requests.get(f"{BACKEND_URL}/lookup/{code_input}", timeout=5)
                if resp.status_code == 200:
                    st.write(resp.json()["url"])
                else:
                    st.error("Code not found")
            except Exception as e:
                st.error(f"Could not reach backend: {e}")

with tab2:
    st.subheader("Upload an image")
    uploaded_file = st.file_uploader("Choose an image", type=["png", "jpg", "jpeg"])

    if uploaded_file and st.button("Resize"):
        try:
            files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
            resp = requests.post(f"{BACKEND_URL}/resize", files=files, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                st.session_state["job_id"] = data["job_id"]
                st.session_state["sizes"] = data["sizes"]
                st.session_state["dimensions"] = data["dimensions"]
                st.success(f"Processed. Job ID: {data['job_id']}")
            else:
                st.error(f"Backend error: {resp.status_code} — {resp.text}")
        except Exception as e:
            st.error(f"Could not reach backend: {e}")

    if "job_id" in st.session_state:
        st.divider()
        st.subheader("Results")
        for size in st.session_state["sizes"]:
            resp = requests.get(f"{BACKEND_URL}/result/{st.session_state['job_id']}/{size}", timeout=10)
            if resp.status_code == 200:
                result = resp.json()
                img_bytes = base64.b64decode(result["image_base64"])

                st.write(f"**{size}**")
                st.caption(result["dimensions"])
                st.image(img_bytes)
            else:
                st.warning(f"Could not fetch {size}")