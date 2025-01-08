import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

###############################################################################
# PARSE ROBUSTO (TENTA SUBSTRING FIXO SE A LINHA ~200 CHARS, SENÃO FALLBACK)
###############################################################################
def robust_parse_ssim_line(line: str):
    line_str = line.rstrip("\n")
    if not line_str.strip().startswith("3"):
        return None

    # Se >= 120..200 chars, tentar substring fixo
    if len(line_str) >= 120:
        rec = parse_by_substring(line_str)
        if rec:
            return rec
    # fallback
    return parse_by_split(line_str)

def parse_by_substring(line_str: str):
    """Exemplo de slicing fixo. Ajuste conforme seu SSIM real."""
    try:
        cia        = line_str[2:4].strip()
        eight_char = line_str[6:14].strip()
        data_ini   = line_str[15:22].strip()
        data_fim   = line_str[22:29].strip()
        freq       = line_str[30:37].strip()
        orig_blk   = line_str[37:52].strip()  # ex "SDU10051005-0300"
        dest_blk   = line_str[52:68].strip()
        equip      = line_str[68:71].strip()
        next_voo   = ""
        if len(line_str)>=124:
            next_voo  = line_str[120:124].strip()

        if len(eight_char)<4:
            return None
        num_voo = eight_char[:4]

        def parse_ap(blk: str):
            if len(blk)>=7:
                apt = blk[:3]
                hhmm= blk[3:7]
                return apt, hhmm
            return "",""

        orig, hp = parse_ap(orig_blk)
        dst , hc = parse_ap(dest_blk)

        return {
          "Cia": cia,
          "NumVoo": num_voo,
          "DataIni": data_ini,
          "DataFim": data_fim,
          "Freq": freq,
          "Origem": orig, "HoraPartida": hp,
          "Destino": dst, "HoraChegada": hc,
          "Equip": equip,
          "NextVoo": next_voo
        }
    except:
        return None

def parse_by_split(line_str: str):
    """Fallback parse."""
    splitted = line_str.strip().split()
    if len(splitted)<4:
        return None
    if splitted[0]!="3":
        return None
    cia = splitted[1]
    chunk2 = splitted[2]
    freq = splitted[3]
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

    def parse_ap(blk):
        if len(blk)>=7:
            return blk[:3], blk[3:7]
        return "",""
    o,hp = parse_ap(orig_blk)
    d,hc = parse_ap(dest_blk)

    return {
      "Cia": cia,
      "NumVoo": num_voo,
      "DataIni": data_ini_str,
      "DataFim": data_fim_str,
      "Freq": freq,
      "Origem": o, "HoraPartida": hp,
      "Destino": d, "HoraChegada": hc,
      "Equip": equip,
      "NextVoo": nxtvoo
    }

def parse_ssim_line(line:str):
    return robust_parse_ssim_line(line)

###############################################################################
# EXPAND DATAS
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
            freq_set.add(int(c)) # 1=seg,...,7=dom

    results=[]
    d= dt_i
    while d<=dt_f:
        dow = d.weekday()+1
        if dow in freq_set:
            newr = dict(row)
            newr["DataOper"] = d.strftime("%d/%m/%Y")  # '01/01/2025'
            results.append(newr)
        d += timedelta(days=1)
    return results

###############################################################################
# DUPLICA EM CHEGADA/PARTIDA
###############################################################################
def fix_time_4digits(tt:str)->str:
    if len(tt)==4:
        return tt[:2]+":"+tt[2:]
    return tt

def build_arrdep_rows(row:dict):
    dataop = row["DataOper"]
    orig   = row.get("Origem","")
    horaP  = fix_time_4digits(row.get("HoraPartida",""))
    dst    = row.get("Destino","")
    horaC  = fix_time_4digits(row.get("HoraChegada",""))
    recs=[]
    # Partida
    if orig and horaP:
        recs.append({
          "Aeroporto": orig,
          "CP":"P",
          "DataOper": dataop,
          "NumVoo": row["NumVoo"],
          "Hora": horaP,
          "Equip": row.get("Equip",""),
          "NextVoo": row.get("NextVoo","")
        })
    # Chegada
    if dst and horaC:
        recs.append({
          "Aeroporto": dst,
          "CP":"C",
          "DataOper": dataop,
          "NumVoo": row["NumVoo"],
          "Hora": horaC,
          "Equip": row.get("Equip",""),
          "NextVoo": row.get("NextVoo","")
        })
    return recs

