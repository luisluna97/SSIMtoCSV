import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

###############################################################################
# 1) PARSE POR OFFSETS FIXOS (ASSUME 200 CHARS EM TODAS AS LINHAS)
###############################################################################
def parse_ssim_line(line: str):
    """
    Lê uma linha de 200 chars do tipo 3. 
    Exemplo de offsets (ajuste se necessário):
      line[0]   = '3'
      line[1]   = espaço
      line[2:4] = cia (2 chars)
      line[4]   = espaço
      line[6:14]= 8-char field (p.ex "10020101")
      line[14]  = status (1 char?)
      line[15:22] = dataIni (7 chars, ex "01JAN25")
      line[22:29] = dataFim (7 chars, ex "08JAN25")
      line[29]     = espaço
      line[30:37] = freq (7 chars, ex "1234567")
      line[37:44], line[44:51], etc. => A definir
      ...
      line[37:52] => Origem+hora+tz? (15 chars)
      line[52:67] => Destino+hora+tz? (15 chars)
      line[68:71] => Equip (3 chars)
      ...
      line[120:124] => nextVoo (4 chars)
      ...
    Se a linha for <200 chars, descartamos.
    Se algo falhar, retornamos None.
    """

    # Checar se a linha tem 200 chars
    if len(line) < 200:
        return None
    if line[0] != '3':
        return None

    try:
        # airline
        cia        = line[2:4].strip()
        eight_char = line[6:14].strip()    # ex "10020101"
        # status    = line[14]
        data_ini   = line[15:22].strip()   # "01JAN25"
        data_fim   = line[22:29].strip()   # "08JAN25"
        freq       = line[30:37].strip()   # "1234567"

        # Origem + hora
        # Ex.: line[37:52] => "CGH09050905-0300"
        # Mas se for REAL SSIM, ver se é 15 chars
        orig_blk   = line[37:52].strip()
        # Destino + hora
        dest_blk   = line[52:67].strip()
        equip      = line[68:71].strip()
        # nextVoo
        next_voo   = line[120:124].strip()

        # ex "10020101" => num_voo = "1002"
        num_voo = eight_char[:4]

        def parse_apt(block:str):
            """
            Se block ex "CGH0905-0300", 
            apt= block[:3] => "CGH"
            hora= block[3:7] => "0905" (ou "0905" e ignora tz?)
            Ajuste se seu tz for fixo. 
            """
            if len(block)>=7:
                apt  = block[:3]
                hhmm = block[3:7]
                return apt, hhmm
            return "", ""

        orig,hp = parse_apt(orig_blk)
        dst ,hc = parse_apt(dest_blk)

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
# 2) EXPAND DATAS (MESMA LÓGICA)
###############################################################################
def expand_dates(row: dict):
    di = row.get("DataIni","")
    df = row.get("DataFim","")
    freq_str = row.get("Freq","")
    if not di or not df:
        return []
    try:
        dt_i = datetime.strptime(di, "%d%b%y")
        dt_f = datetime.strptime(df, "%d%b%y")
    except:
        return []

    freq_set = set()
    for c in freq_str:
        if c.isdigit():
            freq_set.add(int(c))  # 1=seg,...7=dom

    expanded=[]
    d= dt_i
    while d<= dt_f:
        dow= d.weekday()+1
        if dow in freq_set:
            newr = dict(row)
            newr["DataOper"] = d.strftime("%d/%m/%Y")
            expanded.append(newr)
        d+=timedelta(days=1)
    return expanded

###############################################################################
# 3) DUPLICAR C/P
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
# 4) CONECTAR => UMA LINHA POR CHEGADA + PARTIDA
###############################################################################
def to_hhmm(delta_hrs:float)->str:
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

    # agrupar dep => (Aeroporto, NumVoo, DataOper)
    dep_grp = dep.groupby(["Aeroporto","NumVoo","DataOper"])

    for idx, rowC in arr.iterrows():
        nxtv = rowC.get("NextVoo","")
        if not nxtv:
            continue
        apr = rowC["Aeroporto"]
        dOp = rowC["DataOper"]
        dtC = rowC["dt"]
        key= (apr,nxtv,dOp)
        if key in dep_grp.groups:
            idxs = dep_grp.groups[key]
            cand = dep.loc[idxs]
            cand2= cand[cand["dt"]>= dtC]
            if len(cand2)>0:
                c2s= cand2.sort_values("dt")
                dp = c2s.iloc[0]
                delta_h = (dp["dt"] - dtC).total_seconds()/3600
                arr.at[idx,"TempoSolo"]   = to_hhmm(delta_h)
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
      "HoraPartida","VooPartida","TempoSolo","EquipCheg","EquipPart"
    ]
    return arr[final_cols]

###############################################################################
def process_ssim_file(lines):
    """
    Este é o fluxo principal para rodar no Colab ou local.
    """
    # 1) parse
    base=[]
    for l in lines:
        rec = parse_ssim_line(l)
        if rec:
            base.append(rec)
    if not base:
        return pd.DataFrame()

    # 2) expand
    expanded=[]
    for b in base:
        exps = expand_dates(b)
        expanded.extend(exps)
    if not expanded:
        return pd.DataFrame()

    # 3) duplicar
    arrdep=[]
    for e in expanded:
        arrdep += build_arrdep_rows(e)
    if not arrdep:
        return pd.DataFrame()
    dfAD = pd.DataFrame(arrdep)

    # 4) connect
    dfC = connect_rows(dfAD)
    return dfC


###############################################################################
# ABAIXO: CÓDIGO STREAMLIT (SE QUISER RODAR NO COLAB, ADAPTAR)
###############################################################################
def main():
    st.title("Conversor SSIM com offsets fixos (200 chars) E parse antigo")
    ssim_file = st.file_uploader("Selecione o arquivo SSIM (200 chars p/ linha):", type=["ssim","txt"])
    if ssim_file:
        lines = ssim_file.read().decode("latin-1").splitlines()

        dfC = process_ssim_file(lines)

        if len(dfC)==0:
            st.error("Nenhuma linha processada ou nenhuma chegada conectada.")
            return

        # Exibir
        st.dataframe(dfC)
        csv_str = dfC.to_csv(index=False).encode("utf-8")
        st.download_button("Baixar CSV", csv_str, file_name="ssim_final.csv", mime="text/csv")

if __name__=="__main__":
    main()
