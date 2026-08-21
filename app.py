import streamlit as st
import base64
from runwayml import RunwayML, TaskFailedError

st.set_page_config(
    page_title="My Image to Video",
    page_icon="",
    layout="centered"
)

st.title(" My Image to Video")
st.write("ဓာတ်ပုံတင်ပြီး AI Video ဖန်တီးမယ်")

uploaded_file = st.file_uploader(
    " ဓာတ်ပုံရွေးပါ",
    type=["jpg", "jpeg", "png", "webp"]
)

prompt = st.text_area(
    " Video Prompt",
    placeholder="ဥပမာ - The woman slowly walks forward, cinematic camera movement..."
)

duration = st.selectbox(
    " Video Length",
    [5, 10]
)

if uploaded_file is not None:
    st.image(uploaded_file, caption="ရွေးထားသောပုံ", use_container_width=True)

if st.button(" Generate Video", use_container_width=True):

    if uploaded_file is None:
        st.warning("ဓာတ်ပုံတစ်ပုံ အရင်ရွေးပါ။")

    elif not prompt.strip():
        st.warning("Video Prompt ရေးပါ။")

    else:
        try:
            api_key = st.secrets["RUNWAY_API_KEY"]

            client = RunwayML(
                api_key=api_key
            )

            image_bytes = uploaded_file.getvalue()
            mime_type = uploaded_file.type

            image_base64 = base64.b64encode(image_bytes).decode("utf-8")
            image_data_uri = f"data:{mime_type};base64,{image_base64}"

            with st.spinner("AI Video ဖန်တီးနေပါတယ်... ခဏစောင့်ပါ "):

                task = client.image_to_video.create(
                    model="gen4_turbo",
                    prompt_image=image_data_uri,
                    prompt_text=prompt,
                    duration=duration,
                    ratio="720:1280"
                ).wait_for_task_output()

            if task.output:
                video_url = task.output[0]

                st.success(" Video ပြီးပါပြီ!")
                st.video(video_url)

                st.link_button(
                    " Video ဖွင့်ရန်",
                    video_url,
                    use_container_width=True
                )

            else:
                st.error("Video output မရပါ။ ပြန်စမ်းကြည့်ပါ။")

        except TaskFailedError as e:
            st.error("Video generation မအောင်မြင်ပါ။")
            st.write(e.task_details)

        except Exception as e:
            st.error("Error တစ်ခုဖြစ်သွားပါတယ်။")
            st.write(str(e))
