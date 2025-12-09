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
    # Se for rodar local, coloque sua chave aqui
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
    """Cria os agentes especialistas em extração e tributação."""
    extrator = Agent(
        role='Auditor Tributário Sênior',
        goal='Extrair dados detalhados distinguindo entre Comércio (ICMS) e Serviço (ISS).',
        backstory='Especialista em legislação. Você sabe que DANFE gera ICMS/IPI e NFS-e gera ISSQN. Você extrai Tomador, NCM e impostos corretamente.',
        verbose=False, allow_delegation=False, llm=MODELO_LLM
    )
    auditor = Agent(
        role='Engenheiro de Dados',
        goal='Padronizar JSON e corrigir tipos numéricos.',
        backstory='Garante que números sejam float e campos vazios sejam 0.0.',
        verbose=False, allow_delegation=False, llm=MODELO_LLM
    )
    return extrator, auditor

def analisar_dados_com_ia(df_json):
    """Agente CFO para gerar insights."""
    analista = Agent(
        role='CFO Virtual',
        goal='Gerar insights financeiros e tributários.',
        backstory='Diretor financeiro que analisa custos, carga tributária (ICMS vs ISS) e anomalias.',
        verbose=True, allow_delegation=False, llm=MODELO_LLM
    )
    task_analise = Task(
        description=f"Analise estes dados financeiros:\n{df_json}\n\nEscreva um relatório executivo (Markdown) citando o maior fornecedor, total gasto em Serviços vs Produtos e sugestões de economia.",
        expected_output="Relatório em Markdown.",
        agent=analista
    )
    return Crew(agents=[analista], tasks=[task_analise]).kickoff()

# --- 3. INTERFACE ---
st.title("🏢 Agente Fiscal: Extração Universal + BI")
st.markdown("Extrai Tomador, NCM, e separa automaticamente **ICMS (Produtos)** de **ISSQN (Serviços)**.")

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
                
                # --- PROMPT ATUALIZADO (LÓGICA DA CONTADORA) ---
                task_ex = Task(
                    description=f"""
                    Analise o texto da nota fiscal:
                    ---
                    {texto}
                    ---
                    
                    IDENTIFIQUE O TIPO E EXTRAIA:
                    
                    1. TIPO DE NOTA:
                       - É Venda/Comércio (DANFE)? Foco em ICMS e IPI.
                       - É Serviço (NFS-e)? Foco em ISSQN.
                    
                    2. DADOS CADASTRAIS (Sempre extrair):
                       - Emissor (Nome, CNPJ)
                       - Tomador (Nome, CNPJ) - Muito importante!
                       - Número Nota, Data Emissão
                       - Descrição do Item/Serviço
                       - Código NCM ou Código de Serviço
                    
                    3. VALORES FINANCEIROS:
                       - Valor Bruto (Total da Nota)
                       - Valor Líquido (A pagar)
                    
                    4. IMPOSTOS (Preencha conforme o tipo, o resto deixe zero):
                       - Valor ICMS (Só se for produto)
                       - Valor IPI (Só se for produto)
                       - Valor ICMS-ST (Substituição Tributária)
                       - Valor ISSQN (Só se for serviço)
                       - Retenção de ISSQN (Se houver)
                    """,
                    expected_output="Lista detalhada de dados fiscais.", agent=extrator
                )
                
                # --- JSON PADRONIZADO COM CAMPOS SEPARADOS ---
                task_json = Task(
                    description="""
                    Gere JSON válido com estas chaves exatas (use 0.0 se não encontrar): 
                    {
                        "numero_nota": "string", 
                        "data_emissao": "string", 
                        "emissor_nome": "string", 
                        "emissor_cnpj": "string", 
                        "tomador_nome": "string", 
                        "tomador_cnpj": "string", 
                        "descricao_item": "string", 
                        "codigo_ncm": "string", 
                        "valor_bruto": float, 
                        "valor_liquido": float, 
                        "valor_icms": float,
                        "valor_ipi": float,
                        "valor_icms_st": float,
                        "valor_issqn": float,
                        "retencao_issqn": float
                    }
                    """,
                    expected_output="JSON válido.", agent=auditor
                )
                
                crew = Crew(agents=[extrator, auditor], tasks=[task_ex, task_json])
                
                try:
                    res = crew.kickoff()
                    # Limpeza de segurança
                    clean_res = str(res).replace("```json", "").replace("```", "").strip()
                    if clean_res.startswith("json"): clean_res = clean_res[4:]
                    
                    dados = json.loads(clean_res)
                    dados['arquivo_origem'] = arquivo.name
                    resultados.append(dados)
                    
                    # Feedback visual inteligente
                    tipo = "📦 Produto" if dados.get('valor_icms', 0) > 0 else "🛠️ Serviço"
                    st.success(f"✅ {arquivo.name} ({tipo}): R$ {dados.get('valor_bruto', 0)}")
                    
                except Exception as e:
                    st.error(f"Falha em {arquivo.name}: {e}")

        st.session_state.dados_processados = resultados
        status.success("Auditoria Concluída!")

# --- 5. VISUALIZAÇÃO E DOWNLOAD ---
if st.session_state.dados_processados:
    df = pd.DataFrame(st.session_state.dados_processados)
    
    # Tratamento de Tipos para Gráficos
    cols_num = ['valor_bruto', 'valor_liquido', 'valor_icms', 'valor_ipi', 'valor_icms_st', 'valor_issqn', 'retencao_issqn']
    for col in cols_num:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
    
    # Abas (Mantendo idêntico ao anterior)
    tab1, tab2, tab3 = st.tabs(["📥 Excel BI", "📊 Dashboard Dinâmico", "🤖 Análise CFO"])
    
    with tab1:
        st.dataframe(df)
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        buffer.seek(0)
        st.download_button("Baixar Excel (.xlsx) para Power BI", buffer, "dados_fiscais_master.xlsx", 
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")

    with tab2:
        st.write("### Monte seu Gráfico")
        colA, colB, colC = st.columns(3)
        # Seletores mantidos, mas agora com as novas colunas de impostos disponíveis
        with colA: x_axis = st.selectbox("Eixo X", df.columns, index=2) 
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
