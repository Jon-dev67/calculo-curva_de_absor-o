import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import requests
import urllib.parse
from datetime import date, datetime, timedelta
from io import BytesIO
import json
import numpy as np
import warnings
warnings.filterwarnings('ignore')

# ================================
# CONFIGURAÇÕES INICIAIS
# ================================
st.set_page_config(
    page_title="🌱 Gerenciador Avançado de Produção",
    layout="wide",
    initial_sidebar_state="expanded",
)
plt.style.use("dark_background")

ARQUIVO_DADOS = "colheitas.xlsx"
ARQUIVO_INSUMOS = "insumos.xlsx"
ARQUIVO_CONFIG = "config_precos.json"
API_KEY = "sua_chave_openweather_aqui"  # Substitua pela sua chave real
CIDADE_PADRAO = "Londrina"

# ================================
# FUNÇÕES AUXILIARES
# ================================
def carregar_dados():
    try:
        return pd.read_excel(ARQUIVO_DADOS)
    except:
        return pd.DataFrame(columns=["Data","Local","Produto","Caixas","Caixas de Segunda","Temperatura","Umidade","Chuva"])

def salvar_dados(df):
    df.to_excel(ARQUIVO_DADOS, index=False)

def carregar_insumos():
    try:
        return pd.read_excel(ARQUIVO_INSUMOS)
    except:
        return pd.DataFrame(columns=["Data", "Tipo", "Descricao", "Quantidade", "Unidade", "Custo", "Local"])

def salvar_insumos(df):
    df.to_excel(ARQUIVO_INSUMOS, index=False)

def carregar_config_precos():
    try:
        with open(ARQUIVO_CONFIG, 'r') as f:
            return json.load(f)
    except:
        return {
            "preco_primeira": 10.0,
            "preco_segunda": 5.0,
            "custos_fixos": 1000.0
        }

def salvar_config_precos(config):
    with open(ARQUIVO_CONFIG, 'w') as f:
        json.dump(config, f)

def normalizar_colunas(df):
    df = df.copy()
    col_map = {
        "Estufa":"Local",
        "Área":"Local",
        "Produção":"Caixas",
        "Primeira":"Caixas",
        "Segunda":"Caixas de Segunda",
        "Qtd":"Caixas",
        "Quantidade":"Caixas",
    }
    df.rename(columns={c:col_map.get(c,c) for c in df.columns}, inplace=True)
    if "Data" in df.columns:
        df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    for col in ["Caixas","Caixas de Segunda","Temperatura","Umidade","Chuva"]:
        if col not in df.columns:
            df[col] = 0
    if "Local" not in df.columns: df["Local"] = ""
    if "Produto" not in df.columns: df["Produto"] = ""
    return df

def plot_bar(ax, x, y, df, cores, titulo, ylabel):
    df.groupby(x)[y].sum().plot(kind="bar", ax=ax, color=cores, width=0.6)
    ax.set_title(titulo, fontsize=14)
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", linestyle="--", alpha=0.7)
    for p in ax.patches:
        ax.text(p.get_x() + p.get_width()/2, p.get_height() + 0.01*df[y].max(), 
                f"{int(p.get_height())}", ha="center")

def clima_atual(cidade):
    """Busca clima atual no OpenWeather"""
    try:
        city_encoded = urllib.parse.quote(cidade)
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city_encoded}&appid={API_KEY}&units=metric&lang=pt_br"
        r = requests.get(url)
        data = r.json()
        if r.status_code != 200:
            return None
        return {
            "temp": data["main"]["temp"],
            "umidade": data["main"]["humidity"],
            "chuva": data.get("rain", {}).get("1h", 0)
        }
    except:
        return None

