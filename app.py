import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os

###############################################################################
# 1) PARSE SSIM (inspirado no "robusto", mas simplificado para evitar bugs)
###############################################################################
def parse_ssim_line(line: str):
    """
    Tenta extrair campos de uma linha do tipo 3.
    Caso o SSIM tenha ~200 chars, podemos fazer substring;
    se isso falhar, cair no split() fallback.

    Ajuste se seu SSIM for bem padronizado (200 chars fixos) ou se for variável.
    """
    line_str = line.strip()
    if not line_str.startswith("3"):
        return None

    # Tentar slice fixo (se >=120 chars, por ex.)
    if len(line_str) >= 120:
        return parse_by_substring(line_str)
    else:
        # fallback
        return parse_by_split(line_str)

def parse_by_substring(line_str: str):
    """
    Se tivermos ~200 chars, extrairmos posições fixas.
    Ajuste se seu layout for outro.
    """
    # Exemplo de índices (bem genérico). Ajustar ao seu SSIM real:
    try:
        cia        = line_str[2:4].strip()
        eight_char = line_str[6:14].strip()   # 8 chars => "10020101"
        data_ini   = line_str[15:22].strip()  # "01JAN25"
        data_fim   = line_str[22:29].strip()  # "15JAN25"
        freq       = line_str[30:37].strip()  # "1234567"
        orig_blk   = line_str[37:52].strip()  # "CGH09050905-0300" p.ex.
        dest_blk   = line_str[52:68].strip()  # "SDU10101010-0300"
        equip      = line_str[68:71].strip()
        next_voo   = line_str[120:124].strip()  # p.ex. "2136"

        num_voo = eight_char[:4]

        def parse_ap(block):
            if len(block)>=7:
                apt = block[:3]
                hora= block[3:7]
                return apt,hora
            else:
                return "",""
        orig,hp = parse_ap(orig_blk)
        dest,hc = parse_ap(dest_blk)

        # Monta dict
        return {
          "Cia": cia,
          "NumVoo": num_voo,
          "DataIni": data_ini,
          "DataFim": data_fim,
          "Freq": freq,
          "Origem": orig,
          "HoraPartida": hp,
          "Destino": dest,
          "HoraChegada": hc,
          "Equip": equip,
          "NextVoo": next_voo
        }
    except:
        return None

def parse_by_split(line_str: str):
    """
    fallback: split por espaços e extrair algo parecido.
    Ajuste se seu SSIM é bem 'frouxo' nos espaços.
    """
    splitted = line_str.split()
    if len(splitted)<4:
        return None
    # splitted[1] => cia
    cia = splitted[1]
    chunk2 = splitted[2]
    freq_str = splitted[3]
    # se chunk2 < 23 => sem data
    if len(chunk2)<23:
        return None
    eight_char   = chunk2[:8]
    data_ini_str = chunk2[9:16]
    data_fim_str = chunk2[16:23]

    num_voo = eight_char[:4]
    # supor splitted[4] => "CGH0905..."
    orig_blk = splitted[4] if len(splitted)>4 else ""
    dest_blk = splitted[5] if len(splitted)>5 else ""
    equip    = splitted[6] if len(splitted)>6 else ""
    nxtv     = splitted[9] if len(splitted)>9 else ""

    def parse_ap(bk):
        if len(bk)>=7:
            return bk[:3], bk[3:7]
        return "",""
    orig,hp = parse_ap(orig_blk)
    dst, hc = parse_ap(dest_blk)

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
      "NextVoo": nxtv
    }

###############################################################################
# 2) EXPANDIR DATAS
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
    d = dt_i
    while d<=dt_f:
        dow = d.weekday()+1 # 1=mon,...7=sun
        if dow in freq_set:
            newr = dict(row)
            newr["DataOper"] = d.strftime("%d/%m/%Y")
            results.append(newr)
        d+=timedelta(days=1)
    return results

def fix_time_4digits(t:str)->str:
    if len(t)==4:
        return t[:2]+":"+t[2:]
    return t

###############################################################################
# 3) DUPLICAR (CHEGADA/PARTIDA)
###############################################################################
def build_arrdep_rows(row:dict):
    dataop = row.get("DataOper","")
    orig = row.get("Origem","")
    horaP= fix_time_4digits(row.get("HoraPartida",""))
    dst  = row.get("Destino","")
    horaC= fix_time_4digits(row.get("HoraChegada",""))

    recs=[]
    # Partida
    if orig and horaP:
        recs.append({
          "Aeroporto": orig,
          "CP":"P",
          "DataOper": dataop,
          "Cia": row.get("Cia",""),
          "NumVoo": row.get("NumVoo",""),
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
          "Cia": row.get("Cia",""),
          "NumVoo": row.get("NumVoo",""),
          "Hora": horaC,
          "Equip": row.get("Equip",""),
          "NextVoo": row.get("NextVoo","")
        })
    return recs

