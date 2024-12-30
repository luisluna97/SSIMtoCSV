import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os

def parse_ssim_line(line: str):
    line_stripped = line.lstrip()
    splitted = line_stripped.split()
    if len(splitted) < 4:
        return None  # Linha muito curta
    if splitted[0] != "3":
        return None  # Não é linha do tipo 3

    # splitted[1] => cod_cliente
    # splitted[2] => '10000101J01DEC2308DEC23'
    # splitted[3] => frequência (ex. '5')
    # splitted[4] => origem + hora
    # splitted[5] => destino + hora
    # splitted[6] => equip
    # splitted[9] => possível voo de casamento (ou chunk sem o 'Z' etc.)

    cod_cliente   = splitted[1]
    chunk2        = splitted[2] if len(splitted) > 2 else ""
    freq_str      = splitted[3] if len(splitted) > 3 else ""
    origem_info   = splitted[4] if len(splitted) > 4 else ""
    destino_info  = splitted[5] if len(splitted) > 5 else ""
    equip         = splitted[6] if len(splitted) > 6 else ""
    casamento     = splitted[9] if len(splitted) > 9 else ""

    # Se tiver 'Z' solto depois do número do voo, ou se splitted[9] == 'Z', ignoramos
    # Ex.: "... G3 1251 Z ..."
    if casamento == "Z":  
        return None  # ignora essa linha

    # chunk2 => ex.: '10000101J01DEC2308DEC23'
    if len(chunk2) < 23:
        return None

    eight_char   = chunk2[0:8]   # ex. '10000101'
    data_inicial = chunk2[9:16]  # ex. '01DEC23'
    data_final   = chunk2[16:23] # ex. '08DEC23'
    voo          = eight_char[0:4]

    # origem e partida
    if len(origem_info) >= 7:
        origem       = origem_info[:3]
        hora_partida = origem_info[3:7]
    else:
        return None  # sem origem/hora, linha incompleta => ignorar

    # destino e chegada
    if len(destino_info) >= 7:
        destino      = destino_info[:3]
        hora_chegada = destino_info[3:7]
    else:
        return None  # sem destino/hora => ignorar

    return {
        "CodCliente":   cod_cliente,
        "Voo":          voo,
        "DataInicial":  data_inicial,
        "DataFinal":    data_final,
        "Frequencia":   freq_str,
        "Origem":       origem,
        "HoraPartida":  hora_partida,
        "Destino":      destino,
        "HoraChegada":  hora_chegada,
        "Equip":        equip,
        "Casamento":    casamento
    }

def expand_with_frequency(row: dict):
    """
    Expandir datas: DataInicial -> DataFinal, 
    filtrando pelos dias da semana contidos em 'Frequencia' (1=seg,...,7=dom).
    Formatar data em dd/mm/yyyy e hora em HH:MM.
    """
    di = row.get("DataInicial","")
    df = row.get("DataFinal","")
    fs = row.get("Frequencia","")
    if not di or not df:
        return []

    # converter data
    try:
        dt_ini = datetime.strptime(di, "%d%b%y")
        dt_fim = datetime.strptime(df, "%d%b%y")
    except:
        return []

    freq_set = set()
    for c in fs:
        if c.isdigit():
            freq_set.add(int(c))  # 1=seg,...,7=dom

    expanded = []
    d = dt_ini
    while d <= dt_fim:
        dow = d.weekday()+1  # 1=seg,...,7=dom
        if dow in freq_set:
            newrow = dict(row)
            newrow["DataPartida"] = d.strftime("%d/%m/%Y")
            newrow["DataChegada"] = d.strftime("%d/%m/%Y")
            # horaPartida => "HH:MM"
            hp = row.get("HoraPartida","")
            if len(hp) == 4:
                hp_formatted = hp[:2] + ":" + hp[2:]
            else:
                hp_formatted = hp
            newrow["HoraPartida"] = hp_formatted
            hc = row.get("HoraChegada","")
            if len(hc) == 4:
                hc_formatted = hc[:2] + ":" + hc[2:]
            else:
                hc_formatted = hc
            newrow["HoraChegada"] = hc_formatted

            expanded.append(newrow)
        d += timedelta(days=1)
    return expanded

@st.cache_data
def load_support_files():
    try:
        df_airlines = pd.read_csv("iata_airlines.csv")
    except:
        df_airlines = pd.DataFrame(columns=["IATA Designator","Airline Name","ICAO code"])
    try:
        df_airport = pd.read_csv("airport.csv")
    except:
        df_airport = pd.DataFrame(columns=["IATA","Airport","ICAO"])
    return df_airlines, df_airport