###############################################################################
# CONECTAR => GERAR UMA LINHA POR CHEGADA + PARTIDA
# RESULTANDO NO CABEÇALHO:
#  Aeroporto, DataOper, HoraChegada, VooChegada, HoraPartida, VooPartida, TempoSolo, EquipCheg, EquipPart
###############################################################################
def to_hhmm(delta_h: float)->str:
    """
    Converte float de horas (ex 30.5 => '30:30'), mesmo se >24
    """
    if delta_h<0:
        return "00:00"
    h = int(delta_h)
    m = int(round((delta_h - h)*60))
    return f"{h}:{m:02d}"

def connect_vision(df):
    """
    Monta a 'visão do aeroporto': cada linha no final = 1 Chegada + (opcional) Partida
    TempoSolo em 'hh:mm'.
    """
    df["dt"] = pd.to_datetime(df["DataOper"]+" "+df["Hora"], format="%d/%m/%Y %H:%M", errors="coerce")

    arr = df[df["CP"]=="C"].copy()
    dep = df[df["CP"]=="P"].copy()

    # Campos extras no arr
    arr["HoraPartida"] = None
    arr["VooPartida"]  = None
    arr["TempoSolo"]   = None
    arr["EquipPart"]   = None

    # agrupar dep p/ lookup => (Aeroporto, NumVoo, DataOper)
    grp_dep = dep.groupby(["Aeroporto","NumVoo","DataOper"])

    for idx, rowC in arr.iterrows():
        nxtv = rowC["NextVoo"]
        if not nxtv:
            continue
        apr  = rowC["Aeroporto"]
        dOp  = rowC["DataOper"]
        dtC  = rowC["dt"]
        key  = (apr,nxtv,dOp)
        if key in grp_dep.groups:
            idxs = grp_dep.groups[key]
            cand = dep.loc[idxs]
            # filtra cand dt>=dtC
            cand2= cand[cand["dt"]>= dtC]
            if len(cand2)>0:
                c2s = cand2.sort_values("dt")
                dp  = c2s.iloc[0]  # a 1a partida
                delta_hrs = (dp["dt"] - dtC).total_seconds()/3600
                arr.at[idx,"TempoSolo"]   = to_hhmm(delta_hrs)
                arr.at[idx,"VooPartida"]  = dp["NumVoo"]
                arr.at[idx,"HoraPartida"] = dp["Hora"]
                arr.at[idx,"EquipPart"]   = dp["Equip"]

    # Renomear col 'Hora'=>'HoraChegada','NumVoo'=>'VooChegada','Equip'=>'EquipCheg'
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
# FLUXO COMPLETO
###############################################################################
def process_ssim(ssim_file):
    lines = ssim_file.read().decode("latin-1").splitlines()

    # 1) parse
    base=[]
    for l in lines:
        rec = robust_parse_ssim_line(l)
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

    # 3) duplicar => arrdep
    arrdep=[]
    for row in expanded:
        arrdep += build_arrdep_rows(row)
    if not arrdep:
        return pd.DataFrame()
    dfAD = pd.DataFrame(arrdep)

    # 4) connect => 'visão do aeroporto'
    dfVision = connect_vision(dfAD)
    return dfVision

###############################################################################
def main():
    st.title("CONVERSOR DE SSIM PARA CSV")

    ssim_file = st.file_uploader("Selecione o arquivo SSIM:", type=["ssim","txt"])
    if ssim_file:
        if st.button("Processar"):
            dfVision = process_ssim(ssim_file)
            if len(dfVision)==0:
                st.error("Nenhum voo processado ou nenhuma chegada conectada.")
                return

            # Exibir Tabela-Resumo (exemplo: consideramos so CP="C" do arrdep? 
            # Mas agora DF final so tem 1 line p/ each 'aeroporto vision'.
            # se quisermos contagem de 'chegadas' propriamente, precisamos dfArr?
            # Faremos contagem do final DF => 'count por Aeroporto'
            st.write("### Quantidade de 'linhas' (visão do aeroporto) por Aeroporto")
            sum_air = dfVision.groupby("Aeroporto")["VooChegada"].count().reset_index(name="Qtde")
            st.dataframe(sum_air)

            st.write("### Resultado Final (Visão do Aeroporto)")
            st.dataframe(dfVision)

            csv_data = dfVision.to_csv(index=False).encode("utf-8")
            st.download_button("Baixar CSV", data=csv_data, file_name="ssim_aeroporto.csv", mime="text/csv")

if __name__=="__main__":
    main()
