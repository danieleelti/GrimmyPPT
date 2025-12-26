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
        # 1. INSERIMENTO IMMAGINE (SFONDO)
        # La inseriamo PRIMA di tutto, così sta sotto.
        if img_bytes:
            image_stream = io.BytesIO(img_bytes)
            pic = slide.shapes.add_picture(image_stream, Inches(0), Inches(0), width=Inches(13.333), height=Inches(7.5))
            # Spostiamo indietro (livello 1) per sicurezza
            try:
                slide.shapes._spTree.remove(pic._element)
                slide.shapes._spTree.insert(1, pic._element)
            except: pass

        # 2. SOSTITUZIONE TESTI (METODO "TROVA E SOSTITUISCI")
        # Invece di cercare il placeholder per tipo, cerchiamo TUTTI i box di testo
        # e vediamo qual è il titolo e quale il claim in base alla posizione.
        
        shapes_with_text = []
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text.strip() != "":
                shapes_with_text.append(shape)
        
        # Ordiniamo per altezza (Y): Quello più in alto è il titolo, quello sotto è il claim
        shapes_with_text.sort(key=lambda x: x.top)
        
        title_written = False
        claim_written = False
        
        # A. TITOLO (Il primo in alto o quello che si chiama Title)
        if slide.shapes.title:
            target = slide.shapes.title
        elif len(shapes_with_text) > 0:
            target = shapes_with_text[0]
        else:
            target = None

        if target:
            # PORTA IN PRIMO PIANO
            slide.shapes._spTree.remove(target.element)
            slide.shapes._spTree.append(target.element)
            # SCRIVI
            target.text_frame.paragraphs[0].text = data.get("format_name", "FORMAT NAME")
            title_written = True
        
        # B. CLAIM (Il secondo in alto, o quello che contiene "Subtitle")
        claim_target = None
        
        # Cerchiamo un candidato valido per il claim
        for shape in shapes_with_text:
            if shape == target: continue # Salta il titolo già usato
            # Se troviamo un box che sembra un sottotitolo
            claim_target = shape
            break # Prendiamo il primo disponibile sotto il titolo
            
        if claim_target:
             # PORTA IN PRIMO PIANO
            slide.shapes._spTree.remove(claim_target.element)
            slide.shapes._spTree.append(claim_target.element)
            # SCRIVI
            claim_target.text_frame.paragraphs[0].text = data.get("claim", "CLAIM")
            claim_written = True
        
        # Se non abbiamo trovato dove scrivere, creiamo box nuovi (Extrema Ratio)
        if not title_written:
            tb = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(10), Inches(2))
            tb.text_frame.text = data.get("format_name", "")
            tb.text_frame.paragraphs[0].font.size = Pt(50)
            tb.text_frame.paragraphs[0].font.bold = True
            
        if not claim_written:
            tb = slide.shapes.add_textbox(Inches(1), Inches(4), Inches(10), Inches(1))
            tb.text_frame.text = data.get("claim", "")
            tb.text_frame.paragraphs[0].font.size = Pt(24)

        return True
    except Exception as e:
        st.error(f"Errore Page 1: {e}")
        return False