def analisar_tendencias_simples(df):
    """Analisa tendências usando métodos estatísticos simples"""
    if len(df) < 5:
        return {"mensagem": "Dados insuficientes para análise (mínimo 5 registros)"}
    
    try:
        # Análise de tendência temporal
        df_temporal = df.copy()
        df_temporal['Mes'] = df_temporal['Data'].dt.to_period('M')
        tendencia_mensal = df_temporal.groupby('Mes')['Total'].sum().pct_change().mean() * 100
        
        # Correlações simples
        correlacoes = {
            "temp_producao": df['Temperatura'].corr(df['Total']),
            "umidade_producao": df['Umidade'].corr(df['Total']),
            "chuva_producao": df['Chuva'].corr(df['Total'])
        }
        
        # Previsão simples baseada na média móvel
        if len(df) >= 3:
            media_movel = df['Total'].rolling(window=3).mean().iloc[-1]
            previsao = media_movel * 30  # Estimativa mensal
        else:
            previsao = df['Total'].mean() * 30
        
        return {
            "tendencia_mensal": tendencia_mensal,
            "correlacoes": correlacoes,
            "previsao_mensal": previsao,
            "status": "Crescimento" if tendencia_mensal > 0 else "Queda" if tendencia_mensal < 0 else "Estável"
        }
    except Exception as e:
        return {"erro": f"Erro na análise: {str(e)}"}

def calcular_balanco(df_colheitas, df_insumos, config):
    """Calcula balanço financeiro"""
    receita_primeira = df_colheitas['Caixas'].sum() * config['preco_primeira']
    receita_segunda = df_colheitas['Caixas de Segunda'].sum() * config['preco_segunda']
    custos_insumos = df_insumos['Custo'].sum() if not df_insumos.empty else 0
    custos_totais = custos_insumos + config['custos_fixos']
    
    receita_total = receita_primeira + receita_segunda
    lucro = receita_total - custos_totais
    margem_lucro = (lucro / receita_total * 100) if receita_total > 0 else 0
    
    return {
        "receita_total": receita_total,
        "receita_primeira": receita_primeira,
        "receita_segunda": receita_segunda,
        "custos_insumos": custos_insumos,
        "custos_fixos": config['custos_fixos'],
        "custos_totais": custos_totais,
        "lucro": lucro,
        "margem_lucro": margem_lucro
    }

# ================================
# MENU PRINCIPAL
# ================================
st.sidebar.title("📌 Menu")
pagina = st.sidebar.radio("Escolha a página:", 
                         ["Cadastro de Produção", "Cadastro de Insumos", "Análise", "Configurações"])

