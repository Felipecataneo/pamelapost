import streamlit as st
from PIL import Image
import io
import numpy as np
import cv2
import tempfile
import os
from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip

st.set_page_config(page_title="Combinador de Mídias", layout="wide")

st.title("Combinador de Imagens e Vídeos com Logo")
st.write("Este aplicativo permite combinar duas imagens ou vídeos lado a lado e adicionar um logo em uma posição personalizada.")

# Função para combinar imagens e adicionar logo
def combine_images_with_logo(img1, img2, logo, logo_x, logo_y, logo_size, logo_opacity):
    # Redimensionando as imagens para a mesma altura
    height = min(img1.height, img2.height)
    img1_resized = img1.resize((int(img1.width * height / img1.height), height))
    img2_resized = img2.resize((int(img2.width * height / img2.height), height))
    
    # Criando uma nova imagem para combiná-las
    combined_width = img1_resized.width + img2_resized.width
    combined_img = Image.new('RGBA', (combined_width, height), (255, 255, 255, 255))
    
    # Colando as imagens lado a lado
    combined_img.paste(img1_resized, (0, 0))
    combined_img.paste(img2_resized, (img1_resized.width, 0))
    
    # Redimensionando o logo
    logo_width = int(combined_width * logo_size / 100)
    logo_height = int(logo.height * logo_width / logo.width)
    logo_resized = logo.resize((logo_width, logo_height))
    
    # Convertendo para RGBA se não estiver neste formato
    if logo_resized.mode != 'RGBA':
        logo_resized = logo_resized.convert('RGBA')
    
    # Ajustando a opacidade do logo
    logo_array = np.array(logo_resized)
    if logo_array.shape[2] == 4:  # Verificando se a imagem tem canal alpha
        logo_array[:, :, 3] = logo_array[:, :, 3] * logo_opacity / 100
        logo_transparent = Image.fromarray(logo_array)
    else:
        # Se a imagem não tem canal alpha, criamos um
        r, g, b = logo_resized.split()
        alpha = Image.new('L', logo_resized.size, int(255 * logo_opacity / 100))
        logo_transparent = Image.merge('RGBA', (r, g, b, alpha))
    
    # Calculando a posição do logo
    logo_x_pos = int(combined_width * logo_x / 100 - logo_width / 2)
    logo_y_pos = int(height * logo_y / 100 - logo_height / 2)
    
    # Verificando se a imagem combinada está em RGBA
    if combined_img.mode != 'RGBA':
        combined_img = combined_img.convert('RGBA')
    
    # Criando uma máscara a partir do canal alpha do logo
    if logo_transparent.mode == 'RGBA':
        logo_mask = logo_transparent.split()[3]
    else:
        logo_mask = None
    
    # Colando o logo na posição escolhida
    combined_img.paste(logo_transparent, (logo_x_pos, logo_y_pos), logo_mask)
    
    return combined_img

