import streamlit as st
import google.generativeai as genai
import json
import requests
import io
from pptx.util import Inches

# --- 1. ANALISI TESTO (Scenario Emozionale) ---
def analyze_content(context, gemini_model):
    try:
        model = genai.GenerativeModel(gemini_model)
        prompt_text = f"""
        Sei un Copywriter creativo. Stiamo scrivendo la PAGINA 2: LO SCENARIO (CONCEPT).
        
        Analizza il testo e restituisci:
        1. "format_name": Il nome del format (Titolo slide).
        2. "emotional_text": Un testo EVOCATIVO, EMOZIONALE e ISPIRAZIONALE che descriva l'atmosfera del format. (Sarà scritto in corsivo nel template, quindi usa un tono elegante e coinvolgente). Max 2-3 frasi.
        3. "imagen_prompt": Un prompt per un'immagine di SFONDO A TUTTA PAGINA. Deve essere atmosferica, ampia e cinematografica.

        RISPONDI SOLO JSON: 
        {{
            "format_name": "...", 
            "emotional_text": "...", 
            "imagen_prompt": "..."
        }}

        TESTO SORGENTE: {context[:6000]}
        """
        res_text = model.generate_content(prompt_text, generation_config={"response_mime_type": "application/json"})
        return json.loads(res_text.text)
    except Exception as e:
        st.error(f"Errore Analisi Page 2: {e}")
        return None

# --- 2. GENERAZIONE IMMAGINE ---
def generate_image(prompt, api_key, model_name):
    # Gestione nome modello
    if not model_name.startswith("models/"): model_name = f"models/{model_name}"
    
    url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:predict?key={api_key}"
    headers = {"Content-Type": "application/json"}
    # Usiamo 16:9 per lo sfondo a tutto schermo
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
        st.error(f"Errore Imagen Page 2: {e}")
        return None

# --- 3. INSERIMENTO NELLA SLIDE (Sfondo Full Page + Testo) ---
def insert_into_slide(slide, data, img_bytes):
    try:
        # A. TITOLO
        if slide.shapes.title:
            slide.shapes.title.text = data.get("format_name", "")
        
        # B. TESTO EMOZIONALE (Placeholder Corsivo)
        # Cerchiamo i placeholder di testo. Nel tuo screenshot c'è un grosso box "Edit text".
        # Escludiamo il titolo.
        text_placeholders = [s for s in slide.placeholders if s.has_text_frame and s != slide.shapes.title]
        
        if text_placeholders:
            # Il primo placeholder trovato sarà quello del testo emozionale
            # Nota: Assegnare .text mantiene il font del paragrafo se il placeholder è ben fatto,
            # ma resetta le formattazioni locali. Poiché il tuo template ha il corsivo nello stile, dovrebbe funzionare.
            text_placeholders[0].text = data.get("emotional_text", "")
            
        # C. IMMAGINE DI SFONDO (Z-Order Fix)
        if img_bytes:
            image_stream = io.BytesIO(img_bytes)
            
            # 1. Inserisci a tutto schermo (copre tutto inizialmente)
            # Dimensioni standard PPT 16:9 = 13.333 x 7.5 pollici
            pic = slide.shapes.add_picture(image_stream, Inches(0), Inches(0), width=Inches(13.333), height=Inches(7.5))
            
            # 2. Sposta DIETRO (Send to Back)
            # Indice 2: Subito dopo le proprietà della slide, ma prima di Titoli e Testi (che solitamente sono indici più alti)
            try:
                slide.shapes._spTree.remove(pic._element)
                slide.shapes._spTree.insert(2, pic._element)
            except Exception as e:
                st.warning(f"Impossibile spostare lo sfondo in secondo piano: {e}")

        return True
    except Exception as e:
        st.error(f"Errore scrittura Page 2: {e}")
        return False
