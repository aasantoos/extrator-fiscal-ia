import streamlit as st
import os
import pandas as pd
import json
import io
import sqlite3
import time
from datetime import datetime
import plotly.express as px
from crewai import Agent, Task, Crew
from PyPDF2 import PdfReader
from streamlit_option_menu import option_menu # <--- NOVIDADE VISUAL

# --- 1. CONFIGURAÇÕES VISUAIS (FRONT-END) ---
st.set_page_config(page_title="Opertix System", page_icon="🚀", layout="wide")

# CSS PERSONALIZADO (A MÁGICA DO DESIGN)
st.markdown("""
<style>
    /* Fundo geral mais escuro e moderno */
    .stApp {
        background-color: #0E1117;
    }
    
    /* Cartões de Métricas (KPIs) */
    .kpi-card {
        background-color: #262730;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.5);
        text-align: center;
        border-left: 5px solid #FF4B4B;
    }
    .kpi-value {
        font-size: 32px;
        font-weight: bold;
        color: #FFFFFF;
        margin: 0;
    }
    .kpi-label {
        font-size: 14px;
        color: #A0A0A0;
        margin-top: 5px;
    }
    
    /* Ajuste do Menu Lateral */
    .css-1d391kg {
        background-color: #262730;
    }
</style>
""", unsafe_allow_html=True)

# Config API Key
if "OPENAI_API_KEY" in st.secrets:
    os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]
else:
    os.environ["OPENAI_API_KEY"] = "SUA_CHAVE_AQUI"

MODELO_LLM = "gpt-4o-mini"

# --- 2. FUNÇÕES DE BANCO E IA (MANTIDAS DO ORIGINAL) ---
def conectar_banco():
    return sqlite3.connect("dados_fiscais.db")

