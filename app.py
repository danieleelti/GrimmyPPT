import streamlit as st
import os
import google.generativeai as genai
from pptx import Presentation
from pptx.util import Inches
import tempfile
import time

# --- CONFIGURAZIONE E GESTIONE SECRETS ---
st.set_page_config(page_title="AI PPTX Restyler", layout="wide")

api_key = None

# 1. Prova a prendere la chiave dai Secrets di Streamlit
if "GOOGLE_API_KEY" in st.secrets:
    api_key = st.secrets["GOOGLE_API_KEY"]

# 2. Se non c'è nei secrets, chiedila nella Sidebar (utile per test rapidi o per altri utenti)
if not api_key:
    with st.sidebar:
        st.header("Configurazione")
        api_key = st.text_input("Inserisci Gemini API Key", type="password")
        if not api_key:
            st.warning("Inserisci la chiave API per continuare.")
            st.stop() # Ferma l'app finché non c'è la chiave

# Configura la libreria
genai.configure(api_key=api_key)

st.title("🤖 AI PowerPoint Restyler Agent")
st.markdown("Carica i tuoi vecchi PPTX e il nuovo Template. L'AI migrerà i contenuti.")

# --- FUNZIONI CORE ---

def get_gemini_decision(slide_text, available_layouts):
    """
    Chiede a Gemini quale layout usare basandosi sul testo della vecchia slide.
    """
    model = genai.GenerativeModel('gemini-1.5-pro-latest') # O 'gemini-1.5-flash' per velocità
    
    prompt = f"""
    Ho una slide con questo contenuto testuale:
    "{slide_text}"
    
    I layout disponibili nel nuovo template sono: {available_layouts}.
    
    Il tuo compito:
    1. Analizza il contenuto.
    2. Scegli il NOME esatto del layout più adatto tra quelli forniti.
    3. Restituisci SOLO il nome del layout, nient'altro.
    """
    
    try:
        response = model.generate_content(prompt)
        chosen_layout = response.text.strip()
        # Pulizia base se l'AI è verbosa
        for layout in available_layouts:
            if layout in chosen_layout:
                return layout
        return available_layouts[0] # Fallback sul primo layout
    except Exception as e:
        return available_layouts[0]

def copy_images(source_slide, target_slide):
    """
    Tenta di copiare le immagini dalla slide vecchia alla nuova.
    Nota: È complesso mantenere la posizione perfetta, qui le mettiamo in un punto standard.
    """
    left = Inches(1)
    top = Inches(2)
    height = Inches(3)
    
    for shape in source_slide.shapes:
        if shape.shape_type == 13: # 13 è il tipo PICTURE
            # Salvataggio temporaneo dell'immagine
            image_stream = shape.image.blob
            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_img:
                tmp_img.write(image_stream)
                tmp_img_path = tmp_img.name
            
            try:
                target_slide.shapes.add_picture(tmp_img_path, left, top, height=height)
                left = left + Inches(3.5) # Sposta la prossima immagine a destra
            except:
                pass

def process_presentation(source_file, template_path):
    source_prs = Presentation(source_file)
    target_prs = Presentation(template_path)
    
    # Mappatura dei layout del nuovo template
    layout_map = {layout.name: layout for layout in target_prs.slide_master_layouts}
    layout_names = list(layout_map.keys())
    
    progress_bar = st.progress(0)
    total_slides = len(source_prs.slides)
    
    for i, slide in enumerate(source_prs.slides):
        # 1. Estrazione Testo
        text_content = []
        for shape in slide.shapes:
            if hasattr(shape, "text"):
                text_content.append(shape.text)
        full_text = " | ".join(text_content)
        
        # 2. Decisione AI (Layout)
        # Se c'è poco testo, assumiamo sia una slide titolo o immagine, altrimenti chiediamo a Gemini
        if len(full_text) < 10:
             chosen_layout_name = layout_names[0] # Default
        else:
             chosen_layout_name = get_gemini_decision(full_text, layout_names)
        
        # Se l'AI sbaglia nome, usiamo il layout generico (di solito indice 1)
        if chosen_layout_name not in layout_map:
            chosen_layout_name = layout_names[1] if len(layout_names) > 1 else layout_names[0]
            
        selected_layout = layout_map[chosen_layout_name]
        
        # 3. Creazione Nuova Slide
        new_slide = target_prs.slides.add_slide(selected_layout)
        
        # 4. Migrazione Contenuto (Semplificata)
        # Qui cerchiamo il Titolo e il Body. 
        # Logica euristica: Il primo testo è il titolo, il resto è il corpo.
        
        try:
            # Cerca il placeholder del titolo nella nuova slide
            if new_slide.shapes.title:
                new_slide.shapes.title.text = text_content[0] if text_content else "Slide senza titolo"
            
            # Cerca un placeholder per il corpo del testo (Body)
            # Di solito i placeholder hanno idx 1 per il corpo
            body_shape = None
            for shape in new_slide.placeholders:
                if shape.placeholder_format.idx == 1:
                    body_shape = shape
                    break
            
            if body_shape and len(text_content) > 1:
                # Uniamo tutto il resto del testo
                body_text = "\n".join(text_content[1:])
                body_shape.text = body_text
        except Exception as e:
            st.warning(f"Slide {i+1}: Layout adattato con difficoltà. {e}")

        # 5. Migrazione Immagini
        copy_images(slide, new_slide)
        
        # Aggiorna progress bar
        progress_bar.progress((i + 1) / total_slides)
        time.sleep(0.1) # Per non saturare l'API

    return target_prs

# --- INTERFACCIA UTENTE ---

uploaded_template = st.file_uploader("1. Carica il Modello (Template .pptx o .potx)", type=['pptx', 'potx'])
uploaded_files = st.file_uploader("2. Carica i file da convertire", type=['pptx'], accept_multiple_files=True)

if st.button("Avvia Elaborazione 🚀") and api_key and uploaded_template and uploaded_files:
    
    # Salva il template su disco temporaneamente
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pptx') as tmp_template:
        tmp_template.write(uploaded_template.getvalue())
        template_path = tmp_template.name

    for uploaded_file in uploaded_files:
        st.subheader(f"Elaborazione: {uploaded_file.name}")
        
        # Processa
        try:
            new_prs = process_presentation(uploaded_file, template_path)
            
            # Salva output
            output_name = f"NEW_{uploaded_file.name}"
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pptx') as tmp_out:
                new_prs.save(tmp_out.name)
                
                with open(tmp_out.name, "rb") as file:
                    st.download_button(
                        label=f"📥 Scarica {output_name}",
                        data=file,
                        file_name=output_name,
                        mime="application/vnd.openxmlformats-officedocument.presentationml.presentation"
                    )
        except Exception as e:
            st.error(f"Errore su {uploaded_file.name}: {e}")
