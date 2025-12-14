import streamlit as st
import os
import pandas as pd
import json
import io
import sqlite3
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import plotly.express as px
from crewai import Agent, Task, Crew
from PyPDF2 import PdfReader
from streamlit_option_menu import option_menu
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors

# --- 1. CONFIGURAÇÕES INICIAIS E VISUAL ---
st.set_page_config(page_title="Opertix System", page_icon="🚀", layout="wide")

# CSS PERSONALIZADO (LOGIN, KPI, DARK MODE)
st.markdown("""
<style>
    /* Fundo Geral */
    .stApp { background-color: #0E1117; }
    
    /* Cards de KPI */
    .kpi-card {
        background-color: #262730; 
        padding: 20px; 
        border-radius: 10px;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.5); 
        text-align: center;
        border-left: 5px solid #FF4B4B;
    }
    .kpi-value { font-size: 32px; font-weight: bold; color: #FFFFFF; margin: 0; }
    .kpi-label { font-size: 14px; color: #A0A0A0; margin-top: 5px; }
    
    /* Menu Lateral */
    .css-1d391kg { background-color: #262730; }
    
    /* Ajustes do Login */
    [data-testid="InputInstructions"] { display: none !important; }
    
    div[data-baseweb="input"] > div {
        border: 1px solid #555 !important;
        border-radius: 8px !important;
        background-color: #1E1E24 !important;
    }
    
    div[data-testid="stForm"] {
        background-color: #262730;
        padding: 40px;
        border-radius: 15px;
        border: 1px solid #444;
        box-shadow: 0px 0px 30px rgba(0,0,0,0.7);
    }
</style>
""", unsafe_allow_html=True)

# Configuração da API Key
if "OPENAI_API_KEY" in st.secrets:
    os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]
else:
    os.environ["OPENAI_API_KEY"] = "SUA_CHAVE_AQUI" # Coloque sua chave aqui se rodar local sem secrets

MODELO_LLM = "gpt-4o-mini"

# --- 2. SISTEMA DE LOGIN ---
USUARIOS = {
    "admin": "admin123",
    "cliente": "12345"
}

def verificar_login():
    """Gerencia a sessão de login e bloqueia acesso não autorizado"""
    if 'logado' not in st.session_state:
        st.session_state['logado'] = False
        st.session_state['usuario_atual'] = None

    if not st.session_state['logado']:
        # Layout ajustado [1, 2, 1] para a caixa ficar larga
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown("<br><br>", unsafe_allow_html=True)
            st.markdown("<h1 style='text-align: center; color: #FF4B4B;'>🔒 Opertix</h1>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; color: gray;'>Sistema de Inteligência Fiscal</p>", unsafe_allow_html=True)
            
            with st.form("login_form"):
                st.markdown("**Credenciais de Acesso**")
                user = st.text_input("Usuário", placeholder="Digite seu usuário")
                pwd = st.text_input("Senha", type="password", placeholder="Digite sua senha")
                
                st.markdown("<br>", unsafe_allow_html=True)
                submit = st.form_submit_button("Acessar Sistema", type="primary", use_container_width=True)
                
                if submit:
                    if user in USUARIOS and USUARIOS[user] == pwd:
                        st.session_state['logado'] = True
                        st.session_state['usuario_atual'] = user
                        st.toast("Login realizado com sucesso!", icon="✅")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Usuário ou senha incorretos.")
        return False
    return True

# Bloqueio de Segurança
if not verificar_login():
    st.stop()

# =========================================================
# ÁREA RESTRITA (SISTEMA CARREGA ABAIXO)
# =========================================================

# --- 3. CONEXÃO GOOGLE SHEETS (NUVEM) ---
def conectar_gsheets():
    """Tenta conectar ao Google Sheets usando creds.json"""
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        if os.path.exists("creds.json"):
            creds = ServiceAccountCredentials.from_json_keyfile_name("creds.json", scope)
            client = gspread.authorize(creds)
            # ATENÇÃO: O nome aqui deve ser EXATAMENTE igual ao da sua planilha no Google
            sheet = client.open("Dados Fiscais Opertix").sheet1
            return sheet
        else:
            return None
    except Exception as e:
        return None

