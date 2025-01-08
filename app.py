import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

def parse_ssim_line(line: str):
    """
    Lógica simples de parse (similar ao que 'funcionava bem' antes).
    - Tenta splitar e extrair chunk2 => datas e freq
    - Se falhar, ignora a linha
    """
    line_str = line.strip()
    if not line_str.startswith("3"):
        return None
    splitted = line_str.split()
    if len(splitted) < 4:
        return None

    cia = splitted[1]
    chunk2 = splitted[2]
    freq_str = splitted[3]

    # Precisamos de pelo menos 23 chars em chunk2 para dataIni e dataFim
    if len(chunk2) < 23:
        return None

    eight_char   = chunk2[0:8]   # ex "10020101"
    data_ini_str = chunk2[9:16]  # ex "01JAN25"
    data_fim_str = chunk2[16:23] # ex "15JAN25"
    num_voo      = eight_char[:4]

    # Origem e destino
    origem_blk = splitted[4] if len(splitted)>4 else ""
    destino_blk= splitted[5] if len(splitted)>5 else ""
    equip      = splitted[6] if len(splitted)>6 else ""
    next_voo   = splitted[9] if len(splitted)>9 else ""  # pode não existir

    def parse_ap(block):
        if len(block)>=7:
            apt = block[:3]
            hora= block[3:7]
            return apt,hora
        return "",""

    orig,hp = parse_ap(origem_blk)
    dst ,hc = parse_ap(destino_blk)

    return {
      "Cia": cia,
      "NumVoo": num_voo,
      "DataIni": data_ini_str,
      "DataFim": data_fim_str,
      "Freq": freq_str,
      "Origem": orig,
      "HoraPartida": hp,
      "Destino": dst,
      "HoraChegada": hc,
      "Equip": equip,
      "NextVoo": next_voo
    }

def expand_dates(row: dict):
    """
    Expande datas de DataIni->DataFim filtrando freq.
    Frequência => 1=Seg,...,7=Dom
    """
    di = row.get("DataIni","")
    df = row.get("DataFim","")
    fs = row.get("Freq","")
    if not di or not df: 
        return []
    try:
        dt_i = datetime.strptime(di, "%d%b%y")
        dt_f = datetime.strptime(df, "%d%b%y")
    except:
        return []

    freq_set = set()
    for c in fs:
        if c.isdigit():
            freq_set.add(int(c))

    expanded=[]
    d = dt_i
    while d<= dt_f:
        dow = d.weekday()+1  # 1=Mon,...,7=Sun
        if dow in freq_set:
            newr = dict(row)
            newr["DataOper"] = d.strftime("%d/%m/%Y")  # ex "01/01/2025"
            expanded.append(newr)
        d+= timedelta(days=1)
    return expanded

def fix_time_4digits(tt:str)->str:
    if len(tt)==4:
        return tt[:2]+":"+tt[2:]
    return tt

def build_arrdep_rows(row:dict):
    """
    Gera 2 linhas: Chegada e Partida
    """
    arrdep=[]
    dataop = row.get("DataOper","")
    orig   = row.get("Origem","")
    hp     = fix_time_4digits(row.get("HoraPartida",""))
    dst    = row.get("Destino","")
    hc     = fix_time_4digits(row.get("HoraChegada",""))
    # Partida
    if orig and hp:
        arrdep.append({
          "Aeroporto": orig,
          "CP": "P",
          "DataOper": dataop,
          "Cia": row["Cia"],
          "NumVoo": row["NumVoo"],
          "Hora": hp,
          "Equip": row.get("Equip",""),
          "NextVoo": row.get("NextVoo","")
        })
    # Chegada
    if dst and hc:
        arrdep.append({
          "Aeroporto": dst,
          "CP": "C",
          "DataOper": dataop,
          "Cia": row["Cia"],
          "NumVoo": row["NumVoo"],
          "Hora": hc,
          "Equip": row.get("Equip",""),
          "NextVoo": row.get("NextVoo","")
        })
    return arrdep

