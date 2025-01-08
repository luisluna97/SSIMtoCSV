import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

###############################################################################
# 1) Parse each 200-char SSIM line (type 3) with fixed offsets
###############################################################################
def parse_ssim_line(line: str):
    """
    OFFSETS (adjust as needed):
      line[0]    = '3'
      line[2:4]  = Cia (2 chars)
      line[5:13] = 8-char field (p.ex "10020801")
      line[14:21]= DataIni (7 chars, ex. "03FEB25")
      line[21:28]= DataFim (7 chars, ex. "28FEB25")
      line[28:35]= freq (7 chars)
      line[36:51]= origem+hora (15 chars)
      line[52:67]= destino+hora (15 chars)
      line[72:75]= equip (3 chars) -- Ex: "7M8"
      line[140:144]= nextVoo (4 chars) -- Ex: "2136"
    """

    if len(line) < 200:
        return None
    if line[0] != '3':
        return None

    try:
        cia        = line[2:4].strip()
        eight_char = line[5:13].strip()  
        data_ini   = line[14:21].strip()  
        data_fim   = line[21:28].strip()  
        freq       = line[28:35].strip()  

        orig_blk   = line[36:51].strip()  
        dest_blk   = line[52:67].strip()  

        equip      = line[72:75].strip()  
        next_voo   = line[140:144].strip()  

        num_voo = eight_char[:4]

        def parse_apt(block: str):
            # ex "CGH0900-0300" => apt= "CGH", hora= "0900"
            if len(block) >= 7:
                apt = block[:3]
                hhmm= block[3:7]
                return apt, hhmm
            return "", ""

        orig, hp = parse_apt(orig_blk)
        dst , hc = parse_apt(dest_blk)

        return {
          "Cia": cia,
          "NumVoo": num_voo,
          "DataIni": data_ini,
          "DataFim": data_fim,
          "Freq": freq,
          "Origem": orig,
          "HoraPartida": hp,
          "Destino": dst,
          "HoraChegada": hc,
          "Equip": equip,
          "NextVoo": next_voo
        }
    except:
        return None

###############################################################################
# 2) Expand dates (DataIni->DataFim), freq=1..7 => 1=Mon,...7=Sun
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

    expanded = []
    d = dt_i
    while d <= dt_f:
        dow = d.weekday() + 1  # 1=Mon,...7=Sun
        if dow in freq_set:
            newr = dict(row)
            newr["DataOper"] = d.strftime("%d/%m/%Y")
            expanded.append(newr)
        d += timedelta(days=1)
    return expanded

###############################################################################
# 3) Duplicate each flight into Chegada/Partida
###############################################################################
def fix_time_4digits(tt: str) -> str:
    if len(tt) == 4:
        return tt[:2] + ":" + tt[2:]
    return tt

def build_arrdep_rows(row: dict):
    dataop = row["DataOper"]
    orig   = row["Origem"]
    hp     = fix_time_4digits(row["HoraPartida"])
    dst    = row["Destino"]
    hc     = fix_time_4digits(row["HoraChegada"])

    recs=[]
    # Partida
    if orig and hp:
        recs.append({
          "Aeroporto": orig,
          "CP": "P",
          "DataOper": dataop,
          "NumVoo": row["NumVoo"],
          "Hora": hp,
          "Equip": row["Equip"],
          "NextVoo": row["NextVoo"]
        })
    # Chegada
    if dst and hc:
        recs.append({
          "Aeroporto": dst,
          "CP": "C",
          "DataOper": dataop,
          "NumVoo": row["NumVoo"],
          "Hora": hc,
          "Equip": row["Equip"],
          "NextVoo": row["NextVoo"]
        })
    return recs

###############################################################################
# 4) Connect arrivals & next flight => single row
###############################################################################
def to_hhmm(delta_hrs: float) -> str:
    if delta_hrs < 0:
        return "00:00"
    h = int(delta_hrs)
    m = int(round((delta_hrs - h)*60))
    return f"{h}:{m:02d}"

def connect_rows(df):
    df["dt"] = pd.to_datetime(df["DataOper"] + " " + df["Hora"], format="%d/%m/%Y %H:%M", errors="coerce")

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
        dtA = rowC["dt"]
        key = (apr, nxtv, dop)
        if key in dep_gb.groups:
            idxs = dep_gb.groups[key]
            cand = dep.loc[idxs]
            cand2= cand[cand["dt"]>= dtA]
            if len(cand2)>0:
                c2s = cand2.sort_values("dt")
                dp  = c2s.iloc[0]
                delta_hrs = (dp["dt"] - dtA).total_seconds()/3600
                arr.at[idx,"TempoSolo"]   = to_hhmm(delta_hrs)
                arr.at[idx,"VooPartida"]  = dp["NumVoo"]
                arr.at[idx,"HoraPartida"] = dp["Hora"]
                arr.at[idx,"EquipPart"]   = dp["Equip"]

    arr.rename(columns={
      "Hora": "HoraChegada",
      "NumVoo": "VooChegada",
      "Equip": "EquipCheg"
    }, inplace=True)

    final_cols = [
      "Aeroporto","DataOper","HoraChegada","VooChegada",
      "HoraPartida","VooPartida","TempoSolo","EquipCheg","EquipPart"
    ]
    return arr[final_cols]

###############################################################################
# FLUXO COMPLETO
###############################################################################
def process_ssim(ssim_file):
    lines = ssim_file.read().decode("latin-1").splitlines()

    # parse
    base=[]
    for l in lines:
        rec= parse_ssim_line(l)
        if rec:
            base.append(rec)
    if len(base)==0:
        return None

    # expand
    expanded=[]
    for b in base:
        e2= expand_dates(b)
        expanded.extend(e2)
    if len(expanded)==0:
        return None

    # duplicar
    arrdep=[]
    for r in expanded:
        recs= build_arrdep_rows(r)
        arrdep.extend(recs)
    if len(arrdep)==0:
        return None
    dfAD= pd.DataFrame(arrdep)

    # connect
    dfC= connect_rows(dfAD)
    if len(dfC)==0:
        return None
    return dfC

###############################################################################
def main():
    st.title("SSIM to CSV Converter")
    st.subheader("This application reads a 200-char SSIM file, expands flights by frequency, duplicates (arr/dep), connects next flights, and provides a final CSV.")

    ssim_file= st.file_uploader("Upload SSIM (200 chars/line):", type=["ssim","txt"])
    if ssim_file:
        if st.button("Process"):
            dfC = process_ssim(ssim_file)
            if dfC is None or len(dfC)==0:
                st.error("No processed lines or no arrivals connected.")
                return

            # Cria a coluna 'Month' p/ extrair o mês
            dfC["dtM"] = pd.to_datetime(dfC["DataOper"], format="%d/%m/%Y", errors="coerce")
            dfC["Month"] = dfC["dtM"].dt.to_period("M").astype(str)

            # Monta a matriz (Aeroporto x Month)
            # Contando quantas linhas => pivot
            summary = dfC.groupby(["Aeroporto","Month"]).size().unstack(fill_value=0)

            st.write("### Summary Matrix (Aeroporto x Month)")
            st.dataframe(summary)

            st.write("### Final Table (Arr/Dep Connected)")
            st.dataframe(dfC.drop(columns=["dtM","Month"]))

            # Download
            csv_str = dfC.drop(columns=["dtM","Month"]).to_csv(index=False).encode("utf-8")
            st.download_button("Download CSV", csv_str, file_name="ssim_final.csv", mime="text/csv")


if __name__=="__main__":
    main()
