import os
import base64
import streamlit as st

try:
    import fal_client
except ImportError:
    fal_client = None

try:
    from runwayml import RunwayML, TaskFailedError
except ImportError:
    RunwayML = None
    TaskFailedError = Exception


st.set_page_config(
    page_title="AI Image to Video",
    page_icon="🎬",
    layout="centered",
)

st.title("🎬 AI Image to Video")
st.caption("ပုံတစ်ပုံတင်ပြီး 9:16 သို့မဟုတ် 16:9 AI Video ထုတ်နိုင်ပါတယ်။")


def read_secret(*names):
    for name in names:
        try:
            value = st.secrets.get(name)
            if value:
                return value
        except Exception:
            pass

        value = os.getenv(name)
        if value:
            return value

    return None


FAL_KEY = read_secret("FAL_KEY")
RUNWAY_KEY = read_secret("RUNWAYML_API_SECRET", "RUNWAY_API_KEY")

if FAL_KEY:
    os.environ["FAL_KEY"] = FAL_KEY

if RUNWAY_KEY:
    os.environ["RUNWAYML_API_SECRET"] = RUNWAY_KEY


st.markdown("---")
st.subheader("⚙️ Video Settings")

provider = st.selectbox(
    "AI Provider",
    ["FAL (Kling)", "Runway"],
)

ratio_choice = st.selectbox(
    "Video Size",
    ["9:16 (Vertical)", "16:9 (Horizontal)"],
)

duration = st.selectbox(
    "Duration",
    [5, 10],
    index=0,
)

prompt = st.text_area(
    "Video Prompt",
    placeholder="ဥပမာ - cinematic motion, natural face movement, slow camera push-in",
    height=120,
)

uploaded_file = st.file_uploader(
    "🖼️ ပုံတင်ပါ",
    type=["jpg", "jpeg", "png", "webp"],
)


if uploaded_file is None:
    st.info("👆 အရင်ဆုံး ပုံတစ်ပုံတင်ပါ။")
    st.stop()


image_bytes = uploaded_file.getvalue()
mime_type = uploaded_file.type or "image/jpeg"

st.image(
    image_bytes,
    caption="တင်ထားသောပုံ",
    use_container_width=True,
)


if st.button(
    "🎬 Video ထုတ်မယ်",
    type="primary",
    use_container_width=True,
):

    if not prompt.strip():
        st.warning("Video Prompt အရင်ရေးပါ။")
        st.stop()

    is_vertical = ratio_choice.startswith("9:16")

    # =========================================================
    # FAL / Kling
    # =========================================================
    if provider.startswith("FAL"):

        if fal_client is None:
            st.error("fal-client package မရှိပါ။ requirements.txt ကိုစစ်ပါ။")
            st.stop()

        if not FAL_KEY:
            st.error("FAL_KEY မတွေ့ပါ။ Streamlit Secrets ထဲ FAL_KEY ထည့်ပါ။")
            st.stop()

        try:
            with st.spinner("FAL / Kling နဲ့ video ထုတ်နေပါတယ်..."):

                image_url = fal_client.upload(image_bytes, mime_type)

                result = fal_client.subscribe(
                    "fal-ai/kling-video/v1.6/pro/image-to-video",
                    arguments={
                        "prompt": prompt.strip(),
                        "image_url": image_url,
                        "duration": str(duration),
                        "aspect_ratio": "9:16" if is_vertical else "16:9",
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
                st.link_button("Video ကိုဖွင့်မယ်", video_url)
            else:
                st.error("FAL က video URL မပြန်ပေးပါ။")
                st.write(result)

        except Exception as e:
            st.error("FAL Video ထုတ်ရာမှာ Error ဖြစ်ပါတယ်။")
            st.exception(e)

    # =========================================================
    # Runway
    # =========================================================
    else:

        if RunwayML is None:
            st.error("runwayml package မရှိပါ။ requirements.txt ကိုစစ်ပါ။")
            st.stop()

        if not RUNWAY_KEY:
            st.error(
                "Runway API key မတွေ့ပါ။ "
                "Streamlit Secrets ထဲ RUNWAYML_API_SECRET ထည့်ပါ။"
            )
            st.stop()

        # Runway allows image Data URIs up to 5 MB.
        if len(image_bytes) > 5 * 1024 * 1024:
            st.error("Runway အတွက် ပုံဖိုင်ကို 5 MB အောက် လျှော့ပြီး ပြန်တင်ပါ။")
            st.stop()

        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        image_data_uri = f"data:{mime_type};base64,{image_b64}"

        try:
            with st.spinner("Runway နဲ့ video ထုတ်နေပါတယ်..."):

                client = RunwayML(api_key=RUNWAY_KEY)

                task = client.image_to_video.create(
                    model="gen4.5",
                    prompt_image=image_data_uri,
                    prompt_text=prompt.strip(),
                    ratio="720:1280" if is_vertical else "1280:720",
                    duration=duration,
                ).wait_for_task_output()

            output = getattr(task, "output", None)
            video_url = None

            if isinstance(output, list) and output:
                video_url = output[0]
            elif isinstance(output, str):
                video_url = output

            if video_url:
                st.success("✅ Video ထုတ်ပြီးပါပြီ!")
                st.video(video_url)
                st.link_button("Video ကိုဖွင့်မယ်", video_url)
            else:
                st.error("Runway က video URL မပြန်ပေးပါ။")
                st.write(task)

        except TaskFailedError as e:
            st.error("Runway task မအောင်မြင်ပါ။")
            details = getattr(e, "task_details", None)
            if details:
                st.write(details)
            else:
                st.exception(e)

        except Exception as e:
            st.error("Runway Video ထုတ်ရာမှာ Error ဖြစ်ပါတယ်။")
            st.exception(e)


st.markdown("---")
st.caption("AI Image to Video • Personal App")
