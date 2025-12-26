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

    # Container vuoto per il login nella sidebar
    password_placeholder = st.sidebar.empty()
    pwd = password_placeholder.text_input("Password", type="password")
    
    if st.sidebar.button("Login"):
        if pwd == st.secrets["app_password"]:
            st.session_state['password_correct'] = True
            password_placeholder.empty()
            st.rerun()
        else:
            st.error("Password errata")
            return False
    return False

if not check_password():
    st.stop()

# --- CONFIGURAZIONE API GOOGLE ---
try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=GOOGLE_API_KEY)
except KeyError:
    st.error("Errore: Chiave 'GOOGLE_API_KEY' mancante nei secrets.")
    st.stop()

# --- FUNZIONE RECUPERO MODELLI ---
@st.cache_data(ttl=3600) 
def get_available_models():
    gemini_options = []
    imagen_options = []
    
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                gemini_options.append(m.name)
            if 'image' in m.name.lower() or 'generateImage' in m.supported_generation_methods:
                imagen_options.append(m.name)
    except Exception:
        # Fallback in caso di errore API
        return ["models/gemini-1.5-pro"], ["imagen-3.0"]

    if not imagen_options:
        imagen_options = ["imagen-3.0-generate-001", "imagen-3.0"]
        
    gemini_options.sort(reverse=True)
    return gemini_options, imagen_options

def find_best_default(options, target_keyword):
    for index, name in enumerate(options):
        if target_keyword in name.lower():
            return index
    return 0 

# --- SIDEBAR (PULITA) ---
gemini_list, imagen_list = get_available_models()
gemini_default_index = find_best_default(gemini_list, "gemini-3")
imagen_default_index = find_best_default(imagen_list, "3")

with st.sidebar:
    st.title("🎛️ Control Panel")
    # RIMOSSO box verde accesso
    
    st.divider()
    
    # Selettori minimali
    selected_gemini_model = st.selectbox(
        "🧠 Modello LLM", 
        gemini_list, 
        index=gemini_default_index
    )
    
    selected_imagen_model = st.selectbox(
        "🎨 Modello Immagini", 
        imagen_list, 
        index=imagen_default_index
    )
    # RIMOSSO box blu "stai usando..."
    
    st.divider()
    
    template_file = st.file_uploader("1. Template (Grafica Nuova)", type=['pptx'])
    content_file = st.file_uploader("2. Content (Vecchio PPT)", type=['pptx'])

# --- LOGICA AI ---
def extract_text_from_pptx(pptx_file):
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
    system_instruction = f"""
    Sei un esperto di Team Building. Analizza la presentazione caricata e adatta i contenuti.
    Rispondi SOLO in JSON:
    {{
        "slides_content": [
            {{
                "slide_number": 1,
                "title": "...",
                "body": "...",
                "imagen_prompts": ["Prompt 1 per {imagen_target}...", "Prompt 2..."]
            }}
        ],
        "summary": "..."
    }}
    """
    
    prompt = f"Analizza e ristruttura: {source_text}"

    model = genai.GenerativeModel(model_name, system_instruction=system_instruction)
    generation_config = genai.GenerationConfig(response_mime_type="application/json")
    
    try:
        response = model.generate_content(prompt, generation_config=generation_config)
        return json.loads(response.text)
    except Exception as e:
        st.error(f"Errore generazione: {e}")
        return None

def fill_presentation(template_file, ai_data):
    prs = Presentation(template_file)
    slides_data = ai_data.get("slides_content", [])
    
    for i, slide in enumerate(prs.slides):
        if i >= len(slides_data): break
        data = slides_data[i]
        
        for shape in slide.shapes:
            if not shape.has_text_frame: continue
            
            if shape == slide.shapes.title:
                shape.text = data.get("title", "")
            elif len(shape.text) > 0 or "PLACEHOLDER" in shape.text_frame.text.upper():
                shape.text = data.get("body", "")
                     
    output = io.BytesIO()
    prs.save(output)
    output.seek(0)
    return output

# --- INTERFACCIA PRINCIPALE ---
st.title("🚀 Team Building AI Architect")

if template_file and content_file:
    if st.button("✨ Avvia Processo"):
        
        with st.spinner("Analisi in corso..."):
            raw_text = extract_text_from_pptx(content_file)
            ai_response = generate_ai_content(raw_text, selected_gemini_model, selected_imagen_model)
            
        if ai_response:
            st.divider()
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.subheader("📝 Contenuti")
                st.write(ai_response.get("summary"))
                st.json(ai_response.get("slides_content"))
            
            with col2:
                st.subheader("🎨 Prompt Immagini")
                for slide in ai_response.get("slides_content", []):
                    st.markdown(f"**Slide {slide['slide_number']}**")
                    prompts = slide.get('imagen_prompts', [])
                    if not prompts and 'imagen_3_prompts' in slide: prompts = slide['imagen_3_prompts']
                    for p in prompts: st.code(p, language="text")
            
            new_ppt = fill_presentation(template_file, ai_response)
            st.download_button("📥 Scarica PPT", new_ppt, "New_Presentation.pptx")
else:
    st.info("Carica i file nella sidebar per iniziare.")
