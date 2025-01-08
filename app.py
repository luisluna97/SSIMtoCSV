import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

###############################################################################
# PARSE COM OFFSETS DEFINIDOS:
# Baseado no exemplo que voce passou com '*' no lugar de espaco
###############################################################################
def parse_ssim_line(line: str, debug=False):
    # Ver se tem >= 200 chars
    if len(line) < 200:
        if debug:
            st.write(f"DEBUG parse_ssim_line: linha com <200 chars (len={len(line)}), descartada:", repr(line))
        return None
    
    # Checar se [0] == '3'
    if line[0] != '3':
        if debug:
            st.write("DEBUG: [0] != '3', descartada")
        return None

    # Tentar extrair pelos offsets (ver tabela acima):
    # Ajuste indices caso seu layout seja ligeiramente diferente

    try:
        cia          = line[2:4].strip()            # ex "G3"
        eight_char   = line[5:13].strip()           # ex "10020801"
        status_char  = line[13]                     # 'J' (se usar)
        data_ini     = line[14:21].strip()          # "03FEB25"
        data_fim     = line[21:28].strip()          # "28FEB25"
        freq         = line[28:35].strip()          # "1234567"
        origem_blk   = line[36:51].strip()          # ex "CGH09000900-0300"
        destino_blk  = line[52:67].strip()          # ex "SDU10051005-0300"
        equip        = line[68:71].strip()          # ex "73X"
        # nextVoo supondo que esteja em [120:124]
        next_voo     = line[120:124].strip()

        # Pegar o num_voo => ex "1002" a partir de eight_char
        num_voo = eight_char[:4]

        def parse_ap(block:str):
            # ex "CGH09000900-0300" => apt= "CGH", hora= "0900"
            # Se for 15 chars => "CGH09000900-0300", p. ex.
            # Vamos so pegar apt= block[:3], hora= block[3:7]
            if len(block)>=7:
                apt = block[:3]
                hr4= block[3:7]  # "0900"
                return apt, hr4
            return "", ""

        orig, hp = parse_ap(origem_blk)
        dst , hc = parse_ap(destino_blk)

        record = {
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
        if debug:
            st.write("DEBUG offsets parse =>", record)
        return record

    except Exception as e:
        if debug:
            st.write("DEBUG parse error =>", e)
        return None

###############################################################################
def expand_dates(row: dict, debug=False):
    di = row.get("DataIni","")
    df = row.get("DataFim","")
    freq_str = row.get("Freq","")
    if not di or not df:
        if debug:
            st.write(f"DEBUG expand_dates => dataIni/dataFim em branco => {row}")
        return []
    try:
        dt_i = datetime.strptime(di, "%d%b%y")
        dt_f = datetime.strptime(df, "%d%b%y")
    except:
        if debug:
            st.write(f"DEBUG expand_dates => erro no strptime => {di}, {df}")
        return []

    freq_set = set()
    for c in freq_str:
        if c.isdigit():
            freq_set.add(int(c))

    expanded=[]
    d= dt_i
    while d<= dt_f:
        dow = d.weekday()+1
        if dow in freq_set:
            newr = dict(row)
            newr["DataOper"] = d.strftime("%d/%m/%Y")
            expanded.append(newr)
        d+=timedelta(days=1)
    if debug and len(expanded)==0:
        st.write("DEBUG expand_dates => freq nao casou datas =>", row)
    return expanded

def fix_time_4digits(tt:str)-> str:
    if len(tt)==4:
        return tt[:2]+":"+tt[2:]
    return tt

def build_arrdep_rows(row: dict, debug=False):
    dataop = row.get("DataOper","")
    orig   = row.get("Origem","")
    hp     = fix_time_4digits(row.get("HoraPartida",""))
    dst    = row.get("Destino","")
    hc     = fix_time_4digits(row.get("HoraChegada",""))

    recs=[]
    if orig and hp:
        recs.append({
          "Aeroporto": orig,
          "CP":"P",
          "DataOper": dataop,
          "NumVoo": row["NumVoo"],
          "Hora": hp,
          "Equip": row.get("Equip",""),
          "NextVoo": row.get("NextVoo","")
        })
    if dst and hc:
        recs.append({
          "Aeroporto": dst,
          "CP":"C",
          "DataOper": dataop,
          "NumVoo": row["NumVoo"],
          "Hora": hc,
          "Equip": row.get("Equip",""),
          "NextVoo": row.get("NextVoo","")
        })
    if debug and len(recs)==0:
        st.write("DEBUG build_arrdep => Orig/Dest vazios =>", row)
    return recs

def to_hhmm(delta_hrs:float)->str:
    if delta_hrs<0:
        return "00:00"
    hh = int(delta_hrs)
    mm = int(round((delta_hrs - hh)*60))
    return f"{hh}:{mm:02d}"

def connect_rows(df, debug=False):
    df["dt"] = pd.to_datetime(df["DataOper"]+" "+df["Hora"], format="%d/%m/%Y %H:%M", errors="coerce")

    arr = df[df["CP"]=="C"].copy()
    dep = df[df["CP"]=="P"].copy()

    arr["HoraPartida"] = None
    arr["VooPartida"]  = None
    arr["EquipPart"]   = None
    arr["TempoSolo"]   = None

    dep_gb = dep.groupby(["Aeroporto","NumVoo","DataOper"])

    connect_count=0
    for idx, rowC in arr.iterrows():
        nxtv = rowC.get("NextVoo","")
        if not nxtv:
            continue
        apr = rowC["Aeroporto"]
        dOp = rowC["DataOper"]
        dtC = rowC["dt"]
        key = (apr,nxtv,dOp)
        if key in dep_gb.groups:
            idxs = dep_gb.groups[key]
            cand = dep.loc[idxs]
            cand2= cand[cand["dt"]>= dtC]
            if len(cand2)>0:
                c2s= cand2.sort_values("dt")
                dp= c2s.iloc[0]
                delta_hrs= (dp["dt"] - dtC).total_seconds()/3600
                arr.at[idx,"TempoSolo"]   = to_hhmm(delta_hrs)
                arr.at[idx,"VooPartida"]  = dp["NumVoo"]
                arr.at[idx,"HoraPartida"] = dp["Hora"]
                arr.at[idx,"EquipPart"]   = dp["Equip"]
                connect_count+=1

    if debug:
        st.write(f"DEBUG connect => conexões feitas: {connect_count}")

    arr.rename(columns={
      "Hora":"HoraChegada",
      "NumVoo":"VooChegada",
      "Equip":"EquipCheg"
    }, inplace=True)

    final_cols = [
      "Aeroporto","DataOper","HoraChegada","VooChegada","HoraPartida","VooPartida","TempoSolo","EquipCheg","EquipPart"
    ]
    return arr[final_cols]

def process_ssim(lines, debug=False):
    # 1 parse
    base=[]
    parse_count=0
    for i, line in enumerate(lines):
        rec = parse_ssim_line(line, debug)
        if rec:
            base.append(rec)
            parse_count+=1
    if debug:
        st.write("DEBUG parse => base len =", parse_count)

    if len(base)==0:
        return None

    # 2 expand
    expanded=[]
    for br in base:
        exs = expand_dates(br, debug)
        expanded.extend(exs)
    if debug:
        st.write("DEBUG expand => expanded len =", len(expanded))
    if len(expanded)==0:
        return None

    # 3 duplicar
    arrdep=[]
    for e2 in expanded:
        recs= build_arrdep_rows(e2, debug)
        arrdep.extend(recs)
    if debug:
        st.write("DEBUG duplicar => arrdep len =", len(arrdep))
    if len(arrdep)==0:
        return None

    dfAD = pd.DataFrame(arrdep)
    # 4 connect
    dfC = connect_rows(dfAD, debug)
    if debug:
        st.write("DEBUG connect => final len =", len(dfC))
    if len(dfC)==0:
        return None
    return dfC


def main():
    st.title("Debug SSIM com offsets fixos")

    debug_mode = st.checkbox("Exibir logs de debug", value=False)
    ssim_file = st.file_uploader("Selecione SSIM (200 chars/linha):", type=["ssim","txt"])
    if ssim_file:
        lines = ssim_file.read().decode("latin-1").splitlines()
        st.write("DEBUG: total lines =", len(lines))

        if st.button("Processar"):
            dfC = process_ssim(lines, debug=debug_mode)
            if dfC is None or len(dfC)==0:
                st.error("Nenhuma linha no resultado final.")
                return
            st.write("## Tabela Final")
            st.dataframe(dfC)
            csv_str = dfC.to_csv(index=False).encode("utf-8")
            st.download_button("Baixar CSV", csv_str, file_name="ssim_final.csv", mime="text/csv")

if __name__=="__main__":
    main()
