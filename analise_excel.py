import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import requests
import urllib.parse
import json
import os
import re
import time
from io import BytesIO
from datetime import date, datetime, timedelta
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import hashlib
import zipfile
import base64
from pathlib import Path

# ===============================
# CONFIGURAÇÕES INICIAIS
# ===============================
st.set_page_config(
    page_title="🌱 Sistema Integrado de Gestão Agrícola", 
    layout="wide",
    page_icon="🌱",
    initial_sidebar_state="expanded"
)

# Configurações de caminhos para funcionar no Streamlit Cloud
DB_PATH = "dados_sitio.db"
CONFIG_PATH = "config.json"

# Otimização: Cache para melhor performance
@st.cache_resource
def init_database():
    """Inicializa o banco de dados com conexão otimizada"""
    try:
        # Garantir que o diretório existe
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        
        # Configurar para melhor performance
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA cache_size = -10000")
        
        return conn
    except Exception as e:
        st.error(f"Erro ao conectar com o banco de dados: {e}")
        # Fallback: criar conexão em memória se não conseguir com arquivo
        return sqlite3.connect(":memory:", check_same_thread=False)

@st.cache_data(ttl=300)
def carregar_config():
    """Carrega as configurações do sistema com cache"""
    try:
        if not os.path.exists(CONFIG_PATH):
            cfg = {
                "cidade": "Londrina",
                "alerta_pct_segunda": 25.0,
                "alerta_prod_baixo_pct": 30.0,
                "preco_padrao_primeira": 30.0,
                "preco_padrao_segunda": 15.0,
                "custo_medio_insumos": {
                    "Adubo Orgânico": 2.5, "Adubo Químico": 4.0, "Defensivo Agrícola": 35.0,
                    "Semente": 0.5, "Muda": 1.2, "Fertilizante Foliar": 15.0, "Corretivo de Solo": 1.8
                },
                "ultimo_backup": None,
                "modo_offline": False
            }
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=4)
            return cfg
        
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Erro ao carregar configurações: {e}")
        # Retornar configuração padrão em caso de erro
        return {
            "cidade": "Londrina",
            "alerta_pct_segunda": 25.0,
            "alerta_prod_baixo_pct": 30.0,
            "preco_padrao_primeira": 30.0,
            "preco_padrao_segunda": 15.0,
            "custo_medio_insumos": {
                "Adubo Orgânico": 2.5, "Adubo Químico": 4.0, "Defensivo Agrícola": 35.0,
                "Semente": 0.5, "Muda": 1.2, "Fertilizante Foliar": 15.0, "Corretivo de Solo": 1.8
            },
            "ultimo_backup": None,
            "modo_offline": False
        }

# Constantes
TIPOS_INSUMOS = [
    "Adubo Orgânico", "Adubo Químico", "Defensivo Agrícola", 
    "Semente", "Muda", "Fertilizante Foliar", 
    "Corretivo de Solo", "Insumo para Irrigação", "Outros"
]

UNIDADES = ["kg", "g", "L", "mL", "unidade", "saco", "caixa", "pacote"]

# Gerar estufas e campos com formatação padronizada
ESTUFAS = [f"Estufa {i}" for i in range(1, 31)]
CAMPOS = [f"Campo {i}" for i in range(1, 31)]
AREAS_PRODUCAO = ESTUFAS + CAMPOS

# Cores personalizadas para o tema escuro
colors = {
    'primary': '#2E8B57',  # Verde agrícola
    'secondary': '#3CB371',
    'accent': '#FFD700',   # Dourado
    'background': '#1A1A1A',
    'text': '#FFFFFF',
    'success': '#32CD32',
    'warning': '#FFA500',
    'danger': '#DC143C'
}

