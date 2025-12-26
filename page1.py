import streamlit as st
import google.generativeai as genai
import json
import requests
import io
from pptx.util import Inches

def generate_image_with_imagen(prompt, api_key):
    """
    Chiama direttamente l'API REST di Imagen 3 per generare l'immagine.
    Restituisce i bytes dell'immagine o None se fallisce.
    """
    # Endpoint ufficiale per Imagen 3 su Gemini API
    url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-001:predict?key={api_key}"
    
    headers = {"Content-Type": "application/json"}
    data = {
        "instances": [{"prompt": prompt}],
        "parameters": {
            "aspectRatio": "16:9", # Formato slide standard
            "sampleCount": 1
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status() # Lancia errore se c'è un codice 4xx/5xx
        
        result = response.json()
        # L'immagine arriva in base64, dobbiamo decodificarla
        if "predictions" in result:
            import base64
            b64_data = result["predictions"][0]["bytesBase64Encoded"]
            return base64.b64decode(b64_data)
        else:
            st.error(f"Errore struttura risposta Imagen: {result}")
            return None
            
    except Exception as e:
        st.error(f"Errore chiamata Imagen 3: {e}")
        return None

def process(slide, context, model_name):
    """
    LOGICA PAGE 1 - COVER COMPLETA
    Genera Testi E Immagine fisica.
    """
    st.divider()
    st.markdown(f"### 🎨 AVVIO CREAZIONE COVER (Testi + Immagine Reale)")
    
    # Recupera API Key dai secrets (necessaria per la chiamata REST immagine)
    api_key = st.secrets["GOOGLE_API_KEY"]

    # 1. Configurazione Modello Testuale
    try:
        model = genai.GenerativeModel(model_name)
    except Exception as e:
        st.error(f"❌ Errore modello testo: {e}")
        return

    # 2. Prompt per i Contenuti
    prompt_text = f"""
    Sei un Art Director e Copywriter. Stiamo facendo la COVER.
    
    COMPITI:
    1. Estrai il NOME DEL FORMAT (esatto).
    2. Crea un CLAIM (Slogan) commerciale.
    3. Scrivi un PROMPT VISIVO per Imagen 3 (in inglese, dettagliato, fotorealistico, wide shot).

    RISPONDI SOLO JSON:
    {{
        "format_name": "...",
        "claim": "...",
        "imagen_prompt": "..."
    }}

    TESTO SORGENTE:
    {context[:4000]}
    """
    
    st.info("1️⃣ Generazione Testi e Prompt Visivo in corso...")
    
    try:
        # Generazione Testi
        res_text = model.generate_content(prompt_text, generation_config={"response_mime_type": "application/json"})
        data = json.loads(res_text.text)
        st.success("✅ Testi generati.")
        
        # --- SCRITTURA TESTI NEL PPT ---
        # A. Titolo
        if slide.shapes.title:
            slide.shapes.title.text = data.get("format_name", "")
        else:
            # Fallback titolo
            for s in slide.placeholders:
                if s.has_text_frame: 
                    s.text = data.get("format_name", "")
                    break
        
        # B. Claim (Sottotitolo)
        for s in slide.placeholders:
            if s.has_text_frame and s != slide.shapes.title and s.text != data.get("format_name", ""):
                s.text = data.get("claim", "")
                break
        
        # --- GENERAZIONE E INSERIMENTO IMMAGINE ---
        img_prompt = data.get("imagen_prompt")
        if img_prompt:
            st.info(f"2️⃣ Generazione Immagine con Imagen 3...\nPrompt: *{img_prompt}*")
            
            # Chiamata alla funzione immagine
            img_bytes = generate_image_with_imagen(img_prompt, api_key)
            
            if img_bytes:
                st.success("✅ Immagine creata! Inserimento nella slide...")
                
                # Cerca il placeholder immagine
                # I placeholder immagine in PPTX hanno tipo 18 (PICTURE) o sono generici
                inserted = False
                for shape in slide.placeholders:
                    # Verifica se è un placeholder immagine (tipo 18) o generico oggetto (tipo 7)
                    # p.s. idx varia a seconda del template, cerchiamo un placeholder vuoto che non sia titolo/testo
                    if shape.placeholder_format.type in [18, 7]: # 18=Picture, 7=Body/Object
                        try:
                            # Inserisce l'immagine dallo stream di byte
                            image_stream = io.BytesIO(img_bytes)
                            shape.insert_picture(image_stream)
                            st.success(f"🖼️ Immagine inserita nel placeholder {shape.placeholder_format.idx}")
                            inserted = True
                            break
                        except Exception as e_ins:
                            st.warning(f"Impossibile inserire nel placeholder {shape.name}: {e_ins}")
                
                if not inserted:
                    st.warning("⚠️ Nessun placeholder 'Immagine' specifico trovato. Provo a mettere l'immagine sullo sfondo.")
                    # Fallback: aggiungi immagine come shape libera se non trova il placeholder
                    image_stream = io.BytesIO(img_bytes)
                    slide.shapes.add_picture(image_stream, Inches(0), Inches(0), height=Inches(7.5)) # Adatta altezza slide

            else:
                st.error("❌ Generazione immagine fallita (nessun byte ricevuto).")
        
    except Exception as e:
        st.error(f"❌ ERRORE CRITICO PAGE 1: {e}")
