import os
import streamlit as st
import tempfile
from dotenv import load_dotenv
from mistralai import Mistral
from groq import Groq
import notion_client
import streamlit_rec as sar
from pydub import AudioSegment
import io
import openai

load_dotenv()

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
NOTION_PAGE_ID = "20717e80e7e28098b73dd296e824dc95"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")


def load_context():
        with open("./context.txt", "r", encoding="utf-8") as file:
            return file.read()


def get_notion_content():
    notion = notion_client.Client(auth=NOTION_API_KEY)
    blocks = []
    start_cursor = None
    while True:
        response = notion.blocks.children.list(block_id=NOTION_PAGE_ID, start_cursor=start_cursor)
        blocks.extend(response.get("results"))
        if not response.get("has_more"):
            break
        start_cursor = response.get("next_cursor")

    full_text = ""
    for block in blocks:
        block_type = block["type"]
        content = block[block_type].get("rich_text", [])
        text_content = "".join(part.get("plain_text", "") for part in content)
        full_text += text_content + "\n"
    return full_text.strip()


def transcribe_audio(file_path):
    client = Groq(api_key=GROQ_API_KEY)
    with open(file_path, "rb") as file:
        transcription = client.audio.transcriptions.create(
            file=file,
            model="whisper-large-v3-turbo",
            prompt="Décris un rêve dans un style onirique",
            response_format="verbose_json",
            timestamp_granularities=["word", "segment"],
            language="fr",
            temperature=0.0
        )
    return transcription.text


def update_notion_content(user_input, notion_content):
    client = Mistral(api_key=MISTRAL_API_KEY)
    prompt = f"""
    Tu es un assistant rédactionnel expert chargé de mettre à jour un rapport structuré.
    Voici le rapport actuel :

    {notion_content}

    Voici de nouvelles informations à intégrer :

    {user_input}

    Ta tâche : intégrer ces informations de manière naturelle, fluide et cohérente dans le rapport, sans redondance, sans explication, sans commentaire.

    Réponds uniquement avec le texte mis à jour du rapport, prêt à être utilisé dans Notion.
    """
    chat_response = client.chat.complete(
        model="mistral-large-latest",
        messages=[
            {"role": "system", "content": load_context()},
            {"role": "user", "content": prompt},
        ]
    )
    return chat_response.choices[0].message.content


def clear_notion_page_content():
    notion = notion_client.Client(auth=NOTION_API_KEY)
    children = notion.blocks.children.list(block_id=NOTION_PAGE_ID).get("results", [])
    for child in children:
        notion.blocks.delete(block_id=child["id"])


def write_text_to_page(text_for_notion):
    notion = notion_client.Client(auth=NOTION_API_KEY)
    clear_notion_page_content()
    lines = text_for_notion.strip().split("\n")
    blocks = []

    for line in lines:
        if line.strip():
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{
                        "type": "text",
                        "text": {"content": line}
                    }]
                }
            })

    if blocks:
        notion.blocks.children.append(block_id=NOTION_PAGE_ID, children=blocks)


# === STREAMLIT UI ===
# === STREAMLIT UI ===
st.title("📝 TALK PLAN AI")
st.markdown("Enregistre ta voix, et mets automatiquement à jour le contenu dans Notion.")

wav_audio_data = sar.audiorecorder("Clique pour enregistrer", "Clique pour arrêter")

if wav_audio_data is not None:
    if isinstance(wav_audio_data, bytes):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmpfile:
            tmpfile.write(wav_audio_data)
            audio_path = tmpfile.name
    else:
        audio_buffer = io.BytesIO()
        wav_audio_data.export(audio_buffer, format="wav")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmpfile:
            tmpfile.write(audio_buffer.getvalue())
            audio_path = tmpfile.name

if wav_audio_data is not None:
    if isinstance(wav_audio_data, bytes):
        audio_bytes = wav_audio_data
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmpfile:
            tmpfile.write(audio_bytes)
            audio_path = tmpfile.name
    else:
        audio_buffer = io.BytesIO()
        wav_audio_data.export(audio_buffer, format="wav")
        audio_bytes = audio_buffer.getvalue()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmpfile:
            tmpfile.write(audio_bytes)
            audio_path = tmpfile.name

    st.audio(audio_bytes, format='audio/wav')  # ✅ Use audio_bytes here
    st.success("🎤 Audio enregistré !")


    # ➕ Ajout du bouton qui lance tout le processus
    if st.button("📌 Transcrire et mettre à jour le rapport Notion"):
        with st.spinner("📥 Transcription en cours..."):
            user_input = transcribe_audio(audio_path)

        st.text_area("✍️ Texte transcrit :", user_input, height=200)

        with st.spinner("📚 Récupération du contenu actuel de Notion..."):
            notion_content = get_notion_content()

        with st.spinner("✏️ Mise à jour du rapport avec Mistral..."):
            updated_text = update_notion_content(user_input, notion_content)

        with st.spinner("📤 Écriture dans Notion..."):
            write_text_to_page(updated_text)

        st.success("✅ Rapport mis à jour avec succès !")