def inicializar_banco():
    conn = conectar_banco()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS notas_fiscais (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_upload TIMESTAMP,
            arquivo_origem TEXT,
            numero_nota TEXT,
            data_emissao TEXT,
            emissor_nome TEXT,
            emissor_cnpj TEXT,
            tomador_nome TEXT,
            tomador_cnpj TEXT,
            descricao_item TEXT,
            codigo_ncm TEXT,
            valor_bruto REAL,
            valor_liquido REAL,
            valor_icms REAL,
            valor_ipi REAL,
            valor_icms_st REAL,
            valor_issqn REAL,
            retencao_issqn REAL,
            valor_desconto REAL,
            json_completo TEXT
        )
    ''')
    conn.commit()
    conn.close()

def salvar_no_banco(df_novo):
    if df_novo.empty: return
    conn = conectar_banco()
    df_novo['data_upload'] = datetime.now()
    colunas_banco = ['arquivo_origem', 'numero_nota', 'data_emissao', 'emissor_nome', 'emissor_cnpj', 
                     'tomador_nome', 'tomador_cnpj', 'descricao_item', 'codigo_ncm', 'valor_bruto', 
                     'valor_liquido', 'valor_icms', 'valor_ipi', 'valor_icms_st', 'valor_issqn', 
                     'retencao_issqn', 'valor_desconto', 'data_upload']
    for col in colunas_banco:
        if col not in df_novo.columns: df_novo[col] = None
    df_novo['json_completo'] = df_novo.apply(lambda x: x.to_json(), axis=1)
    colunas_finais = colunas_banco + ['json_completo']
    df_novo[colunas_finais].to_sql('notas_fiscais', conn, if_exists='append', index=False)
    conn.close()

def carregar_historico():
    conn = conectar_banco()
    try:
        df = pd.read_sql("SELECT * FROM notas_fiscais ORDER BY data_upload DESC", conn)
    except:
        df = pd.DataFrame()
    conn.close()
    return df

inicializar_banco()

# --- FUNÇÕES AUXILIARES DE DESIGN ---
def card_metric_html(label, value, prefix="R$"):
    """Cria um cartão HTML bonito para métricas"""
    return f"""
    <div class="kpi-card">
        <div class="kpi-value">{prefix} {value:,.2f}</div>
        <div class="kpi-label">{label}</div>
    </div>
    """

def ler_pdf(uploaded_file):
    try:
        pdf_reader = PdfReader(uploaded_file)
        text = ""
        for page in pdf_reader.pages: text += page.extract_text()
        return text
    except: return ""

def criar_equipe_extracao():
    extrator = Agent(role='Auditor', goal='Extrair dados.', backstory='Auditor Fiscal.', verbose=False, llm=MODELO_LLM)
    auditor = Agent(role='Engenheiro', goal='JSON puro.', backstory='Engenheiro de dados.', verbose=False, llm=MODELO_LLM)
    return extrator, auditor

def analisar_dados_com_ia(df_historico):
    analista = Agent(role='CFO', goal='Análise financeira.', backstory='CFO experiente.', verbose=True, llm=MODELO_LLM)
    task = Task(description=f"Analise: {df_historico.head(20).to_string()}", expected_output="Relatório MD", agent=analista)
    return Crew(agents=[analista], tasks=[task]).kickoff()

# --- 3. MENU LATERAL PROFISSIONAL ---
with st.sidebar:
    # Logo ou Título estilizado
    st.markdown("<h1 style='text-align: center; color: #FF4B4B;'>OPERTIX</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Sistema de Inteligência Fiscal</p>", unsafe_allow_html=True)
    st.divider()
    
    selected = option_menu(
        menu_title=None,
        options=["Nova Auditoria", "Dashboard BI", "Banco de Dados"],
        icons=["cloud-upload", "graph-up-arrow", "database"],
        menu_icon="cast",
        default_index=0,
        styles={
            "container": {"padding": "0!important", "background-color": "transparent"},
            "icon": {"color": "orange", "font-size": "20px"}, 
            "nav-link": {"font-size": "16px", "text-align": "left", "margin":"0px", "--hover-color": "#333"},
            "nav-link-selected": {"background-color": "#FF4B4B"},
        }
    )
    
    st.divider()
    st.info("Status: Online 🟢")

# --- 4. CONTEÚDO DAS PÁGINAS ---

# === PÁGINA 1: NOVA AUDITORIA (UPLOAD) ===
if selected == "Nova Auditoria":
    st.title("🚀 Nova Auditoria")
    st.markdown("Arraste suas notas fiscais (PDF) para processamento imediato.")
    
    uploaded_files = st.file_uploader("Selecione os arquivos PDF", type='pdf', accept_multiple_files=True)
    
    if uploaded_files:
        if st.button("Iniciar Processamento Inteligente", type="primary"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            resultados = []
            
            for i, arquivo in enumerate(uploaded_files):
                progress_bar.progress((i + 1) / len(uploaded_files))
                status_text.markdown(f"🔄 **Processando:** `{arquivo.name}`...")
                
                texto = ler_pdf(arquivo)
                extrator, auditor = criar_equipe_extracao()
                
                # Tarefas (Simplificadas para o exemplo visual, use seu prompt blindado aqui)
                t1 = Task(description=f"Extraia do texto: {texto}. Identifique se é ICMS ou ISS. Extraia valores, datas, emissor, tomador.", expected_output="Dados", agent=extrator)
                t2 = Task(description="JSON válido: {numero_nota, emissor_nome, valor_bruto, valor_liquido, valor_icms, valor_issqn, valor_desconto}", expected_output="JSON", agent=auditor)
                
                try:
                    res = Crew(agents=[extrator, auditor], tasks=[t1, t2]).kickoff()
                    clean = str(res).replace("```json", "").replace("```", "").strip()
                    if clean.startswith("json"): clean = clean[4:]
                    dados = json.loads(clean)
                    dados['arquivo_origem'] = arquivo.name
                    resultados.append(dados)
                except:
                    st.error(f"Falha em {arquivo.name}")
            
            if resultados:
                df = pd.DataFrame(resultados)
                # Tratamento numérico simples
                for c in ['valor_bruto', 'valor_icms', 'valor_issqn', 'valor_desconto']:
                    if c not in df.columns: df[c] = 0.0
                    df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)
                
                salvar_no_banco(df)
                status_text.success("✅ Processamento concluído! Vá para a aba Dashboard.")
                time.sleep(1)

# === PÁGINA 2: DASHBOARD BI (VISUAL) ===
elif selected == "Dashboard BI":
    st.title("📊 Painel de Inteligência")
    df = carregar_historico()
    
    if df.empty:
        st.warning("Nenhum dado encontrado. Faça uma auditoria primeiro.")
    else:
        # 1. Cartões de KPI (HTML/CSS Customizado)
        st.markdown("### Indicadores Chave")
        c1, c2, c3, c4 = st.columns(4)
        
        # Tratamento de Nulos
        for col in ['valor_bruto', 'valor_icms', 'valor_issqn', 'valor_liquido']:
            if col not in df.columns: df[col] = 0.0
            df[col] = df[col].fillna(0.0)
            
        with c1: st.markdown(card_metric_html("Total Processado", df['valor_bruto'].sum()), unsafe_allow_html=True)
        with c2: st.markdown(card_metric_html("Total ICMS (Prod)", df['valor_icms'].sum()), unsafe_allow_html=True)
        with c3: st.markdown(card_metric_html("Total ISSQN (Serv)", df['valor_issqn'].sum()), unsafe_allow_html=True)
        with c4: st.markdown(card_metric_html("Total Líquido", df['valor_liquido'].sum()), unsafe_allow_html=True)
        
        st.markdown("---")
        
        # 2. Gráficos Modernos
        c_left, c_right = st.columns(2)
        
        with c_left:
            st.markdown("#### 🏆 Top Fornecedores")
            # Agrupa por emissor e soma valor bruto
            df_chart = df.groupby('emissor_nome')['valor_bruto'].sum().reset_index().sort_values('valor_bruto', ascending=False).head(5)
            fig = px.bar(df_chart, x='valor_bruto', y='emissor_nome', orientation='h', text_auto=True, color='valor_bruto', color_continuous_scale='Reds')
            fig.update_layout(showlegend=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color='white'))
            st.plotly_chart(fig, use_container_width=True)
            
        with c_right:
            st.markdown("#### ⚖️ Produtos vs Serviços")
            total_icms = df['valor_icms'].sum()
            total_iss = df['valor_issqn'].sum()
            df_pizza = pd.DataFrame({'Tipo': ['Produtos (ICMS)', 'Serviços (ISS)'], 'Valor': [total_icms, total_iss]})
            fig2 = px.pie(df_pizza, names='Tipo', values='Valor', hole=0.5, color_discrete_sequence=['#FF4B4B', '#FFA500'])
            fig2.update_layout(paper_bgcolor='rgba(0,0,0,0)', font=dict(color='white'))
            st.plotly_chart(fig2, use_container_width=True)

        # 3. Análise CFO
        st.markdown("---")
        if st.button("🤖 Gerar Análise Executiva do CFO"):
            with st.spinner("O CFO Virtual está analisando os números..."):
                analise = analisar_dados_com_ia(df)
                st.info("Relatório de Inteligência:")
                st.markdown(analise)

# === PÁGINA 3: BANCO DE DADOS (DADOS BRUTOS) ===
elif selected == "Banco de Dados":
    st.title("📂 Base de Dados Detalhada")
    df = carregar_historico()
    
    if not df.empty:
        # Remover colunas técnicas
        cols_drop = ['json_completo', 'id']
        df_show = df.drop(columns=[c for c in cols_drop if c in df.columns])
        
        st.dataframe(df_show, use_container_width=True, height=500)
        
        # Botões de Ação
        c1, c2 = st.columns([1, 4])
        with c1:
            if st.button("🗑️ Deletar Tudo"):
                conn = conectar_banco()
                conn.execute("DELETE FROM notas_fiscais")
                conn.commit()
                conn.close()
                st.warning("Base limpa!")
                time.sleep(1)
                st.rerun()
        with c2:
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_show.to_excel(writer, index=False)
            buffer.seek(0)
            st.download_button("📥 Baixar Excel Completo", buffer, "opertix_full.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
