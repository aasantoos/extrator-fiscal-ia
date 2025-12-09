import streamlit as st
import os
import pandas as pd
import json
import io
import plotly.express as px
from crewai import Agent, Task, Crew, Process
from PyPDF2 import PdfReader

# --- 1. CONFIGURAÇÕES ---
st.set_page_config(page_title="Agente Fiscal Inteligente", page_icon="⚖️", layout="wide")

if "OPENAI_API_KEY" in st.secrets:
    os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]
else:
    os.environ["OPENAI_API_KEY"] = "SUA_CHAVE_AQUI"

MODELO_LLM = "gpt-4o-mini"

# --- 2. FUNÇÕES ---
def ler_pdf(uploaded_file):
    try:
        pdf_reader = PdfReader(uploaded_file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text()
        return text
    except Exception as e:
        return f"Erro: {e}"

def criar_equipe_extracao():
    """Cria agentes com conhecimento tributário específico."""
    extrator = Agent(
        role='Auditor Tributário Sênior',
        goal='Distinguir entre Nota de Produto (ICMS) e Serviço (ISS) e extrair os impostos corretos.',
        backstory='Você é especialista em legislação fiscal brasileira. Você sabe que DANFE tem ICMS/IPI e NFS-e tem ISSQN.',
        verbose=False, allow_delegation=False, llm=MODELO_LLM
    )
    auditor = Agent(
        role='Engenheiro de Dados',
        goal='Padronizar JSON separando campos de ICMS e ISS.',
        backstory='Garante que números sejam float e campos não encontrados sejam 0.0.',
        verbose=False, allow_delegation=False, llm=MODELO_LLM
    )
    return extrator, auditor

def analisar_dados_com_ia(df_json):
    analista = Agent(
        role='Consultor Fiscal',
        goal='Analisar a natureza das operações (Comércio vs Serviço).',
        backstory='Analisa se a empresa está gastando mais com produtos ou serviços e verifica a carga tributária.',
        verbose=True, allow_delegation=False, llm=MODELO_LLM
    )
    task_analise = Task(
        description=f"Analise estes dados:\n{df_json}\n\nRelatório Executivo: Separe o total gasto em PRODUTOS vs SERVIÇOS. Cite o maior fornecedor de cada categoria.",
        expected_output="Relatório Markdown.",
        agent=analista
    )
    return Crew(agents=[analista], tasks=[task_analise]).kickoff()

# --- 3. INTERFACE ---
st.title("⚖️ Agente Fiscal: ICMS vs ISSQN")
st.markdown("Identifica automaticamente se é **Venda (ICMS)** ou **Serviço (ISSQN)**.")

arquivos_upload = st.file_uploader("Upload de Notas (PDF)", type="pdf", accept_multiple_files=True)

if 'dados_processados' not in st.session_state:
    st.session_state.dados_processados = None

# --- 4. PROCESSAMENTO ---
if arquivos_upload:
    if st.button("🚀 Auditar Impostos", type="primary"):
        resultados = []
        barra = st.progress(0)
        status = st.empty()
        
        with st.expander("Ver logs da Auditoria", expanded=True):
            for i, arquivo in enumerate(arquivos_upload):
                barra.progress((i + 1) / len(arquivos_upload))
                status.write(f"Analisando: {arquivo.name}...")
                
                texto = ler_pdf(arquivo)
                extrator, auditor = criar_equipe_extracao()
                
                # --- AQUI ESTÁ A CORREÇÃO (LÓGICA CONDICIONAL) ---
                task_ex = Task(
                    description=f"""
                    Analise o documento fiscal abaixo:
                    ---
                    {texto}
                    ---
                    
                    PASSO 1: IDENTIFIQUE O TIPO DE NOTA.
                    - É "DANFE" ou Nota de Venda de Mercadoria? -> O foco é ICMS e IPI.
                    - É "NFS-e" ou Nota de Serviço? -> O foco é ISSQN.
                    
                    PASSO 2: EXTRAIA OS DADOS CORRETOS BASEADO NO TIPO.
                    
                    Se for PRODUTO (Venda):
                    - Extraia: Valor do ICMS, Base de Cálculo ICMS, Valor IPI.
                    - (ISSQN deve ser 0).
                    
                    Se for SERVIÇO (NFS-e):
                    - Extraia: Valor do ISSQN, Valor Líquido.
                    - (ICMS deve ser 0).
                    
                    CAMPOS COMUNS PARA EXTRAIR:
                    - Nome Emissor, CNPJ Emissor
                    - Data Emissão, Número Nota
                    - Valor Total da Nota
                    - Descrição Principal
                    """,
                    expected_output="Lista de dados fiscais.", agent=extrator
                )
                
                task_json = Task(
                    description="""
                    Gere um JSON com estas chaves exatas (use 0.0 se não encontrar):
                    {
                        "tipo_nota": "PRODUTO" ou "SERVICO",
                        "numero": "string",
                        "data": "string",
                        "emissor": "string",
                        "cnpj": "string",
                        "valor_total": float,
                        "valor_icms": float,
                        "valor_ipi": float,
                        "valor_issqn": float,
                        "descricao": "string"
                    }
                    """,
                    expected_output="JSON válido.", agent=auditor
                )
                
                crew = Crew(agents=[extrator, auditor], tasks=[task_ex, task_json])
                
                try:
                    res = crew.kickoff()
                    clean_res = str(res).replace("```json", "").replace("```", "").strip()
                    if clean_res.startswith("json"): clean_res = clean_res[4:]
                    
                    dados = json.loads(clean_res)
                    dados['arquivo'] = arquivo.name
                    resultados.append(dados)
                    
                    # Feedback visual na hora
                    if dados.get('valor_icms', 0) > 0:
                        st.info(f"📦 {arquivo.name}: Produto detectado (ICMS: R$ {dados['valor_icms']})")
                    else:
                        st.success(f"🛠️ {arquivo.name}: Serviço detectado (ISS: R$ {dados['valor_issqn']})")
                        
                except Exception as e:
                    st.error(f"Erro em {arquivo.name}: {e}")

        st.session_state.dados_processados = resultados
        status.success("Auditoria Finalizada!")

# --- 5. VISUALIZAÇÃO ---
if st.session_state.dados_processados:
    df = pd.DataFrame(st.session_state.dados_processados)
    
    # Tratamento numérico
    cols = ['valor_total', 'valor_icms', 'valor_ipi', 'valor_issqn']
    for c in cols:
        if c in df.columns: df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)

    tab1, tab2, tab3 = st.tabs(["📥 Relatório Contábil", "📊 Gráficos Fiscais", "🤖 Parecer da IA"])
    
    with tab1:
        st.dataframe(df)
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        buffer.seek(0)
        st.download_button("Baixar Excel (.xlsx)", buffer, "relatorio_fiscal.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")

    with tab2:
        col1, col2, col3 = st.columns(3)
        col1.metric("Total ICMS (Mercadoria)", f"R$ {df['valor_icms'].sum():,.2f}")
        col2.metric("Total ISSQN (Serviço)", f"R$ {df['valor_issqn'].sum():,.2f}")
        col3.metric("Total Geral", f"R$ {df['valor_total'].sum():,.2f}")
        
        st.divider()
        
        # Gráfico comparativo
        df_melted = df.melt(id_vars=['emissor'], value_vars=['valor_icms', 'valor_issqn'], var_name='Imposto', value_name='Valor')
        st.plotly_chart(px.bar(df_melted, x='emissor', y='Valor', color='Imposto', title="ICMS vs ISSQN por Fornecedor"), use_container_width=True)

    with tab3:
        with st.spinner("Analisando regime tributário..."):
            analise = analisar_dados_com_ia(st.session_state.dados_processados)
            st.markdown(analise)
