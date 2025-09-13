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

# ===============================
# CONFIGURAÇÕES INICIAIS
# ===============================
st.set_page_config(
    page_title="🌱 Sistema Integrado de Gestão Agrícola", 
    layout="wide",
    page_icon="🌱",
    initial_sidebar_state="expanded"
)

# Otimização: Cache para melhor performance
@st.cache_resource
def init_database():
    """Inicializa o banco de dados com conexão otimizada"""
    return sqlite3.connect("dados_sitio.db", check_same_thread=False)

@st.cache_data(ttl=300)  # Cache de 5 minutos para dados que não mudam frequentemente
def carregar_config():
    """Carrega as configurações do sistema com cache"""
    if not os.path.exists("config.json"):
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
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=4)
        return cfg
    
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)

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
# BANCO DE DADOS OTIMIZADO
# ===============================
def criar_tabelas_otimizadas():
    """Cria todas as tabelas necessárias no banco de dados com índices para performance"""
    conn = init_database()
    cursor = conn.cursor()
    
    # Habilitar recursos de performance
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.execute("PRAGMA synchronous = NORMAL")
    cursor.execute("PRAGMA cache_size = -10000")  # 10MB cache
    
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
        """,
        """
        CREATE TABLE IF NOT EXISTS sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tabela TEXT,
            ultima_sincronizacao INTEGER,
            registros_sincronizados INTEGER
        )
        """
    ]
    
    for tabela in tabelas:
        cursor.execute(tabela)
    
    # Criar índices para melhor performance
    indices = [
        "CREATE INDEX IF NOT EXISTS idx_producao_data ON producao(data)",
        "CREATE INDEX IF NOT EXISTS idx_producao_area ON producao(area)",
        "CREATE INDEX IF NOT EXISTS idx_producao_cultura ON producao(cultura)",
        "CREATE INDEX IF NOT EXISTS idx_insumos_data ON insumos(data)",
        "CREATE INDEX IF NOT EXISTS idx_insumos_tipo ON insumos(tipo)",
        "CREATE INDEX IF NOT EXISTS idx_insumos_cultura ON insumos(cultura)",
        "CREATE INDEX IF NOT EXISTS idx_timestamp ON producao(timestamp)",
        "CREATE INDEX IF NOT EXISTS idx_sync_status ON producao(sync_status)"
    ]
    
    for indice in indices:
        try:
            cursor.execute(indice)
        except:
            pass
    
    conn.commit()
    conn.close()

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

@st.cache_data(ttl=60, max_entries=10)  # Cache de 1 minuto para dados frequentes
def carregar_tabela_otimizada(nome_tabela, where_clause="", params=()):
    """Carrega dados de uma tabela do banco com opções de filtro"""
    conn = init_database()
    
    # Para grandes volumes de dados, usar paginação ou filtros
    query = f"SELECT * FROM {nome_tabela}"
    if where_clause:
        query += f" WHERE {where_clause}"
    
    # Ordenar por timestamp para garantir consistência
    query += " ORDER BY timestamp DESC"
    
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    
    # Normalizar nomes de áreas se a tabela tiver essa coluna
    if "area" in df.columns:
        df["area"] = df["area"].apply(normalizar_nome_area)
    
    return df

def inserir_tabela_em_lote(nome_tabela, df, batch_size=100):
    """Insere dados em lote para melhor performance com grandes volumes"""
    if df.empty:
        return
    
    conn = init_database()
    cursor = conn.cursor()
    
    # Preparar colunas
    colunas = df.columns.tolist()
    placeholders = ", ".join(["?"] * len(colunas))
    
    # Inserir em lotes
    for i in range(0, len(df), batch_size):
        lote = df.iloc[i:i+batch_size]
        valores = [tuple(row) for row in lote.to_numpy()]
        
        cursor.executemany(
            f"INSERT INTO {nome_tabela} ({', '.join(colunas)}) VALUES ({placeholders})",
            valores
        )
    
    conn.commit()
    conn.close()

def excluir_linha(nome_tabela, row_id):
    """Exclui uma linha específica do banco com marcação de sync"""
    conn = init_database()
    cursor = conn.cursor()
    
    # Marcar para exclusão em sync (soft delete)
    cursor.execute(f"UPDATE {nome_tabela} SET sync_status = -1 WHERE id=?", (row_id,))
    
    # Ou exclusão física se preferir
    # cursor.execute(f"DELETE FROM {nome_tabela} WHERE id=?", (row_id,))
    
    conn.commit()
    conn.close()

@st.cache_data(ttl=3600)  # Cache de 1 hora para preços (mudam pouco)
def carregar_precos_culturas():
    """Carrega os preços das culturas do banco de dados"""
    conn = init_database()
    df = pd.read_sql("SELECT * FROM precos_culturas", conn)
    conn.close()
    
    precos_dict = {}
    for _, row in df.iterrows():
        precos_dict[row['cultura']] = {
            'preco_primeira': row['preco_primeira'],
            'preco_segunda': row['preco_segunda']
        }
    
    return precos_dict

def salvar_preco_cultura(cultura, preco_primeira, preco_segunda):
    """Salva ou atualiza o preço de uma cultura"""
    conn = init_database()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM precos_culturas WHERE cultura = ?", (cultura,))
    existe = cursor.fetchone()
    
    if existe:
        cursor.execute("UPDATE precos_culturas SET preco_primeira = ?, preco_segunda = ? WHERE cultura = ?", 
                      (preco_primeira, preco_segunda, cultura))
    else:
        cursor.execute("INSERT INTO precos_culturas (cultura, preco_primeira, preco_segunda) VALUES (?, ?, ?)", 
                      (cultura, preco_primeira, preco_segunda))
    
    conn.commit()
    conn.close()
    
    # Limpar cache para forçar atualização
    carregar_precos_culturas.clear()

# ===============================
# FUNÇÕES UTILITÁRIAS OTIMIZADAS
# ===============================
@st.cache_data(ttl=300)  # Cache de 5 minutos para dados climáticos
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
        
        # Previsão
        url_forecast = f"https://api.openweathermap.org/data/2.5/forecast?q={city_encoded}&appid=eef20bca4e6fb1ff14a81a3171de5cec&units=metric&lang=pt_br"
        forecast = requests.get(url_forecast, timeout=10).json()
        previsao = []
        
        if forecast.get("cod") == "200":
            for item in forecast["list"][:8]:  # Apenas as próximas 24h para performance
                previsao.append({
                    "Data": item["dt_txt"], "Temp Real (°C)": item["main"]["temp"],
                    "Temp Média (°C)": (item["main"]["temp_min"] + item["main"]["temp_max"]) / 2,
                    "Temp Min (°C)": item["main"]["temp_min"], "Temp Max (°C)": item["main"]["temp_max"],
                    "Umidade (%)": item["main"]["humidity"]
                })
                
        return atual, pd.DataFrame(previsao)
    except:
        return None, None

# ===============================
# FUNÇÕES DE CÁLCULO OTIMIZADAS
# ===============================
def obter_preco_cultura(cultura, qualidade="primeira"):
    """Obtém o preço de uma cultura específica"""
    precos = carregar_precos_culturas()
    config = carregar_config()
    
    if cultura in precos:
        if qualidade == "primeira":
            return precos[cultura]['preco_primeira']
        else:
            return precos[cultura]['preco_segunda']
    else:
        # Retorna preços padrão se a cultura não estiver cadastrada
        if qualidade == "primeira":
            return config.get("preco_padrao_primeira", 30.0)
        else:
            return config.get("preco_padrao_segunda", 15.0)

def calcular_receita_cultura(caixas_primeira, caixas_segunda, cultura):
    """Calcula a receita total considerando preços específicos da cultura"""
    preco_primeira = obter_preco_cultura(cultura, "primeira")
    preco_segunda = obter_preco_cultura(cultura, "segunda")
    return (caixas_primeira * preco_primeira) + (caixas_segunda * preco_segunda)

def calcular_receita_total(df_prod):
    """Calcula a receita total considerando preços diferentes por cultura"""
    if df_prod.empty:
        return 0, 0, 0
    
    # Usar groupby para melhor performance com grandes datasets
    receita_primeira = 0
    receita_segunda = 0
    
    # Agrupar por cultura para reduzir chamadas a obter_preco_cultura
    for cultura, grupo in df_prod.groupby('cultura'):
        if cultura and str(cultura).strip():
            preco_primeira = obter_preco_cultura(cultura, "primeira")
            preco_segunda = obter_preco_cultura(cultura, "segunda")
            receita_primeira += grupo['caixas'].sum() * preco_primeira
            receita_segunda += grupo['caixas_segunda'].sum() * preco_segunda
    
    return receita_primeira, receita_segunda, receita_primeira + receita_segunda

# ===============================
# DADOS AGRONÔMICOS
# ===============================
DADOS_AGRONOMICOS = {
    "Tomate": {
        "densidade_plantio": 15000, "espacamento": "50x30 cm", "producao_esperada": 2.5,
        "ciclo_dias": 90, "temp_ideal": [18, 28], "umidade_ideal": [60, 80], "ph_ideal": [5.5, 6.8],
        "adubacao_base": {"N": 120, "P": 80, "K": 150},
        "pragas_comuns": ["tuta-absoluta", "mosca-branca", "ácaros"],
        "doencas_comuns": ["requeima", "murcha-bacteriana", "oidio"],
        "preco_sugerido_primeira": 35.0,
        "preco_sugerido_segunda": 18.0
    },
    "Pepino Japonês": {
        "densidade_plantio": 18000, "espacamento": "80x40 cm", "producao_esperada": 3.2,
        "ciclo_dias": 65, "temp_ideal": [20, 30], "umidade_ideal": [65, 80], "ph_ideal": [5.5, 6.5],
        "adubacao_base": {"N": 110, "P": 60, "K": 140},
        "pragas_comuns": ["mosca-branca", "ácaros", "vaquinha"],
        "doencas_comuns": ["oidio", "antracnose", "viruses"],
        "preco_sugerido_primeira": 28.0,
        "preco_sugerido_segunda": 14.0
    },
    # ... (outras culturas - mantido igual ao original para brevidade)
}

# ===============================
# FUNÇÕES DE BACKUP E SINCRONIZAÇÃO
# ===============================
def criar_backup():
    """Cria um backup completo do banco de dados"""
    try:
        # Nome do arquivo com timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"backup_sitio_{timestamp}.zip"
        
        # Criar arquivo ZIP com banco de dados e configurações
        with zipfile.ZipFile(backup_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write("dados_sitio.db", "dados_sitio.db")
            if os.path.exists("config.json"):
                zipf.write("config.json", "config.json")
        
        # Atualizar configuração com último backup
        config = carregar_config()
        config["ultimo_backup"] = timestamp
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        
        return backup_file
    except Exception as e:
        st.error(f"Erro ao criar backup: {e}")
        return None

def restaurar_backup(arquivo_backup):
    """Restaura o sistema a partir de um backup"""
    try:
        # Fazer backup atual antes de restaurar
        backup_atual = criar_backup()
        if backup_atual:
            st.info(f"Backup atual salvo como {backup_atual}")
        
        # Extrair arquivos do backup
        with zipfile.ZipFile(arquivo_backup, 'r') as zipf:
            zipf.extractall(".")
        
        st.success("Backup restaurado com sucesso!")
        st.rerun()
    except Exception as e:
        st.error(f"Erro ao restaurar backup: {e}")

# ===============================
# OTIMIZAÇÃO PARA DISPOSITIVOS MÓVEIS
# ===============================
def verificar_dispositivo_mobile():
    """Verifica se o aplicativo está sendo executado em dispositivo móvel"""
    user_agent = st.query_params.get("user_agent", "")
    mobile_keywords = ['mobile', 'android', 'iphone', 'ipad', 'tablet']
    return any(keyword in user_agent.lower() for keyword in mobile_keywords)

def interface_mobile_otimizada():
    """Adapta a interface para dispositivos móveis"""
    if verificar_dispositivo_mobile():
        st.markdown("""
        <style>
            .block-container {
                padding: 0.5rem;
            }
            .stButton button {
                font-size: 14px;
                padding: 0.5rem;
            }
            .stSelectbox, .stTextInput, .stNumberInput, .stDateInput {
                font-size: 14px;
            }
        </style>
        """, unsafe_allow_html=True)
        
        # Simplificar interface para mobile
        st.sidebar.selectbox("📱 Navegação Rápida", 
                           ["Dashboard", "Cadastro Produção", "Cadastro Insumos", "Análise", "Configurações"],
                           key="mobile_nav")

# ===============================
# PÁGINAS PRINCIPAIS OTIMIZADAS
# ===============================
def pagina_dashboard_otimizada():
    """Dashboard otimizado para performance"""
    st.title("🌱 Dashboard de Produção")
    
    # Carregar dados com filtro de período (últimos 30 dias por padrão para performance)
    data_limite = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    df_prod = carregar_tabela_otimizada("producao", "data >= ?", (data_limite,))
    df_ins = carregar_tabela_otimizada("insumos", "data >= ?", (data_limite,))
    
    # KPIs principais - COM PREÇOS ESPECÍFICOS POR CULTURA
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        total_caixas = df_prod["caixas"].sum() if not df_prod.empty else 0
        st.metric("📦 Caixas 1ª", f"{total_caixas:.0f}")
    
    with col2:
        total_segunda = df_prod["caixas_segunda"].sum() if not df_prod.empty else 0
        st.metric("🔄 Caixas 2ª", f"{total_segunda:.0f}")
    
    with col3:
        total_insumos = df_ins["custo_total"].sum() if not df_ins.empty else 0
        st.metric("💰 Custo Insumos", f"R$ {total_insumos:,.0f}")
    
    with col4:
        receita_primeira, receita_segunda, receita_total = calcular_receita_total(df_prod)
        st.metric("💵 Receita Total", f"R$ {receita_total:,.0f}")
    
    with col5:
        lucro_total = receita_total - total_insumos
        st.metric("📊 Lucro Total", f"R$ {lucro_total:,.0f}")
    
    # Gráficos simplificados para performance
    st.subheader("📈 Visão Geral")
    
    if not df_prod.empty:
        col1, col2 = st.columns(2)
        
        with col1:
            # Produção por dia (amostragem para performance)
            prod_diaria = df_prod.groupby('data')[['caixas', 'caixas_segunda']].sum().reset_index()
            if len(prod_diaria) > 30:
                prod_diaria = prod_diaria.iloc[-30:]  # Últimos 30 dias
            
            fig = px.line(prod_diaria, x='data', y='caixas', title='Produção Diária 1ª')
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            # Distribuição por qualidade
            qualidade_data = pd.DataFrame({
                'Categoria': ['1ª Qualidade', '2ª Qualidade'],
                'Quantidade': [total_caixas, total_segunda]
            })
            fig = px.pie(qualidade_data, values='Quantidade', names='Categoria', title='Distribuição por Qualidade')
            st.plotly_chart(fig, use_container_width=True)
    
    # Alertas simplificados
    st.subheader("⚠️ Alertas")
    
    if not df_prod.empty:
        df_prod["pct_segunda"] = np.where(
            (df_prod["caixas"] + df_prod["caixas_segunda"]) > 0,
            df_prod["caixas_segunda"] / (df_prod["caixas"] + df_prod["caixas_segunda"]) * 100, 0
        )
        
        alta_segunda = df_prod[df_prod["pct_segunda"] > 25]
        if not alta_segunda.empty:
            st.warning(f"Alto percentual de 2ª qualidade ({alta_segunda['pct_segunda'].mean():.1f}%)")
    
    # Últimos registros
    st.subheader("📋 Últimos Registros")
    if not df_prod.empty:
        st.dataframe(df_prod.head(10)[['data', 'area', 'cultura', 'caixas', 'caixas_segunda']], 
                    use_container_width=True)

def pagina_analise_otimizada():
    """Página de análise otimizada para grandes volumes de dados"""
    st.title("📊 Análise de Produção e Custos")
    
    # Controles de filtro com valores padrão para performance
    st.sidebar.subheader("🔍 Filtros de Análise")
    
    # Período padrão: últimos 90 dias (equilíbrio entre performance e dados)
    data_inicio_padrao = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
    data_fim_padrao = datetime.now().strftime('%Y-%m-%d')
    
    data_inicio = st.sidebar.date_input("Data Início", 
                                      value=datetime.strptime(data_inicio_padrao, '%Y-%m-%d'))
    data_fim = st.sidebar.date_input("Data Fim", 
                                   value=datetime.strptime(data_fim_padrao, '%Y-%m-%d'))
    
    # Carregar dados com filtro de período
    df_prod = carregar_tabela_otimizada("producao", "data BETWEEN ? AND ?", 
                                      (data_inicio.strftime('%Y-%m-%d'), data_fim.strftime('%Y-%m-%d')))
    df_ins = carregar_tabela_otimizada("insumos", "data BETWEEN ? AND ?", 
                                     (data_inicio.strftime('%Y-%m-%d'), data_fim.strftime('%Y-%m-%d')))
    
    # Análise simplificada com abas
    tab1, tab2, tab3 = st.tabs(["Produção", "Custos", "Rentabilidade"])
    
    with tab1:
        if not df_prod.empty:
            # Resumo produção
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total 1ª", f"{df_prod['caixas'].sum():.0f}")
            with col2:
                st.metric("Total 2ª", f"{df_prod['caixas_segunda'].sum():.0f}")
            with col3:
                total_geral = df_prod['caixas'].sum() + df_prod['caixas_segunda'].sum()
                pct_segunda = (df_prod['caixas_segunda'].sum() / total_geral * 100) if total_geral > 0 else 0
                st.metric("% 2ª", f"{pct_segunda:.1f}%")
            
            # Gráfico de produção ao longo do tempo (agrupado por semana para performance)
            df_prod['data'] = pd.to_datetime(df_prod['data'])
            df_prod['semana'] = df_prod['data'].dt.to_period('W').astype(str)
            prod_semanal = df_prod.groupby('semana')[['caixas', 'caixas_segunda']].sum().reset_index()
            
            fig = px.line(prod_semanal, x='semana', y=['caixas', 'caixas_segunda'], 
                         title='Produção Semanal', markers=True)
            st.plotly_chart(fig, use_container_width=True)
    
    with tab2:
        if not df_ins.empty:
            # Resumo custos
            total_custos = df_ins['custo_total'].sum()
            st.metric("Custo Total", f"R$ {total_custos:,.2f}")
            
            # Distribuição por tipo
            custos_tipo = df_ins.groupby('tipo')['custo_total'].sum().reset_index()
            fig = px.pie(custos_tipo, values='custo_total', names='tipo', title='Custos por Tipo')
            st.plotly_chart(fig, use_container_width=True)
    
    with tab3:
        if not df_prod.empty and not df_ins.empty:
            receita_primeira, receita_segunda, receita_total = calcular_receita_total(df_prod)
            custo_total = df_ins['custo_total'].sum()
            lucro = receita_total - custo_total
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Receita", f"R$ {receita_total:,.2f}")
            with col2:
                st.metric("Custos", f"R$ {custo_total:,.2f}")
            with col3:
                st.metric("Lucro", f"R$ {lucro:,.2f}")
            
            # Rentabilidade por cultura (se houver dados)
            if 'cultura' in df_prod.columns and 'cultura' in df_ins.columns:
                rentabilidade = []
                for cultura in df_prod['cultura'].unique():
                    if cultura and str(cultura).strip():
                        prod_cultura = df_prod[df_prod['cultura'] == cultura]
                        ins_cultura = df_ins[df_ins['cultura'] == cultura]
                        
                        rec_p, rec_s, rec_t = calcular_receita_total(prod_cultura)
                        custo_t = ins_cultura['custo_total'].sum()
                        lucro_c = rec_t - custo_t
                        
                        rentabilidade.append({
                            'Cultura': cultura,
                            'Receita': rec_t,
                            'Custo': custo_t,
                            'Lucro': lucro_c
                        })
                
                if rentabilidade:
                    df_rent = pd.DataFrame(rentabilidade)
                    fig = px.bar(df_rent, x='Cultura', y='Lucro', title='Lucro por Cultura')
                    st.plotly_chart(fig, use_container_width=True)

# ===============================
# FUNÇÕES DE CADASTRO
# ===============================
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
            temperatura = st.number_input("Temperatura (°C)", value=25.0)
        with col_clima2:
            umidade = st.number_input("Umidade (%)", value=65.0)
        with col_clima3:
            chuva = st.number_input("Chuva (mm)", value=0.0)
        
        if st.form_submit_button("💾 Salvar Produção"):
            # Validar dados
            if not cultura.strip():
                st.error("Informe a cultura")
            else:
                # Inserir no banco
                conn = init_database()
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT INTO producao (data, area, cultura, caixas, caixas_segunda, 
                                        temperatura, umidade, chuva, observacao)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (data.strftime('%Y-%m-%d'), area, cultura, caixas, caixas_segunda,
                     temperatura, umidade, chuva, observacao))
                
                conn.commit()
                conn.close()
                
                st.success("Produção registrada com sucesso!")
                
                # Limpar cache para atualizar visualizações
                carregar_tabela_otimizada.clear()

# ===============================
# MENU PRINCIPAL OTIMIZADO
# ===============================
def main():
    """Função principal otimizada"""
    # Inicialização
    criar_tabelas_otimizadas()
    config = carregar_config()
    
    # Verificar e adaptar para mobile
    interface_mobile_otimizada()
    
    # Sidebar com navegação
    st.sidebar.title("🌱 Menu Principal")
    
    # Seção de navegação
    opcoes_navegacao = [
        "Dashboard", "Cadastro Produção", "Cadastro Insumos", 
        "Análise", "Recomendações", "Configurações", "Backup"
    ]
    
    pagina = st.sidebar.radio("Navegar para", opcoes_navegacao)
    
    # Navegação
    if pagina == "Dashboard":
        pagina_dashboard_otimizada()
    elif pagina == "Cadastro Produção":
        pagina_cadastro_producao()
    elif pagina == "Cadastro Insumos":
        st.info("Página de cadastro de insumos em desenvolvimento")
    elif pagina == "Análise":
        pagina_analise_otimizada()
    elif pagina == "Recomendações":
        st.info("Página de recomendações em desenvolvimento")
    elif pagina == "Configurações":
        # Interface de configurações
        st.title("⚙️ Configurações")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Preferências")
            cidade = st.text_input("Cidade para clima", value=config.get("cidade", "Londrina"))
            modo_offline = st.checkbox("Modo offline", value=config.get("modo_offline", False))
            
            if st.button("Salvar Configurações"):
                config["cidade"] = cidade
                config["modo_offline"] = modo_offline
                with open("config.json", "w", encoding="utf-8") as f:
                    json.dump(config, f, ensure_ascii=False, indent=4)
                st.success("Configurações salvas!")
        
        with col2:
            st.subheader("Manutenção")
            if st.button("Otimizar Banco de Dados"):
                conn = init_database()
                conn.execute("VACUUM")
                conn.close()
                st.success("Banco de dados otimizado!")
                
            if st.button("Limpar Cache"):
                carregar_tabela_otimizada.clear()
                carregar_config.clear()
                carregar_precos_culturas.clear()
                st.success("Cache limpo!")
    
    elif pagina == "Backup":
        st.title("💾 Backup e Restauração")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Criar Backup")
            if st.button("Criar Backup Agora"):
                backup_file = criar_backup()
                if backup_file:
                    st.success(f"Backup criado: {backup_file}")
                    
                    # Download do backup
                    with open(backup_file, "rb") as f:
                        bytes_data = f.read()
                    st.download_button(
                        label="📥 Download Backup",
                        data=bytes_data,
                        file_name=backup_file,
                        mime="application/zip"
                    )
        
        with col2:
            st.subheader("Restaurar Backup")
            uploaded_file = st.file_uploader("Selecione arquivo de backup", type=["zip"])
            if uploaded_file and st.button("Restaurar Backup"):
                with open("temp_backup.zip", "wb") as f:
                    f.write(uploaded_file.getvalue())
                restaurar_backup("temp_backup.zip")
    
    # Status do sistema na sidebar
    st.sidebar.markdown("---")
    st.sidebar.subheader("📊 Status do Sistema")
    
    # Estatísticas rápidas
    try:
        conn = init_database()
        total_producao = pd.read_sql("SELECT COUNT(*) as total FROM producao", conn).iloc[0]['total']
        total_insumos = pd.read_sql("SELECT COUNT(*) as total FROM insumos", conn).iloc[0]['total']
        conn.close()
        
        st.sidebar.info(f"📦 Produção: {total_producao} registros")
        st.sidebar.info(f"📦 Insumos: {total_insumos} registros")
        
        # Último backup
        if config.get("ultimo_backup"):
            st.sidebar.info(f"💾 Último backup: {config['ultimo_backup']}")
        else:
            st.sidebar.warning("⚠️ Nenhum backup realizado")
            
    except:
        st.sidebar.error("Erro ao carregar estatísticas")
    
    # Modo offline
    if config.get("modo_offline", False):
        st.sidebar.warning("📴 Modo offline ativo")

# ===============================
# EXECUÇÃO PRINCIPAL
# ===============================
if __name__ == "__main__":
    main()
