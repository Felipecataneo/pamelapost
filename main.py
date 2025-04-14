import streamlit as st
from PIL import Image, ImageOps # ImageOps pode ser útil para padding se necessário
import io
import numpy as np
import tempfile
import os
from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip

st.set_page_config(page_title="Combinador de Mídias", layout="wide")

st.title("Combinador de Imagens e Vídeos com Logo")
st.write("Este aplicativo combina duas imagens ou vídeos lado a lado, preservando a orientação original das imagens, e adiciona um logo.")

# Função para aplicar zoom (sem alterações)
def apply_zoom(img, zoom_factor, center_x, center_y):
    if zoom_factor <= 1.0:
        return img.copy()
       
    original_width, original_height = img.size
   
    # Calcular novo tamanho após o zoom (área a ser cortada)
    crop_width = int(original_width / zoom_factor)
    crop_height = int(original_height / zoom_factor)
   
    # Garantir que o centro permaneça na imagem
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

    # Recortar a imagem
    crop = img.crop((left, top, right, bottom))
   
    # Redimensionar o recorte de volta para as dimensões originais da imagem
    return crop.resize((original_width, original_height), Image.LANCZOS)

# Função para combinar imagens LADO A LADO, MANTENDO ORIENTAÇÃO VISUAL
def combine_images_with_logo(img1_orig, img2_orig, logo_orig, logo_x, logo_y, logo_size, logo_opacity, zoom_img1, zoom_img2, zoom_point_x1, zoom_point_y1, zoom_point_x2, zoom_point_y2):
   
    # Aplicar zoom primeiro, se necessário
    img1 = apply_zoom(img1_orig, zoom_img1, zoom_point_x1, zoom_point_y1)
    img2 = apply_zoom(img2_orig, zoom_img2, zoom_point_x2, zoom_point_y2)

    # ----- Lógica de Redimensionamento para Altura Máxima -----
   
    # Obter dimensões após o zoom (que são as mesmas das originais)
    w1, h1 = img1.size
    w2, h2 = img2.size

    # Determinar a altura máxima
    max_height = max(h1, h2)
   
    # Se max_height for 0, não há o que fazer
    if max_height == 0:
         raise ValueError("Altura da imagem inválida (0).")

    # Redimensionar img1 para ter a altura max_height, mantendo a proporção
    if h1 > 0:
        ratio1 = max_height / h1
        new_w1 = int(w1 * ratio1)
        img1_resized = img1.resize((new_w1, max_height), Image.LANCZOS)
    else:
        # Caso de altura 0 (improvável, mas defensivo)
        new_w1 = 0
        img1_resized = Image.new('RGBA', (0, max_height))

    # Redimensionar img2 para ter a altura max_height, mantendo a proporção
    if h2 > 0:
        ratio2 = max_height / h2
        new_w2 = int(w2 * ratio2)
        img2_resized = img2.resize((new_w2, max_height), Image.LANCZOS)
    else:
        # Caso de altura 0
        new_w2 = 0
        img2_resized = Image.new('RGBA', (0, max_height))

    # Calcular a largura total da imagem combinada
    combined_width = new_w1 + new_w2

    # Se a largura combinada for 0, não há o que fazer
    if combined_width == 0:
        raise ValueError("Largura combinada das imagens inválida (0).")

    # Criar a nova imagem (canvas) com a largura total e a altura máxima
    combined_img = Image.new('RGBA', (combined_width, max_height), (255, 255, 255, 255)) # Fundo branco

    # Colar as imagens redimensionadas lado a lado
    combined_img.paste(img1_resized, (0, 0))
    combined_img.paste(img2_resized, (new_w1, 0)) # Posição X da segunda imagem é a largura da primeira

    # --- Lógica do Logo (calculada com base nas dimensões combinadas) ---
   
    # Certificar que o logo foi carregado
    if logo_orig is None:
        return combined_img # Retorna a imagem sem logo se não houver logo

    logo = logo_orig.copy() # Trabalhar com cópia

    # Redimensionando o logo com base na largura combinada
    logo_base_width = int(combined_width * logo_size / 100)
    # Mantendo a proporção do logo
    if logo.width > 0:
        logo_ratio = logo.height / logo.width
        logo_final_width = logo_base_width
        logo_final_height = int(logo_final_width * logo_ratio)
    else:
        logo_final_width = 0
        logo_final_height = 0
   
    # Garantir que o logo não seja maior que a imagem combinada (opcional, mas bom)
    logo_final_width = min(logo_final_width, combined_width)
    logo_final_height = min(logo_final_height, max_height)
   
    # Redimensionando o logo com o tamanho calculado e validado
    if logo_final_width > 0 and logo_final_height > 0:
        logo_resized = logo.resize((logo_final_width, logo_final_height), Image.LANCZOS)
    else:
        # Se o logo for inválido ou tamanho calculado for 0, não adiciona o logo
        return combined_img

    # Calculando a posição do logo (canto superior esquerdo)
    # O centro do logo estará em (logo_x%, logo_y%) da imagem combinada
    # Usar combined_width e max_height como referência
    logo_center_x = combined_width * logo_x / 100
    logo_center_y = max_height * logo_y / 100
   
    logo_x_pos = int(logo_center_x - logo_resized.width / 2)
    logo_y_pos = int(logo_center_y - logo_resized.height / 2)

    # Garantir que a posição não saia dos limites da imagem
    logo_x_pos = max(0, min(logo_x_pos, combined_width - logo_resized.width))
    logo_y_pos = max(0, min(logo_y_pos, max_height - logo_resized.height))

    # Convertendo para RGBA se não estiver neste formato
    if logo_resized.mode != 'RGBA':
        logo_resized = logo_resized.convert('RGBA')
   
    # Ajustando a opacidade do logo
    alpha = logo_resized.split()[3] # Pega o canal alfa existente
    alpha = alpha.point(lambda p: p * (logo_opacity / 100.0)) # Aplica a opacidade
   
    # Convertendo a imagem combinada para RGBA para garantir compatibilidade
    if combined_img.mode != 'RGBA':
        combined_img = combined_img.convert('RGBA')

    # Colando o logo na posição escolhida usando o canal alfa como máscara
    # Certifique-se que a imagem base (combined_img) está em RGBA
    combined_img.paste(logo_resized, (logo_x_pos, logo_y_pos), alpha)
   
    return combined_img

