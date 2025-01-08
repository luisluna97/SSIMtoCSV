import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

################################################################################
# PARSE INSPIRED BY "leg_record.py" from Schiphol-Hub/ssim (positions-based).
# If line isn't ~200 chars, fallback to a simpler 'split()' approach.
################################################################################

def parse_record_type_3(line: str):
    """
    Posição aproximada (ajuste se seu SSIM tiver outra conformidade):
      - line[0]   => '3'
      - line[2:5] => Airline IATA (3 chars, às vezes 2 + 1 space)
      - line[6:10]=> flight number
      - line[10]  => operational suffix? (pode ser espaço)
      - line[11]  => Variation
      - line[12:19] => dataIni (7 chars, ex "01JAN25")
      - line[19:26] => dataFim (7 chars)
      - line[26:33] => Freq (7 chars) ex "1234567"
      - line[33:48] => Origem + hora + timezone (15 chars) ex "CGH09050905-0300"
      - line[48:63] => Destino + hora + timezone (15 chars)
      - line[63:66] => Equip
      ...
      - line[110:114]? => NextVoo
    Este é um EXEMPLO; mapeie de fato seu SSIM real.
    """

    # Se não tem 80+ chars, pode falhar
    if len(line) < 80:
        return None

    try:
        if line[0] != '3':
            return None

        airline = line[2:5].strip()
        flight_num = line[6:10].strip()  # 4 chars
        # skip operational suffix line[10]
        # skip variation line[11]
        data_ini = line[12:19].strip()  # "01JAN25"
        data_fim = line[19:26].strip()  # "08JAN25"
        freq     = line[26:33].strip()  # "1234567"
        orig_blk = line[33:48].strip()  # "CGH09050905-0300"
        dest_blk = line[48:63].strip()  # "SDU10101010-0300"
        equip    = line[63:66].strip()  # ex "73X"

        # next voo? ex line[110:114], mas se seu real SSIM for outro, ajuste
        next_voo = ""
        if len(line)>=114:
            next_voo = line[110:114].strip()

        def parse_apt(block):
            if len(block)>=7:
                apt  = block[:3]
                hhmm = block[3:7]
                return apt, hhmm
            return "", ""

        orig,hp = parse_apt(orig_blk)
        dst ,hc = parse_apt(dest_blk)

        # flight_num => ex "1002"
        return {
            "Cia": airline,
            "NumVoo": flight_num,
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

def parse_simplified_split(line: str):
    """
    Fallback if line not ~200 chars or substring fails.
    Similar to your "old code that worked well" with splitted[2], splitted[3], etc.
    """
    splitted = line.strip().split()
    if len(splitted)<4:
        return None
    if splitted[0]!="3":
        return None

    cia = splitted[1]
    chunk2 = splitted[2]  # ex "10020101J01JAN2508JAN25"
    freq_str= splitted[3]

    if len(chunk2)<23:
        return None

    eight_char   = chunk2[:8]   # "10020101"
    data_ini_str = chunk2[9:16] # "01JAN25"
    data_fim_str = chunk2[16:23]# "08JAN25"
    num_voo      = eight_char[:4]

    orig_blk = splitted[4] if len(splitted)>4 else ""
    dest_blk = splitted[5] if len(splitted)>5 else ""
    equip    = splitted[6] if len(splitted)>7 else ""
    nxtv     = splitted[9] if len(splitted)>9 else ""

    def parse_ap(bk:str):
        if len(bk)>=7:
            return bk[:3], bk[3:7]
        return "",""

    o,hp = parse_ap(orig_blk)
    d,hc = parse_ap(dest_blk)

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
      "NextVoo": nxtv
    }

def parse_ssim_line(line:str):
    """
    Função principal de parse do tipo 3:
     - Tenta parse tipo 3 com substring fixo (inspirado no "leg_record.py" approach).
     - Se falhar, fallback p/ 'parse_simplified_split'.
    """
    rec = parse_record_type_3(line)
    if rec:
        return rec
    else:
        return parse_simplified_split(line)

###############################################################################
# EXPAND DATAS
###############################################################################
def expand_dates(row: dict):
    di = row.get("DataIni","")
    df = row.get("DataFim","")
    freq= row.get("Freq","")
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
            freq_set.add(int(c)) # 1=Seg,...7=Dom

    out=[]
    d = dt_i
    while d<=dt_f:
        dow = d.weekday()+1
        if dow in freq_set:
            newr = dict(row)
            newr["DataOper"] = d.strftime("%d/%m/%Y")
            out.append(newr)
        d+= timedelta(days=1)
    return out

