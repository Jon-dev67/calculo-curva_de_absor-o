import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import urllib.parse
import json
import os

# ================================
# CONFIGURAÇÕES INICIAIS
# ================================
st.set_page_config(
    page_title="🌱 Painel Integrado de Produção",
    layout="wide",
    initial_sidebar_state="expanded",
)

CONFIG_FILE = "config.json"
API_KEY = "eef20bca4e6fb1ff14a81a3171de5cec"  # sua chave

# ================================
# FUNÇÕES AUXILIARES
# ================================
def carregar_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "cidade": "Londrina",
        "fenologia": {
            "estagios": [
                {"nome": "Estágio 1", "dias": "0-20", "adubo": 2},
                {"nome": "Estágio 2", "dias": "21-40", "adubo": 4},
                {"nome": "Estágio 3", "dias": "41-60", "adubo": 6},
                {"nome": "Estágio 4", "dias": "61-80", "adubo": 8},
            ]
        }
    }

def salvar_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=4)

def buscar_clima(cidade):
    try:
        city_encoded = urllib.parse.quote(cidade)
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city_encoded}&appid={API_KEY}&units=metric&lang=pt_br"
        response = requests.get(url)
        data = response.json()
        if response.status_code != 200:
            return None, None
        atual = {
            "temp": data["main"]["temp"],
            "umidade": data["main"]["humidity"],
        }
        # previsão
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

# ================================
# CARREGA CONFIGURAÇÕES
# ================================
config = carregar_config()

# ================================
# MENU LATERAL DE CONFIGURAÇÕES
# ================================
st.sidebar.title("⚙️ Configurações")

# Cidade padrão
cidade = st.sidebar.text_input("🌍 Cidade para clima", value=config.get("cidade", "Londrina"))

# Estágios fenológicos
st.sidebar.subheader("🌱 Estágios Fenológicos")
num_estagios = st.sidebar.number_input("Quantos estágios?", min_value=1, max_value=10, value=len(config["fenologia"]["estagios"]))
estagios = []
for i in range(num_estagios):
    if i < len(config["fenologia"]["estagios"]):
        e = config["fenologia"]["estagios"][i]
        nome = st.sidebar.text_input(f"Nome do estágio {i+1}", value=e["nome"])
        dias = st.sidebar.text_input(f"Dias do estágio {i+1}", value=e["dias"])
        adubo = st.sidebar.number_input(f"Adubo (kg) estágio {i+1}", value=e["adubo"], step=1)
    else:
        nome = st.sidebar.text_input(f"Nome do estágio {i+1}", value=f"Estágio {i+1}")
        dias = st.sidebar.text_input(f"Dias do estágio {i+1}", value=f"{i*20}-{(i+1)*20}")
        adubo = st.sidebar.number_input(f"Adubo (kg) estágio {i+1}", value=(i+1)*2, step=1)
    estagios.append({"nome": nome, "dias": dias, "adubo": adubo})

if st.sidebar.button("💾 Salvar Configurações"):
    config["cidade"] = cidade
    config["fenologia"]["estagios"] = estagios
    salvar_config(config)
    st.sidebar.success("Configurações salvas!")

# ================================
# PÁGINA PRINCIPAL
# ================================
st.title("🌱 Painel Integrado de Produção")

# --- Fenologia
st.subheader("📊 Curva de absorção de nutrientes")
fenologia_df = pd.DataFrame({
    "Estágio": [f"{e['dias']} ({e['nome']})" for e in estagios],
    "Adubo (kg)": [e["adubo"] for e in estagios]
})
st.dataframe(fenologia_df, use_container_width=True)
fig = px.line(fenologia_df, x="Estágio", y="Adubo (kg)", markers=True, title="Curva de absorção de nutrientes")
st.plotly_chart(fig, use_container_width=True)

# --- Colheitas
st.subheader("📦 Colheitas")
uploaded_file = st.file_uploader("Envie a planilha de colheitas (xlsx)", type=["xlsx"])
df_colheita = None
if uploaded_file:
    df_colheita = pd.read_excel(uploaded_file)
    if "Data" in df_colheita.columns:
        df_colheita["Data"] = pd.to_datetime(df_colheita["Data"], errors="coerce")
    st.dataframe(df_colheita, use_container_width=True)

    if "Data" in df_colheita.columns and "Caixas" in df_colheita.columns:
        df_colheita = df_colheita.sort_values("Data")

        # === GRÁFICO DE PRODUÇÃO AO LONGO DO TEMPO - BARRAS ===
        fig2 = px.bar(
            df_colheita,
            x="Data",
            y="Caixas",
            color="Caixas",
            color_continuous_scale="Viridis",
            title="Produção ao longo do tempo",
            labels={"Caixas": "Caixas", "Data": "Data"}
        )
        st.plotly_chart(fig2, use_container_width=True)

# --- Clima
st.subheader("🌤️ Dados Climáticos")
atual, previsao_df = buscar_clima(cidade)
if atual:
    c1, c2 = st.columns(2)
    c1.metric("🌡️ Temperatura atual", f"{atual['temp']} °C")
    c2.metric("💧 Umidade", f"{atual['umidade']}%")

if previsao_df is not None and not previsao_df.empty:
    st.dataframe(previsao_df, use_container_width=True)

    fig_media = px.line(previsao_df, x="Data", y="Temp Média (°C)", markers=True, title="Temperatura média prevista")
    st.plotly_chart(fig_media, use_container_width=True)

    fig_minmax = px.line(previsao_df, x="Data", y=["Temp Min (°C)", "Temp Média (°C)", "Temp Max (°C)"],
                         title="Temperatura Mínima, Média e Máxima (próximos dias)")
    st.plotly_chart(fig_minmax, use_container_width=True)

# --- Relatórios
st.subheader("📈 Relatórios e análises")
if df_colheita is not None:
    total_caixas = df_colheita["Caixas"].sum()
    total_adubo = sum([e["adubo"] for e in estagios])
    eficiencia = total_caixas / total_adubo if total_adubo > 0 else None

    col1, col2, col3 = st.columns(3)
    col1.metric("📦 Total de Caixas Colhidas", total_caixas)
    col2.metric("🧪 Total de Adubo Aplicado (kg)", total_adubo)
    if eficiencia:
        col3.metric("⚖️ Eficiência (Caixas/kg Adubo)", round(eficiencia, 2))

    relacao_df = pd.DataFrame({
        "Categoria": ["Produção (Caixas)", "Adubo (kg)"],
        "Valor": [total_caixas, total_adubo]
    })
    fig_rel = px.bar(relacao_df, x="Categoria", y="Valor", title="Comparativo Produção x Adubo")
    st.plotly_chart(fig_rel, use_container_width=True)
else:
    st.info("Envie uma planilha de colheita para gerar relatórios completos.")
