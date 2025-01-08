import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

def robust_parse_ssim_line(line: str):
    """
    Faz parse robusto de uma linha do tipo 3.
    - Se linha >= 120..200 chars, tenta substring fixo (inspirado no repo Schiphol-Hub/ssim).
    - Se isso falhar, fallback em 'split()'.
    """
    line_str = line.rstrip("\n")
    if not line_str.strip().startswith("3"):
        return None

    if len(line_str) >= 120:
        # Tentar substring fixo (ajuste conforme seu SSIM real):
        return parse_by_substring(line_str)
    else:
        # fallback
        return parse_by_split(line_str)

def parse_by_substring(line_str: str):
    """
    Exemplo de posições (inspirado no SSIM):
      [2:4]   => cia
      [6:14]  => 8-char field
      [15:22] => dataIni
      [22:29] => dataFim
      [30:37] => freq
      [37:52] => origem + hora
      [52:68] => destino + hora
      [68:71] => equip
      [120:124] => nextVoo
    Ajuste se seu arquivo SSIM tiver outro layout.
    """
    try:
        cia        = line_str[2:4].strip()
        eight_char = line_str[6:14].strip()
        data_ini   = line_str[15:22].strip()
        data_fim   = line_str[22:29].strip()
        freq       = line_str[30:37].strip()
        orig_blk   = line_str[37:52].strip()
        dest_blk   = line_str[52:68].strip()
        equip      = line_str[68:71].strip()
        # se tiver 200 chars, nextvoo ficaria ~ [120:124]
        # mas se menor, tentamos ~ [120:124]...
        next_voo   = ""
        if len(line_str)>=124:
            next_voo   = line_str[120:124].strip()

        if len(eight_char)<4:
            return None
        num_voo = eight_char[:4]

        def parse_ap(blk: str):
            if len(blk)>=7:
                apt = blk[:3]
                hhmm= blk[3:7]
                return apt, hhmm
            return "",""

        orig,hp = parse_ap(orig_blk)
        dst, hc = parse_ap(dest_blk)

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

def parse_by_split(line_str: str):
    """
    Fallback parse se não tiver ~200 chars ou substring fixo falhar.
    """
    splitted = line_str.strip().split()
    if len(splitted)<4: 
        return None
    if splitted[0] != "3":
        return None

    cia = splitted[1]
    chunk2 = splitted[2]
    freq_str = splitted[3]
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
      "Freq": freq_str,
      "Origem": o,
      "HoraPartida": hp,
      "Destino": d,
      "HoraChegada": hc,
      "Equip": equip,
      "NextVoo": nxtvoo
    }

def parse_ssim_line(line:str):
    return robust_parse_ssim_line(line)

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
            freq_set.add(int(c))  # 1=seg,...,7=dom
    results=[]
    d = dt_i
    while d<= dt_f:
        dow = d.weekday()+1
        if dow in freq_set:
            newr = dict(row)
            newr["DataOper"] = d.strftime("%d/%m/%Y")
            results.append(newr)
        d+=timedelta(days=1)
    return results

def fix_time_4digits(hhmm:str)->str:
    if len(hhmm)==4:
        return hhmm[:2]+":"+hhmm[2:]
    return hhmm

def build_arrdep_rows(row:dict):
    dataop = row.get("DataOper","")
    orig = row.get("Origem","")
    hp   = fix_time_4digits(row.get("HoraPartida",""))
    dst  = row.get("Destino","")
    hc   = fix_time_4digits(row.get("HoraChegada",""))

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
    return recs

def to_hhmm(delta_hours: float)->str:
    """
    Converte float de horas (ex 30.5 => 30h 30m) em 'hh:mm', mesmo se >24.
    ex 30.5 => '30:30'
    """
    if delta_hours<0:
        return "00:00"
    h = int(delta_hours)               # parte inteira
    m = int(round((delta_hours - h)*60))
    return f"{h:02d}:{m:02d}"

