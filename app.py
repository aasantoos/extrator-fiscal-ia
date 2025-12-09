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
st.set_page_config(page_title="Opertix", page_icon="💾", layout="wide")

if "OPENAI_API_KEY" in st.secrets:
    os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]
else:
    os.environ["OPENAI_API_KEY"] = "SUA_CHAVE_AQUI"

MODELO_LLM = "gpt-4o-mini"

# --- 2. BANCO DE DADOS ---
def conectar_banco():
    return sqlite3.connect("dados_fiscais.db")

def inicializar_banco():
    conn = conectar_banco()
    c = conn.cursor()
    # Tabela com todos os campos fiscais
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
    
    colunas_banco = [
        'arquivo_origem', 'numero_nota', 'data_emissao', 
        'emissor_nome', 'emissor_cnpj', 'tomador_nome', 'tomador_cnpj',
        'descricao_item', 'codigo_ncm', 
        'valor_bruto', 'valor_liquido', 
        'valor_icms', 'valor_ipi', 'valor_icms_st', 'valor_issqn', 'retencao_issqn',
        'data_upload'
    ]
    
    # Preenche colunas faltantes com None
    for col in colunas_banco:
        if col not in df_novo.columns:
            df_novo[col] = None
            
    # Salva o JSON completo (backup técnico invisível ao cliente)
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

