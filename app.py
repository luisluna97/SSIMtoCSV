import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

###############################################################################
# 1) PARSE COM SPLIT - INSPIRAÇÃO NO REPO ssim
#    (apenas tokens, sem substring fixo)
###############################################################################
def parse_ssim_line(line: str):
    """
    Lê a linha, se começa com '3 ' ou '3', faz split e tenta extrair:
      splitted[0] = '3'
      splitted[1] = cia
      splitted[2] = chunk2 (eightChar+datas)
      splitted[3] = freq
      splitted[4] = origem+hora
      splitted[5] = destino+hora
      splitted[6] = equip
      splitted[9] = nextVoo (às vezes)
    Se a linha não tiver ao menos splitted[2] com 23 chars, descartamos.
    """
    line_str = line.strip()
    if not line_str.startswith('3'):
        return None

    splitted = line_str.split()
    if len(splitted)<4:
        return None

    cia = splitted[1]
    chunk2 = splitted[2]
    freq_str = splitted[3]

    if len(chunk2)<23:
        # chunk2 ex: '10020101J01JAN2508JAN25' => 24+ ...
        return None

    # ex: chunk2 = "10020101J01JAN2508JAN25"
    # => 0..8 => "10020101"
    # => 9..16 => "01JAN25"
    # =>16..23 => "08JAN25"
    eight_char   = chunk2[:8]        # "10020101"
    data_ini_str = chunk2[9:16]      # "01JAN25"
    data_fim_str = chunk2[16:23]     # "08JAN25"

    num_voo = eight_char[:4]         # "1002"

    # Origem e destino
    origem_blk = splitted[4] if len(splitted)>4 else ""
    destino_blk= splitted[5] if len(splitted)>5 else ""
    equip      = splitted[6] if len(splitted)>7 else ""
    next_voo   = splitted[9] if len(splitted)>9 else ""

    def parse_apt(block:str):
        # ex "CGH0905"
        if len(block)>=7:
            apt = block[:3]
            hhmm= block[3:7]
            return apt, hhmm
        return "", ""

    orig,hp = parse_apt(origem_blk)
    dst ,hc = parse_apt(destino_blk)

    return {
      "Cia": cia,
      "NumVoo": num_voo,
      "DataIni": data_ini_str,
      "DataFim": data_fim_str,
      "Freq": freq_str,   # ex. "2345"
      "Origem": orig,
      "HoraPartida": hp,
      "Destino": dst,
      "HoraChegada": hc,
      "Equip": equip,
      "NextVoo": next_voo
    }

###############################################################################
# 2) EXPAND DATAS (DataIni->DataFim) usando freq=1..7 (1=Seg,...,7=Dom)
###############################################################################
def expand_dates(row: dict):
    di = row.get("DataIni","")
    df = row.get("DataFim","")
    freq = row.get("Freq","")
    if not di or not df:
        return []

    try:
        dt_i = datetime.strptime(di, "%d%b%y")
        dt_f = datetime.strptime(df, "%d%b%y")
    except:
        return []

    freq_set = set()
    for c in freq:
        if c.isdigit():
            freq_set.add(int(c))  # 1=Seg,...,7=Dom

    expanded = []
    d = dt_i
    while d<=dt_f:
        dow = d.weekday()+1  # 1=Mon,...,7=Sun
        if dow in freq_set:
            newr = dict(row)
            newr["DataOper"] = d.strftime("%d/%m/%Y") # ex "01/01/2025"
            expanded.append(newr)
        d += timedelta(days=1)
    return expanded

###############################################################################
# DUPLICA EM 2 LINHAS: CHEGADA & PARTIDA
###############################################################################
def fix_time_4digits(tt:str)->str:
    if len(tt)==4:
        return tt[:2]+":"+tt[2:]
    return tt

def build_arrdep_rows(row: dict):
    dataop = row.get("DataOper","")
    orig   = row.get("Origem","")
    hp     = fix_time_4digits(row.get("HoraPartida",""))
    dst    = row.get("Destino","")
    hc     = fix_time_4digits(row.get("HoraChegada",""))

    recs=[]
    # Partida
    if orig and hp:
        recs.append({
          "Aeroporto": orig,
          "CP": "P",
          "DataOper": dataop,
          "NumVoo": row["NumVoo"],
          "Hora": hp,
          "Equip": row.get("Equip",""),
          "NextVoo": row.get("NextVoo","") 
        })
    # Chegada
    if dst and hc:
        recs.append({
          "Aeroporto": dst,
          "CP": "C",
          "DataOper": dataop,
          "NumVoo": row["NumVoo"],
          "Hora": hc,
          "Equip": row.get("Equip",""),
          "NextVoo": row.get("NextVoo","")
        })
    return recs