def connect_rows(df):
    """
    Mantemos APENAS as chegadas (CP='C').
    Calculamos tempo de solo => se Chegada tem NextVoo => achar Partida(NextVoo)
    no mesmo Aeroporto, dt >= dtChegada, e pegar a 1a p/ TempoSolo
    => tempoSolo em 'hh:mm'
    E renomeamos colunas => HoraChegada, VooChegada, HoraPartida, VooPartida, TempoSolo, EquipCheg, EquipPart
    """
    df["dt"] = pd.to_datetime(df["DataOper"]+" "+df["Hora"], format="%d/%m/%Y %H:%M", errors="coerce")

    arr = df[df["CP"]=="C"].copy()
    dep = df[df["CP"]=="P"].copy()

    # adicionamos col extra
    arr["TempoSolo"]   = None
    arr["VooPartida"]  = None
    arr["HoraPartida"] = None
    arr["EquipPart"]   = None

    dep_grp = dep.groupby(["Aeroporto","NumVoo","DataOper"])

    for idx, rowC in arr.iterrows():
        nxtv = rowC["NextVoo"]
        if not nxtv:
            continue
        apr = rowC["Aeroporto"]
        dOp = rowC["DataOper"]
        dtA= rowC["dt"]
        key = (apr,nxtv,dOp)
        if key in dep_grp.groups:
            idxs = dep_grp.groups[key]
            cand = dep.loc[idxs]
            cand2= cand[cand["dt"]>=dtA]
            if len(cand2)>0:
                cand2s = cand2.sort_values("dt")
                dp = cand2s.iloc[0]
                delta_hrs = (dp["dt"]- dtA).total_seconds()/3600
                arr.at[idx,"TempoSolo"]   = to_hhmm(delta_hrs)
                arr.at[idx,"VooPartida"]  = dp["NumVoo"]
                arr.at[idx,"HoraPartida"] = dp["Hora"]
                arr.at[idx,"EquipPart"]   = dp["Equip"]

    # renomear col 'Hora' => 'HoraChegada', 'NumVoo' => 'VooChegada', 'Equip' => 'EquipCheg'
    arr.rename(columns={
      "Hora": "HoraChegada",
      "NumVoo":"VooChegada",
      "Equip":"EquipCheg"
    }, inplace=True)

    # reorganizar
    final_cols = [
      "Aeroporto","DataOper","HoraChegada","VooChegada",
      "HoraPartida","VooPartida","TempoSolo","EquipCheg","EquipPart"
    ]
    return arr[final_cols]

def process_ssim(ssim_file):
    lines = ssim_file.read().decode("latin-1").splitlines()
    base=[]
    for l in lines:
        rec = parse_ssim_line(l)
        if rec:
            base.append(rec)

    # expand
    expanded=[]
    for b in base:
        e2 = expand_dates(b)
        expanded.extend(e2)

    # arrdep
    arrdep=[]
    for e in expanded:
        arrdep += build_arrdep_rows(e)

    dfAD = pd.DataFrame(arrdep)
    if len(dfAD)==0:
        return None

    dfC = connect_rows(dfAD)
    if len(dfC)==0:
        return None

    return dfC

def main():
    st.title("CONVERSOR DE SSIM PARA CSV")

    ssim_file = st.file_uploader("Selecione o arquivo SSIM:", type=["ssim","txt"])
    if ssim_file:
        if st.button("Processar"):
            dfC = process_ssim(ssim_file)
            if dfC is None or len(dfC)==0:
                st.error("Nenhuma chegada obtida ou nada gerado.")
                return

            # exibir dfC
            st.dataframe(dfC)

            # download
            csv_str = dfC.to_csv(index=False)
            st.download_button("Baixar CSV", data=csv_str.encode("utf-8"), file_name="ssim_chegadas.csv", mime="text/csv")

if __name__=="__main__":
    main()
