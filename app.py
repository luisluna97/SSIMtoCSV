import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os

###############################################################################
# 1) PARSE DA LINHA TIPO 3
###############################################################################
def parse_ssim_line(line: str):
    line_stripped = line.lstrip()
    splitted = line_stripped.split()
    if len(splitted) < 4: 
        return None
    if splitted[0] != "3":
        return None

    # splitted[1] => cia
    # splitted[2] => "10020101J01JAN2515JAN251234567" etc.
    # splitted[9] => next voo/casamento (ex. 2136)
    cod_cliente = splitted[1]
    chunk2      = splitted[2] if len(splitted)>2 else ""
    freq_str    = splitted[3] if len(splitted)>3 else ""
    origem_info = splitted[4] if len(splitted)>4 else ""
    destino_info= splitted[5] if len(splitted)>5 else ""
    equip       = splitted[6] if len(splitted)>6 else ""
    next_voo    = splitted[9] if len(splitted)>9 else ""

    # chunk2 => 8 chars + 1 status + 7 + 7 => ex.: "10020101J01JAN2515JAN251234567..."
    if len(chunk2)<23:
        return None
    eight_char   = chunk2[0:8]    # p.ex. "10020101"
    data_ini_str = chunk2[9:16]   # p.ex. "01JAN25"
    data_fim_str = chunk2[16:23]  # p.ex. "15JAN25"
    # Frequência pode continuar além, ex. "1234567" (podemos usar splitted[3] por simplicidade)
    voo_num      = eight_char[0:4] # "1002" etc.

    # Origem e HoraPartida
    if len(origem_info)>=7:
        origem = origem_info[:3]
        hora_part = origem_info[3:7]
    else:
        origem = ""
        hora_part = ""

    # Destino e HoraChegada
    if len(destino_info)>=7:
        destino = destino_info[:3]
        hora_cheg= destino_info[3:7]
    else:
        destino = ""
        hora_cheg= ""

    return {
        "Cia": cod_cliente,
        "NumVoo": voo_num,
        "DataIni": data_ini_str,
        "DataFim": data_fim_str,
        "Freq": freq_str,
        "Origem": origem,
        "HoraPartida": hora_part,
        "Destino": destino,
        "HoraChegada": hora_cheg,
        "Equip": equip,
        "NextVoo": next_voo
    }

###############################################################################
# 2) EXPANDIR DATAS (DataIni->DataFim) FILTRANDO FREQUÊNCIA
#    1=Seg,2=Ter,3=Qua,4=Qui,5=Sex,6=Sáb,7=Dom
###############################################################################
def expand_dates(row: dict):
    di = row.get("DataIni","")
    df = row.get("DataFim","")
    freq_str = row.get("Freq","")
    if not di or not df:
        return []

    # Converte datas: "01JAN25" => %d%b%y
    try:
        dt_ini = datetime.strptime(di, "%d%b%y")
        dt_fim = datetime.strptime(df, "%d%b%y")
    except:
        return []

    freq_set = set()
    for c in freq_str:
        if c.isdigit():
            freq_set.add(int(c))  # 1=Seg,...,7=Dom

    expanded = []
    d = dt_ini
    while d <= dt_fim:
        # weekday(): 0=Mon,...,6=Sun => +1 => 1=Mon,...,7=Sun
        dow = d.weekday()+1
        if dow in freq_set:
            newrow = dict(row)
            # formata data => dd/mm/yyyy
            newrow["DataOper"] = d.strftime("%d/%m/%Y")
            expanded.append(newrow)
        d+=timedelta(days=1)
    return expanded

###############################################################################
# 3) DUPLICAR CADA VOO (CHEGADA E PARTIDA)
###############################################################################
def build_arrdep_rows(row: dict):
    """
    Recebe um row ex.: {
      "Cia":"G3", "NumVoo":"1002", "DataOper":"05/01/2025",
      "Origem":"CGH","HoraPartida":"0905","Destino":"GRU","HoraChegada":"1010",
      "Equip":"73X", "NextVoo":"2136"
    }
    Cria 2 registros:
      [1] -> Partida (P) no Origem
      [2] -> Chegada (C) no Destino
    """
    results = []
    # formata hora => HH:MM
    hp = row.get("HoraPartida","")
    hc = row.get("HoraChegada","")
    def fmtHora(x):
        if len(x)==4:
            return x[:2]+":"+x[2:]
        return x

    hp_form = fmtHora(hp)
    hc_form = fmtHora(hc)

    # PARTIDA
    part_rec = {
      "Aeroporto": row["Origem"],
      "CP": "P",  # Partida
      "Cia": row["Cia"],
      "NumVoo": row["NumVoo"],
      "DataOper": row["DataOper"],  # Mesmo dia assumido
      "Hora": hp_form,
      "Equip": row["Equip"],
      "NextVoo": row["NextVoo"],  # Se define nextvoo no ORIGEM ou no DEST?
    }
    results.append(part_rec)

    # CHEGADA
    cheg_rec = {
      "Aeroporto": row["Destino"],
      "CP": "C", # Chegada
      "Cia": row["Cia"],
      "NumVoo": row["NumVoo"],
      "DataOper": row["DataOper"],
      "Hora": hc_form,
      "Equip": row["Equip"],
      "NextVoo": row["NextVoo"],
    }
    results.append(cheg_rec)
    return results

