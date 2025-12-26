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
        # Accesso diretto alla chiave 'app_password' (struttura flat)
        if pwd == st.secrets["app_password"]:
            st.session_state['password_correct'] = True
            password_placeholder.empty()
            st.rerun()
        else:
            st.error("Password non corretta")
            return False
    return False

if not check_password():
    st.stop()

# --- CONFIGURAZIONE API GOOGLE ---
try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=GOOGLE_API_KEY)
except KeyError:
    st.error("Errore Critico: Chiave 'GOOGLE_API_KEY' non trovata nei secrets.")
    st.stop()


# --- FUNZIONE RECUPERO MODELLI DISPONIBILI ---
@st.cache_data(ttl=3600) # Cache per un'ora per non chiamare l'API ogni secondo
def get_available_models():
    """
    Interroga Google per sapere quali modelli sono ATTIVAMENTE disponibili
    per questa API Key.
    """
    gemini_options = []
    imagen_options = []
    
    try:
        # Recupera la lista dei modelli
        for m in genai.list_models():
            # Filtra per modelli generativi di testo (Gemini)
            if 'generateContent' in m.supported_generation_methods:
                gemini_options.append(m.name)
            
            # Nota: Imagen a volte non appare in list_models standard SDK a seconda dell'accesso,
            # ma se appare, ha metodi specifici o nomi specifici.
            # Per sicurezza, aggiungiamo i noti se l'API non li esplicita, 
            # ma controlliamo prima se l'API li restituisce.
            if 'image' in m.name.lower() or 'generateImage' in m.supported_generation_methods:
                imagen_options.append(m.name)
                
    except Exception as e:
        st.error(f"Impossibile recuperare la lista modelli: {e}")
        # Fallback manuale se l'API fallisce il listing
        return ["models/gemini-1.5-pro", "models/gemini-1.0-pro"], ["imagen-3.0"]

    # Se la lista imagen è vuota (comune con l'SDK standard), forziamo le stringhe note
    # per permettere all'utente di provare comunque a chiamarle.
    if not imagen_options:
        imagen_options = ["imagen-3.0-generate-001", "imagen-3.0", "imagen-2.0"]
        
    # Ordiniamo in ordine inverso (solitamente i più nuovi hanno numeri più alti)
    gemini_options.sort(reverse=True)
    
    return gemini_options, imagen_options

def find_best_default(options, target_keyword):
    """Trova l'indice del modello che contiene la keyword (es. 'gemini-3')"""
    for index, name in enumerate(options):
        if target_keyword in name.lower():
            return index
    return 0 # Se non trova la versione specifica, torna il primo della lista (il più recente)

# --- SIDEBAR E SELEZIONE MODELLI ---
gemini_list, imagen_list = get_available_models()

# Calcolo indici di default
gemini_default_index = find_best_default(gemini_list, "gemini-3") # Cerca Gemini 3
imagen_default_index = find_best_default(imagen_list, "3") # Cerca Imagen 3

with st.sidebar:
    st.title("🎛️ Control Panel")
    st.success(f"🔐 Accesso Autorizzato")
    
    st.divider()
    st.subheader("🧠 Scelta Cervello (LLM)")
    
    selected_gemini_model = st.selectbox(
        "Versione Gemini", 
        gemini_list, 
        index=gemini_default_index,
        help="Seleziona il modello di ragionamento. Gemini 3 è pre-selezionato se disponibile."
    )
    
    st.subheader("🎨 Scelta Creativo (Image Gen)")
    selected_imagen_model = st.selectbox(
        "Versione Imagen (Target Prompt)", 
        imagen_list, 
        index=imagen_default_index,
        help="L'AI scriverà i prompt ottimizzati per questa versione."
    )
    
    st.info(f"Stai usando: **{selected_gemini_model}**")
    
    st.divider()
    st.subheader("📂 Uploads")
    template_file = st.file_uploader("1. Carica il PPT Template (Nuova Grafica)", type=['pptx'])
    content_file = st.file_uploader("2. Carica il Vecchio PPT (Contenuti)", type=['pptx'])

# --- FUNZIONI DI ELABORAZIONE ---
def extract_text_from_pptx(pptx_file):
    """Estrae tutto il testo da una presentazione."""
    prs = Presentation(pptx_file)
    full_text = []
    for i, slide in enumerate(prs.slides):
        slide_text = []
        for shape in slide.shapes:
            if hasattr(shape, "text"):
                slide_text.append(shape.text)
        full_text.append(f"Slide {i+1}: " + " | ".join(slide_text))
    return "\n".join(full_text)

