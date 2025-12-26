import streamlit as st
import google.generativeai as genai
import json
import requests
import io
from pptx.util import Inches

def generate_image_with_imagen(prompt, api_key, model_name):
    """
    Chiama l'API usando il modello specifico selezionato nel menu a tendina.
    """
    # Pulizia nome modello per URL (l'API vuole 'models/nome' o solo 'nome' a seconda dell'endpoint, 
    # ma solitamente l'endpoint v1beta accetta models/imagen-...)
    
    # Se il modello selezionato non ha il prefisso 'models/', glielo aggiungiamo per sicurezza nella URL
    if not model_name.startswith("models/"):
        model_name = f"models/{model_name}"
        
    url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:predict?key={api_key}"
    
    headers = {"Content-Type": "application/json"}
    data = {
        "instances": [{"prompt": prompt}],
        "parameters": {
            "aspectRatio": "16:9", 
            "sampleCount": 1
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status() 
        
        result = response.json()
        if "predictions" in result:
            import base64
            b64_data = result["predictions"][0]["bytesBase64Encoded"]
            return base64.b64decode(b64_data)
        else:
            st.error(f"Errore risposta Imagen: {result}")
            return None
            
    except Exception as e:
        st.error(f"Errore chiamata a {model_name}: {e}")
        return None

def process(slide, context, gemini_model, imagen_model):
    """
    LOGICA PAGE 1
    Riceve i nomi dei due modelli dalle tendine.
    """
    st.divider()
    st.markdown(f"### 🎨 AVVIO COVER")
    st.caption(f"Brain: `{gemini_model}` | Painter: `{imagen_model}`")
    
    api_key = st.secrets["GOOGLE_API_KEY"]

    # 1. Configurazione Modello Testo
    try:
        model = genai.GenerativeModel(gemini_model)
    except Exception as e:
        st.error(f"❌ Errore caricamento {gemini_model}: {e}")
        return

    # 2. Prompt Testuale
    prompt_text = f"""
    Sei un Art Director.
    
    COMPITI:
    1. Estrai il NOME DEL FORMAT (esatto).
    2. Crea un CLAIM (Slogan) commerciale.
    3. Scrivi un PROMPT VISIVO in inglese per la copertina.

    RISPONDI SOLO JSON:
    {{
        "format_name": "...",
        "claim": "...",
        "imagen_prompt": "..."
    }}

    TESTO SORGENTE:
    {context[:4000]}
    """
    
    st.info("1️⃣ Generazione Testi in corso...")
    
    try:
        res_text = model.generate_content(prompt_text, generation_config={"response_mime_type": "application/json"})
        data = json.loads(res_text.text)
        st.success("✅ Testi generati.")
        
        # Scrittura Testi
        if slide.shapes.title:
            slide.shapes.title.text = data.get("format_name", "")
        else:
            for s in slide.placeholders:
                if s.has_text_frame: 
                    s.text = data.get("format_name", "")
                    break
        
        for s in slide.placeholders:
            if s.has_text_frame and s != slide.shapes.title and s.text != data.get("format_name", ""):
                s.text = data.get("claim", "")
                break
        
        # 3. Generazione Immagine (Usa il modello passato come parametro)
        img_prompt = data.get("imagen_prompt")
        if img_prompt:
            st.info(f"2️⃣ Generazione Immagine con **{imagen_model}**...")
            
            img_bytes = generate_image_with_imagen(img_prompt, api_key, imagen_model)
            
            if img_bytes:
                st.success("✅ Immagine creata! Inserimento...")
                
                inserted = False
                for shape in slide.placeholders:
                    if shape.placeholder_format.type in [18, 7]: 
                        try:
                            image_stream = io.BytesIO(img_bytes)
                            shape.insert_picture(image_stream)
                            inserted = True
                            break
                        except: pass
                
                if not inserted:
                    image_stream = io.BytesIO(img_bytes)
                    slide.shapes.add_picture(image_stream, Inches(0), Inches(0), height=Inches(7.5))

            else:
                st.error("❌ Generazione immagine fallita.")
        
    except Exception as e:
        st.error(f"❌ ERRORE CRITICO: {e}")