###############################################################################
# CONECTA (Chegada + NextVoo=Partida) => 1 linha com colunas:
# Aeroporto, DataOper, HoraChegada, VooChegada, HoraPartida, VooPartida, TempoSolo, EquipCheg, EquipPart
###############################################################################
def to_hhmm(delta_h:float)->str:
    """Ex: 30.5 => '30:30' """
    if delta_h<0:
        return "00:00"
    h = int(delta_h)
    m = int(round( (delta_h - h)*60 ))
    return f"{h}:{m:02d}"

def connect_rows(df):
    """
    Filtra CP="C" como base, e p/ cada Chegada se NextVoo=xxx, busca Partida => CP="P", NumVoo=xxx, dt>= dtChegada
    e gera col TempoSolo= 'hh:mm'
    Renomeia col 'Hora' => 'HoraChegada','NumVoo' => 'VooChegada','Equip'=>'EquipCheg'
    E adiciona col 'HoraPartida','VooPartida','TempoSolo','EquipPart'
    Retorna df final.
    """
    # dt
    df["dt"] = pd.to_datetime(df["DataOper"]+" "+df["Hora"], format="%d/%m/%Y %H:%M", errors="coerce")

    arr = df[df["CP"]=="C"].copy()
    dep = df[df["CP"]=="P"].copy()

    arr["HoraPartida"] = None
    arr["VooPartida"]  = None
    arr["EquipPart"]   = None
    arr["TempoSolo"]   = None

    # agrupar dep => (Aeroporto, NumVoo, DataOper)
    dep_grp = dep.groupby(["Aeroporto","NumVoo","DataOper"])

    for idx, rowC in arr.iterrows():
        nxtv = rowC["NextVoo"]
        if not nxtv:
            continue
        apr = rowC["Aeroporto"]
        dOp = rowC["DataOper"]
        dtA= rowC["dt"]
        key = (apr, nxtv, dOp)
        if key in dep_grp.groups:
            idxs = dep_grp.groups[key]
            cand = dep.loc[idxs]
            # filtra cand dt>= dtA
            cand2= cand[cand["dt"]>= dtA]
            if len(cand2)>0:
                dp = cand2.sort_values("dt").iloc[0]
                delta_hrs= (dp["dt"] - dtA).total_seconds()/3600
                arr.at[idx,"TempoSolo"]   = to_hhmm(delta_hrs)
                arr.at[idx,"VooPartida"]  = dp["NumVoo"]
                arr.at[idx,"HoraPartida"] = dp["Hora"]
                arr.at[idx,"EquipPart"]   = dp["Equip"]

    arr.rename(columns={
      "Hora":"HoraChegada",
      "NumVoo":"VooChegada",
      "Equip":"EquipCheg"
    }, inplace=True)

    final_cols = [
      "Aeroporto","DataOper","HoraChegada","VooChegada",
      "HoraPartida","VooPartida","TempoSolo",
      "EquipCheg","EquipPart"
    ]
    return arr[final_cols]

###############################################################################
# FLUXO COMPLETO
###############################################################################
def process_ssim(ssim_file):
    # 1) parse
    lines = ssim_file.read().decode("latin-1").splitlines()
    base=[]
    for l in lines:
        rec = parse_ssim_line(l)
        if rec:
            base.append(rec)
    if not base:
        return None

    # 2) expand
    expanded=[]
    for b in base:
        e2 = expand_dates(b)
        expanded.extend(e2)
    if not expanded:
        return None

    # 3) duplicar c/p
    arrdep=[]
    for e in expanded:
        arrdep+= build_arrdep_rows(e)
    if not arrdep:
        return None
    dfAD = pd.DataFrame(arrdep)

    # 4) connect => “visão do aeroporto”
    dfC = connect_rows(dfAD)
    if len(dfC)==0:
        return None

    return dfC

###############################################################################
def main():
    st.title("CONVERSOR DE SSIM PARA CSV")

    ssim_file = st.file_uploader("Selecione o arquivo SSIM:", type=["ssim","txt"])
    if ssim_file:
        if st.button("Processar"):
            dfC = process_ssim(ssim_file)
            if dfC is None or len(dfC)==0:
                st.error("Nenhum voo processado ou nenhuma chegada conectada.")
                return

            # TABELA-RESUMO NO SITE (mas sem alterar CSV):
            # ex: contagem de voos (chegadas) por Aeroporto
            st.write("### Resumo: chegadas por Aeroporto")
            sum_air = dfC.groupby("Aeroporto")["VooChegada"].count().reset_index(name="Qtde")
            st.dataframe(sum_air)

            # Exibir final
            st.write("### Tabela final (Visão do Aeroporto)")
            st.dataframe(dfC)

            # Download
            csv_str = dfC.to_csv(index=False)
            st.download_button("Baixar CSV", csv_str.encode("utf-8"), file_name="ssim_visao.csv", mime="text/csv")

if __name__=="__main__":
    main()