# ================================
# PÁGINA CADASTRO DE PRODUÇÃO
# ================================
if pagina == "Cadastro de Produção":
    st.title("📝 Cadastro de Produção")
    df = carregar_dados()
    cidade = st.sidebar.text_input("🌍 Cidade para clima", value=CIDADE_PADRAO)

    with st.form("form_cadastro", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            data = st.date_input("Data", value=date.today())
            local = st.text_input("Local/Estufa")
        with col2:
            produto = st.text_input("Produto")
            caixas = st.number_input("Caixas (1ª)", min_value=0, step=1)
        with col3:
            caixas2 = st.number_input("Caixas (2ª)", min_value=0, step=1)

        # Busca clima automático
        clima = clima_atual(cidade)
        if clima:
            temperatura = clima["temp"]
            umidade = clima["umidade"]
            chuva = clima["chuva"]
            st.info(f"Clima carregado: 🌡️ {temperatura}°C | 💧 {umidade}% | 🌧️ {chuva}mm")
        else:
            st.warning("Não foi possível carregar dados climáticos automaticamente")
            temperatura = st.number_input("Temperatura (°C)", min_value=0.0, step=0.1, value=25.0)
            umidade = st.number_input("Umidade (%)", min_value=0.0, step=0.1, value=60.0)
            chuva = st.number_input("Chuva (mm)", min_value=0.0, step=0.1, value=0.0)

        enviado = st.form_submit_button("Salvar Registro ✅")
        if enviado:
            novo = pd.DataFrame([{
                "Data": pd.to_datetime(data),
                "Local": local,
                "Produto": produto,
                "Caixas": caixas,
                "Caixas de Segunda": caixas2,
                "Temperatura": temperatura,
                "Umidade": umidade,
                "Chuva": chuva
            }])
            df = pd.concat([df, novo], ignore_index=True)
            salvar_dados(df)
            st.success("Registro salvo com sucesso!")

    if not df.empty:
        st.markdown("### 📋 Registros já cadastrados")
        st.dataframe(df.tail(10), use_container_width=True)

# ================================
# PÁGINA CADASTRO DE INSUMOS
# ================================
elif pagina == "Cadastro de Insumos":
    st.title("💰 Cadastro de Insumos")
    df_insumos = carregar_insumos()

    with st.form("form_insumos", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            data = st.date_input("Data", value=date.today())
            tipo = st.selectbox("Tipo de Insumo", ["Semente", "Fertilizante", "Defensivo", "Mão de Obra", "Equipamento", "Outros"])
        with col2:
            descricao = st.text_input("Descrição")
            quantidade = st.number_input("Quantidade", min_value=0.0, step=0.1)
            unidade = st.selectbox("Unidade", ["kg", "L", "un", "h", "sc", "outro"])
        with col3:
            custo = st.number_input("Custo (R$)", min_value=0.0, step=0.01)
            local = st.text_input("Local aplicado")

        enviado = st.form_submit_button("Salvar Insumo ✅")
        if enviado:
            novo = pd.DataFrame([{
                "Data": pd.to_datetime(data),
                "Tipo": tipo,
                "Descricao": descricao,
                "Quantidade": quantidade,
                "Unidade": unidade,
                "Custo": custo,
                "Local": local
            }])
            df_insumos = pd.concat([df_insumos, novo], ignore_index=True)
            salvar_insumos(df_insumos)
            st.success("Insumo salvo com sucesso!")

    if not df_insumos.empty:
        st.markdown("### 📋 Insumos cadastrados")
        st.dataframe(df_insumos.tail(10), use_container_width=True)

# ================================
# PÁGINA CONFIGURAÇÕES
# ================================
elif pagina == "Configurações":
    st.title("⚙️ Configurações de Preços e Custos")
    config = carregar_config_precos()

    with st.form("form_config"):
        col1, col2 = st.columns(2)
        with col1:
            preco_primeira = st.number_input("Preço Caixa 1ª Qualidade (R$)", 
                                           value=float(config['preco_primeira']), 
                                           min_value=0.0, step=0.5)
            preco_segunda = st.number_input("Preço Caixa 2ª Qualidade (R$)", 
                                          value=float(config['preco_segunda']), 
                                          min_value=0.0, step=0.5)
        with col2:
            custos_fixos = st.number_input("Custos Fixos Mensais (R$)", 
                                         value=float(config['custos_fixos']), 
                                         min_value=0.0, step=10.0)
        
        salvar_config = st.form_submit_button("Salvar Configurações 💾")
        if salvar_config:
            novo_config = {
                "preco_primeira": preco_primeira,
                "preco_segunda": preco_segunda,
                "custos_fixos": custos_fixos
            }
            salvar_config_precos(novo_config)
            st.success("Configurações salvas com sucesso!")

# ================================
# PÁGINA ANÁLISE
# ================================
elif pagina == "Análise":
    st.title("📊 Análise Avançada")
    st.markdown("Escolha a fonte de dados:")
    fonte = st.radio("Fonte de dados:", ["Usar dados cadastrados no app","Enviar um arquivo Excel"], horizontal=True)

    df_raw = None
    if fonte == "Usar dados cadastrados no app":
        df_raw = carregar_dados()
    else:
        arquivo = st.file_uploader("Selecione um arquivo Excel", type=["xlsx","xls"])
        if arquivo:
            df_raw = pd.read_excel(arquivo)

    if df_raw is None or df_raw.empty:
        st.warning("Nenhum dado disponível.")
        st.stop()

    df_norm = normalizar_colunas(df_raw)

    # FILTROS
    st.sidebar.markdown("## 🔎 Filtros")
    min_date = df_norm["Data"].min().date() if not df_norm["Data"].isna().all() else date.today()
    max_date = df_norm["Data"].max().date() if not df_norm["Data"].isna().all() else date.today()
    date_range = st.sidebar.date_input("Período", value=(min_date, max_date), min_value=min_date, max_value=max_date)

    locais_all = sorted(df_norm["Local"].dropna().unique())
    locais_sel = st.sidebar.multiselect("Local (todos se vazio)", locais_all, default=locais_all)

    produtos_all = sorted(df_norm["Produto"].dropna().unique())
    produtos_sel = st.sidebar.multiselect("Produto (todos se vazio)", produtos_all, default=produtos_all)

    df_filt = df_norm.copy()
    try:
        start_date, end_date = date_range
    except:
        start_date = end_date = date_range
    df_filt = df_filt[(df_filt["Data"] >= pd.to_datetime(start_date)) & (df_filt["Data"] <= pd.to_datetime(end_date))]

    if locais_sel:
        df_filt = df_filt[df_filt["Local"].isin(locais_sel)]
    if produtos_sel:
        df_filt = df_filt[df_filt["Produto"].isin(produtos_sel)]

    if df_filt.empty:
        st.warning("Nenhum dado após aplicar os filtros.")
        st.stop()

    df_filt["Total"] = df_filt["Caixas"] + df_filt["Caixas de Segunda"]

    # KPIs
    total = df_filt["Total"].sum()
    media = df_filt["Total"].mean()
    maior = df_filt["Total"].max()
    menor = df_filt["Total"].min()

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total de Caixas", f"{total:,.0f}")
    k2.metric("Média por Registro", f"{media:,.2f}")
    k3.metric("Máximo em 1 Registro", f"{maior:,.0f}")
    k4.metric("Mínimo em 1 Registro", f"{menor:,.0f}")

    st.markdown("---")

    # GRÁFICOS BÁSICOS
    st.subheader("🏭 Total por Local")
    fig, ax = plt.subplots(figsize=(12,6))
    plot_bar(ax, "Local", "Total", df_filt, 
             cores=sns.color_palette("tab20", n_colors=len(df_filt["Local"].unique())),
             titulo="Total de Caixas por Local", ylabel="Total de Caixas")
    st.pyplot(fig)

    st.subheader("🍅 Total por Produto")
    fig, ax = plt.subplots(figsize=(10,5))
    plot_bar(ax, "Produto", "Total", df_filt,
             cores=sns.color_palette("Set2", n_colors=len(df_filt["Produto"].unique())),
             titulo="Total de Caixas por Produto", ylabel="Total de Caixas")
    st.pyplot(fig)

    # Comparativo 1ª vs 2ª
    st.subheader("📊 Comparativo Caixas 1ª vs 2ª")
    for tipo in ["Local", "Produto"]:
        if tipo in df_filt.columns:
            df_comp = df_filt.groupby(tipo)[["Caixas", "Caixas de Segunda"]].sum().reset_index()
            fig, ax = plt.subplots(figsize=(12,6))
            df_comp.plot(kind="bar", x=tipo, ax=ax, width=0.7)
            ax.set_ylabel("Quantidade de Caixas")
            ax.set_title(f"Caixas de Primeira vs Segunda por {tipo}")
            ax.grid(axis="y")
            ax.legend(["Caixas (1ª)", "Caixas de Segunda"])
            ax.set_xticklabels(ax.get_xticklabels(), rotation=45, ha='right')
            for p in ax.patches:
                ax.text(p.get_x()+p.get_width()/2, p.get_height()+max(df_filt["Total"])*0.01, f'{int(p.get_height())}', ha='center')
            st.pyplot(fig)

    # Percentual 2ª linha
    st.markdown("---")
    st.subheader("📦 Percentual de Caixas de 2ª Linha")

    # Por Produto
    df_prod_pct = (
        df_filt.groupby("Produto")[["Caixas", "Caixas de Segunda"]]
        .sum()
        .reset_index()
    )
    df_prod_pct["Pct_2a"] = (df_prod_pct["Caixas de Segunda"] / (df_prod_pct["Caixas"] + df_prod_pct["Caixas de Segunda"])) * 100

    fig, ax = plt.subplots(figsize=(10,5))
    sns.barplot(data=df_prod_pct, x="Produto", y="Pct_2a", ax=ax, palette="viridis")
    ax.set_ylabel("% Caixas 2ª")
    ax.set_title("Percentual de Caixas de 2ª por Produto")
    for container in ax.containers:
        ax.bar_label(container, fmt="%.1f%%")
    st.pyplot(fig)

    # Por Local
    df_loc_pct = (
        df_filt.groupby("Local")[["Caixas", "Caixas de Segunda"]]
        .sum()
        .reset_index()
    )
    df_loc_pct["Pct_2a"] = (df_loc_pct["Caixas de Segunda"] / (df_loc_pct["Caixas"] + df_loc_pct["Caixas de Segunda"])) * 100

    fig, ax = plt.subplots(figsize=(10,5))
    sns.barplot(data=df_loc_pct, x="Local", y="Pct_2a", ax=ax, palette="mako")
    ax.set_ylabel("% Caixas 2ª")
    ax.set_title("Percentual de Caixas de 2ª por Local")
    for container in ax.containers:
        ax.bar_label(container, fmt="%.1f%%")
    st.pyplot(fig)

    # ANÁLISE DE TENDÊNCIAS SIMPLES
    st.markdown("---")
    st.subheader("📈 Análise de Tendências")
    
    resultado_analise = analisar_tendencias_simples(df_filt)
    
    if "mensagem" in resultado_analise:
        st.info(resultado_analise["mensagem"])
    elif "erro" in resultado_analise:
        st.error(resultado_analise["erro"])
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Tendência Mensal", f"{resultado_analise['tendencia_mensal']:.1f}%")
        with col2:
            st.metric("Previsão Mensal", f"{resultado_analise['previsao_mensal']:,.0f} caixas")
        with col3:
            st.metric("Status", resultado_analise['status'])
        
        # Correlações
        st.subheader("🔗 Correlações com Fatores Climáticos")
        correl_df = pd.DataFrame({
            'Fator': ['Temperatura', 'Umidade', 'Chuva'],
            'Correlação': [
                resultado_analise['correlacoes']['temp_producao'],
                resultado_analise['correlacoes']['umidade_producao'],
                resultado_analise['correlacoes']['chuva_producao']
            ]
        })
        
        fig, ax = plt.subplots(figsize=(10, 6))
        sns.barplot(data=correl_df, x='Fator', y='Correlação', ax=ax, palette='coolwarm')
        ax.set_title('Correlação entre Fatores Climáticos e Produção')
        ax.set_ylim(-1, 1)
        for container in ax.containers:
            ax.bar_label(container, fmt="%.2f")
        st.pyplot(fig)

    # BALANÇO FINANCEIRO
    st.markdown("---")
    st.subheader("💰 Balanço Financeiro")
    
    df_insumos = carregar_insumos()
    config = carregar_config_precos()
    
    # Filtrar insumos pelo mesmo período
    if not df_insumos.empty and "Data" in df_insumos.columns:
        df_insumos["Data"] = pd.to_datetime(df_insumos["Data"])
        df_insumos_filtrado = df_insumos[
            (df_insumos["Data"] >= pd.to_datetime(start_date)) & 
            (df_insumos["Data"] <= pd.to_datetime(end_date))
        ]
    else:
        df_insumos_filtrado = pd.DataFrame()
    
    balanco = calcular_balanco(df_filt, df_insumos_filtrado, config)
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Receita Total", f"R$ {balanco['receita_total']:,.2f}")
    col2.metric("Custos Totais", f"R$ {balanco['custos_totais']:,.2f}")
    col3.metric("Lucro", f"R$ {balanco['lucro']:,.2f}")
    col4.metric("Margem de Lucro", f"{balanco['margem_lucro']:.1f}%")
    
    # Gráfico de balanço
    fig, ax = plt.subplots(figsize=(10, 6))
    categorias = ['Receita 1ª', 'Receita 2ª', 'Custos Insumos', 'Custos Fixos']
    valores = [balanco['receita_primeira'], balanco['receita_segunda'], 
              balanco['custos_insumos'], balanco['custos_fixos']]
    
    cores = ['#2ecc71', '#27ae60', '#e74c3c', '#c0392b']
    bars = ax.bar(categorias, valores, color=cores)
    ax.set_ylabel('Valores (R$)')
    ax.set_title('Composição do Balanço Financeiro')
    
    for bar, valor in zip(bars, valores):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(valores)*0.01, 
                f'R$ {valor:,.2f}', ha='center')
    
    st.pyplot(fig)

    # Download filtrado
    st.markdown("---")
    buffer = BytesIO()
    df_filt.to_excel(buffer, index=False, engine="openpyxl")
    buffer.seek(0)
    st.download_button("📥 Baixar dados filtrados em Excel", data=buffer,
                       file_name="colheitas_filtradas.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
