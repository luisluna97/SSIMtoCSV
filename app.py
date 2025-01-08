import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

###############################################################################
# Debug flags: para não poluir demais, podemos usar checkboxes no app
###############################################################################
def parse_ssim_line(line: str, debug_enabled: bool=False):
    """
    Tenta parsear pelos offsets fixos se >= 200 chars, senão fallback no split.
    Exibe logs caso debug_enabled seja True.
    """
    if debug_enabled:
        st.write("DEBUG Original line (len={}):".format(len(line)), repr(line))

    # se <200 chars => fallback
    if len(line) >= 200:
        rec = parse_by_offsets(line, debug_enabled)
        if rec:
            return rec
        else:
            # fallback
            if debug_enabled:
                st.write("DEBUG substring approach falhou, tentando split()")
    return parse_by_split(line, debug_enabled)

def parse_by_offsets(line: str, debug_enabled: bool=False):
    """Exemplo de offsets fixos."""
    if line[0] != '3':
        return None
    try:
        cia        = line[2:4].strip()
        eight_char = line[6:14].strip()
        data_ini   = line[15:22].strip()
        data_fim   = line[22:29].strip()
        freq       = line[30:37].strip()
        orig_blk   = line[37:52].strip()
        dest_blk   = line[52:67].strip()
        equip      = line[68:71].strip()
        next_voo   = line[120:124].strip() if len(line)>=124 else ""

        num_voo = eight_char[:4]  # "1002"
        def parse_ap(bk:str):
            if len(bk)>=7:
                apt = bk[:3]
                hora= bk[3:7]
                return apt, hora
            return "", ""

        orig, hp = parse_ap(orig_blk)
        dst , hc = parse_ap(dest_blk)

        if debug_enabled:
            st.write("DEBUG offsets parse =>", {
                "cia": cia, "num_voo": num_voo, 
                "data_ini": data_ini, "data_fim": data_fim, 
                "freq": freq, 
                "origem": orig, "horaPart": hp, 
                "destino": dst, "horaCheg": hc,
                "equip": equip, "next_voo": next_voo
            })

        # Se freq, etc. estiverem vazios ou algo, retorno None se quiser
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

def parse_by_split(line: str, debug_enabled: bool=False):
    """Fallback parse. Similar ao 'código que funcionava'."""
    splitted = line.strip().split()
    if debug_enabled:
        st.write("DEBUG splitted =>", splitted)
    if len(splitted)<4:
        return None
    if splitted[0]!="3":
        return None

    cia = splitted[1]
    chunk2 = splitted[2]
    freq_str= splitted[3]
    if len(chunk2)<23:
        return None

    eight_char   = chunk2[:8]
    data_ini_str = chunk2[9:16]
    data_fim_str = chunk2[16:23]
    num_voo      = eight_char[:4]

    orig_blk = splitted[4] if len(splitted)>4 else ""
    dest_blk = splitted[5] if len(splitted)>5 else ""
    equip    = splitted[6] if len(splitted)>6 else ""
    nxtvoo   = splitted[9] if len(splitted)>9 else ""

    def parse_ap(bk:str):
        if len(bk)>=7:
            return bk[:3], bk[3:7]
        return "",""

    o,hp = parse_ap(orig_blk)
    d,hc = parse_ap(dest_blk)

    if debug_enabled:
        st.write("DEBUG splitted parse =>", {
            "cia": cia, "num_voo": num_voo,
            "dataIni": data_ini_str, "dataFim": data_fim_str,
            "freq": freq_str,
            "origem": o, "horaPart": hp,
            "destino": d, "horaCheg": hc,
            "equip": equip, "next_voo": nxtvoo
        })

    return {
      "Cia": cia,
      "NumVoo": num_voo,
      "DataIni": data_ini_str,
      "DataFim": data_fim_str,
      "Freq": freq_str,
      "Origem": o,
      "HoraPartida": hp,
      "Destino": d,
      "HoraChegada": hc,
      "Equip": equip,
      "NextVoo": nxtvoo
    }

###############################################################################
# 2) expand_dates
###############################################################################
def expand_dates(row: dict, debug_enabled: bool=False):
    di = row.get("DataIni","")
    df = row.get("DataFim","")
    freq = row.get("Freq","")
    if not di or not df:
        return []
    try:
        dt_i = datetime.strptime(di, "%d%b%y")
        dt_f = datetime.strptime(df, "%d%b%y")
    except:
        if debug_enabled:
            st.write("DEBUG expand_dates => Erro ao converter dataIni/dataFim =>", di, df)
        return []

    freq_set = set()
    for c in freq:
        if c.isdigit():
            freq_set.add(int(c))

    expanded=[]
    d= dt_i
    while d<=dt_f:
        dow = d.weekday()+1
        if dow in freq_set:
            newr = dict(row)
            newr["DataOper"] = d.strftime("%d/%m/%Y")
            expanded.append(newr)
        d+=timedelta(days=1)
    return expanded

