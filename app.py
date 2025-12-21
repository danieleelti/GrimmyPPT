import streamlit as st
import os
import google.generativeai as genai
from pptx import Presentation
from pptx.util import Inches
import tempfile
import time

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="AI PPTX Restyler", layout="wide")

# --- BLOCCO DI SICUREZZA (LOGIN) ---
def check_password():
    """Ritorna True se l'utente è loggato, altrimenti chiede password."""
    
    # Se la password non è definita nei secrets, mostra errore (o permetti accesso libero se preferisci)
    if "APP_PASSWORD" not in st.secrets:
        st.warning("⚠️ 'APP_PASSWORD' non trovata in secrets.toml. Accesso libero (non sicuro).")
        return True

    # Inizializza lo stato di autenticazione
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    # Se è già autenticato, procedi
    if st.session_state.authenticated:
        return True

    # Se non è autenticato, mostra il form di login
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🔒 Accesso Richiesto")
        password = st.text_input("Inserisci la password di accesso", type="password")
        
        if st.button("Accedi"):
            if password == st.secrets["APP_PASSWORD"]:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Password non corretta.")
            
    return False

# Se il check password fallisce, ferma l'esecuzione qui.
if not check_password():
    st.stop()

# =========================================================
#  DA QUI IN POI IL CODICE VIENE ESEGUITO SOLO SE LOGGATI
# =========================================================

# --- GESTIONE API KEY GEMINI ---
api_key = None

# 1. Prova a prendere la chiave dai Secrets
if "GOOGLE_API_KEY" in st.secrets:
    api_key = st.secrets["GOOGLE_API_KEY"]

# 2. Se non c'è, chiedila nella Sidebar
if not api_key:
    with st.sidebar:
        st.header("Configurazione API")
        api_key = st.text_input("Inserisci Gemini API Key", type="password")
        if not api_key:
            st.warning("Inserisci la chiave API di Google per continuare.")
            st.stop()

# Configura Gemini
genai.configure(api_key=api_key)

# --- INTERFACCIA PRINCIPALE ---
st.title("🤖 AI PowerPoint Restyler Agent")
st.markdown("Carica i tuoi vecchi PPTX e il nuovo Template. L'AI migrerà i contenuti.")
st.markdown("---")

# --- FUNZIONI CORE ---

def get_gemini_decision(slide_text, available_layouts):
    """
    Chiede a Gemini quale layout usare basandosi sul testo della vecchia slide.
    """
    # Usa 'gemini-1.5-flash' per velocità o 'gemini-1.5-pro' per maggiore intelligenza
    model = genai.GenerativeModel('gemini-1.5-flash') 
    
    prompt = f"""
    Ho una slide con questo contenuto testuale:
    "{slide_text}"
    
    I layout disponibili nel nuovo template sono: {available_layouts}.
    
    Il tuo compito:
    1. Analizza il contenuto (è un titolo? è un elenco puntato? è una frase di chiusura?).
    2. Scegli il NOME esatto del layout più adatto tra quelli forniti.
    3. Restituisci SOLO il nome del layout, nient'altro.
    """
    
    try:
        response = model.generate_content(prompt)
        chosen_layout = response.text.strip()
        
        # Verifica se la risposta contiene uno dei layout validi
        for layout in available_layouts:
            if layout in chosen_layout:
                return layout
        # Fallback se la risposta è strana
        return available_layouts[0]
    except Exception as e:
        return available_layouts[0]

def copy_images(source_slide, target_slide):
    """
    Tenta di copiare le immagini dalla slide vecchia alla nuova.
    Le posiziona in fila partendo da sinistra.
    """
    left = Inches(1)
    top = Inches(2.5)
    height = Inches(3)
    
    for shape in source_slide.shapes:
        # 13 è il tipo PICTURE
        if shape.shape_type == 13: 
            try:
                # Estrae i byte dell'immagine
                image_stream = shape.image.blob
                # Salva su file temporaneo (necessario per python-pptx)
                with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_img:
                    tmp_img.write(image_stream)
                    tmp_img_path = tmp_img.name
                
                # Aggiunge alla nuova slide
                target_slide.shapes.add_picture(tmp_img_path, left, top, height=height)
                left = left + Inches(3.5) # Sposta la prossima immagine a destra
            except Exception:
                pass # Ignora immagini corrotte o problematiche