###############################################################################
# 4) CONECTAR CHEGADA E PARTIDA
#    - "C" row com NextVoo=XYZ => achar "P" row do NumVoo=XYZ, no mesmo Aeroporto e DataOper
###############################################################################
def connect_rows(df):
    """
    df: colunas: [Aeroporto,CP,Cia,NumVoo,DataOper,Hora,Equip,NextVoo]
    Gera um df final do tipo:
      [Aeroporto, Data, HoraChegada, VooChegada, HoraPartida, VooPartida, TempoSolo, ...]
    """
    # Converter DataOper + Hora -> datetime p/ ordenação
    df["dt"] = pd.to_datetime(df["DataOper"] + " " + df["Hora"], format="%d/%m/%Y %H:%M", errors="coerce")

    final_rows = []
    # Para cada row CP="C", se NextVoo=xyz, buscar no df a row CP="P", NumVoo=xyz, mesmo Aeroporto, DataOper => dt>...
    # Precisamos agrupar por (Aeroporto, DataOper) e ordenar por dt
    grouped = df.groupby(["Aeroporto","DataOper"])

    for (apr, dataop), subdf in grouped:
        subdf_sorted = subdf.sort_values("dt").reset_index(drop=True)

        # Vamos varrer as linhas CP="C" e ver NextVoo
        for i, r_c in subdf_sorted.iterrows():
            if r_c["CP"]=="C" and r_c["NextVoo"]:
                nxt = r_c["NextVoo"]
                # Procurar PARTIDA
                # -> subdf_sorted com CP="P" e NumVoo=nxt, dt maior ou igual à dt do r_c
                cand = subdf_sorted[
                  (subdf_sorted["CP"]=="P") &
                  (subdf_sorted["NumVoo"]==nxt) &
                  (subdf_sorted["dt"] >= r_c["dt"])
                ]
                if len(cand)>0:
                    # Pegamos a 1a (menor dt)
                    r_p = cand.iloc[0]
                    # Calcular tempo de solo
                    if pd.notna(r_c["dt"]) and pd.notna(r_p["dt"]):
                        delta_h = (r_p["dt"] - r_c["dt"]).total_seconds()/3600
                    else:
                        delta_h = 0

                    # Monta 1 registro final
                    reg = {
                      "Aeroporto": apr,
                      "DataOper": dataop,
                      "HoraChegada": r_c["Hora"],
                      "VooChegada": r_c["NumVoo"],
                      "HoraPartida": r_p["Hora"],
                      "VooPartida": r_p["NumVoo"],
                      "TempoSolo": round(delta_h,2),
                      "EquipCheg": r_c["Equip"],
                      "EquipPart": r_p["Equip"]
                    }
                    final_rows.append(reg)

    df_final = pd.DataFrame(final_rows)
    return df_final

###############################################################################
@st.cache_data
def load_support_files():
    # se quiser algo
    return None, None

def gerar_csv(ssim_file):
    """
    - Parse
    - Expand datas
    - Duplicar
    - Conectar
    - Summaries
    """
    # Ler lines
    lines = ssim_file.read().decode("latin-1").splitlines()
    base_rows = []
    for l in lines:
        pr = parse_ssim_line(l.rstrip("\n"))
        if pr:
            base_rows.append(pr)

    # Expand
    expanded = []
    for row in base_rows:
        exps = expand_dates(row)
        for e2 in exps:
            expanded.append(e2)

    # Duplicar em C/P
    arrdep = []
    for row in expanded:
        # row => {Cia,NumVoo,DataOper,Origem,HoraPartida,Destino,HoraChegada,Equip,NextVoo...}
        arrdep += build_arrdep_rows(row)

    df = pd.DataFrame(arrdep)
    if len(df)==0:
        return None, pd.DataFrame(), pd.DataFrame()

    # Connect
    df_final = connect_rows(df)

    # Summaries (pedido: “quantidade de voos por aeroporto e por modelo”)
    # 1) Por Aeroporto: contagem (C+P)
    summary_airport = df.groupby("Aeroporto")["NumVoo"].count().reset_index(name="QtdeVoos")

    # 2) Por Tipo (df tem Equip?). Se preferir, usar "Equip"
    summary_equip = df.groupby("Equip")["NumVoo"].count().reset_index(name="QtdeVoos")

    return df_final, summary_airport, summary_equip

###############################################################################
def main():
    st.title("Conversor SSIM - Frequência, Conexão e Resumos")
    st.write("Carregue um arquivo SSIM. Expandimos as datas, viramos em 'arrivals/departures', conectamos NextVoo e geramos CSV.")
    _, _ = load_support_files()

    ssim_file = st.file_uploader("Selecione o arquivo SSIM:", type=["ssim","txt"])
    if ssim_file:
        if st.button("Processar"):
            df_final, summary_airport, summary_equip = gerar_csv(ssim_file)
            if df_final is None or len(df_final)==0:
                st.error("Não foi possível gerar a planilha final (nenhuma linha processada).")
                return
            # Exibir Summaries
            st.write("### Voos por Aeroporto")
            st.dataframe(summary_airport)
            st.write("### Voos por Modelo de Aeronave (Equip)")
            st.dataframe(summary_equip)

            # Baixar CSV
            csv_bytes = df_final.to_csv(index=False).encode("utf-8")
            st.download_button("Baixar CSV Final", csv_bytes, file_name="ssim_conectado.csv", mime="text/csv")

if __name__=="__main__":
    main()