# --- 4. BANCO DE DADOS (LOCAL + NUVEM) ---
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
    
    # 1. SALVAR NO SQLITE (LOCAL)
    conn = conectar_banco()
    df_novo['data_upload'] = datetime.now()
    
    colunas_banco = ['arquivo_origem', 'numero_nota', 'data_emissao', 'emissor_nome', 'emissor_cnpj', 
                     'tomador_nome', 'tomador_cnpj', 'descricao_item', 'codigo_ncm', 'valor_bruto', 
                     'valor_liquido', 'valor_icms', 'valor_ipi', 'valor_icms_st', 'valor_issqn', 
                     'retencao_issqn', 'valor_desconto', 'data_upload']
    
    for col in colunas_banco:
        if col not in df_novo.columns: df_novo[col] = None
        
    df_novo['json_completo'] = df_novo.apply(lambda x: x.to_json(), axis=1)
    
    # Prepara dataframe para salvar (converte data para string)
    df_salvar = df_novo.copy()
    df_salvar['data_upload'] = df_salvar['data_upload'].astype(str)
    
    colunas_finais = colunas_banco + ['json_completo']
    df_salvar[colunas_finais].to_sql('notas_fiscais', conn, if_exists='append', index=False)
    conn.close()

    # 2. SALVAR NO GOOGLE SHEETS (NUVEM)
    sheet = conectar_gsheets()
    if sheet:
        try:
            # Debug visual para confirmar conexão
            st.info(f"🔗 Conectado à planilha: {sheet.title} (ID: {sheet.spreadsheet.id})")
            
            # Se planilha vazia, cria cabeçalho
            if len(sheet.get_all_values()) == 0:
                sheet.append_row(colunas_banco)
            
            # Converte para lista e salva
            dados_nuvem = df_salvar[colunas_banco].fillna("").values.tolist()
            for linha in dados_nuvem:
                sheet.append_row(linha)
            
            st.toast("Backup na Nuvem (Google Sheets) realizado!", icon="☁️")
        except Exception as e:
            st.error(f"Erro ao salvar na nuvem: {e}")
    else:
        st.warning("Salvo apenas Localmente (Planilha não encontrada ou creds.json ausente).")

def carregar_historico():
    conn = conectar_banco()
    try:
        df = pd.read_sql("SELECT * FROM notas_fiscais ORDER BY data_upload DESC", conn)
    except:
        df = pd.DataFrame()
    conn.close()
    return df

inicializar_banco()

# --- 5. GERADOR DE PDF ---
def gerar_relatorio_pdf(df_filtrado):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    # Cabeçalho
    c.setFillColor(colors.darkblue)
    c.rect(0, height - 100, width, 100, fill=True, stroke=False)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 28)
    c.drawString(40, height - 60, "OPERTIX")
    c.setFont("Helvetica", 14)
    c.drawString(40, height - 85, "Relatório de Auditoria Fiscal & Financeira")
    
    # Corpo
    c.setFillColor(colors.black)
    y = height - 150
    
    # Resumo Financeiro
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, y, "1. Resumo do Período")
    y -= 30
    
    val_bruto = df_filtrado['valor_bruto'].sum()
    val_liq = df_filtrado['valor_liquido'].sum()
    val_icms = df_filtrado['valor_icms'].sum()
    val_iss = df_filtrado['valor_issqn'].sum()
    
    c.setFont("Helvetica", 12)
    c.drawString(40, y, f"• Total Processado: R$ {val_bruto:,.2f}")
    y -= 20
    c.drawString(40, y, f"• Total Líquido a Pagar: R$ {val_liq:,.2f}")
    y -= 20
    c.drawString(40, y, f"• Total ICMS (Produtos): R$ {val_icms:,.2f}")
    y -= 20
    c.drawString(40, y, f"• Total ISSQN (Serviços): R$ {val_iss:,.2f}")
    
    y -= 40
    c.setStrokeColor(colors.gray)
    c.line(40, y, width - 40, y)
    y -= 40
    
    # Detalhamento
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, y, "2. Detalhamento por Nota (Top Recentes)")
    y -= 30
    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, y, "DATA")
    c.drawString(120, y, "EMISSOR")
    c.drawString(300, y, "TIPO")
    c.drawString(450, y, "VALOR")
    y -= 15
    
    c.setFont("Helvetica", 9)
    # Pega apenas as primeiras 30 notas para não quebrar o PDF de exemplo
    for idx, row in df_filtrado.head(30).iterrows():
        if y < 50: # Nova página se acabar espaço
            c.showPage()
            y = height - 50
        
        data = str(row['data_emissao'])[:10]
        emissor = str(row['emissor_nome'])[:25]
        tipo = "Produto" if row['valor_icms'] > 0 else "Serviço"
        valor = f"R$ {row['valor_bruto']:,.2f}"
        
        c.drawString(40, y, data)
        c.drawString(120, y, emissor)
        c.drawString(300, y, tipo)
        c.drawString(450, y, valor)
        y -= 15

    # Rodapé
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(40, 30, f"Gerado automaticamente em {datetime.now().strftime('%d/%m/%Y')}")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

