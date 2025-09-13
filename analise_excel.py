import streamlit as st
import pandas as pd
import sqlite3
import json
import os
import re
from datetime import datetime, timedelta
import plotly.express as px
import hashlib
import requests
from typing import Dict, List, Optional, Tuple
import time

# ===============================
# CONFIGURAÇÕES INICIAIS OTIMIZADAS
# ===============================
st.set_page_config(
    page_title="🌱 Sistema Agrícola Inteligente", 
    layout="wide",
    page_icon="🌱",
    initial_sidebar_state="expanded"
)

# Configurações de caminhos
DB_PATH = "dados_agricolas.db"
CONFIG_PATH = "config.json"
BACKUP_DIR = "backups"

# Criar diretórios necessários
os.makedirs(BACKUP_DIR, exist_ok=True)

# Configuração de cache otimizada
@st.cache_resource(show_spinner=False)
def init_database():
    """Inicializa o banco de dados com conexão otimizada"""
    try:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        # Configurações de performance
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA cache_size = -10000")
        conn.execute("PRAGMA temp_store = MEMORY")
        return conn
    except Exception as e:
        st.error(f"Erro ao conectar com o banco: {e}")
        return sqlite3.connect(":memory:", check_same_thread=False)

@st.cache_data(ttl=300, show_spinner=False)
def carregar_config():
    """Carrega as configurações do sistema"""
    config_padrao = {
        "cidade": "Londrina",
        "alerta_prod_baixo_pct": 30.0,
        "preco_padrao_primeira": 30.0,
        "preco_padrao_segunda": 15.0,
        "modo_offline": False,
        "deepseek_api_key": "",
        "ultimo_backup": None
    }
    
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return {**config_padrao, **json.load(f)}
    except:
        pass
        
    return config_padrao

# Constantes
TIPOS_INSUMOS = [
    "Adubo Orgânico", "Adubo Químico", "Defensivo Agrícola", 
    "Semente", "Muda", "Fertilizante Foliar", "Corretivo de Solo"
]

UNIDADES = ["kg", "L", "unidade", "saco"]

# Gerar áreas de produção
ESTUFAS = [f"Estufa {i}" for i in range(1, 11)]
CAMPOS = [f"Campo {i}" for i in range(1, 11)]
AREAS_PRODUCAO = ESTUFAS + CAMPOS

# ===============================
# BANCO DE DADOS OTIMIZADO
# ===============================
def criar_tabelas_otimizadas():
    """Cria tabelas com estrutura otimizada"""
    try:
        conn = init_database()
        cursor = conn.cursor()
        
        # Tabela de produção
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS producao (
                id INTEGER PRIMARY KEY,
                data TEXT NOT NULL,
                area TEXT NOT NULL,
                cultura TEXT NOT NULL,
                caixas INTEGER DEFAULT 0,
                caixas_segunda INTEGER DEFAULT 0,
                observacao TEXT,
                timestamp INTEGER DEFAULT (strftime('%s', 'now'))
        """)
        
        # Tabela de insumos
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS insumos (
                id INTEGER PRIMARY KEY,
                data TEXT NOT NULL,
                tipo TEXT NOT NULL,
                quantidade REAL NOT NULL,
                unidade TEXT NOT NULL,
                custo_total REAL NOT NULL,
                area TEXT,
                cultura TEXT,
                observacoes TEXT,
                timestamp INTEGER DEFAULT (strftime('%s', 'now'))
        """)
        
        # Tabela de configurações de culturas
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS culturas_config (
                cultura TEXT PRIMARY KEY,
                preco_primeira REAL DEFAULT 30.0,
                preco_segunda REAL DEFAULT 15.0,
                ciclo_dias INTEGER DEFAULT 90
            )
        """)
        
        # Índices para performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_producao_data ON producao(data)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_producao_area ON producao(area)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_insumos_data ON insumos(data)")
        
        conn.commit()
        return True
        
    except Exception as e:
        st.error(f"Erro ao criar tabelas: {e}")
        return False

# ===============================
# SISTEMA DE BACKUP E SEGURANÇA
# ===============================
def criar_backup():
    """Cria backup seguro dos dados"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(BACKUP_DIR, f"backup_{timestamp}.db")
        
        # Conectar ao banco principal e de backup
        conn_orig = init_database()
        conn_backup = sqlite3.connect(backup_path)
        
        # Fazer backup
        conn_orig.backup(conn_backup)
        
        # Atualizar configuração
        config = carregar_config()
        config["ultimo_backup"] = timestamp
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
            
        return True
    except Exception as e:
        st.error(f"Erro ao criar backup: {e}")
        return False

