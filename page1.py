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

# --- FUNZIONE 3: INSERIMENTO NEL PPT (FIX DEFINITIVO) ---
def insert_content_into_ppt(slide, data, img_bytes):
    """
    Inserisce l'immagine nella Slide alle coordinate dello Schema e la manda in fondo.
    """
    try:
        # 1. INSERIMENTO TESTI
        if slide.shapes.title: 
            slide.shapes.title.text = data.get("format_name", "")
        else:
            for s in slide.placeholders:
                if s.has_text_frame: s.text = data.get("format_name", ""); break
        
        for s in slide.placeholders:
            if s.has_text_frame and s != slide.shapes.title and s.text != data.get("format_name", ""):
                s.text = data.get("claim", ""); break
        
        # 2. GESTIONE IMMAGINE (GEOMETRIA SCHEMA + Z-ORDER)
        if img_bytes:
            # Recuperiamo il Layout (Schema) per leggere DOVE deve andare l'immagine
            layout = slide.slide_layout
            target_placeholder = None
            
            # Cerchiamo il placeholder nello schema
            for shape in layout.placeholders:
                if shape.placeholder_format.type in [18, 7]: # Picture o Object
                    target_placeholder = shape
                    break
            
            image_stream = io.BytesIO(img_bytes)
            
            if target_placeholder:
                # A. COPIAMO LE COORDINATE DALLO SCHEMA
                left = target_placeholder.left
                top = target_placeholder.top
                width = target_placeholder.width
                height = target_placeholder.height
                
                # B. INSERIAMO NELLA SLIDE (NON NEL LAYOUT)
                # Questo evita l'errore 'LayoutShapes object has no attribute add_picture'
                pic = slide.shapes.add_picture(image_stream, left, top, width, height)
                
                # C. SPOSTIAMO IN SECONDO PIANO (Send to Back)
                # Spostiamo l'elemento XML all'inizio della lista shapes (indice 0 = sfondo)
                try:
                    slide.shapes._spTree.remove(pic._element)
                    slide.shapes._spTree.insert(0, pic._element)
                except Exception as e:
                    st.warning(f"Z-Order non applicato perfettamente: {e}")
                    
            else:
                st.warning("⚠️ Segnaposto non trovato nello schema. Inserisco a tutto schermo come sfondo.")
                # Fallback: A tutto schermo e manda in fondo
                pic = slide.shapes.add_picture(image_stream, Inches(0), Inches(0), height=Inches(7.5))
                slide.shapes._spTree.remove(pic._element)
                slide.shapes._spTree.insert(0, pic._element)

        return True
    except Exception as e:
        st.error(f"Errore critico inserimento PPT: {e}")
        return False
