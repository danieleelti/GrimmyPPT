import streamlit as st
import google.generativeai as genai
from pptx import Presentation
import io
import json

# --- SETUP PAGINA ---
st.set_page_config(page_title="Team Building AI Architect", layout="wide")

# --- GESTIONE LOGIN ---
if 'password_correct' not in st.session_state: st.session_state['password_correct'] = False

def check_password():
    if st.session_state['password_correct']: return True
    # Placeholder vuoto per pulizia UI
    pwd_placeholder = st.sidebar.empty()
    pwd = pwd_placeholder.text_input("Password", type="password")
    if st.sidebar.button("Login"):
        if pwd == st.secrets["app_password"]:
            st.session_state['password_correct'] = True
            pwd_placeholder.empty()
            st.rerun()
        else:
            st.error("Password errata")
    return False

if not check_password(): st.stop()

# --- SETUP GOOGLE ---
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
except:
    st.error("Manca GOOGLE_API_KEY nei secrets.")
    st.stop()

# --- UTILITÀ ---
@st.cache_data(ttl=3600)
def get_available_models():
    g_ops, i_ops = [], []
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods: g_ops.append(m.name)
            if 'image' in m.name.lower() or 'generateImage' in m.supported_generation_methods: i_ops.append(m.name)
    except: return ["models/gemini-1.5-pro"], ["imagen-3.0"]
    if not i_ops: i_ops = ["imagen-3.0-generate-001"]
    g_ops.sort(reverse=True)
    return g_ops, i_ops

def find_best_default(options, keyword):
    for i, n in enumerate(options):
        if keyword in n.lower(): return i
    return 0

def extract_text_from_pptx(file):
    prs = Presentation(file)
    text = []
    for i, slide in enumerate(prs.slides):
        s_txt = [s.text for s in slide.shapes if hasattr(s, "text")]
        text.append(f"Slide {i+1}: {' | '.join(s_txt)}")
    return "\n".join(text)

# --- CERVELLO AI (GEMINI 3) ---
def generate_ai_content(text, g_model, i_model):
    """
    Prompt avanzato che distingue tra COVER e SLIDE INTERNE.
    """
    sys_prompt = f"""
    Sei un esperto creativo di Team Building. Devi rifare una presentazione.
    
    STRUTTURA DELL'OUTPUT JSON:
    Devi restituire un array "slides".
    
    1. LA PRIMA SLIDE DEVE ESSERE DI TIPO "COVER":
       - "type": "cover"
       - "title": Nome del format (mantieni quello originale o miglioralo leggermente)
       - "subtitle": Un CLAIM accattivante, breve e commerciale (Slogan).
       - "image_prompt": Descrizione per immagine di copertina epica con {i_model}.

    2. LE ALTRE SLIDE SONO DI TIPO "CONTENT":
       - "type": "content"
       - "title": Titolo della sezione (es. Dettagli, Obiettivi, Timeline).
       - "category": Una o due parole chiave (es. "Logistica", "Formazione").
       - "body": Il testo descrittivo rielaborato in ottica persuasiva.
       - "image_prompt": Prompt per immagine di supporto.

    Output atteso (JSON puro):
    {{
        "slides": [
            {{ "type": "cover", "title": "...", "subtitle": "...", "image_prompt": "..." }},
            {{ "type": "content", "title": "...", "category": "...", "body": "...", "image_prompt": "..." }}
        ],
        "summary": "..."
    }}
    """
    
    try:
        model = genai.GenerativeModel(g_model, system_instruction=sys_prompt)
        resp = model.generate_content(f"Analizza questo PPT: {text}", generation_config={"response_mime_type": "application/json"})
        return json.loads(resp.text)
    except Exception as e:
        st.error(f"Errore AI: {e}")
        return None