# --- 6. AGENTES IA & UTILITÁRIOS ---
def ler_pdf(uploaded_file):
    try:
        pdf_reader = PdfReader(uploaded_file)
        text = ""
        for page in pdf_reader.pages: text += page.extract_text()
        return text
    except: return ""

def criar_equipe_extracao():
    extrator = Agent(
        role='Auditor Tributário Sênior',
        goal='Extrair dados com fidelidade absoluta, distinguindo Comércio (ICMS) e Serviço (ISS).',
        backstory='Especialista em legislação fiscal. Você não inventa dados.',
        verbose=False, allow_delegation=False, llm=MODELO_LLM
    )
    auditor = Agent(
        role='Engenheiro de Dados',
        goal='Padronizar JSON e sanitizar dados.',
        backstory='Garante datas em DD/MM/AAAA, floats corretos e campos vazios zerados.',
        verbose=False, allow_delegation=False, llm=MODELO_LLM
    )
    return extrator, auditor

def analisar_dados_com_ia(df_historico):
    analista = Agent(
        role='CFO Virtual',
        goal='Analisar o histórico financeiro acumulado.',
        backstory='Analisa tendências de longo prazo e carga tributária.',
        verbose=True, allow_delegation=False, llm=MODELO_LLM
    )
    task = Task(description=f"Analise: {df_historico.head(50).to_string()}", expected_output="Relatório Executivo Markdown", agent=analista)
    return Crew(agents=[analista], tasks=[task]).kickoff()

def card_metric_html(label, value, prefix="R$"):
    return f"""
    <div class="kpi-card">
        <div class="kpi-value">{prefix} {value:,.2f}</div>
        <div class="kpi-label">{label}</div>
    </div>
    """

# --- 7. MENU LATERAL ---
with st.sidebar:
    st.markdown("<h1 style='text-align: center; color: #FF4B4B;'>OPERTIX</h1>", unsafe_allow_html=True)
    st.markdown(f"<p style='text-align: center; color: gray;'>Usuário: <b>{st.session_state['usuario_atual']}</b></p>", unsafe_allow_html=True)
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
    if st.button("🚪 Sair do Sistema"):
        st.session_state['logado'] = False
        st.session_state['usuario_atual'] = None
        st.rerun()

# --- 8. PÁGINAS ---

