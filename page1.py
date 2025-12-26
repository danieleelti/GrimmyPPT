import streamlit as st
import google.generativeai as genai
import json

def process(slide, context):
    """
    LOGICA ESCLUSIVA PER LA COVER (Pagina 1) - VERSIONE DEBUG VISIVO
    """
    st.divider()
    st.markdown("### 🕵️‍♂️ DEBUG PAGE 1 (Cover)")
    
    # 1. VERIFICA CONTESTO
    if not context or len(context) < 10:
        st.error("❌ ERRORE CRITICO: Il testo estratto dal vecchio PPT è vuoto o troppo breve!")
        return
    else:
        st.success(f"✅ Testo sorgente letto: {len(context)} caratteri.")

    # 2. CONFIGURAZIONE MODELLO
    # Nota: Se il tuo account non ha accesso a 'gemini-3.0-pro', questo darà errore.
    # Proviamo con una lista di priorità.
    model_name = "gemini-1.5-pro" # Usiamo il 1.5 come base sicura per testare il flusso. Se funziona, cambieremo in 3.0.
    
    st.info(f"🤖 Tentativo connessione AI con modello: `{model_name}`...")
    
    try:
        model = genai.GenerativeModel(model_name)
        
        prompt = f"""
        Sei un esperto di Marketing. 
        Analizza questo testo e estrai i dati per la COPERTINA.
        
        Rispondi ESCLUSIVAMENTE con questo JSON:
        {{
            "format_name": "Nome esatto del format (copialo dal testo)",
            "claim": "Slogan commerciale breve (max 6 parole)",
            "imagen_prompt": "Descrizione immagine sfondo (in inglese)"
        }}
        
        TESTO:
        {context[:3000]} 
        """
        # (Taglio il contesto a 3000 caratteri per sicurezza in questo test)
        
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        data = json.loads(response.text)
        st.success("✅ Gemini ha risposto! Dati generati:")
        st.json(data) # Mostra a video il JSON per conferma
        
    except Exception as e:
        st.error(f"❌ ERRORE CHIAMATA AI: {e}")
        return # Si ferma qui se l'AI fallisce

    # 3. SCRITTURA NEL PPT (DIAGNOSTICA)
    st.markdown("#### ✏️ Scrittura nel Template...")
    
    try:
        # A. TITOLO
        if slide.shapes.title:
            old_title = slide.shapes.title.text
            slide.shapes.title.text = data.get("format_name", "NOME NON TROVATO")
            st.write(f"🔹 Titolo aggiornato: da `{old_title}` a `{slide.shapes.title.text}`")
        else:
            st.warning("⚠️ ATTENZIONE: Nessun 'Titolo Slide' standard trovato nel layout.")

        # B. CLAIM (CERCA TUTTI I SEGNAPOSTO)
        st.write("🔎 Cerco segnaposto per il Claim...")
        found_claim_spot = False
        
        for i, shape in enumerate(slide.placeholders):
            # Info di debug per ogni shape trovata
            st.caption(f"Box {i}: idx={shape.placeholder_format.idx}, type={shape.placeholder_format.type}, ha_testo={shape.has_text_frame}")
            
            # Se è un testo e NON è il titolo, ci scriviamo il claim
            if shape.has_text_frame and shape != slide.shapes.title:
                shape.text = data.get("claim", "CLAIM DEFAULT")
                st.write(f"✅ Claim scritto nel Box {i} (idx {shape.placeholder_format.idx})")
                found_claim_spot = True
                break # Ci fermiamo al primo trovato
        
        if not found_claim_spot:
            st.error("❌ NON HO TROVATO NESSUN BOX DI TESTO PER IL CLAIM (a parte il titolo).")

        # C. PROMPT IMMAGINE (NOTE)
        if not slide.has_notes_slide:
            slide.notes_slide = slide.part.presentation.slides._library.add_notes_slide(slide.part, slide.part.slide_layout)
        slide.notes_slide.notes_text_frame.text = f"PROMPT: {data.get('imagen_prompt')}"
        st.success("✅ Prompt salvato nelle note della slide.")

    except Exception as e:
        st.error(f"❌ Errore durante la scrittura nel PPT: {e}")

    st.divider()
