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
        # 1. IMMAGINE (SAFE)
        if img_bytes:
            try:
                image_stream = io.BytesIO(img_bytes)
                pic = slide.shapes.add_picture(image_stream, Inches(0), Inches(0), width=Inches(13.333), height=Inches(7.5))
                slide.shapes._spTree.remove(pic._element)
                slide.shapes._spTree.insert(1, pic._element)
            except Exception as e:
                print(f"Z-Order Error P2: {e}")
                # Continua anche se fallisce lo spostamento

        # 2. CERCA IL TITOLO
        title_shape = None
        if slide.shapes.title:
            title_shape = slide.shapes.title
        else:
            # Cerca shape che contiene "TITLE"
            for s in slide.shapes:
                if s.has_text_frame and "TITLE" in s.text.upper():
                    title_shape = s
                    break
        
        if title_shape:
            # Porta su e Scrivi
            try:
                slide.shapes._spTree.remove(title_shape.element)
                slide.shapes._spTree.append(title_shape.element)
            except: pass
            
            # Scrivi Titolo
            try:
                title_shape.text_frame.paragraphs[0].text = data.get("format_name", "")
            except:
                title_shape.text = data.get("format_name", "")

        # 3. CERCA IL TESTO "EDIT TEXT" (Logica Fallback Multipla)
        target_text_shape = None
        
        # A. Cerca parola chiave specifica
        for s in slide.shapes:
            if s.has_text_frame and s != title_shape:
                txt = s.text.strip().lower()
                if "edit" in txt or "text" in txt or "subtitle" in txt:
                    target_text_shape = s
                    break
        
        # B. Se non trova, cerca il Placeholder BODY (tipo 7)
        if not target_text_shape:
            for s in slide.placeholders:
                if s.placeholder_format.type == 7: # Body
                    target_text_shape = s
                    break
                    
        # C. Se non trova, cerca il box più grande rimasto
        if not target_text_shape:
            candidates = [s for s in slide.shapes if s.has_text_frame and s != title_shape and s.width > Inches(2)]
            if candidates:
                target_text_shape = max(candidates, key=lambda x: x.width * x.height)

        # SCRITTURA TESTO
        if target_text_shape:
            # Porta su
            try:
                slide.shapes._spTree.remove(target_text_shape.element)
                slide.shapes._spTree.append(target_text_shape.element)
            except: pass
            
            # Scrivi (Preservando lo stile del primo paragrafo se esiste)
            tf = target_text_shape.text_frame
            if len(tf.paragraphs) > 0:
                tf.paragraphs[0].text = data.get("emotional_text", "")
            else:
                tf.text = data.get("emotional_text", "")
            
            # Feedback positivo nascosto (o toast se vuoi)
            # st.toast("Testo P2 Scritto!", icon="✅")
        
        else:
            # ULTIMA SPIAGGIA: Crea box nuovo
            st.warning("P2: Box testo non trovato. Creazione manuale.")
            tb = slide.shapes.add_textbox(Inches(1), Inches(3), Inches(10), Inches(3))
            p = tb.text_frame.add_paragraph()
            p.text = data.get("emotional_text", "")
            p.font.size = Pt(24)
            p.font.italic = True

        return True
    except Exception as e:
        st.error(f"Errore critico scrittura P2: {e}")
        return False # Non crashare l'app
