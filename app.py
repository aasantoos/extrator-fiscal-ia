import streamlit as st
import os
import pandas as pd
import json
import io
import plotly.express as px
from crewai import Agent, Task, Crew, Process
from PyPDF2 import PdfReader

# --- 1. CONFIGURAÇÕES ---
st.set_page_config(page_title="Agente Fiscal Master", page_icon="🏢", layout="wide")

# Segurança da API Key
if "OPENAI_API_KEY" in st.secrets:
    os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]
else:
    # Se for rodar local, coloque sua chave aqui para testes
    os.environ["OPENAI_API_KEY"] = "SUA_CHAVE_AQUI"

MODELO_LLM = "gpt-4o-mini"

# --- 2. FUNÇÕES ESSENCIAIS ---
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
    """Cria os agentes especialistas em extração."""
    extrator = Agent(
        role='Auditor Fiscal Senior',
        goal='Extrair TODOS os dados detalhados de notas (Serviço e Produto).',
        backstory='Especialista em identificar Tomador, Prestador, NCM, Códigos de Tributação e Retenções (ISS/INSS).',
        verbose=False, allow_delegation=False, llm=MODELO_LLM
    )
    auditor = Agent(
        role='Engenheiro de Dados',
        goal='Padronizar JSON e corrigir tipos numéricos.',
        backstory='Garante que números sejam float e campos vazios sejam null.',
        verbose=False, allow_delegation=False, llm=MODELO_LLM
    )
    return extrator, auditor

def analisar_dados_com_ia(df_json):
    """Agente CFO para gerar insights."""
    analista = Agent(
        role='CFO Virtual',
        goal='Gerar insights financeiros sobre as notas processadas.',
        backstory='Diretor financeiro que analisa custos, carga tributária e anomalias.',
        verbose=True, allow_delegation=False, llm=MODELO_LLM
    )
    task_analise = Task(
        description=f"Analise estes dados financeiros:\n{df_json}\n\nEscreva um relatório executivo (Markdown) citando o maior fornecedor, total de impostos retidos e sugestões de economia.",
        expected_output="Relatório em Markdown.",
        agent=analista
    )
    return Crew(agents=[analista], tasks=[task_analise]).kickoff()

# --- 3. INTERFACE ---
st.title("🏢 Agente Fiscal: Extração Universal + BI")
st.markdown("Extrai Tomador, NCM, Retenções e gera Dashboards Automáticos.")

arquivos_upload = st.file_uploader("Upload de Notas (PDF)", type="pdf", accept_multiple_files=True)

if 'dados_processados' not in st.session_state:
    st.session_state.dados_processados = None

# --- 4. PROCESSAMENTO (LOOP) ---
if arquivos_upload:
    if st.button("🚀 Processar Notas Completas", type="primary"):
        resultados = []
        barra = st.progress(0)
        status = st.empty()
        
        with st.expander("Ver logs de extração (Tempo Real)", expanded=True):
            for i, arquivo in enumerate(arquivos_upload):
                barra.progress((i + 1) / len(arquivos_upload))
                status.write(f"Auditando: {arquivo.name}...")
                
                texto = ler_pdf(arquivo)
                extrator, auditor = criar_equipe_extracao()
                
                # --- PROMPT UNIVERSAL (MANTIDO) ---
                task_ex = Task(
                    description=f"""
                    Analise o texto da nota:
                    ---
                    {texto}
                    ---
                    Extraia TUDO:
                    1. Emissor (Nome, CNPJ)
                    2. Tomador (Nome, CNPJ)
                    3. Detalhes (Número Nota, Data Emissão, Código Tributação/NCM, Descrição Serviço)
                    4. Valores (Valor Bruto, Valor Líquido)
                    5. Impostos (Retenção ISSQN, ICMS ST, Total Tributos)
                    """,
                    expected_output="Lista completa de dados.", agent=extrator
                )
                
                # --- JSON PADRONIZADO ---
                task_json = Task(
                    description="""
                    Gere JSON válido com chaves: 
                    {numero_nota, data_emissao, emissor_nome, emissor_cnpj, tomador_nome, tomador_cnpj, 
                    descricao_item, codigo_ncm_tributacao, valor_bruto, valor_liquido, retencao_issqn, icms_st, total_tributos}
                    Use 0.0 para valores numéricos não encontrados.
                    """,
                    expected_output="JSON válido.", agent=auditor
                )
                
                crew = Crew(agents=[extrator, auditor], tasks=[task_ex, task_json])
                
                try:
                    res = crew.kickoff()
                    # Limpeza de segurança
                    clean_res = str(res).replace("```json", "").replace("```", "").strip()
                    if clean_res.startswith("json"): clean_res = clean_res[4:] # Remove prefixo json solto
                    
                    dados = json.loads(clean_res)
                    dados['arquivo_origem'] = arquivo.name
                    resultados.append(dados)
                    st.success(f"✅ {arquivo.name}: R$ {dados.get('valor_bruto', 0)}")
                except Exception as e:
                    st.error(f"Falha em {arquivo.name}: {e}")

        st.session_state.dados_processados = resultados
        status.success("Auditoria Concluída!")

# --- 5. VISUALIZAÇÃO E DOWNLOAD ---
if st.session_state.dados_processados:
    df = pd.DataFrame(st.session_state.dados_processados)
    
    # Tratamento de Tipos para Gráficos
    cols_num = ['valor_bruto', 'valor_liquido', 'retencao_issqn', 'icms_st', 'total_tributos']
    for col in cols_num:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    # Abas
    tab1, tab2, tab3 = st.tabs(["📥 Excel BI", "📊 Dashboard Dinâmico", "🤖 Análise CFO"])
    
    with tab1:
        st.dataframe(df)
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        buffer.seek(0)
        st.download_button("Baixar Excel (.xlsx) para Power BI", buffer, "dados_fiscais_universal.xlsx", 
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")

    with tab2:
        st.write("### Monte seu Gráfico")
        colA, colB, colC = st.columns(3)
        with colA: x_axis = st.selectbox("Eixo X", df.columns, index=2) # Tenta pegar emissor_nome por padrão se existir
        with colB: y_axis = st.selectbox("Eixo Y", cols_num, index=0)
        with colC: chart_type = st.selectbox("Tipo", ["Barra", "Pizza", "Linha", "Dispersão"])
        
        if chart_type == "Barra": st.plotly_chart(px.bar(df, x=x_axis, y=y_axis, color=x_axis), use_container_width=True)
        if chart_type == "Pizza": st.plotly_chart(px.pie(df, values=y_axis, names=x_axis), use_container_width=True)
        if chart_type == "Linha": st.plotly_chart(px.line(df, x=x_axis, y=y_axis), use_container_width=True)
        if chart_type == "Dispersão": st.plotly_chart(px.scatter(df, x=x_axis, y=y_axis, size=y_axis), use_container_width=True)

    with tab3:
        st.info("O CFO Virtual está analisando os dados extraídos...")
        with st.spinner("Gerando relatório de inteligência..."):
            analise = analisar_dados_com_ia(st.session_state.dados_processados)
            st.markdown(analise)