# Função process_videos_with_logo permanece a mesma da resposta anterior
# (Já coloca os vídeos lado a lado redimensionando pela menor altura)
# ... (código da função process_videos_with_logo omitido por brevidade, use o da resposta anterior) ...
def process_videos_with_logo(video_file1, video_file2, logo_file, logo_x, logo_y, logo_size, logo_opacity):
    # Salvar os arquivos temporariamente
    temp_dir = tempfile.mkdtemp()
    temp_output = os.path.join(temp_dir, "output.mp4")
    temp_video1 = os.path.join(temp_dir, "video1.mp4")
    temp_video2 = os.path.join(temp_dir, "video2.mp4")
    temp_logo = os.path.join(temp_dir, "logo.png")
   
    video1 = video2 = video1_resized = video2_resized = video1_final = video2_final = logo_clip = final_clip = None # Inicializa para o finally

    try:
        with open(temp_video1, "wb") as f:
            f.write(video_file1.read())
       
        with open(temp_video2, "wb") as f:
            f.write(video_file2.read())
       
        # Salvar logo como imagem
        logo_img = Image.open(logo_file)
        # Garante que o logo salvo tenha transparência se o original tiver
        logo_img.save(temp_logo, format="PNG")
       
        # Carregar os vídeos com moviepy
        video1 = VideoFileClip(temp_video1)
        video2 = VideoFileClip(temp_video2)
       
        # Determinar altura comum (usar a menor)
        height = min(video1.h, video2.h)
       
        # Redimensionar os vídeos para terem a mesma altura
        # Usar interpolação bilinear ou lanczos pode melhorar a qualidade
        video1_resized = video1.resize(height=height)
        video2_resized = video2.resize(height=height)
       
        # Determinar a duração (usar a menor)
        duration = min(video1.duration, video2.duration)
       
        # Cortar os vídeos para terem a mesma duração
        video1_final = video1_resized.subclip(0, duration)
        video2_final = video2_resized.subclip(0, duration)
       
        # Colocar o segundo vídeo ao lado do primeiro
        # A posição é relativa ao canto superior esquerdo do vídeo base (video1_final)
        video2_final = video2_final.set_position((video1_final.w, 0))
       
        # Carregar o logo (certifique-se que ele tenha transparência para moviepy)
        # ismask=True ajuda a preservar a transparência do PNG
        logo_clip = ImageClip(temp_logo, ismask=False, transparent=True).set_duration(duration)
       
        # Calcular dimensões finais do vídeo combinado
        combined_width = video1_final.w + video2_final.w
       
        # Redimensionar o logo (com base na largura combinada)
        logo_width = int(combined_width * logo_size / 100)
        # Manter proporção
        if logo_clip.w > 0: # Evitar divisão por zero
             logo_clip = logo_clip.resize(width=logo_width)
        else:
             # Lidar com logo de largura zero se necessário
             logo_clip = logo_clip.resize(width=1) # Ou algum valor padrão/erro

        # Ajustar opacidade
        logo_clip = logo_clip.set_opacity(logo_opacity / 100.0)
       
        # Calcular posição do logo (centro do logo em x%, y%)
        logo_x_pos = int(combined_width * logo_x / 100 - logo_clip.w / 2)
        logo_y_pos = int(height * logo_y / 100 - logo_clip.h / 2)

        # Garantir que a posição não saia dos limites
        logo_x_pos = max(0, min(logo_x_pos, combined_width - logo_clip.w))
        logo_y_pos = max(0, min(logo_y_pos, height - logo_clip.h))

        logo_clip = logo_clip.set_position((logo_x_pos, logo_y_pos))
       
        # Combinar tudo
        # O tamanho final precisa ser especificado para o CompositeVideoClip
        final_clip = CompositeVideoClip([video1_final, video2_final, logo_clip], size=(combined_width, height))
       
        # Renderizar o vídeo final
        # Preset 'ultrafast' ou 'superfast' pode acelerar, 'medium' é padrão
        # thread=N pode usar mais núcleos da CPU
        final_clip.write_videofile(temp_output, codec="libx264", audio_codec="aac", preset="medium", threads=4)
       
        # Ler o arquivo de saída
        with open(temp_output, "rb") as f:
            output_bytes = f.read()
           
    finally:
        # Fechar clipes para liberar memória e arquivos
        if video1: video1.close()
        if video2: video2.close()
        if video1_resized: video1_resized.close()
        if video2_resized: video2_resized.close()
        if video1_final: video1_final.close()
        if video2_final: video2_final.close()
        if logo_clip: logo_clip.close()
        if final_clip: final_clip.close()

        # Limpar arquivos temporários
        for file in [temp_video1, temp_video2, temp_logo, temp_output]:
            if os.path.exists(file):
                try:
                    os.remove(file)
                except Exception as e:
                    st.warning(f"Não foi possível remover o arquivo temporário {file}: {e}")
        if os.path.exists(temp_dir):
            try:
                os.rmdir(temp_dir)
            except Exception as e:
                st.warning(f"Não foi possível remover o diretório temporário {temp_dir}: {e}")

    return output_bytes

