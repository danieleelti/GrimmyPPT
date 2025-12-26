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
    # Gestione nome modello
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

# --- FUNZIONE 3: INSERIMENTO NEL PPT (FIX SCHEMA DIAPOSITIVA) ---
def insert_content_into_ppt(slide, data, img_bytes):
    """
    Inserisce testi nella slide e l'immagine DIRETTAMENTE NEL LAYOUT (Schema).
    """
    try:
        # 1. INSERIMENTO TESTI (Nella slide normale)
        # Titolo
        if slide.shapes.title: 
            slide.shapes.title.text = data.get("format_name", "")
        else:
            # Fallback se non trova il titolo standard
            for s in slide.placeholders:
                if s.has_text_frame: 
                    s.text = data.get("format_name", "")
                    break
        
        # Claim
        for s in slide.placeholders:
            if s.has_text_frame and s != slide.shapes.title and s.text != data.get("format_name", ""):
                s.text = data.get("claim", "")
                break
        
        # 2. INSERIMENTO IMMAGINE NEL LAYOUT (SCHEMA)
        if img_bytes:
            # Recuperiamo lo schema (layout) usato da questa slide
            layout = slide.slide_layout
            target_placeholder = None
            
            # Cerchiamo il placeholder immagine nello SCHEMA per prenderne le coordinate
            for shape in layout.placeholders:
                # Tipo 18 (Picture) o 7 (Object/Body)
                if shape.placeholder_format.type in [18, 7]:
                    target_placeholder = shape
                    break
            
            image_stream = io.BytesIO(img_bytes)
            
            if target_placeholder:
                # PRENDIAMO LE COORDINATE DEL SEGNAPOSTO
                left = target_placeholder.left
                top = target_placeholder.top
                width = target_placeholder.width
                height = target_placeholder.height
                
                # AGGIUNGIAMO L'IMMAGINE ALLO SCHEMA (Come forma semplice, non nel placeholder)
                # Questo risolve l'errore "LayoutPlaceholder object has no attribute insert_picture"
                pic = layout.shapes.add_picture(image_stream, left, top, width, height)
                
                # (Opzionale) Spostiamo l'immagine indietro nello stack XML dello schema 
                # per evitare che copra altri elementi fissi dello schema
                # Sposta l'elemento immagine all'inizio della lista delle shape
                try:
                    layout.shapes._spTree.remove(pic._element)
                    layout.shapes._spTree.insert(2, pic._element) # Indice 2 per non rompere lo sfondo base
                except:
                    pass # Se fallisce lo spostamento livello, rimane dove è (spesso va bene comunque)

            else:
                st.warning("⚠️ Segnaposto immagine non trovato nello Schema. Aggiungo l'immagine come sfondo a pagina intera nello Schema.")
                # Fallback: Immagine a tutto schermo nel layout
                pic = layout.shapes.add_picture(image_stream, Inches(0), Inches(0), height=Inches(7.5))
                # Sposta indietro
                try:
                    layout.shapes._spTree.remove(pic._element)
                    layout.shapes._spTree.insert(2, pic._element)
                except: pass

        return True
    except Exception as e:
        st.error(f"Errore critico inserimento PPT: {e}")
        return False
