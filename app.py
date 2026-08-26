import streamlit as st
import fal_client
import edge_tts
import asyncio
import tempfile
import os

st.set_page_config(
    page_title="Myanmar Talking Video",
    page_icon="🎬",
    layout="centered",
)

st.title("🎬 Myanmar Talking Video")
st.write("ပုံတစ်ပုံ + မြန်မာစာ → မြန်မာစကားပြော Video")

# FAL API Key
try:
    os.environ["FAL_KEY"] = st.secrets["FAL_KEY"]
except Exception:
    st.error("FAL_KEY မထည့်ရသေးပါ")
    st.stop()

uploaded_file = st.file_uploader(
    "📷 ဓာတ်ပုံရွေးပါ",
    type=["jpg", "jpeg", "png", "webp"],
)

text = st.text_area(
    "📝 ပြောစေချင်တဲ့ မြန်မာစာ",
    placeholder="ဥပမာ - မင်္ဂလာပါ။ ဒီနေ့ ဇာတ်လမ်းအသစ်တစ်ပုဒ် ပြောပြပါမယ်။",
    height=160,
)

voice_name = st.radio(
    "🎤 အသံရွေးပါ",
    ["Nilar", "Thiha"],
    horizontal=True,
)

voice_map = {
    "Nilar": "my-MM-NilarNeural",
    "Thiha": "my-MM-ThihaNeural",
}

if uploaded_file is not None:
    st.image(
        uploaded_file,
        caption="ရွေးထားသောပုံ",
        use_container_width=True,
    )


async def make_audio(text_value, voice_value, output_path):
    communicate = edge_tts.Communicate(
        text_value,
        voice_value,
    )
    await communicate.save(output_path)


if st.button(
    "🎬 မြန်မာစကားပြော Video ထုတ်မယ်",
    use_container_width=True,
):
    if uploaded_file is None:
        st.warning("ဓာတ်ပုံ အရင်ရွေးပါ")

    elif not text.strip():
        st.warning("မြန်မာစာ အရင်ရေးပါ")

    else:
        try:
            with st.spinner("မြန်မာအသံ ဖန်တီးနေပါတယ်..."):
                with tempfile.NamedTemporaryFile(
                    delete=False,
                    suffix=".mp3",
                ) as temp_audio:
                    audio_path = temp_audio.name

                asyncio.run(
                    make_audio(
                        text,
                        voice_map[voice_name],
                        audio_path,
                    )
                )

            st.success("✅ မြန်မာအသံ ပြီးပါပြီ")
            st.audio(audio_path)

            with st.spinner("ပုံနဲ့အသံ Upload လုပ်နေပါတယ်..."):
                image_bytes = uploaded_file.getvalue()

                image_url = fal_client.upload(
                    image_bytes,
                    uploaded_file.type or "image/jpeg",
                )

                audio_url = fal_client.upload_file(audio_path)

            with st.spinner(
                "🎬 စကားပြော Video ဖန်တီးနေပါတယ်... ခဏစောင့်ပါ"
            ):
                result = fal_client.subscribe(
                    "fal-ai/flashtalk",
                    arguments={
                        "image_url": image_url,
                        "audio_url": audio_url,
                    },
                )

            video_url = result["video"]["url"]

            st.success("🎉 Video ပြီးပါပြီ!")
            st.video(video_url)

            st.link_button(
                "📥 Video ဖွင့်ရန်",
                video_url,
                use_container_width=True,
            )

            try:
                os.remove(audio_path)
            except Exception:
                pass

        except Exception as e:
            st.error("Video ထုတ်ရာမှာ Error ဖြစ်နေပါတယ်")
            st.write(str(e))
