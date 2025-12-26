import google.generativeai as genai
import json
import streamlit as st

def process_slide(slide, full_context):
    """
    Logica specifica per la Slide 1 (Cover).
    Riceve l'oggetto slide di python-pptx e tutto il testo del vecchio ppt.
    """
    
    # Configura il modello (puoi centralizzare la config se preferisci)
    model = genai.GenerativeModel("gemini-1.5-pro") # Sostituisci con gemini-3 appena disponibile l'ID
    
    # Prompt chirurgico per la Cover
    prompt = f"""
    Sei un esperto di Team Building. Stiamo creando la COPERTINA.
    
    Analizza il testo completo della vecchia presentazione fornito qui sotto.
    Trova il NOME DEL FORMAT (es. "Cooking Quiz", "Urban Game"). Deve essere esatto.
    Inventa un CLAIM (Slogan) commerciale ed energico.
    Crea un PROMPT per Imagen 3 per lo sfondo.

    Rispondi SOLO in JSON:
    {{
        "format_name": "Nome esatto trovato",
        "claim": "Slogan di vendita",
        "imagen_prompt": "Prompt dettagliato in inglese per immagine di sfondo..."
    }}

    TESTO VECCHIO PPT:
    {full_context}
    """
    
    # Chiamata AI
    response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
    data = json.loads(response.text)
    
    # --- MODIFICA DEL FILE PPT ---
    
    # 1. Titolo (Format Name)
    if slide.shapes.title:
        slide.shapes.title.text = data.get("format_name", "Format Name Not Found")
        
    # 2. Sottotitolo (Claim)
    # Cerchiamo il placeholder giusto. Nella cover solitamente è il secondo text frame.
    found = False
    for shape in slide.placeholders:
        if shape.has_text_frame and shape != slide.shapes.title:
            shape.text = data.get("claim", "")
            found = True
            break
            
    # 3. Prompt Immagine (nelle note)
    if not slide.has_notes_slide:
        slide.notes_slide = slide.part.presentation.slides._library.add_notes_slide(slide.part, slide.part.slide_layout)
    slide.notes_slide.notes_text_frame.text = f"IMAGEN 3 PROMPT:\n{data.get('imagen_prompt')}"

    return True
