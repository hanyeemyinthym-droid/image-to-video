 import os
import base64
import streamlit as st

try:
    import fal_client
except ImportError:
    fal_client = None

try:
    from runwayml import RunwayML
except ImportError:
    RunwayML = None


# --------------------------------------------------
# Page setup
# --------------------------------------------------

st.set_page_config(
    page_title="AI Image to Video",
    page_icon="🎬",
    layout="centered",
)

st.title("🎬 AI Image to Video")
st.write("ပုံတစ်ပုံတင်ပြီး AI Video ထုတ်နိုင်ပါတယ်။")


# --------------------------------------------------
# API Keys
# --------------------------------------------------

def get_secret(name):
    try:
        return st.secrets[name]
    except Exception:
        return os.getenv(name)


FAL_KEY = get_secret("FAL_KEY")
RUNWAY_API_KEY = get_secret("RUNWAY_API_KEY")

if FAL_KEY:
    os.environ["FAL_KEY"] = FAL_KEY


# --------------------------------------------------
# Settings
# --------------------------------------------------

st.markdown("---")
st.subheader("⚙️ Video Settings")

provider = st.selectbox(
    "AI Provider",
    ["FAL", "Runway"],
)

resolution = st.selectbox(
    "Video Resolution",
    [
        "9:16 (Vertical)",
        "16:9 (Horizontal)",
    ],
    index=0,
)

prompt = st.text_area(
    "Video Prompt",
    placeholder="ဥပမာ - cinematic movement, natural motion, realistic lighting",
    height=120,
)

uploaded_file = st.file_uploader(
    "🖼️ ပုံတင်ပါ",
    type=["jpg", "jpeg", "png", "webp"],
)


# --------------------------------------------------
# Uploaded image
# --------------------------------------------------

if uploaded_file is not None:

    image_bytes = uploaded_file.getvalue()

    st.image(
        image_bytes,
        caption="တင်ထားသောပုံ",
        use_container_width=True,
    )

    mime_type = uploaded_file.type or "image/jpeg"

    image_base64 = base64.b64encode(
        image_bytes
    ).decode("utf-8")

    image_data_url = (
        f"data:{mime_type};base64,{image_base64}"
    )

    if st.button(
        "🎬 Video ထုတ်မယ်",
        type="primary",
        use_container_width=True,
    ):

        if not prompt.strip():
            st.warning("Video Prompt အရင်ရေးပေးပါ။")
            st.stop()

        # ==========================================
        # FAL
        # ==========================================

        if provider == "FAL":

            if not FAL_KEY:
                st.error(
                    "FAL_KEY မတွေ့ပါ။ "
                    "Secrets သို့မဟုတ် Environment Variables ထဲမှာ "
                    "FAL_KEY ထည့်ထားပါ။"
                )
                st.stop()

            if fal_client is None:
                st.error(
                    "fal-client package မရှိသေးပါ။ "
                    "requirements.txt ထဲမှာ fal-client ထည့်ပါ။"
                )
                st.stop()

            try:

                with st.spinner(
                    "🎬 FAL နဲ့ Video ထုတ်နေပါတယ်..."
                ):

                    aspect_ratio = (
                        "9:16"
                        if resolution.startswith("9:16")
                        else "16:9"
                    )

                    result = fal_client.subscribe(
                        "fal-ai/kling-video/v1.6/standard/image-to-video",
                        arguments={
                            "prompt": prompt,
                            "image_url": image_data_url,
                            "aspect_ratio": aspect_ratio,
                        },
                    )

                video_url = None

                if isinstance(result, dict):

                    video = result.get("video")

                    if isinstance(video, dict):
                        video_url = video.get("url")

                    elif isinstance(video, str):
                        video_url = video

                if video_url:

                    st.success("✅ Video ထုတ်ပြီးပါပြီ!")
                    st.video(video_url)

                else:

                    st.error(
                        "Video URL မရပါ။ "
                        "FAL response ကို အောက်မှာပြထားပါတယ်။"
                    )
                    st.write(result)

            except Exception as e:

                st.error("FAL Video ထုတ်ရာမှာ Error ဖြစ်ပါတယ်။")
                st.exception(e)


        # ==========================================
        # Runway
        # ==========================================

        elif provider == "Runway":

            if not RUNWAY_API_KEY:
                st.error(
                    "RUNWAY_API_KEY မတွေ့ပါ။ "
                    "Secrets သို့မဟုတ် Environment Variables ထဲမှာ "
                    "RUNWAY_API_KEY ထည့်ထားပါ။"
                )
                st.stop()

            if RunwayML is None:
                st.error(
                    "runwayml package မရှိသေးပါ။ "
                    "requirements.txt ထဲမှာ runwayml ထည့်ပါ။"
                )
                st.stop()

            try:

                with st.spinner(
                    "🎬 Runway နဲ့ Video ထုတ်နေပါတယ်..."
                ):

                    runway = RunwayML(
                        api_key=RUNWAY_API_KEY
                    )

                    ratio = (
                        "720:1280"
                        if resolution.startswith("9:16")
                        else "1280:720"
                    )

                    task = runway.image_to_video.create(
                        model="gen4_turbo",
                        prompt_image=image_data_url,
                        prompt_text=prompt,
                        ratio=ratio,
                        duration=5,
                    )

                    task_id = task.id

                    completed_task = (
                        runway.tasks.retrieve(task_id)
                        .wait_for_task_output()
                    )

                output = completed_task.output

                video_url = None

                if output:

                    if isinstance(output, list):
                        video_url = output[0]

                    elif isinstance(output, str):
                        video_url = output

                if video_url:

                    st.success("✅ Video ထုတ်ပြီးပါပြီ!")
                    st.video(video_url)

                else:

                    st.error(
                        "Runway က Video URL မပေးသေးပါ။"
                    )
                    st.write(completed_task)

            except Exception as e:

                st.error(
                    "Runway Video ထုတ်ရာမှာ Error ဖြစ်ပါတယ်။"
                )
                st.exception(e)


else:

    st.info(
        "👆 အရင်ဆုံး ပုံတစ်ပုံရွေးပြီး တင်ပါ။"
    )


# --------------------------------------------------
# Footer
# --------------------------------------------------

st.markdown("---")
st.caption("AI Image to Video • Personal App")
