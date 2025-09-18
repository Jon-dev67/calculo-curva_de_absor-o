import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import requests
import urllib.parse
import json
import os
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
st.set_page_config(page_title="🌱 Gerenciador Integrado de Produção", layout="wide")
plt.style.use("dark_background")
sns.set_theme(style="darkgrid")

DB_NAME = "dados_sitio.db"
CONFIG_FILE = "config.json"
API_KEY = "eef20bca4e6fb1ff14a81a3171de5cec"  # OpenWeather API Key
CIDADE_PADRAO = "Londrina"

# Tipos de insumos pré-definidos para padronização
TIPOS_INSUMOS = [
    "Adubo Orgânico", "Adubo Químico", "Defensivo Agrícola", 
    "Semente", "Muda", "Fertilizante Foliar", 
    "Corretivo de Solo", "Insumo para Irrigação", "Outros"
]

UNIDADES = ["kg", "g", "L", "mL", "unidade", "saco", "caixa", "pacote"]

# ===============================
# BANCO DE DADOS
# ===============================
def criar_tabelas():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Tabela de produção
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS producao (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data TEXT,
        estufa TEXT,
        cultura TEXT,
        caixas INTEGER,
        caixas_segunda INTEGER,
        temperatura REAL,
        umidade REAL,
        chuva REAL,
        observacao TEXT
    )
    """)
    
    # Tabela de insumos (ampliada)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS insumos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data TEXT,
        estufa TEXT,
        cultura TEXT,
        tipo TEXT,
        quantidade REAL,
        unidade TEXT,
        custo_unitario REAL,
        custo_total REAL,
        fornecedor TEXT,
        lote TEXT,
        observacoes TEXT
    )
    """)
    
    # Nova tabela para custos operacionais
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS custos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data TEXT,
        tipo TEXT,
        descricao TEXT,
        valor REAL,
        area TEXT,
        observacoes TEXT
    )
    """)
    
    conn.commit()
    conn.close()

def inserir_tabela(nome_tabela, df):
    conn = sqlite3.connect(DB_NAME)
    df.to_sql(nome_tabela, conn, if_exists="append", index=False)
    conn.close()

def carregar_tabela(nome_tabela):
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql(f"SELECT * FROM {nome_tabela}", conn)
    conn.close()
    return df

def excluir_linha(nome_tabela, row_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(f"DELETE FROM {nome_tabela} WHERE id=?", (row_id,))
    conn.commit()
    conn.close()

criar_tabelas()

# ===============================
# CONFIGURAÇÕES
# ===============================
def carregar_config():
    if not os.path.exists(CONFIG_FILE):
        cfg = {
            "cidade": CIDADE_PADRAO,
            "fenologia": {
                "estagios": [
                    {"nome": "Germinação/Vegetativo", "dias": "0-30", "adubo": 2.0, "agua": 1.5},
                    {"nome": "Floração", "dias": "31-60", "adubo": 4.0, "agua": 2.0},
                    {"nome": "Frutificação", "dias": "61-90", "adubo": 3.0, "agua": 2.5},
                    {"nome": "Maturação", "dias": "91-120", "adubo": 1.0, "agua": 1.0}
                ]
            },
            "alerta_pct_segunda": 25.0,
            "alerta_prod_baixo_pct": 30.0,
            "preco_medio_caixa": 30.0,
            "custo_medio_insumos": {
                "Adubo Orgânico": 2.5,
                "Adubo Químico": 4.0,
                "Defensivo Agrícola": 35.0,
                "Semente": 0.5,
                "Muda": 1.2,
                "Fertilizante Foliar": 15.0,
                "Corretivo de Solo": 1.8,
                "Insumo para Irrigação": 0.0,
                "Outros": 0.0
            }
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=4)
        return cfg
    
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def salvar_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=4)

config = carregar_config()

# ===============================
# FUNÇÕES UTILITÁRIAS
# ===============================
def buscar_clima(cidade):
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
                    "Data": item["dt_txt"],
                    "Temp Real (°C)": item["main"]["temp"],
                    "Temp Média (°C)": (item["main"]["temp_min"] + item["main"]["temp_max"]) / 2,
                    "Temp Min (°C)": item["main"]["temp_min"],
                    "Temp Max (°C)": item["main"]["temp_max"],
                    "Umidade (%)": item["main"]["humidity"]
                })
                
        return atual, pd.DataFrame(previsao)
    except:
        return None, None

def normalizar_colunas(df):
    df = df.copy()
    col_map = {
        "Estufa": "estufa", "Área": "estufa", "Produção": "caixas", 
        "Primeira": "caixas", "Segunda": "caixas_segunda", 
        "Qtd": "caixas", "Quantidade": "caixas", "Data": "data"
    }
    df.rename(columns={c: col_map.get(c, c) for c in df.columns}, inplace=True)
    
    if "data" in df.columns: 
        df["data"] = pd.to_datetime(df["data"], errors="coerce").dt.strftime('%Y-%m-%d')
    
    for col in ["caixas", "caixas_segunda", "temperatura", "umidade", "chuva"]:
        if col not in df.columns: 
            df[col] = 0
    
    if "estufa" not in df.columns: 
        df["estufa"] = ""
    
    if "cultura" not in df.columns: 
        df["cultura"] = ""
    
    return df

def plot_bar_sum(ax, df, x, y, titulo, ylabel, palette="tab20"):
    if df.empty:
        ax.set_axis_off()
        return
        
    g = df.groupby(x)[y].sum().reset_index()
    if g.empty: 
        ax.set_axis_off()
        return
        
    sns.barplot(data=g, x=x, y=y, ax=ax, palette=palette)
    ax.set_title(titulo, fontsize=14)
    ax.set_ylabel(ylabel)
    ax.set_xlabel("")
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    
    for c in ax.containers: 
        ax.bar_label(c, fmt="%.0f")

def calcular_estagio_fenologico(data_plantio):
    """Calcula o estágio fenológico com base na data de plantio"""
    if not data_plantio:
        return "Não especificado"
        
    try:
        dias = (datetime.now() - datetime.strptime(data_plantio, "%Y-%m-%d")).days
        
        for estagio in config["fenologia"]["estagios"]:
            dias_range = estagio["dias"].split("-")
            if len(dias_range) == 2 and dias >= int(dias_range[0]) and dias <= int(dias_range[1]):
                return estagio["nome"]
                
        return "Colheita concluída"
    except:
        return "Data inválida"

def recomendar_adubacao(estagio):
    """Retorna recomendação de adubação baseada no estágio fenológico"""
    for e in config["fenologia"]["estagios"]:
        if e["nome"] == estagio:
            return f"Recomendado: {e['adubo']}kg/ha de adubo e {e['agua']}L/planta de água"
    
    return "Sem recomendação específica"

# ===============================
# SIDEBAR / MENU
# ===============================
st.sidebar.title("📌 Menu Navegação")
pagina = st.sidebar.radio("Escolha a página:", 
                         ["Dashboard", "Cadastro Produção", "Cadastro Insumos", "Análise", "Configurações"])

# ===============================
# PÁGINA: DASHBOARD
# ===============================
if pagina == "Dashboard":
    st.title("🌱 Dashboard de Produção")
    
    # Carregar dados
    df_prod = carregar_tabela("producao")
    df_ins = carregar_tabela("insumos")
    
    # KPIs principais
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_caixas = df_prod["caixas"].sum() if not df_prod.empty else 0
        total_segunda = df_prod["caixas_segunda"].sum() if not df_prod.empty else 0
        st.metric("📦 Caixas 1ª Qualidade", f"{total_caixas:.0f}")
    
    with col2:
        st.metric("🔄 Caixas 2ª Qualidade", f"{total_segunda:.0f}")
    
    with col3:
        total_insumos = df_ins["custo_total"].sum() if not df_ins.empty else 0
        st.metric("💰 Custo Insumos", f"R$ {total_insumos:,.2f}")
    
    with col4:
        receita_estimada = total_caixas * config.get("preco_medio_caixa", 30)
        lucro_estimado = receita_estimada - total_insumos if receita_estimada else 0
        st.metric("💵 Lucro Estimado", f"R$ {lucro_estimado:,.2f}")
    
    # Alertas
    st.subheader("⚠️ Alertas e Recomendações")
    
    if not df_prod.empty:
        # Alertas de produção
        df_prod["pct_segunda"] = np.where(
            (df_prod["caixas"] + df_prod["caixas_segunda"]) > 0,
            df_prod["caixas_segunda"] / (df_prod["caixas"] + df_prod["caixas_segunda"]) * 100,
            0
        )
        
        alta_segunda = df_prod[df_prod["pct_segunda"] > config.get("alerta_pct_segunda", 25)]
        if not alta_segunda.empty:
            st.warning(f"Alto percentual de 2ª qualidade ({alta_segunda['pct_segunda'].mean():.1f}%)")
        
        # Alertas de clima
        ultimo_clima = df_prod.iloc[-1] if not df_prod.empty else None
        if ultimo_clima is not None and ultimo_clima["umidade"] > 85:
            st.error("Alerta: Umidade muito alta, risco de doenças fúngicas!")
        
        if ultimo_clima is not None and ultimo_clima["temperatura"] < 10:
            st.error("Alerta: Temperatura muito baixa, risco de danos às plantas!")
    
    # Gráficos resumos
    st.subheader("📊 Visão Geral")
    
    if not df_prod.empty:
        col1, col2 = st.columns(2)
        
        with col1:
            # Produção por estufa
            prod_estufa = df_prod.groupby("estufa")[["caixas", "caixas_segunda"]].sum().reset_index()
            if not prod_estufa.empty:
                fig = px.bar(prod_estufa, x="estufa", y=["caixas", "caixas_segunda"], 
                            title="Produção por Estufa", barmode="group")
                st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            # Evolução temporal
            df_prod["data"] = pd.to_datetime(df_prod["data"])
            prod_temporal = df_prod.groupby("data")[["caixas", "caixas_segunda"]].sum().reset_index()
            if not prod_temporal.empty:
                fig = px.line(prod_temporal, x="data", y=["caixas", "caixas_segunda"], 
                             title="Evolução da Produção", markers=True)
                st.plotly_chart(fig, use_container_width=True)
    
    if not df_ins.empty:
        col1, col2 = st.columns(2)
        
        with col1:
            # Custos por tipo de insumo
            custos_tipo = df_ins.groupby("tipo")["custo_total"].sum().reset_index()
            if not custos_tipo.empty:
                fig = px.pie(custos_tipo, values="custo_total", names="tipo", 
                            title="Distribuição de Custos por Tipo")
                st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            # Custos por cultura
            custos_cultura = df_ins.groupby("cultura")["custo_total"].sum().reset_index()
            if not custos_cultura.empty:
                fig = px.bar(custos_cultura, x="cultura", y="custo_total", 
                            title="Custos por Cultura")
                st.plotly_chart(fig, use_container_width=True)

# ===============================
# PÁGINA: CADASTRO PRODUÇÃO
# ===============================
elif pagina == "Cadastro Produção":
    st.title("📝 Cadastro de Produção")
    df = carregar_tabela("producao")
    cidade = st.sidebar.text_input("🌍 Cidade para clima", value=config.get("cidade", CIDADE_PADRAO))

    with st.form("form_cadastro_producao", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        with col1: 
            data_val = st.date_input("Data", value=date.today())
            estufa = st.text_input("Estufa/Área")
        with col2: 
            cultura = st.text_input("Cultura")
            caixas = st.number_input("Caixas (1ª)", min_value=0, step=1)
        with col3: 
            caixas2 = st.number_input("Caixas (2ª)", min_value=0, step=1)
            observacao = st.text_input("Observações")
        
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
                "data": str(data_val),
                "estufa": estufa.strip(),
                "cultura": cultura.strip(),
                "caixas": int(caixas),
                "caixas_segunda": int(caixas2),
                "temperatura": float(temperatura),
                "umidade": float(umidade),
                "chuva": float(chuva),
                "observacao": observacao
            }])
            inserir_tabela("producao", novo)
            st.success("Registro salvo com sucesso!")

    if not df.empty:
        st.markdown("### 📋 Registros recentes")
        df_display = df.sort_values("data", ascending=False).head(15)
        st.dataframe(df_display, use_container_width=True)
        
        # Excluir linha
        ids = st.multiselect("Selecione ID(s) para excluir", df["id"].tolist())
        if st.button("Excluir selecionados"):
            for i in ids: 
                excluir_linha("producao", i)
            st.success("✅ Linhas excluídas!")
            st.rerun()

    # Import Excel
    st.subheader("📂 Importar Excel")
    uploaded_file = st.file_uploader("Envie planilha Excel (Produção)", type=["xlsx"])
    if uploaded_file:
        df_excel = pd.read_excel(uploaded_file)
        df_excel = normalizar_colunas(df_excel)
        inserir_tabela("producao", df_excel)
        st.success("✅ Dados importados do Excel!")
        st.rerun()

# ===============================
# PÁGINA: CADASTRO INSUMOS
# ===============================
elif pagina == "Cadastro Insumos":
    st.title("📦 Cadastro de Insumos")
    df_ins = carregar_tabela("insumos")
    
    with st.form("form_insumos", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            data_i = st.date_input("Data", value=date.today())
            estufa_i = st.text_input("Estufa/Área")
            cultura_i = st.text_input("Cultura (opcional)")
            tipo_i = st.selectbox("Tipo de Insumo", TIPOS_INSUMOS)
            fornecedor_i = st.text_input("Fornecedor (opcional)")
            
        with col2:
            qtd_i = st.number_input("Quantidade", min_value=0.0, step=0.1)
            un_i = st.selectbox("Unidade", UNIDADES)
            custo_unit_i = st.number_input("Custo Unitário (R$)", min_value=0.0, step=0.01, value=0.0)
            custo_total_i = st.number_input("Custo Total (R$)", min_value=0.0, step=0.01, 
                                          value=0.0, 
                                          help="Se não preenchido, será calculado automaticamente")
            lote_i = st.text_input("Nº Lote (opcional)")
            
        observacoes_i = st.text_area("Observações")
        
        # Calcular custo total automaticamente se necessário
        if custo_unit_i > 0 and qtd_i > 0 and custo_total_i == 0:
            custo_total_i = custo_unit_i * qtd_i
            st.info(f"Custo total calculado: R$ {custo_total_i:.2f}")
            
        enviado_i = st.form_submit_button("Salvar Insumo ✅")
        if enviado_i:
            novo = pd.DataFrame([{
                "data": str(data_i),
                "estufa": estufa_i,
                "cultura": cultura_i,
                "tipo": tipo_i,
                "quantidade": qtd_i,
                "unidade": un_i,
                "custo_unitario": custo_unit_i,
                "custo_total": custo_total_i if custo_total_i > 0 else custo_unit_i * qtd_i,
                "fornecedor": fornecedor_i,
                "lote": lote_i,
                "observacoes": observacoes_i
            }])
            inserir_tabela("insumos", novo)
            st.success("Insumo salvo com sucesso!")

    if not df_ins.empty:
        st.subheader("📋 Histórico de Insumos")
        
        # Filtros
        col1, col2, col3 = st.columns(3)
        with col1:
            filtro_tipo = st.multiselect("Filtrar por tipo", options=df_ins["tipo"].unique())
        with col2:
            filtro_estufa = st.multiselect("Filtrar por estufa", options=df_ins["estufa"].unique())
        with col3:
            filtro_cultura = st.multiselect("Filtrar por cultura", options=df_ins["cultura"].unique())
        
        # Aplicar filtros
        df_filtrado = df_ins.copy()
        if filtro_tipo:
            df_filtrado = df_filtrado[df_filtrado["tipo"].isin(filtro_tipo)]
        if filtro_estufa:
            df_filtrado = df_filtrado[df_filtrado["estufa"].isin(filtro_estufa)]
        if filtro_cultura:
            df_filtrado = df_filtrado[df_filtrado["cultura"].isin(filtro_cultura)]
            
        st.dataframe(df_filtrado.sort_values("data", ascending=False).head(20), use_container_width=True)
        
        # Estatísticas de custos
        st.subheader("📊 Estatísticas de Custos")
        if not df_filtrado.empty:
            total_custo = df_filtrado["custo_total"].sum()
            media_custo = df_filtrado["custo_total"].mean()
            st.write(f"**Total gasto:** R$ {total_custo:,.2f} | **Média por registro:** R$ {media_custo:,.2f}")
            
            # Gráfico de evolução de custos
            df_filtrado["data"] = pd.to_datetime(df_filtrado["data"])
            custos_mensais = df_filtrado.groupby(df_filtrado["data"].dt.to_period("M"))["custo_total"].sum().reset_index()
            custos_mensais["data"] = custos_mensais["data"].astype(str)
            
            fig = px.bar(custos_mensais, x="data", y="custo_total", 
                        title="Evolução Mensal de Custos com Insumos")
            st.plotly_chart(fig, use_container_width=True)
        
        # Excluir registros
        ids_insumos = st.multiselect("Selecione ID(s) de insumos para excluir", df_ins["id"].tolist())
        if st.button("Excluir insumos selecionados"):
            for i in ids_insumos: 
                excluir_linha("insumos", i)
            st.success("✅ Insumos excluídos!")
            st.rerun()

    # Import Excel para insumos
    st.subheader("📂 Importar Excel (Insumos)")
    uploaded_file = st.file_uploader("Envie planilha Excel (Insumos)", type=["xlsx"], key="insumos_upload")
    if uploaded_file:
        df_excel = pd.read_excel(uploaded_file)
        df_excel.rename(columns=lambda x: x.lower(), inplace=True)
        inserir_tabela("insumos", df_excel)
        st.success("✅ Dados de insumos importados do Excel!")
        st.rerun()

# ===============================
# PÁGINA: ANÁLISE
# ===============================
elif pagina == "Análise":
    st.title("📊 Análise Avançada de Produção e Custos")
    
    # Carregar dados
    df_prod = carregar_tabela("producao")
    df_ins = carregar_tabela("insumos")
    
    if df_prod.empty and df_ins.empty:
        st.warning("📭 Nenhum dado disponível para análise. Cadastre dados de produção e insumos primeiro.")
        st.stop()
    
    # Filtros avançados na sidebar
    st.sidebar.subheader("🔍 Filtros de Análise")
    
    # Período temporal
    if not df_prod.empty:
        datas_disponiveis = pd.to_datetime(df_prod['data']).sort_values()
        min_date = datas_disponiveis.min().date()
        max_date = datas_disponiveis.max().date()
    else:
        min_date = date.today() - timedelta(days=365)
        max_date = date.today()
    
    date_range = st.sidebar.date_input(
        "📅 Período de análise",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date
    )
    
    if len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date, end_date = min_date, max_date
    
    # Filtros adicionais
    col1, col2 = st.sidebar.columns(2)
    
    with col1:
        if not df_prod.empty:
            estufas_disponiveis = df_prod['estufa'].unique()
            estufas_selecionadas = st.multiselect(
                "🏭 Estufas", 
                options=estufas_disponiveis,
                default=estufas_disponiveis
            )
        else:
            estufas_selecionadas = []
        
        if not df_ins.empty:
            tipos_insumos_disponiveis = df_ins['tipo'].unique()
            tipos_selecionados = st.multiselect(
                "📦 Tipos de Insumos", 
                options=tipos_insumos_disponiveis,
                default=tipos_insumos_disponiveis
            )
        else:
            tipos_selecionados = []
    
    with col2:
        if not df_prod.empty:
            culturas_disponiveis = df_prod['cultura'].unique()
            culturas_selecionadas = st.multiselect(
                "🌱 Culturas", 
                options=culturas_disponiveis,
                default=culturas_disponiveis
            )
        else:
            culturas_selecionadas = []
    
    # Aplicar filtros
    if not df_prod.empty:
        df_prod['data'] = pd.to_datetime(df_prod['data'])
        df_prod_filtrado = df_prod[
            (df_prod['data'] >= pd.to_datetime(start_date)) & 
            (df_prod['data'] <= pd.to_datetime(end_date))
        ]
        if estufas_selecionadas:
            df_prod_filtrado = df_prod_filtrado[df_prod_filtrado['estufa'].isin(estufas_selecionadas)]
        if culturas_selecionadas:
            df_prod_filtrado = df_prod_filtrado[df_prod_filtrado['cultura'].isin(culturas_selecionadas)]
    else:
        df_prod_filtrado = pd.DataFrame()
    
    if not df_ins.empty:
        df_ins['data'] = pd.to_datetime(df_ins['data'])
        df_ins_filtrado = df_ins[
            (df_ins['data'] >= pd.to_datetime(start_date)) & 
            (df_ins['data'] <= pd.to_datetime(end_date))
        ]
        if tipos_selecionados:
            df_ins_filtrado = df_ins_filtrado[df_ins_filtrado['tipo'].isin(tipos_selecionados)]
    else:
        df_ins_filtrado = pd.DataFrame()
    
    # Métricas de performance
    st.header("📈 Métricas de Performance")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if not df_prod_filtrado.empty:
            total_caixas = df_prod_filtrado['caixas'].sum()
            st.metric("📦 Caixas 1ª Qualidade", f"{total_caixas:,.0f}")
        else:
            st.metric("📦 Caixas 1ª Qualidade", "0")
    
    with col2:
        if not df_prod_filtrado.empty:
            total_segunda = df_prod_filtrado['caixas_segunda'].sum()
            pct_segunda = (total_segunda / (total_caixas + total_segunda) * 100) if (total_caixas + total_segunda) > 0 else 0
            st.metric("🔄 % 2ª Qualidade", f"{pct_segunda:.1f}%")
        else:
            st.metric("🔄 % 2ª Qualidade", "0%")
    
    with col3:
        if not df_ins_filtrado.empty:
            custo_total = df_ins_filtrado['custo_total'].sum()
            st.metric("💰 Custo Total", f"R$ {custo_total:,.2f}")
        else:
            st.metric("💰 Custo Total", "R$ 0,00")
    
    with col4:
        if not df_prod_filtrado.empty and not df_ins_filtrado.empty:
            receita_estimada = total_caixas * config.get('preco_medio_caixa', 30)
            lucro = receita_estimada - custo_total
            st.metric("💵 Lucro Estimado", f"R$ {lucro:,.2f}")
        else:
            st.metric("💵 Lucro Estimado", "R$ 0,00")
    
    # Análise de Produção
    if not df_prod_filtrado.empty:
        st.header("🌱 Análise de Produção")
        
        tab1, tab2, tab3, tab4 = st.tabs(["Visão Geral", "Por Cultura", "Por Estufa", "Tendências"])
        
        with tab1:
            col1, col2 = st.columns(2)
            
            with col1:
                # Produção diária
                prod_diaria = df_prod_filtrado.groupby('data')[['caixas', 'caixas_segunda']].sum().reset_index()
                fig = px.line(prod_diaria, x='data', y=['caixas', 'caixas_segunda'],
                             title='📅 Produção Diária', markers=True)
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                # Qualidade da produção
                qualidade_data = pd.DataFrame({
                    'Categoria': ['1ª Qualidade', '2ª Qualidade'],
                    'Quantidade': [total_caixas, total_segunda]
                })
                fig = px.pie(qualidade_data, values='Quantidade', names='Categoria',
                            title='🎯 Distribuição por Qualidade')
                st.plotly_chart(fig, use_container_width=True)
        
        with tab2:
            # Análise por cultura
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
            # Análise por estufa
            prod_estufa = df_prod_filtrado.groupby('estufa')[['caixas', 'caixas_segunda']].sum().reset_index()
            dias_producao = len(df_prod_filtrado['data'].unique())
            prod_estufa['Produtividade'] = prod_estufa['caixas'] / dias_producao if dias_producao > 0 else 0
            
            col1, col2 = st.columns(2)
            
            with col1:
                fig = px.bar(prod_estufa, x='estufa', y='caixas',
                            title='🏭 Produção Total por Estufa')
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                fig = px.bar(prod_estufa, x='estufa', y='Produtividade',
                            title='📈 Produtividade Média Diária')
                st.plotly_chart(fig, use_container_width=True)
        
        with tab4:
            # Análise de tendências
            df_prod_filtrado['semana'] = df_prod_filtrado['data'].dt.isocalendar().week
            prod_semanal = df_prod_filtrado.groupby('semana')[['caixas', 'caixas_segunda']].sum().reset_index()
            
            fig = px.line(prod_semanal, x='semana', y=['caixas', 'caixas_segunda'],
                         title='📈 Tendência Semanal de Produção', markers=True)
            st.plotly_chart(fig, use_container_width=True)
    
    # Análise de Custos
    if not df_ins_filtrado.empty:
        st.header("💰 Análise de Custos")
        
        tab1, tab2, tab3 = st.tabs(["Visão Geral", "Por Tipo", "Eficiência"])
        
        with tab1:
            col1, col2 = st.columns(2)
            
            with col1:
                # Evolução de custos
                custos_mensais = df_ins_filtrado.groupby(df_ins_filtrado['data'].dt.to_period('M'))['custo_total'].sum().reset_index()
                custos_mensais['data'] = custos_mensais['data'].astype(str)
                fig = px.line(custos_mensais, x='data', y='custo_total',
                             title='📅 Evolução Mensal de Custos', markers=True)
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                # Distribuição por cultura
                custos_cultura = df_ins_filtrado.groupby('cultura')['custo_total'].sum().reset_index()
                if not custos_cultura.empty:
                    fig = px.pie(custos_cultura, values='custo_total', names='cultura',
                                title='🌿 Custos por Cultura')
                    st.plotly_chart(fig, use_container_width=True)
        
        with tab2:
            # Análise por tipo de insumo
            custos_tipo = df_ins_filtrado.groupby('tipo')['custo_total'].sum().reset_index()
            custos_tipo = custos_tipo.sort_values('custo_total', ascending=False)
            
            col1, col2 = st.columns(2)
            
            with col1:
                fig = px.bar(custos_tipo, x='tipo', y='custo_total',
                            title='📦 Custos por Tipo de Insumo')
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                fig = px.pie(custos_tipo, values='custo_total', names='tipo',
                            title='📊 Distribuição Percentual')
                st.plotly_chart(fig, use_container_width=True)
        
        with tab3:
            # Análise de eficiência (custo vs produção)
            if not df_prod_filtrado.empty:
                # Agrupar dados por cultura para análise de eficiência
                custos_por_cultura = df_ins_filtrado.groupby('cultura')['custo_total'].sum().reset_index()
                producao_por_cultura = df_prod_filtrado.groupby('cultura')['caixas'].sum().reset_index()
                
                eficiencia = pd.merge(custos_por_cultura, producao_por_cultura, on='cultura', how='inner')
                eficiencia['Custo por Caixa'] = eficiencia['custo_total'] / eficiencia['caixas']
                eficiencia['Custo por Caixa'] = eficiencia['Custo por Caixa'].round(2)
                
                col1, col2 = st.columns(2)
                
                with col1:
                    fig = px.bar(eficiencia, x='cultura', y='Custo por Caixa',
                                title='📊 Custo por Caixa (1ª Qualidade)')
                    st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    st.dataframe(eficiencia[['cultura', 'custo_total', 'caixas', 'Custo por Caixa']]
                                .rename(columns={
                                    'cultura': 'Cultura',
                                    'custo_total': 'Custo Total (R$)',
                                    'caixas': 'Caixas 1ª'
                                }), use_container_width=True)
    
    # Análise de Rentabilidade
    if not df_prod_filtrado.empty and not df_ins_filtrado.empty:
        st.header("💵 Análise de Rentabilidade")
        
        # Calcular receita e lucro por cultura
        receita_por_cultura = df_prod_filtrado.groupby('cultura')['caixas'].sum().reset_index()
        receita_por_cultura['Receita'] = receita_por_cultura['caixas'] * config.get('preco_medio_caixa', 30)
        
        custos_por_cultura = df_ins_filtrado.groupby('cultura')['custo_total'].sum().reset_index()
        
        rentabilidade = pd.merge(receita_por_cultura, custos_por_cultura, on='cultura', how='left').fillna(0)
        rentabilidade['Lucro'] = rentabilidade['Receita'] - rentabilidade['custo_total']
        rentabilidade['Margem'] = (rentabilidade['Lucro'] / rentabilidade['Receita'] * 100).round(1)
        rentabilidade['ROI'] = (rentabilidade['Lucro'] / rentabilidade['custo_total'] * 100).round(1)
        
        col1, col2 = st.columns(2)
        
        with col1:
            fig = px.bar(rentabilidade, x='cultura', y='Lucro',
                        title='📈 Lucro por Cultura')
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            fig = px.bar(rentabilidade, x='cultura', y='Margem',
                        title='📊 Margem de Lucro (%)')
            st.plotly_chart(fig, use_container_width=True)
        
        # Tabela detalhada
        st.subheader("📋 Resumo de Rentabilidade por Cultura")
        rentabilidade_display = rentabilidade[['cultura', 'caixas', 'Receita', 'custo_total', 'Lucro', 'Margem', 'ROI']]
        rentabilidade_display.columns = ['Cultura', 'Caixas 1ª', 'Receita (R$)', 'Custos (R$)', 'Lucro (R$)', 'Margem (%)', 'ROI (%)']
        st.dataframe(rentabilidade_display.style.format({
            'Receita (R$)': '{:,.2f}',
            'Custos (R$)': '{:,.2f}', 
            'Lucro (R$)': '{:,.2f}'
        }), use_container_width=True)
    
    # Relatório de Insights
    st.header("🔍 Insights e Recomendações")
    
    if not df_prod_filtrado.empty:
        # Calcular métricas para insights
        pct_segunda_geral = (df_prod_filtrado['caixas_segunda'].sum() / 
                            (df_prod_filtrado['caixas'].sum() + df_prod_filtrado['caixas_segunda'].sum()) * 100)
        
        # Insights de qualidade
        if pct_segunda_geral > config.get('alerta_pct_segunda', 25):
            st.error(f"⚠️ **Alerta de Qualidade:** Percentual de 2ª qualidade ({pct_segunda_geral:.1f}%) está acima do limite recomendado ({config.get('alerta_pct_segunda', 25)}%). Avalie práticas de cultivo.")
        else:
            st.success(f"✅ **Qualidade:** Percentual de 2ª qualidade ({pct_segunda_geral:.1f}%) dentro dos limites aceitáveis.")
        
        # Insights de produtividade
        prod_diaria_media = df_prod_filtrado['caixas'].sum() / len(df_prod_filtrado['data'].unique()) if len(df_prod_filtrado['data'].unique()) > 0 else 0
        st.info(f"📊 **Produtividade Média Diária:** {prod_diaria_media:.1f} caixas/dia")
    
    if not df_ins_filtrado.empty and not df_prod_filtrado.empty:
        custo_total = df_ins_filtrado['custo_total'].sum()
        receita_total = df_prod_filtrado['caixas'].sum() * config.get('preco_medio_caixa', 30)
        lucro_total = receita_total - custo_total
        margem_total = (lucro_total / receita_total * 100) if receita_total > 0 else 0
        
        st.info(f"💰 **Rentabilidade Geral:** Margem de {margem_total:.1f}% | Lucro: R$ {lucro_total:,.2f}")
        
        if margem_total < 20:
            st.warning("📉 **Alerta de Rentabilidade:** Margem abaixo de 20%. Considere revisar custos ou preços.")
        
        # Identificar culturas mais lucrativas
        if 'rentabilidade' in locals():
            cultura_mais_lucrativa = rentabilidade.loc[rentabilidade['Lucro'].idxmax()] if not rentabilidade.empty else None
            if cultura_mais_lucrativa is not None:
                st.success(f"🏆 **Cultura mais lucrativa:** {cultura_mais_lucrativa['cultura']} (Lucro: R$ {cultura_mais_lucrativa['Lucro']:,.2f})")

# ===============================
# PÁGINA: CONFIGURAÇÕES
# ===============================
elif pagina == "Configurações":
    st.title("⚙️ Configurações do Sistema")
    
    tab1, tab2, tab3 = st.tabs(["Geral", "Fenologia", "Alertas & Preços"])
    
    with tab1:
        st.subheader("Configurações Gerais")
        cidade_nova = st.text_input("Cidade padrão para clima", value=config.get("cidade", CIDADE_PADRAO))
        
        if st.button("Salvar Configurações Gerais"):
            config["cidade"] = cidade_nova
            salvar_config(config)
            st.success("Configurações salvas!")
    
    with tab2:
        st.subheader("Estágios Fenológicos")
        st.info("Configure os estágios de desenvolvimento das culturas e suas necessidades")
        
        for i, estagio in enumerate(config["fenologia"]["estagios"]):
            with st.expander(f"Estágio: {estagio['nome']}"):
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    nome = st.text_input("Nome", value=estagio["nome"], key=f"nome_{i}")
                with col2:
                    dias = st.text_input("Duração (dias)", value=estagio["dias"], key=f"dias_{i}")
                with col3:
                    adubo = st.number_input("Adubo (kg/ha)", value=float(estagio["adubo"]), key=f"adubo_{i}")
                with col4:
                    agua = st.number_input("Água (L/planta)", value=float(estagio["agua"]), key=f"agua_{i}")
                
                config["fenologia"]["estagios"][i] = {
                    "nome": nome, "dias": dias, "adubo": adubo, "agua": agua
                }
        
        if st.button("Salvar Configurações Fenológicas"):
            salvar_config(config)
            st.success("Configurações fenológicas salvas!")
    
    with tab3:
        st.subheader("Alertas e Preços")
        
        col1, col2 = st.columns(2)
        
        with col1:
            alerta_segunda = st.number_input(
                "Alerta % 2ª Qualidade (%)", 
                min_value=0.0, max_value=100.0, value=float(config.get("alerta_pct_segunda", 25.0))
            )
            
            alerta_prod_baixo = st.number_input(
                "Alerta Produção Baixa (%)", 
                min_value=0.0, max_value=100.0, value=float(config.get("alerta_prod_baixo_pct", 30.0))
            )
            
            preco_caixa = st.number_input(
                "Preço Médio Caixa (R$)", 
                min_value=0.0, value=float(config.get("preco_medio_caixa", 30.0))
            )
        
        with col2:
            st.subheader("Custos Médios por Tipo")
            for tipo, custo in config.get("custo_medio_insumos", {}).items():
                novo_custo = st.number_input(
                    f"{tipo} (R$)", 
                    min_value=0.0, value=float(custo), key=f"custo_{tipo}"
                )
                config["custo_medio_insumos"][tipo] = novo_custo
        
        if st.button("Salvar Alertas e Preços"):
            config["alerta_pct_segunda"] = alerta_segunda
            config["alerta_prod_baixo_pct"] = alerta_prod_baixo
            config["preco_medio_caixa"] = preco_caixa
            salvar_config(config)
            st.success("Configurações de alertas e preços salvas!")
    
    # Backup e Restauração
    st.subheader("💾 Backup dos Dados")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("Fazer Backup"):
            conn = sqlite3.connect(DB_NAME)
            backup_data = {}
            for table in ["producao", "insumos", "custos"]:
                df = pd.read_sql(f"SELECT * FROM {table}", conn)
                backup_data[table] = df.to_dict()
            
            with open("backup_dados.json", "w", encoding="utf-8") as f:
                json.dump(backup_data, f, ensure_ascii=False, indent=4)
            
            st.success("Backup realizado com sucesso!")
    
    with col2:
        uploaded_backup = st.file_uploader("Restaurar Backup", type=["json"])
        if uploaded_backup and st.button("Restaurar Dados"):
            backup_data = json.load(uploaded_backup)
            conn = sqlite3.connect(DB_NAME)
            
            for table, data in backup_data.items():
                df = pd.DataFrame(data)
                df.to_sql(table, conn, if_exists="replace", index=False)
            
            st.success("Dados restaurados com sucesso!")
            st.rerun()

# ===============================
# RODAPÉ
# ===============================
st.sidebar.markdown("---")
st.sidebar.info("🌱 **Gerenciador Integrado de Produção Agrícola** v1.0")
