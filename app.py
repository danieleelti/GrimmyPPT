import streamlit as st
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from pptx import Presentation
import json
import os

# --- ID PREDEFINITI ---
DEFAULT_TEMPLATE_ID = "1BHac-ciWsMCxjtNrv8RxB68LyDi9cZrV6VMWEeXCw5A"
DEFAULT_FOLDER_ID = "1GGDGFQjAqck9Tdo30EZiLEo3CVJOlUKX"

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Slide Monster IT", page_icon="🇮🇹", layout="wide")

# --- LOGIN ---
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    
    if "gcp_service_account" in st.secrets and "json_content" in st.secrets["gcp_service_account"]:
        json_str = st.secrets["gcp_service_account"]["json_content"]
        service_account_info = json.loads(json_str)
    else:
        service_account_info = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
    
    creds = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/presentations']
    )
    drive_service = build('drive', 'v3', credentials=creds)
    slides_service = build('slides', 'v1', credentials=creds)

except Exception as e:
    st.error(f"⚠️ Errore Configurazione Secrets: {e}")
    st.stop()

# --- SIDEBAR (SEMPLIFICATA) ---
with st.sidebar:
    st.header("🧠 Configurazione")
    # Forziamo Gemini 1.5 Pro o 3.0 se disponibile, altrimenti Flash
    models = ["models/gemini-1.5-pro-latest", "models/gemini-1.5-flash"]
    selected_gemini = st.selectbox("Modello AI", models, index=0)
    
    st.divider()
    
    st.header("🎨 Immagini")
    image_style = st.selectbox("Stile", ["Fotorealistico", "Illustrazione 3D", "Disegno"], index=0)

# --- FUNZIONI ---

def extract_text_from_pptx(file_obj):
    prs = Presentation(file_obj)
    full_text = []
    for slide in prs.slides:
        s_txt = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                s_txt.append(shape.text.strip())
        full_text.append(" | ".join(s_txt))
    return "\n---\n".join(full_text)

def brain_process(text, model, style):
    # Prompt modificato per ITALIANO
    style_prompt = "photorealistic, cinematic lighting"
    if style == "Illustrazione 3D": style_prompt = "3d render, clay style, clean"
    
    prompt = f"""
    Sei un Copywriter esperto. Il tuo compito è ristrutturare questa presentazione mantenendo la lingua ITALIANA.
    
    INPUT: Testo grezzo di una presentazione.
    OUTPUT: JSON strutturato per riempire un Template di 6 slide.
    
    REGOLE FONDAMENTALI:
    1. NON TRADURRE. L'output deve essere in ITALIANO.
    2. Migliora il testo: rendilo più accattivante e commerciale, ma mantieni il senso originale.
    3. Cover: Il sottotitolo deve essere uno slogan.
    4. Image Prompts: Descrizione dell'immagine in INGLESE (perché il generatore di immagini capisce solo inglese).
       Stile richiesto: {style_prompt}.
    
    STRUTTURA JSON TASSATIVA:
    {{
        "cover": {{ "title": "Titolo Format", "subtitle": "Slogan", "image_prompt": "..." }},
        "slides": [
            {{ "id": 1, "title": "...", "body": "...", "image_prompt": "..." }},
            {{ "id": 2, "title": "...", "body": "...", "image_prompt": "..." }},
            {{ "id": 3, "title": "...", "body": "...", "image_prompt": "..." }},
            {{ "id": 4, "title": "...", "body": "...", "image_prompt": "..." }},
            {{ "id": 5, "title": "...", "body": "...", "image_prompt": "..." }}
        ]
    }}
    """
    
    ai = genai.GenerativeModel(model)
    try:
        resp = ai.generate_content(f"{prompt}\n\nTESTO SORGENTE:\n{text}", generation_config={"response_mime_type": "application/json"})
        return json.loads(resp.text)
    except Exception as e:
        st.error(f"Errore Gemini: {e}")
        return None

def generate_image_url(prompt):
    clean_prompt = prompt.replace(' ', '%20')
    return f"https://image.pollinations.ai/prompt/{clean_prompt}?width=1920&height=1080&model=flux&nologo=true&seed={os.urandom(2).hex()}"

def find_image_element_id(prs_id, label):
    try:
        prs = slides_service.presentations().get(presentationId=prs_id).execute()
        for slide in prs.get('slides', []):
            for el in slide.get('pageElements', []):
                if el.get('description') == label: return el['objectId']
    except: pass
    return None

