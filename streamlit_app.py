import streamlit as st
import pandas as pd
import io
import base64
from PIL import Image
import tempfile
import os

# Tente importar as bibliotecas específicas para processamento de PDF
try:
    from pdf2image import convert_from_bytes
    import google.generativeai as genai
    PDF_PROCESSING_AVAILABLE = True
except ImportError:
    PDF_PROCESSING_AVAILABLE = False
    st.warning("Algumas bibliotecas não foram instaladas corretamente. O processamento de PDF pode estar indisponível.")

# Configuração da página
st.set_page_config(page_title="Extrator de Boletos", page_icon="📄", layout="wide")

# Título do aplicativo
st.title("Extrator de Dados de Boletos")

# Sidebar para configurações
with st.sidebar:
    st.header("Configurações")
    api_key = st.text_input("API Key do Google Gemini", type="password", help="Obtenha sua chave em https://makersuite.google.com/app/apikey")
    
    st.header("Opções")
    option = st.radio("Escolha o método de entrada:", ["Upload de PDF", "Linha Digitável/Código de Barras"])

# Funções do seu código do Colab (adaptadas para Streamlit)
def converter_pdf_para_imagens(pdf_bytes):
    try:
        imagens = convert_from_bytes(
            pdf_bytes,
            dpi=300,
            fmt='png'
        )
        return imagens
    except Exception as e:
        st.error(f"Erro ao converter PDF para imagens: {e}")
        return []

def imagem_para_base64(imagem):
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode('utf-8')

def extrair_dados_com_gemini(imagem, api_key):
    if not api_key:
        st.error("Por favor, forneça uma API key do Gemini")
        return None
    
    try:
        # Configurar o Gemini
        genai.configure(api_key=api_key)
        
        # Criar modelo
        generation_config = {
            "temperature": 0,
            "top_p": 0.95,
            "top_k": 64,
        }
        
        model = genai.GenerativeModel(
            model_name="gemini-1.5-pro-latest",
            generation_config=generation_config
        )
        
        # Preparar a imagem
        img_data = imagem_para_base64(imagem)
        img_parts = [{"mime_type": "image/png", "data": img_data}]
        
        # Criar o prompt para o Gemini
        prompt = """
        Você é um assistente especializado em extrair informações de boletos de aluguel e condomínio.
        Extraia todos os itens de cobrança deste boleto e seus respectivos valores.
        
        Exemplos de itens comuns: Aluguel, Aluguel Mínimo, Condomínio, Fundo de Promoção, 
        IPTU, Ar Condicionado, Energia, Água, etc.
        
        Responda APENAS no formato JSON abaixo, sem texto adicional:
        {
          "empreendimento": "nome do shopping/edifício",
          "loja": "número ou identificação da loja/unidade",
          "data_vencimento": "data de vencimento",
          "valor_total": valor numérico,
          "itens": [
            {"item": "nome do item 1", "valor": valor numérico},
            {"item": "nome do item 2", "valor": valor numérico},
            ...
          ]
        }
        
        IMPORTANTE: Inclua TODOS os itens e valores encontrados.
        """
        
        # Informar o usuário
        with st.spinner("Processando imagem com IA..."):
            # Enviar para o Gemini
            response = model.generate_content([prompt] + img_parts)
            resposta = response.text
            
            # Extrair o JSON da resposta
            import json
            inicio = resposta.find('{')
            fim = resposta.rfind('}') + 1
            
            if inicio >= 0 and fim > inicio:
                json_text = resposta[inicio:fim]
                return json.loads(json_text)
            else:
                st.error("Não foi possível encontrar dados estruturados na resposta")
                return None
                
    except Exception as e:
        st.error(f"Erro ao processar com Gemini: {e}")
        return None