def connect_rows(df):
    """
    - df: colunas [Aeroporto,CP,DataOper,Cia,NumVoo,Hora,Equip,NextVoo]
    - Mantemos apenas Chegadas (CP="C").
    - Para cada Chegada com NextVoo=xxx, procuramos Partida (CP="P") com NumVoo=xxx no mesmo Aeroporto e DataOper e dt>= dtChegada
    - Calculamos TempoSolo
    """
    df["dt"] = pd.to_datetime(df["DataOper"]+" "+df["Hora"], format="%d/%m/%Y %H:%M", errors="coerce")
    arr = df[df["CP"]=="C"].copy()
    dep = df[df["CP"]=="P"].copy()

    arr["TempoSolo"] = None
    arr["VooPartida"] = None
    arr["HoraSaida"] = None

    # agrupar departures p/ lookup
    # (Aeroporto,NumVoo,DataOper)
    dep_grp = dep.groupby(["Aeroporto","NumVoo","DataOper"])

    for idx, ar in arr.iterrows():
        nxtv = ar["NextVoo"]
        if not nxtv:
            continue
        apr = ar["Aeroporto"]
        dOp = ar["DataOper"]
        dtA= ar["dt"]
        key = (apr,nxtv,dOp)
        if key in dep_grp.groups:
            idxs = dep_grp.groups[key]  # indices
            cand = dep.loc[idxs]
            # filtra cand dt >= dtA
            cand2 = cand[cand["dt"]>= dtA]
            if len(cand2)>0:
                c2s = cand2.sort_values("dt")
                dp  = c2s.iloc[0]
                delta_h = (dp["dt"]- dtA).total_seconds()/3600
                arr.at[idx,"TempoSolo"]  = round(delta_h,2)
                arr.at[idx,"VooPartida"] = dp["NumVoo"]
                arr.at[idx,"HoraSaida"]  = dp["Hora"]

    return arr

def process_ssim(ssim_file):
    """
    1) parse
    2) expand
    3) duplicar
    4) connect => filtra so CP="C"
    """
    lines = ssim_file.read().decode("latin-1").splitlines()
    base_rows=[]
    for l in lines:
        pr = parse_ssim_line(l)
        if pr:
            base_rows.append(pr)

    # expand
    expanded=[]
    for row in base_rows:
        eds = expand_dates(row)
        expanded.extend(eds)

    # duplicar
    arrdep=[]
    for e2 in expanded:
        arrdep += build_arrdep_rows(e2)
    dfAD = pd.DataFrame(arrdep)
    if len(dfAD)==0:
        return None

    # connect
    dfC = connect_rows(dfAD)
    # dfC => so CP="C"
    if len(dfC)==0:
        return None

    return dfC

def main():
    st.title("Conversor SSIM")
    ssim_file = st.file_uploader("Selecione SSIM:", type=["ssim","txt"])
    if ssim_file:
        if st.button("Processar"):
            dfC = process_ssim(ssim_file)
            if dfC is None or len(dfC)==0:
                st.error("Nenhuma chegada obtida.")
                return
            # exibir resumo
            st.write("### Resumo: Chegadas por Mês")
            dfC["dt"] = pd.to_datetime(dfC["DataOper"]+" "+dfC["Hora"], format="%d/%m/%Y %H:%M", errors="coerce")
            dfC["Month"] = dfC["dt"].dt.to_period("M").astype(str)
            sum_month = dfC.groupby("Month")["NumVoo"].count().reset_index(name="QtdeChegadas")
            st.dataframe(sum_month)

            # exibir
            st.write("### Tabela de Chegadas Detalhada")
            st.dataframe(dfC[["Aeroporto","DataOper","Hora","NumVoo","VooPartida","HoraSaida","TempoSolo","Equip"]])

            # download
            csv_str = dfC.to_csv(index=False)
            st.download_button("Baixar CSV", data=csv_str.encode("utf-8"), file_name="ssim_chegadas.csv", mime="text/csv")

if __name__=="__main__":
    main()
