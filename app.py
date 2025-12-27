import streamlit as st
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from pptx import Presentation
import json
import os
import re
import time
import urllib.parse

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Slide Monster: Visual Agent", page_icon="👁️", layout="wide")

# --- I TUOI ID ---
DEFAULT_TEMPLATE_ID = "1BHac-ciWsMCxjtNrv8RxB68LyDi9cZrV6VMWEeXCw5A" 
DEFAULT_FOLDER_ID = "1wL1oxos7ISS03GzfW0db44XoAk3UocV0"

# --- INIZIALIZZAZIONE SESSION STATE ---
if "analysis_done" not in st.session_state:
    st.session_state.analysis_done = False
if "results" not in st.session_state:
    st.session_state.results = {} # Conterrà i dati generati

# --- LOGIN ---
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    if "gcp_service_account" in st.secrets and "json_content" in st.secrets["gcp_service_account"]:
        service_account_info = json.loads(st.secrets["gcp_service_account"]["json_content"])
    else:
        service_account_info = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
    
    creds = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/presentations']
    )
    drive_service = build('drive', 'v3', credentials=creds)
    slides_service = build('slides', 'v1', credentials=creds)

except Exception as e:
    st.error(f"⚠️ Errore Secrets: {e}")
    st.stop()

# --- SIDEBAR ---
with st.sidebar:
    st.header("🧠 Configurazione")
    models = ["models/gemini-3-pro-preview", "models/gemini-1.5-pro", "models/gemini-1.5-flash"]
    selected_gemini = st.selectbox("Modello Attivo", models, index=0)
    st.divider()
    image_style = st.selectbox("Stile Immagini", ["Imagen 4 (High Fidelity)", "Flux Realism", "Illustrazione 3D"], index=0)
    
    st.divider()
    st.subheader("🔍 Diagnostica")
    if st.button("Analizza Etichette Template"):
        try:
            st.write("Scansione in corso...")
            prs = slides_service.presentations().get(presentationId=DEFAULT_TEMPLATE_ID).execute()
            found_tags = []
            for slide in prs.get('slides', []):
                for el in slide.get('pageElements', []):
                    if 'description' in el:
                        found_tags.append(f"Slide {slide['objectId'][-3:]}: {el['description']}")
            
            if found_tags:
                st.success(f"Trovate {len(found_tags)} etichette:")
                st.code("\n".join(found_tags))
            else:
                st.error("❌ NESSUNA etichetta trovata! Il robot non sa dove mettere le foto.")
        except Exception as e:
            st.error(f"Errore scansione: {e}")

# --- FUNZIONI ---