# Interface principal baseada na opção selecionada
if option == "Upload de PDF":
    st.header("Upload de PDF de Boletos")
    
    uploaded_files = st.file_uploader("Escolha arquivos PDF", accept_multiple_files=True, type="pdf")
    
    if uploaded_files and api_key:
        if st.button("Processar Boletos"):
            # Lista para armazenar resultados
            todos_dados = []
            todos_itens = []
            
            progress_bar = st.progress(0)
            
            for i, uploaded_file in enumerate(uploaded_files):
                st.subheader(f"Processando: {uploaded_file.name}")
                
                # Ler bytes do arquivo
                pdf_bytes = uploaded_file.getvalue()
                
                # Converter PDF para imagens
                imagens = converter_pdf_para_imagens(pdf_bytes)
                
                if not imagens:
                    st.warning(f"Não foi possível converter {uploaded_file.name} em imagens.")
                    continue
                
                st.info(f"PDF convertido em {len(imagens)} páginas.")
                
                # Processar cada página
                for j, imagem in enumerate(imagens):
                    st.text(f"Processando página {j+1}...")
                    
                    # Mostrar thumbnail da imagem
                    st.image(imagem, width=200, caption=f"Página {j+1}")
                    
                    # Extrair dados
                    dados = extrair_dados_com_gemini(imagem, api_key)
                    
                    if dados:
                        # Adicionar informação da origem
                        dados['arquivo'] = uploaded_file.name
                        dados['pagina'] = j + 1
                        
                        # Adicionar aos resultados
                        todos_dados.append(dados)
                        
                        # Adicionar itens individuais
                        if 'itens' in dados:
                            for item in dados['itens']:
                                item_completo = {
                                    'arquivo': uploaded_file.name,
                                    'pagina': j + 1,
                                    'empreendimento': dados.get('empreendimento', 'Não identificado'),
                                    'loja': dados.get('loja', 'Não identificado'),
                                    'data_vencimento': dados.get('data_vencimento', 'Não identificado'),
                                    'item': item.get('item', 'Não identificado'),
                                    'valor': item.get('valor', 0)
                                }
                                todos_itens.append(item_completo)
                        
                        # Exibir resultados desta página
                        st.success(f"Dados extraídos com sucesso da página {j+1}")
                        st.json(dados)
                    else:
                        st.error(f"Não foi possível extrair dados da página {j+1}")
                
                # Atualizar barra de progresso
                progress_bar.progress((i + 1) / len(uploaded_files))
            
            # Exibir resultados consolidados
            if todos_dados:
                st.header("Resultados Consolidados")
                
                # Criar dataframes
                df_resumo = pd.DataFrame([
                    {
                        'Arquivo': d['arquivo'],
                        'Página': d['pagina'],
                        'Empreendimento': d.get('empreendimento', 'Não identificado'),
                        'Loja/Unidade': d.get('loja', 'Não identificado'),
                        'Data Vencimento': d.get('data_vencimento', 'Não identificado'),
                        'Valor Total': d.get('valor_total', 0),
                        'Quantidade de Itens': len(d.get('itens', []))
                    }
                    for d in todos_dados
                ])
                
                df_itens = pd.DataFrame(todos_itens)
                
                # Mostrar tabelas
                st.subheader("Resumo de Boletos")
                st.dataframe(df_resumo)
                
                st.subheader("Itens Detalhados")
                st.dataframe(df_itens)
                
                # Exportar para Excel
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df_resumo.to_excel(writer, sheet_name='Resumo', index=False)
                    df_itens.to_excel(writer, sheet_name='Itens_Detalhados', index=False)
                
                buffer.seek(0)
                
                st.download_button(
                    label="Baixar Excel",
                    data=buffer,
                    file_name="boletos_gemini.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.warning("Nenhum dado foi extraído dos PDFs.")
                
else:  # Linha Digitável/Código de Barras
    st.header("Entrada Manual de Boletos")
    
    # Interface para entrada manual
    input_type = st.radio("Tipo de entrada:", ["Linha Digitável", "Código de Barras"])
    
    if input_type == "Linha Digitável":
        linha_digitavel = st.text_input("Digite a linha digitável do boleto:")
        if st.button("Processar Linha Digitável") and linha_digitavel:
            st.info("Esta funcionalidade será implementada em breve")
            # Aqui você conectaria com a API do Replit
    else:
        codigo_barras = st.text_input("Digite o código de barras do boleto:")
        if st.button("Processar Código de Barras") and codigo_barras:
            st.info("Esta funcionalidade será implementada em breve")
            # Aqui você conectaria com a API do Replit

# Rodapé
st.markdown("---")
st.markdown("Desenvolvido com ❤️ usando Streamlit e Google Gemini")