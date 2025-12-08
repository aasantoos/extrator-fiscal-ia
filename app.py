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
if "OPENAI_API_KEY" in st.secrets:
    os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]
else:
    os.environ["OPENAI_API_KEY"] = "SUA_CHAVE_AQUI" # <--- Se rodar local, coloque sua chave aqui

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
    """Cria os agentes."""
    extrator = Agent(
        role='Analista Fiscal',
        goal='Extrair dados complexos de notas fiscais de serviço (NFS-e).',
        backstory='Especialista em identificar Tomadores, Prestadores, Retenções de Impostos e Códigos Tributários.',
        verbose=False,
        allow_delegation=False,
        llm=MODELO_LLM
    )
    
    auditor = Agent(
        role='Engenheiro de Dados',
        goal='Padronizar os dados em JSON.',
        backstory='Você garante que a saída seja apenas um JSON válido, convertendo valores monetários para float (ponto).',
        verbose=False,
        allow_delegation=False,
        llm=MODELO_LLM
    )
    return extrator, auditor

# --- 3. INTERFACE ---
st.title("🤖 Extrator de Notas Fiscais (NFS-e)")
st.markdown("### Extração detalhada: Tomador, Impostos e Valores Líquidos.")

with st.sidebar:
    st.header("Painel de Controle")
    st.info(f"Modelo Ativo: {MODELO_LLM}")
    st.write("Dica: Funciona melhor com Notas de Serviço (NFS-e).")

arquivos_upload = st.file_uploader(
    "Solte seus arquivos PDF aqui", 
    type="pdf", 
    accept_multiple_files=True
)

# --- 4. LÓGICA DE PROCESSAMENTO ---
if arquivos_upload:
    st.write(f"📂 **{len(arquivos_upload)} arquivos identificados.**")
    
    if st.button("🚀 Processar Tudo", type="primary"):
        
        resultados_finais = []
        barra_progresso = st.progress(0)
        status_text = st.empty()
        
        for i, arquivo in enumerate(arquivos_upload):
            porcentagem = (i + 1) / len(arquivos_upload)
            barra_progresso.progress(porcentagem)
            status_text.text(f"Lendo nota {i+1} de {len(arquivos_upload)}: {arquivo.name}...")
            
            texto_nota = ler_pdf(arquivo)
            
            extrator, auditor = criar_agentes()
            
            # --- ONDE A MÁGICA ACONTECE (ALTERAÇÃO 1: O Pedido) ---
            task_extract = Task(
                description=f"""
                Analise o texto desta Nota Fiscal de Serviço e extraia:
                
                Texto da Nota:
                ---
                {texto_nota}
                ---
                
                CAMPOS OBRIGATÓRIOS PARA EXTRAIR:
                1. Nome do Prestador (Emissor)
                2. Nome do Tomador do Serviço (Cliente)
                3. Número da Nota
                4. Data de Emissão
                5. Código de Tributação Nacional (ou Código do Serviço / CNAE)
                6. Valor do Serviço (Valor Bruto)
                7. Valor Líquido da Nota (Valor a pagar)
                8. Valor da Retenção de ISSQN (Se não houver, zero)
                
                """,
                expected_output="Lista com os dados encontrados.",
                agent=extrator
            )
            
            # --- (ALTERAÇÃO 2: A Estrutura JSON) ---
            task_json = Task(
                description="""
                Formate os dados extraídos APENAS como JSON válido. Use estas chaves exatas:
                {
                    "prestador": "string",
                    "tomador": "string",
                    "numero_nota": "string",
                    "data_emissao": "string",
                    "codigo_tributacao": "string",
                    "valor_servico": float,
                    "valor_liquido": float,
                    "retencao_issqn": float
                }
                """,
                expected_output="JSON válido.",
                agent=auditor
            )
            
            crew = Crew(
                agents=[extrator, auditor],
                tasks=[task_extract, task_json],
                process=Process.sequential
            )
            
            try:
                resultado = crew.kickoff()
                json_str = str(resultado).replace("```json", "").replace("```", "").strip()
                dados = json.loads(json_str)
                dados['arquivo_origem'] = arquivo.name
                resultados_finais.append(dados)
                
            except Exception as e:
                st.error(f"Erro ao processar {arquivo.name}: {e}")
        
        barra_progresso.empty()
        status_text.success("✅ Processamento concluído!")
        
        # --- (ALTERAÇÃO 3: As Colunas do Excel) ---
        if resultados_finais:
            df = pd.DataFrame(resultados_finais)
            
            # Definindo a ordem das colunas no Excel
            colunas_ordenadas = [
                'arquivo_origem', 
                'numero_nota', 
                'data_emissao', 
                'prestador', 
                'tomador', 
                'valor_servico', 
                'valor_liquido', 
                'retencao_issqn', 
                'codigo_tributacao'
            ]
            
            # Filtra apenas colunas que realmente vieram (para evitar erro se faltar alguma)
            cols_finais = [c for c in colunas_ordenadas if c in df.columns]
            df = df[cols_finais]

            st.dataframe(df)

            csv = df.to_csv(index=False).encode('utf-8')
            
            st.download_button(
                label="📥 Baixar Planilha Detalhada (CSV)",
                data=csv,
                file_name="relatorio_fiscal_detalhado.csv",
                mime="text/csv",
                type="primary"
            )
