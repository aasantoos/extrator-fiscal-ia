import streamlit as st
import os
import pandas as pd
import json
import plotly.express as px
from crewai import Agent, Task, Crew, Process
from PyPDF2 import PdfReader

# --- 1. CONFIGURAÇÕES ---
st.set_page_config(page_title="Agente Fiscal B.I.", page_icon="📊", layout="wide")

# Segurança da Chave API
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
    """Cria os agentes de extração."""
    extrator = Agent(
        role='Auditor Fiscal',
        goal='Extrair dados de notas fiscais com precisão.',
        backstory='Especialista em DANFE e NFS-e.',
        verbose=False, allow_delegation=False, llm=MODELO_LLM
    )
    auditor = Agent(
        role='Engenheiro de Dados',
        goal='Padronizar JSON.',
        backstory='Garante que números sejam float e datas sejam strings iso.',
        verbose=False, allow_delegation=False, llm=MODELO_LLM
    )
    return extrator, auditor

def analisar_dados_com_ia(df_json):
    """Cria um agente extra para analisar o resultado final."""
    analista = Agent(
        role='CFO Virtual',
        goal='Analisar os gastos e impostos extraídos e gerar insights.',
        backstory='Você é um diretor financeiro experiente. Você lê os dados consolidados e aponta onde estamos gastando mais e se há anomalias tributárias.',
        verbose=True, allow_delegation=False, llm=MODELO_LLM
    )
    
    task_analise = Task(
        description=f"""
        Analise os dados financeiros extraídos abaixo (em formato JSON):
        {df_json}
        
        Escreva um RELATÓRIO EXECUTIVO (em markdown) contendo:
        1. Resumo do total gasto.
        2. Qual o fornecedor mais caro.
        3. Análise da carga tributária (Estamos pagando muito imposto?).
        4. Alerta sobre qualquer anomalia.
        """,
        expected_output="Texto em markdown com a análise.",
        agent=analista
    )
    
    crew_analise = Crew(agents=[analista], tasks=[task_analise])
    return crew_analise.kickoff()

# --- 3. INTERFACE ---
st.title("📊 Dashboard Fiscal com IA")
st.markdown("Extração de dados + Análise Financeira Automática.")

arquivos_upload = st.file_uploader("Upload de Notas (PDF)", type="pdf", accept_multiple_files=True)

if 'dados_processados' not in st.session_state:
    st.session_state.dados_processados = None

# --- 4. PROCESSAMENTO ---
if arquivos_upload:
    if st.button("🚀 Processar e Analisar", type="primary"):
        
        resultados = []
        barra = st.progress(0)
        status = st.empty()
        
        # Aba de logs para não poluir a visão principal
        with st.expander("Ver logs de processamento", expanded=True):
            for i, arquivo in enumerate(arquivos_upload):
                barra.progress((i + 1) / len(arquivos_upload))
                status.write(f"Lendo: {arquivo.name}...")
                
                texto = ler_pdf(arquivo)
                extrator, auditor = criar_equipe_extracao()
                
                # Tarefa simplificada para o exemplo (mas usando o prompt universal)
                task_ex = Task(
                    description=f"Extraia do texto:\n{texto}\nCampos: Emissor, CNPJ Emissor, Data, Valor Total, Valor Liquido, Valor Impostos (Soma de ICMS/ISS).",
                    expected_output="Lista de dados.", agent=extrator
                )
                task_json = Task(
                    description="JSON: {emissor, cnpj, data, valor_total, valor_liquido, valor_impostos}",
                    expected_output="JSON válido.", agent=auditor
                )
                
                crew = Crew(agents=[extrator, auditor], tasks=[task_ex, task_json])
                
                try:
                    res = crew.kickoff()
                    clean_res = str(res).replace("```json", "").replace("```", "").strip()
                    dados = json.loads(clean_res)
                    dados['arquivo'] = arquivo.name
                    resultados.append(dados)
                    st.success(f"✅ {arquivo.name} processado.")
                except Exception as e:
                    st.error(f"Erro em {arquivo.name}")

        st.session_state.dados_processados = resultados
        status.success("Concluído!")

# --- 5. VISUALIZAÇÃO E B.I. ---
if st.session_state.dados_processados:
    df = pd.DataFrame(st.session_state.dados_processados)
    
    # Tratamento de dados para gráficos (garantir que números são números)
    df['valor_total'] = pd.to_numeric(df['valor_total'], errors='coerce').fillna(0)
    df['valor_impostos'] = pd.to_numeric(df['valor_impostos'], errors='coerce').fillna(0)
    
    # Criando Abas
    tab1, tab2, tab3 = st.tabs(["📂 Dados Brutos", "📈 Dashboard Visual", "🤖 Análise do CFO"])
    
    with tab1:
        st.dataframe(df)
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("Baixar CSV", csv, "relatorio_fiscal.csv", "text/csv")
        
    with tab2:
        col1, col2, col3 = st.columns(3)
        total_gasto = df['valor_total'].sum()
        total_imposto = df['valor_impostos'].sum()
        
        col1.metric("Total Gasto", f"R$ {total_gasto:,.2f}")
        col2.metric("Total Impostos", f"R$ {total_imposto:,.2f}")
        col3.metric("Carga Tributária", f"{((total_imposto/total_gasto)*100):.1f}%" if total_gasto > 0 else "0%")
        
        st.divider()
        
        # Gráfico 1: Quem levou meu dinheiro?
        fig_fornecedor = px.bar(df, x='emissor', y='valor_total', title="Gastos por Fornecedor", color='valor_total')
        st.plotly_chart(fig_fornecedor, use_container_width=True)
        
        # Gráfico 2: Composição (Pizza)
        # Criando um DF auxiliar para pizza
        df_pizza = pd.DataFrame({
            'Categoria': ['Valor Líquido', 'Impostos'],
            'Valor': [df['valor_liquido'].sum(), df['valor_impostos'].sum()]
        })
        fig_pizza = px.pie(df_pizza, values='Valor', names='Categoria', title="Peso dos Impostos no Custo Total")
        st.plotly_chart(fig_pizza, use_container_width=True)

    with tab3:
        st.info("O Agente 'CFO Virtual' está analisando seus números agora...")
        with st.spinner("Escrevendo relatório..."):
            # Envia o JSON dos dados para a IA analisar
            resumo_ia = analisar_dados_com_ia(st.session_state.dados_processados)
            st.markdown(resumo_ia)
