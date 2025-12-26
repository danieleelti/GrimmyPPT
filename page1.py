import google.generativeai as genai
import json

def process(slide, context):
    """
    LOGICA ESCLUSIVA PER LA COVER (Pagina 1)
    Obiettivi:
    1. Inserire il NOME DEL FORMAT (senza modifiche) nel titolo.
    2. Inserire un CLAIM (slogan) nel sottotitolo.
    3. Scrivere il PROMPT PER L'IMMAGINE DI SFONDO nelle note della slide.
    """
    
    print("--- Inizio elaborazione Page 1 (Cover) ---")

    # 1. Configurazione Modello (Tenta Gemini 3, fallback su 1.5)
    # IMPORTANTE: Verifica il nome esatto del modello Gemini 3 nel tuo account.
    target_model = "gemini-3.0-pro" 
    try:
        # Tenta di configurare il modello richiesto
        model = genai.GenerativeModel(target_model)
        print(f"Utilizzo del modello: {target_model}")
    except Exception:
        # Fallback se il modello non è disponibile/trovato
        fallback_model = "gemini-1.5-pro"
        print(f"Attenzione: Modello {target_model} non trovato. Fallback su {fallback_model}.")
        model = genai.GenerativeModel(fallback_model)

    # 2. Prompt per Gemini
    prompt = f"""
    Sei un esperto di Marketing. Stai creando i contenuti per la COPERTINA di una presentazione.
    
    Analizza il testo fornito e svolgi i seguenti compiti:
    1.  **NOME FORMAT**: Trova il nome esatto del format/prodotto. Copialo FEDELMENTE, senza cambiarlo.
    2.  **CLAIM**: Inventa uno slogan commerciale breve, accattivante ed energico per vendere questo format.
    3.  **PROMPT IMMAGINE**: Scrivi una descrizione dettagliata per generare con Imagen 3 un'immagine di sfondo epica e fotorealistica per la copertina.
    
    Rispondi ESCLUSIVAMENTE con un JSON in questo formato:
    {{
        "format_name": "Il nome esatto del format",
        "claim": "Lo slogan commerciale creato",
        "imagen_prompt": "La descrizione per l'immagine di sfondo"
    }}
    
    TESTO SORGENTE:
    {context}
    """
    
    try:
        # 3. Chiamata all'IA
        print("Invio richiesta a Gemini...")
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        data = json.loads(response.text)
        print("Dati ricevuti da Gemini.")
        
        # 4. Riempimento del PPT
        
        # a) Titolo (Nome Format)
        title_shape = slide.shapes.title
        if title_shape:
            title_shape.text = data.get("format_name", "")
            print(f"Titolo impostato: {title_shape.text}")
        else:
            print("Errore: Placeholder Titolo non trovato.")
            # Tentativo di fallback sul primo placeholder di testo disponibile
            for shape in slide.placeholders:
                if shape.has_text_frame:
                    shape.text = data.get("format_name", "")
                    title_shape = shape # Segna come usato
                    print(f"Titolo impostato (fallback): {shape.text}")
                    break

        # b) Sottotitolo (Claim)
        # Cerca il primo placeholder di testo che non sia il titolo
        subtitle_found = False
        for shape in slide.placeholders:
            if shape.has_text_frame and shape != title_shape:
                shape.text = data.get("claim", "")
                print(f"Claim impostato: {shape.text}")
                subtitle_found = True
                break
        if not subtitle_found:
            print("Attenzione: Placeholder per il Claim non trovato.")

        # c) Prompt Immagine (Nelle note)
        if not slide.has_notes_slide:
            slide.notes_slide = slide.part.presentation.slides._library.add_notes_slide(slide.part, slide.part.slide_layout)
        
        notes_frame = slide.notes_slide.notes_text_frame
        notes_frame.text = f"--- PROMPT IMAGEN 3 (SFONDO) ---\n{data.get('imagen_prompt')}"
        print("Prompt immagine salvato nelle note.")
        
    except Exception as e:
        print(f"ERRORE CRITICO in Page 1: {e}")

    print("--- Fine elaborazione Page 1 ---")