# Aplicar estilo CSS personalizado
st.markdown(f"""
<style>
    .main .block-container {{
        padding-top: 2rem;
        padding-bottom: 2rem;
        background-color: {colors['background']};
        color: {colors['text']};
    }}
    .stButton>button {{
        background-color: {colors['primary']};
        color: white;
        border: none;
        border-radius: 4px;
        padding: 0.5rem 1rem;
    }}
    .stButton>button:hover {{
        background-color: {colors['secondary']};
        color: white;
    }}
    .css-1d391kg {{
        background-color: {colors['background']};
    }}
    h1, h2, h3, h4, h5, h6 {{
        color: {colors['primary']};
    }}
    .stMetric {{
        background-color: #2A2A2A;
        padding: 15px;
        border-radius: 10px;
        border-left: 4px solid {colors['primary']};
    }}
    .stAlert {{
        border-radius: 10px;
    }}
    /* Otimização para mobile */
    @media (max-width: 768px) {{
        .block-container {{
            padding: 1rem;
        }}
        .stButton>button {{
            width: 100%;
            margin-bottom: 0.5rem;
        }}
    }}
</style>
""", unsafe_allow_html=True)

# ===============================
# BANCO DE DADOS OTIMIZADO - CORRIGIDO
# ===============================
def criar_tabelas_otimizadas():
    """Cria todas as tabelas necessárias no banco de dados com índices para performance"""
    try:
        conn = init_database()
        cursor = conn.cursor()
        
        tabelas = [
            """
            CREATE TABLE IF NOT EXISTS producao (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT, area TEXT, cultura TEXT, caixas INTEGER,
                caixas_segunda INTEGER, temperatura REAL, umidade REAL,
                chuva REAL, observacao TEXT,
                timestamp INTEGER DEFAULT (strftime('%s', 'now')),
                sync_status INTEGER DEFAULT 0
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS insumos (
                id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, area TEXT,
                cultura TEXT, tipo TEXT, quantidade REAL, unidade TEXT,
                custo_unitario REAL, custo_total REAL, fornecedor TEXT,
                lote TEXT, observacoes TEXT,
                timestamp INTEGER DEFAULT (strftime('%s', 'now')),
                sync_status INTEGER DEFAULT 0
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS custos (
                id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, tipo TEXT,
                descricao TEXT, valor REAL, area TEXT, observacoes TEXT,
                timestamp INTEGER DEFAULT (strftime('%s', 'now')),
                sync_status INTEGER DEFAULT 0
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS precos_culturas (
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                cultura TEXT UNIQUE,
                preco_primeira REAL,
                preco_segunda REAL,
                timestamp INTEGER DEFAULT (strftime('%s', 'now'))
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS plantios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_plantio TEXT,
                area TEXT,
                cultura TEXT,
                quantidade_mudas INTEGER,
                espacamento TEXT,
                estimativa_colheita REAL,
                data_estimada_colheita TEXT,
                observacoes TEXT,
                timestamp INTEGER DEFAULT (strftime('%s', 'now')),
                sync_status INTEGER DEFAULT 0
            )
            """
        ]
        
        for tabela in tabelas:
            try:
                cursor.execute(tabela)
            except Exception as e:
                st.warning(f"Erro ao criar tabela: {e}")
        
        # Criar índices para melhor performance
        indices = [
            "CREATE INDEX IF NOT EXISTS idx_producao_data ON producao(data)",
            "CREATE INDEX IF NOT EXISTS idx_producao_area ON producao(area)",
            "CREATE INDEX IF NOT EXISTS idx_producao_cultura ON producao(cultura)",
            "CREATE INDEX IF NOT EXISTS idx_insumos_data ON insumos(data)",
            "CREATE INDEX IF NOT EXISTS idx_insumos_tipo ON insumos(tipo)",
            "CREATE INDEX IF NOT EXISTS idx_insumos_cultura ON insumos(cultura)"
        ]
        
        for indice in indices:
            try:
                cursor.execute(indice)
            except Exception as e:
                st.warning(f"Erro ao criar índice: {e}")
        
        conn.commit()
        return True
        
    except Exception as e:
        st.error(f"Erro crítico ao criar tabelas: {e}")
        return False
    finally:
        try:
            conn.close()
        except:
            pass