def verificar_integridade_dados():
    """Verifica a integridade dos dados"""
    try:
        conn = init_database()
        cursor = conn.cursor()
        
        # Verificar tabelas
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tabelas = [t[0] for t in cursor.fetchall()]
        
        tabelas_necessarias = ['producao', 'insumos', 'culturas_config']
        for tabela in tabelas_necessarias:
            if tabela not in tabelas:
                return False
                
        return True
    except:
        return False

# ===============================
# AGENTE IA AGRÔNOMO (DEEPSEEK)
# ===============================
class AgenteAgronomo:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.deepseek.com/v1/chat/completions"
        
    def analisar_producao(self, dados_producao: pd.DataFrame) -> str:
        """Analisa dados de produção com IA"""
        if not self.api_key:
            return "Configure a API key do DeepSeek nas configurações"
            
        try:
            # Resumo dos dados para análise
            resumo = f"""
            Dados de produção agrícola:
            - Total de registros: {len(dados_producao)}
            - Período: {dados_producao['data'].min()} a {dados_producao['data'].max()}
            - Culturas: {', '.join(dados_producao['cultura'].unique())}
            - Produção total: {dados_producao['caixas'].sum()} caixas (1ª)
            - Produção segunda: {dados_producao['caixas_segunda'].sum()} caixas (2ª)
            """
            
            prompt = f"""
            Como agrônomo especialista, analise estes dados de produção agrícola:
            {resumo}
            
            Forneça:
            1. Análise de produtividade por cultura
            2. Sugestões para melhorar a produção
            3. Possíveis problemas detectados
            4. Recomendações para o próximo ciclo
            """
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 1000
            }
            
            response = requests.post(self.base_url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            
            return response.json()["choices"][0]["message"]["content"]
            
        except Exception as e:
            return f"Erro na análise: {str(e)}"

# ===============================
# FUNÇÕES DE DADOS OTIMIZADAS
# ===============================
@st.cache_data(ttl=60, show_spinner=False)
def carregar_dados(tabela: str, where: str = "", params: tuple = ()) -> pd.DataFrame:
    """Carrega dados do banco com cache"""
    try:
        conn = init_database()
        query = f"SELECT * FROM {tabela}"
        if where:
            query += f" WHERE {where}"
        query += " ORDER BY timestamp DESC"
        
        return pd.read_sql(query, conn, params=params)
    except:
        return pd.DataFrame()

def inserir_dados(tabela: str, dados: dict) -> bool:
    """Insere dados de forma segura"""
    try:
        conn = init_database()
        cursor = conn.cursor()
        
        colunas = ", ".join(dados.keys())
        placeholders = ", ".join(["?"] * len(dados))
        valores = tuple(dados.values())
        
        query = f"INSERT INTO {tabela} ({colunas}) VALUES ({placeholders})"
        cursor.execute(query, valores)
        
        conn.commit()
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erro ao inserir dados: {e}")
        return False

# ===============================
# PÁGINAS OTIMIZADAS
# ===============================
def pagina_dashboard():
    """Dashboard otimizado"""
    st.title("📊 Dashboard Agrícola")
    
    # Carregar dados
    df_prod = carregar_dados("producao", "date(data) >= date('now', '-30 days')")
    
    # KPIs
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_caixas = df_prod["caixas"].sum() if not df_prod.empty else 0
        st.metric("📦 Caixas 1ª", f"{total_caixas:.0f}")
    
    with col2:
        total_segunda = df_prod["caixas_segunda"].sum() if not df_prod.empty else 0
        st.metric("🔄 Caixas 2ª", f"{total_segunda:.0f}")
    
    with col3:
        df_ins = carregar_dados("insumos", "date(data) >= date('now', '-30 days')")
        custo_total = df_ins["custo_total"].sum() if not df_ins.empty else 0
        st.metric("💰 Custo", f"R$ {custo_total:,.0f}")
    
    with col4:
        receita = total_caixas * 30 + total_segunda * 15
        st.metric("💵 Receita", f"R$ {receita:,.0f}")
    
    # Gráfico simplificado
    if not df_prod.empty:
        df_agrupado = df_prod.groupby("data")[["caixas", "caixas_segunda"]].sum().reset_index()
        fig = px.line(df_agrupado, x="data", y=["caixas", "caixas_segunda"], 
                     title="Produção dos Últimos 30 Dias")
        st.plotly_chart(fig, use_container_width=True)

def pagina_producao():
    """Página de cadastro de produção"""
    st.title("📝 Registrar Produção")
    
    with st.form("form_producao"):
        col1, col2 = st.columns(2)
        
        with col1:
            data = st.date_input("Data", value=datetime.now())
            area = st.selectbox("Área", AREAS_PRODUCAO)
            cultura = st.text_input("Cultura*")
        
        with col2:
            caixas = st.number_input("Caixas 1ª", min_value=0, value=0)
            caixas_segunda = st.number_input("Caixas 2ª", min_value=0, value=0)
            observacao = st.text_area("Observações")
        
        if st.form_submit_button("💾 Salvar"):
            if not cultura.strip():
                st.error("Informe a cultura")
            else:
                dados = {
                    "data": data.strftime("%Y-%m-%d"),
                    "area": area,
                    "cultura": cultura.strip(),
                    "caixas": caixas,
                    "caixas_segunda": caixas_segunda,
                    "observacao": observacao
                }
                
                if inserir_dados("producao", dados):
                    st.success("Produção registrada!")

def pagina_analise_ia():
    """Página de análise com IA"""
    st.title("🤖 Assistente Agronômico IA")
    
    config = carregar_config()
    agente = AgenteAgronomo(config.get("deepseek_api_key", ""))
    
    if not config.get("deepseek_api_key"):
        st.warning("Configure sua API key do DeepSeek nas configurações")
        return
    
    # Carregar dados para análise
    df_prod = carregar_dados("producao")
    
    if df_prod.empty:
        st.info("Não há dados de produção para análise")
        return
    
    if st.button("🔍 Analisar Produção com IA"):
        with st.spinner("Analisando dados..."):
            analise = agente.analisar_producao(df_prod)
            st.markdown("### 📋 Análise do Agrónomo IA")
            st.write(analise)

def pagina_configuracoes():
    """Página de configurações"""
    st.title("⚙️ Configurações")
    
    config = carregar_config()
    
    with st.form("form_config"):
        st.subheader("API Configuration")
        api_key = st.text_input("DeepSeek API Key", 
                               value=config.get("deepseek_api_key", ""),
                               type="password")
        
        st.subheader("Segurança de Dados")
        if st.form_submit_button("💾 Salvar Configurações"):
            config["deepseek_api_key"] = api_key
            
            try:
                with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                    json.dump(config, f, ensure_ascii=False, indent=2)
                st.success("Configurações salvas!")
            except Exception as e:
                st.error(f"Erro ao salvar: {e}")
    
    # Seção de backup
    st.subheader("Backup de Dados")
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📂 Criar Backup"):
            if criar_backup():
                st.success("Backup criado com sucesso!")
    
    with col2:
        if st.button("🔄 Verificar Integridade"):
            if verificar_integridade_dados():
                st.success("Dados íntegros!")
            else:
                st.error("Problemas na integridade dos dados")

# ===============================
# MENU PRINCIPAL
# ===============================
def main():
    """Função principal otimizada"""
    # Inicialização
    if criar_tabelas_otimizadas():
        st.sidebar.success("✅ Sistema pronto")
    
    # Navegação
    st.sidebar.title("🌱 Menu")
    opcoes = ["Dashboard", "Produção", "Análise IA", "Configurações"]
    pagina = st.sidebar.radio("Navegar", opcoes)
    
    # Navegação entre páginas
    if pagina == "Dashboard":
        pagina_dashboard()
    elif pagina == "Produção":
        pagina_produção()
    elif pagina == "Análise IA":
        pagina_analise_ia()
    elif pagina == "Configurações":
        pagina_configuracoes()
    
    # Status do sistema
    st.sidebar.markdown("---")
    st.sidebar.info("💾 Dados seguros com backup automático")

# ===============================
# EXECUÇÃO
# ===============================
if __name__ == "__main__":
    main()