def worker_bot(template_id, folder_id, filename, ai_data):
    # 1. COPIA FILE (Punto critico per i permessi)
    try:
        file_metadata = {'name': filename, 'parents': [folder_id]}
        copy = drive_service.files().copy(fileId=template_id, body=file_metadata).execute()
        new_id = copy.get('id')
    except Exception as e:
        st.error(f"❌ ERRORE DRIVE CRITICO: Non riesco a copiare il file! Controlla se 'slide-bot' è EDITOR della cartella {folder_id}. Dettaglio: {e}")
        return None
    
    # 2. SOSTITUZIONE TESTI
    reqs = []
    # Cover
    if 'cover' in ai_data:
        reqs.append({'replaceAllText': {'containsText': {'text': '{{TITLE}}'}, 'replaceText': ai_data['cover'].get('title', 'Titolo')}})
        reqs.append({'replaceAllText': {'containsText': {'text': '{{SUBTITLE}}'}, 'replaceText': ai_data['cover'].get('subtitle', '')}})
    
    # Slides interne
    if 'slides' in ai_data:
        for i, s in enumerate(ai_data['slides']):
            idx = i + 1
            reqs.append({'replaceAllText': {'containsText': {'text': f'{{{{TITLE_{idx}}}}}'}, 'replaceText': s.get('title', '')}})
            reqs.append({'replaceAllText': {'containsText': {'text': f'{{{{BODY_{idx}}}}}'}, 'replaceText': s.get('body', '')}})
            
    if reqs:
        slides_service.presentations().batchUpdate(presentationId=new_id, body={'requests': reqs}).execute()

    # 3. SOSTITUZIONE IMMAGINI
    reqs_img = []
    img_map = {}
    if 'cover' in ai_data: img_map['IMG_COVER'] = ai_data['cover'].get('image_prompt', '')
    if 'slides' in ai_data:
        for i, s in enumerate(ai_data['slides']): img_map[f'IMG_{i+1}'] = s.get('image_prompt', '')
        
    for label, prompt in img_map.items():
        if prompt:
            el_id = find_image_element_id(new_id, label)
            if el_id:
                reqs_img.append({
                    'replaceImage': {
                        'imageObjectId': el_id,
                        'imageReplaceMethod': 'CENTER_CROP',
                        'url': generate_image_url(prompt)
                    }
                })
    
    if reqs_img:
        slides_service.presentations().batchUpdate(presentationId=new_id, body={'requests': reqs_img}).execute()
        
    return new_id

# --- INTERFACCIA ---
st.title("🇮🇹 Slide Monster (Italian Mode)")

col1, col2 = st.columns([1, 2])

with col1:
    st.info("I file verranno generati in ITALIANO.")
    tmpl = st.text_input("ID Template", value=DEFAULT_TEMPLATE_ID)
    fold = st.text_input("ID Cartella", value=DEFAULT_FOLDER_ID)

with col2:
    uploaded = st.file_uploader("Carica PPT", accept_multiple_files=True, type=['pptx'])
    
    if st.button("🚀 ELABORA ORA", type="primary"):
        if not uploaded:
            st.warning("Carica almeno un file!")
        else:
            bar = st.progress(0)
            log_box = st.empty()
            
            for i, f in enumerate(uploaded):
                fname = f.name.replace(".pptx", "") + "_V2"
                log_box.write(f"⏳ Analisi testo di **{f.name}**...")
                
                # Step 1: Estrai
                txt = extract_text_from_pptx(f)
                
                # Step 2: AI
                log_box.write(f"🧠 Gemini sta scrivendo i testi per **{fname}**...")
                data = brain_process(txt, selected_gemini, image_style)
                
                if data:
                    # Step 3: Drive
                    log_box.write(f"💾 Salvataggio su Drive in corso...")
                    res_id = worker_bot(tmpl, fold, fname, data)
                    
                    if res_id:
                        st.toast(f"✅ Salvato: {fname}")
                        log_box.write(f"✅ **{fname}** completato con successo!")
                    else:
                        st.error("Fallito salvataggio su Drive.")
                else:
                    st.error(f"Errore AI sul file {f.name}")
                
                bar.progress((i+1)/len(uploaded))
            
            st.success("Operazione Completata.")