# --- MANIPOLAZIONE PPT (LOGICA COVER + CONTENT) ---
def fill_presentation_smart(template_file, ai_data):
    prs = Presentation(template_file)
    
    # Rimuoviamo tutte le slide esistenti nel template per partire puliti
    # (Oppure assumiamo che il template sia vuoto e usiamo i layout)
    # Metodo sicuro: Creiamo nuove slide basate sui Layout del Master.
    
    # Mappatura Layout (Assumiamo l'ordine standard nello Schema Diapositiva)
    layout_cover = prs.slide_layouts[0]   # Il primo layout è la Cover
    layout_content = prs.slide_layouts[1] # Il secondo è il Contenuto standard
    
    # Se il template caricato ha già delle slide, le cancelliamo per riscriverle
    # Nota: python-pptx non ha un metodo clear() semplice, quindi creiamo un nuovo ppt basato sul template
    # ma per semplicità qui APPENDIAMO le slide se il template è vuoto, o usiamo quelle esistenti.
    
    # APPROCCIO MIGLIORE: Usare i dati AI per creare slide NUOVE usando i layout corretti.
    # Per farlo, dobbiamo svuotare il prs caricato o ignorare le slide esistenti.
    # Qui sotto: Iteriamo i dati AI e creiamo slide.
    
    # Cancellazione brutale slide esistenti (xml manipulation) per partire da zero col template grafico
    while len(prs.slides) > 0:
        xml_slides = prs.slides._sldIdLst
        slides = list(xml_slides)
        xml_slides.remove(slides[0])

    generated_slides = ai_data.get("slides", [])
    
    for slide_data in generated_slides:
        s_type = slide_data.get("type", "content")
        
        if s_type == "cover":
            # --- CREAZIONE COVER ---
            slide = prs.slides.add_slide(layout_cover)
            
            # Titolo (Nome Format)
            if slide.shapes.title:
                slide.shapes.title.text = slide_data.get("title", "")
            
            # Sottotitolo (Claim) -> Di solito è il secondo placeholder
            # Cerchiamo il placeholder del sottotitolo
            for shape in slide.placeholders:
                if shape.element.ph_idx == 1: # Indice tipico sottotitolo
                    shape.text = slide_data.get("subtitle", "")
            
            # Nota: L'immagine non la inseriamo (solo prompt), ma il placeholder resta lì.

        else:
            # --- CREAZIONE CONTENUTO ---
            slide = prs.slides.add_slide(layout_content)
            
            # Titolo
            if slide.shapes.title:
                slide.shapes.title.text = slide_data.get("title", "")
                
            # Logica "Intelligente" per Categoria (piccolo) e Body (grande)
            # Raccogliamo i placeholder di testo (escluso il titolo)
            text_placeholders = [
                s for s in slide.placeholders 
                if s.has_text_frame and s != slide.shapes.title
            ]
            
            # Ordinamento semplice (spesso basta l'indice, ma l'AI a volte inverte)
            # Assumiamo: Primo placeholder trovato = Categoria, Secondo = Corpo
            if len(text_placeholders) >= 1:
                text_placeholders[0].text = slide_data.get("category", "")
            if len(text_placeholders) >= 2:
                text_placeholders[1].text = slide_data.get("body", "")

    out = io.BytesIO()
    prs.save(out)
    out.seek(0)
    return out

# --- INTERFACCIA UTENTE ---
gem_ops, img_ops = get_available_models()
idx_g = find_best_default(gem_ops, "gemini-3")
idx_i = find_best_default(img_ops, "3")

with st.sidebar:
    st.title("🎛️ Control Panel")
    st.divider()
    sel_gem = st.selectbox("Cervello", gem_ops, index=idx_g)
    sel_img = st.selectbox("Immagini", img_ops, index=idx_i)
    st.divider()
    # Logica caricamento
    f_tmpl = st.file_uploader("1. Template (Layout Vuoti)", type=['pptx'])
    f_cont = st.file_uploader("2. Contenuti (Vecchio PPT)", type=['pptx'])

st.title("🚀 Team Building AI Architect")

if f_tmpl and f_cont:
    if st.button("✨ Genera Presentazione"):
        with st.spinner("Analisi e Design in corso..."):
            # 1. Legge contenuti vecchi
            raw_text = extract_text_from_pptx(f_cont)
            
            # 2. Chiama Gemini 3
            ai_resp = generate_ai_content(raw_text, sel_gem, sel_img)
            
        if ai_resp:
            st.divider()
            
            # UI Visualizzazione
            col1, col2 = st.columns([1,1])
            with col1:
                st.subheader("Ragionamento & Testi")
                st.info(ai_resp.get("summary"))
                st.json(ai_resp.get("slides"))
            
            with col2:
                st.subheader("Prompt Generati")
                for s in ai_resp.get("slides", []):
                    tipo = s.get('type', 'slide').upper()
                    st.markdown(f"**{tipo}: {s.get('title')}**")
                    st.code(s.get('image_prompt'), language="text")

            # 3. Creazione PPT
            with st.spinner("Impaginazione nel Template..."):
                final_ppt = fill_presentation_smart(f_tmpl, ai_resp)
            
            st.success("Completato!")
            st.download_button(
                "📥 Scarica PPT Definitivo", 
                final_ppt, 
                "TeamBuilding_Remake.pptx"
            )
else:
    st.info("Carica i file nella sidebar.")