# === NOVA AUDITORIA ===
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
                
                # Tarefas Blindadas
                t1 = Task(
                    description=f"""
                    Analise o texto:
                    ---
                    {texto}
                    ---
                    REGRAS:
                    1. NÃO ALUCINE. Se não achar, use 0.0.
                    2. DATAS: Converta para DD/MM/AAAA.
                    3. EXTRAIA: Tipo (DANFE/NFSe), Emissor, Tomador, Num, Data.
                    4. FINANCEIRO: Bruto, Líquido, Desconto.
                    5. IMPOSTOS: ICMS, IPI, ISSQN, Retenções.
                    """,
                    expected_output="Dados extraídos.", agent=extrator
                )
                
                t2 = Task(
                    description="""
                    Gere JSON válido:
                    {
                        "numero_nota": "string", "data_emissao": "string", 
                        "emissor_nome": "string", "emissor_cnpj": "string", 
                        "tomador_nome": "string", "tomador_cnpj": "string", 
                        "descricao_item": "string", "codigo_ncm": "string", 
                        "valor_bruto": float, "valor_desconto": float, "valor_liquido": float, 
                        "valor_icms": float, "valor_ipi": float, "valor_icms_st": float,
                        "valor_issqn": float, "retencao_issqn": float
                    }
                    """,
                    expected_output="JSON válido.", agent=auditor
                )
                
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
                cols_num = ['valor_bruto', 'valor_liquido', 'valor_icms', 'valor_issqn', 'valor_ipi', 'valor_desconto']
                for c in cols_num:
                    if c not in df.columns: df[c] = 0.0
                    df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)
                
                salvar_no_banco(df)
                status_text.success("✅ Processamento concluído! Dados salvos.")
                time.sleep(2)

# === DASHBOARD BI ===
elif selected == "Dashboard BI":
    st.title("📊 Painel de Inteligência")
    df = carregar_historico()
    
    if df.empty:
        st.warning("Nenhum dado encontrado.")
    else:
        # Botão PDF
        col_pdf, _ = st.columns([1, 4])
        with col_pdf:
            pdf_bytes = gerar_relatorio_pdf(df)
            st.download_button(
                label="📄 Baixar Relatório Executivo (PDF)",
                data=pdf_bytes,
                file_name="relatorio_opertix.pdf",
                mime="application/pdf"
            )

        # Filtro Visual
        cols_drop = ['json_completo', 'id']
        df_visual = df.drop(columns=[c for c in cols_drop if c in df.columns], errors='ignore')

        st.markdown("### Indicadores Chave")
        c1, c2, c3, c4 = st.columns(4)
        
        for col in ['valor_bruto', 'valor_icms', 'valor_issqn', 'valor_liquido']:
            if col not in df.columns: df[col] = 0.0
            df[col] = df[col].fillna(0.0)
            
        with c1: st.markdown(card_metric_html("Total Processado", df['valor_bruto'].sum()), unsafe_allow_html=True)
        with c2: st.markdown(card_metric_html("Total ICMS (Prod)", df['valor_icms'].sum()), unsafe_allow_html=True)
        with c3: st.markdown(card_metric_html("Total ISSQN (Serv)", df['valor_issqn'].sum()), unsafe_allow_html=True)
        with c4: st.markdown(card_metric_html("Total Líquido", df['valor_liquido'].sum()), unsafe_allow_html=True)
        
        st.markdown("---")
        c_left, c_right = st.columns(2)
        
        with c_left:
            st.markdown("#### 🏆 Top Fornecedores")
            if 'emissor_nome' in df.columns:
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

        st.markdown("---")
        if st.button("🤖 Gerar Análise Executiva do CFO"):
            with st.spinner("O CFO Virtual está analisando os números..."):
                analise = analisar_dados_com_ia(df)
                st.info("Relatório de Inteligência:")
                st.markdown(analise)

# === BANCO DE DADOS ===
elif selected == "Banco de Dados":
    st.title("📂 Base de Dados Detalhada")
    df = carregar_historico()
    
    if not df.empty:
        cols_drop = ['json_completo', 'id']
        df_show = df.drop(columns=[c for c in cols_drop if c in df.columns], errors='ignore')
        
        st.dataframe(df_show, use_container_width=True, height=500)
        
        c1, c2 = st.columns([1, 4])
        with c1:
            if st.button("🗑️ Deletar Tudo (Local)"):
                conn = conectar_banco()
                conn.execute("DELETE FROM notas_fiscais")
                conn.commit()
                conn.close()
                st.warning("Base Local limpa!")
                time.sleep(1)
                st.rerun()
        with c2:
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_show.to_excel(writer, index=False)
            buffer.seek(0)
            st.download_button("📥 Baixar Excel Completo", buffer, "opertix_full.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
