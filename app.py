import streamlit as st
import google.generativeai as genai
from pptx import Presentation
from pptx.util import Inches, Pt
import tempfile
import json
import re
import os

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="AI Team Building Restyler", layout="wide", page_icon="🎨")

# --- AUTHENTICATION ---
def check_password():
    if "APP_PASSWORD" not in st.secrets:
        st.warning("⚠️ 'APP_PASSWORD' non trovata in secrets.toml. Accesso libero (non sicuro).")
        return True
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if st.session_state.authenticated:
        return True

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🔒 Accesso Team Building AI")
        password = st.text_input("Password", type="password")
        if st.button("Entra"):
            if password == st.secrets["APP_PASSWORD"]:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Password errata.")
    return False

if not check_password():
    st.stop()

# --- SETUP API ---
api_key = st.secrets.get("GOOGLE_API_KEY")
if not api_key:
    with st.sidebar:
        api_key = st.text_input("Gemini API Key", type="password")
        if not api_key:
            st.stop()
genai.configure(api_key=api_key)

# --- FUNZIONI DI SUPPORTO ---

def extract_content_from_pptx(file_path):
    """Estrae testo e immagini dal vecchio PPTX."""
    prs = Presentation(file_path)
    full_text = []
    images = []

    for slide in prs.slides:
        slide_text = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                slide_text.append(shape.text.strip())
            
            # Estrazione Immagini (Shape Type 13 = Picture)
            if shape.shape_type == 13:
                try:
                    image_blob = shape.image.blob
                    images.append(image_blob)
                except:
                    pass
        
        if slide_text:
            full_text.append(" | ".join(slide_text))
    
    return "\n".join(full_text), images