# Função para processar vídeo e adicionar logo
def process_videos_with_logo(video_file1, video_file2, logo_file, logo_x, logo_y, logo_size, logo_opacity):
    # Salvar os arquivos temporariamente
    temp_dir = tempfile.mkdtemp()
    temp_output = os.path.join(temp_dir, "output.mp4")
    temp_video1 = os.path.join(temp_dir, "video1.mp4")
    temp_video2 = os.path.join(temp_dir, "video2.mp4")
    temp_logo = os.path.join(temp_dir, "logo.png")
    
    with open(temp_video1, "wb") as f:
        f.write(video_file1.read())
    
    with open(temp_video2, "wb") as f:
        f.write(video_file2.read())
    
    # Salvar logo como imagem
    logo_img = Image.open(logo_file)
    logo_img.save(temp_logo)
    
    # Carregar os vídeos com moviepy
    video1 = VideoFileClip(temp_video1)
    video2 = VideoFileClip(temp_video2)
    
    # Determinar altura comum (usar a menor)
    height = min(video1.h, video2.h)
    
    # Redimensionar os vídeos para terem a mesma altura
    video1_resized = video1.resize(height=height)
    video2_resized = video2.resize(height=height)
    
    # Determinar a duração (usar a menor)
    duration = min(video1.duration, video2.duration)
    
    # Cortar os vídeos para terem a mesma duração
    video1_final = video1_resized.subclip(0, duration)
    video2_final = video2_resized.subclip(0, duration)
    
    # Colocar o segundo vídeo ao lado do primeiro
    video2_final = video2_final.set_position((video1_final.w, 0))
    
    # Carregar o logo
    logo_clip = ImageClip(temp_logo).set_duration(duration)
    
    # Calcular dimensões finais
    combined_width = video1_final.w + video2_final.w
    
    # Redimensionar o logo
    logo_width = int(combined_width * logo_size / 100)
    logo_clip = logo_clip.resize(width=logo_width)
    
    # Ajustar opacidade
    logo_clip = logo_clip.set_opacity(logo_opacity / 100)
    
    # Calcular posição do logo
    logo_x_pos = int(combined_width * logo_x / 100 - logo_clip.w / 2)
    logo_y_pos = int(height * logo_y / 100 - logo_clip.h / 2)
    logo_clip = logo_clip.set_position((logo_x_pos, logo_y_pos))
    
    # Combinar tudo
    final_clip = CompositeVideoClip([video1_final, video2_final, logo_clip], size=(combined_width, height))
    
    # Renderizar o vídeo final
    final_clip.write_videofile(temp_output, codec="libx264", audio_codec="aac")
    
    # Ler o arquivo de saída
    with open(temp_output, "rb") as f:
        output_bytes = f.read()
    
    # Limpar arquivos temporários
    for file in [temp_video1, temp_video2, temp_logo, temp_output]:
        if os.path.exists(file):
            os.remove(file)
    os.rmdir(temp_dir)
    
    return output_bytes

# Interface do Streamlit
st.header("Selecione o tipo de mídia")
media_type = st.radio("Tipo de mídia", ["Imagens", "Vídeos"])

if media_type == "Imagens":
    col1, col2 = st.columns(2)

    with col1:
        st.header("Imagem 1")
        uploaded_img1 = st.file_uploader("Carregar primeira imagem", type=["jpg", "jpeg", "png"], key="img1")
        
    with col2:
        st.header("Imagem 2")
        uploaded_img2 = st.file_uploader("Carregar segunda imagem", type=["jpg", "jpeg", "png"], key="img2")
    
    st.header("Logo")
    uploaded_logo = st.file_uploader("Carregar logo", type=["jpg", "jpeg", "png"], key="logo_img")
    
    # Controles para posicionamento do logo
    st.header("Ajustes do Logo")
    col_x, col_y = st.columns(2)
    with col_x:
        logo_x = st.slider("Posição Horizontal (%)", 0, 100, 50, key="logo_x_img")
    with col_y:
        logo_y = st.slider("Posição Vertical (%)", 0, 100, 50, key="logo_y_img")

    col_size, col_opacity = st.columns(2)
    with col_size:
        logo_size = st.slider("Tamanho do Logo (%)", 5, 50, 15, key="logo_size_img")
    with col_opacity:
        logo_opacity = st.slider("Opacidade do Logo (%)", 0, 100, 80, key="logo_opacity_img")
    
    # Processamento das imagens
    if uploaded_img1 is not None and uploaded_img2 is not None:
        img1 = Image.open(uploaded_img1)
        img2 = Image.open(uploaded_img2)
        
        if uploaded_logo is not None:
            logo = Image.open(uploaded_logo)
            
            # Combinando as imagens com o logo
            result = combine_images_with_logo(img1, img2, logo, logo_x, logo_y, logo_size, logo_opacity)
            
            # Exibindo o resultado
            st.header("Resultado")
            st.image(result, caption="Imagens combinadas com logo")
            
            # Botão para download
            buf = io.BytesIO()
            result.save(buf, format="PNG")
            byte_im = buf.getvalue()
            
            st.download_button(
                label="Baixar imagem combinada",
                data=byte_im,
                file_name="imagens_combinadas.png",
                mime="image/png"
            )
        else:
            st.info("Por favor, faça o upload de um logo para continuar.")
    else:
        st.info("Por favor, faça o upload das duas imagens para continuar.")

