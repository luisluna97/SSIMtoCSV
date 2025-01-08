import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

###############################################################################
# 1. PARSE VIA SPLIT - MESMA LÓGICA ANTIGA
###############################################################################
def parse_ssim_line(line: str):
    """
    Antigo approach com splitted:
    splitted[0] = '3'
    splitted[1] = 'G3' (cia)
    splitted[2] = '10000101J01DEC2308DEC23'  (eight_char + dataIni + dataFim)
    splitted[3] = '12345'  (frequência)
    splitted[4] = 'CGH0905...' (origem+hora)
    splitted[5] = 'SDU1010...' (dest+hora)
    splitted[6] = 'equip'
    splitted[9] = 'nextVoo' (às vezes)
    """

    line_str = line.strip()
    if not line_str.startswith("3"):
        return None

    splitted = line_str.split()
    if len(splitted) < 4:
        return None

    cia     = splitted[1]
    chunk2  = splitted[2]  # ex "10020101J01DEC2308DEC23"
    freq    = splitted[3]

    # Precisamos de ao menos 23 chars p/ dataIni(7) + dataFim(7)
    if len(chunk2) < 23:
        return None

    # ex chunk2[:8] => "10020101" => 4 chars p/ voo + 2 p/ dateCount + 2 p/ etapa (se for o caso)
    eight_char   = chunk2[:8]        # "10020101"
    data_ini_str = chunk2[9:16]      # "01DEC23"
    data_fim_str = chunk2[16:23]     # "08DEC23"
    num_voo      = eight_char[:4]    # ex "1002"

    # Origem e destino
    orig_blk = splitted[4] if len(splitted)>4 else ""
    dest_blk = splitted[5] if len(splitted)>5 else ""
    equip    = splitted[6] if len(splitted)>7 else ""
    next_voo = splitted[9] if len(splitted)>9 else ""

    def parse_apt(block:str):
        """
        ex: 'CGH0905...' => apt=CGH,hora=0905
        se len(block)<7 => retorna '', ''
        """
        if len(block)>=7:
            apt  = block[:3]
            hora = block[3:7]
            return apt, hora
        return "", ""

    orig,hp = parse_apt(orig_blk)
    dst ,hc = parse_apt(dest_blk)

    return {
      "Cia": cia,
      "NumVoo": num_voo,
      "DataIni": data_ini_str,   # ex "01DEC23"
      "DataFim": data_fim_str,   # ex "08DEC23"
      "Freq": freq,              # ex "1234567"
      "Origem": orig,
      "HoraPartida": hp,
      "Destino": dst,
      "HoraChegada": hc,
      "Equip": equip,
      "NextVoo": next_voo
    }

###############################################################################
# 2. EXPAND DATAS (DataIni->DataFim) usando freq=1..7 (1=Seg,...7=Dom)
###############################################################################
def expand_dates(row: dict):
    di = row.get("DataIni","")
    df = row.get("DataFim","")
    freq = row.get("Freq","")

    if not di or not df:
        return []

    try:
        dt_i = datetime.strptime(di, "%d%b%y")   # ex "01DEC23"
        dt_f = datetime.strptime(df, "%d%b%y")   # ex "08DEC23"
    except:
        return []

    freq_set = set()
    for c in freq:
        if c.isdigit():
            freq_set.add(int(c))  # 1=Seg,...,7=Dom

    expanded=[]
    d = dt_i
    while d<=dt_f:
        dow = d.weekday()+1  # python: 0=Mon,...6=Sun => +1 =>1=Mon,...7=Sun
        if dow in freq_set:
            newr = dict(row)
            # dataOper => dd/mm/yyyy
            newr["DataOper"] = d.strftime("%d/%m/%Y")
            expanded.append(newr)
        d+=timedelta(days=1)
    return expanded

###############################################################################
# 3. DUPLICAR EM CHEGADA / PARTIDA
###############################################################################
def fix_time_4digits(tt:str)->str:
    if len(tt)==4:
        return tt[:2]+":"+tt[2:]
    return tt

