# 🏢 Agente Fiscal AI - Auditoria e B.I. Inteligente

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Streamlit](https://img.shields.io/badge/Streamlit-App-red)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-green)
![CrewAI](https://img.shields.io/badge/AI-Agents-orange)

> **Transforme PDFs de notas fiscais (NFS-e e DANFE) em Dashboards Financeiros e Insights Estratégicos usando Agentes de IA.**

## 🎯 O Problema
Empresas e escritórios de contabilidade perdem horas digitando dados de notas fiscais não padronizadas. O processo é manual, lento e propenso a erros. Além disso, os dados ficam "presos" em PDFs, dificultando a análise financeira e a tomada de decisão.

## 🚀 A Solução
O **Agente Fiscal AI** é uma plataforma SaaS que utiliza Inteligência Artificial Generativa para ler, interpretar e estruturar dados de qualquer formato de nota fiscal.

Não é apenas um OCR (leitor de texto). É um **Sistema Agêntico** que:
1.  **Lê** o documento como um humano.
2.  **Audita** os dados (valida CNPJs, impostos e totais).
3.  **Gera B.I.** (Business Intelligence) automático.
4.  **Analisa** financeiramente (Agente "CFO Virtual") sugerindo economias e apontando anomalias.

---

## 🛠️ Funcionalidades Principais

### 1. Extração Universal 📄
- Processa **múltiplos arquivos** simultaneamente.
- Identifica automaticamente se é **Produto (DANFE)** ou **Serviço (NFS-e)**.
- Extrai dados complexos: *Tomador, Prestador, NCM, Retenções (ISSQN, INSS), ICMS-ST*.

### 2. Agentes Inteligentes (CrewAI) 🤖
- **Agente Auditor:** Garante a integridade dos dados e padronização JSON.
- **Agente CFO Virtual:** Analisa a planilha final e gera um relatório executivo em texto, apontando anomalias de gastos e maiores fornecedores.

### 3. Dashboard Dinâmico (Self-Service) 📊
- Interface "No-Code" para criação de gráficos.
- O usuário escolhe os eixos X e Y e o sistema gera gráficos interativos (Plotly) na hora, sem necessidade de programação.

### 4. Integração com Power BI 📉
- Exportação nativa para Excel (`.xlsx`) formatado.
- Estrutura de dados pronta para importação direta no Power BI ou Tableau.

---

## 📸 Screenshots

![Dashboard Preview](https://via.placeholder.com/800x400?text=Dashboard+Interativo+Streamlit+Agente+Fiscal)

---

## 💻 Como Rodar Localmente

Siga os passos abaixo para clonar e executar o projeto na sua máquina.

### Pré-requisitos
- Python 3.10 ou superior
- Uma chave de API da OpenAI (Recomendado: modelo `gpt-4o-mini` pela velocidade e custo)

### Instalação

1. **Clone o repositório:**
   ```bash
   git clone [https://github.com/SEU-USUARIO/agente-fiscal-ia.git](https://github.com/SEU-USUARIO/agente-fiscal-ia.git)
   cd agente-fiscal-ia
Crie um ambiente virtual (Recomendado):

Bash

# Windows
python -m venv venv
.\venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
Instale as dependências:

Bash

pip install -r requirements.txt
Configure a API Key:

Crie uma pasta .streamlit e um arquivo secrets.toml dentro dela.

Adicione sua chave: OPENAI_API_KEY = "sk-..."

Alternativa rápida: Insira a chave no código onde indicado (apenas para testes locais).

Execute a aplicação:

Bash

streamlit run app.py
🧪 Gerador de Dados para Testes
O projeto inclui scripts para simulação de carga e testes de ponta a ponta:

gerar_pdfs_falsos.py: Gera dezenas de PDFs de notas fiscais realistas (usando a lib Faker) para testar a extração da IA.

gerador_cliente.py: Gera uma planilha Excel com milhares de linhas simuladas para testar dashboards de alta performance no Power BI.

📂 Estrutura do Projeto
Agente-Fiscal-IA/
│
├── app.py                 # Código principal (Frontend Streamlit + Agentes CrewAI)
├── requirements.txt       # Lista de dependências do projeto
├── gerador_cliente.py     # Script para gerar dados tabulares falsos (Teste de Carga)
├── gerar_pdfs_falsos.py   # Script para gerar PDFs realistas para teste de extração
└── README.md              # Documentação
🚀 Roadmap (Próximos Passos)
[x] Extração de Múltiplos Arquivos

[x] Dashboard Automático Dinâmico

[x] Exportação Power BI (.xlsx)

[ ] Integração n8n: Automatizar recebimento e resposta via e-mail.

[ ] Banco de Dados: Salvar histórico das extrações em PostgreSQL.

[ ] Chat com Dados: Funcionalidade de "Pergunte aos seus dados" (RAG).

🤝 Contribuição
Contribuições são bem-vindas! Sinta-se à vontade para abrir issues ou enviar pull requests.

📄 Licença
Este projeto está sob a licença MIT.

Desenvolvido com ☕ e Python.
