import google.generativeai as genai
import json

def process(slide, context):
    """LOGICA ESCLUSIVA PER LA COVER"""
    
    # Usa Gemini 1.5 Pro (o 3.0 se hai l'ID)
    model = genai.GenerativeModel("gemini-1.5-pro")
    
    prompt = f"""
    Sei un esperto di Marketing. Stai lavorando ESCLUSIVAMENTE sulla COVER.
    
    OBIETTIVI:
    1. Estrai il NOME DEL FORMAT (esatto, senza modifiche).
    2. Inventa un CLAIM (Slogan) potente per la vendita.
    3. Descrivi l'immagine di copertina per Imagen 3.

    Rispondi SOLO in JSON:
    {{
        "format_name": "Nome esatto...",
        "claim": "Slogan...",
        "imagen_prompt": "Prompt dettagliato..."
    }}
    
    CONTESTO: {context}
    """
    
    try:
        res = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        data = json.loads(res.text)
        
        # Applicazione al PPT
        if slide.shapes.title:
            slide.shapes.title.text = data.get("format_name", "")
            
        # Cerca il sottotitolo (spesso il placeholder 1)
        for shape in slide.placeholders:
            if shape.has_text_frame and shape != slide.shapes.title:
                shape.text = data.get("claim", "")
                break
                
        # Note per Immagine
        if not slide.has_notes_slide: slide.notes_slide = slide.part.presentation.slides._library.add_notes_slide(slide.part, slide.part.slide_layout)
        slide.notes_slide.notes_text_frame.text = f"PROMPT IMAGEN 3:\n{data.get('imagen_prompt')}"
        
    except Exception as e:
        print(f"Errore Page 1: {e}")