def generate_ai_content(source_text, model_name, imagen_target):
    """
    Logica Core AI.
    """
    
    system_instruction = f"""
    Sei un esperto mondiale di Team Building e comunicazione aziendale. 
    Il tuo compito è analizzare una vecchia presentazione e ristrutturarne i contenuti 
    per un nuovo template moderno.
    
    DEVI restituire ESCLUSIVAMENTE un oggetto JSON valido con questa struttura:
    {{
        "slides_content": [
            {{
                "slide_number": 1,
                "title": "Titolo accattivante rielaborato",
                "body": "Testo riassunto e migliorato per massimizzare l'impatto...",
                "imagen_prompts": [
                    "Prompt 1 specifico per {imagen_target}: fotorealistico, corporate...",
                    "Prompt 2 alternativo per {imagen_target}: stile illustration..."
                ]
            }}
        ],
        "summary": "Breve spiegazione del ragionamento adottato"
    }}
    """
    
    prompt = f"""
    Ecco il contenuto grezzo della vecchia presentazione:
    {source_text}
    
    Rielabora tutto il contenuto. Migliora il tono di voce (deve essere professionale ma energico).
    Crea prompt ottimizzati specificamente per il modello di immagini: {imagen_target}.
    """

    # Utilizza il modello selezionato dinamicamente
    model = genai.GenerativeModel(model_name, system_instruction=system_instruction)
    
    # Configurazione JSON
    generation_config = genai.GenerationConfig(response_mime_type="application/json")
    
    try:
        response = model.generate_content(prompt, generation_config=generation_config)
        return json.loads(response.text)
    except Exception as e:
        st.error(f"Errore nella chiamata a {model_name}: {e}")
        return None

def fill_presentation(template_file, ai_data):
    """Riempie il template con i dati generati."""
    prs = Presentation(template_file)
    slides_data = ai_data.get("slides_content", [])
    
    for i, slide in enumerate(prs.slides):
        if i >= len(slides_data): break
        data = slides_data[i]
        
        for shape in slide.shapes:
            if not shape.has_text_frame: continue
            
            # Gestione Titolo
            if shape == slide.shapes.title:
                shape.text = data.get("title", "")
                continue

            # Gestione Corpo (Cerca placeholder o testo esistente)
            if len(shape.text) > 0 or "PLACEHOLDER" in shape.text_frame.text.upper(): 
                 shape.text = data.get("body", "")
                 # Se vuoi riempire solo UNO shape per slide come body, scommenta il break sotto
                 # break 
                     
    output = io.BytesIO()
    prs.save(output)
    output.seek(0)
    return output

# --- MAIN FLOW ---
st.title("🚀 Team Building AI Architect")
st.markdown("Carica i file, seleziona i motori AI e genera la nuova presentazione.")

if template_file and content_file:
    if st.button("✨ Avvia Processo AI"):
        
        # 1. Estrazione
        with st.spinner("Lettura del vecchio PPT..."):
            raw_text = extract_text_from_pptx(content_file)
            
        # 2. Generazione AI (Con i modelli scelti)
        with st.spinner(f"Elaborazione con {selected_gemini_model} (Target Img: {selected_imagen_model})..."):
            ai_response = generate_ai_content(raw_text, selected_gemini_model, selected_imagen_model)
            
        if ai_response:
            st.divider()
            col1, col2 = st.columns([1, 1])
            
            # Colonna 1: Testi e Ragionamento
            with col1:
                st.subheader("🧠 Ragionamento AI")
                st.info(ai_response.get("summary"))
                st.subheader("📝 Contenuti Generati")
                st.json(ai_response.get("slides_content"))
            
            # Colonna 2: Prompt Immagini
            with col2:
                st.subheader(f"🎨 Prompt per {selected_imagen_model}")
                for slide in ai_response.get("slides_content", []):
                    st.markdown(f"**Slide {slide['slide_number']}**")
                    prompts = slide.get('imagen_prompts', []) # Gestione sicura chiave
                    if not prompts and 'imagen_3_prompts' in slide: prompts = slide['imagen_3_prompts'] # Fallback retrocompatibilità
                    
                    for prompt in prompts:
                        st.code(prompt, language="text")
            
            # 3. Creazione File
            with st.spinner("Creazione file PPTx finale..."):
                new_ppt_buffer = fill_presentation(template_file, ai_response)
                
            st.success("✅ Finito!")
            st.download_button(
                label="📥 Scarica PPT Elaborato",
                data=new_ppt_buffer,
                file_name="AI_Remake_Presentation.pptx",
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation"
            )
else:
    st.info("👈 Carica i due file PPT nella sidebar per iniziare.")
