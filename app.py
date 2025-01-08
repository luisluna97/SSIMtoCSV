import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

###############################################################################
# 1) PARSE DA LINHA TIPO 3 (APENAS SPLIT)
###############################################################################
def parse_ssim_line(line: str):
    """
    Igual ao código 'antigo' que funcionava bem:
    splitted[0] = '3'
    splitted[1] = cia
    splitted[2] = ex. "10020101J01JAN2508JAN25"
    splitted[3] = freq ex. "1234567"
    splitted[4] = origem+hora
    splitted[5] = destino+hora
    splitted[6] = equip
    splitted[9] = nextvoo (às vezes)

    Se chunk2 < 23 chars => descarta
    Origem e destino => 3 chars p/ apt + 4 chars p/ hora
    """
    line_str = line.strip()
    if not line_str.startswith("3"):
        return None

    splitted = line_str.split()
    if len(splitted) < 4:
        return None

    cia      = splitted[1]
    chunk2   = splitted[2]
    freq_str = splitted[3]

    # Precisamos de 23+ chars em chunk2 p/ dataIni e dataFim
    if len(chunk2) < 23:
        return None

    # ex chunk2[:8] => "10020101"
    eight_char   = chunk2[:8]       # "10020101"
    data_ini_str = chunk2[9:16]     # "01JAN25"
    data_fim_str = chunk2[16:23]    # "08JAN25"
    num_voo      = eight_char[:4]   # "1002"

    # Podem existir splitted[4], [5], [6], [9]
    orig_blk = splitted[4] if len(splitted)>4 else ""
    dest_blk = splitted[5] if len(splitted)>5 else ""
    equip    = splitted[6] if len(splitted)>6 else ""
    next_voo = splitted[9] if len(splitted)>9 else ""

    def parse_ap(block: str):
        """
        ex: "CGH0905..." => apt=CGH, hora=0905
        Se len(block)<7 => apt="", hora=""
        """
        if len(block)>=7:
            apt  = block[:3]
            hora = block[3:7]
            return apt, hora
        return "", ""

    orig, hp = parse_ap(orig_blk)
    dst , hc = parse_ap(dest_blk)

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

###############################################################################
# 2) EXPAND DATAS (DataIni->DataFim), Freq=1..7 => 1=Seg,...7=Dom
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
            freq_set.add(int(c))

    expanded=[]
    d = dt_i
    while d<= dt_f:
        dow = d.weekday()+1  # 1=Mon,...7=Sun
        if dow in freq_set:
            newr = dict(row)
            newr["DataOper"] = d.strftime("%d/%m/%Y")
            expanded.append(newr)
        d+=timedelta(days=1)
    return expanded

###############################################################################
# 3) DUPLICAR EM CHEGADA/PARTIDA
###############################################################################
def fix_time_4digits(tt: str)->str:
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
# 4) CONECTAR => Chegada + Partida => 1 linha (visão do aeroporto)
###############################################################################
def to_hhmm(delta_hrs: float)-> str:
    """
    ex 30.5 => '30:30'
    se <0 => '00:00'
    """
    if delta_hrs<0:
        return "00:00"
    hh = int(delta_hrs)
    mm = int(round((delta_hrs - hh)*60))
    return f"{hh}:{mm:02d}"

def connect_rows(df):
    """
    - df => colunas: [Aeroporto,CP,DataOper,NumVoo,Hora,Equip,NextVoo,...]
    - Filtramos CP="C", para cada Chegada, se NextVoo=xxx => achar Partida(NumVoo=xxx) no msm (Aeroporto,DataOper) c/ dt>= dtChegada
    - Calcula TempoSolo => 'hh:mm'
    - Final => colunas: Aeroporto,DataOper,HoraChegada,VooChegada,HoraPartida,VooPartida,TempoSolo,EquipCheg,EquipPart
    """
    # converter date+time
    df["dt"] = pd.to_datetime(df["DataOper"]+" "+df["Hora"], format="%d/%m/%Y %H:%M", errors="coerce")

    arr = df[df["CP"]=="C"].copy()
    dep = df[df["CP"]=="P"].copy()

    arr["HoraPartida"] = None
    arr["VooPartida"]  = None
    arr["EquipPart"]   = None
    arr["TempoSolo"]   = None

    dep_gb = dep.groupby(["Aeroporto","NumVoo","DataOper"])

    for idx, rowC in arr.iterrows():
        nxtv = rowC["NextVoo"]
        if not nxtv:
            continue
        apr = rowC["Aeroporto"]
        dop = rowC["DataOper"]
        dtC = rowC["dt"]
        key = (apr,nxtv,dop)
        if key in dep_gb.groups:
            idxs = dep_gb.groups[key]
            cand = dep.loc[idxs]
            # filtra cand dt>= dtC
            cand2 = cand[cand["dt"]>= dtC]
            if len(cand2)>0:
                c2s = cand2.sort_values("dt")
                dp  = c2s.iloc[0]
                delta_hrs = (dp["dt"] - dtC).total_seconds()/3600
                arr.at[idx,"TempoSolo"]   = to_hhmm(delta_hrs)
                arr.at[idx,"VooPartida"]  = dp["NumVoo"]
                arr.at[idx,"HoraPartida"] = dp["Hora"]
                arr.at[idx,"EquipPart"]   = dp["Equip"]

    # renomear
    arr.rename(columns={
      "Hora":"HoraChegada",
      "NumVoo":"VooChegada",
      "Equip":"EquipCheg"
    }, inplace=True)

    final_cols = [
      "Aeroporto","DataOper","HoraChegada","VooChegada",
      "HoraPartida","VooPartida","TempoSolo","EquipCheg","EquipPart"
    ]
    return arr[final_cols]

###############################################################################
# 5) FLUXO COMPLETO
###############################################################################
def process_ssim(ssim_file):
    lines = ssim_file.read().decode("latin-1").splitlines()

    # parse
    base=[]
    for l in lines:
        rec = parse_ssim_line(l)
        if rec:
            base.append(rec)
    if not base:
        return None

    # expand
    expanded=[]
    for br in base:
        e2 = expand_dates(br)
        expanded.extend(e2)
    if not expanded:
        return None

    # duplicar
    arrdep=[]
    for row in expanded:
        arrdep += build_arrdep_rows(row)
    if not arrdep:
        return None
    dfAD = pd.DataFrame(arrdep)

    # connect
    dfC = connect_rows(dfAD)
    if len(dfC)==0:
        return None

    return dfC

###############################################################################
def main():
    st.title("Conversor SSIM - (Código Antigo + TempoSolo em hh:mm)")

    ssim_file = st.file_uploader("Selecione o arquivo SSIM:", type=["ssim","txt"])
    if ssim_file:
        if st.button("Processar"):
            dfC = process_ssim(ssim_file)
            if dfC is None or len(dfC)==0:
                st.error("Nenhum voo processado ou nenhuma chegada conectada.")
                return

            # Exibe um sum. ex contagem p/ Aeroporto
            st.write("### Resumo final por Aeroporto")
            sum_air = dfC.groupby("Aeroporto")["VooChegada"].count().reset_index(name="Qtde")
            st.dataframe(sum_air)

            st.write("### Tabela final (Chegada+Partida)")
            st.dataframe(dfC)

            # Download
            csv_str = dfC.to_csv(index=False).encode("utf-8")
            st.download_button("Baixar CSV", data=csv_str, file_name="ssim_visao.csv", mime="text/csv")

if __name__=="__main__":
    main()
