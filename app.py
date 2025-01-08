import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os

###############################################################################
# INSPIRATION NOTE:
# Parte desta lógica de parse e expansão foi inspirada no repositório:
#   https://github.com/Schiphol-Hub/ssim
# que oferece classes e métodos para ler o SSIM com mais robustez.
# Aqui seguimos abordagem procedural mas levando em conta ideias e fixes do repo.
###############################################################################

def robust_parse_ssim_line(line: str):
    """
    Uma função 'robusta' inspirada no repo Schiphol-Hub/ssim para parsear
    uma linha do tipo 3, tentando evitar erros como 'AEP05000500-0300' cair em Equip.

    PRINCÍPIO GERAL:
    - Cada registro tipo 3 deve ter 200 caracteres no SSIM 'puro'.
    - Mas às vezes no seu arquivo pode vir com espaços diferentes.
    - Para minimizar erro, vamos extrair subcampos fixos por posição (como no SSIM oficial).

    Se o seu SSIM varia, ajuste os índices a seu critério. Abaixo, um layout EXEMPLO:
    0..1     -> "3 "
    2..4     -> cia iata (ex "G3")
    6..14    -> 8-char field
    14       -> status
    15..22   -> data inicial
    22..29   -> data final
    30..36   -> frequencia
    36..52   -> origem + hora + timezone
    52..68   -> destino + hora + timezone
    68..71   -> equip
    ...
    120..124 -> next voo (ex "2136")
    ...
    Entretanto, nem todo arquivo segue 100% as posições fixas.

    => Se seu arquivo "real" não for 200 chars, podemos cair no fallback de "split()".

    Abaixo, tentamos primeiro substring fixo, se falhar, usamos split.
    """

    line_padded = line.rstrip("\n")
    if len(line_padded) < 50:
        return None
    # Tentar checar se começa com '3'
    if not line_padded.strip().startswith('3'):
        return None

    # Se for >=200 chars, tentamos extrair pos fixas:
    if len(line_padded) >= 120:  # meio heurístico
        # Exemplo de extração por slice (ajuste as faixas!)
        # cia iata -> line[2:4]
        cia = line_padded[2:4].strip()

        eight_char = line_padded[6:14].strip()    # 8 chars
        data_ini   = line_padded[15:22].strip()   # 7 chars '01JAN25'
        data_fim   = line_padded[22:29].strip()   # 7 chars
        freq       = line_padded[30:37].strip()   # freq
        origem_blk = line_padded[37:52].strip()   # ex "CGH09050905-0300"
        destino_blk= line_padded[52:68].strip()   # ex "SDU10101010-0300"
        equip      = line_padded[68:71].strip()
        next_voo   = line_padded[120:124].strip()  # ex "2136"

        # ex. "10020101" => 0..4=1002, etc.
        if len(eight_char)<8:
            return None
        num_voo     = eight_char[0:4]
        # dateCount  = eight_char[4:6]
        # etapa      = eight_char[6:8]

        def parse_origem_destino(blk:str):
            if len(blk)>=7:
                apt = blk[:3]
                hora= blk[3:7]
                return apt, hora
            return "", ""

        orig, hora_p = parse_origem_destino(origem_blk)
        dest, hora_c = parse_origem_destino(destino_blk)

        return {
          "Cia": cia,
          "NumVoo": num_voo,
          "DataIni": data_ini,
          "DataFim": data_fim,
          "Freq": freq,
          "Origem": orig,
          "HoraPartida": hora_p,
          "Destino": dest,
          "HoraChegada": hora_c,
          "Equip": equip,
          "NextVoo": next_voo
        }
    else:
        # fallback: "split approach"
        splitted = line_padded.strip().split()
        if len(splitted)<4:
            return None
        if splitted[0]!="3":
            return None
        # splitted[2], splitted[3] => data e freq etc
        # etc. (similar ao parse anterior)
        # Para simplificar, iremos usar a parse_simplificada:
        return parse_simplificada_split(splitted)

