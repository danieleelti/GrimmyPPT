import streamlit as st
import google.generativeai as genai
import json
import requests
import io
from pptx.util import Inches

# --- FUNZIONE 1: ANALISI TESTO (Gemini) ---
def analyze_content(context, gemini_model):
    """Analizza il testo e restituisce i dati (Titolo, Claim, Prompt Immagine)."""
    try:
        model = genai.GenerativeModel(gemini_model)
        prompt_text = f"""
        Sei un Art Director. COMPITI:
        1. NOME FORMAT: Estrailo ESATTO dal testo.
        2. CLAIM: Crea uno slogan commerciale potente.
        3. PROMPT IMMAGINE: Scrivi un prompt DETTAGLIATO in inglese per una copertina FOTOREALISTICA.

        RISPONDI SOLO JSON: {{"format_name": "...", "claim": "...", "imagen_prompt": "..."}}

        TESTO SORGENTE: {context[:5000]}
        """
        res_text = model.generate_content(prompt_text, generation_config={"response_mime_type": "application/json"})
        return json.loads(res_text.text)
    except Exception as e:
        st.error(f"Errore Analisi Gemini: {e}")
        return None

# --- FUNZIONE 2: GENERAZIONE IMMAGINE (Imagen) ---
def generate_image_with_imagen(prompt, api_key, model_name):
    """Chiama l'API di Imagen per generare l'immagine dal prompt."""
    if not model_name.startswith("models/"): model_name = f"models/{model_name}"
    url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:predict?key={api_key}"
    headers = {"Content-Type": "application/json"}
    data = {"instances": [{"prompt": prompt}], "parameters": {"aspectRatio": "16:9", "sampleCount": 1}}
    
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        if "predictions" in result:
            import base64
            return base64.b64decode(result["predictions"][0]["bytesBase64Encoded"])
        return None
    except Exception as e:
        st.error(f"Errore Imagen: {e}")
        return None

# --- FUNZIONE 3: INSERIMENTO NEL PPT (Con logica Schema Diapositiva) ---
def insert_content_into_ppt(slide, data, img_bytes):
    """Inserisce testi nella slide e IMMAGINE NELLO SCHEMA DIAPOSITIVA."""
    try:
        # 1. INSERIMENTO TESTI (Nella slide normale)
        # Titolo
        if slide.shapes.title: slide.shapes.title.text = data.get("format_name", "")
        else:
            for s in slide.placeholders:
                if s.has_text_frame: s.text = data.get("format_name", ""); break
        # Claim
        for s in slide.placeholders:
            if s.has_text_frame and s != slide.shapes.title and s.text != data.get("format_name", ""):
                s.text = data.get("claim", ""); break
        
        # 2. INSERIMENTO IMMAGINE NELLO SCHEMA (Master Layout)
        if img_bytes:
            # Ottieni il layout (schema) associato a questa slide
            slide_layout = slide.slide_layout
            inserted_in_master = False
            
            # Cerca il placeholder immagine nel LAYOUT, non nella slide
            for shape in slide_layout.placeholders:
                # Tipo 18 = Picture, Tipo 7 = Body/Object (che può contenere immagini)
                if shape.placeholder_format.type in [18, 7]:
                    try:
                        image_stream = io.BytesIO(img_bytes)
                        # Inserisce l'immagine nel placeholder dello schema
                        shape.insert_picture(image_stream)
                        inserted_in_master = True
                        # st.info(f"Immagine inserita nello Schema Diapositiva (Placeholder {shape.placeholder_format.idx})")
                        break
                    except Exception as e:
                        st.warning(f"Impossibile inserire nel placeholder dello schema: {e}")
            
            if not inserted_in_master:
                st.warning("⚠️ Nessun placeholder immagine trovato nello Schema Diapositiva. L'immagine non è stata inserita come sfondo.")
                # Opzionale: fallback per inserirla nella slide normale se lo schema fallisce
                # image_stream = io.BytesIO(img_bytes)
                # slide.shapes.add_picture(image_stream, Inches(0), Inches(0), height=Inches(7.5))

        return True
    except Exception as e:
        st.error(f"Errore nell'inserimento nel PPT: {e}")
        return False

# La vecchia funzione 'process' non serve più, è stata divisa nelle 3 funzioni sopra.