def normalizar_nome_area(nome):
    """Normaliza o nome da área para formato padrão"""
    if not nome or pd.isna(nome):
        return ""
    
    nome = str(nome).strip()
    
    # Padronizar Estufa
    if re.match(r'estufa\s*\d+', nome.lower()):
        numero = re.search(r'\d+', nome).group()
        return f"Estufa {numero}"
    
    # Padronizar Campo
    if re.match(r'campo\s*\d+', nome.lower()):
        numero = re.search(r'\d+', nome).group()
        return f"Campo {numero}"
    
    return nome

def normalizar_colunas(df):
    """Normaliza os nomes das colunas do DataFrame"""
    df = df.copy()
    col_map = {
        "Estufa": "area", "Área": "area", "Produção": "caixas", 
        "Primeira": "caixas", "Segunda": "caixas_segunda", 
        "Qtd": "caixas", "Quantidade": "caixas", "Data": "data",
        "Observação": "observacao", "Observacoes": "observacao", "Obs": "observacao",
        "Temperatura": "temperatura", "Umidade": "umidade", "Chuva": "chuva"
    }
    df.rename(columns={c: col_map.get(c, c) for c in df.columns}, inplace=True)
    
    if "data" in df.columns: 
        df["data"] = pd.to_datetime(df["data"], errors="coerce").dt.strftime('%Y-%m-%d')
    
    for col in ["caixas", "caixas_segunda", "temperatura", "umidade", "chuva", "observacao"]:
        if col not in df.columns: 
            df[col] = 0 if col != "observacao" else ""
    
    for col in ["area", "cultura"]:
        if col not in df.columns: 
            df[col] = ""
    
    # Normalizar nomes de áreas
    if "area" in df.columns:
        df["area"] = df["area"].apply(normalizar_nome_area)
    
    return df

@st.cache_data(ttl=60, max_entries=10)
def carregar_tabela_otimizada(nome_tabela, where_clause="", params=()):
    """Carrega dados de uma tabela do banco com opções de filtro"""
    try:
        conn = init_database()
        
        # Para grandes volumes de dados, usar paginação ou filtros
        query = f"SELECT * FROM {nome_tabela}"
        if where_clause:
            query += f" WHERE {where_clause}"
        
        # Ordenar por timestamp para garantir consistência
        query += " ORDER BY timestamp DESC"
        
        df = pd.read_sql(query, conn, params=params)
        return df
        
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")
        return pd.DataFrame()
    finally:
        try:
            conn.close()
        except:
            pass

def inserir_producao(data, area, cultura, caixas, caixas_segunda, temperatura, umidade, chuva, observacao):
    """Insere dados de produção de forma segura"""
    try:
        conn = init_database()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO producao (data, area, cultura, caixas, caixas_segunda, 
                                temperatura, umidade, chuva, observacao)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (data.strftime('%Y-%m-%d'), area, cultura, caixas, caixas_segunda,
             temperatura, umidade, chuva, observacao))
        
        conn.commit()
        return True
        
    except Exception as e:
        st.error(f"Erro ao inserir produção: {e}")
        return False
    finally:
        try:
            conn.close()
        except:
            pass

def excluir_linha(nome_tabela, row_id):
    """Exclui uma linha específica do banco com marcação de sync"""
    try:
        conn = init_database()
        cursor = conn.cursor()
        
        # Marcar para exclusão em sync (soft delete)
        cursor.execute(f"UPDATE {nome_tabela} SET sync_status = -1 WHERE id=?", (row_id,))
        
        conn.commit()
        return True
        
    except Exception as e:
        st.error(f"Erro ao excluir linha: {e}")
        return False
    finally:
        try:
            conn.close()
        except:
            pass