def fix_time_4digits(tt:str)->str:
    if len(tt)==4:
        return tt[:2]+":"+tt[2:]
    return tt

###############################################################################
# DUPLICAR EM CHEG/PART
###############################################################################
def build_arrdep_rows(r: dict):
    dataop = r.get("DataOper","")
    orig = r.get("Origem","")
    hp   = fix_time_4digits(r.get("HoraPartida",""))
    dst  = r.get("Destino","")
    hc   = fix_time_4digits(r.get("HoraChegada",""))

    recs=[]
    # Partida
    if orig and hp:
        recs.append({
          "Aeroporto": orig,
          "CP":"P",
          "DataOper": dataop,
          "NumVoo": r["NumVoo"],
          "Hora": hp,
          "Equip": r.get("Equip",""),
          "NextVoo": r.get("NextVoo","")
        })
    # Chegada
    if dst and hc:
        recs.append({
          "Aeroporto": dst,
          "CP":"C",
          "DataOper": dataop,
          "NumVoo": r["NumVoo"],
          "Hora": hc,
          "Equip": r.get("Equip",""),
          "NextVoo": r.get("NextVoo","")
        })
    return recs

###############################################################################
# CONECTAR => "VISÃO DO AEROPORTO"
###############################################################################
def to_hhmm(delta_hrs: float)->str:
    if delta_hrs<0:
        return "00:00"
    hh = int(delta_hrs)
    mm = int(round((delta_hrs - hh)*60))
    return f"{hh}:{mm:02d}"

def connect_rows(df):
    """
    Filtra CP="C" => arr, CP="P" => dep
    p/ cada arr se NextVoo => achar dep no mesmo (Aeroporto, DataOper),
    dtdep >= dtarr => 1a => TempoSolo em hh:mm
    renomeia col p/ final:
      "Aeroporto","DataOper","HoraChegada","VooChegada",
      "HoraPartida","VooPartida","TempoSolo","EquipCheg","EquipPart"
    """
    df["dt"] = pd.to_datetime(df["DataOper"]+" "+df["Hora"], format="%d/%m/%Y %H:%M", errors="coerce")
    arr = df[df["CP"]=="C"].copy()
    dep = df[df["CP"]=="P"].copy()

    arr["HoraPartida"] = None
    arr["VooPartida"]  = None
    arr["EquipPart"]   = None
    arr["TempoSolo"]   = None

    dep_grp = dep.groupby(["Aeroporto","NumVoo","DataOper"])

    for idx, rowC in arr.iterrows():
        nxtv = rowC["NextVoo"]
        if not nxtv:
            continue
        apr = rowC["Aeroporto"]
        dop = rowC["DataOper"]
        dtC = rowC["dt"]
        key = (apr,nxtv,dop)
        if key in dep_grp.groups:
            idxs = dep_grp.groups[key]
            cand = dep.loc[idxs]
            cand2= cand[cand["dt"]>= dtC]
            if len(cand2)>0:
                c2s = cand2.sort_values("dt")
                dp  = c2s.iloc[0]
                dH  = (dp["dt"] - dtC).total_seconds()/3600
                arr.at[idx,"TempoSolo"]   = to_hhmm(dH)
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
# FLUXO COMPLETO
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
    for b in base:
        exps = expand_dates(b)
        expanded.extend(exps)
    if not expanded:
        return None

    # duplicar c/p
    arrdep=[]
    for e in expanded:
        arrdep += build_arrdep_rows(e)
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
    st.title("CONVERSOR DE SSIM PARA CSV")

    ssim_file = st.file_uploader("Selecione o arquivo SSIM:", type=["ssim","txt"])
    if ssim_file:
        if st.button("Processar"):
            dfC = process_ssim(ssim_file)
            if dfC is None or len(dfC)==0:
                st.error("Nenhum voo processado ou nenhuma chegada conectada.")
                return

            # Tabela-resumo no site: contagem de linhas final p/ cada aeroporto
            st.write("### Resumo: Visão final (Chegada) por Aeroporto")
            sum_air = dfC.groupby("Aeroporto")["VooChegada"].count().reset_index(name="Qtde")
            st.dataframe(sum_air)

            st.write("### Tabela final - Visão do Aeroporto")
            st.dataframe(dfC)

            csv_data = dfC.to_csv(index=False).encode("utf-8")
            st.download_button("Baixar CSV", csv_data, file_name="ssim_visao.csv", mime="text/csv")

if __name__=="__main__":
    main()
