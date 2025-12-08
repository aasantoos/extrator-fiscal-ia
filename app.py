import streamlit as st
import os
import pandas as pd
import json
import time
from crewai import Agent, Task, Crew, Process
from PyPDF2 import PdfReader

# --- 1. CONFIGURAÇÕES E SEGURANÇA ---
st.set_page_config(page_title="Agente Fiscal Universal", page_icon="🤖", layout="wide")

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
        role='Auditor Fiscal Senior',
        goal='Extrair TODOS os dados possíveis de notas fiscais (Produtos ou Serviços).',
        backstory='Você é um especialista que analisa tanto DANFE (Produtos) quanto NFS-e (Serviços). Você não deixa passar nenhum detalhe: CNPJs, impostos retidos ou descrições de itens.',
        verbose=False,
        allow_delegation=False,
        llm=MODELO_LLM
    )
    
    auditor = Agent(
        role='Engenheiro de Dados',
        goal='Padronizar os dados em JSON plano.',
        backstory='Você recebe dados brutos e padroniza em um JSON. Se um campo não existir na nota (ex: ICMS ST em nota de serviço), você deixa como null ou 0.',
        verbose=False,
        allow_delegation=False,
        llm=MODELO_LLM
    )
    return extrator, auditor

# --- 3. INTERFACE ---
st.title("🤖 Extrator Fiscal Universal (Produtos & Serviços)")
st.markdown("### Processa qualquer tipo de nota e extrai o máximo de dados.")

with st.sidebar:
    st.header("Painel de Controle")
    st.info(f"Modelo Ativo: {MODELO_LLM}")
    st.write("Dica: O CSV final terá colunas para todos os tipos de nota.")

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
            status_text.text(f"Auditando nota {i+1} de {len(arquivos_upload)}: {arquivo.name}...")
            
            texto_nota = ler_pdf(arquivo)
            
            extrator, auditor = criar_agentes()
            
            # --- TAREFA 1: Extração Completa (O "Super Prompt") ---
            task_extract = Task(
                description=f"""
                Analise o texto da Nota Fiscal abaixo. Pode ser de PRODUTO (Danfe) ou SERVIÇO (NFS-e).
                
                TEXTO DA NOTA:
                ---
                {texto_nota}
                ---
                
                Extraia TODOS os campos abaixo (se encontrar):
                
                1. DADOS CADASTRAIS:
                   - Nome do Emissor (Prestador) e CNPJ do Emissor
                   - Nome do Tomador (Cliente) e CNPJ/CPF do Tomador
                   - Número da Nota
                   - Data de Emissão
                
                2. VALORES FINANCEIROS:
                   - Valor Total da Nota (Bruto)
                   - Valor Líquido (A pagar)
                   - Valor do Serviço (se houver)
                
                3. IMPOSTOS E RETENÇÕES:
                   - Retenção de ISSQN
                   - Valor do ICMS ST
                   - Valor Total de Tributos (Aproximado)
                
                4. DETALHES DO ITEM/SERVIÇO:
                   - Descrição do item principal ou serviço realizado
                   - Código NCM (para produtos) OU Código do Serviço (para serviços)
                """,
                expected_output="Lista completa de dados encontrados.",
                agent=extrator
            )
            
            # --- TAREFA 2: JSON Unificado ---
            task_json = Task(
                description="""
                Formate a saída APENAS como um JSON válido. Use chaves padronizadas (use null ou 0.0 se não encontrar):
                
                {
                    "numero_nota": "string",
                    "data_emissao": "string",
                    "emissor_nome": "string",
                    "emissor_cnpj": "string",
                    "tomador_nome": "string",
                    "tomador_cnpj": "string",
                    "descricao_item_servico": "string",
                    "codigo_ncm_servico": "string",
                    "valor_bruto": float,
                    "valor_liquido": float,
                    "retencao_issqn": float,
                    "icms_st": float,
                    "total_tributos": float
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
        
        # --- EXPORTAÇÃO PARA EXCEL ---
        if resultados_finais:
            df = pd.DataFrame(resultados_finais)
            
            # Ordem lógica das colunas para facilitar a leitura do contador
            colunas_logicas = [
                'arquivo_origem', 
                'numero_nota', 
                'data_emissao',
                'emissor_nome', 'emissor_cnpj',
                'tomador_nome', 'tomador_cnpj',
                'valor_bruto', 'valor_liquido',
                'retencao_issqn', 'icms_st', 'total_tributos',
                'descricao_item_servico', 'codigo_ncm_servico'
            ]
            
            # Filtra para não dar erro se a IA inventar uma chave nova, 
            # mas garante que as nossas chaves estejam na ordem certa.
            cols_existentes = [c for c in colunas_logicas if c in df.columns]
            df = df[cols_existentes]

            st.dataframe(df)

            csv = df.to_csv(index=False).encode('utf-8')
            
            st.download_button(
                label="📥 Baixar Planilha Universal (CSV)",
                data=csv,
                file_name="relatorio_fiscal_universal.csv",
                mime="text/csv",
                type="primary"
            )