@st.cache_data(ttl=3600)
def carregar_precos_culturas():
    """Carrega os preços das culturas do banco de dados"""
    try:
        conn = init_database()
        df = pd.read_sql("SELECT * FROM precos_culturas", conn)
        
        precos_dict = {}
        for _, row in df.iterrows():
            precos_dict[row['cultura']] = {
                'preco_primeira': row['preco_primeira'],
                'preco_segunda': row['preco_segunda']
            }
        
        return precos_dict
        
    except Exception as e:
        st.error(f"Erro ao carregar preços: {e}")
        return {}
    finally:
        try:
            conn.close()
        except:
            pass

# ===============================
# FUNÇÕES UTILITÁRIAS OTIMIZADAS
# ===============================
@st.cache_data(ttl=300)
def buscar_clima(cidade):
    """Busca dados climáticos da API com tratamento de erro melhorado"""
    try:
        # Verificar modo offline
        config = carregar_config()
        if config.get("modo_offline", False):
            return None, None
            
        city_encoded = urllib.parse.quote(cidade)
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city_encoded}&appid=eef20bca4e6fb1ff14a81a3171de5cec&units=metric&lang=pt_br"
        r = requests.get(url, timeout=10)
        data = r.json()
        
        if r.status_code != 200: 
            return None, None
        
        atual = {
            "temp": float(data["main"]["temp"]),
            "umidade": float(data["main"]["humidity"]),
            "chuva": float(data.get("rain", {}).get("1h", 0) or 0.0)
        }
        
        return atual, pd.DataFrame()
        
    except Exception as e:
        st.warning(f"Erro ao buscar clima: {e}")
        return None, None

# ===============================
# PÁGINAS PRINCIPAIS OTIMIZADAS
# ===============================
def pagina_dashboard_otimizada():
    """Dashboard otimizado para performance"""
    st.title("🌱 Dashboard de Produção")
    
    # Carregar dados com filtro de período (últimos 30 dias por padrão para performance)
    try:
        data_limite = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        df_prod = carregar_tabela_otimizada("producao", "data >= ?", (data_limite,))
        df_ins = carregar_tabela_otimizada("insumos", "data >= ?", (data_limite,))
    except:
        df_prod = pd.DataFrame()
        df_ins = pd.DataFrame()
    
    # KPIs principais
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        total_caixas = df_prod["caixas"].sum() if not df_prod.empty else 0
        st.metric("📦 Caixas 1ª", f"{total_caixas:.0f}")
    
    with col2:
        total_segunda = df_prod["caixas_segunda"].sum() if not df_prod.empty else 0
        st.metric("🔄 Caixas 2ª", f"{total_segunda:.0f}")
    
    with col3:
        total_insumos = df_ins["custo_total"].sum() if not df_ins.empty else 0
        st.metric("💰 Custo", f"R$ {total_insumos:,.0f}")
    
    with col4:
        receita_total = total_caixas * 30 + total_segunda * 15  # Simplificado
        st.metric("💵 Receita", f"R$ {receita_total:,.0f}")
    
    with col5:
        lucro_total = receita_total - total_insumos
        st.metric("📊 Lucro", f"R$ {lucro_total:,.0f}")
    
    # Gráficos simplificados
    if not df_prod.empty:
        st.subheader("📈 Produção Recente")
        
        # Últimos 7 dias para performance
        ultimos_7_dias = df_prod.tail(7) if len(df_prod) > 7 else df_prod
        
        if not ultimos_7_dias.empty:
            fig = px.bar(ultimos_7_dias, x='data', y=['caixas', 'caixas_segunda'], 
                         title='Produção dos Últimos Dias', barmode='group')
            st.plotly_chart(fig, use_container_width=True)
    
    # Últimos registros
    st.subheader("📋 Últimos Registros")
    if not df_prod.empty:
        st.dataframe(df_prod[['data', 'area', 'cultura', 'caixas', 'caixas_segunda']].head(5), 
                    use_container_width=True)

