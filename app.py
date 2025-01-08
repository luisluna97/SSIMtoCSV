import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

###############################################################################
# 1) PARSE SSIM (200 chars) POR OFFSETS CORRETOS
###############################################################################
def parse_ssim_line(line: str):
    """
    Lê uma linha de 200 caracteres do tipo 3, usando índices fixos.
    
    Offsets definidos com base no que você ajustou:
      line[0]   = '3' 
      line[2:4] = cia (2 chars) ex: "G3"
      line[5:13]= eight_char ("10020801" p.ex.)
      line[14:21]= dataIni (7 chars) ex "03FEB25"
      line[21:28]= dataFim (7 chars) ex "28FEB25"
      line[28:35]= freq (7 chars)
      line[36:51]= origem+hora (15 chars)
      line[52:67]= destino+hora(15 chars)
      line[72:75]= equip (3 chars)
      line[140:144]= nextVoo (4 chars)
    Ajuste se algo sair deslocado.
    """
    # Ver se tem >=200 chars
    if len(line)<200:
        return None
    if line[0] != '3':
        return None

    try:
        cia        = line[2:4].strip()
        eight_char = line[5:13].strip()    # "10020801"
        data_ini   = line[14:21].strip()   # "03FEB25"
        data_fim   = line[21:28].strip()   # "28FEB25"
        freq       = line[28:35].strip()   # "1234567"

        orig_blk   = line[36:51].strip()   # 15 chars
        dest_blk   = line[52:67].strip()   # 15 chars

        # Você mencionou equip é [72:75]
        equip      = line[72:75].strip()
        next_voo   = line[140:144].strip()

        # ex "1002" no eight_char
        num_voo = eight_char[:4]

        def parse_ap(block:str):
            # ex "CGH0900-0300"
            # apt= block[:3], hora= block[3:7]
            if len(block)>=7:
                apt = block[:3]
                hr4= block[3:7]
                return apt, hr4
            return "", ""

        orig, hp = parse_ap(orig_blk)
        dst , hc = parse_ap(dest_blk)

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
# 2) EXPAND DATAS
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

    expanded=[]
    d = dt_i
    while d<= dt_f:
        dow = d.weekday()+1
        if dow in freq_set:
            newr= dict(row)
            newr["DataOper"] = d.strftime("%d/%m/%Y")
            expanded.append(newr)
        d+=timedelta(days=1)
    return expanded

###############################################################################
# 3) DUPLICAR EM CHEGADA/PARTIDA
###############################################################################
def fix_time_4digits(tt:str)->str:
    if len(tt)==4:
        return tt[:2]+":"+tt[2:]
    return tt

def build_arrdep_rows(row: dict):
    dataop= row.get("DataOper","")
    orig  = row.get("Origem","")
    hp    = fix_time_4digits(row.get("HoraPartida",""))
    dst   = row.get("Destino","")
    hc    = fix_time_4digits(row.get("HoraChegada",""))

    recs=[]
    # PARTIDA
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
    # CHEGADA
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
# 4) CONECTAR => UMA LINHA POR CHEGADA+PARTIDA
###############################################################################
import math

def to_hhmm(delta_hrs: float)->str:
    """Formata tempo em hh:mm, mesmo se >24"""
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

    dep_grp = dep.groupby(["Aeroporto","NumVoo","DataOper"])
    for idx, rc in arr.iterrows():
        nxtv= rc["NextVoo"]
        if not nxtv:
            continue
        apr= rc["Aeroporto"]
        dop= rc["DataOper"]
        dtA= rc["dt"]
        key= (apr,nxtv,dop)
        if key in dep_grp.groups:
            idxs= dep_grp.groups[key]
            cand= dep.loc[idxs]
            cand2= cand[cand["dt"]>= dtA]
            if len(cand2)>0:
                c2s= cand2.sort_values("dt")
                dp= c2s.iloc[0]
                delta_hrs= (dp["dt"]- dtA).total_seconds()/3600
                arr.at[idx,"TempoSolo"]   = to_hhmm(delta_hrs)
                arr.at[idx,"VooPartida"]  = dp["NumVoo"]
                arr.at[idx,"HoraPartida"] = dp["Hora"]
                arr.at[idx,"EquipPart"]   = dp["Equip"]

    arr.rename(columns={
      "Hora":"HoraChegada",
      "NumVoo":"VooChegada",
      "Equip":"EquipCheg"
    }, inplace=True)

    final_cols= [
      "Aeroporto","DataOper","HoraChegada","VooChegada",
      "HoraPartida","VooPartida","TempoSolo","EquipCheg","EquipPart"
    ]
    return arr[final_cols]

###############################################################################
# FLUXO COMPLETO (parse->expand->dup->connect)
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
    for br in base:
        exs= expand_dates(br)
        expanded.extend(exs)
    if len(expanded)==0:
        return None

    # duplicar
    arrdep=[]
    for e in expanded:
        recs= build_arrdep_rows(e)
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
    st.title("Conversor SSIM (Offsets Fixos) -> Expand -> Duplicar -> Conectar")

    ssim_file= st.file_uploader("Arquivo SSIM (200 chars/linha):", type=["ssim","txt"])
    if ssim_file:
        if st.button("Processar"):
            dfC= process_ssim(ssim_file)
            if dfC is None or len(dfC)==0:
                st.error("Nenhuma linha processada ou 0 chegadas conectadas.")
                return
            st.write("### Tabela Final")
            st.dataframe(dfC)
            csv_str= dfC.to_csv(index=False).encode("utf-8")
            st.download_button("Baixar CSV", csv_str, file_name="ssim_final.csv", mime="text/csv")

if __name__=="__main__":
    main()