def gerar_csv_from_ssim(ssim_path, df_airlines, df_airport):
    """
    Lê SSIM, parse, expande datas, faz casamento (2 voos),
    e salva CSV com nome <arquivo>_convertido.csv
    """
    # extrair nome do ssim sem extensão
    base_name = os.path.basename(ssim_path)
    root, ext = os.path.splitext(base_name)
    output_csv = f"{root}_convertido.csv"

    with open(ssim_path,"r",encoding="latin-1") as f:
        lines = f.readlines()

    base_rows = []
    ignored_count_parse = 0
    for line in lines:
        parsed = parse_ssim_line(line.rstrip('\n'))
        if parsed:
            base_rows.append(parsed)
        else:
            ignored_count_parse += 1

    if not base_rows:
        st.error("Nenhuma linha do tipo 3 reconhecida no SSIM.")
        return None, None

    expanded = []
    for row in base_rows:
        multi = expand_with_frequency(row)
        expanded.extend(multi)

    if not expanded:
        st.error("Nenhuma data gerada após expandir pela frequência.")
        return None, None

    df_voos = pd.DataFrame(expanded)

    # Mapeamentos
    map_iata_to_name = dict(zip(df_airlines["IATA Designator"], df_airlines["Airline Name"]))
    map_iata_to_icao = dict(zip(df_airlines["IATA Designator"], df_airlines["ICAO code"]))
    equip_map = {"73G":"B738","73X":"B738","77W":"B777"}

    # converter date+time p/ datetime
    df_voos["dt_partida"] = None
    for i, r in df_voos.iterrows():
        try:
            parted_str = r["DataPartida"] + " " + r["HoraPartida"]  # "dd/mm/yyyy HH:MM"
            dtp = datetime.strptime(parted_str, "%d/%m/%Y %H:%M")
            df_voos.at[i,"dt_partida"] = dtp
        except:
            df_voos.at[i,"dt_partida"] = None

    grouped = df_voos.groupby(["Casamento","DataPartida"])
    final_rows = []
    ignored_count_casamento = 0

    for (cas_key, data_str), g in grouped:
        g2 = g.sort_values("dt_partida", na_position="first").reset_index(drop=True)

        # Precisamos de pelo menos 2 linhas p/ formar saida+chegada
        if len(g2) < 2:
            ignored_count_casamento += len(g2)
            continue

        reg = {
            "Base": None,
            "Cod. Cliente": None,
            "Nome": None,
            "Data": data_str,
            "Mod": None,
            "Tipo": None,
            "Voo": None,
            "Hora Chegada": None,
            "Hora Saída": None,
            "ICAO": None,
            "AERONAVE": None
        }
        parted_dt = None

        # 1a linha => saída
        r_out = g2.iloc[0]
        reg["Base"] = r_out["Origem"]
        reg["Cod. Cliente"] = r_out["CodCliente"]
        reg["Nome"] = map_iata_to_name.get(r_out["CodCliente"], r_out["CodCliente"])
        reg["ICAO"] = map_iata_to_icao.get(r_out["CodCliente"], r_out["CodCliente"])
        reg["Voo"] = r_out["Voo"]
        eq_ = r_out["Equip"]
        reg["Tipo"] = equip_map.get(eq_, eq_)
        if not reg["Tipo"]:
            # se equip for inválido, pular
            ignored_count_casamento += len(g2)
            continue
        reg["AERONAVE"] = reg["Tipo"]
        reg["Hora Saída"] = r_out["HoraPartida"]

        parted_dt = r_out["dt_partida"]

        # 2a linha => chegada
        if len(g2) >= 2:
            r_in = g2.iloc[1]
            reg["Hora Chegada"] = r_in["HoraChegada"]
            chg_dt = r_in["dt_partida"]
            if parted_dt and chg_dt:
                diff_h = (chg_dt - parted_dt).total_seconds()/3600
                if diff_h > 4:
                    reg["Mod"] = "PNT"
                else:
                    reg["Mod"] = "TST"
            else:
                reg["Mod"] = "TST"
        else:
            ignored_count_casamento += 1
            continue

        final_rows.append(reg)

    df_final = pd.DataFrame(final_rows)
    df_final = df_final[[
        "Base","Cod. Cliente","Nome","Data","Mod","Tipo","Voo",
        "Hora Chegada","Hora Saída","ICAO","AERONAVE"
    ]]

    df_final.to_csv(output_csv, index=False, encoding="utf-8")

    return output_csv, (ignored_count_parse, ignored_count_casamento)

def main():
    st.title("Conversor SSIM - CSV (Expansão + Casamento)")
    df_airlines, df_airport = load_support_files()

    ssim_file = st.file_uploader("Selecione o arquivo SSIM:", type=["ssim","txt"])
    if ssim_file:
        ssim_filename = ssim_file.name
        with open(ssim_filename,"wb") as f:
            f.write(ssim_file.getbuffer())

        if st.button("Processar"):
            outcsv, ignore_info = gerar_csv_from_ssim(ssim_filename, df_airlines, df_airport)
            if outcsv:
                st.success(f"Gerado arquivo: {outcsv}")
                if ignore_info:
                    parse_ign, cas_ign = ignore_info
                    st.write(f"Linhas ignoradas no parse: {parse_ign}")
                    st.write(f"Linhas ignoradas no casamento: {cas_ign}")
                try:
                    with open(outcsv,"rb") as fx:
                        st.download_button("Baixar CSV", fx, file_name=outcsv, mime="text/csv")
                except Exception as e:
                    st.error(f"Erro download: {e}")

if __name__ == "__main__":
    main()