# --- 3. AGENTES ---
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
    extrator = Agent(
        role='Auditor Tributário Sênior',
        goal='Extrair dados com fidelidade absoluta, distinguindo Comércio (ICMS) e Serviço (ISS).',
        backstory='Especialista em legislação fiscal. Você não inventa dados. Se não achar, deixa vazio.',
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
    dados_texto = df_historico.head(50).to_string()
    
    task = Task(
        description=f"Analise este histórico financeiro:\n{dados_texto}\n\nRelatório: Tendência de gastos, proporção de Serviços vs Produtos e sugestões de economia.",
        expected_output="Relatório Markdown.",
        agent=analista
    )
    return Crew(agents=[analista], tasks=[task]).kickoff()

# --- 4. INTERFACE ---
st.title("💾 Opertix")
st.markdown("Auditoria Fiscal Inteligente + Banco de Dados.")

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
                
                # --- PROMPT BLINDADO ---
                task_ex = Task(
                    description=f"""
                    Você é um Auditor Fiscal implacável. Analise o texto da nota fiscal:
                    ---
                    {texto}
                    ---
                    
                    REGRAS DE OURO:
                    1. NÃO ALUCINE: Se não achar, retorne "N/A" ou 0.0.
                    2. DATAS: Converta SEMPRE para DD/MM/AAAA.
                    3. VALORES: Ignore 'R$'. Use ponto para decimais.
                    
                    IDENTIFIQUE E EXTRAIA:
                    
                    A) TIPO DE DOCUMENTO:
                       - É DANFE/Venda? -> Foco em ICMS, IPI.
                       - É NFS-e/Serviço? -> Foco em ISSQN.
                    
                    B) ENTIDADES (Não inverta!):
                       - EMISSOR (Prestador/Vendedor): Quem recebe o dinheiro.
                       - TOMADOR (Cliente/Destinatário): Quem paga a conta.
                    
                    C) DETALHES:
                       - Número Nota (Apenas dígitos)
                       - Data Emissão (DD/MM/AAAA)
                       - Descrição Principal do Item/Serviço
                       - Código NCM (Produtos) ou Código Serviço
                    
                    D) FINANCEIRO:
                       - Valor Bruto (Total)
                       - Valor do DESCONTO (Se houver)
                       - Valor LÍQUIDO (Total a pagar)
                    
                    E) IMPOSTOS (Conforme o tipo):
                       - Valor ICMS, Valor IPI, Valor ICMS-ST (Se produto)
                       - Valor ISSQN, Retenção ISSQN (Se serviço)
                    """,
                    expected_output="Lista estruturada e auditada.", agent=extrator
                )
                
                # --- JSON BLINDADO ---
                task_json = Task(
                    description="""
                    Gere APENAS um JSON válido.
                    Estrutura Obrigatória (use 0.0 se vazio):
                    {
                        "numero_nota": "string", "data_emissao": "string", 
                        "emissor_nome": "string", "emissor_cnpj": "string", 
                        "tomador_nome": "string", "tomador_cnpj": "string", 
                        "descricao_item": "string", "codigo_ncm": "string", 
                        "valor_bruto": float, 
                        "valor_desconto": float,
                        "valor_liquido": float, 
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
                    
                    # Feedback visual
                    tipo = "📦 Produto" if dados.get('valor_icms', 0) > 0 else "🛠️ Serviço"
                    st.success(f"✅ {arquivo.name} ({tipo}): R$ {dados.get('valor_bruto', 0)}")
                    
                except Exception as e:
                    st.error(f"Erro em {arquivo.name}: {e}")

        if resultados:
            df_novos = pd.DataFrame(resultados)
            
            # Tratamento numérico seguro
            cols_num = ['valor_bruto', 'valor_liquido', 'valor_icms', 'valor_ipi', 'valor_icms_st', 'valor_issqn', 'retencao_issqn', 'valor_desconto']
            for c in cols_num:
                if c not in df_novos.columns: df_novos[c] = 0.0
                df_novos[c] = pd.to_numeric(df_novos[c], errors='coerce').fillna(0.0)
            
            salvar_no_banco(df_novos)
            st.success("Dados salvos na memória!")
            time.sleep(1)
            st.rerun()

# --- 6. VISUALIZAÇÃO LIMPA (SEM JSON) ---
if not df_hist.empty:
    st.divider()
    st.subheader("📂 Painel Geral")
    
    # 1. CRIAÇÃO DA VISUALIZAÇÃO LIMPA
    # Remove colunas técnicas que o cliente não precisa ver
    cols_to_drop = ['json_completo', 'id']
    df_visual = df_hist.drop(columns=cols_to_drop, errors='ignore')

    # Preenche zeros para visualização bonita
    cols_check = ['valor_icms', 'valor_issqn', 'valor_bruto']
    for c in cols_check:
        if c not in df_visual.columns: df_visual[c] = 0.0
        else: df_visual[c] = df_visual[c].fillna(0.0)

    # Reordena as colunas de forma lógica (se existirem)
    ordem_ideal = [
        'data_upload', 'arquivo_origem', 'numero_nota', 'data_emissao',
        'emissor_nome', 'emissor_cnpj', 
        'tomador_nome', 'tomador_cnpj',
        'descricao_item', 'codigo_ncm',
        'valor_bruto', 'valor_liquido',
        'valor_icms', 'valor_ipi', 'valor_icms_st', 
        'valor_issqn', 'retencao_issqn'
    ]
    # Filtra apenas as colunas que realmente estão no banco para não dar erro
    cols_existentes = [c for c in ordem_ideal if c in df_visual.columns]
    df_visual = df_visual[cols_existentes]

    tab1, tab2, tab3 = st.tabs(["📥 Excel Limpo", "📊 Dashboard", "🤖 Análise CFO"])
    
    with tab1:
        st.dataframe(df_visual) # Mostra tabela sem JSON
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_visual.to_excel(writer, index=False) # Baixa Excel sem JSON
        buffer.seek(0)
        
        st.download_button("Baixar Relatório Gerencial (.xlsx)", buffer, "relatorio_opertix.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    with tab2:
        colA, colB, colC = st.columns(3)
        colA.metric("Total ICMS (Produtos)", f"R$ {df_hist['valor_icms'].sum():,.2f}")
        colB.metric("Total ISSQN (Serviços)", f"R$ {df_hist['valor_issqn'].sum():,.2f}")
        
        ipi = df_hist['valor_ipi'].sum() if 'valor_ipi' in df_hist.columns else 0
        st_val = df_hist['valor_icms_st'].sum() if 'valor_icms_st' in df_hist.columns else 0
        colC.metric("Total IPI + ST", f"R$ {(ipi + st_val):,.2f}")
        
        st.write("#### Selecione os Eixos do Gráfico")
        c1, c2, c3 = st.columns(3)
        
        # Usa df_visual para garantir que o JSON não apareça nas opções do gráfico
        idx_x = list(df_visual.columns).index('emissor_nome') if 'emissor_nome' in df_visual.columns else 0
        
        x_axis = c1.selectbox("Eixo X", df_visual.columns, index=idx_x)
        # Filtra apenas colunas numéricas para o Y
        cols_numericas = [c for c in df_visual.columns if df_visual[c].dtype in ['float64', 'int64']]
        y_axis = c2.selectbox("Eixo Y", cols_numericas if cols_numericas else df_visual.columns, index=0)
        chart = c3.selectbox("Tipo", ["Barra", "Pizza", "Linha"])
        
        if chart == "Barra": st.plotly_chart(px.bar(df_visual, x=x_axis, y=y_axis, color=x_axis), use_container_width=True)
        if chart == "Pizza": st.plotly_chart(px.pie(df_visual, values=y_axis, names=x_axis), use_container_width=True)
        if chart == "Linha": st.plotly_chart(px.line(df_visual, x=x_axis, y=y_axis), use_container_width=True)

    with tab3:
        if st.button("🧠 Pedir Análise do CFO"):
            with st.spinner("Analisando histórico..."):
                res = analisar_dados_com_ia(df_hist)
                st.markdown(res)
else:
    st.info("Histórico vazio. Faça upload acima.")
