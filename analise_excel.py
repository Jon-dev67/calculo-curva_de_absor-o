import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import requests
import urllib.parse
import json
import os
import re
from io import BytesIO
from datetime import date, datetime, timedelta
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ===============================
# CONFIGURAÇÕES INICIAIS
# ===============================
st.set_page_config(
    page_title="🌱 Sistema Integrado de Gestão Agrícola", 
    layout="wide",
    page_icon="🌱"
)

# Tema personalizado mais profissional
plt.style.use("dark_background")
sns.set_theme(style="darkgrid")

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
</style>
""", unsafe_allow_html=True)

# Constantes
DB_NAME = "dados_sitio.db"
CONFIG_FILE = "config.json"
API_KEY = "eef20bca4e6fb1ff14a81a3171de5cec"
CIDADE_PADRAO = "Londrina"

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

# ===============================
# BANCO DE DADOS
# ===============================
def criar_tabelas():
    """Cria todas as tabelas necessárias no banco de dados"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    tabelas = [
        """
        CREATE TABLE IF NOT EXISTS producao (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT, area TEXT, cultura TEXT, caixas INTEGER,
            caixas_segunda INTEGER, temperatura REAL, umidade REAL,
            chuva REAL, observacao TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS insumos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, area TEXT,
            cultura TEXT, tipo TEXT, quantidade REAL, unidade TEXT,
            custo_unitario REAL, custo_total REAL, fornecedor TEXT,
            lote TEXT, observacoes TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS custos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, tipo TEXT,
            descricao TEXT, valor REAL, area TEXT, observacoes TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS precos_culturas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            cultura TEXT UNIQUE,
            preco_primeira REAL,
            preco_segunda REAL
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
            observacoes TEXT
        )
        """
    ]
    
    for tabela in tabelas:
        cursor.execute(tabela)
    
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
        "Observação": "observacao", "Observacoes": "observacao", "Obs": "observacao"
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

def inserir_tabela(nome_tabela, df):
    """Insere dados em uma tabela do banco"""
    conn = sqlite3.connect(DB_NAME)
    
    if nome_tabela == "producao":
        df = normalizar_colunas(df)
    
    df.to_sql(nome_tabela, conn, if_exists="append", index=False)
    conn.close()

def carregar_tabela(nome_tabela):
    """Carrega dados de uma tabela do banco"""
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql(f"SELECT * FROM {nome_tabela}", conn)
    conn.close()
    
    # Normalizar nomes de áreas se a tabela tiver essa coluna
    if "area" in df.columns:
        df["area"] = df["area"].apply(normalizar_nome_area)
    
    return df

def excluir_linha(nome_tabela, row_id):
    """Exclui uma linha específica do banco"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(f"DELETE FROM {nome_tabela} WHERE id=?", (row_id,))
    conn.commit()
    conn.close()

def carregar_precos_culturas():
    """Carrega os preços das culturas do banco de dados"""
    conn = sqlite3.connect(DB_NAME)
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
    conn = sqlite3.connect(DB_NAME)
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

# ===============================
# CONFIGURAÇÕES
# ===============================
def carregar_config():
    """Carrega as configurações do sistema"""
    if not os.path.exists(CONFIG_FILE):
        cfg = {
            "cidade": CIDADE_PADRAO,
            "alerta_pct_segunda": 25.0,
            "alerta_prod_baixo_pct": 30.0,
            "preco_padrao_primeira": 30.0,
            "preco_padrao_segunda": 15.0,
            "custo_medio_insumos": {
                "Adubo Orgânico": 2.5, "Adubo Químico": 4.0, "Defensivo Agrícola": 35.0,
                "Semente": 0.5, "Muda": 1.2, "Fertilizante Foliar": 15.0, "Corretivo de Solo": 1.8
            }
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=4)
        return cfg
    
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def salvar_config(cfg):
    """Salva as configurações do sistema"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=4)

# ===============================
# FUNÇÕES UTILITÁRIAS
# ===============================
def buscar_clima(cidade):
    """Busca dados climáticos da API"""
    try:
        city_encoded = urllib.parse.quote(cidade)
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city_encoded}&appid={API_KEY}&units=metric&lang=pt_br"
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
        url_forecast = f"https://api.openweathermap.org/data/2.5/forecast?q={city_encoded}&appid={API_KEY}&units=metric&lang=pt_br"
        forecast = requests.get(url_forecast).json()
        previsao = []
        
        if forecast.get("cod") == "200":
            for item in forecast["list"]:
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
# FUNÇÕES UTILITÁRIAS PARA CÁLCULO
# ===============================
def obter_preco_cultura(cultura, qualidade="primeira"):
    """Obtém o preço de uma cultura específica"""
    if cultura in precos_culturas:
        if qualidade == "primeira":
            return precos_culturas[cultura]['preco_primeira']
        else:
            return precos_culturas[cultura]['preco_segunda']
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
    
    receita_primeira = 0
    receita_segunda = 0
    
    for _, row in df_prod.iterrows():
        cultura = row['cultura']
        if cultura and cultura.strip():
            preco_primeira = obter_preco_cultura(cultura, "primeira")
            preco_segunda = obter_preco_cultura(cultura, "segunda")
            receita_primeira += row['caixas'] * preco_primeira
            receita_segunda += row['caixas_segunda'] * preco_segunda
    
    return receita_primeira, receita_segunda, receita_primeira + receita_segunda

def calcular_lucro(df_prod, custos):
    """Calcula o lucro considerando preços diferentes por cultura"""
    _, _, receita_total = calcular_receita_total(df_prod)
    return receita_total - custos

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
    "Pepino Caipira": {
        "densidade_plantio": 15000, "espacamento": "100x50 cm", "producao_esperada": 2.8,
        "ciclo_dias": 70, "temp_ideal": [18, 28], "umidade_ideal": [60, 75], "ph_ideal": [5.8, 6.8],
        "adubacao_base": {"N": 100, "P": 50, "K": 120},
        "pragas_comuns": ["vaquinha", "broca", "ácaros"],
        "doencas_comuns": ["oidio", "mancha-angular", "viruses"],
        "preco_sugerido_primeira": 25.0,
        "preco_sugerido_segunda": 12.0
    },
    "Abóbora Itália": {
        "densidade_plantio": 8000, "espacamento": "200x100 cm", "producao_esperada": 4.5,
        "ciclo_dias": 85, "temp_ideal": [20, 30], "umidade_ideal": [60, 75], "ph_ideal": [6.0, 7.0],
        "adubacao_base": {"N": 80, "P": 50, "K": 100},
        "pragas_comuns": ["vaquinha", "broca", "pulgão"],
        "doencas_comuns": ["oidio", "antracnose", "murgas"],
        "preco_sugerido_primeira": 22.0,
        "preco_sugerido_segunda": 11.0
    },
    "Abóbora Menina": {
        "densidade_plantio": 6000, "espacamento": "250x120 cm", "producao_esperada": 6.0,
        "ciclo_dias": 95, "temp_ideal": [22, 32], "umidade_ideal": [65, 80], "ph_ideal": [6.0, 7.2],
        "adubacao_base": {"N": 70, "P": 45, "K": 90},
        "pragas_comuns": ["vaquinha", "broca", "pulgão"],
        "doencas_comuns": ["oidio", "antracnose", "murcha-bacteriana"],
        "preco_sugerido_primeira": 20.0,
        "preco_sugerido_segunda": 10.0
    },
    "Alface": {
        "densidade_plantio": 60000, "espacamento": "25x25 cm", "producao_esperada": 0.3,
        "ciclo_dias": 45, "temp_ideal": [15, 25], "umidade_ideal": [70, 85], "ph_ideal": [6.0, 7.0],
        "adubacao_base": {"N": 80, "P": 40, "K": 60},
        "pragas_comuns": ["pulgão", "lagarta", "vaquinha"],
        "doencas_comuns": ["podridão-mole", "queima-das-folhas", "míldio"],
        "preco_sugerido_primeira": 12.0,
        "preco_sugerido_segunda": 6.0
    },
    "Couve": {
        "densidade_plantio": 30000, "espacamento": "40x40 cm", "producao_esperada": 0.4,
        "ciclo_dias": 60, "temp_ideal": [15, 25], "umidade_ideal": [65, 80], "ph_ideal": [6.0, 7.0],
        "adubacao_base": {"N": 100, "P": 50, "K": 80},
        "pragas_comuns": ["lagarta", "pulgão", "besouro"],
        "doencas_comuns": ["mancha-das-folhas", "podridão-negra", "oidio"],
        "preco_sugerido_primeira": 15.0,
        "preco_sugerido_segunda": 7.5
    }
}