###############################################################################
# 4) CONECTAR: Precisamos de CP="C" e NextVoo => CP="P" do mesmo NextVoo
###############################################################################
def connect_rows(df):
    """
    Retornamos APENAS as chegadas (CP="C") com colunas extras de VooPartida, HoraSaida, TempoSolo...
    Se não achar a Partida do NextVoo => fica sem tempoSolo.
    """
    # Precisamos do dt
    df["dt"] = pd.to_datetime(df["DataOper"]+" "+df["Hora"], format="%d/%m/%Y %H:%M", errors="coerce")

    # separar arrivals e departures
    arr = df[df["CP"]=="C"].copy()
    dep = df[df["CP"]=="P"].copy()

    arr["TempoSolo"] = None
    arr["VooPartida"] = None
    arr["HoraSaida"] = None

    # agrupar dep p/ lookup
    # Precisamos do (Aeroporto, NumVoo, DataOper). 
    # E iremos buscar dep dt >= arr dt
    # Se houver >1 cand, pegamos a 1a
    dep_gb = dep.groupby(["Aeroporto","NumVoo","DataOper"])

    for idx, ar in arr.iterrows():
        nxt = ar["NextVoo"]
        apr= ar["Aeroporto"]
        dO = ar["DataOper"]
        dtA= ar["dt"]
        if not nxt: 
            continue

        # achar group (apr,nxt,dO)
        if (apr,nxt,dO) in dep_gb.groups:
            group_idx = dep_gb.groups[(apr,nxt,dO)]
            cand = dep.loc[group_idx]
            # filtra cand dt >= dtA
            cand2 = cand[cand["dt"]>= dtA]
            if len(cand2)>0:
                cand2_sorted = cand2.sort_values("dt")
                dp = cand2_sorted.iloc[0]
                delta_h = (dp["dt"] - dtA).total_seconds()/3600
                arr.at[idx,"TempoSolo"] = round(delta_h,2)
                arr.at[idx,"VooPartida"] = dp["NumVoo"]
                arr.at[idx,"HoraSaida"] = dp["Hora"]

    return arr

def process_ssim(ssim_file):
    lines = ssim_file.read().decode("latin-1").splitlines()
    base=[]
    for l in lines:
        pr = parse_ssim_line(l)
        if pr:
            base.append(pr)

    # expand
    expanded=[]
    for br in base:
        exps = expand_dates(br)
        expanded.extend(exps)

    # duplicar c/p
    arrdep=[]
    for r in expanded:
        arrdep += build_arrdep_rows(r)

    df = pd.DataFrame(arrdep)
    if len(df)==0:
        return None

    # connect
    dfC = connect_rows(df)
    return dfC

###############################################################################
def main():
    st.title("Conversor SSIM - Exibe apenas chegadas e faz resumo")
    ssim_file = st.file_uploader("Selecione SSIM:", type=["ssim","txt"])
    if ssim_file:
        if st.button("Processar"):
            dfC = process_ssim(ssim_file)
            if dfC is None or len(dfC)==0:
                st.error("Nenhuma chegada obtida ou arquivo não gerou dados.")
                return
            # Tabela final => dfC
            # Podemos agrupar por mes
            dfC["Month"] = pd.to_datetime(dfC["DataOper"], format="%d/%m/%Y", errors="coerce").dt.to_period("M").astype(str)

            # Mostramos um mini-sum: group by Month, count lines
            st.write("### Contagem de chegadas por mês")
            sum_by_month = dfC.groupby("Month")["NumVoo"].count().reset_index(name="Qtde")
            st.dataframe(sum_by_month)

            # Exibir dfC
            st.write("### Chegadas (Conectadas), por Mês:")
            grouped = dfC.groupby("Month")
            for mon, g in grouped:
                st.write(f"**Mês: {mon}**")
                st.dataframe(g[["Aeroporto","DataOper","Hora","NumVoo","VooPartida","HoraSaida","TempoSolo"]])

            # Download
            csv_str = dfC.to_csv(index=False)
            st.download_button("Baixar CSV Chegadas", data=csv_str.encode("utf-8"), file_name="ssim_chegadas.csv", mime="text/csv")

if __name__=="__main__":
    main()
