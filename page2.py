import streamlit as st
import google.generativeai as genai
import json
import requests
import io
from pptx.util import Inches

# --- 1. ANALISI TESTO (Scenario/Concept) ---
def analyze_content(context, gemini_model):
    try:
        model = genai.GenerativeModel(gemini_model)
        prompt_text = f"""
        Sei un Copywriter per eventi aziendali. Stiamo scrivendo la PAGINA 2: LO SCENARIO / CONCEPT.
        
        Analizza il testo e restituisci:
        1. "format_name": Il nome del format (Titolo slide).
        2. "subtitle": Un titolo breve per la sezione (es: "L'Obiettivo", "Lo Scenario", "La Missione").
        3. "body": Una descrizione coinvolgente di cosa succede (max 400 caratteri).
        4. "imagen_prompt": Un prompt per un'immagine che illustri l'azione o il setting dell'attività (fotorealistico).

        RISPONDI SOLO JSON: 
        {{
            "format_name": "...", 
            "subtitle": "...", 
            "body": "...", 
            "imagen_prompt": "..."
        }}

        TESTO SORGENTE: {context[:6000]}
        """
        res_text = model.generate_content(prompt_text, generation_config={"response_mime_type": "application/json"})
        return json.loads(res_text.text)
    except Exception as e:
        st.error(f"Errore Analisi Page 2: {e}")
        return None

# --- 2. GENERAZIONE IMMAGINE (Standard) ---
def generate_image(prompt, api_key, model_name):
    if not model_name.startswith("models/"): model_name = f"models/{model_name}"
    url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:predict?key={api_key}"
    headers = {"Content-Type": "application/json"}
    data = {"instances": [{"prompt": prompt}], "parameters": {"aspectRatio": "4:3", "sampleCount": 1}} # 4:3 spesso meglio per slide interne
    
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

# --- 3. INSERIMENTO NELLA SLIDE (Semplice & Diretto) ---
def insert_into_slide(slide, data, img_bytes):
    try:
        # A. TITOLO
        if slide.shapes.title:
            slide.shapes.title.text = data.get("format_name", "")
        
        # B. TESTI (Sottotitolo e Corpo)
        # Cerchiamo tutti i placeholder di testo (escluso il titolo)
        text_placeholders = [s for s in slide.placeholders if s.has_text_frame and s != slide.shapes.title]
        
        # Ordiniamo dall'alto in basso (Top position)
        text_placeholders.sort(key=lambda x: x.top)
        
        if len(text_placeholders) >= 2:
            # Se ne abbiamo 2: il primo è il sottotitolo, il secondo è il corpo
            text_placeholders[0].text = data.get("subtitle", "")
            text_placeholders[1].text = data.get("body", "")
        elif len(text_placeholders) == 1:
            # Se ne abbiamo solo 1: uniamo tutto
            text_placeholders[0].text = f"{data.get('subtitle', '').upper()}\n\n{data.get('body', '')}"
            
        # C. IMMAGINE (Inserimento nel placeholder o a lato)
        if img_bytes:
            image_stream = io.BytesIO(img_bytes)
            inserted = False
            
            # Cerca placeholder immagine (Type 18 = Picture)
            for shape in slide.placeholders:
                if shape.placeholder_format.type == 18:
                    shape.insert_picture(image_stream)
                    inserted = True
                    break
            
            # Fallback: Se non c'è un placeholder immagine specifico, cerchiamo un placeholder generico vuoto
            if not inserted:
                for shape in slide.placeholders:
                    # Type 7 = Body (spesso usato per contenuto misto) e se è vuoto
                    if shape.placeholder_format.type == 7 and not shape.has_text_frame:
                         shape.insert_picture(image_stream)
                         inserted = True
                         break
            
            # Ultimo Fallback: Aggiungi immagine come oggetto libero
            if not inserted:
                # La mettiamo in basso a destra come default
                slide.shapes.add_picture(image_stream, Inches(8), Inches(2), width=Inches(4))

        return True
    except Exception as e:
        st.error(f"Errore scrittura Page 2: {e}")
        return False