else:  # Vídeos
    col1, col2 = st.columns(2)

    with col1:
        st.header("Vídeo 1")
        uploaded_video1 = st.file_uploader("Carregar primeiro vídeo", type=["mp4", "mov", "avi"], key="vid1")
        if uploaded_video1:
            st.video(uploaded_video1)
        
    with col2:
        st.header("Vídeo 2")
        uploaded_video2 = st.file_uploader("Carregar segundo vídeo", type=["mp4", "mov", "avi"], key="vid2")
        if uploaded_video2:
            st.video(uploaded_video2)
    
    st.header("Logo")
    uploaded_logo_video = st.file_uploader("Carregar logo", type=["jpg", "jpeg", "png"], key="logo_vid")
    
    # Controles para posicionamento do logo
    st.header("Ajustes do Logo")
    col_x, col_y = st.columns(2)
    with col_x:
        logo_x_video = st.slider("Posição Horizontal (%)", 0, 100, 50, key="logo_x_vid")
    with col_y:
        logo_y_video = st.slider("Posição Vertical (%)", 0, 100, 50, key="logo_y_vid")

    col_size, col_opacity = st.columns(2)
    with col_size:
        logo_size_video = st.slider("Tamanho do Logo (%)", 5, 50, 15, key="logo_size_vid")
    with col_opacity:
        logo_opacity_video = st.slider("Opacidade do Logo (%)", 0, 100, 80, key="logo_opacity_vid")
    
    # Processamento dos vídeos
    if uploaded_video1 is not None and uploaded_video2 is not None and uploaded_logo_video is not None:
        if st.button("Processar Vídeos"):
            with st.spinner("Processando vídeos, por favor aguarde..."):
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
                    st.video(result_bytes)
                    
                    # Botão de download
                    st.download_button(
                        label="Baixar vídeo combinado",
                        data=result_bytes,
                        file_name="videos_combinados.mp4",
                        mime="video/mp4"
                    )
                except Exception as e:
                    st.error(f"Erro ao processar os vídeos: {str(e)}")
        else:
            st.info("Clique em 'Processar Vídeos' para iniciar a combinação dos vídeos com o logo.")
    else:
        st.info("Por favor, faça o upload dos dois vídeos e do logo para continuar.")

# Informações de ajuda
with st.expander("Como usar este aplicativo"):
    st.write("""
    ### Modo Imagens
    1. Selecione o tipo de mídia "Imagens"
    2. Carregue duas imagens que você deseja combinar lado a lado
    3. Carregue um logo que será sobreposto na imagem final
    4. Use os controles deslizantes para ajustar:
       - A posição horizontal e vertical do logo
       - O tamanho do logo
       - A opacidade do logo
    5. Visualize o resultado e clique em "Baixar imagem combinada"
    
    ### Modo Vídeos
    1. Selecione o tipo de mídia "Vídeos"
    2. Carregue dois vídeos que você deseja combinar lado a lado
    3. Carregue um logo que será sobreposto no vídeo final
    4. Use os controles deslizantes para ajustar:
       - A posição horizontal e vertical do logo
       - O tamanho do logo
       - A opacidade do logo
    5. Clique em "Processar Vídeos" e aguarde o processamento
    6. Visualize o resultado e clique em "Baixar vídeo combinado"
    
    Obs: O aplicativo vai redimensionar automaticamente as mídias para terem a mesma altura e, no caso dos vídeos, a mesma duração.
    """)