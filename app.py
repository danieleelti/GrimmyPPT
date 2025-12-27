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

# --- GESTIONE STATO ---
if "app_state" not in st.session_state:
    st.session_state.app_state = "UPLOAD"
if "draft_data" not in st.session_state:
    st.session_state.draft_data = {}
if "final_images" not in st.session_state:
    st.session_state.final_images = {} # Qui salviamo gli URL generati man mano

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
    if st.button("🔄 Nuova Sessione (Reset)"):
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
    # Pulizia rigorosa per evitare errori "No connection adapters"
    safe_prompt = prompt.strip().replace("\n", " ").replace("\r", "")
    if safe_prompt.endswith("."): safe_prompt = safe_prompt[:-1]
    
    encoded_prompt = urllib.parse.quote(safe_prompt)
    seed = os.urandom(2).hex()
    
    url = f"[https://image.pollinations.ai/prompt/](https://image.pollinations.ai/prompt/){encoded_prompt}?width=1920&height=1080&model=flux&nologo=true&seed={seed}"
    return url.strip()

def get_image_bytes(url):
    """Scarica l'immagine per l'anteprima"""
    headers = {"User-Agent": "Mozilla/5.0"}
    if not url or not url.startswith("http"): return None
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
    # 1. Copia File
    try:
        copy = drive_service.files().copy(
            fileId=template_id, body={'name': filename, 'parents': [folder_id]}, supportsAllDrives=True
        ).execute()
        new_id = copy.get('id')
    except Exception as e:
        st.error(f"❌ Errore Drive Copy: {e}")
        return None
    
    # 2. Testi
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

    # 3. Immagini (Usa quelle già generate)
    url_map = {}
    if 'cover' in ai_data: url_map['IMG_COVER'] = pregenerated_urls.get('cover')
    if 'slides' in ai_data:
        for i, s in enumerate(ai_data['slides']): url_map[f'IMG_{i+1}'] = pregenerated_urls.get(f'slide_{i+1}')
        
    for label, url in url_map.items():
        if url and url.startswith("http"):
            el_id = find_image_element_id_smart(new_id, label)
            if el_id:
                req = {'replaceImage': {'imageObjectId': el_id, 'imageReplaceMethod': 'CENTER_CROP', 'url': url}}
                try:
                    slides_service.presentations().batchUpdate(presentationId=new_id, body={'requests': [req]}).execute()
                    time.sleep(0.5)
                except Exception: pass
    return new_id

# ==========================================
# INTERFACCIA PRINCIPALE
# ==========================================

st.title("🎬 Slide Monster: Director Mode")

col1, col2 = st.columns([1, 2])
with col1:
    tmpl = st.text_input("ID Template", value=DEFAULT_TEMPLATE_ID)
    fold = st.text_input("ID Cartella Output", value=DEFAULT_FOLDER_ID)

# --- FASE 1: UPLOAD & BOZZA ---
if st.session_state.app_state == "UPLOAD":
    with col2:
        st.info("Passo 1: Carica i file per generare la bozza dei testi e dei prompt.")
        uploaded = st.file_uploader("Carica PPT", accept_multiple_files=True, type=['pptx'])
        
        if st.button("🧠 Analizza e Proponi Prompt", type="primary"):
            if uploaded:
                st.session_state.draft_data = {}
                st.session_state.final_images = {}
                
                bar = st.progress(0)
                for i, f in enumerate(uploaded):
                    fname = f.name.replace(".pptx", "") + "_ITA"
                    txt = extract_text_from_pptx(f)
                    data = brain_process(txt, selected_gemini, image_style)
                    
                    if data:
                        st.session_state.draft_data[fname] = {
                            "ai_data": data,
                            "original_file": f.name
                        }
                        # Crea contenitore vuoto per le immagini di questo file
                        st.session_state.final_images[fname] = {}
                        
                    bar.progress((i+1)/len(uploaded))
                
                st.session_state.app_state = "EDIT"
                st.rerun()

