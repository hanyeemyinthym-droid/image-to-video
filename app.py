import os
import base64
import tempfile
import subprocess
from pathlib import Path

import streamlit as st
from PIL import Image
import imageio_ffmpeg
import requests

# Optional paid providers
try:
    import fal_client
except Exception:
    fal_client = None

try:
    from runwayml import RunwayML, TaskFailedError
except Exception:
    RunwayML = None
    TaskFailedError = Exception


# =========================================================
# PAGE
# =========================================================
st.set_page_config(
    page_title="HYM AI Video",
    page_icon="🎬",
    layout="centered",
)

st.title("🎬 AI Image to Video")
st.caption("🆓 Free Motion + FAL (Kling) + Runway")


# =========================================================
# HELPERS
# =========================================================
def read_secret(name, default=None):
    try:
        return st.secrets[name]
    except Exception:
        return os.getenv(name, default)


def uploaded_image_to_rgb_file(uploaded_file, work_dir: Path) -> Path:
    """Normalize JPG/PNG/WEBP/etc. to a regular RGB JPG for FFmpeg/API use."""
    img = Image.open(uploaded_file).convert("RGB")
    out = work_dir / "input.jpg"
    img.save(out, "JPEG", quality=95)
    return out


def run_cmd(cmd):
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-5000:] or "FFmpeg error")
    return result


def build_free_motion_video(
    uploaded_file,
    width: int,
    height: int,
    duration: int,
    motion: str,
) -> bytes:
    """
    Create a 5/10-second MP4 from one still image locally.
    No FAL/Runway API call, so no AI-provider credit is used.
    """
    fps = 30
    frames = max(1, int(duration * fps))

    with tempfile.TemporaryDirectory() as tmp:
        work_dir = Path(tmp)
        input_path = uploaded_image_to_rgb_file(uploaded_file, work_dir)
        output_path = work_dir / "free_motion.mp4"

        # Fill the selected frame without black bars.
        base = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height}"
        )

        if motion == "Slow Zoom In":
            z = f"1+0.12*on/{max(1, frames-1)}"
            x = "iw/2-(iw/zoom/2)"
            y = "ih/2-(ih/zoom/2)"
        elif motion == "Slow Zoom Out":
            z = f"1.12-0.12*on/{max(1, frames-1)}"
            x = "iw/2-(iw/zoom/2)"
            y = "ih/2-(ih/zoom/2)"
        elif motion == "Pan Left → Right":
            z = "1.10"
            x = f"(iw-iw/zoom)*on/{max(1, frames-1)}"
            y = "ih/2-(ih/zoom/2)"
        elif motion == "Pan Right → Left":
            z = "1.10"
            x = f"(iw-iw/zoom)*(1-on/{max(1, frames-1)})"
            y = "ih/2-(ih/zoom/2)"
        elif motion == "Pan Up":
            z = "1.10"
            x = "iw/2-(iw/zoom/2)"
            y = f"(ih-ih/zoom)*(1-on/{max(1, frames-1)})"
        else:  # Gentle Auto
            z = f"1+0.08*on/{max(1, frames-1)}"
            x = "iw/2-(iw/zoom/2)"
            y = "ih/2-(ih/zoom/2)"

        fade_out_start = max(0.0, float(duration) - 0.25)
        vf = (
            f"{base},"
            f"zoompan=z='{z}':x='{x}':y='{y}':"
            f"d={frames}:s={width}x{height}:fps={fps},"
            "format=yuv420p,"
            "fade=t=in:st=0:d=0.20,"
            f"fade=t=out:st={fade_out_start:.2f}:d=0.20"
        )

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        cmd = [
            ffmpeg,
            "-y",
            "-i", str(input_path),
            "-vf", vf,
            "-frames:v", str(frames),
            "-an",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(output_path),
        ]
        run_cmd(cmd)

        return output_path.read_bytes()


def extract_video_url(result):
    if isinstance(result, dict):
        video = result.get("video")
        if isinstance(video, dict) and video.get("url"):
            return video["url"]
        if isinstance(video, str):
            return video
        if result.get("url"):
            return result["url"]
        output = result.get("output")
        if isinstance(output, list) and output:
            return output[0]
        if isinstance(output, str):
            return output
    return None


