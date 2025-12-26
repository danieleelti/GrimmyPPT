import google.generativeai as genai
import json

def process_slide(slide, full_context, slide_type="Contenuto"):
    """
    Logica per una pagina interna standard (Titolo + Categoria + Corpo).
    slide_type: Aiuta l'AI a capire cosa cercare (es. "Logistica", "Obiettivi").
    """
    
    model = genai.GenerativeModel("gemini-1.5-pro")
    
    prompt = f"""
    Sei un esperto di Team Building. Stiamo creando la pagina dedicata a: {slide_type.upper()}.
    
    Regole:
    1. TITOLO: Usa sempre il nome del format (cercalo nel contesto).
    2. CATEGORIA: Scrivi "{slide_type}" o una variazione breve.
    3. CORPO: Estrai dal contesto le informazioni relative a "{slide_type}". 
       Riscrivile in modo chiaro, bullet point o paragrafo persuasivo.
    4. IMMAGINE: Prompt per Imagen 3 coerente con {slide_type}.

    Rispondi SOLO in JSON:
    {{
        "title": "Nome Format",
        "category_text": "Intestazione (es. {slide_type})",
        "body_text": "Il testo rielaborato...",
        "imagen_prompt": "Prompt visivo..."
    }}

    CONTESTO VECCHIO PPT:
    {full_context}
    """
    
    response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
    data = json.loads(response.text)
    
    # --- MODIFICA PPT ---
    
    # 1. Titolo
    if slide.shapes.title:
        slide.shapes.title.text = data.get("title", "")
        
    # 2. Riempimento Intelligente (Categoria vs Corpo)
    # Prendiamo tutti i placeholder di testo tranne il titolo
    text_shapes = []
    for shape in slide.placeholders:
        if shape.has_text_frame and shape != slide.shapes.title:
            text_shapes.append(shape)
    
    # Ordiniamo per posizione verticale (il box più in alto è la categoria, quello sotto è il corpo)
    text_shapes.sort(key=lambda s: s.top)
    
    if len(text_shapes) >= 2:
        text_shapes[0].text = data.get("category_text", "") # Box piccolo in alto
        text_shapes[1].text = data.get("body_text", "")     # Box grande in basso
    elif len(text_shapes) == 1:
        # Se c'è un solo box, uniamo tutto
        text_shapes[0].text = f"{data.get('category_text')}\n\n{data.get('body_text')}"

    # 3. Note Immagine
    if not slide.has_notes_slide:
        slide.notes_slide = slide.part.presentation.slides._library.add_notes_slide(slide.part, slide.part.slide_layout)
    slide.notes_slide.notes_text_frame.text = f"IMAGEN 3 PROMPT:\n{data.get('imagen_prompt')}"

    return True