# ===============================
# FUNÇÕES DE RECOMENDAÇÃO
# ===============================
def calcular_producao_esperada(cultura, area_m2):
    """Calcula a produção esperada baseada em dados técnicos"""
    if cultura not in DADOS_AGRONOMICOS:
        return None
    
    dados = DADOS_AGRONOMICOS[cultura]
    plantas = (area_m2 * dados['densidade_plantio']) / 10000
    producao_kg = plantas * dados['producao_esperada']
    
    return {
        'plantas_estimadas': int(plantas),
        'producao_kg': round(producao_kg, 2),
        'producao_caixas': round(producao_kg / 20, 1),
        'ciclo_dias': dados['ciclo_dias']
    }

def gerar_recomendacoes_clima(cultura, dados_clima):
    """Gera recomendações baseadas nas condições climáticas"""
    if cultura not in DADOS_AGRONOMICOS:
        return []
    
    dados = DADOS_AGRONOMICOS[cultura]
    recomendacoes = []
    
    temp = dados_clima.get('temperatura', 25)
    if temp < dados['temp_ideal'][0]:
        recomendacoes.append(f"🌡️ Temperatura baixa ({temp}°C) - considerar aquecimento ou cobertura")
    elif temp > dados['temp_ideal'][1]:
        recomendacoes.append(f"🌡️ Temperatura alta ({temp}°C) - aumentar ventilação/sombreamento")
    
    umidade = dados_clima.get('umidade', 70)
    if umidade < dados['umidade_ideal'][0]:
        recomendacoes.append(f"💧 Umidade baixa ({umidade}%) - aumentar irrigação")
    elif umidade > dados['umidade_ideal'][1]:
        recomendacoes.append(f"💧 Umidade alta ({umidade}%) - risco de doenças, melhorar ventilação")
    
    return recomendacoes

def recomendar_adubacao_especifica(cultura, area_m2):
    """Recomenda adubação específica baseada na cultura"""
    if cultura not in DADOS_AGRONOMICOS:
        return None
    
    dados = DADOS_AGRONOMICOS[cultura]
    area_ha = area_m2 / 10000
    
    recomendacao = {}
    for nutriente, quantidade in dados['adubacao_base'].items():
        recomendacao[nutriente] = round(quantidade * area_ha, 2)
    
    return recomendacao

def verificar_alertas_sanitarios(cultura, dados_clima):
    """Verifica condições propícias para pragas e doenças"""
    if cultura not in DADOS_AGRONOMICOS:
        return []
    
    dados = DADOS_AGRONOMICOS[cultura]
    alertas = []
    
    if dados_clima.get('umidade', 70) > 80:
        alertas.append(f"⚠️ Condições favoráveis para doenças fúngicas em {cultura}")
        alertas.append(f"   Doenças comuns: {', '.join(dados['doencas_comuns'][:2])}")
    
    if dados_clima.get('temperatura', 25) > 28 and dados_clima.get('umidade', 70) > 70:
        alertas.append(f"⚠️ Condições ideais para pragas em {cultura}")
        alertas.append(f"   Pragas comuns: {', '.join(dados['pragas_comuns'][:2])}")
    
    return alertas

def calcular_otimizacao_espaco(estufa_area, cultura):
    """Calcula otimização de espaço para a cultura"""
    if cultura not in DADOS_AGRONOMICOS:
        return None
    
    dados = DADOS_AGRONOMICOS[cultura]
    plantas_possiveis = (estufa_area * dados['densidade_plantio']) / 10000
    
    return {
        'cultura': cultura, 'area_estufa_m2': estufa_area,
        'plantas_recomendadas': int(plantas_possiveis),
        'producao_estimada_kg': round(plantas_possiveis * dados['producao_esperada'], 2),
        'espacamento_recomendado': dados['espacamento'],
        'rendimento_por_m2': round((plantas_possiveis * dados['producao_esperada']) / estufa_area, 3)
    }