def generate_fal_kling(uploaded_file, prompt, duration, aspect_ratio):
    if fal_client is None:
        raise RuntimeError(
            "fal-client package မရှိပါ။ requirements.txt ကို update လုပ်ပါ။"
        )

    fal_key = read_secret("FAL_KEY")
    if not fal_key:
        raise RuntimeError(
            "FAL_KEY မတွေ့ပါ။ Streamlit Secrets ထဲမှာ FAL_KEY ထည့်ပါ။"
        )

    os.environ["FAL_KEY"] = fal_key

    mime_type = uploaded_file.type or "image/jpeg"
    image_bytes = uploaded_file.getvalue()

    # Keep compatibility with the fal-client style used by this app.
    if hasattr(fal_client, "upload"):
        image_url = fal_client.upload(image_bytes, mime_type)
    else:
        with tempfile.NamedTemporaryFile(
            suffix=".jpg", delete=False
        ) as f:
            temp_name = f.name
            f.write(image_bytes)
        try:
            image_url = fal_client.upload_file(temp_name)
        finally:
            try:
                os.remove(temp_name)
            except OSError:
                pass

    result = fal_client.subscribe(
        "fal-ai/kling-video/v1.6/pro/image-to-video",
        arguments={
            "prompt": prompt.strip(),
            "image_url": image_url,
            "duration": str(duration),
            "aspect_ratio": aspect_ratio,
        },
    )

    video_url = extract_video_url(result)
    if not video_url:
        raise RuntimeError(f"FAL result ထဲမှာ video URL မတွေ့ပါ။ Result: {result}")
    return video_url


def to_data_uri(uploaded_file):
    mime_type = uploaded_file.type or "image/jpeg"
    data = base64.b64encode(uploaded_file.getvalue()).decode("utf-8")
    return f"data:{mime_type};base64,{data}"


def generate_runway(uploaded_file, prompt, duration, ratio):
    if RunwayML is None:
        raise RuntimeError(
            "runwayml package မရှိပါ။ requirements.txt ကို update လုပ်ပါ။"
        )

    runway_key = (
        read_secret("RUNWAYML_API_SECRET")
        or read_secret("RUNWAY_API_KEY")
    )
    if not runway_key:
        raise RuntimeError(
            "Runway API key မတွေ့ပါ။ Streamlit Secrets ကို စစ်ပါ။"
        )

    client = RunwayML(api_key=runway_key)

    task = client.image_to_video.create(
        model="gen4.5",
        prompt_image=to_data_uri(uploaded_file),
        prompt_text=prompt.strip(),
        ratio=ratio,
        duration=duration,
    ).wait_for_task_output()

    output = getattr(task, "output", None)
    if isinstance(output, list) and output:
        return output[0]
    if isinstance(output, str):
        return output

    if isinstance(task, dict):
        output = task.get("output")
        if isinstance(output, list) and output:
            return output[0]
        if isinstance(output, str):
            return output

    raise RuntimeError("Runway result ထဲမှာ video URL မတွေ့ပါ။")


# =========================================================
# VIDEO SETTINGS
# =========================================================
st.header("⚙️ Video Settings")

provider = st.selectbox(
    "AI Provider",
    [
        "🆓 FREE (No Credit)",
        "FAL (Kling)",
        "Runway",
    ],
)

video_size = st.selectbox(
    "Video Size",
    [
        "9:16 (Vertical)",
        "16:9 (Horizontal)",
    ],
)

duration = st.selectbox(
    "Duration",
    [5, 10],
    index=0,
)

is_vertical = video_size.startswith("9:16")
width, height = ((720, 1280) if is_vertical else (1280, 720))
aspect_ratio = "9:16" if is_vertical else "16:9"
runway_ratio = "720:1280" if is_vertical else "1280:720"

