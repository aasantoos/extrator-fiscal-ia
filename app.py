import streamlit as st
import os
import pandas as pd
import json
import time
from crewai import Agent, Task, Crew, Process
from PyPDF2 import PdfReader

# --- 1. CONFIGURAÇÕES E SEGURANÇA ---
st.set_page_config(page_title="Agente Fiscal Pro", page_icon="🤖", layout="wide")

# Lógica de Segurança para API KEY
# 1. Tenta pegar dos Segredos do Streamlit (Quando estiver na Nuvem)
if "OPENAI_API_KEY" in st.secrets:
    os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]
# 2. Se não achar (estiver rodando local), usa a chave abaixo
# ATENÇÃO: Se for subir este arquivo no GitHub, APAGUE SUA CHAVE DAQUI antes.
else:
    os.environ["OPENAI_API_KEY"] = "SUA_CHAVE_AQUI"

MODELO_LLM = "gpt-4o-mini"

# --- 2. FUNÇÕES ---
def ler_pdf(uploaded_file):
    """Lê o arquivo PDF e retorna o texto."""
    try:
        pdf_reader = PdfReader(uploaded_file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text()
        return text
    except Exception as e:
        return f"Erro ao ler PDF: {e}"

def criar_agentes():
    """Cria os agentes. Definimos aqui para recriar a cada execução e não misturar contextos."""
    extrator = Agent(
        role='Analista Fiscal',
        goal='Extrair dados chave de notas fiscais.',
        backstory='Especialista em identificar CNPJ, Datas e Valores em documentos financeiros.',
        verbose=False,
        allow_delegation=False,
        llm=MODELO_LLM
    )
    
    auditor = Agent(
        role='Engenheiro de Dados',
        goal='Padronizar os dados em JSON.',
        backstory='Você garante que a saída seja apenas um JSON válido, sem texto adicional.',
        verbose=False,
        allow_delegation=False,
        llm=MODELO_LLM
    )
    return extrator, auditor

# --- 3. INTERFACE ---
st.title("🤖 Extrator de Notas Fiscais em Lote")
st.markdown("### Arraste múltiplos arquivos e gere um relatório único.")

with st.sidebar:
    st.header("Painel de Controle")
    st.info(f"Modelo Ativo: {MODELO_LLM}")
    st.write("Dica: Arraste 3 ou 4 notas de uma vez para testar.")

# Upload que aceita múltiplos arquivos
arquivos_upload = st.file_uploader(
    "Solte seus arquivos PDF aqui (pode selecionar vários)", 
    type="pdf", 
    accept_multiple_files=True
)

# --- 4. LÓGICA DE PROCESSAMENTO EM LOTE ---
if arquivos_upload:
    st.write(f"📂 **{len(arquivos_upload)} arquivos identificados.**")
    
    if st.button("🚀 Processar Tudo", type="primary"):
        
        resultados_finais = []
        barra_progresso = st.progress(0)
        status_text = st.empty()
        
        # Início do Loop
        for i, arquivo in enumerate(arquivos_upload):
            # Atualiza barra de progresso
            porcentagem = (i + 1) / len(arquivos_upload)
            barra_progresso.progress(porcentagem)
            status_text.text(f"Processando arquivo {i+1} de {len(arquivos_upload)}: {arquivo.name}...")
            
            # 1. Ler o PDF atual
            texto_nota = ler_pdf(arquivo)
            
            # 2. Configurar Agentes e Tarefas para ESTE arquivo
            extrator, auditor = criar_agentes()
            
            task_extract = Task(
                description=f"Extraia dados desta nota fiscal:\n\n{texto_nota}\n\nCampos: Emissor, CNPJ, Data, Valor Total, NCM do primeiro item, ICMS ST.",
                expected_output="Lista de dados.",
                agent=extrator
            )
            
            task_json = Task(
                description="Formate a extração anterior apenas como JSON: {emissor, cnpj, data, valor_total, ncm, icms_st}",
                expected_output="JSON válido.",
                agent=auditor
            )
            
            crew = Crew(
                agents=[extrator, auditor],
                tasks=[task_extract, task_json],
                process=Process.sequential
            )
            
            # 3. Rodar a IA
            try:
                resultado = crew.kickoff()
                
                # Limpeza básica do JSON
                json_str = str(resultado).replace("```json", "").replace("```", "").strip()
                dados = json.loads(json_str)
                
                # Adicionar o nome do arquivo para saber de qual nota veio
                dados['arquivo_origem'] = arquivo.name
                
                # Salvar na lista geral
                resultados_finais.append(dados)
                
            except Exception as e:
                st.error(f"Erro ao processar {arquivo.name}: {e}")
        
        # Fim do Loop
        barra_progresso.empty()
        status_text.success("✅ Processamento concluído!")
        
        # --- 5. EXIBIÇÃO E DOWNLOAD ---
        if resultados_finais:
            df = pd.DataFrame(resultados_finais)
            
            # Reordenar colunas
            colunas_preferidas = ['arquivo_origem', 'emissor', 'cnpj', 'data', 'valor_total', 'icms_st', 'ncm']
            colunas_finais = [c for c in colunas_preferidas if c in df.columns]
            df = df[colunas_finais]

            st.dataframe(df)

            csv = df.to_csv(index=False).encode('utf-8')
            
            st.download_button(
                label="📥 Baixar Planilha Consolidada (CSV)",
                data=csv,
                file_name="relatorio_fiscal_consolidado.csv",
                mime="text/csv",
                type="primary"
            )