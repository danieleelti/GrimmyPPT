import streamlit as st
import google.generativeai as genai
from pptx import Presentation
import io
import json

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Team Building AI Architect", layout="wide")

# --- LOGIN ---
if 'password_correct' not in st.session_state: st.session_state['password_correct'] = False

def check_password():
    if st.session_state['password_correct']: return True
    pwd = st.sidebar.text_input("Password", type="password")
    if st.sidebar.button("Login"):
        if pwd == st.secrets["app_password"]:
            st.session_state['password_correct'] = True
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
        s_txt = []
        # Cerca testo in tutte le shape, non solo placeholder
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                s_txt.append(shape.text.strip())
        text.append(f"Slide {i+1}: {' | '.join(s_txt)}")
    return "\n".join(text)

# --- INTELLIGENZA (GEMINI) ---
def generate_ai_content(text, g_model, i_model):
    sys_prompt = f"""
    Sei un esperto Senior di Team Building. Il tuo compito è migrare i contenuti di una vecchia presentazione in un nuovo format.
    
    REGOLA TASSATIVA 1 (NOMI): Il "Titolo" della slide deve essere ESATTAMENTE il nome del format originale presente nel testo sorgente. NON cambiarlo, NON tradurlo, NON inventarlo. Se si chiama "Cooking Chef", deve restare "Cooking Chef".
    
    REGOLA TASSATIVA 2 (STRUTTURA):
    Devi restituire un JSON con un array "slides".
    
    1. PRIMA SLIDE (COVER):
       - "type": "cover"
       - "title": Nome esatto del Format.
       - "subtitle": Un claim commerciale breve e d'impatto (Slogan).
       - "image_prompt": Descrizione per Imagen di una copertina spettacolare.

    2. ALTRE SLIDE (CONTENT):
       - "type": "content"
       - "title": Nome esatto del Format (ripetilo sempre).
       - "category": Il titolo della sezione (es: "Dettagli Tecnici", "Obiettivi", "Svolgimento").
       - "body": Il testo descrittivo. Riscrivilo in modo professionale, chiaro ed energico.
       - "image_prompt": Descrizione visiva per Imagen relativa al contenuto.

    Output JSON atteso:
    {{
        "slides": [
            {{ "type": "cover", "title": "...", "subtitle": "...", "image_prompt": "..." }},
            {{ "type": "content", "title": "...", "category": "...", "body": "...", "image_prompt": "..." }}
        ],
        "summary": "Analisi breve..."
    }}
    """
    
    try:
        model = genai.GenerativeModel(g_model, system_instruction=sys_prompt)
        resp = model.generate_content(f"Analizza questo PPT e estrai i contenuti:\n{text}", generation_config={"response_mime_type": "application/json"})
        return json.loads(resp.text)
    except Exception as e:
        st.error(f"Errore AI: {e}")
        return None

# --- MANIPOLAZIONE PPT (LOGICA ROBUSTA) ---
def move_slide(prs, slide_element, new_index):
    """Sposta una slide a un indice specifico modificando l'XML."""
    xml_slides = prs.slides._sldIdLst
    slides = list(xml_slides)
    try:
        xml_slides.remove(slide_element)
        xml_slides.insert(new_index, slide_element)
    except ValueError:
        pass # Già rimossa o non trovata