# --- Interface Streamlit ---
# (O restante do código da interface Streamlit permanece o mesmo da resposta anterior)
# ... (código da interface omitido por brevidade) ...

st.header("Selecione o tipo de mídia")
media_type = st.radio("Tipo de mídia", ["Imagens", "Vídeos"])

if media_type == "Imagens":
    col1, col2 = st.columns(2)

    with col1:
        st.header("Imagem 1")
        uploaded_img1 = st.file_uploader("Carregar primeira imagem", type=["jpg", "jpeg", "png"], key="img1")
        if uploaded_img1:
            img1_preview = Image.open(uploaded_img1)
            st.image(img1_preview, caption="Imagem 1 Original", use_column_width=True)
       
    with col2:
        st.header("Imagem 2")
        uploaded_img2 = st.file_uploader("Carregar segunda imagem", type=["jpg", "jpeg", "png"], key="img2")
        if uploaded_img2:
            img2_preview = Image.open(uploaded_img2)
            st.image(img2_preview, caption="Imagem 2 Original", use_column_width=True)
   
    # Controles de zoom para imagem 1
    st.header("Zoom e Foco - Imagem 1")
    zoom_img1 = st.slider("Zoom Imagem 1", 1.0, 5.0, 1.0, 0.1, key="zoom_img1", help="Valores maiores que 1.0 aplicam zoom.")
   
    col_zoom_x1, col_zoom_y1 = st.columns(2)
    with col_zoom_x1:
        zoom_point_x1 = st.slider("Ponto focal X (%)", 0, 100, 50, key="zoom_point_x1", help="Centro horizontal do zoom (0=esquerda, 100=direita).")
    with col_zoom_y1:
        zoom_point_y1 = st.slider("Ponto focal Y (%)", 0, 100, 50, key="zoom_point_y1", help="Centro vertical do zoom (0=topo, 100=base).")
   
    # Controles de zoom para imagem 2
    st.header("Zoom e Foco - Imagem 2")
    zoom_img2 = st.slider("Zoom Imagem 2", 1.0, 5.0, 1.0, 0.1, key="zoom_img2", help="Valores maiores que 1.0 aplicam zoom.")
   
    col_zoom_x2, col_zoom_y2 = st.columns(2)
    with col_zoom_x2:
        zoom_point_x2 = st.slider("Ponto focal X (%)", 0, 100, 50, key="zoom_point_x2", help="Centro horizontal do zoom (0=esquerda, 100=direita).")
    with col_zoom_y2:
        zoom_point_y2 = st.slider("Ponto focal Y (%)", 0, 100, 50, key="zoom_point_y2", help="Centro vertical do zoom (0=topo, 100=base).")
   
    st.header("Logo")
    uploaded_logo = st.file_uploader("Carregar logo (preferencialmente PNG com transparência)", type=["png", "jpg", "jpeg"], key="logo_img")
    logo_obj = None # Define fora do if para garantir que existe
    if uploaded_logo:
        try:
            logo_obj = Image.open(uploaded_logo)
            st.image(logo_obj, caption="Preview do Logo", use_column_width=False, width=200)
        except Exception as e:
            st.error(f"Erro ao carregar preview do logo: {e}")
            uploaded_logo = None # Reseta se der erro
            logo_obj = None
   
    # Controles para posicionamento do logo
    st.header("Ajustes do Logo")
    col_x, col_y = st.columns(2)
    with col_x:
        logo_x = st.slider("Posição Horizontal (%)", 0, 100, 50, key="logo_x_img", help="Define o centro horizontal do logo (0=esquerda, 100=direita).")
    with col_y:
        logo_y = st.slider("Posição Vertical (%)", 0, 100, 50, key="logo_y_img", help="Define o centro vertical do logo (0=topo, 100=base).")

    col_size, col_opacity = st.columns(2)
    with col_size:
        logo_size = st.slider("Tamanho do Logo (% da largura total)", 1, 100, 15, key="logo_size_img", help="Tamanho do logo relativo à largura da imagem combinada.")
    with col_opacity:
        logo_opacity = st.slider("Opacidade do Logo (%)", 0, 100, 80, key="logo_opacity_img", help="Transparência do logo (0=invisível, 100=opaco).")
   
    # Processamento das imagens
    if uploaded_img1 is not None and uploaded_img2 is not None:
        # O logo é opcional, mas se fornecido, deve ser válido
        if uploaded_logo is None or logo_obj is not None:
            try:
                img1_data = Image.open(uploaded_img1)
                img2_data = Image.open(uploaded_img2)
               
                # Passa logo_obj que é None se o upload falhou ou não foi feito
                result = combine_images_with_logo(
                    img1_data, img2_data, logo_obj,
                    logo_x, logo_y, logo_size, logo_opacity,
                    zoom_img1, zoom_img2,
                    zoom_point_x1, zoom_point_y1,
                    zoom_point_x2, zoom_point_y2
                )
               
                if result: # Verifica se a função retornou uma imagem válida
                    st.header("Resultado")
                    st.image(result, caption="Imagens combinadas com logo")
                   
                    # Botão para download
                    buf = io.BytesIO()
                    result.save(buf, format="PNG")
                    byte_im = buf.getvalue()
                   
                    st.download_button(
                        label="Baixar imagem combinada (PNG)",
                        data=byte_im,
                        file_name="imagens_combinadas.png",
                        mime="image/png"
                    )
                else:
                     # A função pode retornar None se houve erro interno, como dimensões inválidas
                     st.error("Não foi possível gerar a imagem combinada devido a um erro interno.")

            except ValueError as ve:
                 st.error(f"Erro de Valor: {ve}")
            except Exception as e:
                st.error(f"Ocorreu um erro inesperado ao processar as imagens: {e}")
                st.exception(e)
        # Se o logo foi carregado mas deu erro (logo_obj é None), informa o usuário
        elif uploaded_logo is not None and logo_obj is None:
             st.warning("O arquivo de logo foi enviado, mas houve um erro ao carregá-lo. Tente outro arquivo.")

    elif uploaded_img1 is None or uploaded_img2 is None:
        st.info("Por favor, faça o upload das duas imagens para continuar.")

