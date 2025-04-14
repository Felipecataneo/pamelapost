# -*- coding: utf-8 -*-
import streamlit as st
from PIL import Image, ImageOps # ImageOps pode ser útil para padding/cropping
import io
import numpy as np
import tempfile
import os
from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip
import time # Para nomes de arquivo únicos e evitar colisões de chave

# --- Configuração da Página ---
# Deve ser a primeira chamada do Streamlit
st.set_page_config(page_title="Combinador de Mídias Pro", layout="wide")

# --- Título e Descrição ---
st.title("✨ Combinador de Mídias Pro ✨")
st.write("Combine duas imagens ou vídeos lado a lado, ajuste zoom/foco, adicione um logo personalizável e mantenha a orientação original!")

# --- Funções Auxiliares ---

@st.cache_data(show_spinner=False) # Cache para otimizar zoom/crop repetido com mesmos params
def apply_zoom(img_bytes, img_name, zoom_factor, center_x, center_y):
    """
    Aplica zoom a uma imagem.
    Recebe bytes da imagem para ser compatível com cache do Streamlit.
    Retorna um objeto PIL Image.
    """
    try:
        img = Image.open(io.BytesIO(img_bytes))
    except Exception as e:
        st.error(f"Erro ao abrir imagem '{img_name}' para zoom: {e}")
        return None # Retorna None em caso de erro ao abrir

    if zoom_factor <= 1.0:
        # Retorna uma cópia para evitar modificar o original implicitamente
        return img.copy()

    original_width, original_height = img.size

    # Calcular novo tamanho após o zoom (área a ser cortada)
    crop_width = int(original_width / zoom_factor)
    crop_height = int(original_height / zoom_factor)

    # Garantir que o centro permaneça na imagem (0 a 100)
    center_x = max(0, min(center_x, 100))
    center_y = max(0, min(center_y, 100))

    # Converter percentagem para pixels no centro
    center_x_px = int(original_width * center_x / 100)
    center_y_px = int(original_height * center_y / 100)

    # Calcular as coordenadas do recorte (top-left)
    left = max(0, center_x_px - crop_width // 2)
    top = max(0, center_y_px - crop_height // 2)

    # Calcular as coordenadas do recorte (bottom-right)
    # Garantir que o recorte não exceda as dimensões originais
    right = min(original_width, left + crop_width)
    bottom = min(original_height, top + crop_height)

    # Ajustar left/top se o recorte bateu na borda direita/inferior e ficou menor que o esperado
    if right - left < crop_width:
        left = max(0, right - crop_width)
    if bottom - top < crop_height:
        top = max(0, bottom - crop_height)

    # Garantir que as dimensões do crop sejam válidas (pelo menos 1x1 pixel)
    if left >= right or top >= bottom:
        st.warning(f"Ajuste de zoom/foco inválido para '{img_name}' resultou em dimensões de corte zero ou negativas. Usando imagem original.")
        return img.copy() # Retorna cópia do original se o crop for inválido

    # Recortar a imagem
    try:
        crop = img.crop((left, top, right, bottom))
    except ValueError as e:
        st.error(f"Erro ao cortar a imagem '{img_name}': {e}. Coordenadas: {(left, top, right, bottom)}")
        return img.copy()

    # Redimensionar o recorte de volta para as dimensões originais da imagem
    if crop.width == 0 or crop.height == 0:
         st.warning(f"Crop da imagem '{img_name}' resultou em tamanho zero. Usando imagem original.")
         return img.copy()

    # Usar resampling=Image.LANCZOS para Pillow >= 9 ou Image.LANCZOS para < 9
    resample_method = Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.LANCZOS
    return crop.resize((original_width, original_height), resample=resample_method)

# Função principal de combinação de imagens
# Não usar cache aqui pois depende dos sliders que mudam constantemente
def combine_images_with_logo(img1_obj, img2_obj, logo_obj,
                             logo_x, logo_y, logo_size, logo_opacity,
                             zoom_img1, zoom_img2,
                             zoom_point_x1, zoom_point_y1, zoom_point_x2, zoom_point_y2,
                             img1_name="Imagem 1", img2_name="Imagem 2"):
    """Combina duas imagens PIL lado a lado, aplica zoom e adiciona logo."""

    if not img1_obj or not img2_obj:
         raise ValueError("Objetos de imagem inválidos fornecidos.")

    # Aplicar zoom usando a função cacheada (passando bytes)
    img1_processed = apply_zoom(img1_obj['bytes'], img1_name, zoom_img1, zoom_point_x1, zoom_point_y1)
    img2_processed = apply_zoom(img2_obj['bytes'], img2_name, zoom_img2, zoom_point_x2, zoom_point_y2)

    # Verificar se o zoom retornou imagens válidas
    if not img1_processed or not img2_processed:
        st.error("Falha ao aplicar zoom em uma ou ambas as imagens.")
        return None

    # Obter dimensões APÓS o zoom (que são as mesmas das originais)
    w1, h1 = img1_processed.size
    w2, h2 = img2_processed.size

    # Lidar com imagens de dimensão zero (embora apply_zoom tente evitar)
    if h1 <= 0 or w1 <= 0 or h2 <= 0 or w2 <= 0:
        st.error("Uma das imagens processadas tem dimensões inválidas (<= 0).")
        return None

    # --- Lógica de Redimensionamento para Altura Máxima (Preserva Orientação) ---
    max_height = max(h1, h2)

    # Redimensionar img1 para ter a altura max_height, mantendo a proporção
    ratio1 = max_height / h1
    new_w1 = max(1, int(w1 * ratio1)) # Garantir largura mínima de 1px
    resample_method = Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.LANCZOS
    try:
        img1_resized = img1_processed.resize((new_w1, max_height), resample=resample_method)
    except Exception as e:
        st.error(f"Erro ao redimensionar {img1_name}: {e}")
        return None

    # Redimensionar img2 para ter a altura max_height, mantendo a proporção
    ratio2 = max_height / h2
    new_w2 = max(1, int(w2 * ratio2)) # Garantir largura mínima de 1px
    try:
        img2_resized = img2_processed.resize((new_w2, max_height), resample=resample_method)
    except Exception as e:
        st.error(f"Erro ao redimensionar {img2_name}: {e}")
        return None

    # Calcular a largura total da imagem combinada
    combined_width = new_w1 + new_w2
    if combined_width <= 0:
        st.error("Largura combinada das imagens resultou em valor inválido.")
        return None

    # Criar a nova imagem (canvas) com fundo transparente
    combined_img = Image.new('RGBA', (combined_width, max_height), (255, 255, 255, 0))

    # Colar as imagens redimensionadas lado a lado
    # Garantir que sejam RGBA para colar corretamente no canvas RGBA
    img1_resized = img1_resized.convert('RGBA') if img1_resized.mode != 'RGBA' else img1_resized
    img2_resized = img2_resized.convert('RGBA') if img2_resized.mode != 'RGBA' else img2_resized

    combined_img.paste(img1_resized, (0, 0))
    combined_img.paste(img2_resized, (new_w1, 0)) # Posição X da segunda imagem

    # --- Lógica do Logo ---
    if logo_obj and isinstance(logo_obj.get('image'), Image.Image):
        logo = logo_obj['image'].copy() # Trabalhar com cópia da imagem PIL do logo
        logo_name = logo_obj.get('name', 'Logo')

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

            # Redimensionar o logo
            try:
                if logo_final_width > 0 and logo_final_height > 0:
                    logo_resized = logo.resize((logo_final_width, logo_final_height), resample=resample_method)
                else:
                    st.warning(f"Tamanho calculado do logo '{logo_name}' inválido. Não será adicionado.")
                    logo_resized = None # Flag para não adicionar
            except Exception as e:
                st.error(f"Erro ao redimensionar o logo '{logo_name}': {e}")
                logo_resized = None

            if logo_resized:
                # Converter logo para RGBA para opacidade e transparência
                logo_resized = logo_resized.convert('RGBA') if logo_resized.mode != 'RGBA' else logo_resized

                # Aplicar opacidade
                if logo_opacity < 100:
                    alpha = logo_resized.split()[3]
                    alpha = alpha.point(lambda p: int(p * (logo_opacity / 100.0)))
                    logo_resized.putalpha(alpha)

                # Calcular posição do logo (canto superior esquerdo) baseado no centro percentual
                logo_center_x = combined_width * logo_x / 100
                logo_center_y = max_height * logo_y / 100
                logo_x_pos = max(0, min(int(logo_center_x - logo_resized.width / 2), combined_width - logo_resized.width))
                logo_y_pos = max(0, min(int(logo_center_y - logo_resized.height / 2), max_height - logo_resized.height))

                # Colar o logo usando seu próprio canal alfa como máscara
                combined_img.paste(logo_resized, (logo_x_pos, logo_y_pos), logo_resized)

    return combined_img

# Função de processamento de vídeo (sem alterações significativas na lógica interna)
def process_videos_with_logo(video_file1, video_file2, logo_file, logo_x, logo_y, logo_size, logo_opacity):
    """Combina dois vídeos lado a lado com logo usando MoviePy."""
    # Salvar os arquivos temporariamente
    temp_dir = tempfile.mkdtemp()
    timestamp = int(time.time() * 1000)
    temp_output = os.path.join(temp_dir, f"output_{timestamp}.mp4")
    # Usar nomes base dos arquivos originais se disponíveis, senão genéricos
    vid1_name = getattr(video_file1, 'name', f'video1_{timestamp}')
    vid2_name = getattr(video_file2, 'name', f'video2_{timestamp}')
    logo_name = getattr(logo_file, 'name', f'logo_{timestamp}')
    temp_video1 = os.path.join(temp_dir, f"in_{vid1_name}")
    temp_video2 = os.path.join(temp_dir, f"in_{vid2_name}")
    temp_logo = os.path.join(temp_dir, f"in_{logo_name}.png") # Salvar como PNG

    # Inicializar variáveis para o bloco finally
    video1 = video2 = video1_resized = video2_resized = video1_final = video2_final = logo_clip = final_clip = None
    output_bytes = None

    try:
        # Salvar arquivos de entrada
        video_file1.seek(0)
        with open(temp_video1, "wb") as f: f.write(video_file1.read())
        video_file2.seek(0)
        with open(temp_video2, "wb") as f: f.write(video_file2.read())
        logo_file.seek(0)
        try:
            logo_img = Image.open(logo_file).convert("RGBA") # Garantir RGBA
            logo_img.save(temp_logo, format="PNG")
        except Exception as e:
            raise ValueError(f"Erro ao processar arquivo de logo: {e}") from e

        # Carregar vídeos
        video1 = VideoFileClip(temp_video1)
        video2 = VideoFileClip(temp_video2)

        # Validar vídeos
        if video1.duration is None or video2.duration is None or video1.h <=0 or video2.h <=0:
             raise ValueError("Um ou ambos os vídeos parecem inválidos ou corrompidos.")

        # Determinar altura comum (menor) e duração comum (menor)
        height = min(video1.h, video2.h)
        duration = min(video1.duration, video2.duration)
        if height <= 0 or duration <= 0:
            raise ValueError("Dimensões ou duração inválida(s) detectada(s) nos vídeos.")

        # Redimensionar e cortar vídeos
        video1_resized = video1.resize(height=height)
        video2_resized = video2.resize(height=height)
        video1_final = video1_resized.subclip(0, duration)
        video2_final = video2_resized.subclip(0, duration)

        # Calcular largura combinada APÓS redimensionamento
        combined_width = video1_final.w + video2_final.w
        if combined_width <= 0:
             raise ValueError("Largura combinada do vídeo inválida.")

        # Posicionar segundo vídeo
        video2_final = video2_final.set_position((video1_final.w, 0))

        # Processar Logo
        logo_clip = ImageClip(temp_logo, ismask=False, transparent=True).set_duration(duration)
        if logo_clip.w <= 0:
            st.warning("Logo com largura inválida. Não será adicionado ao vídeo.")
            logo_clip_final = None # Flag para não incluir no CompositeVideoClip
        else:
            # Redimensionar logo
            logo_target_width = max(1, int(combined_width * logo_size / 100))
            logo_clip_resized = logo_clip.resize(width=logo_target_width)

            # Aplicar opacidade
            if logo_opacity < 100:
                logo_clip_resized = logo_clip_resized.set_opacity(logo_opacity / 100.0)

            # Calcular posição (baseado no centro percentual)
            logo_center_x_px = combined_width * logo_x / 100
            logo_center_y_px = height * logo_y / 100
            logo_x_pos_px = max(0, min(int(logo_center_x_px - logo_clip_resized.w / 2), combined_width - logo_clip_resized.w))
            logo_y_pos_px = max(0, min(int(logo_center_y_px - logo_clip_resized.h / 2), height - logo_clip_resized.h))

            logo_clip_final = logo_clip_resized.set_position((logo_x_pos_px, logo_y_pos_px))

        # Combinar clipes
        clips_to_composite = [video1_final, video2_final]
        if logo_clip_final:
            clips_to_composite.append(logo_clip_final)

        final_clip = CompositeVideoClip(clips_to_composite, size=(combined_width, height))

        # Renderizar vídeo final
        st.info("Renderizando vídeo... por favor, aguarde.") # Mensagem durante renderização
        final_clip.write_videofile(temp_output,
                                   codec="libx264", # Codec comum e compatível
                                   audio_codec="aac", # Codec de áudio comum
                                   preset="medium",   # Equilíbrio entre velocidade e qualidade/tamanho
                                   threads=os.cpu_count() or 4, # Usar núcleos disponíveis
                                   logger=None) # 'bar' mostra progresso no console, None para UI limpa

        # Ler bytes do arquivo de saída
        with open(temp_output, "rb") as f:
            output_bytes = f.read()

    except Exception as e:
         st.error(f"Erro durante o processamento do vídeo: {e}")
         # Considerar logar o traceback completo para depuração interna
         # import traceback
         # st.text(traceback.format_exc())
         output_bytes = None # Garante que não retornará nada em caso de erro
         # Não re-levanta a exceção para permitir a limpeza no finally

    finally:
        # --- Liberação de Recursos Crucial ---
        clips_to_close = [video1, video2, video1_resized, video2_resized,
                          video1_final, video2_final, logo_clip, final_clip]
        for clip in clips_to_close:
            if clip:
                try:
                    clip.close()
                except Exception as e:
                    print(f"Warning (non-critical): Could not close moviepy clip: {e}") # Log no console

        # Limpar arquivos temporários
        files_to_remove = [temp_video1, temp_video2, temp_logo, temp_output]
        for file_path in files_to_remove:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except PermissionError:
                     print(f"Warning: Could not remove temp file {os.path.basename(file_path)} (likely still in use).")
                except Exception as e:
                    print(f"Warning: Could not remove temp file {os.path.basename(file_path)}: {e}")
        # Tentar remover o diretório temporário
        if temp_dir and os.path.exists(temp_dir):
            try:
                os.rmdir(temp_dir)
            except OSError as e:
                print(f"Warning: Could not remove temp directory {temp_dir}: {e}")

    return output_bytes

# --- Interface Streamlit ---

st.header("1. Selecione o Tipo de Mídia")
media_type = st.radio("Trabalhar com:", ["Imagens", "Vídeos"], key="media_type_selector", horizontal=True)

# --- Modo Imagens ---
if media_type == "Imagens":
    st.header("2. Carregue suas Imagens")
    col1_img_upload, col2_img_upload = st.columns(2)

    with col1_img_upload:
        uploaded_img1 = st.file_uploader("🖼️ Imagem 1 (Esquerda)", type=["jpg", "jpeg", "png", "webp"], key="img1_upload")
        if uploaded_img1:
            # Armazenar bytes e nome no session_state para usar com cache e detectar mudanças
            if 'img1_data' not in st.session_state or st.session_state.img1_data['name'] != uploaded_img1.name:
                try:
                    img1_bytes = uploaded_img1.getvalue()
                    # Tenta abrir para validar antes de guardar
                    Image.open(io.BytesIO(img1_bytes))
                    st.session_state.img1_data = {"bytes": img1_bytes, "name": uploaded_img1.name}
                    st.rerun() # Força rerun para atualizar preview imediatamente
                except Exception as e:
                    st.error(f"Erro ao carregar Imagem 1 ({uploaded_img1.name}): {e}")
                    if 'img1_data' in st.session_state: del st.session_state.img1_data # Limpa estado se inválido
        # Exibir preview se dados válidos no estado
        if 'img1_data' in st.session_state:
            st.image(st.session_state.img1_data['bytes'], caption=f"Original: {st.session_state.img1_data['name']}", use_container_width=True)
        elif uploaded_img1 is None and 'img1_data' in st.session_state:
             del st.session_state.img1_data # Limpa se usuário removeu o arquivo

    with col2_img_upload:
        uploaded_img2 = st.file_uploader("🖼️ Imagem 2 (Direita)", type=["jpg", "jpeg", "png", "webp"], key="img2_upload")
        if uploaded_img2:
             if 'img2_data' not in st.session_state or st.session_state.img2_data['name'] != uploaded_img2.name:
                try:
                    img2_bytes = uploaded_img2.getvalue()
                    Image.open(io.BytesIO(img2_bytes))
                    st.session_state.img2_data = {"bytes": img2_bytes, "name": uploaded_img2.name}
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao carregar Imagem 2 ({uploaded_img2.name}): {e}")
                    if 'img2_data' in st.session_state: del st.session_state.img2_data
        if 'img2_data' in st.session_state:
             st.image(st.session_state.img2_data['bytes'], caption=f"Original: {st.session_state.img2_data['name']}", use_container_width=True)
        elif uploaded_img2 is None and 'img2_data' in st.session_state:
             del st.session_state.img2_data

    # Controles de zoom e foco (só mostrar se AMBAS as imagens estiverem carregadas)
    if 'img1_data' in st.session_state and 'img2_data' in st.session_state:
        st.divider()
        st.header("3. Ajustes de Zoom e Foco")
        col_adjust1, col_adjust2 = st.columns(2)
        with col_adjust1:
            st.subheader(f"Ajustes: {st.session_state.img1_data['name']}")
            zoom_img1 = st.slider("🔎 Zoom", 1.0, 5.0, 1.0, 0.1, key="zoom_img1", help="Acima de 1.0 aplica zoom.")
            zoom_point_x1 = st.slider("↔️ Foco Horizontal (%)", 0, 100, 50, key="zoom_point_x1", help="0% (Esquerda) a 100% (Direita)")
            zoom_point_y1 = st.slider("↕️ Foco Vertical (%)", 0, 100, 50, key="zoom_point_y1", help="0% (Topo) a 100% (Base)")

        with col_adjust2:
            st.subheader(f"Ajustes: {st.session_state.img2_data['name']}")
            zoom_img2 = st.slider("🔎 Zoom", 1.0, 5.0, 1.0, 0.1, key="zoom_img2", help="Acima de 1.0 aplica zoom.")
            zoom_point_x2 = st.slider("↔️ Foco Horizontal (%)", 0, 100, 50, key="zoom_point_x2", help="0% (Esquerda) a 100% (Direita)")
            zoom_point_y2 = st.slider("↕️ Foco Vertical (%)", 0, 100, 50, key="zoom_point_y2", help="0% (Topo) a 100% (Base)")

    # --- Seção do Logo (Comum a Imagens e Vídeos, mas com controles separados) ---
    st.divider()
    st.header("4. Logo (Opcional)")
    uploaded_logo_img = st.file_uploader("🏷️ Carregar Logo", type=["png", "jpg", "jpeg", "webp"], key="logo_img_upload")

    if uploaded_logo_img:
        if 'logo_img_data' not in st.session_state or st.session_state.logo_img_data['name'] != uploaded_logo_img.name:
            try:
                logo_bytes = uploaded_logo_img.getvalue()
                logo_pil = Image.open(io.BytesIO(logo_bytes)).convert("RGBA") # Converte para RGBA ao carregar
                st.session_state.logo_img_data = {"bytes": logo_bytes, "name": uploaded_logo_img.name, "image": logo_pil}
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao carregar Logo ({uploaded_logo_img.name}): {e}")
                if 'logo_img_data' in st.session_state: del st.session_state.logo_img_data
    # Limpa se usuário removeu
    elif uploaded_logo_img is None and 'logo_img_data' in st.session_state:
        del st.session_state.logo_img_data

    # Mostrar preview e controles do logo SE ele estiver carregado no state
    if 'logo_img_data' in st.session_state:
        logo_data = st.session_state.logo_img_data
        st.image(logo_data['bytes'], caption=f"Logo: {logo_data['name']}", width=150) # Preview menor

        st.subheader("Ajustes do Logo")
        col_logo_pos, col_logo_size = st.columns(2)
        with col_logo_pos:
            logo_x = st.slider("↔️ Posição Horizontal (%)", 0, 100, 50, key="logo_x_img", help="Centro Horizontal: 0% (Esq) a 100% (Dir)")
            logo_y = st.slider("↕️ Posição Vertical (%)", 0, 100, 50, key="logo_y_img", help="Centro Vertical: 0% (Topo) a 100% (Base)")
        with col_logo_size:
            logo_size = st.slider("📏 Tamanho (% da Largura Total)", 1, 50, 15, key="logo_size_img", help="Tamanho relativo à largura combinada.") # Max 50% default
            logo_opacity = st.slider("💧 Opacidade (%)", 0, 100, 80, key="logo_opacity_img", help="0% (Transparente) a 100% (Opaco)")
    else:
        # Define valores padrão se não houver logo, para a função não falhar se chamada
        logo_x, logo_y, logo_size, logo_opacity = 50, 50, 15, 80
        st.info("Carregue um arquivo de logo acima para ajustar sua posição, tamanho e opacidade.")


    # --- Processamento e Exibição da Prévia do Resultado (Imagens) ---
    st.divider()
    st.header("5. Prévia e Download (Imagens)")
    if 'img1_data' in st.session_state and 'img2_data' in st.session_state:
        try:
            # Passa os dicionários do state e os valores atuais dos sliders
            result_image = combine_images_with_logo(
                st.session_state.img1_data,
                st.session_state.img2_data,
                st.session_state.get('logo_img_data'), # Passa dados do logo (pode ser None)
                logo_x, logo_y, logo_size, logo_opacity,
                zoom_img1, zoom_img2,
                zoom_point_x1, zoom_point_y1,
                zoom_point_x2, zoom_point_y2,
                st.session_state.img1_data['name'], # Passa nomes para mensagens de erro
                st.session_state.img2_data['name']
            )

            if result_image and isinstance(result_image, Image.Image):
                st.subheader("Resultado:")
                st.image(result_image, caption="Prévia da Imagem Combinada", use_container_width=True)

                # Botão para download
                buf = io.BytesIO()
                result_image.save(buf, format="PNG") # Salvar como PNG para transparência
                byte_im = buf.getvalue()

                st.download_button(
                    label="💾 Baixar Imagem Combinada (PNG)",
                    data=byte_im,
                    file_name="imagem_combinada.png",
                    mime="image/png",
                    key="download_img_button"
                )
            elif result_image is None:
                # Erro já deve ter sido mostrado dentro da função combine_images
                st.error("Não foi possível gerar a imagem combinada devido a um erro interno.")
            else:
                st.error("Ocorreu um erro inesperado e a imagem não pôde ser gerada.")

        except ValueError as ve:
             st.error(f"Erro de Configuração: {ve}")
        except Exception as e:
            st.error(f"Ocorreu um erro inesperado durante a combinação das imagens:")
            st.exception(e) # Mostra detalhes técnicos do erro

    else:
        st.warning("⬅️ Carregue ambas as imagens (Imagem 1 e Imagem 2) para ver a prévia e habilitar o download.")

# --- Modo Vídeos ---
else: # media_type == "Vídeos"
    st.header("2. Carregue seus Vídeos")
    col1_vid_upload, col2_vid_upload = st.columns(2)

    # Usar session state para guardar os objetos UploadedFile
    with col1_vid_upload:
        uploaded_video1 = st.file_uploader("🎬 Vídeo 1 (Esquerda)", type=["mp4", "mov", "avi", "mkv", "webm"], key="vid1_upload")
        if uploaded_video1:
            # Só atualiza se for um arquivo novo
            if 'vid1_file' not in st.session_state or st.session_state.get('vid1_name') != uploaded_video1.name:
                st.session_state.vid1_file = uploaded_video1
                st.session_state.vid1_name = uploaded_video1.name
                st.rerun() # Atualiza preview
        elif 'vid1_file' in st.session_state and uploaded_video1 is None: # Limpa se usuário removeu
             del st.session_state.vid1_file
             if 'vid1_name' in st.session_state: del st.session_state.vid1_name
             st.rerun()
        # Mostra preview se estiver no state
        if 'vid1_file' in st.session_state:
            st.video(st.session_state.vid1_file)

    with col2_vid_upload:
        uploaded_video2 = st.file_uploader("🎬 Vídeo 2 (Direita)", type=["mp4", "mov", "avi", "mkv", "webm"], key="vid2_upload")
        if uploaded_video2:
            if 'vid2_file' not in st.session_state or st.session_state.get('vid2_name') != uploaded_video2.name:
                st.session_state.vid2_file = uploaded_video2
                st.session_state.vid2_name = uploaded_video2.name
                st.rerun()
        elif 'vid2_file' in st.session_state and uploaded_video2 is None:
             del st.session_state.vid2_file
             if 'vid2_name' in st.session_state: del st.session_state.vid2_name
             st.rerun()
        if 'vid2_file' in st.session_state:
            st.video(st.session_state.vid2_file)

    st.divider()
    st.header("3. Logo para Vídeo (Opcional)")
    # Uploader de logo específico para vídeo (chave diferente)
    uploaded_logo_video = st.file_uploader("🏷️ Carregar Logo para Vídeo", type=["png", "jpg", "jpeg", "webp"], key="logo_vid_upload")

    if uploaded_logo_video:
        if 'logo_vid_file' not in st.session_state or st.session_state.get('logo_vid_name') != uploaded_logo_video.name:
            try:
                # Apenas guardar o file object, validação será feita no processamento
                st.session_state.logo_vid_file = uploaded_logo_video
                st.session_state.logo_vid_name = uploaded_logo_video.name
                st.rerun() # Atualiza preview do logo
            except Exception as e:
                 st.error(f"Erro ao preparar logo do vídeo: {e}")
                 if 'logo_vid_file' in st.session_state: del st.session_state.logo_vid_file
                 if 'logo_vid_name' in st.session_state: del st.session_state.logo_vid_name
    elif 'logo_vid_file' in st.session_state and uploaded_logo_video is None:
        del st.session_state.logo_vid_file
        if 'logo_vid_name' in st.session_state: del st.session_state.logo_vid_name
        st.rerun()

    # Mostrar preview e controles do logo SE ele estiver carregado no state
    if 'logo_vid_file' in st.session_state:
        try:
            logo_vid_preview = Image.open(st.session_state.logo_vid_file)
            st.image(logo_vid_preview, caption=f"Logo: {st.session_state.logo_vid_name}", width=150)
        except Exception as e:
            st.warning(f"Não foi possível gerar preview do logo: {e}")

        st.subheader("Ajustes do Logo no Vídeo")
        # Usar chaves diferentes para os sliders do vídeo
        col_logo_vid_pos, col_logo_vid_size = st.columns(2)
        with col_logo_vid_pos:
            logo_x_video = st.slider("↔️ Posição Horizontal (%)", 0, 100, 50, key="logo_x_vid", help="Centro Horizontal: 0% (Esq) a 100% (Dir)")
            logo_y_video = st.slider("↕️ Posição Vertical (%)", 0, 100, 50, key="logo_y_vid", help="Centro Vertical: 0% (Topo) a 100% (Base)")
        with col_logo_vid_size:
            logo_size_video = st.slider("📏 Tamanho (% da Largura Total)", 1, 50, 15, key="logo_size_vid", help="Tamanho relativo à largura combinada.")
            logo_opacity_video = st.slider("💧 Opacidade (%)", 0, 100, 80, key="logo_opacity_vid", help="0% (Transparente) a 100% (Opaco)")
    else:
        # Valores padrão se não houver logo
        logo_x_video, logo_y_video, logo_size_video, logo_opacity_video = 50, 50, 15, 80
        st.info("Carregue um arquivo de logo acima para ajustar sua posição, tamanho e opacidade no vídeo.")

    st.divider()
    st.header("4. Processar Vídeos")

    # Verificar se todos os arquivos necessários estão no session_state
    # O logo é opcional para o processamento iniciar, mas necessário se ajustes são feitos
    videos_prontos = 'vid1_file' in st.session_state and 'vid2_file' in st.session_state
    logo_pronto = 'logo_vid_file' in st.session_state

    # Botão só é clicável se os dois vídeos estiverem carregados
    if st.button("🚀 Processar Vídeos Agora!", key="process_vid_button", disabled=not videos_prontos, help="Requer que Vídeo 1 e Vídeo 2 estejam carregados."):
        if videos_prontos:
            # Verificar se há logo carregado para passar para a função
            logo_file_to_process = st.session_state.logo_vid_file if logo_pronto else None

            if logo_file_to_process is None:
                st.warning("Iniciando processamento sem logo, pois nenhum foi carregado.")
                # Usar valores padrão para logo, eles não serão usados na função se logo_file_to_process for None
                logo_x_eff, logo_y_eff, logo_size_eff, logo_opacity_eff = 50, 50, 15, 80
            else:
                 logo_x_eff, logo_y_eff, logo_size_eff, logo_opacity_eff = logo_x_video, logo_y_video, logo_size_video, logo_opacity_video

            with st.spinner("⚙️ Processando vídeos... Isso pode levar vários minutos! Por favor, aguarde..."):
                try:
                    # Obter os file objects do state
                    video1_to_process = st.session_state.vid1_file
                    video2_to_process = st.session_state.vid2_file

                    # Resetar ponteiros é feito dentro da função process_videos_with_logo

                    # Processar os vídeos
                    result_bytes = process_videos_with_logo(
                        video1_to_process,
                        video2_to_process,
                        logo_file_to_process, # Pode ser None
                        logo_x_eff, logo_y_eff, logo_size_eff, logo_opacity_eff
                    )

                    if result_bytes:
                        st.header("✅ Vídeo Resultante")
                        # Armazenar no estado para o download funcionar mesmo após rerun
                        st.session_state.video_result_bytes = result_bytes
                        st.video(st.session_state.video_result_bytes, format='video/mp4')
                        st.success("Processamento de vídeo concluído com sucesso!")
                    else:
                        # Erro já foi mostrado dentro de process_videos_with_logo
                        st.error("Falha no processamento do vídeo. Verifique as mensagens de erro acima.")
                        if 'video_result_bytes' in st.session_state:
                             del st.session_state.video_result_bytes # Limpar resultado anterior

                except Exception as e:
                    st.error(f"Erro GERAL e inesperado ao processar os vídeos: {str(e)}")
                    st.exception(e) # Mostra o traceback completo para depuração
                    if 'video_result_bytes' in st.session_state:
                         del st.session_state.video_result_bytes

    # Mostrar botão de download se o resultado existe no state
    if 'video_result_bytes' in st.session_state and st.session_state.video_result_bytes:
         st.download_button(
             label="💾 Baixar Vídeo Combinado (MP4)",
             data=st.session_state.video_result_bytes,
             file_name="video_combinado.mp4",
             mime="video/mp4",
             key="download_vid_button"
         )

    # Mensagens informativas sobre o que falta para habilitar o botão
    if not videos_prontos:
        if 'vid1_file' not in st.session_state and 'vid2_file' not in st.session_state:
            st.warning("⬅️ Carregue o Vídeo 1 e o Vídeo 2 para habilitar o processamento.")
        elif 'vid1_file' not in st.session_state:
            st.warning("⬅️ Carregue o Vídeo 1 para habilitar o processamento.")
        else: # Só falta o vídeo 2
            st.warning("⬅️ Carregue o Vídeo 2 para habilitar o processamento.")


# --- Informações de Ajuda (Atualizadas) ---
st.divider()
with st.expander("ℹ️ Ajuda e Dicas de Uso", expanded=False):
    st.markdown("""
    #### Como Usar

    1.  **Selecione o Tipo:** Escolha se vai trabalhar com `Imagens` ou `Vídeos`.
    2.  **Carregue os Arquivos:** Faça upload das duas mídias principais (imagens ou vídeos) e, opcionalmente, um logo.
        *   *Formatos Suportados:* Imagens (JPG, PNG, WEBP), Vídeos (MP4, MOV, AVI, MKV, WEBM), Logo (como imagem). PNG com transparência é ideal para logos.
    3.  **Ajustes (Imagens):**
        *   Use os sliders de **Zoom** e **Foco** (Horizontal/Vertical) para enquadrar cada imagem individualmente *antes* da combinação.
        *   A prévia do resultado é **atualizada automaticamente** a cada ajuste.
    4.  **Ajustes (Logo):**
        *   Se carregou um logo, use os sliders para definir a **Posição**, **Tamanho** e **Opacidade**.
        *   Para imagens, a prévia com o logo ajustado é mostrada instantaneamente. Para vídeos, os ajustes serão aplicados ao clicar em "Processar".
    5.  **Processar/Baixar:**
        *   **Imagens:** A prévia é o resultado final. Clique em **"Baixar Imagem Combinada (PNG)"** quando estiver satisfeito.
        *   **Vídeos:** Clique em **"Processar Vídeos Agora!"** (requer Vídeo 1 e 2 carregados). Aguarde o processamento. Após a conclusão, o vídeo resultante será exibido e o botão **"Baixar Vídeo Combinado (MP4)"** aparecerá.

    #### Dicas Importantes

    *   **Orientação Preservada:** O app mantém a orientação original das imagens (retrato/paisagem). Imagens são combinadas lado a lado e redimensionadas para terem a **mesma altura** (a da imagem mais alta), preservando a proporção individual.
    *   **Vídeos - Dimensões e Duração:** Vídeos são redimensionados para a **menor altura** entre os dois e cortados para a **menor duração** para garantir sincronia e evitar barras pretas.
    *   **Desempenho:** O processamento de vídeo pode ser **demorado** e consumir recursos do computador (CPU/Memória), especialmente para vídeos longos ou de alta resolução. Seja paciente!
    *   **Prévia:** A prévia dinâmica só está disponível para o modo **Imagens** devido à velocidade de processamento.
    *   **Limpeza:** Se remover um arquivo (clicando no 'x' do uploader), o estado interno é limpo e a prévia/botões são atualizados.
    *   **Erros:** Se encontrar erros, verifique os formatos dos arquivos e tente novamente. Mensagens de erro podem dar pistas sobre o problema.
    """)

# --- Rodapé (Opcional) ---
st.markdown("---")
st.caption("Desenvolvido com Streamlit e ❤️ por IA")