def parse_simplificada_split(splitted):
    """
    Fallback parse se a linha não tiver 200 chars fixos.
    Ajuste conforme seu layout real.
    """
    cia = splitted[1]
    chunk2 = splitted[2]
    freq_str = splitted[3]
    # ...
    # Exemplo igual do code anterior
    if len(chunk2)<23:
        return None
    # ...
    eight_char   = chunk2[0:8]
    data_ini_str = chunk2[9:16]
    data_fim_str = chunk2[16:23]
    voo_num      = eight_char[0:4]

    return {
      "Cia": cia,
      "NumVoo": voo_num,
      "DataIni": data_ini_str,
      "DataFim": data_fim_str,
      "Freq": freq_str,
      # e etc, leftover
      "Origem": "",
      "HoraPartida": "",
      "Destino": "",
      "HoraChegada": "",
      "Equip": "",
      "NextVoo": ""
    }

def expand_dates(row:dict):
    di = row.get("DataIni","")
    df = row.get("DataFim","")
    fs = row.get("Freq","")
    if not di or not df:
        return []

    # freq => ex "2345" => 2=ter,3=qua,4=qui,5=sex
    try:
        dt_ini = datetime.strptime(di, "%d%b%y")
        dt_fim = datetime.strptime(df, "%d%b%y")
    except:
        return []

    freq_set = set()
    for c in fs:
        if c.isdigit():
            freq_set.add(int(c))  # 1=seg,...,7=dom

    expanded=[]
    d = dt_ini
    while d <= dt_fim:
        # python: weekday(): 0=mon ...6=sun => +1 => 1=mon,...7=sun
        dow = d.weekday()+1
        if dow in freq_set:
            newrow = dict(row)
            # format "dd/mm/yyyy"
            newrow["DataOper"] = d.strftime("%d/%m/%Y")
            expanded.append(newrow)
        d+=timedelta(days=1)
    return expanded

def fix_time_4digits(hhmm:str)-> str:
    """Transform '0905' -> '09:05' etc."""
    if len(hhmm)==4:
        return hhmm[:2]+":"+hhmm[2:]
    return hhmm

def build_arrdep_rows(row:dict):
    """
    Gera 2 linhas: Chegada e Partida. Assim podemos filtrar apenas Chegada,
    ou só Partida, ou conectar, etc.
    """
    result=[]
    # data => row["DataOper"]
    data_str = row.get("DataOper","")
    # format hora
    hp = fix_time_4digits(row.get("HoraPartida",""))
    hc = fix_time_4digits(row.get("HoraChegada",""))

    # Partida
    if row.get("Origem","")!="" and hp!="":
        recP = {
          "Aeroporto": row["Origem"],
          "CP": "P",
          "DataOper": data_str,
          "Cia": row.get("Cia",""),
          "NumVoo": row.get("NumVoo",""),
          "Hora": hp,
          "Equip": row.get("Equip",""),
          "NextVoo": row.get("NextVoo","") # se define nextvoo no origem?
        }
        result.append(recP)

    # Chegada
    if row.get("Destino","")!="" and hc!="":
        recC = {
          "Aeroporto": row["Destino"],
          "CP": "C",
          "DataOper": data_str,
          "Cia": row.get("Cia",""),
          "NumVoo": row.get("NumVoo",""),
          "Hora": hc,
          "Equip": row.get("Equip",""),
          "NextVoo": row.get("NextVoo","")
        }
        result.append(recC)

    return result

