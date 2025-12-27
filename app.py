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
import requests
from io import BytesIO

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Slide Monster: Director Mode", page_icon="🎬", layout="wide")

# --- I TUOI ID ---
DEFAULT_TEMPLATE_ID = "1BHac-ciWsMCxjtNrv8RxB68LyDi9cZrV6VMWEeXCw5A" 
DEFAULT_FOLDER_ID = "1wL1oxos7ISS03GzfW0db44XoAk3UocV0"

# --- GESTIONE STATO (MEMORIA) ---
if "app_state" not in st.session_state:
    st.session_state.app_state = "UPLOAD" # Stati: UPLOAD -> EDIT -> PREVIEW
if "draft_data" not in st.session_state:
    st.session_state.draft_data = {} # Qui salviamo i testi e i prompt modificabili
if "final_images" not in st.session_state:
    st.session_state.final_images = {} # Qui salviamo gli URL generati

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
    st.header("🎬 Regia")
    models = ["models/gemini-3-pro-preview", "models/gemini-1.5-pro", "models/gemini-1.5-flash"]
    selected_gemini = st.selectbox("Modello Attivo", models, index=0)
    st.divider()
    image_style = st.selectbox("Stile Immagini", ["Imagen 4 (High Fidelity)", "Flux Realism", "Illustrazione 3D"], index=0)
    
    st.divider()
    if st.button("🔄 Reset Totale"):
        st.session_state.app_state = "UPLOAD"
        st.session_state.draft_data = {}
        st.session_state.final_images = {}
        st.rerun()

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
    except Exception:
        return None

def generate_image_url(prompt, style_choice):
    safe_prompt = prompt.replace("\n", " ").strip()
    encoded_prompt = urllib.parse.quote(safe_prompt)
    seed = os.urandom(2).hex()
    return f"[https://image.pollinations.ai/prompt/](https://image.pollinations.ai/prompt/){encoded_prompt}?width=1920&height=1080&model=flux&nologo=true&seed={seed}"

