import streamlit as st
import google.generativeai as genai
import json
import requests
import io
from pptx.util import Inches
from pptx.opc.constants import RELATIONSHIP_TYPE as RT

# --- 1. ANALISI TESTO ---
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

# --- 2. GENERAZIONE IMMAGINE ---
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

# --- 3. INSERIMENTO NEL PPT (FIX TESTI + Z-ORDER) ---
def insert_content_into_ppt(slide, data, img_bytes):
    try:
        # A. INSERIMENTO TESTI (Logica Robusta per Posizione)
        # 1. Titolo Principale (Cerca shape Titolo o usa il primo placeholder in alto)
        if slide.shapes.title:
            slide.shapes.title.text = data.get("format_name", "")
        
        # 2. Claim (Sottotitolo)
        # Raccogliamo tutti i placeholder di testo che NON sono il titolo
        text_placeholders = [s for s in slide.placeholders if s.has_text_frame and s != slide.shapes.title]
        # Li ordiniamo dall'alto verso il basso (così il primo sotto il titolo è sicuramente il claim)
        text_placeholders.sort(key=lambda x: x.top)
        
        if text_placeholders:
            # Scriviamo il Claim nel primo box disponibile sotto il titolo
            text_placeholders[0].text = data.get("claim", "")

        # B. INSERIMENTO IMMAGINE (Chirurgia Layout + Fallback Sicuro)
        if img_bytes:
            layout = slide.slide_layout
            image_stream = io.BytesIO(img_bytes)
            
            # Coordinate target (cerca nel layout o usa full screen)
            target_left, target_top = Inches(0), Inches(0)
            target_width, target_height = Inches(13.333), Inches(7.5)
            
            for shape in layout.placeholders:
                if shape.placeholder_format.type in [18, 7]: # Picture or Body
                    target_left, target_top = shape.left, shape.top
                    target_width, target_height = shape.width, shape.height
                    break

            # 1. Aggiungi alla SLIDE (temporaneamente o definitivamente)
            pic = slide.shapes.add_picture(image_stream, target_left, target_top, target_width, target_height)
            
            # 2. Tentativo di Spostamento nel LAYOUT (Sfondo Fisso)
            moved_to_layout = False
            try:
                rId_slide = pic.element.blipFill.blip.embed
                image_part = slide.part.related_part(rId_slide)
                rId_layout = layout.part.relate_to(image_part, RT.IMAGE)
                pic.element.blipFill.blip.embed = rId_layout
                
                # Sposta XML da Slide a Layout
                slide.shapes._spTree.remove(pic.element)
                layout.shapes._spTree.insert(2, pic.element) # Indice 2 = Sfondo Layout
                moved_to_layout = True
            except Exception:
                # Se la chirurgia fallisce, l'immagine è ancora sulla Slide (ma sopra il testo!)
                moved_to_layout = False

            # 3. Fallback: Se è rimasta sulla Slide, la mandiamo IN FONDO (Dietro al testo)
            if not moved_to_layout:
                try:
                    slide.shapes._spTree.remove(pic.element)
                    slide.shapes._spTree.insert(2, pic.element) # Indice 2 = Sfondo Slide (Dietro i testi)
                except:
                    pass

        return True
    except Exception as e:
        st.error(f"Errore Page 1: {e}")
        return False
