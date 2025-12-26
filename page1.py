import streamlit as st
import google.generativeai as genai
import json
import requests
import io
from pptx.util import Inches

# --- FUNZIONE 1: ANALISI TESTO ---
def analyze_content(context, gemini_model):
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

# --- FUNZIONE 2: GENERAZIONE IMMAGINE ---
def generate_image_with_imagen(prompt, api_key, model_name):
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

# --- FUNZIONE 3: INSERIMENTO NEL PPT (FIX SALVA FILE) ---
def insert_content_into_ppt(slide, data, img_bytes):
    """
    Inserisce i contenuti e gestisce l'immagine di sfondo senza corrompere l'XML.
    """
    try:
        # 1. TESTI
        if slide.shapes.title: 
            slide.shapes.title.text = data.get("format_name", "")
        else:
            for s in slide.placeholders:
                if s.has_text_frame: s.text = data.get("format_name", ""); break
        
        for s in slide.placeholders:
            if s.has_text_frame and s != slide.shapes.title and s.text != data.get("format_name", ""):
                s.text = data.get("claim", ""); break
        
        # 2. IMMAGINE (FIX "SEND TO BACK" SICURO)
        if img_bytes:
            layout = slide.slide_layout
            
            # A. CERCA LE COORDINATE DAL LAYOUT
            target_ph = None
            for shape in layout.placeholders:
                if shape.placeholder_format.type in [18, 7]: # Picture or Body
                    target_ph = shape
                    break
            
            image_stream = io.BytesIO(img_bytes)
            pic = None

            # B. AGGIUNGI IMMAGINE ALLA SLIDE
            if target_ph:
                pic = slide.shapes.add_picture(image_stream, target_ph.left, target_ph.top, target_ph.width, target_ph.height)
            else:
                # Fallback tutto schermo
                pic = slide.shapes.add_picture(image_stream, Inches(0), Inches(0), height=Inches(7.5))
            
            # C. SPOSTA DIETRO (SAFE MODE)
            # NON usare index 0 (corrompe il file). Usiamo un metodo più sicuro.
            # Spostiamo l'elemento XML alla posizione 2, che solitamente è dopo le proprietà di base ma prima degli altri oggetti.
            try:
                slide.shapes._spTree.remove(pic._element)
                # L'indice 2 è statisticamente sicuro per PPTX (salta nvGrpSpPr e grpSpPr)
                # Se la slide è molto semplice, anche 1 va bene, ma 2 è safe.
                slide.shapes._spTree.insert(2, pic._element) 
            except Exception as e:
                st.warning(f"Impossibile spostare l'immagine sullo sfondo (Z-Order): {e}")
                # Se fallisce lo spostamento, l'immagine rimane, solo che copre il testo.
                # Meglio un PPT che si apre con l'immagine sopra, piuttosto che uno corrotto.

        return True
    except Exception as e:
        st.error(f"Errore critico PPT: {e}")
        return False