# --- Modo Vídeo ---
else:  # Vídeos
    col1, col2 = st.columns(2)

    with col1:
        st.header("Vídeo 1")
        uploaded_video1 = st.file_uploader("Carregar primeiro vídeo", type=["mp4", "mov", "avi", "mkv"], key="vid1") # Adicionado mkv
        if uploaded_video1:
            st.video(uploaded_video1)
       
    with col2:
        st.header("Vídeo 2")
        uploaded_video2 = st.file_uploader("Carregar segundo vídeo", type=["mp4", "mov", "avi", "mkv"], key="vid2") # Adicionado mkv
        if uploaded_video2:
            st.video(uploaded_video2)
   
    st.header("Logo")
    uploaded_logo_video = st.file_uploader("Carregar logo (preferencialmente PNG com transparência)", type=["png", "jpg", "jpeg"], key="logo_vid")
    if uploaded_logo_video:
        try:
            logo_vid_preview = Image.open(uploaded_logo_video)
            st.image(logo_vid_preview, caption="Preview do Logo", use_column_width=False, width=200)
        except Exception as e:
            st.error(f"Erro ao carregar preview do logo: {e}")
            uploaded_logo_video = None # Reseta se der erro

    # Controles para posicionamento do logo
    st.header("Ajustes do Logo no Vídeo")
    col_x_vid, col_y_vid = st.columns(2)
    with col_x_vid:
        logo_x_video = st.slider("Posição Horizontal (%)", 0, 100, 50, key="logo_x_vid", help="Define o centro horizontal do logo (0=esquerda, 100=direita).")
    with col_y_vid:
        logo_y_video = st.slider("Posição Vertical (%)", 0, 100, 50, key="logo_y_vid", help="Define o centro vertical do logo (0=topo, 100=base).")

    col_size_vid, col_opacity_vid = st.columns(2)
    with col_size_vid:
        logo_size_video = st.slider("Tamanho do Logo (% da largura total)", 1, 100, 15, key="logo_size_vid", help="Tamanho do logo relativo à largura do vídeo combinado.")
    with col_opacity_vid:
        logo_opacity_video = st.slider("Opacidade do Logo (%)", 0, 100, 80, key="logo_opacity_vid", help="Transparência do logo (0=invisível, 100=opaco).")
   
    # Processamento dos vídeos
    if uploaded_video1 is not None and uploaded_video2 is not None and uploaded_logo_video is not None:
        if st.button("Processar Vídeos", key="process_vid_button"):
            with st.spinner("Processando vídeos, isso pode levar alguns minutos..."):
                try:
                    # Processar os vídeos
                    result_bytes = process_videos_with_logo(
                        uploaded_video1,
                        uploaded_video2,
                        uploaded_logo_video,
                        logo_x_video,
                        logo_y_video,
                        logo_size_video,
                        logo_opacity_video
                    )
                   
                    # Exibir o resultado
                    st.header("Vídeo Resultante")
                    st.video(result_bytes, format='video/mp4') # Especificar o formato
                   
                    # Botão de download
                    st.download_button(
                        label="Baixar vídeo combinado (MP4)",
                        data=result_bytes,
                        file_name="videos_combinados.mp4",
                        mime="video/mp4"
                    )
                    st.success("Processamento de vídeo concluído!")
                except Exception as e:
                    st.error(f"Erro ao processar os vídeos: {str(e)}")
                    st.exception(e) # Mostra o traceback para depuração
        else:
            st.info("Clique em 'Processar Vídeos' para iniciar a combinação.")
    # Informa se falta algum arquivo essencial
    elif uploaded_video1 is None or uploaded_video2 is None:
         st.info("Por favor, faça o upload dos dois vídeos para processar.")
    elif uploaded_logo_video is None:
         st.info("Por favor, faça o upload do logo para processar.")