def build_arrdep_rows(row: dict):
    """
    Ex: row => {Cia,NumVoo,DataOper,Origem,HoraPartida,Destino,HoraChegada,Equip,NextVoo,...}
    Gera 2 lines:
      P => Partida
      C => Chegada
    """
    dataop = row.get("DataOper","")
    orig   = row.get("Origem","")
    hp     = fix_time_4digits(row.get("HoraPartida",""))
    dst    = row.get("Destino","")
    hc     = fix_time_4digits(row.get("HoraChegada",""))

    recs=[]
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
# 4. CONECTA => 1 LINHA p/ cada Chegada, se NextVoo => acha Partida
#    Result colunas:
#    Aeroporto, DataOper, HoraChegada, VooChegada, HoraPartida, VooPartida,
#    TempoSolo, EquipCheg, EquipPart
###############################################################################
def to_hhmm(delta_hrs: float)->str:
    """ex: 30.5 => '30:30' (hh:mm)"""
    if delta_hrs<0:
        return "00:00"
    h = int(delta_hrs)
    m = int(round((delta_hrs - h)*60))
    return f"{h}:{m:02d}"

def connect_rows(df):
    df["dt"] = pd.to_datetime(df["DataOper"]+" "+df["Hora"], format="%d/%m/%Y %H:%M", errors="coerce")

    arr = df[df["CP"]=="C"].copy()
    dep = df[df["CP"]=="P"].copy()

    arr["HoraPartida"] = None
    arr["VooPartida"]  = None
    arr["EquipPart"]   = None
    arr["TempoSolo"]   = None

    # agrupar departures => (Aeroporto,NumVoo,DataOper)
    dep_grp = dep.groupby(["Aeroporto","NumVoo","DataOper"])

    for idx, rowC in arr.iterrows():
        nxtv = rowC.get("NextVoo","")
        if not nxtv:
            continue
        apr = rowC["Aeroporto"]
        dOp = rowC["DataOper"]
        dtC = rowC["dt"]
        key = (apr,nxtv,dOp)
        if key in dep_grp.groups:
            idxs = dep_grp.groups[key]
            cand = dep.loc[idxs]
            # filtra cand dt>= dtC
            cand2= cand[cand["dt"]>= dtC]
            if len(cand2)>0:
                c2s = cand2.sort_values("dt")
                dp  = c2s.iloc[0]
                delta_hrs= (dp["dt"]- dtC).total_seconds()/3600
                arr.at[idx,"TempoSolo"]   = to_hhmm(delta_hrs)
                arr.at[idx,"VooPartida"]  = dp["NumVoo"]
                arr.at[idx,"HoraPartida"] = dp["Hora"]
                arr.at[idx,"EquipPart"]   = dp["Equip"]

    # rename col
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
# 5. PROCESS SSIM (parse -> expand -> duplicar -> connect)
###############################################################################
def process_ssim(ssim_file):
    lines = ssim_file.read().decode("latin-1").splitlines()
    base=[]
    for l in lines:
        rec = parse_ssim_line(l)
        if rec:
            base.append(rec)
    if not base:
        return None

    expanded=[]
    for b in base:
        exps = expand_dates(b)
        expanded.extend(exps)
    if not expanded:
        return None

    arrdep=[]
    for e in expanded:
        arrdep += build_arrdep_rows(e)
    if not arrdep:
        return None
    dfAD= pd.DataFrame(arrdep)

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

            # Exibir sum
            st.write("### Resumo final por Aeroporto")
            sum_air = dfC.groupby("Aeroporto")["VooChegada"].count().reset_index(name="Qtde")
            st.dataframe(sum_air)

            st.write("### Tabela final")
            st.dataframe(dfC)

            # Baixar CSV
            csv_str= dfC.to_csv(index=False).encode("utf-8")
            st.download_button("Baixar CSV", data=csv_str, file_name="ssim_visao.csv", mime="text/csv")


if __name__=="__main__":
    main()