# --- FASE 2: SALA DI REGIA (EDITING PUNTUALE) ---
elif st.session_state.app_state == "EDIT":
    st.divider()
    st.subheader("✏️ Sala di Regia: Genera Immagini Una per Una")
    st.info("Modifica il prompt se vuoi, poi clicca sul pulsante 'Genera' per vedere il risultato IMMEDIATAMENTE.")

    # Loop su ogni file caricato
    for fname, content in st.session_state.draft_data.items():
        data = content['ai_data']
        
        with st.expander(f"📂 File: **{fname}**", expanded=True):
            
            # === COPERTINA ===
            st.markdown("### 1. Copertina")
            c1, c2 = st.columns([1, 1])
            
            # COLONNA SINISTRA: Prompt e Pulsante
            with c1:
                st.markdown(f"**Titolo:** {data['cover'].get('title')}")
                key_prompt_cover = f"p_cover_{fname}"
                new_prompt = st.text_area(
                    "Prompt Copertina", 
                    value=data['cover'].get('image_prompt', ''), 
                    height=100, 
                    key=key_prompt_cover
                )
                # Salviamo il prompt aggiornato
                st.session_state.draft_data[fname]['ai_data']['cover']['image_prompt'] = new_prompt
                
                # PULSANTE DEDICATO COVER
                if st.button(f"🎨 Genera Copertina", key=f"btn_cover_{fname}"):
                    with st.spinner("Creazione immagine in corso..."):
                        url = generate_image_url(new_prompt, image_style)
                        # Salva URL
                        st.session_state.final_images[fname]['cover'] = url
                        # Tentativo di scaricamento (check)
                        try: requests.get(url, timeout=5)
                        except: pass
                        st.rerun() # Ricarica per mostrare l'immagine a destra

            # COLONNA DESTRA: Anteprima Immagine
            with c2:
                current_url = st.session_state.final_images[fname].get('cover')
                if current_url:
                    img_bytes = get_image_bytes(current_url)
                    if img_bytes:
                        st.success("✅ Generata")
                        st.image(img_bytes, use_container_width=True)
                    else:
                        st.warning("⚠️ Immagine creata ma non caricabile (Timeout)")
                else:
                    st.info("L'immagine apparirà qui.")

            st.markdown("---")

            # === SLIDES ===
            if 'slides' in data:
                st.markdown("### 2. Slide Interne")
                for idx, slide in enumerate(data['slides']):
                    s_key = f"slide_{idx+1}"
                    sc1, sc2 = st.columns([1, 1])
                    
                    # COLONNA SINISTRA
                    with sc1:
                        st.caption(f"Slide {idx+1}")
                        st.markdown(f"**{slide.get('title')}**")
                        
                        key_prompt_slide = f"p_slide_{idx}_{fname}"
                        new_slide_prompt = st.text_area(
                            f"Prompt Slide {idx+1}", 
                            value=slide.get('image_prompt', ''), 
                            height=100, 
                            key=key_prompt_slide
                        )
                        st.session_state.draft_data[fname]['ai_data']['slides'][idx]['image_prompt'] = new_slide_prompt
                        
                        # PULSANTE DEDICATO SLIDE
                        if st.button(f"🎨 Genera Slide {idx+1}", key=f"btn_slide_{idx}_{fname}"):
                            with st.spinner(f"Creazione Slide {idx+1}..."):
                                url = generate_image_url(new_slide_prompt, image_style)
                                st.session_state.final_images[fname][s_key] = url
                                try: requests.get(url, timeout=5)
                                except: pass
                                st.rerun()

                    # COLONNA DESTRA
                    with sc2:
                        current_url_slide = st.session_state.final_images[fname].get(s_key)
                        if current_url_slide:
                            img_bytes = get_image_bytes(current_url_slide)
                            if img_bytes:
                                st.success(f"✅ Slide {idx+1}")
                                st.image(img_bytes, use_container_width=True)
                            else:
                                st.warning("⚠️ Errore caricamento")
                        else:
                            st.empty() # Spazio vuoto

                    st.divider()

    # --- FOOTER AZIONI ---
    st.markdown("### ✅ Ho finito")
    col_back, col_save = st.columns([1, 4])
    
    with col_back:
        if st.button("⬅️ Indietro"):
            st.session_state.app_state = "UPLOAD"
            st.rerun()
            
    with col_save:
        if st.button("💾 SALVA TUTTO SU DRIVE", type="primary", use_container_width=True):
            bar = st.progress(0)
            status_box = st.empty()
            
            i = 0
            for fname, content in st.session_state.draft_data.items():
                status_box.write(f"Scrittura file **{fname}** e inserimento immagini...")
                urls = st.session_state.final_images.get(fname, {})
                
                # Chiamata al worker finale che usa gli URL già generati
                res = worker_bot_finalize(tmpl, fold, fname, content['ai_data'], urls)
                
                if res: st.toast(f"✅ Salvato: {fname}")
                else: st.error(f"❌ Errore salvataggio {fname}")
                
                i += 1
                bar.progress(i / len(st.session_state.draft_data))
            
            st.balloons()
            st.success("Operazione Completata! Controlla la cartella Drive.")
