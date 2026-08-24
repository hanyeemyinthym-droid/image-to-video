import streamlit as st
import base64
from runwayml import RunwayML

st.set_page_config(
    page_title="My Image to Video",
    page_icon="",
    layout="centered"
)

st.title(" My Image to Video")
st.write("ဓာတ်ပုံတစ်ပုံကနေ AI Video ဖန်တီးမယ်")

uploaded_file = st.file_uploader(
    " ဓာတ်ပုံရွေးပါ",
    type=["jpg", "jpeg", "png", "webp"]
)

prompt = st.text_area(
    " Video Prompt",
    placeholder="ဥပမာ - မိန်းကလေးက ဖြည်းဖြည်းချင်း ရှေ့ကိုလမ်းလျှောက်လာသည်"
)

ratio = st.selectbox(
    " Video အရွယ်အစား",
    ["9:16", "16:9"]
)

duration = st.selectbox(
    " Video ကြာချိန်",
    [5, 10]
)

if uploaded_file is not None:
    st.image(
        uploaded_file,
        caption="ရွေးထားသောပုံ",
        use_container_width=True
    )

if st.button(" Video ထုတ်မယ်", use_container_width=True):

    if uploaded_file is None:
        st.warning("ဓာတ်ပုံတစ်ပုံ အရင်ရွေးပါ")

    elif not prompt.strip():
        st.warning("Video Prompt ရေးပါ")

    else:
        try:
            api_key = st.secrets["RUNWAY_API_KEY"]

            client = RunwayML(
                api_key=api_key
            )

            image_bytes = uploaded_file.getvalue()
            mime_type = uploaded_file.type

            image_base64 = base64.b64encode(
                image_bytes
            ).decode("utf-8")

            image_data_uri = (
                f"data:{mime_type};base64,{image_base64}"
            )

            if ratio == "9:16":
                runway_ratio = "720:1280"
            else:
                runway_ratio = "1280:720"

            with st.spinner(
                "AI Video ဖန်တီးနေပါတယ်... ခဏစောင့်ပါ"
            ):
                task = client.image_to_video.create(
                    model="gen4_turbo",
                    prompt_image=image_data_uri,
                    prompt_text=prompt,
                    duration=duration,
                    ratio=runway_ratio
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
                st.error("Video output မရသေးပါ")

        except Exception as e:
            st.error("Video ထုတ်ရာမှာ Error ဖြစ်နေပါတယ်")
            st.write(str(e))
