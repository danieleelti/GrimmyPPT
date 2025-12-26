import google.generativeai as genai
import json

def process(slide, context):
    """LOGICA ESCLUSIVA PER PAGINA 2: INTRODUZIONE"""
    
    model = genai.GenerativeModel("gemini-1.5-pro")
    
    prompt = f"""
    Sei un esperto Team Building. Stai lavorando sulla pagina: INTRODUZIONE AL FORMAT.
    
    OBIETTIVI:
    1. Titolo: Usa il Nome del Format.
    2. Box Piccolo (Categoria): Scrivi "Il Concept" o "Descrizione".
    3. Box Grande (Corpo): Scrivi una descrizione emozionale e coinvolgente di cosa succede durante l'attività.
    4. Imagen 3: Un'immagine d'insieme dell'attività.

    Rispondi SOLO in JSON:
    {{
        "title": "Nome Format",
        "category": "Il Concept",
        "body": "Testo descrittivo...",
        "imagen_prompt": "Prompt..."
    }}
    
    CONTESTO: {context}
    """
    
    try:
        res = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        data = json.loads(res.text)
        
        # Titolo
        if slide.shapes.title: slide.shapes.title.text = data.get("title", "")
        
        # Testi (Ordina dall'alto in basso: Categoria -> Corpo)
        shapes = [s for s in slide.placeholders if s.has_text_frame and s != slide.shapes.title]
        shapes.sort(key=lambda s: s.top)
        
        if len(shapes) >= 2:
            shapes[0].text = data.get("category", "")
            shapes[1].text = data.get("body", "")
            
        # Note Immagine
        if not slide.has_notes_slide: slide.notes_slide = slide.part.presentation.slides._library.add_notes_slide(slide.part, slide.part.slide_layout)
        slide.notes_slide.notes_text_frame.text = f"PROMPT IMAGEN 3:\n{data.get('imagen_prompt')}"
        
    except Exception as e:
        print(f"Errore Page 2: {e}")
