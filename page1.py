import streamlit as st
import google.generativeai as genai
import json

def process(slide, context, model_name):
    """
    LOGICA PAGE 1 - COVER
    Riceve il modello esatto selezionato dall'utente nella sidebar.
    """
    
    st.divider()
    st.markdown(f"### 🔵 AVVIO COVER con `{model_name}`")
    
    # Istanzia il modello scelto dalla tendina
    try:
        model = genai.GenerativeModel(model_name)
    except Exception as e:
        st.error(f"❌ Impossibile caricare il modello {model_name}: {e}")
        return

    prompt = f"""
    Sei un esperto copywriter. Analizza il testo per la COVER del PowerPoint.
    
    COMPITI:
    1. Trova il NOME DEL FORMAT (Copia incolla esatto).
    2. Scrivi un CLAIM (Slogan) di vendita potente.
    3. Scrivi un PROMPT per immagine di sfondo (Imagen 3).

    RISPONDI SOLO JSON:
    {{
        "format_name": "Nome Format",
        "claim": "Slogan",
        "imagen_prompt": "Descrizione immagine"
    }}

    TESTO SORGENTE:
    {context[:5000]}
    """
    
    st.write("...Invio richiesta all'AI...")
    
    try:
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        data = json.loads(response.text)
        st.success("✅ Risposta ricevuta!")
        st.json(data) # Debug visivo
        
        # --- SCRITTURA ---
        # 1. Titolo
        if slide.shapes.title:
            slide.shapes.title.text = data.get("format_name", "")
        else:
            # Fallback se non trova il placeholder titolo standard
            for s in slide.placeholders:
                if s.has_text_frame: 
                    s.text = data.get("format_name", "")
                    break

        # 2. Claim (secondo placeholder)
        claim_done = False
        for s in slide.placeholders:
            if s.has_text_frame and s != slide.shapes.title and s.text != data.get("format_name", ""):
                s.text = data.get("claim", "")
                claim_done = True
                break
        
        if not claim_done: st.warning("⚠️ Non ho trovato un box per il Claim")

        # 3. Prompt Immagine (Note)
        if not slide.has_notes_slide: 
            slide.notes_slide = slide.part.presentation.slides._library.add_notes_slide(slide.part, slide.part.slide_layout)
        slide.notes_slide.notes_text_frame.text = f"PROMPT: {data.get('imagen_prompt')}"

    except Exception as e:
        st.error(f"❌ ERRORE GENERAZIONE: {e}")
