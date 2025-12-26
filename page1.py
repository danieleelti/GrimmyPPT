import streamlit as st
import google.generativeai as genai
import json
import requests
import io
from pptx.util import Inches, Pt

def analyze_content(context, gemini_model):
    try:
        model = genai.GenerativeModel(gemini_model)
        prompt_text = f"""
        Sei un Art Director. COMPITI:
        1. NOME FORMAT: Estrailo ESATTO dal testo.
        2. CLAIM: Crea uno slogan commerciale potente (max 10 parole).
        3. PROMPT IMMAGINE: Scrivi un prompt DETTAGLIATO in inglese per una copertina FOTOREALISTICA.

        RISPONDI SOLO JSON: {{"format_name": "...", "claim": "...", "imagen_prompt": "..."}}

        TESTO SORGENTE: {context[:5000]}
        """
        res_text = model.generate_content(prompt_text, generation_config={"response_mime_type": "application/json"})
        return json.loads(res_text.text)
    except Exception as e:
        st.error(f"Errore Analisi Gemini: {e}")
        return None

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

def insert_content_into_ppt(slide, data, img_bytes):
    try:
        # 1. IMMAGINE (Tentativo Safe)
        if img_bytes:
            try:
                image_stream = io.BytesIO(img_bytes)
                pic = slide.shapes.add_picture(image_stream, Inches(0), Inches(0), width=Inches(13.333), height=Inches(7.5))
                # Tentativo di spostare indietro
                slide.shapes._spTree.remove(pic._element)
                slide.shapes._spTree.insert(1, pic._element)
            except Exception as e:
                print(f"Warning Z-Order Img P1: {e}")
                # Se fallisce lo spostamento, fa nulla. L'immagine resta dov'è.

        # 2. TESTI (Metodo Safe)
        # Cerchiamo tutti i box testo
        text_shapes = []
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text.strip() != "":
                text_shapes.append(shape)
        
        # Ordina per altezza (Titolo in alto, Claim sotto)
        text_shapes.sort(key=lambda x: x.top)
        
        # Scrittura Titolo
        if text_shapes:
            t = text_shapes[0]
            # Porta in primo piano (Safe)
            try:
                slide.shapes._spTree.remove(t.element)
                slide.shapes._spTree.append(t.element)
            except: pass
            
            t.text_frame.paragraphs[0].text = data.get("format_name", "")
            
        # Scrittura Claim
        if len(text_shapes) > 1:
            c = text_shapes[1]
            try:
                slide.shapes._spTree.remove(c.element)
                slide.shapes._spTree.append(c.element)
            except: pass
            
            c.text_frame.paragraphs[0].text = data.get("claim", "")
            
        return True
    except Exception as e:
        st.error(f"Errore critico Page 1: {e}")
        # Ritorniamo False ma NON crashiamo l'app
        return False
