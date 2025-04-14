# -*- coding: utf-8 -*-
import streamlit as st
from PIL import Image, ImageOps # ImageOps é crucial para EXIF
import io
import numpy as np
import tempfile
import os
from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip
import time
import traceback # Para log detalhado de erros

# --- Configuração da Página ---
st.set_page_config(page_title="Combinador de Mídias Pro", layout="wide")

# --- Título e Descrição ---
st.title("✨ Combinador de Mídias Pro ✨")
st.write("Combine duas imagens ou vídeos lado a lado, ajuste zoom/foco, adicione um logo personalizável e **mantenha a orientação original (Retrato/Paisagem)!**")

# --- Funções Auxiliares ---

# Cache para otimizar zoom/crop repetido com mesmos params
# Recebe bytes da imagem ORIGINAL para chave de cache estável
@st.cache_data(show_spinner=False)
def apply_zoom(img_original_bytes, img_name, zoom_factor, center_x, center_y):
    """
    Aplica zoom a uma imagem (baseado nos bytes originais para cache).
    Retorna um objeto PIL Image zoomeado e orientado corretamente.
    """
    try:
        # Abre a imagem a partir dos bytes originais
        img_pil = Image.open(io.BytesIO(img_original_bytes))
        # *** Aplica a correção EXIF aqui também, dentro da função cacheada ***
        # Isso garante que o crop/resize seja feito na imagem orientada corretamente
        img_pil_oriented = ImageOps.exif_transpose(img_pil)

    except Exception as e:
        st.error(f"Erro ao abrir/orientar '{img_name}' para zoom: {e}")
        return None # Retorna None em caso de erro

    if zoom_factor <= 1.0:
        # Retorna a imagem orientada, sem zoom
        return img_pil_oriented.copy()

    original_width, original_height = img_pil_oriented.size # Usa dimensões da imagem orientada

    # Calcular novo tamanho após o zoom (área a ser cortada)
    crop_width = int(original_width / zoom_factor)
    crop_height = int(original_height / zoom_factor)

    # Garantir que o centro permaneça na imagem (0 a 100)
    center_x = max(0, min(center_x, 100))
    center_y = max(0, min(center_y, 100))

    # Converter percentagem para pixels no centro (na imagem orientada)
    center_x_px = int(original_width * center_x / 100)
    center_y_px = int(original_height * center_y / 100)

    # Calcular as coordenadas do recorte (top-left)
    left = max(0, center_x_px - crop_width // 2)
    top = max(0, center_y_px - crop_height // 2)

    # Calcular as coordenadas do recorte (bottom-right)
    right = min(original_width, left + crop_width)
    bottom = min(original_height, top + crop_height)

    # Ajustar left/top se o recorte bateu na borda e ficou menor
    if right - left < crop_width:
        left = max(0, right - crop_width)
    if bottom - top < crop_height:
        top = max(0, bottom - crop_height)

    # Garantir que as dimensões do crop sejam válidas
    if left >= right or top >= bottom:
        st.warning(f"Ajuste de zoom/foco inválido para '{img_name}'. Usando imagem orientada original.")
        return img_pil_oriented.copy()

    # Recortar a imagem JÁ ORIENTADA
    try:
        crop = img_pil_oriented.crop((left, top, right, bottom))
    except ValueError as e:
        st.error(f"Erro ao cortar '{img_name}': {e}. Coords: {(left, top, right, bottom)}")
        return img_pil_oriented.copy()

    # Redimensionar o recorte de volta para as dimensões originais (da imagem orientada)
    if crop.width <= 0 or crop.height <= 0:
         st.warning(f"Crop de '{img_name}' resultou em tamanho inválido. Usando imagem orientada original.")
         return img_pil_oriented.copy()

    resample_method = Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.LANCZOS
    try:
        zoomed_img = crop.resize((original_width, original_height), resample=resample_method)
        return zoomed_img
    except Exception as e:
        st.error(f"Erro ao redimensionar crop de '{img_name}': {e}")
        return img_pil_oriented.copy() # Retorna orientada original em caso de erro

# Função principal de combinação de imagens
def combine_images_with_logo(img1_data, img2_data, logo_data, # Recebe os dicionários do session_state
                             logo_x, logo_y, logo_size, logo_opacity,
                             zoom_img1, zoom_img2,
                             zoom_point_x1, zoom_point_y1, zoom_point_x2, zoom_point_y2):
    """Combina duas imagens PIL lado a lado, aplica zoom e adiciona logo."""

    # Validações Iniciais
    if not img1_data or not img1_data.get('corrected_image') or not isinstance(img1_data['corrected_image'], Image.Image):
        st.error("Dados da Imagem 1 inválidos ou ausentes.")
        return None
    if not img2_data or not img2_data.get('corrected_image') or not isinstance(img2_data['corrected_image'], Image.Image):
        st.error("Dados da Imagem 2 inválidos ou ausentes.")
        return None

    img1_name = img1_data.get('name', 'Imagem 1')
    img2_name = img2_data.get('name', 'Imagem 2')

    # Aplicar zoom usando a função cacheada (passando bytes originais)
    # O resultado já será um objeto PIL orientado e zoomeado/recortado corretamente
    img1_processed = apply_zoom(img1_data['original_bytes'], img1_name, zoom_img1, zoom_point_x1, zoom_point_y1)
    img2_processed = apply_zoom(img2_data['original_bytes'], img2_name, zoom_img2, zoom_point_x2, zoom_point_y2)

    # Verificar se o zoom retornou imagens válidas
    if not img1_processed or not isinstance(img1_processed, Image.Image):
        st.error(f"Falha ao aplicar zoom na {img1_name}.")
        return None
    if not img2_processed or not isinstance(img2_processed, Image.Image):
        st.error(f"Falha ao aplicar zoom na {img2_name}.")
        return None

    # Obter dimensões das imagens JÁ PROCESSADAS (zoomeadas e orientadas)
    w1, h1 = img1_processed.size
    w2, h2 = img2_processed.size

    if h1 <= 0 or w1 <= 0 or h2 <= 0 or w2 <= 0:
        st.error("Uma das imagens processadas (pós-zoom) tem dimensões inválidas (<= 0).")
        return None

    # --- Lógica de Redimensionamento para Altura Máxima (Preserva Orientação) ---
    max_height = max(h1, h2)

    resample_method = Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.LANCZOS

    # Redimensionar img1 processada para ter a altura max_height, mantendo a proporção
    ratio1 = max_height / h1
    new_w1 = max(1, int(w1 * ratio1))
    try:
        img1_resized = img1_processed.resize((new_w1, max_height), resample=resample_method)
    except Exception as e:
        st.error(f"Erro ao redimensionar {img1_name} processada: {e}")
        return None

    # Redimensionar img2 processada para ter a altura max_height, mantendo a proporção
    ratio2 = max_height / h2
    new_w2 = max(1, int(w2 * ratio2))
    try:
        img2_resized = img2_processed.resize((new_w2, max_height), resample=resample_method)
    except Exception as e:
        st.error(f"Erro ao redimensionar {img2_name} processada: {e}")
        return None

    # Calcular a largura total da imagem combinada
    combined_width = new_w1 + new_w2
    if combined_width <= 0:
        st.error("Largura combinada das imagens resultou em valor inválido.")
        return None

    # Criar a nova imagem (canvas) com fundo transparente
    combined_img = Image.new('RGBA', (combined_width, max_height), (255, 255, 255, 0))

    # Colar as imagens redimensionadas lado a lado (já devem estar orientadas corretamente)
    img1_resized = img1_resized.convert('RGBA') if img1_resized.mode != 'RGBA' else img1_resized
    img2_resized = img2_resized.convert('RGBA') if img2_resized.mode != 'RGBA' else img2_resized

    combined_img.paste(img1_resized, (0, 0))
    combined_img.paste(img2_resized, (new_w1, 0))

    # --- Lógica do Logo ---
    # Verifica se logo_data existe e contém uma imagem PIL válida e corrigida
    if logo_data and isinstance(logo_data.get('corrected_image'), Image.Image):
        logo = logo_data['corrected_image'].copy() # Usa a imagem JÁ CORRIGIDA do logo
        logo_name = logo_data.get('name', 'Logo')

        if logo.width <= 0 or logo.height <= 0:
            st.warning(f"Arquivo de logo '{logo_name}' tem dimensões inválidas.")
        else:
            # Redimensionando o logo com base na LARGURA COMBINADA
            logo_base_width = int(combined_width * logo_size / 100)
            logo_ratio = logo.height / logo.width
            logo_final_width = max(1, logo_base_width)
            logo_final_height = max(1, int(logo_final_width * logo_ratio))

            # Garantir que o logo não seja maior que a imagem combinada
            logo_final_width = min(logo_final_width, combined_width)
            logo_final_height = min(logo_final_height, max_height)

            try:
                if logo_final_width > 0 and logo_final_height > 0:
                    logo_resized = logo.resize((logo_final_width, logo_final_height), resample=resample_method)
                else:
                    st.warning(f"Tamanho calculado do logo '{logo_name}' inválido. Não será adicionado.")
                    logo_resized = None
            except Exception as e:
                st.error(f"Erro ao redimensionar o logo '{logo_name}': {e}")
                logo_resized = None

            if logo_resized:
                logo_resized = logo_resized.convert('RGBA') if logo_resized.mode != 'RGBA' else logo_resized

                if logo_opacity < 100:
                    alpha = logo_resized.split()[3]
                    alpha = alpha.point(lambda p: int(p * (logo_opacity / 100.0)))
                    logo_resized.putalpha(alpha)

                logo_center_x = combined_width * logo_x / 100
                logo_center_y = max_height * logo_y / 100
                logo_x_pos = max(0, min(int(logo_center_x - logo_resized.width / 2), combined_width - logo_resized.width))
                logo_y_pos = max(0, min(int(logo_center_y - logo_resized.height / 2), max_height - logo_resized.height))

                combined_img.paste(logo_resized, (logo_x_pos, logo_y_pos), logo_resized)

    return combined_img

# Função de processamento de vídeo (sem alterações na lógica interna de vídeo, mas mantém EXIF no logo se aplicável)
def process_videos_with_logo(video_file1, video_file2, logo_data, # Recebe logo_data
                            logo_x, logo_y, logo_size, logo_opacity):
    """Combina dois vídeos lado a lado com logo usando MoviePy."""
    temp_dir = tempfile.mkdtemp()
    timestamp = int(time.time() * 1000)
    temp_output = os.path.join(temp_dir, f"output_{timestamp}.mp4")
    vid1_name = getattr(video_file1, 'name', f'video1_{timestamp}')
    vid2_name = getattr(video_file2, 'name', f'video2_{timestamp}')
    temp_video1 = os.path.join(temp_dir, f"in_{vid1_name}")
    temp_video2 = os.path.join(temp_dir, f"in_{vid2_name}")
    temp_logo = None # Será definido se houver logo

    video1 = video2 = video1_resized = video2_resized = video1_final = video2_final = logo_clip = final_clip = None
    output_bytes = None

    try:
        # Salvar vídeos de entrada
        video_file1.seek(0)
        with open(temp_video1, "wb") as f: f.write(video_file1.read())
        video_file2.seek(0)
        with open(temp_video2, "wb") as f: f.write(video_file2.read())

        # Salvar logo (se existir) como PNG, usando a imagem JÁ CORRIGIDA
        if logo_data and isinstance(logo_data.get('corrected_image'), Image.Image):
             logo_name = logo_data.get('name', f'logo_{timestamp}')
             temp_logo = os.path.join(temp_dir, f"in_{logo_name}.png")
             try:
                 logo_img_corrected = logo_data['corrected_image'].convert("RGBA") # Usa a imagem corrigida
                 logo_img_corrected.save(temp_logo, format="PNG")
             except Exception as e:
                 st.warning(f"Erro ao salvar o logo orientado para vídeo: {e}. Processando sem logo.")
                 temp_logo = None # Anula se erro ao salvar
        else:
            st.info("Nenhum logo válido carregado para o vídeo.")
            temp_logo = None

        # Carregar vídeos
        video1 = VideoFileClip(temp_video1)
        video2 = VideoFileClip(temp_video2)

        # Validações de vídeo
        if video1.duration is None or video2.duration is None or video1.h <=0 or video2.h <=0:
             raise ValueError("Um ou ambos os vídeos parecem inválidos ou corrompidos.")
        height = min(video1.h, video2.h)
        duration = min(video1.duration, video2.duration)
        if height <= 0 or duration <= 0:
            raise ValueError("Dimensões ou duração inválida(s) detectada(s) nos vídeos.")

        # Redimensionar e cortar vídeos
        video1_resized = video1.resize(height=height)
        video2_resized = video2.resize(height=height)
        video1_final = video1_resized.subclip(0, duration)
        video2_final = video2_resized.subclip(0, duration)

        combined_width = video1_final.w + video2_final.w
        if combined_width <= 0: raise ValueError("Largura combinada do vídeo inválida.")
        video2_final = video2_final.set_position((video1_final.w, 0))

        # Processar Logo (se o arquivo temporário foi criado)
        logo_clip_final = None
        if temp_logo and os.path.exists(temp_logo):
            try:
                logo_clip = ImageClip(temp_logo, ismask=False, transparent=True).set_duration(duration)
                if logo_clip.w <= 0:
                    st.warning("Logo com largura inválida no vídeo. Não será adicionado.")
                else:
                    logo_target_width = max(1, int(combined_width * logo_size / 100))
                    logo_clip_resized = logo_clip.resize(width=logo_target_width)
                    if logo_opacity < 100:
                        logo_clip_resized = logo_clip_resized.set_opacity(logo_opacity / 100.0)

                    logo_center_x_px = combined_width * logo_x / 100
                    logo_center_y_px = height * logo_y / 100
                    logo_x_pos_px = max(0, min(int(logo_center_x_px - logo_clip_resized.w / 2), combined_width - logo_clip_resized.w))
                    logo_y_pos_px = max(0, min(int(logo_center_y_px - logo_clip_resized.h / 2), height - logo_clip_resized.h))
                    logo_clip_final = logo_clip_resized.set_position((logo_x_pos_px, logo_y_pos_px))
            except Exception as e:
                st.error(f"Erro ao processar o logo para o vídeo: {e}")
                logo_clip_final = None # Ignora logo se houver erro

        # Combinar clipes
        clips_to_composite = [video1_final, video2_final]
        if logo_clip_final:
            clips_to_composite.append(logo_clip_final)
        final_clip = CompositeVideoClip(clips_to_composite, size=(combined_width, height))

        # Renderizar vídeo final
        st.info("Renderizando vídeo... por favor, aguarde.")
        final_clip.write_videofile(temp_output, codec="libx264", audio_codec="aac", preset="medium", threads=os.cpu_count() or 4, logger=None)

        with open(temp_output, "rb") as f: output_bytes = f.read()

    except Exception as e:
         st.error(f"Erro durante o processamento do vídeo: {e}")
         st.text(traceback.format_exc()) # Log mais detalhado
         output_bytes = None
    finally:
        # Liberação de Recursos (Mesmo código de antes)
        clips_to_close = [video1, video2, video1_resized, video2_resized, video1_final, video2_final, logo_clip, final_clip]
        for clip in clips_to_close:
            if clip:
                try: clip.close()
                except Exception as e: print(f"Warning (non-critical): Could not close moviepy clip: {e}")
        files_to_remove = [temp_video1, temp_video2, temp_logo, temp_output]
        for file_path in files_to_remove:
            if file_path and os.path.exists(file_path):
                try: os.remove(file_path)
                except Exception as e: print(f"Warning: Could not remove temp file {os.path.basename(file_path)}: {e}")
        if temp_dir and os.path.exists(temp_dir):
            try: os.rmdir(temp_dir)
            except OSError as e: print(f"Warning: Could not remove temp directory {temp_dir}: {e}")

    return output_bytes

# --- Interface Streamlit ---

st.header("1. Selecione o Tipo de Mídia")
media_type = st.radio("Trabalhar com:", ["Imagens", "Vídeos"], key="media_type_selector", horizontal=True)

# --- Modo Imagens ---
if media_type == "Imagens":
    st.header("2. Carregue suas Imagens")
    col1_img_upload, col2_img_upload = st.columns(2)

    # Função auxiliar para carregar e corrigir imagem
    def load_and_correct_image(uploaded_file, session_state_key, img_label):
        if uploaded_file:
            data_key = f"{session_state_key}_data"
            current_data = st.session_state.get(data_key)
            # Recarrega se não existe ou o nome mudou
            if not current_data or current_data['name'] != uploaded_file.name:
                try:
                    original_bytes = uploaded_file.getvalue()
                    img_original_pil = Image.open(io.BytesIO(original_bytes))
                    # *** APLICA CORREÇÃO EXIF AQUI ***
                    img_corrected_pil = ImageOps.exif_transpose(img_original_pil)
                    # Armazena bytes originais E imagem corrigida
                    st.session_state[data_key] = {
                        "original_bytes": original_bytes, # Para cache do zoom
                        "name": uploaded_file.name,
                        "corrected_image": img_corrected_pil # Para processamento
                    }
                    # st.rerun() # Pode causar loop se não for cuidadoso, melhor evitar por enquanto
                except Exception as e:
                    st.error(f"Erro ao carregar/corrigir {img_label} ({uploaded_file.name}): {e}")
                    if data_key in st.session_state: del st.session_state[data_key]
        # Limpa se usuário removeu o arquivo
        elif session_state_key + "_data" in st.session_state and uploaded_file is None:
            del st.session_state[session_state_key + "_data"]


    with col1_img_upload:
        uploaded_img1 = st.file_uploader("🖼️ Imagem 1 (Esquerda)", type=["jpg", "jpeg", "png", "webp"], key="img1_upload")
        load_and_correct_image(uploaded_img1, "img1", "Imagem 1")
        # Exibir preview usando a imagem CORRIGIDA
        if 'img1_data' in st.session_state:
            st.image(st.session_state.img1_data['corrected_image'], caption=f"Original: {st.session_state.img1_data['name']}", use_container_width=True)

    with col2_img_upload:
        uploaded_img2 = st.file_uploader("🖼️ Imagem 2 (Direita)", type=["jpg", "jpeg", "png", "webp"], key="img2_upload")
        load_and_correct_image(uploaded_img2, "img2", "Imagem 2")
        if 'img2_data' in st.session_state:
            st.image(st.session_state.img2_data['corrected_image'], caption=f"Original: {st.session_state.img2_data['name']}", use_container_width=True)

    # Controles de zoom e foco
    if 'img1_data' in st.session_state and 'img2_data' in st.session_state:
        st.divider()
        st.header("3. Ajustes de Zoom e Foco")
        col_adjust1, col_adjust2 = st.columns(2)
        with col_adjust1:
            st.subheader(f"Ajustes: {st.session_state.img1_data['name']}")
            zoom_img1 = st.slider("🔎 Zoom", 1.0, 5.0, 1.0, 0.1, key="zoom_img1")
            zoom_point_x1 = st.slider("↔️ Foco H (%)", 0, 100, 50, key="zoom_point_x1")
            zoom_point_y1 = st.slider("↕️ Foco V (%)", 0, 100, 50, key="zoom_point_y1")
        with col_adjust2:
            st.subheader(f"Ajustes: {st.session_state.img2_data['name']}")
            zoom_img2 = st.slider("🔎 Zoom", 1.0, 5.0, 1.0, 0.1, key="zoom_img2")
            zoom_point_x2 = st.slider("↔️ Foco H (%)", 0, 100, 50, key="zoom_point_x2")
            zoom_point_y2 = st.slider("↕️ Foco V (%)", 0, 100, 50, key="zoom_point_y2")

    # --- Seção do Logo (Comum, mas usa chave diferente e aplica EXIF) ---
    st.divider()
    st.header("4. Logo (Opcional)")
    uploaded_logo_img = st.file_uploader("🏷️ Carregar Logo", type=["png", "jpg", "jpeg", "webp"], key="logo_img_upload")
    load_and_correct_image(uploaded_logo_img, "logo_img", "Logo") # Usa a mesma função

    # Mostrar preview e controles do logo SE ele estiver carregado
    if 'logo_img_data' in st.session_state:
        logo_data_img = st.session_state.logo_img_data
        # Exibe preview da imagem JÁ CORRIGIDA
        st.image(logo_data_img['corrected_image'], caption=f"Logo: {logo_data_img['name']}", width=150)

        st.subheader("Ajustes do Logo")
        col_logo_pos, col_logo_size = st.columns(2)
        with col_logo_pos:
            logo_x = st.slider("↔️ Posição H (%)", 0, 100, 50, key="logo_x_img")
            logo_y = st.slider("↕️ Posição V (%)", 0, 100, 50, key="logo_y_img")
        with col_logo_size:
            logo_size = st.slider("📏 Tamanho (% Largura)", 1, 50, 15, key="logo_size_img")
            logo_opacity = st.slider("💧 Opacidade (%)", 0, 100, 80, key="logo_opacity_img")
    else:
        logo_x, logo_y, logo_size, logo_opacity = 50, 50, 15, 80
        st.info("Carregue um arquivo de logo acima para ajustar.")

    # --- Processamento e Exibição da Prévia (Imagens) ---
    st.divider()
    st.header("5. Prévia e Download (Imagens)")
    if 'img1_data' in st.session_state and 'img2_data' in st.session_state:
        try:
            # Chama a função passando os dicionários completos do state
            result_image = combine_images_with_logo(
                st.session_state.img1_data,
                st.session_state.img2_data,
                st.session_state.get('logo_img_data'), # Pode ser None
                logo_x, logo_y, logo_size, logo_opacity,
                # Passa os valores atuais dos sliders de zoom/foco
                st.session_state.get("zoom_img1", 1.0), st.session_state.get("zoom_img2", 1.0),
                st.session_state.get("zoom_point_x1", 50), st.session_state.get("zoom_point_y1", 50),
                st.session_state.get("zoom_point_x2", 50), st.session_state.get("zoom_point_y2", 50)
            )

            if result_image and isinstance(result_image, Image.Image):
                st.subheader("Resultado:")
                st.image(result_image, caption="Prévia da Imagem Combinada", use_container_width=True)
                buf = io.BytesIO()
                result_image.save(buf, format="PNG")
                byte_im = buf.getvalue()
                st.download_button(label="💾 Baixar Imagem (PNG)", data=byte_im, file_name="imagem_combinada.png", mime="image/png", key="download_img_button")
            elif result_image is None:
                 st.error("Não foi possível gerar a imagem. Verifique os erros acima.")

        except Exception as e:
            st.error(f"Erro inesperado ao gerar a prévia:")
            st.exception(e)
    else:
        st.warning("⬅️ Carregue Imagem 1 e Imagem 2 para ver a prévia.")

# --- Modo Vídeos ---
else: # media_type == "Vídeos"
    st.header("2. Carregue seus Vídeos")
    col1_vid_upload, col2_vid_upload = st.columns(2)

    # Função auxiliar para vídeo (sem correção EXIF, só guarda file object)
    def load_video(uploaded_file, session_state_key):
         if uploaded_file:
             if session_state_key not in st.session_state or st.session_state.get(f"{session_state_key}_name") != uploaded_file.name:
                 st.session_state[session_state_key] = uploaded_file
                 st.session_state[f"{session_state_key}_name"] = uploaded_file.name
                 # st.rerun() # Cuidado com reruns
         elif session_state_key in st.session_state and uploaded_file is None:
             del st.session_state[session_state_key]
             if f"{session_state_key}_name" in st.session_state: del st.session_state[f"{session_state_key}_name"]
             # st.rerun()

    with col1_vid_upload:
        uploaded_video1 = st.file_uploader("🎬 Vídeo 1 (Esquerda)", type=["mp4", "mov", "avi", "mkv", "webm"], key="vid1_upload")
        load_video(uploaded_video1, "vid1_file")
        if 'vid1_file' in st.session_state: st.video(st.session_state.vid1_file)

    with col2_vid_upload:
        uploaded_video2 = st.file_uploader("🎬 Vídeo 2 (Direita)", type=["mp4", "mov", "avi", "mkv", "webm"], key="vid2_upload")
        load_video(uploaded_video2, "vid2_file")
        if 'vid2_file' in st.session_state: st.video(st.session_state.vid2_file)

    st.divider()
    st.header("3. Logo para Vídeo (Opcional)")
    # Usa a mesma função de carregar imagem, mas chave de state diferente
    uploaded_logo_video = st.file_uploader("🏷️ Carregar Logo para Vídeo", type=["png", "jpg", "jpeg", "webp"], key="logo_vid_upload")
    load_and_correct_image(uploaded_logo_video, "logo_vid", "Logo do Vídeo") # Aplica EXIF se houver

    # Mostrar preview e controles do logo do vídeo
    if 'logo_vid_data' in st.session_state:
        logo_data_vid = st.session_state.logo_vid_data
        st.image(logo_data_vid['corrected_image'], caption=f"Logo: {logo_data_vid['name']}", width=150) # Preview corrigido
        st.subheader("Ajustes do Logo no Vídeo")
        col_logo_vid_pos, col_logo_vid_size = st.columns(2)
        with col_logo_vid_pos:
            logo_x_video = st.slider("↔️ Posição H (%)", 0, 100, 50, key="logo_x_vid")
            logo_y_video = st.slider("↕️ Posição V (%)", 0, 100, 50, key="logo_y_vid")
        with col_logo_vid_size:
            logo_size_video = st.slider("📏 Tamanho (% Largura)", 1, 50, 15, key="logo_size_vid")
            logo_opacity_video = st.slider("💧 Opacidade (%)", 0, 100, 80, key="logo_opacity_vid")
    else:
        logo_x_video, logo_y_video, logo_size_video, logo_opacity_video = 50, 50, 15, 80
        st.info("Carregue um logo acima para ajustar.")

    st.divider()
    st.header("4. Processar Vídeos")

    videos_prontos = 'vid1_file' in st.session_state and 'vid2_file' in st.session_state
    # Botão habilitado apenas se os vídeos estiverem carregados
    if st.button("🚀 Processar Vídeos Agora!", key="process_vid_button", disabled=not videos_prontos, help="Requer Vídeo 1 e 2 carregados."):
        if videos_prontos:
            # Passa os dados do logo do vídeo (pode ser None)
            logo_data_to_process = st.session_state.get('logo_vid_data')

            if logo_data_to_process is None: st.warning("Processando sem logo.")

            with st.spinner("⚙️ Processando vídeos... Isso pode levar vários minutos!"):
                try:
                    result_bytes = process_videos_with_logo(
                        st.session_state.vid1_file,
                        st.session_state.vid2_file,
                        logo_data_to_process, # Passa o dicionário do logo
                        # Usa os valores dos sliders específicos do vídeo
                        st.session_state.get("logo_x_vid", 50),
                        st.session_state.get("logo_y_vid", 50),
                        st.session_state.get("logo_size_vid", 15),
                        st.session_state.get("logo_opacity_vid", 80)
                    )
                    if result_bytes:
                        st.header("✅ Vídeo Resultante")
                        st.session_state.video_result_bytes = result_bytes
                        st.video(st.session_state.video_result_bytes, format='video/mp4')
                        st.success("Processamento concluído!")
                    else:
                        st.error("Falha no processamento. Verifique erros acima.")
                        if 'video_result_bytes' in st.session_state: del st.session_state.video_result_bytes
                except Exception as e:
                    st.error(f"Erro GERAL ao processar vídeos: {str(e)}")
                    st.exception(e)
                    if 'video_result_bytes' in st.session_state: del st.session_state.video_result_bytes

    # Botão de download do vídeo
    if 'video_result_bytes' in st.session_state and st.session_state.video_result_bytes:
         st.download_button(label="💾 Baixar Vídeo (MP4)", data=st.session_state.video_result_bytes, file_name="video_combinado.mp4", mime="video/mp4", key="download_vid_button")

    # Mensagens informativas
    if not videos_prontos:
        st.warning("⬅️ Carregue Vídeo 1 e Vídeo 2 para habilitar o processamento.")

# --- Informações de Ajuda ---
st.divider()
with st.expander("ℹ️ Ajuda e Dicas de Uso", expanded=False):
    st.markdown("""
    #### Como Usar
    1.  **Selecione o Tipo:** `Imagens` ou `Vídeos`.
    2.  **Carregue os Arquivos:** Faça upload das duas mídias principais e, opcionalmente, um logo. **A orientação (retrato/paisagem) das imagens será corrigida automaticamente.**
    3.  **Ajustes (Imagens):** Use Zoom/Foco. A prévia atualiza automaticamente.
    4.  **Ajustes (Logo):** Use Posição/Tamanho/Opacidade. Para imagens, a prévia atualiza; para vídeos, os ajustes são aplicados no processamento.
    5.  **Processar/Baixar:**
        *   **Imagens:** Veja a prévia e clique em **"Baixar Imagem (PNG)"**.
        *   **Vídeos:** Clique em **"Processar Vídeos Agora!"**, aguarde, e depois clique em **"Baixar Vídeo (MP4)"**.

    #### Dicas Importantes
    *   **Orientação EXIF:** Corrigida automaticamente para imagens carregadas (incluindo logos).
    *   **Dimensões (Imagens):** Combinadas lado a lado, mesma altura (da mais alta), proporção mantida.
    *   **Dimensões (Vídeos):** Combinadas lado a lado, menor altura, menor duração.
    *   **Desempenho:** Processamento de vídeo é lento.
    *   **Prévia:** Só para imagens.
    """)

# --- Rodapé ---
st.markdown("---")
st.caption("Combinador Pro v1.1 - Orientação Corrigida")