def fill_presentation_smart(template_file, ai_data):
    prs = Presentation(template_file)
    
    # 1. Mappatura Layout (Assumiamo Cover=0, Content=1 nel Master)
    # Se il template ha un ordine diverso, prova a invertire questi indici (0 e 1)
    layout_cover = prs.slide_layouts[0]
    layout_content = prs.slide_layouts[1]
    
    # 2. Gestione Slide Esistenti (Le ultime 4)
    # Non cancelliamo nulla. Assumiamo che le slide presenti nel file caricato siano quelle fisse (footer, contatti, ecc.)
    # Le nuove slide verranno inserite PRIMA di queste.
    num_existing_slides = len(prs.slides)
    insertion_index = 0 # Iniziamo a inserire dalla posizione 0 (inizio)
    
    generated_slides = ai_data.get("slides", [])
    
    for slide_data in generated_slides:
        s_type = slide_data.get("type", "content")
        
        # Scegli il layout
        current_layout = layout_cover if s_type == "cover" else layout_content
        
        # Crea la slide (pptx aggiunge sempre alla fine)
        slide = prs.slides.add_slide(current_layout)
        
        # SPOSTAMENTO: Muoviamo la slide appena creata all'indice corretto
        # L'indice corretto è 'insertion_index'. 
        # Dopo averla spostata, incrementiamo insertion_index per la prossima.
        # Nota: slide._element è l'oggetto XML necessario per lo spostamento.
        move_slide(prs, slide._element, insertion_index)
        insertion_index += 1
        
        # --- RIEMPIMENTO CONTENUTI (Logica "Fuzzy" per evitare slide vuote) ---
        
        # 1. TITOLO (Cerca la shape che funge da titolo)
        if slide.shapes.title:
            slide.shapes.title.text = slide_data.get("title", "")
        
        # 2. IDENTIFICAZIONE BOX DI TESTO (Escluso titolo)
        # Raccogliamo tutti i placeholder che accettano testo
        text_shapes = []
        for shape in slide.placeholders:
            # Escludiamo il titolo e i placeholder grafici puri se non hanno text_frame
            if shape.element.ph_idx > 0 and shape.has_text_frame and shape != slide.shapes.title:
                 text_shapes.append(shape)
        
        # Ordiniamo i box trovati. 
        # Strategia: Il Sottotitolo/Categoria è solitamente più piccolo o posizionato più in alto del Body.
        # Proviamo a ordinare per posizione verticale (top)
        text_shapes.sort(key=lambda s: s.top)
        
        if s_type == "cover":
            # COVER: Titolo (già fatto), Sottotitolo (Claim)
            # Cerchiamo un posto per il sottotitolo
            if len(text_shapes) > 0:
                text_shapes[0].text = slide_data.get("subtitle", "")
                
            # PROMPT IMMAGINE: Se c'è un placeholder immagine, scriviamoci il prompt dentro per debug
            # (O nelle note se preferisci non sporcare la slide)
            # Per ora lo scriviamo nelle note della slide
            if slide.has_notes_slide:
                notes = slide.notes_slide.notes_text_frame
                notes.text = f"IMAGE PROMPT: {slide_data.get('image_prompt')}"
            else:
                # Creiamo le note se non esistono
                pass 

        else:
            # CONTENT: Titolo, Categoria, Body
            # Se abbiamo almeno 2 box testo:
            # Box 1 (Alto) -> Categoria
            # Box 2 (Basso/Grande) -> Body
            
            if len(text_shapes) >= 2:
                # Caso perfetto: abbiamo due box distinti
                text_shapes[0].text = slide_data.get("category", "")
                text_shapes[1].text = slide_data.get("body", "")
            elif len(text_shapes) == 1:
                # Caso fallback: un solo box. Mettiamo tutto lì.
                combined_text = f"{slide_data.get('category', '').upper()}\n\n{slide_data.get('body', '')}"
                text_shapes[0].text = combined_text
                
        # --- GESTIONE IMMAGINE (SOLO TESTO PROMPT) ---
        # Cerchiamo placeholder immagine per inserire il testo del prompt (così vedi che c'è)
        # Oppure lo lasciamo vuoto se l'obiettivo è solo mettere l'immagine dopo.
        # Se vuoi vedere il prompt SULLA slide temporaneamente:
        # for shape in slide.placeholders:
        #    if shape.placeholder_format.type == 18: # 18 = Picture
        #        if not shape.has_text_frame: continue # Alcuni picture placeholder non hanno testo
        #        shape.text = f"[IMG PROMPT]: {slide_data.get('image_prompt')}"

    out = io.BytesIO()
    prs.save(out)
    out.seek(0)
    return out

# --- INTERFACCIA ---
gem_ops, img_ops = get_available_models()
idx_g = find_best_default(gem_ops, "gemini-3")
idx_i = find_best_default(img_ops, "3")

with st.sidebar:
    st.title("🎛️ Control Panel")
    st.divider()
    sel_gem = st.selectbox("Cervello", gem_ops, index=idx_g)
    sel_img = st.selectbox("Immagini", img_ops, index=idx_i)
    st.divider()
    f_tmpl = st.file_uploader("1. Template (Con 4 pag finali)", type=['pptx'])
    f_cont = st.file_uploader("2. Contenuti (Vecchio PPT)", type=['pptx'])

st.title("🚀 Team Building AI Architect")

if f_tmpl and f_cont:
    if st.button("✨ Genera Presentazione"):
        with st.spinner("Analisi e Design in corso..."):
            raw_text = extract_text_from_pptx(f_cont)
            ai_resp = generate_ai_content(raw_text, sel_gem, sel_img)
            
        if ai_resp:
            st.divider()
            col1, col2 = st.columns([1,1])
            with col1:
                st.subheader("Contenuti Generati")
                st.info(ai_resp.get("summary"))
                st.json(ai_resp.get("slides"))
            
            with col2:
                st.subheader("Prompt Immagini (Imagen)")
                for s in ai_resp.get("slides", []):
                    st.markdown(f"**{s.get('type').upper()}: {s.get('title')}**")
                    st.code(s.get('image_prompt'), language="text")

            with st.spinner("Impaginazione e mantenimento slide finali..."):
                final_ppt = fill_presentation_smart(f_tmpl, ai_resp)
            
            st.success("Completato! Le slide finali sono state mantenute.")
            st.download_button("📥 Scarica PPT Definitivo", final_ppt, "New_Presentation.pptx")
else:
    st.info("Carica i file per iniziare.")