# ===============================
# MÓDULO AGRONÔMICO
# ===============================
def mostrar_modulo_agronomico():
    """Interface do módulo agronômico"""
    st.title("🌿 Recomendações Agronômicas Inteligentes")
    
    tab1, tab2, tab3, tab4 = st.tabs(["Calculadora de Produção", "Recomendações de Manejo", 
                                    "Alertas Sanitários", "Otimização de Espaço"])
    
    with tab1:
        st.header("📊 Calculadora de Produção Esperada")
        col1, col2 = st.columns(2)
        
        with col1:
            cultura = st.selectbox("Selecione a cultura:", list(DADOS_AGRONOMICOS.keys()))
            area_m2 = st.number_input("Área disponível (m²):", min_value=1.0, value=100.0)
        
        with col2:
            if cultura:
                dados = DADOS_AGRONOMICOS[cultura]
                preco_primeira = obter_preco_cultura(cultura, "primeira")
                preco_segunda = obter_preco_cultura(cultura, "segunda")
                
                st.info(f"""**Dados Técnicos da {cultura}:**
                - Densidade: {dados['densidade_plantio']} plantas/ha
                - Espaçamento: {dados['espacamento']}
                - Ciclo: {dados['ciclo_dias']} dias
                - Produção esperada: {dados['producao_esperada']} kg/planta
                - Preço 1ª: R$ {preco_primeira:.2f}/caixa
                - Preço 2ª: R$ {preco_segunda:.2f}/caixa""")
        
        if st.button("Calcular Produção Esperada"):
            resultado = calcular_producao_esperada(cultura, area_m2)
            if resultado:
                # Calcular receita estimada
                receita_primeira = resultado['producao_caixas'] * 0.8 * obter_preco_cultura(cultura, "primeira")
                receita_segunda = resultado['producao_caixas'] * 0.2 * obter_preco_cultura(cultura, "segunda")
                receita_total = receita_primeira + receita_segunda
                
                st.success(f"""**Resultado para {cultura} em {area_m2}m²:**
                - 👨‍🌾 Plantas estimadas: {resultado['plantas_estimadas']}
                - 📦 Produção estimada: {resultado['producao_kg']} kg ({resultado['producao_caixas']} caixas)
                - 💰 Receita estimada: R$ {receita_total:,.2f}
                - ⏰ Ciclo: {resultado['ciclo_dias']} dias""")
    
    with tab2:
        st.header("🌡️ Recomendações de Manejo")
        cultura = st.selectbox("Cultura para análise:", list(DADOS_AGRONOMICOS.keys()), key="cultura_manejo")
        
        col1, col2 = st.columns(2)
        with col1:
            temperatura = st.slider("Temperatura atual (°C):", 0.0, 40.0, 25.0)
        
        with col2:
            umidade = st.slider("Umidade relativa (%):", 0.0, 100.0, 70.0)
            area = st.number_input("Área (m²):", min_value=1.0, value=100.0, key="area_manejo")
        
        if st.button("Gerar Recomendações"):
            rec_clima = gerar_recomendacoes_clima(cultura, {'temperatura': temperatura, 'umidade': umidade})
            if rec_clima:
                st.info("**Recomendações Climáticas:**")
                for rec in rec_clima:
                    st.write(f"- {rec}")
            
            adubacao = recomendar_adubacao_especifica(cultura, area)
            if adubacao:
                st.success("**Recomendação de Adubação:**")
                st.write(f"- Nitrogênio (N): {adubacao['N']} kg/ha")
                st.write(f"- Fósforo (P): {adubacao['P']} kg/ha")
                st.write(f"- Potássio (K): {adubacao['K']} kg/ha")
    
    with tab3:
        st.header("⚠️ Alertas Sanitários")
        cultura = st.selectbox("Cultura para monitoramento:", list(DADOS_AGRONOMICOS.keys()), key="cultura_alerta")
        
        col1, col2 = st.columns(2)
        with col1:
            temp = st.slider("Temperatura (°C):", 0.0, 40.0, 25.0, key="temp_alerta")
        with col2:
            umid = st.slider("Umidade (%):", 0.0, 100.0, 70.0, key="umid_alerta")
        
        if st.button("Verificar Alertas"):
            alertas = verificar_alertas_sanitarios(cultura, {'temperatura': temp, 'umidade': umid})
            if alertas:
                st.error("**Alertas Sanitários:**")
                for alerta in alertas:
                    st.write(f"- {alerta}")
            else:
                st.success("✅ Condições dentro dos parâmetros normais")
    
    with tab4:
        st.header("📐 Otimização de Espaço")
        cultura = st.selectbox("Cultura para otimização:", list(DADOS_AGRONOMICOS.keys()), key="cultura_otimizacao")
        area_estufa = st.number_input("Área da estufa (m²):", min_value=1.0, value=200.0)
        
        if st.button("Calcular Otimização"):
            resultado = calcular_otimizacao_espaco(area_estufa, cultura)
            if resultado:
                # Calcular receita estimada
                receita_primeira = resultado['producao_estimada_kg'] / 20 * 0.8 * obter_preco_cultura(cultura, "primeira")
                receita_segunda = resultado['producao_estimada_kg'] / 20 * 0.2 * obter_preco_cultura(cultura, "segunda")
                receita_total = receita_primeira + receita_segunda
                
                st.success(f"""**Otimização para {cultura}:**
                - 🏭 Área disponível: {resultado['area_estufa_m2']} m²
                - 👨‍🌾 Plantas recomendadas: {resultado['plantas_recomendadas']}
                - 📦 Produção estimada: {resultado['producao_estimada_kg']} kg
                - 💰 Receita estimada: R$ {receita_total:,.2f}
                - 📏 Espaçamento: {resultado['espacamento_recomendado']}
                - 📊 Rendimento: {resultado['rendimento_por_m2']} kg/m²""")

def adicionar_recomendacoes_dashboard():
    """Adiciona cards de recomendação ao dashboard principal"""
    df_prod = carregar_tabela("producao")
    
    if not df_prod.empty:
        st.subheader("🌿 Recomendações Agronômicas")
        ultimo_registro = df_prod.iloc[-1]
        cultura = ultimo_registro['cultura']
        
        if cultura and cultura.strip() and cultura in DADOS_AGRONOMICOS:
            dados_clima = {
                'temperatura': ultimo_registro['temperatura'],
                'umidade': ultimo_registro['umidade']
            }
            
            recomendacoes = gerar_recomendacoes_clima(cultura, dados_clima)
            alertas = verificar_alertas_sanitarios(cultura, dados_clima)
            
            col1, col2 = st.columns(2)
            
            with col1:
                if recomendacoes:
                    st.info("**Recomendações Atuais:**")
                    for rec in recomendacoes[:3]:
                        st.write(f"- {rec}")
                else:
                    st.success("✅ Condições climáticas dentro do ideal")
            
            with col2:
                if alertas:
                    st.error("**Alertas Sanitários:**")
                    for alerta in alertas[:2]:
                        st.write(f"- {alerta}")
                else:
                    st.success("✅ Sem alertas sanitários")
        else:
            st.info("ℹ️ Selecione uma cultura válida para ver recomendações")

