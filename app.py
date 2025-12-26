import streamlit as st
import google.generativeai as genai
from pptx import Presentation
import io
import json

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Team Building AI Agent", layout="wide")

# --- GESTIONE SICUREZZA E LOGIN ---
def check_password():
    """Ritorna True se l'utente è loggato correttamente."""
    if st.session_state.get('password_correct', False):
        return True

    password_placeholder = st.sidebar.empty()
    pwd = password_placeholder.text_input("Password di Accesso", type="password")
    
    if st.sidebar.button("Accedi"):
        if pwd == st.secrets["general"]["app_password"]:
            st.session_state['password_correct'] = True
            password_placeholder.empty()
            st.rerun()
        else:
            st.error("Password non corretta")
            return False
    return False

if not check_password():
    st.stop()

# --- CONFIGURAZIONE AI ---
GOOGLE_API_KEY = st.secrets["google"]["api_key"]
genai.configure(api_key=GOOGLE_API_KEY)

# DEFINIZIONE RIGIDA DELLE VERSIONI (TASSATIVO)
GEMINI_VERSION = "gemini-3.0-pro" 
IMAGEN_VERSION = "imagen-3.0"

# --- SIDEBAR ---
with st.sidebar:
    st.title("🎛️ Control Panel")
    st.success(f"🔐 Accesso Autorizzato")
    
    st.divider()
    st.subheader("⚙️ AI Engine Specs")
    st.info(f"🧠 Reasoning Model: **{GEMINI_VERSION}**")
    st.info(f"🎨 Image Model Target: **{IMAGEN_VERSION}**")
    
    st.divider()
    st.subheader("📂 Uploads")
    template_file = st.file_uploader("1. Carica il PPT Template (Nuova Grafica)", type=['pptx'])
    content_file = st.file_uploader("2. Carica il Vecchio PPT (Contenuti)", type=['pptx'])

# --- FUNZIONI DI UTILITÀ ---
def extract_text_from_pptx(pptx_file):
    """Estrae tutto il testo da una presentazione per darlo in pasto a Gemini."""
    prs = Presentation(pptx_file)
    full_text = []
    for i, slide in enumerate(prs.slides):
        slide_text = []
        for shape in slide.shapes:
            if hasattr(shape, "text"):
                slide_text.append(shape.text)
        full_text.append(f"Slide {i+1}: " + " | ".join(slide_text))
    return "\n".join(full_text)

def generate_ai_content(source_text):
    """
    Chiede a Gemini 3 di agire come esperto di Team Building.
    Restituisce un JSON con i testi riadattati e i prompt per le immagini.
    """
    
    system_instruction = """
    Sei un esperto mondiale di Team Building e comunicazione aziendale. 
    Il tuo compito è analizzare una vecchia presentazione e ristrutturarne i contenuti 
    per un nuovo template moderno.
    
    DEVI restituire ESCLUSIVAMENTE un oggetto JSON con questa struttura:
    {
        "slides_content": [
            {
                "slide_number": 1,
                "title": "Titolo accattivante rielaborato",
                "body": "Testo riassunto e migliorato per massimizzare l'impatto...",
                "imagen_3_prompts": [
                    "Prompt 1 specifico per Imagen 3: fotorealistico, corporate, team building...",
                    "Prompt 2 alternativo per Imagen 3: stile illustration, vibrante..."
                ]
            }
            ... per tutte le slide necessarie
        ],
        "summary": "Breve spiegazione del ragionamento adottato"
    }
    """
    
    prompt = f"""
    Ecco il contenuto grezzo della vecchia presentazione:
    {source_text}
    
    Rielabora tutto il contenuto. Migliora il tono di voce (deve essere professionale ma energico).
    Per ogni slide, crea anche 2 prompt ottimizzati specificamente per {IMAGEN_VERSION} 
    che descrivano visivamente il concetto della slide.
    """

    model = genai.GenerativeModel(GEMINI_VERSION, system_instruction=system_instruction)
    
    # Configurazione per forzare l'output JSON
    generation_config = genai.GenerationConfig(response_mime_type="application/json")
    
    try:
        response = model.generate_content(prompt, generation_config=generation_config)
        return json.loads(response.text)
    except Exception as e:
        st.error(f"Errore nella chiamata a Gemini 3: {e}")
        return None

def fill_presentation(template_file, ai_data):
    """Riempie il template con i dati generati da Gemini."""
    prs = Presentation(template_file)
    
    # Nota: Questa logica è semplificata. In un caso reale, mapping slide-to-slide 
    # richiede di sapere quanti placeholder ci sono nel template.
    # Qui assumiamo che l'AI generi contenuto sequenziale che proviamo a inserire.
    
    slides_data = ai_data.get("slides_content", [])
    
    for i, slide in enumerate(prs.slides):
        if i >= len(slides_data):
            break
            
        data = slides_data[i]
        
        # Cerca titolo e body placeholder
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            
            # Semplice euristica: se è un titolo
            if shape == slide.shapes.title:
                shape.text = data.get("title", "")
            else:
                # Riempie il primo altro box di testo trovato con il corpo
                # (Da raffinare in base al template specifico che caricherai)
                if shape.text_frame.text == "BODY_PLACEHOLDER": # Esempio
                     shape.text = data.get("body", "")
                elif len(shape.text) > 0: # Sovrascrittura generica
                     shape.text = data.get("body", "")
                     
    # Salvataggio in buffer
    output = io.BytesIO()
    prs.save(output)
    output.seek(0)
    return output

# --- MAIN FLOW ---
st.title("🚀 Gemini 3 Team Building Architect")
st.markdown("Carica i file per avviare la rieditazione intelligente.")

if template_file and content_file:
    if st.button("✨ Avvia Processo AI (Gemini 3)"):
        with st.spinner("Gemini 3 sta leggendo il vecchio PPT..."):
            raw_text = extract_text_from_pptx(content_file)
            
        with st.spinner("Gemini 3 sta ragionando e creando i prompt per Imagen 3..."):
            ai_response = generate_ai_content(raw_text)
            
        if ai_response:
            # 1. Mostra il ragionamento e i Prompt
            st.divider()
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.subheader("🧠 Ragionamento & Contenuti")
                st.write(ai_response.get("summary"))
                st.json(ai_response.get("slides_content"))
            
            with col2:
                st.subheader("🎨 Prompt Generati per Imagen 3")
                for slide in ai_response.get("slides_content", []):
                    st.markdown(f"**Slide {slide['slide_number']}**")
                    for p_idx, prompt in enumerate(slide['imagen_3_prompts']):
                        st.code(prompt, language="text")
                        # Qui potresti aggiungere una chiamata API reale a Imagen 3 se lo desideri
            
            # 2. Creazione File
            with st.spinner("Generazione nuovo PPTx in corso..."):
                new_ppt_buffer = fill_presentation(template_file, ai_response)
                
            st.success("✅ Elaborazione completata!")
            
            st.download_button(
                label="📥 Scarica Nuovo PPT",
                data=new_ppt_buffer,
                file_name="TeamBuilding_Gemini3_Remake.pptx",
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation"
            )
else:
    st.info("Attesa caricamento file nella sidebar...")
