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
        Sei un Copywriter. Pagina 2: SCENARIO.
        JSON RICHIESTO:
        1. "format_name": Nome del format.
        2. "emotional_text": Testo emozionale (Max 300 caratteri).
        3. "imagen_prompt": Prompt immagine sfondo 16:9.

        RISPONDI SOLO JSON: {{"format_name": "...", "emotional_text": "...", "imagen_prompt": "..."}}
        TESTO: {context[:6000]}
        """
        res_text = model.generate_content(prompt_text, generation_config={"response_mime_type": "application/json"})
        return json.loads(res_text.text)
    except Exception as e:
        st.error(f"Errore Analisi Page 2: {e}")
        return None

def generate_image(prompt, api_key, model_name):
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

def insert_into_slide(slide, data, img_bytes):
    try:
        # 1. IMMAGINE (SUBITO SOTTO)
        if img_bytes:
            image_stream = io.BytesIO(img_bytes)
            pic = slide.shapes.add_picture(image_stream, Inches(0), Inches(0), width=Inches(13.333), height=Inches(7.5))
            try:
                slide.shapes._spTree.remove(pic._element)
                slide.shapes._spTree.insert(1, pic._element) # Livello 1 = Fondo sicuro
            except: pass

        # 2. TITOLO (Cerca "MASTER TITLE STYLE" o Placeholders Titolo)
        title_found = False
        if slide.shapes.title:
            target = slide.shapes.title
        else:
            # Cerca per testo contenuto
            candidates = [s for s in slide.shapes if s.has_text_frame and "TITLE" in s.text_frame.text.upper()]
            target = candidates[0] if candidates else None
            
        if target:
            slide.shapes._spTree.remove(target.element); slide.shapes._spTree.append(target.element) # Bring to front
            target.text_frame.paragraphs[0].text = data.get("format_name", "")
            title_found = True

        # 3. TESTO EMOZIONALE (Cerca "Edit text" o il box più grande)
        text_found = False
        text_candidates = []
        
        for shape in slide.shapes:
            if shape.has_text_frame and shape != target:
                txt = shape.text_frame.text.strip().lower()
                # Criterio 1: Contiene "edit text"
                if "edit" in txt or "text" in txt:
                    text_candidates.insert(0, shape) # Priorità massima
                # Criterio 2: È un placeholder Body
                elif shape.is_placeholder and shape.placeholder_format.type == 7: # Body
                    text_candidates.append(shape)
                # Criterio 3: È un box grande generico
                elif shape.width > Inches(3):
                    text_candidates.append(shape)

        if text_candidates:
            # Prende il primo candidato migliore
            target_text = text_candidates[0]
            
            # Bring to front
            slide.shapes._spTree.remove(target_text.element); slide.shapes._spTree.append(target_text.element)
            
            # Scrittura Preservando Formattazione
            tf = target_text.text_frame
            # Se c'è almeno un paragrafo, usiamo quello per mantenere il corsivo
            if len(tf.paragraphs) > 0:
                p = tf.paragraphs[0]
                p.text = data.get("emotional_text", "") 
                # Nota: assegnando a p.text, lo stile del paragrafo (es. Corsivo) dovrebbe restare.
                # Se assegnassimo a tf.text, resetterebbe tutto.
            else:
                tf.text = data.get("emotional_text", "")
            
            text_found = True
            st.toast("Testo P2 inserito!", icon="✅")

        # Fallback se non trova nulla
        if not text_found:
            st.warning("Box testo non trovato. Ne creo uno.")
            tb = slide.shapes.add_textbox(Inches(1), Inches(2.5), Inches(10), Inches(3))
            p = tb.text_frame.add_paragraph()
            p.text = data.get("emotional_text", "")
            p.font.size = Pt(24)
            p.font.italic = True # Forziamo corsivo

        return True
    except Exception as e:
        st.error(f"Errore Scrittura P2: {e}")
        return False