# ===============================
# PÁGINAS PRINCIPAIS
# ===============================
def pagina_dashboard():
    """Página principal do dashboard"""
    st.title("🌱 Dashboard de Produção")
    
    df_prod = carregar_tabela("producao")
    df_ins = carregar_tabela("insumos")
    
    # KPIs principais - COM PREÇOS ESPECÍFICOS POR CULTURA
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        total_caixas = df_prod["caixas"].sum() if not df_prod.empty else 0
        st.metric("📦 Caixas 1ª Qualidade", f"{total_caixas:.0f}")
    
    with col2:
        total_segunda = df_prod["caixas_segunda"].sum() if not df_prod.empty else 0
        st.metric("🔄 Caixas 2ª Qualidade", f"{total_segunda:.0f}")
    
    with col3:
        total_insumos = df_ins["custo_total"].sum() if not df_ins.empty else 0
        st.metric("💰 Custo Insumos", f"R$ {total_insumos:,.2f}")
    
    with col4:
        receita_primeira, receita_segunda, receita_total = calcular_receita_total(df_prod)
        st.metric("💵 Receita Total", f"R$ {receita_total:,.2f}")
    
    with col5:
        lucro_total = receita_total - total_insumos
        st.metric("📊 Lucro Total", f"R$ {lucro_total:,.2f}", 
                 delta=f"{((lucro_total/receita_total)*100 if receita_total > 0 else 0):.1f}%")
    
    # Gráfico de Receitas Separadas
    st.subheader("💰 Distribuição de Receitas")
    
    if not df_prod.empty:
        receitas_data = pd.DataFrame({
            'Tipo': ['1ª Qualidade', '2ª Qualidade', 'Custos'],
            'Valor (R$)': [receita_primeira, receita_segunda, -total_insumos],
            'Categoria': ['Receita', 'Receita', 'Custo']
        })
        
        fig = px.bar(receitas_data, x='Tipo', y='Valor (R$)', color='Categoria',
                    title='Receitas e Custos por Categoria', text='Valor (R$)')
        fig.update_traces(texttemplate='R$ %{y:,.2f}', textposition='outside')
        st.plotly_chart(fig, use_container_width=True)
    
    # Receita por Cultura
    st.subheader("🌱 Receita por Cultura")
    
    if not df_prod.empty:
        receitas_culturas = []
        for cultura in df_prod['cultura'].unique():
            if cultura and cultura.strip():
                df_cultura = df_prod[df_prod['cultura'] == cultura]
                rec_primeira, rec_segunda, rec_total = calcular_receita_total(df_cultura)
                receitas_culturas.append({
                    'Cultura': cultura,
                    'Receita 1ª': rec_primeira,
                    'Receita 2ª': rec_segunda,
                    'Receita Total': rec_total
                })
        
        if receitas_culturas:
            df_receitas = pd.DataFrame(receitas_culturas)
            fig = px.bar(df_receitas, x='Cultura', y=['Receita 1ª', 'Receita 2ª'],
                        title='Receita por Cultura', barmode='stack')
            st.plotly_chart(fig, use_container_width=True)
    
    # Alertas
    st.subheader("⚠️ Alertas e Recomendações")
    
    if not df_prod.empty:
        df_prod["pct_segunda"] = np.where(
            (df_prod["caixas"] + df_prod["caixas_segunda"]) > 0,
            df_prod["caixas_segunda"] / (df_prod["caixas"] + df_prod["caixas_segunda"]) * 100, 0
        )
        
        alta_segunda = df_prod[df_prod["pct_segunda"] > config.get("alerta_pct_segunda", 25)]
        if not alta_segunda.empty:
            st.warning(f"Alto percentual de 2ª qualidade ({alta_segunda['pct_segunda'].mean():.1f}%)")
        
        ultimo_clima = df_prod.iloc[-1]
        if ultimo_clima is not None and ultimo_clima["umidade"] > 85:
            st.error("Alerta: Umidade muito alta, risco de doenças fúngicas!")
        if ultimo_clima is not None and ultimo_clima["temperatura"] < 10:
            st.error("Alerta: Temperatura muito baixa, risco de danos às plantas!")
    
    # Gráficos resumos
    st.subheader("📊 Visão Geral")
    
    if not df_prod.empty:
        col1, col2 = st.columns(2)
        
        with col1:
            if "area" in df_prod.columns:
                prod_area = df_prod.groupby("area")[["caixas", "caixas_segunda"]].sum().reset_index()
                if not prod_area.empty:
                    fig = px.bar(prod_area, x="area", y=["caixas", "caixas_segunda"], 
                                title="Produção por Área", barmode="group")
                    st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            if "data" in df_prod.columns:
                df_prod["data"] = pd.to_datetime(df_prod["data"])
                prod_temporal = df_prod.groupby("data")[["caixas", "caixas_segunda"]].sum().reset_index()
                if not prod_temporal.empty:
                    fig = px.line(prod_temporal, x="data", y=["caixas", "caixas_segunda"], 
                                 title="Evolução da Produção", markers=True)
                    st.plotly_chart(fig, use_container_width=True)
    
    if not df_ins.empty:
        col1, col2 = st.columns(2)
        
        with col1:
            custos_tipo = df_ins.groupby("tipo")["custo_total"].sum().reset_index()
            if not custos_tipo.empty:
                fig = px.pie(custos_tipo, values="custo_total", names="tipo", 
                            title="Distribuição de Custos por Tipo")
                st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            custos_cultura = df_ins.groupby("cultura")["custo_total"].sum().reset_index()
            if not custos_cultura.empty:
                fig = px.bar(custos_cultura, x="cultura", y="custo_total", 
                            title="Custos por Cultura")
                st.plotly_chart(fig, use_container_width=True)

    adicionar_recomendacoes_dashboard()