def pagina_cadastro_producao():
    """Página de cadastro de produção com validação"""
    st.title("📝 Cadastro de Produção")
    
    with st.form("form_producao", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            data = st.date_input("Data", value=datetime.now())
            area = st.selectbox("Área", options=AREAS_PRODUCAO)
            cultura = st.text_input("Cultura")
        
        with col2:
            caixas = st.number_input("Caixas 1ª", min_value=0, value=0)
            caixas_segunda = st.number_input("Caixas 2ª", min_value=0, value=0)
            observacao = st.text_area("Observações")
        
        # Dados climáticos
        st.subheader("🌤️ Dados Climáticos")
        col_clima1, col_clima2, col_clima3 = st.columns(3)
        with col_clima1:
            temperatura = st.number_input("Temp. (°C)", value=25.0)
        with col_clima2:
            umidade = st.number_input("Umidade (%)", value=65.0)
        with col_clima3:
            chuva = st.number_input("Chuva (mm)", value=0.0)
        
        if st.form_submit_button("💾 Salvar Produção"):
            if not cultura.strip():
                st.error("Informe a cultura")
            else:
                sucesso = inserir_producao(data, area, cultura, caixas, caixas_segunda, 
                                         temperatura, umidade, chuva, observacao)
                if sucesso:
                    st.success("Produção registrada com sucesso!")
                    # Limpar cache para atualizar visualizações
                    carregar_tabela_otimizada.clear()

def pagina_configuracoes():
    """Página de configurações do sistema"""
    st.title("⚙️ Configurações")
    
    config = carregar_config()
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Preferências")
        cidade = st.text_input("Cidade para clima", value=config.get("cidade", "Londrina"))
        modo_offline = st.checkbox("Modo offline", value=config.get("modo_offline", False))
        
        if st.button("Salvar Configurações"):
            config["cidade"] = cidade
            config["modo_offline"] = modo_offline
            try:
                with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                    json.dump(config, f, ensure_ascii=False, indent=4)
                st.success("Configurações salvas!")
            except Exception as e:
                st.error(f"Erro ao salvar: {e}")
    
    with col2:
        st.subheader("Manutenção")
        if st.button("Otimizar Banco"):
            try:
                conn = init_database()
                conn.execute("VACUUM")
                conn.close()
                st.success("Banco otimizado!")
            except Exception as e:
                st.error(f"Erro: {e}")
                
        if st.button("Limpar Cache"):
            carregar_tabela_otimizada.clear()
            carregar_config.clear()
            carregar_precos_culturas.clear()
            st.success("Cache limpo!")

# ===============================
# MENU PRINCIPAL OTIMIZADO
# ===============================
def main():
    """Função principal otimizada"""
    # Inicialização segura
    if criar_tabelas_otimizadas():
        st.sidebar.success("✅ Sistema inicializado")
    else:
        st.sidebar.error("⚠️ Problema na inicialização")
    
    # Sidebar com navegação
    st.sidebar.title("🌱 Menu Principal")
    
    # Seção de navegação
    opcoes_navegacao = ["Dashboard", "Cadastro Produção", "Configurações"]
    
    pagina = st.sidebar.radio("Navegar para", opcoes_navegacao)
    
    # Navegação
    if pagina == "Dashboard":
        pagina_dashboard_otimizada()
    elif pagina == "Cadastro Produção":
        pagina_cadastro_producao()
    elif pagina == "Configurações":
        pagina_configuracoes()
    
    # Status do sistema na sidebar
    st.sidebar.markdown("---")
    st.sidebar.subheader("📊 Status do Sistema")
    
    try:
        df_prod = carregar_tabela_otimizada("producao")
        total_producao = len(df_prod)
        st.sidebar.info(f"📦 Produção: {total_producao} registros")
        
        config = carregar_config()
        if config.get("modo_offline", False):
            st.sidebar.warning("📴 Modo offline")
            
    except Exception as e:
        st.sidebar.error("Erro ao carregar status")

# ===============================
# EXECUÇÃO PRINCIPAL
# ===============================
if __name__ == "__main__":
    main()