def connect_rows(df):
    """
    Filtra só chegadas, exibe por MÊS e Mostra APENAS Chegadas (pedido: "mostrar apenas chegadas")
    mas iremos também conectar NextVoo => a partida do NextVoo para gerar tempo de solo?

    - We'll do the logic: We'll keep only CP="C" rows, group by month,
      but also do a join with the "partida" row of NextVoo no mesmo Aeroporto + DataOper.

    Observação: se o user só quer "mostrar apenas chegadas" na tabela final,
    podemos ainda calcular tempo de solo e anotar "Voopart" / "Horapart" etc.
    """
    # criar col month
    df["dt"] = pd.to_datetime(df["DataOper"] + " " + df["Hora"], format="%d/%m/%Y %H:%M", errors="coerce")
    df["Month"] = df["dt"].dt.to_period("M")  # ex. 2025-01

    # Filtramos df so com CP="C"
    dfC = df[df["CP"]=="C"].copy()

    # Precisamos, se quisermos tempo solo, achar a row CP="P" do NextVoo
    # Lógica: se dfC[i].NextVoo=xxx, procuramos em df com CP="P", NumVoo=xxx, mesmo Aeroporto, e dt >= dtChegada
    # e pegamos a 1a. -> tempoSolo
    dfC["TempoSolo"] = None
    dfC["VooSaida"] = None
    dfC["HoraSaida"] = None

    # separa dfPart
    dfPart = df[df["CP"]=="P"].copy()

    for idx, rowC in dfC.iterrows():
        nxtv = rowC["NextVoo"]
        if not nxtv:
            continue
        apr = rowC["Aeroporto"]
        dtC = rowC["dt"]
        cand = dfPart[(dfPart["Aeroporto"]==apr)&(dfPart["NumVoo"]==nxtv)&(dfPart["dt"]>=dtC)]
        if len(cand)>0:
            rP = cand.sort_values("dt").iloc[0]
            # tempo de solo
            delta_h = (rP["dt"] - dtC).total_seconds()/3600
            dfC.at[idx,"TempoSolo"] = round(delta_h,2)
            dfC.at[idx,"VooSaida"] = rP["NumVoo"]
            dfC.at[idx,"HoraSaida"] = rP["Hora"]

    return dfC

@st.cache_data
def load_support_files():
    # se quiser algo do iata_airlines.csv, etc.
    return None, None

def gerar_csv(ssim_file):
    lines = ssim_file.read().decode("latin-1").splitlines()

    # parse robusto
    base_rows=[]
    for l in lines:
        rr = robust_parse_ssim_line(l)
        if rr:
            base_rows.append(rr)

    # expand data
    expanded=[]
    for row in base_rows:
        e2 = expand_dates(row)
        expanded.extend(e2)

    # duplicar
    arrdep=[]
    for r2 in expanded:
        arrdep += build_arrdep_rows(r2)

    dfAD = pd.DataFrame(arrdep)
    if len(dfAD)==0:
        return None

    # conectar => filtrar so chegadas => mostrar por mes
    dfC = connect_rows(dfAD)
    if len(dfC)==0:
        return None
    return dfC

def main():
    st.title("Conversor SSIM - Ground Handling")
    st.write("Esta aplicação transforma um SSIM file em um CSV com uma ótica do aeroporto")

    ssim_file = st.file_uploader("Selecione SSIM:", type=["ssim","txt"])
    if ssim_file:
        if st.button("Processar"):
            dfC = gerar_csv(ssim_file)
            if dfC is None or len(dfC)==0:
                st.error("Nenhuma chegada obtida.")
                return
            # exibir
            # agrupar por mes => st.write por mes
            dfC["Month"] = dfC["dt"].dt.to_period("M").astype(str)
            grouped = dfC.groupby("Month")
            for mon, g in grouped:
                st.write(f"#### Mês: {mon}")
                st.dataframe(g[["Aeroporto","DataOper","Hora","NumVoo","VooSaida","HoraSaida","TempoSolo"]])

            # baixar CSV
            csv_data = dfC.to_csv(index=False).encode("utf-8")
            st.download_button("Baixar CSV Chegadas", csv_data, file_name="ssim_chegadas.csv", mime="text/csv")

if __name__=="__main__":
    main()