###############################################################################
# 3) duplicar
###############################################################################
def fix_time_4digits(tt:str)->str:
    if len(tt)==4:
        return tt[:2]+":"+tt[2:]
    return tt

def build_arrdep_rows(row: dict, debug_enabled: bool=False):
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
          "CP":"P",
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
          "CP":"C",
          "DataOper": dataop,
          "NumVoo": row["NumVoo"],
          "Hora": hc,
          "Equip": row.get("Equip",""),
          "NextVoo": row.get("NextVoo","")
        })

    if debug_enabled and len(recs)==0:
        st.write("DEBUG: build_arrdep_rows => Origem/Destino vazios =>", row)
    return recs

###############################################################################
# 4) connect
###############################################################################
def to_hhmm(delta_hrs:float)->str:
    if delta_hrs<0:
        return "00:00"
    hh = int(delta_hrs)
    mm = int(round((delta_hrs - hh)*60))
    return f"{hh}:{mm:02d}"

def connect_rows(df, debug_enabled: bool=False):
    df["dt"] = pd.to_datetime(df["DataOper"]+" "+df["Hora"], format="%d/%m/%Y %H:%M", errors="coerce")

    arr = df[df["CP"]=="C"].copy()
    dep = df[df["CP"]=="P"].copy()

    arr["HoraPartida"] = None
    arr["VooPartida"]  = None
    arr["EquipPart"]   = None
    arr["TempoSolo"]   = None

    dep_gb = dep.groupby(["Aeroporto","NumVoo","DataOper"])

    final_count=0
    for idx, rowC in arr.iterrows():
        nxtv = rowC.get("NextVoo","")
        if not nxtv:
            continue
        apr = rowC["Aeroporto"]
        dOp = rowC["DataOper"]
        dtC = rowC["dt"]
        key= (apr,nxtv,dOp)
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
                final_count+=1

    if debug_enabled:
        st.write(f"DEBUG connect_rows => {final_count} conexões feitas.")
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
# PROCESS FUNCTION
###############################################################################
def process_ssim(lines, debug_enabled=False):
    # 1 parse
    base=[]
    for i, l in enumerate(lines):
        rec = parse_ssim_line(l, debug_enabled)
        if rec:
            base.append(rec)
    if debug_enabled:
        st.write("DEBUG parse => base rows len =", len(base))

    # 2 expand
    expanded=[]
    for br in base:
        exs = expand_dates(br, debug_enabled)
        expanded.extend(exs)
    if debug_enabled:
        st.write("DEBUG expand => expanded len =", len(expanded))

    # 3 duplicar
    arrdep=[]
    for e2 in expanded:
        recs= build_arrdep_rows(e2, debug_enabled)
        arrdep.extend(recs)
    if debug_enabled:
        st.write("DEBUG duplicar => arrdep len =", len(arrdep))

    dfAD = pd.DataFrame(arrdep)
    if len(dfAD)==0:
        return pd.DataFrame()

    # 4 connect
    dfC = connect_rows(dfAD, debug_enabled)
    if debug_enabled:
        st.write("DEBUG connect => final len =", len(dfC))
    return dfC

###############################################################################
def main():
    st.title("Debug SSIM - Parse/Expand/Duplicate/Connect")

    debug_mode = st.checkbox("Ativar logs de depuração?", value=False)
    ssim_file = st.file_uploader("Selecione SSIM:", type=["ssim","txt"])

    if ssim_file:
        lines = ssim_file.read().decode("latin-1").splitlines()
        st.write("DEBUG: total de linhas no arquivo =", len(lines))

        if st.button("Processar"):
            dfC = process_ssim(lines, debug_enabled=debug_mode)
            if len(dfC)==0:
                st.error("Nenhuma linha no resultado final.")
                return
            st.write("## Tabela Final")
            st.dataframe(dfC)
            csv_str = dfC.to_csv(index=False).encode("utf-8")
            st.download_button("Baixar CSV Final", csv_str, file_name="ssim_final.csv", mime="text/csv")

if __name__=="__main__":
    main()
