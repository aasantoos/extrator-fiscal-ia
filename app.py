import streamlit as st
import os
import pandas as pd
import json
import io
import sqlite3
import time
from datetime import datetime
import plotly.express as px
from crewai import Agent, Task, Crew, Process
from PyPDF2 import PdfReader

# --- 1. CONFIGURAÇÕES ---
st.set_page_config(page_title="Agente Fiscal Master + Memória", page_icon="💾", layout="wide")

if "OPENAI_API_KEY" in st.secrets:
    os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]
else:
    os.environ["OPENAI_API_KEY"] = "SUA_CHAVE_AQUI"

MODELO_LLM = "gpt-4o-mini"

# --- 2. BANCO DE DADOS (NOVA FUNCIONALIDADE) ---
def conectar_banco():
    return sqlite3.connect("dados_fiscais.db")

def inicializar_banco():
    conn = conectar_banco()
    c = conn.cursor()
    # Criamos tabela com TODOS os campos da sua lógica fiscal
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
            json_completo TEXT
        )
    ''')
    conn.commit()
    conn.close()

def salvar_no_banco(df_novo):
    if df_novo.empty: return
    
    conn = conectar_banco()
    df_novo['data_upload'] = datetime.now()
    
    # Lista de colunas para garantir a ordem no banco
    colunas_banco = [
        'arquivo_origem', 'numero_nota', 'data_emissao', 
        'emissor_nome', 'emissor_cnpj', 'tomador_nome', 'tomador_cnpj',
        'descricao_item', 'codigo_ncm', 
        'valor_bruto', 'valor_liquido', 
        'valor_icms', 'valor_ipi', 'valor_icms_st', 'valor_issqn', 'retencao_issqn',
        'data_upload'
    ]
    
    # Preenche colunas faltantes com None/0
    for col in colunas_banco:
        if col not in df_novo.columns:
            df_novo[col] = None
            
    # Salva JSON bruto para segurança
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

# Inicia o banco ao abrir
inicializar_banco()

# --- 3. AGENTES (LÓGICA EXISTENTE PRESERVADA) ---
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
    """Mantendo a instrução de distinguir ICMS e ISS."""
    extrator = Agent(
        role='Auditor Tributário Sênior',
        goal='Extrair dados distinguindo Comércio (ICMS) e Serviço (ISS).',
        backstory='Especialista em legislação fiscal (DANFE vs NFS-e).',
        verbose=False, allow_delegation=False, llm=MODELO_LLM
    )
    auditor = Agent(
        role='Engenheiro de Dados',
        goal='Padronizar JSON.',
        backstory='Garante floats corretos e campos vazios zerados.',
        verbose=False, allow_delegation=False, llm=MODELO_LLM
    )
    return extrator, auditor

def analisar_dados_com_ia(df_historico):
    analista = Agent(
        role='CFO Virtual',
        goal='Analisar o histórico financeiro acumulado.',
        backstory='Analisa tendências de longo prazo.',
        verbose=True, allow_delegation=False, llm=MODELO_LLM
    )
    dados_texto = df_historico.head(50).to_string()
    
    task = Task(
        description=f"Analise este histórico:\n{dados_texto}\n\nRelatório: Tendência de gastos, proporção de Serviços vs Produtos e sugestões.",
        expected_output="Relatório Markdown.",
        agent=analista
    )
    return Crew(agents=[analista], tasks=[task]).kickoff()

# --- 4. INTERFACE ---
st.title("💾 Agente Fiscal Master (Com Memória)")
st.markdown("Extração Universal (ICMS/ISS) + Banco de Dados Automático.")

# Sidebar com Memória
with st.sidebar:
    st.header("Banco de Dados")
    df_hist = carregar_historico()
    st.metric("Notas Salvas", len(df_hist))
    val_total = df_hist['valor_bruto'].sum() if not df_hist.empty else 0
    st.metric("Total Processado", f"R$ {val_total:,.2f}")
    
    if st.button("🗑️ Limpar Tudo"):
        conn = conectar_banco()
        conn.execute("DELETE FROM notas_fiscais")
        conn.commit()
        conn.close()
        st.warning("Banco limpo!")
        time.sleep(1)
        st.rerun()

arquivos_upload = st.file_uploader("Processar Novas Notas", type="pdf", accept_multiple_files=True)

# --- 5. PROCESSAMENTO ---
if arquivos_upload:
    if st.button("🚀 Processar e Salvar", type="primary"):
        resultados = []
        barra = st.progress(0)
        status = st.empty()
        
        with st.expander("Logs da Auditoria", expanded=True):
            for i, arquivo in enumerate(arquivos_upload):
                barra.progress((i + 1) / len(arquivos_upload))
                status.write(f"Auditando: {arquivo.name}...")
                
                texto = ler_pdf(arquivo)
                extrator, auditor = criar_equipe_extracao()
                
                # --- PROMPT DA CONTADORA (MANTIDO) ---
                task_ex = Task(
                    description=f"""
                    Analise o texto da nota:
                    ---
                    {texto}
                    ---
                    
                    IDENTIFIQUE E EXTRAIA:
                    
                    1. TIPO DE NOTA (CRUCIAL):
                       - É DANFE/Venda? -> Extraia ICMS, IPI, ICMS-ST.
                       - É NFS-e/Serviço? -> Extraia ISSQN.
                    
                    2. DADOS:
                       - Emissor (Nome, CNPJ)
                       - Tomador (Nome, CNPJ)
                       - Número Nota, Data Emissão
                       - Descrição Item/Serviço, Código NCM
                    
                    3. VALORES:
                       - Valor Bruto, Valor Líquido
                       - Valor ICMS, Valor IPI, Valor ICMS-ST
                       - Valor ISSQN, Retenção ISSQN
                    """,
                    expected_output="Lista detalhada.", agent=extrator
                )
                
                # --- JSON COM CAMPOS SEPARADOS (MANTIDO) ---
                task_json = Task(
                    description="""
                    JSON válido com chaves exatas (use 0.0 se vazio): 
                    {
                        "numero_nota": "string", "data_emissao": "string", 
                        "emissor_nome": "string", "emissor_cnpj": "string", 
                        "tomador_nome": "string", "tomador_cnpj": "string", 
                        "descricao_item": "string", "codigo_ncm": "string", 
                        "valor_bruto": float, "valor_liquido": float, 
                        "valor_icms": float, "valor_ipi": float, "valor_icms_st": float,
                        "valor_issqn": float, "retencao_issqn": float
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
                    dados['arquivo_origem'] = arquivo.name
                    resultados.append(dados)
                    
                    tipo = "📦 Produto" if dados.get('valor_icms', 0) > 0 else "🛠️ Serviço"
                    st.success(f"✅ {arquivo.name} ({tipo}): R$ {dados.get('valor_bruto', 0)}")
                    
                except Exception as e:
                    st.error(f"Erro em {arquivo.name}: {e}")

        # Salvar no Banco (AQUI ENTRA O NOVO RECURSO)
        if resultados:
            df_novos = pd.DataFrame(resultados)
            
            # Tratamento numérico para evitar erros no banco
            cols_num = ['valor_bruto', 'valor_liquido', 'valor_icms', 'valor_ipi', 'valor_icms_st', 'valor_issqn', 'retencao_issqn']
            for c in cols_num:
                if c not in df_novos.columns: df_novos[c] = 0.0
                df_novos[c] = pd.to_numeric(df_novos[c], errors='coerce').fillna(0.0)
            
            salvar_no_banco(df_novos)
            st.success("Dados salvos na memória!")
            time.sleep(1)
            st.rerun()

# --- 6. VISUALIZAÇÃO DO HISTÓRICO (MANTIDO) ---
if not df_hist.empty:
    st.divider()
    st.subheader("📂 Painel Geral (Histórico)")
    
    # Preenche zeros para visualização se o banco tiver campos nulos
    cols_check = ['valor_icms', 'valor_issqn', 'valor_bruto']
    for c in cols_check:
        if c not in df_hist.columns: df_hist[c] = 0.0
        else: df_hist[c] = df_hist[c].fillna(0.0)

    tab1, tab2, tab3 = st.tabs(["📥 Excel Master", "📊 Dashboard", "🤖 Análise CFO"])
    
    with tab1:
        st.dataframe(df_hist)
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_hist.to_excel(writer, index=False)
        buffer.seek(0)
        st.download_button("Baixar Histórico Completo", buffer, "historico_master.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    with tab2:
        colA, colB, colC = st.columns(3)
        colA.metric("Total ICMS (Produtos)", f"R$ {df_hist['valor_icms'].sum():,.2f}")
        colB.metric("Total ISSQN (Serviços)", f"R$ {df_hist['valor_issqn'].sum():,.2f}")
        
        # Correção segura para IPI/ST caso não existam no histórico antigo
        ipi = df_hist['valor_ipi'].sum() if 'valor_ipi' in df_hist.columns else 0
        st_val = df_hist['valor_icms_st'].sum() if 'valor_icms_st' in df_hist.columns else 0
        colC.metric("Total IPI + ST", f"R$ {(ipi + st_val):,.2f}")
        
        st.write("#### Selecione os Eixos do Gráfico")
        c1, c2, c3 = st.columns(3)
        # Tenta selecionar colunas padrão se existirem
        idx_x = list(df_hist.columns).index('emissor_nome') if 'emissor_nome' in df_hist.columns else 0
        
        x_axis = c1.selectbox("Eixo X", df_hist.columns, index=idx_x)
        y_axis = c2.selectbox("Eixo Y", ['valor_bruto', 'valor_icms', 'valor_issqn'], index=0)
        chart = c3.selectbox("Tipo", ["Barra", "Pizza", "Linha"])
        
        if chart == "Barra": st.plotly_chart(px.bar(df_hist, x=x_axis, y=y_axis, color=x_axis), use_container_width=True)
        if chart == "Pizza": st.plotly_chart(px.pie(df_hist, values=y_axis, names=x_axis), use_container_width=True)
        if chart == "Linha": st.plotly_chart(px.line(df_hist, x=x_axis, y=y_axis), use_container_width=True)

    with tab3:
        if st.button("🧠 Pedir Análise do CFO"):
            with st.spinner("Analisando histórico..."):
                res = analisar_dados_com_ia(df_hist)
                st.markdown(res)
else:
    st.info("Histórico vazio. Faça upload acima.")