def get_image_bytes(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    for attempt in range(3):
        try:
            response = requests.get(url, headers=headers, timeout=25)
            if response.status_code == 200: return BytesIO(response.content)
            else: time.sleep(1)
        except Exception: time.sleep(1)
    return None

def find_image_element_id_smart(prs_id, label):
    label_clean = label.strip().upper()
    try:
        prs = slides_service.presentations().get(presentationId=prs_id).execute()
        for slide in prs.get('slides', []):
            for el in slide.get('pageElements', []):
                if 'description' in el:
                    if el['description'].strip().upper() == label_clean:
                        return el['objectId']
    except Exception: pass
    return None

def worker_bot_finalize(template_id, folder_id, filename, ai_data, pregenerated_urls):
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
    
    # TESTI
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

    # IMMAGINI
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
                except Exception: pass
    return new_id

# ==========================================
# INTERFACCIA PRINCIPALE - DIRECTOR MODE
# ==========================================

st.title("🎬 Slide Monster: Director Mode")

col1, col2 = st.columns([1, 2])
with col1:
    tmpl = st.text_input("ID Template", value=DEFAULT_TEMPLATE_ID)
    fold = st.text_input("ID Cartella Output", value=DEFAULT_FOLDER_ID)

# --- FASE 1: UPLOAD & ANALISI TESTUALE ---
if st.session_state.app_state == "UPLOAD":
    with col2:
        st.info("Passo 1: Carica i file per generare la bozza dei testi e dei prompt.")
        uploaded = st.file_uploader("Carica PPT", accept_multiple_files=True, type=['pptx'])
        
        if st.button("🧠 Analizza e Proponi Prompt", type="primary"):
            if uploaded:
                st.session_state.draft_data = {}
                bar = st.progress(0)
                
                for i, f in enumerate(uploaded):
                    fname = f.name.replace(".pptx", "") + "_ITA"
                    txt = extract_text_from_pptx(f)
                    data = brain_process(txt, selected_gemini, image_style)
                    
                    if data:
                        # Salviamo la bozza per l'editing
                        st.session_state.draft_data[fname] = {
                            "ai_data": data,
                            "original_file": f.name
                        }
                    bar.progress((i+1)/len(uploaded))
                
                # Passiamo alla fase 2
                st.session_state.app_state = "EDIT"
                st.rerun()

# --- FASE 2: EDITING PROMPT (IL CUORE DEL CONTROLLO) ---
elif st.session_state.app_state == "EDIT":
    st.divider()
    st.subheader("✏️ Revisione Prompt (Sei tu il Regista)")
    st.info("Ecco cosa ha pensato l'AI. Modifica i prompt delle immagini qui sotto. Quando sei pronto, clicca 'Genera Immagini'.")

    # Iteriamo su ogni file caricato
    for fname, content in st.session_state.draft_data.items():
        data = content['ai_data']
        
        with st.expander(f"📝 Modifica File: **{fname}**", expanded=True):
            
            # COVER
            c1, c2 = st.columns([1, 3])
            with c1: st.markdown(f"**Cover:** {data['cover'].get('title')}")
            with c2:
                new_prompt = st.text_area(
                    f"Prompt Cover ({fname})", 
                    value=data['cover'].get('image_prompt', ''), 
                    height=100,
                    key=f"p_cover_{fname}"
                )
                # Salviamo la modifica in tempo reale
                st.session_state.draft_data[fname]['ai_data']['cover']['image_prompt'] = new_prompt

            # SLIDES
            if 'slides' in data:
                for idx, slide in enumerate(data['slides']):
                    st.markdown("---")
                    s_col1, s_col2 = st.columns([1, 3])
                    with s_col1: 
                        st.caption(f"Slide {idx+1}")
                        st.markdown(f"**{slide.get('title')}**")
                    with s_col2:
                        new_slide_prompt = st.text_area(
                            f"Prompt Slide {idx+1} ({fname})", 
                            value=slide.get('image_prompt', ''), 
                            height=80,
                            key=f"p_slide_{idx}_{fname}"
                        )
                        # Salviamo la modifica
                        st.session_state.draft_data[fname]['ai_data']['slides'][idx]['image_prompt'] = new_slide_prompt

    st.divider()
    col_back, col_go = st.columns([1, 5])
    with col_back:
        if st.button("⬅️ Indietro"):
            st.session_state.app_state = "UPLOAD"
            st.rerun()
    with col_go:
        if st.button("🎨 Conferma Prompt e Genera Immagini", type="primary", use_container_width=True):
            st.session_state.app_state = "PREVIEW"
            st.rerun()

# --- FASE 3: GENERAZIONE E ANTEPRIMA ---
elif st.session_state.app_state == "PREVIEW":
    st.divider()
    st.subheader("🎨 Generazione Artistica in corso...")
    
    # Se non abbiamo ancora generato le immagini, facciamolo ora
    if not st.session_state.final_images:
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        total_steps = len(st.session_state.draft_data)
        current_step = 0
        
        for fname, content in st.session_state.draft_data.items():
            status_text.write(f"🎨 Dipingendo immagini per **{fname}**...")
            data = content['ai_data']
            urls = {}
            
            # Generazione Reale (usando i prompt MODIFICATI)
            if 'cover' in data:
                urls['cover'] = generate_image_url(data['cover']['image_prompt'], image_style)
                requests.get(urls['cover'], timeout=5) # Pre-load
            
            if 'slides' in data:
                for idx, s in enumerate(data['slides']):
                    urls[f'slide_{idx+1}'] = generate_image_url(s['image_prompt'], image_style)
                    requests.get(urls[f'slide_{idx+1}'], timeout=5) # Pre-load
            
            st.session_state.final_images[fname] = urls
            current_step += 1
            progress_bar.progress(current_step / total_steps)
            
        status_text.success("Generazione completata!")
        time.sleep(1)
        st.rerun() # Ricarica per mostrare la galleria

    # MOSTRA GALLERIA
    for fname, content in st.session_state.draft_data.items():
        urls = st.session_state.final_images.get(fname, {})
        
        with st.expander(f"👁️ Anteprima Finale: {fname}", expanded=True):
            # Cover
            if 'cover' in urls:
                st.markdown("### Copertina")
                st.image(urls['cover'], caption=content['ai_data']['cover'].get('image_prompt'), use_container_width=True)
            
            # Slide (Griglia)
            st.markdown("### Slide Interne")
            cols = st.columns(3)
            if 'slides' in content['ai_data']:
                for idx, slide in enumerate(content['ai_data']['slides']):
                    key = f'slide_{idx+1}'
                    if key in urls:
                        with cols[idx % 3]:
                            st.image(urls[key], caption=f"Slide {idx+1}", use_container_width=True)
                            with st.popover(f"Vedi Prompt Slide {idx+1}"):
                                st.write(slide.get('image_prompt'))

    st.divider()
    c1, c2 = st.columns([1, 4])
    with c1:
        if st.button("✏️ Torna a Modificare"):
            st.session_state.final_images = {} # Reset immagini se torniamo indietro
            st.session_state.app_state = "EDIT"
            st.rerun()
            
    with c2:
        if st.button("💾 Conferma Tutto e Salva su Drive", type="primary", use_container_width=True):
            bar = st.progress(0)
            st_msg = st.empty()
            
            i = 0
            for fname, content in st.session_state.draft_data.items():
                st_msg.write(f"Scrittura file **{fname}**...")
                urls = st.session_state.final_images.get(fname, {})
                
                res = worker_bot_finalize(tmpl, fold, fname, content['ai_data'], urls)
                
                if res: st.toast(f"✅ Salvato: {fname}")
                else: st.error(f"❌ Errore salvataggio {fname}")
                
                i += 1
                bar.progress(i / len(st.session_state.draft_data))
                
            st.success("Missione Compiuta! 🦖")
            st.balloons()