def process_presentation(source_file, template_path):
    """Logica principale di conversione."""
    source_prs = Presentation(source_file)
    target_prs = Presentation(template_path)
    
    # Mappatura dei layout del nuovo template
    layout_map = {layout.name: layout for layout in target_prs.slide_master_layouts}
    layout_names = list(layout_map.keys())
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    total_slides = len(source_prs.slides)
    
    for i, slide in enumerate(source_prs.slides):
        status_text.text(f"Elaborazione slide {i+1} di {total_slides}...")
        
        # 1. Estrazione Testo
        text_content = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                text_content.append(shape.text)
        full_text = " | ".join(text_content)
        
        # 2. Decisione AI (Layout)
        # Se c'è pochissimo testo, usiamo il primo layout (spesso Titolo) senza chiamare l'AI
        if len(full_text) < 10:
             chosen_layout_name = layout_names[0] 
        else:
             chosen_layout_name = get_gemini_decision(full_text, layout_names)
        
        # Fallback sicuro se il nome non esiste
        if chosen_layout_name not in layout_map:
            # Prova a prendere il secondo layout (spesso Contenuto) se esiste, altrimenti il primo
            chosen_layout_name = layout_names[1] if len(layout_names) > 1 else layout_names[0]
            
        selected_layout = layout_map[chosen_layout_name]
        
        # 3. Creazione Nuova Slide
        new_slide = target_prs.slides.add_slide(selected_layout)
        
        # 4. Migrazione Contenuto Testuale
        try:
            # Titolo
            if new_slide.shapes.title:
                new_slide.shapes.title.text = text_content[0] if text_content else ""
            
            # Corpo (cerca placeholder idx 1)
            body_shape = None
            for shape in new_slide.placeholders:
                if shape.placeholder_format.idx == 1:
                    body_shape = shape
                    break
            
            if body_shape and len(text_content) > 1:
                # Unisce tutto il testo tranne il titolo
                body_text = "\n".join(text_content[1:])
                body_shape.text = body_text
        except Exception:
            pass # Continua anche se il testo fallisce

        # 5. Migrazione Immagini
        copy_images(slide, new_slide)
        
        # Aggiorna progress bar
        progress_bar.progress((i + 1) / total_slides)
        time.sleep(0.1) # Pausa minima per non sovraccaricare API

    status_text.text("Elaborazione completata!")
    return target_prs

# --- INTERFACCIA DI CARICAMENTO ---

col1, col2 = st.columns(2)

with col1:
    st.info("Step 1: Il Modello")
    uploaded_template = st.file_uploader("Carica il Template (.pptx/.potx)", type=['pptx', 'potx'])

with col2:
    st.info("Step 2: I File Vecchi")
    uploaded_files = st.file_uploader("Carica i file da convertire", type=['pptx'], accept_multiple_files=True)

# --- AVVIO PROCESSO ---

if st.button("Avvia Elaborazione 🚀"):
    if not uploaded_template or not uploaded_files:
        st.error("Per favore carica sia il template che almeno un file da convertire.")
    else:
        # Salva il template su disco temporaneamente
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pptx') as tmp_template:
            tmp_template.write(uploaded_template.getvalue())
            template_path = tmp_template.name

        # Ciclo sui file caricati
        for uploaded_file in uploaded_files:
            st.subheader(f"📄 Elaborazione: {uploaded_file.name}")
            
            try:
                # Chiama la funzione principale
                new_prs = process_presentation(uploaded_file, template_path)
                
                # Prepara il file per il download
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
                # Qui c'era l'errore: ora è gestito correttamente
                st.error(f"Errore durante l'elaborazione di {uploaded_file.name}: {e}")