# Informações de ajuda (sem alterações da última versão)
with st.expander("Como usar este aplicativo"):
    st.write("""
    ### Modo Imagens
    1. Selecione o tipo de mídia "Imagens".
    2. Carregue as duas imagens que você deseja combinar. Elas ficarão lado a lado.
    3. **Importante:** As imagens serão redimensionadas para terem a mesma altura (a da imagem mais alta), preservando suas proporções originais. Imagens verticais continuarão verticais.
    4. Use os controles de zoom e ponto focal para ajustar cada imagem, se necessário.
    5. Carregue um logo (opcional, preferencialmente PNG com fundo transparente).
    6. Se carregou um logo, ajuste sua posição, tamanho e opacidade.
    7. A imagem combinada será exibida automaticamente.
    8. Clique em "Baixar imagem combinada (PNG)" para salvar o resultado.
   
    ### Modo Vídeos
    1. Selecione o tipo de mídia "Vídeos".
    2. Carregue os dois vídeos que você deseja combinar lado a lado.
    3. Carregue um logo (preferencialmente PNG com fundo transparente).
    4. Use os controles deslizantes para ajustar a posição, tamanho e opacidade do logo.
    5. Clique no botão **"Processar Vídeos"** e aguarde.
    6. Visualize o vídeo resultante e clique em "Baixar vídeo combinado (MP4)" para salvar.
   
    ### Dicas
    - Para melhores resultados com logos, use arquivos PNG com fundo transparente.
    - O processamento de vídeo pode consumir bastante memória e CPU.
    - No modo Imagens, a altura final é ditada pela imagem mais alta. A largura será a soma das larguras proporcionais.
    - No modo Vídeos, a altura final é ditada pelo vídeo mais baixo e a duração pelo vídeo mais curto.
    """)