def clean_json_text(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(json)?", "", text, flags=re.MULTILINE)
        text = re.sub(r"```$", "", text, flags=re.MULTILINE)
    return text.strip()

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

def brain_process(text, model_name, style):
    style_prompt = "photorealistic, cinematic lighting, 8k"
    if "Imagen 4" in style:
        style_prompt = "award winning photography, Imagen 4 style, hyper-realistic, 8k resolution"
    
    prompt = f"""
    Sei un Senior Copywriter italiano. Riscrivi i contenuti di questa presentazione.
    INPUT: Testo grezzo estratto da slide.
    OUTPUT: JSON per riempire un template (Cover + 5 slide).
    REGOLE: SCRIVI SOLO IN ITALIANO. Cover: Sottotitolo = slogan.
    Image Prompts: Descrizioni in INGLESE (brevi, visive, dettagliate). Stile: {style_prompt}.
    STRUTTURA JSON:
    {{
        "cover": {{ "title": "Titolo", "subtitle": "Slogan", "image_prompt": "..." }},
        "slides": [
            {{ "id": 1, "title": "...", "body": "...", "image_prompt": "..." }},
            {{ "id": 2, "title": "...", "body": "...", "image_prompt": "..." }},
            {{ "id": 3, "title": "...", "body": "...", "image_prompt": "..." }},
            {{ "id": 4, "title": "...", "body": "...", "image_prompt": "..." }},
            {{ "id": 5, "title": "...", "body": "...", "image_prompt": "..." }}
        ]
    }}
    """
    
    ai = genai.GenerativeModel(model_name)
    try:
        resp = ai.generate_content(f"{prompt}\n\nTESTO:\n{text}", generation_config={"response_mime_type": "application/json"})
        if not resp.text: return None
        return json.loads(clean_json_text(resp.text))
    except Exception as e:
        st.error(f"Errore Modello ({model_name}): {e}")
        return None

def generate_image_url(prompt, style_choice):
    safe_prompt = prompt.replace("\n", " ").strip()
    encoded_prompt = urllib.parse.quote(safe_prompt)
    seed = os.urandom(2).hex()
    return f"[https://image.pollinations.ai/prompt/](https://image.pollinations.ai/prompt/){encoded_prompt}?width=1920&height=1080&model=flux&nologo=true&seed={seed}"

def find_image_element_id_smart(prs_id, label):
    """Cerca l'immagine ignorando spazi e maiuscole"""
    label_clean = label.strip().upper()
    try:
        prs = slides_service.presentations().get(presentationId=prs_id).execute()
        for slide in prs.get('slides', []):
            for el in slide.get('pageElements', []):
                if 'description' in el:
                    current_desc = el['description'].strip().upper()
                    if current_desc == label_clean:
                        return el['objectId']
    except Exception as e:
        print(f"Errore ricerca ID: {e}")
    return None

def worker_bot_finalize(template_id, folder_id, filename, ai_data, pregenerated_urls):
    # 1. COPIA FILE
    try:
        copy = drive_service.files().copy(
            fileId=template_id, 
            body={'name': filename, 'parents': [folder_id]}, 
            supportsAllDrives=True
        ).execute()
        new_id = copy.get('id')
    except Exception as e:
        st.error(f"❌ Errore Drive Copy: {e}")
        return None
    
    # 2. TESTI
    reqs = []
    if 'cover' in ai_data:
        reqs.append({'replaceAllText': {'containsText': {'text': '{{TITLE}}'}, 'replaceText': ai_data['cover'].get('title', 'Titolo')}})
        reqs.append({'replaceAllText': {'containsText': {'text': '{{SUBTITLE}}'}, 'replaceText': ai_data['cover'].get('subtitle', '')}})
    
    if 'slides' in ai_data:
        for i, s in enumerate(ai_data['slides']):
            idx = i + 1
            reqs.append({'replaceAllText': {'containsText': {'text': f'{{{{TITLE_{idx}}}}}'}, 'replaceText': s.get('title', '')}})
            reqs.append({'replaceAllText': {'containsText': {'text': f'{{{{BODY_{idx}}}}}'}, 'replaceText': s.get('body', '')}})
            
    if reqs:
        slides_service.presentations().batchUpdate(presentationId=new_id, body={'requests': reqs}).execute()

    # 3. IMMAGINI (Usiamo gli URL già generati nell'anteprima)
    # Mappa le etichette agli URL generati
    url_map = {}
    if 'cover' in ai_data: url_map['IMG_COVER'] = pregenerated_urls.get('cover')
    if 'slides' in ai_data:
        for i, s in enumerate(ai_data['slides']): url_map[f'IMG_{i+1}'] = pregenerated_urls.get(f'slide_{i+1}')
        
    for label, url in url_map.items():
        if url:
            el_id = find_image_element_id_smart(new_id, label)
            if el_id:
                req = {'replaceImage': {'imageObjectId': el_id, 'imageReplaceMethod': 'CENTER_CROP', 'url': url}}
                try:
                    slides_service.presentations().batchUpdate(presentationId=new_id, body={'requests': [req]}).execute()
                    time.sleep(0.5)
                except Exception as e:
                    st.error(f"Errore inserimento immagine {label}: {e}")
    
    return new_id

# --- INTERFACCIA PRINCIPALE ---
st.title("👁️ Slide Monster: Visual Preview")

col1, col2 = st.columns([1, 2])
with col1:
    tmpl = st.text_input("ID Template", value=DEFAULT_TEMPLATE_ID)
    fold = st.text_input("ID Cartella Output", value=DEFAULT_FOLDER_ID)

with col2:
    uploaded = st.file_uploader("Carica PPT", accept_multiple_files=True, type=['pptx'])
    
    # PULSANTE 1: ANALIZZA E GENERA ANTEPRIMA
    if st.button("✨ Genera Anteprima (Senza Salvare)", type="primary"):
        if uploaded:
            st.session_state.results = {} # Reset
            st.session_state.analysis_done = False
            
            bar = st.progress(0)
            for i, f in enumerate(uploaded):
                fname = f.name.replace(".pptx", "") + "_ITA"
                txt = extract_text_from_pptx(f)
                
                # 1. Genera Dati AI
                data = brain_process(txt, selected_gemini, image_style)
                
                if data:
                    # 2. Genera Immagini SUBITO per l'anteprima
                    image_urls = {}
                    
                    # Cover
                    if 'cover' in data:
                        url = generate_image_url(data['cover']['image_prompt'], image_style)
                        image_urls['cover'] = url
                    
                    # Slides
                    if 'slides' in data:
                        for idx, s in enumerate(data['slides']):
                            url = generate_image_url(s['image_prompt'], image_style)
                            image_urls[f'slide_{idx+1}'] = url
                    
                    # Salva tutto in session state
                    st.session_state.results[fname] = {
                        "ai_data": data,
                        "image_urls": image_urls,
                        "original_file": f.name
                    }
                bar.progress((i+1)/len(uploaded))
            
            st.session_state.analysis_done = True
            st.rerun() # Ricarica la pagina per mostrare i risultati

# --- SEZIONE ANTEPRIMA (Si attiva dopo l'analisi) ---
if st.session_state.analysis_done and st.session_state.results:
    st.divider()
    st.header("🎨 Anteprima Generazione")
    
    for fname, content in st.session_state.results.items():
        with st.expander(f"📂 File: {fname}", expanded=True):
            data = content['ai_data']
            urls = content['image_urls']
            
            # Layout Cover
            c1, c2 = st.columns([1, 1])
            with c1:
                st.subheader("Cover")
                if 'cover' in urls:
                    st.image(urls['cover'], caption=data['cover'].get('title'), use_container_width=True)
                st.markdown(f"**Titolo:** {data['cover'].get('title')}")
                st.markdown(f"**Slogan:** {data['cover'].get('subtitle')}")
                st.caption(f"Prompt: {data['cover'].get('image_prompt')}")
            
            # Layout Slide (Esempio prime 2)
            with c2:
                st.subheader("Slide 1 (Esempio)")
                if 'slides' in data and len(data['slides']) > 0:
                    s1 = data['slides'][0]
                    if 'slide_1' in urls:
                        st.image(urls['slide_1'], use_container_width=True)
                    st.markdown(f"**{s1.get('title')}**")
                    st.caption(f"Prompt: {s1.get('image_prompt')}")

            # Mostra JSON completo se serve
            with st.expander("Vedi Dati Grezzi (JSON)"):
                st.json(data)

    # --- PULSANTE FINALE DI SALVATAGGIO ---
    st.divider()
    if st.button("💾 Conferma tutto e Salva su Drive", type="primary", use_container_width=True):
        progress_text = st.empty()
        bar = st.progress(0)
        
        for i, (fname, content) in enumerate(st.session_state.results.items()):
            progress_text.write(f"Scrittura file **{fname}** su Drive...")
            
            res_id = worker_bot_finalize(
                tmpl, 
                fold, 
                fname, 
                content['ai_data'], 
                content['image_urls']
            )
            
            if res_id:
                st.toast(f"✅ Salvato: {fname}")
            else:
                st.error(f"❌ Errore salvataggio: {fname}")
            
            bar.progress((i+1)/len(st.session_state.results))
        
        st.success("Operazione Completata! Controlla il Drive.")