prompt = st.text_area(
    "Video Prompt",
    height=150,
    placeholder=(
        "ဥပမာ — လူငယ်တစ်ယောက် ဖုန်းကိုကြည့်နေပြီး "
        "camera slowly zooms in, natural movement..."
    ),
)

motion = None
if provider.startswith("🆓"):
    motion = st.selectbox(
        "FREE Motion",
        [
            "Gentle Auto",
            "Slow Zoom In",
            "Slow Zoom Out",
            "Pan Left → Right",
            "Pan Right → Left",
            "Pan Up",
        ],
    )
    st.info(
        "🆓 ဒီ mode က API credit မသုံးပါ။ "
        "ပုံကို Zoom / Pan လှုပ်ရှားမှုနဲ့ MP4 ပြောင်းပေးတာဖြစ်ပြီး "
        "Kling လို လူကို AI နဲ့ တကယ်လှုပ်ရှားစေတာ မဟုတ်ပါ။"
    )

uploaded_image = st.file_uploader(
    "🖼️ ပုံတင်ပါ",
    type=["jpg", "jpeg", "png", "webp"],
    key="motion_image",
)

if uploaded_image is not None:
    st.image(uploaded_image, use_container_width=True)

generate_label = (
    "🆓 FREE Video ထုတ်မယ်"
    if provider.startswith("🆓")
    else "🎬 Video ထုတ်မယ်"
)

if st.button(
    generate_label,
    type="primary",
    use_container_width=True,
):
    if uploaded_image is None:
        st.warning("အရင်ဆုံး ပုံတစ်ပုံတင်ပါ။")
    elif not provider.startswith("🆓") and not prompt.strip():
        st.warning("Video Prompt ထည့်ပါ။")
    else:
        try:
            if provider.startswith("🆓"):
                with st.spinner("🆓 FREE video ပြုလုပ်နေပါတယ်..."):
                    free_bytes = build_free_motion_video(
                        uploaded_file=uploaded_image,
                        width=width,
                        height=height,
                        duration=duration,
                        motion=motion,
                    )

                st.session_state["last_free_video"] = free_bytes
                st.success("✅ FREE video ပြီးပါပြီ — FAL/Runway credit မကုန်ပါ။")

            elif provider == "FAL (Kling)":
                with st.spinner("FAL / Kling နဲ့ video ထုတ်နေပါတယ်..."):
                    video_url = generate_fal_kling(
                        uploaded_file=uploaded_image,
                        prompt=prompt,
                        duration=duration,
                        aspect_ratio=aspect_ratio,
                    )

                st.session_state["last_remote_video"] = video_url
                st.success("✅ FAL / Kling video ပြီးပါပြီ။")

            else:
                with st.spinner("Runway နဲ့ video ထုတ်နေပါတယ်..."):
                    video_url = generate_runway(
                        uploaded_file=uploaded_image,
                        prompt=prompt,
                        duration=duration,
                        ratio=runway_ratio,
                    )

                st.session_state["last_remote_video"] = video_url
                st.success("✅ Runway video ပြီးပါပြီ။")

        except TaskFailedError as e:
            st.error("Runway task မအောင်မြင်ပါ။")
            st.code(str(e))
        except Exception as e:
            st.error("Video ထုတ်ရာမှာ Error ဖြစ်ပါတယ်။")
            st.code(str(e))


# =========================================================
# OUTPUT
# =========================================================
if provider.startswith("🆓"):
    free_video = st.session_state.get("last_free_video")
    if free_video:
        st.subheader("▶️ FREE Result")
        st.video(free_video)
        st.download_button(
            "📥 FREE MP4 Download",
            data=free_video,
            file_name=f"hym_free_{aspect_ratio.replace(':', 'x')}_{duration}s.mp4",
            mime="video/mp4",
            use_container_width=True,
        )
else:
    remote_video = st.session_state.get("last_remote_video")
    if remote_video:
        st.subheader("▶️ Result")
        st.video(remote_video)
        st.link_button(
            "📥 Video ကိုဖွင့် / Download",
            remote_video,
            use_container_width=True,
        )


st.divider()
st.caption("HYM AI Video • Personal App • FREE Motion + AI Providers")
