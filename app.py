import os
import base64
import streamlit as st
from runwayml import RunwayML,TaskFailedError
import fal_client

st.set_page_config(
    page_title="AI Image to Video",
        page_icon="",
            layout="centered"
            )

st.title(" AI Image to Video")
st.write("ပုံတစ်ပုံတင်ပြီး AI Video ထုတ်နိုင်ပါတယ်။")

            # FAL API Key
try:
    
                            os.environ["FAL_KEY"] = os.getenv("FAL_KEY") or st.secrets["FAL_KEY"]
except Exception:
                    st.error("FAL_KEY မတွေ့ပါ။ secrets.toml ထဲမှာ API Key ထည့်ပေးပါ။")
                    st.stop()
os.environ["RUNWAYML_API_SECRET"] = st.secrets["RUNWAYWL_API_SECRET"]
client = RunwayML() 
uploaded_file = st.file_uploader(
                            " ပုံတင်ပါ",
                                type=["png", "jpg", "jpeg", "webp"]
                                )
prompt = st.text_area(
                                    " Video Prompt",
                                        placeholder="ဥပမာ - The woman slowly turns toward the camera, cinematic movement."
                                        )

duration = st.slider(
                                            " Video ကြာချိန်",
                                                min_value=1,
                                                    max_value=16,
                                                        value=5
                                                        )

resolution = st.selectbox(
                                                            " Resolution",
                                                                ["720p", "1080p", "540p", "360p"],
                                                                    index=0
                                                                    )

audio = st.checkbox(
                                                                        " အသံပါထုတ်မယ်",
                                                                            value=False
                                                                            )

if uploaded_file is not None:
                                                                                st.image(uploaded_file, caption="တင်ထားသောပုံ", use_container_width=True)

                                                                                if st.button(" Generate Video", use_container_width=True):

                                                                                    if uploaded_file is None:
                                                                                            st.warning("ပုံတစ်ပုံ အရင်တင်ပါ။")

                                                                                    elif not prompt.strip():
                                                                                                        st.warning("Video Prompt ရေးပါ။")

                                                                                else:
                                                                                    image_bytes = uploaded_file.getvalue()
                                                                                    mime_type = uploaded_file.type

                                                                                    image_base64 = base64.b64encode(image_bytes).decode("utf-8")
                                                                                    image_data_uri = f"data:{mime_type};base64,{image_base64}"

                                                                                    try:                                                              
                                                                                        with st.spinner("AI Video ဖန်တီးနေပါတယ်... ခဏစောင့်ပါ။"):

                                                                                            task =client.image_to_video.create(model="gen4.5",prompt_image=image_data_uri,prompt_text=prompt,ratio="1280;720",duration=5 )
                                                                                            st.success(" Video ပြီးပါပြီ!")
                                                                                            st.video(video_url)
                                                                                            st.link_button(" Video ဖွင့်ရန်", video_url)
                                                                                    except Exception as e: 
                                                                                         st.error(str(e))
