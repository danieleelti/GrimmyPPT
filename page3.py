import google.generativeai as genai
import json

def process(slide, context):
    """LOGICA ESCLUSIVA PER PAGINA 3: DETTAGLI TECNICI"""
    
    model = genai.GenerativeModel("gemini-1.5-pro")
    
    prompt = f"""
    Sei un tecnico esperto. Stai lavorando sulla pagina: DETTAGLI LOGISTICI E TECNICI.
    
    OBIETTIVI:
    1. Titolo: Usa il Nome del Format.
    2. Box Piccolo: Scrivi "Scheda Tecnica".
    3. Box Grande: Estrai durata, numero partecipanti, location (indoor/outdoor) e requisiti tecnici. Usa un elenco puntato.
    4. Imagen 3: Un close-up di un dettaglio tecnico o attrezzatura.

    Rispondi SOLO in JSON:
    {{
        "title": "Nome Format",
        "category": "Scheda Tecnica",
        "body": "Durata: ...\nPartecipanti: ...\nLocation: ...",
        "imagen_prompt": "Prompt..."
    }}
    
    CONTESTO: {context}
    """
    
    try:
        res = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        data = json.loads(res.text)
        
        if slide.shapes.title: slide.shapes.title.text = data.get("title", "")
        
        shapes = [s for s in slide.placeholders if s.has_text_frame and s != slide.shapes.title]
        shapes.sort(key=lambda s: s.top)
        
        if len(shapes) >= 2:
            shapes[0].text = data.get("category", "")
            shapes[1].text = data.get("body", "")
            
        if not slide.has_notes_slide: slide.notes_slide = slide.part.presentation.slides._library.add_notes_slide(slide.part, slide.part.slide_layout)
        slide.notes_slide.notes_text_frame.text = f"PROMPT IMAGEN 3:\n{data.get('imagen_prompt')}"
        
    except Exception as e:
        print(f"Errore Page 3: {e}")