def clean_json_response(text):
    """Pulisce la risposta di Gemini per estrarre il JSON puro."""
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```", "", text)
    return text.strip()

def get_ai_restyling_plan(source_text):
    """
    Il cervello dell'operazione. Chiede a Gemini di mappare il contenuto vecchio
    sui nuovi layout specifici.
    """
    model = genai.GenerativeModel('gemini-1.5-pro-latest') # Uso PRO per ragionamento complesso
    
    prompt = f"""
    Sei un Senior Event Manager esperto in Team Building aziendali.
    Il tuo compito è ristrutturare il contenuto grezzo di una vecchia presentazione in un nuovo formato strutturato.
    
    CONTENUTO GREZZO (Source):
    "{source_text}"

    LAYOUT DISPONIBILI (Target):
    1. "Cover_Main": Solo Titolo evento e Sottotitolo (claim).
    2. "Intro_Concept": Spiegazione emotiva/strategica del concept.
    3. "Activity_Detail": Descrizione operativa delle attività (Cosa si fa). Se il testo è lungo, usa più slide di questo tipo.
    4. "Technical_Grid": Durata, Luogo, Numero partecipanti, Requisiti tecnici.
    5. "Logistics_Info": Cosa è incluso, cosa è escluso, logistica.

    REGOLE DI SCRITTURA (Tone of Voice):
    - Tono: Professionale, coinvolgente, esperto.
    - NON INVENTARE FATTI: Usa solo le durate, i prezzi e i dettagli presenti nel testo. Se mancano, non metterli.
    - Se la descrizione delle attività è povera, espandila leggermente rendendola accattivante ("selling mode"), ma senza aggiungere strumenti o prove non previste.

    OUTPUT RICHIESTO:
    Restituisci ESCLUSIVAMENTE un array JSON. Ogni oggetto rappresenta una slide.
    Struttura:
    [
        {{ "layout": "Cover_Main", "title": "...", "body": "..." }},
        {{ "layout": "Intro_Concept", "title": "...", "body": "..." }},
        ...
    ]
    """
    
    try:
        response = model.generate_content(prompt)
        cleaned_json = clean_json_response(response.text)
        return json.loads(cleaned_json)
    except Exception as e:
        st.error(f"Errore nell'elaborazione AI: {e}")
        return []

def create_new_pptx(plan, images, template_path):
    """Crea il PPT fisico unendo il piano AI, le immagini estratte e le slide fisse."""
    prs = Presentation(template_path)
    
    # Mappa layout per nome
    layout_map = {l.name: l for l in prs.slide_master_layouts}
    
    # 1. Generazione Slide Variabili (da AI)
    img_index = 0
    for slide_data in plan:
        layout_name = slide_data.get("layout", "Intro_Concept")
        
        # Fallback se il layout non esiste nel template
        if layout_name not in layout_map:
            st.warning(f"Layout '{layout_name}' non trovato nel template. Uso il primo disponibile.")
            layout_name = list(layout_map.keys())[0]
            
        slide = prs.slides.add_slide(layout_map[layout_name])
        
        # Inserimento Testi
        try:
            if slide.shapes.title:
                slide.shapes.title.text = slide_data.get("title", "")
            
            # Cerca il placeholder del corpo (Body)
            for shape in slide.placeholders:
                if shape.placeholder_format.idx == 1: # Standard body placeholder
                    shape.text = slide_data.get("body", "")
        except Exception as e:
            print(f"Errore testo su slide {layout_name}: {e}")

        # Inserimento Immagini (Strategia "a rotazione")
        # Se il layout non è la cover (spesso ha sfondo fisso) e abbiamo immagini disponibili
        if layout_name != "Cover_Main" and img_index < len(images):
            try:
                # Salviamo l'immagine temporaneamente
                with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_img:
                    tmp_img.write(images[img_index])
                    tmp_path = tmp_img.name
                
                # Cerchiamo un placeholder immagine, altrimenti la piazziamo a lato
                img_placeholder = None
                for shape in slide.placeholders:
                    if shape.placeholder_format.type == 18: # 18 = PICTURE
                        img_placeholder = shape
                        break
                
                if img_placeholder:
                    img_placeholder.insert_picture(tmp_path)
                else:
                    # Posizionamento manuale standard (es. in basso a destra)
                    slide.shapes.add_picture(tmp_path, Inches(7.5), Inches(2.5), height=Inches(2.5))
                
                img_index += 1
                os.remove(tmp_path)
            except Exception:
                pass

    # 2. Aggiunta Slide Fisse (Standard)
    # Queste slide vengono aggiunte alla fine, vuote di contenuto "nuovo" ma con la grafica del master
    fixed_layouts = ["Standard_Training", "Standard_Extras", "Standard_Payment", "Closing_Contact"]
    
    for fl_name in fixed_layouts:
        if fl_name in layout_map:
            prs.slides.add_slide(layout_map[fl_name])
        else:
            st.warning(f"⚠️ Layout fisso '{fl_name}' mancante nel Master.")

    return prs

# --- INTERFACCIA STREAMLIT ---

st.title("🚀 Team Building PPT Refactory")
st.markdown("""
Questo agente trasforma i vecchi PPT nel nuovo Format Aziendale.
**Logica:**
1. Estrae i contenuti.
2. L'AI li riorganizza in una narrazione coerente (Cover -> Concept -> Attività -> Tecnica).
3. Aggiunge automaticamente le slide standard (Formazione, Pagamenti, Contatti).
""")

col1, col2 = st.columns(2)
with col1:
    template_file = st.file_uploader("1. Carica il Template (.pptx)", type=["pptx", "potx"])
with col2:
    source_files = st.file_uploader("2. Carica i vecchi PPT", type=["pptx"], accept_multiple_files=True)

if st.button("Avvia Trasformazione") and template_file and source_files:
    
    # Salva template temp
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pptx') as tmp_template:
        tmp_template.write(template_file.getvalue())
        template_path = tmp_template.name

    progress_bar = st.progress(0)
    
    for idx, uploaded_file in enumerate(source_files):
        st.subheader(f"🛠️ Elaborazione: {uploaded_file.name}")
        
        # 1. Estrazione
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pptx') as tmp_src:
            tmp_src.write(uploaded_file.getvalue())
            src_path = tmp_src.name
            
        raw_text, images_list = extract_content_from_pptx(src_path)
        st.info(f"Contenuto estratto. Analisi AI in corso...")
        
        # 2. Pianificazione AI
        ai_plan = get_ai_restyling_plan(raw_text)
        
        if not ai_plan:
            st.error("L'AI non è riuscita a generare un piano. Riprova.")
            continue
            
        # 3. Creazione
        try:
            new_prs = create_new_pptx(ai_plan, images_list, template_path)
            
            output_name = f"RESTYLED_{uploaded_file.name}"
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pptx') as tmp_out:
                new_prs.save(tmp_out.name)
                
                with open(tmp_out.name, "rb") as f:
                    st.download_button(
                        label=f"📥 Scarica {output_name}",
                        data=f,
                        file_name=output_name,
                        mime="application/vnd.openxmlformats-officedocument.presentationml.presentation"
                    )
            st.success("Fatto!")
            
        except Exception as e:
            st.error(f"Errore nella generazione del file: {e}")
            
        progress_bar.progress((idx + 1) / len(source_files))
        
        # Pulizia temp
        if os.path.exists(src_path): os.remove(src_path)

    if os.path.exists(template_path): os.remove(template_path)