def pagina_cadastro_producao():
    """Página de cadastro de produção"""
    st.title("📝 Cadastro de Produção")
    df = carregar_tabela("producao")
    cidade = st.sidebar.text_input("🌍 Cidade para clima", value=config.get("cidade", CIDADE_PADRAO))

    with st.form("form_cadastro_producao", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        with col1: 
            data_val = st.date_input("Data", value=date.today())
            area = st.selectbox("Área/Estufa", options=AREAS_PRODUCAO)
        with col2: 
            cultura = st.text_input("Cultura")
            caixas = st.number_input("Caixas (1ª)", min_value=0, step=1)
        with col3: 
            caixas2 = st.number_input("Caixas (2ª)", min_value=0, step=1)
            observacao = st.text_input("Observações")
        
        # Mostrar preços da cultura se existirem
        if cultura and cultura.strip():
            preco_primeira = obter_preco_cultura(cultura, "primeira")
            preco_segunda = obter_preco_cultura(cultura, "segunda")
            receita_estimada = (caixas * preco_primeira) + (caixas2 * preco_segunda)
            
            st.info(f"**Preços para {cultura}:** 1ª: R$ {preco_primeira:.2f} | 2ª: R$ {preco_segunda:.2f} | Receita: R$ {receita_estimada:.2f}")
        
        st.markdown("#### Clima")
        clima_atual, previsao = buscar_clima(cidade)
        
        if clima_atual: 
            temperatura, umidade, chuva = clima_atual["temp"], clima_atual["umidade"], clima_atual["chuva"]
            st.info(f"🌡️ {temperatura:.1f}°C | 💧 {umidade:.0f}% | 🌧️ {chuva:.1f}mm (atual)")
        else: 
            c1, c2, c3 = st.columns(3)
            with c1: temperatura = st.number_input("Temperatura (°C)", value=25.0)
            with c2: umidade = st.number_input("Umidade (%)", value=65.0)
            with c3: chuva = st.number_input("Chuva (mm)", value=0.0)

        enviado = st.form_submit_button("Salvar Registro ✅")
        if enviado:
            novo = pd.DataFrame([{
                "data": str(data_val), "area": area, "cultura": cultura.strip(),
                "caixas": int(caixas), "caixas_segunda": int(caixas2),
                "temperatura": float(temperatura), "umidade": float(umidade),
                "chuva": float(chuva), "observacao": observacao
            }])
            inserir_tabela("producao", novo)
            st.success("Registro salvo com sucesso!")

    if not df.empty:
        st.markdown("### 📋 Registros recentes")
        
        # Adicionar coluna de receita ao dataframe
        df_display = df.copy()
        receitas = []
        for _, row in df_display.iterrows():
            receita = calcular_receita_cultura(row['caixas'], row['caixas_segunda'], row['cultura'])
            receitas.append(receita)
        
        df_display['Receita (R$)'] = receitas
        st.dataframe(df_display.sort_values("data", ascending=False).head(15), use_container_width=True)
        
        st.markdown("### 🗑️ Excluir Registros")
        col1, col2 = st.columns([3, 1])
        with col1:
            ids = st.multiselect("Selecione ID(s) para excluir", df["id"].tolist())
        with col2:
            if st.button("Excluir selecionados", type="secondary"):
                if ids:
                    for i in ids: 
                        excluir_linha("producao", i)
                    st.success("✅ Linhas excluídas!")
                    st.rerun()
                else:
                    st.warning("Selecione pelo menos um ID para excluir")

    st.subheader("📂 Importar Excel")
    uploaded_file = st.file_uploader("Envie planilha Excel (Produção)", type=["xlsx"])
    if uploaded_file:
        df_excel = pd.read_excel(uploaded_file)
        df_excel = normalizar_colunas(df_excel)
        inserir_tabela("producao", df_excel)
        st.success("✅ Dados importados do Excel!")
        st.rerun()

def pagina_cadastro_insumos():
    """Página de cadastro de insumos"""
    st.title("📦 Cadastro de Insumos")
    df_ins = carregar_tabela("insumos")
    
    with st.form("form_insumos", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            data_i = st.date_input("Data", value=date.today())
            area_i = st.selectbox("Área/Estufa", options=AREAS_PRODUCAO)
            cultura_i = st.text_input("Cultura (opcional)")
            tipo_i = st.selectbox("Tipo de Insumo", TIPOS_INSUMOS)
            fornecedor_i = st.text_input("Fornecedor (opcional)")
            
        with col2:
            qtd_i = st.number_input("Quantidade", min_value=0.0, step=0.1)
            un_i = st.selectbox("Unidade", UNIDADES)
            custo_unit_i = st.number_input("Custo Unitário (R$)", min_value=0.0, step=0.01)
            custo_total_i = st.number_input("Custo Total (R$)", min_value=0.0, step=0.01, 
                                          value=0.0, help="Se não preenchido, será calculado automaticamente")
            lote_i = st.text_input("Nº Lote (opcional)")
            
        observacoes_i = st.text_area("Observações")
        
        if custo_unit_i > 0 and qtd_i > 0 and custo_total_i == 0:
            custo_total_i = custo_unit_i * qtd_i
            st.info(f"Custo total calculado: R$ {custo_total_i:.2f}")
            
        enviado_i = st.form_submit_button("Salvar Insumo ✅")
        if enviado_i:
            novo = pd.DataFrame([{
                "data": str(data_i), "area": area_i, "cultura": cultura_i,
                "tipo": tipo_i, "quantidade": qtd_i, "unidade": un_i,
                "custo_unitario": custo_unit_i, "custo_total": custo_total_i if custo_total_i > 0 else custo_unit_i * qtd_i,
                "fornecedor": fornecedor_i, "lote": lote_i, "observacoes": observacoes_i
            }])
            inserir_tabela("insumos", novo)
            st.success("Insumo salvo com sucesso!")

    if not df_ins.empty:
        st.subheader("📋 Histórico de Insumos")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            filtro_tipo = st.multiselect("Filtrar por tipo", options=df_ins["tipo"].unique())
        with col2:
            filtro_area = st.multiselect("Filtrar por área", options=df_ins["area"].unique())
        with col3:
            filtro_cultura = st.multiselect("Filtrar por cultura", options=df_ins["cultura"].unique())
        
        df_filtrado = df_ins.copy()
        if filtro_tipo: df_filtrado = df_filtrado[df_filtrado["tipo"].isin(filtro_tipo)]
        if filtro_area: df_filtrado = df_filtrado[df_filtrado["area"].isin(filtro_area)]
        if filtro_cultura: df_filtrado = df_filtrado[df_filtrado["cultura"].isin(filtro_cultura)]
            
        st.dataframe(df_filtrado.sort_values("data", ascending=False).head(20), use_container_width=True)
        
        st.subheader("📊 Estatísticas de Custos")
        if not df_filtrado.empty:
            total_custo = df_filtrado["custo_total"].sum()
            media_custo = df_filtrado["custo_total"].mean()
            st.write(f"**Total gasto:** R$ {total_custo:,.2f} | **Média por registro:** R$ {media_custo:,.2f}")
            
            df_filtrado["data"] = pd.to_datetime(df_filtrado["data"])
            custos_mensais = df_filtrado.groupby(df_filtrado["data"].dt.to_period("M"))["custo_total"].sum().reset_index()
            custos_mensais["data"] = custos_mensais["data"].astype(str)
            
            fig = px.bar(custos_mensais, x="data", y="custo_total", 
                        title="Evolução Mensal de Custos com Insumos")
            st.plotly_chart(fig, use_container_width=True)
        
        st.markdown("### 🗑️ Excluir Insumos")
        col1, col2 = st.columns([3, 1])
        with col1:
            ids_insumos = st.multiselect("Selecione ID(s) de insumos para excluir", df_ins["id"].tolist())
        with col2:
            if st.button("Excluir insumos selecionados", type="secondary"):
                if ids_insumos:
                    for i in ids_insumos: 
                        excluir_linha("insumos", i)
                    st.success("✅ Insumos excluídos!")
                    st.rerun()
                else:
                    st.warning("Selecione pelo menos um ID para excluir")

    st.subheader("📂 Importar Excel (Insumos)")
    uploaded_file = st.file_uploader("Envie planilha Excel (Insumos)", type=["xlsx"], key="insumos_upload")
    if uploaded_file:
        df_excel = pd.read_excel(uploaded_file)
        df_excel.rename(columns=lambda x: x.lower(), inplace=True)
        inserir_tabela("insumos", df_excel)
        st.success("✅ Dados de insumos importados do Excel!")
        st.rerun()

def pagina_analise():
    """Página de análise de dados"""
    st.title("📊 Análise Avançada de Produção e Custos")
    
    df_prod = carregar_tabela("producao")
    df_ins = carregar_tabela("insumos")
    
    if df_prod.empty and df_ins.empty:
        st.warning("📭 Nenhum dado disponível para análise. Cadastre dados de produção e insumos primeiro.")
        st.stop()
    
    st.sidebar.subheader("🔍 Filtros de Análise")
    
    # Período temporal
    if not df_prod.empty:
        datas_disponiveis = pd.to_datetime(df_prod['data']).sort_values()
        min_date, max_date = datas_disponiveis.min(), datas_disponiveis.max()
    else:
        min_date, max_date = date.today() - timedelta(days=365), date.today()
    
    date_range = st.sidebar.date_input("📅 Período de análise", value=(min_date, max_date),
                                      min_value=min_date, max_value=max_date)
    
    start_date, end_date = date_range if len(date_range) == 2 else (min_date, max_date)
    
    # Filtros adicionais
    col1, col2 = st.sidebar.columns(2)
    
    with col1:
        areas_selecionadas = st.multiselect("🏭 Áreas", options=df_prod['area'].unique(), default=df_prod['area'].unique()) if not df_prod.empty else []
        tipos_selecionados = st.multiselect("📦 Tipos de Insumos", options=df_ins['tipo'].unique(), default=df_ins['tipo'].unique()) if not df_ins.empty else []
    
    with col2:
        culturas_selecionadas = st.multiselect("🌱 Culturas", options=df_prod['cultura'].unique(), default=df_prod['cultura'].unique()) if not df_prod.empty else []
    
    # Aplicar filtros
    if not df_prod.empty:
        df_prod['data'] = pd.to_datetime(df_prod['data'])
        df_prod_filtrado = df_prod[(df_prod['data'] >= pd.to_datetime(start_date)) & 
                                  (df_prod['data'] <= pd.to_datetime(end_date))]
        if areas_selecionadas: df_prod_filtrado = df_prod_filtrado[df_prod_filtrado['area'].isin(areas_selecionadas)]
        if culturas_selecionadas: df_prod_filtrado = df_prod_filtrado[df_prod_filtrado['cultura'].isin(culturas_selecionadas)]
    else:
        df_prod_filtrado = pd.DataFrame()
    
    if not df_ins.empty:
        df_ins['data'] = pd.to_datetime(df_ins['data'])
        df_ins_filtrado = df_ins[(df_ins['data'] >= pd.to_datetime(start_date)) & 
                                (df_ins['data'] <= pd.to_datetime(end_date))]
        if tipos_selecionados: df_ins_filtrado = df_ins_filtrado[df_ins_filtrado['tipo'].isin(tipos_selecionados)]
    else:
        df_ins_filtrado = pd.DataFrame()
    
    # Métricas de performance
    st.header("📈 Métricas de Performance")
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        total_caixas = df_prod_filtrado['caixas'].sum() if not df_prod_filtrado.empty else 0
        st.metric("📦 Caixas 1ª Qualidade", f"{total_caixas:,.0f}")
    
    with col2:
        total_segunda = df_prod_filtrado['caixas_segunda'].sum() if not df_prod_filtrado.empty else 0
        pct_segunda = (total_segunda / (total_caixas + total_segunda) * 100) if (total_caixas + total_segunda) > 0 else 0
        st.metric("🔄 % 2ª Qualidade", f"{pct_segunda:.1f}%")
    
    with col3:
        custo_total = df_ins_filtrado['custo_total'].sum() if not df_ins_filtrado.empty else 0
        st.metric("💰 Custo Total", f"R$ {custo_total:,.2f}")
    
    with col4:
        receita_primeira, receita_segunda, receita_total = calcular_receita_total(df_prod_filtrado)
        st.metric("💵 Receita Total", f"R$ {receita_total:,.2f}")
    
    with col5:
        lucro = receita_total - custo_total
        st.metric("📊 Lucro Estimado", f"R$ {lucro:,.2f}")
    
    # Gráfico de Receitas Separadas
    st.subheader("💰 Distribuição de Receitas")
    
    if not df_prod_filtrado.empty:
        receitas_data = pd.DataFrame({
            'Tipo': ['1ª Qualidade', '2ª Qualidade', 'Custos'],
            'Valor (R$)': [receita_primeira, receita_segunda, -custo_total],
            'Categoria': ['Receita', 'Receita', 'Custo']
        })
        
        fig = px.bar(receitas_data, x='Tipo', y='Valor (R$)', color='Categoria',
                    title='Receitas e Custos por Categoria', text='Valor (R$)')
        fig.update_traces(texttemplate='R$ %{y:,.2f}', textposition='outside')
        st.plotly_chart(fig, use_container_width=True)
    
    # Receita por Cultura
    st.subheader("🌱 Receita por Cultura")
    
    if not df_prod_filtrado.empty:
        receitas_culturas = []
        for cultura in df_prod_filtrado['cultura'].unique():
            if cultura and cultura.strip():
                df_cultura = df_prod_filtrado[df_prod_filtrado['cultura'] == cultura]
                rec_primeira, rec_segunda, rec_total = calcular_receita_total(df_cultura)
                receitas_culturas.append({
                    'Cultura': cultura,
                    'Receita 1ª': rec_primeira,
                    'Receita 2ª': rec_segunda,
                    'Receita Total': rec_total
                })
        
        if receitas_culturas:
            df_receitas = pd.DataFrame(receitas_culturas)
            fig = px.bar(df_receitas, x='Cultura', y=['Receita 1ª', 'Receita 2ª'],
                        title='Receita por Cultura', barmode='stack')
            st.plotly_chart(fig, use_container_width=True)
    
    # Análise de Produção
    if not df_prod_filtrado.empty:
        st.header("🌱 Análise de Produção")
        
        tab1, tab2, tab3, tab4 = st.tabs(["Visão Geral", "Por Cultura", "Por Área", "Tendências"])
        
        with tab1:
            col1, col2 = st.columns(2)
            
            with col1:
                prod_diaria = df_prod_filtrado.groupby('data')[['caixas', 'caixas_segunda']].sum().reset_index()
                fig = px.line(prod_diaria, x='data', y=['caixas', 'caixas_segunda'],
                             title='📅 Produção Diária', markers=True)
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                qualidade_data = pd.DataFrame({
                    'Categoria': ['1ª Qualidade', '2ª Qualidade'],
                    'Quantidade': [total_caixas, total_segunda]
                })
                fig = px.pie(qualidade_data, values='Quantidade', names='Categoria',
                            title='🎯 Distribuição por Qualidade')
                st.plotly_chart(fig, use_container_width=True)
        
        with tab2:
            prod_cultura = df_prod_filtrado.groupby('cultura')[['caixas', 'caixas_segunda']].sum().reset_index()
            prod_cultura['Total'] = prod_cultura['caixas'] + prod_cultura['caixas_segunda']
            prod_cultura['% 2ª'] = (prod_cultura['caixas_segunda'] / prod_cultura['Total'] * 100).round(1)
            
            col1, col2 = st.columns(2)
            
            with col1:
                fig = px.bar(prod_cultura, x='cultura', y=['caixas', 'caixas_segunda'],
                            title='🌿 Produção por Cultura', barmode='group')
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                fig = px.bar(prod_cultura, x='cultura', y='% 2ª',
                            title='📊 Percentual de 2ª por Cultura')
                st.plotly_chart(fig, use_container_width=True)
        
        with tab3:
            if 'area' in df_prod_filtrado.columns:
                prod_area = df_prod_filtrado.groupby('area')[['caixas', 'caixas_segunda']].sum().reset_index()
                prod_area['Produtividade'] = prod_area['caixas'] / len(df_prod_filtrado['data'].unique())
                
                col1, col2 = st.columns(2)
                
                with col1:
                    fig = px.bar(prod_area, x='area', y='caixas',
                                title='🏭 Produção Total por Área')
                    st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    fig = px.bar(prod_area, x='area', y='Produtividade',
                                title='⚡ Produtividade Média Diária por Área')
                    st.plotly_chart(fig, use_container_width=True)
        
        with tab4:
            prod_mensal = df_prod_filtrado.copy()
            prod_mensal['mes'] = prod_mensal['data'].dt.to_period('M').astype(str)
            prod_mensal = prod_mensal.groupby('mes')[['caixas', 'caixas_segunda']].sum().reset_index()
            
            fig = px.line(prod_mensal, x='mes', y=['caixas', 'caixas_segunda'],
                         title='📈 Tendência Mensal de Produção', markers=True)
            st.plotly_chart(fig, use_container_width=True)
    
    # Análise de Custos
    if not df_ins_filtrado.empty:
        st.header("💰 Análise de Custos e Rentabilidade")
        
        tab1, tab2, tab3 = st.tabs(["Distribuição", "Evolução", "Rentabilidade"])
        
        with tab1:
            col1, col2 = st.columns(2)
            
            with col1:
                custos_tipo = df_ins_filtrado.groupby('tipo')['custo_total'].sum().reset_index()
                if not custos_tipo.empty:
                    fig = px.pie(custos_tipo, values='custo_total', names='tipo',
                                title='📊 Distribuição de Custos por Tipo')
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("ℹ️ Nenhum dado de custos disponível para análise")
            
            with col2:
                # Verificar se a coluna 'cultura' existe nos insumos
                if 'cultura' in df_ins_filtrado.columns:
                    custos_cultura = df_ins_filtrado.groupby('cultura')['custo_total'].sum().reset_index()
                    if not custos_cultura.empty:
                        fig = px.bar(custos_cultura, x='cultura', y='custo_total',
                                    title='🌱 Custos por Cultura')
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("ℹ️ Nenhum dado de custos por cultura disponível")
                else:
                    st.info("ℹ️ A coluna 'cultura' não está disponível nos dados de insumos")
        
        with tab2:
            custos_mensal = df_ins_filtrado.copy()
            custos_mensal['mes'] = custos_mensal['data'].dt.to_period('M').astype(str)
            custos_mensal = custos_mensal.groupby('mes')['custo_total'].sum().reset_index()
            
            if not custos_mensal.empty:
                fig = px.line(custos_mensal, x='mes', y='custo_total',
                             title='📈 Evolução Mensal de Custos', markers=True)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("ℹ️ Nenhum dado de custos disponível para análise temporal")
        
        with tab3:
            if not df_prod_filtrado.empty:
                # Calcular rentabilidade por cultura
                rentabilidade_data = []
                for cultura in df_prod_filtrado['cultura'].unique():
                    if cultura and cultura.strip():
                        df_cultura_prod = df_prod_filtrado[df_prod_filtrado['cultura'] == cultura]
                        
                        # Verificar se a coluna 'cultura' existe nos insumos
                        if 'cultura' in df_ins_filtrado.columns:
                            df_cultura_ins = df_ins_filtrado[df_ins_filtrado['cultura'] == cultura]
                            custo_total = df_cultura_ins['custo_total'].sum() if not df_cultura_ins.empty else 0
                        else:
                            custo_total = 0
                        
                        rec_primeira, rec_segunda, rec_total = calcular_receita_total(df_cultura_prod)
                        lucro = rec_total - custo_total
                        
                        if custo_total > 0:
                            roi = (lucro / custo_total) * 100
                        else:
                            roi = 0
                            
                        rentabilidade_data.append({
                            'Cultura': cultura,
                            'Receita Total': rec_total,
                            'Custo Total': custo_total,
                            'Lucro': lucro,
                            'ROI (%)': roi
                        })
                
                if rentabilidade_data:
                    df_rentabilidade = pd.DataFrame(rentabilidade_data)
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        fig = px.bar(df_rentabilidade, x='Cultura', y='Lucro',
                                    title='💵 Lucro por Cultura')
                        st.plotly_chart(fig, use_container_width=True)
                    
                    with col2:
                        fig = px.bar(df_rentabilidade, x='Cultura', y='ROI (%)',
                                    title='📈 ROI (%) por Cultura')
                        st.plotly_chart(fig, use_container_width=True)
                    
                    # Mostrar tabela detalhada
                    st.dataframe(df_rentabilidade.sort_values('Lucro', ascending=False), use_container_width=True)
                else:
                    st.info("ℹ️ Não há dados suficientes para análise de rentabilidade por cultura")
    
    # Análise de Correlação e Insights
    st.header("🔍 Insights e Correlações")
    
    if not df_prod_filtrado.empty:
        col1, col2 = st.columns(2)
        
        with col1:
            correlacao_cols = ['caixas', 'temperatura', 'umidade', 'chuva']
            cols_disponiveis = [col for col in correlacao_cols if col in df_prod_filtrado.columns]
            
            if len(cols_disponiveis) > 1:
                correlacao = df_prod_filtrado[cols_disponiveis].corr()
                fig = px.imshow(correlacao, text_auto=True, aspect="auto",
                               title='📊 Correlação: Clima vs Produção')
                st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            if 'area' in df_prod_filtrado.columns:
                top_areas = df_prod_filtrado.groupby('area')['caixas'].sum().nlargest(5)
                if not top_areas.empty:
                    fig = px.bar(x=top_areas.index, y=top_areas.values,
                                title='🏆 Top 5 Áreas por Produção')
                    st.plotly_chart(fig, use_container_width=True)
    
    # Recomendações baseadas em dados
    st.header("🎯 Recomendações Estratégicas")
    
    insights = []
    
    if not df_prod_filtrado.empty:
        # Verificar culturas mais rentáveis
        rentabilidade_data = []
        for cultura in df_prod_filtrado['cultura'].unique():
            if cultura and cultura.strip():
                df_cultura_prod = df_prod_filtrado[df_prod_filtrado['cultura'] == cultura]
                
                # Verificar se a coluna 'cultura' existe nos insumos
                if 'cultura' in df_ins_filtrado.columns:
                    df_cultura_ins = df_ins_filtrado[df_ins_filtrado['cultura'] == cultura]
                    custo_total = df_cultura_ins['custo_total'].sum() if not df_cultura_ins.empty else 0
                else:
                    custo_total = 0
                
                rec_primeira, rec_segunda, rec_total = calcular_receita_total(df_cultura_prod)
                lucro = rec_total - custo_total
                
                if custo_total > 0:
                    roi = (lucro / custo_total) * 100
                else:
                    roi = 0
                    
                rentabilidade_data.append({
                    'Cultura': cultura,
                    'Lucro': lucro,
                    'ROI': roi
                })
        
        if rentabilidade_data:
            df_rentabilidade = pd.DataFrame(rentabilidade_data)
            if not df_rentabilidade.empty:
                cultura_lucrativa = df_rentabilidade.nlargest(1, 'ROI')['Cultura'].iloc[0]
                roi_max = df_rentabilidade.nlargest(1, 'ROI')['ROI'].iloc[0]
                insights.append(f"✅ **{cultura_lucrativa}** é a cultura mais rentável (ROI: {roi_max:.1f}%)")
    
    if 'pct_segunda' in locals() and pct_segunda > config.get('alerta_pct_segunda', 25):
        insights.append(f"⚠️ **Alerta**: Percentual de 2ª qualidade ({pct_segunda:.1f}%) acima do limite recomendado")
    
    if not df_prod_filtrado.empty and 'area' in df_prod_filtrado.columns:
        prod_area = df_prod_filtrado.groupby('area')['caixas'].mean()
        if not prod_area.empty:
            area_baixa = prod_area.idxmin()
            prod_baixa = prod_area.min()
            insights.append(f"🔍 **Oportunidade**: Área {area_baixa} tem a menor produtividade média ({prod_baixa:.1f} caixas/dia)")
    
    for insight in insights:
        st.info(insight)
    
    if not df_prod_filtrado.empty:
        st.download_button(
            "📊 Exportar Relatório de Análise",
            data=df_prod_filtrado.to_csv(index=False),
            file_name="relatorio_analise.csv",
            mime="text/csv"
        )

def pagina_configuracoes():
    """Página de configurações do sistema"""
    st.title("⚙️ Configurações do Sistema")
    
    tab1, tab2, tab3 = st.tabs(["Geral", "Preços Culturas", "Custos Insumos"])
    
    with tab1:
        st.subheader("Configurações Gerais")
        cidade_new = st.text_input("Cidade padrão para clima", value=config.get("cidade", CIDADE_PADRAO))
        
        pct_alert = st.number_input("Alerta % de segunda qualidade", 
                                   min_value=0.0, max_value=100.0, 
                                   value=float(config.get("alerta_pct_segunda", 25.0)))
        
        prod_alert = st.number_input("Alerta produção baixa (%)", 
                                    min_value=0.0, max_value=100.0,
                                    value=float(config.get("alerta_prod_baixo_pct", 30.0)))
        
        preco_padrao_primeira = st.number_input("Preço padrão caixa 1ª (R$)", min_value=0.0, 
                                     value=float(config.get("preco_padrao_primeira", 30.0)))
        
        preco_padrao_segunda = st.number_input("Preço padrão caixa 2ª (R$)", min_value=0.0,
                                       value=float(config.get("preco_padrao_segunda", 15.0)))
    
    with tab2:
        st.subheader("Preços por Cultura")
        st.info("Configure os preços específicos para cada cultura")
        
        # Lista de culturas únicas do banco de dados
        df_prod = carregar_tabela("producao")
        culturas_unicas = sorted([c for c in df_prod['cultura'].unique() if c and c.strip()])
        
        # Adicionar culturas padrão que não estão no banco ainda
        for cultura in DADOS_AGRONOMICOS.keys():
            if cultura not in culturas_unicas:
                culturas_unicas.append(cultura)
        
        cultura_selecionada = st.selectbox("Selecione a cultura:", culturas_unicas)
        
        if cultura_selecionada:
            preco_atual_primeira = obter_preco_cultura(cultura_selecionada, "primeira")
            preco_atual_segunda = obter_preco_cultura(cultura_selecionada, "segunda")
            
            col1, col2 = st.columns(2)
            with col1:
                novo_preco_primeira = st.number_input("Preço 1ª Qualidade (R$)", 
                                                    value=float(preco_atual_primeira),
                                                    min_value=0.0, step=0.5)
            with col2:
                novo_preco_segunda = st.number_input("Preço 2ª Qualidade (R$)", 
                                                   value=float(preco_atual_segunda),
                                                   min_value=0.0, step=0.5)
            
            if st.button(f"Salvar preços para {cultura_selecionada}"):
                salvar_preco_cultura(cultura_selecionada, novo_preco_primeira, novo_preco_segunda)
                st.success(f"Preços para {cultura_selecionada} salvos com sucesso!")
                # Atualizar o dicionário de preços
                global precos_culturas
                precos_culturas = carregar_precos_culturas()
        
        # Tabela de preços atuais
        st.subheader("Tabela de Preços Atuais")
        precos_lista = []
        for cultura, precos in precos_culturas.items():
            precos_lista.append({
                'Cultura': cultura,
                'Preço 1ª': precos['preco_primeira'],
                'Preço 2ª': precos['preco_segunda']
            })
        
        if precos_lista:
            df_precos = pd.DataFrame(precos_lista)
            st.dataframe(df_precos, use_container_width=True)
    
    with tab3:
        st.subheader("Custos Médios de Insumos")
        st.info("Configure os preços de referência para cada tipo de insumo")
        
        custos_medios = config.get("custo_medio_insumos", {})
        novos_custos = {}
        
        for tipo in TIPOS_INSUMOS:
            valor_atual = custos_medios.get(tipo, 0.0)
            novo_valor = st.number_input(f"{tipo} (R$)", min_value=0.0, value=float(valor_atual), key=f"custo_{tipo}")
            novos_custos[tipo] = novo_valor
        
        config["custo_medio_insumos"] = novos_custos
    
    if st.button("Salvar Configurações Gerais"):
        config["cidade"] = cidade_new
        config["alerta_pct_segunda"] = float(pct_alert)
        config["alerta_prod_baixo_pct"] = float(prod_alert)
        config["preco_padrao_primeira"] = float(preco_padrao_primeira)
        config["preco_padrao_segunda"] = float(preco_padrao_segunda)
        salvar_config(config)
        st.success("Configurações salvas com sucesso!")

# ===============================
# MENU PRINCIPAL
# ===============================
def main():
    """Função principal da aplicação"""
    # Inicialização
    criar_tabelas()
    global config, precos_culturas
    config = carregar_config()
    precos_culturas = carregar_precos_culturas()
    
    # Sidebar
    st.sidebar.title("📌 Menu Navegação")
    pagina = st.sidebar.radio("Escolha a página:", 
                            ["Dashboard", "Cadastro Produção", "Cadastro Insumos", 
                             "Análise", "Recomendações Agronômicas", "Configurações"])
    
    # Navegação
    if pagina == "Dashboard":
        pagina_dashboard()
    elif pagina == "Cadastro Produção":
        pagina_cadastro_producao()
    elif pagina == "Cadastro Insumos":
        pagina_cadastro_insumos()
    elif pagina == "Análise":
        pagina_analise()
    elif pagina == "Recomendações Agronômicas":
        mostrar_modulo_agronomico()
    elif pagina == "Configurações":
        pagina_configuracoes()
    
    # Exportar dados
    st.sidebar.markdown("---")
    st.sidebar.subheader("📤 Exportar Dados")
    
    if st.sidebar.button("Exportar Produção Excel"):
        df_export = carregar_tabela("producao")
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_export.to_excel(writer, sheet_name='Produção', index=False)
            workbook = writer.book
            worksheet = writer.sheets['Produção']
            format_header = workbook.add_format({'bold': True, 'bg_color': '#2c3e50', 'font_color': 'white'})
            for col_num, value in enumerate(df_export.columns.values):
                worksheet.write(0, col_num, value, format_header)
        
        output.seek(0)
        st.sidebar.download_button(
            "📥 Baixar Produção", 
            data=output, 
            file_name="producao_exportada.xlsx", 
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    
    if st.sidebar.button("Exportar Insumos Excel"):
        df_export = carregar_tabela("insumos")
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_export.to_excel(writer, sheet_name='Insumos', index=False)
            workbook = writer.book
            worksheet = writer.sheets['Insumos']
            format_header = workbook.add_format({'bold': True, 'bg_color': '#2c3e50', 'font_color': 'white'})
            for col_num, value in enumerate(df_export.columns.values):
                worksheet.write(0, col_num, value, format_header)
        
        output.seek(0)
        st.sidebar.download_button(
            "📥 Baixar Insumos", 
            data=output, 
            file_name="insumos_exportados.xlsx", 
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    
    st.sidebar.markdown("---")
    st.sidebar.info("🌱 Desenvolvido para otimizar a gestão agrícola")

# ===============================
# EXECUÇÃO PRINCIPAL
# ===============================
if __name__ == "__main__":
    main()
