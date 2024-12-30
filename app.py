import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

###############################################################################
# 1) Função parse_ssim_line:
#    Lê uma linha do tipo 3 (split) e extrai DataInicial, DataFinal, Frequência, etc.
###############################################################################
def parse_ssim_line(line: str):
    line_stripped = line.lstrip()
    splitted = line_stripped.split()
    if len(splitted) < 4:
        return None
    if splitted[0] != '3':
        return None

    # Exemplo de splitted:
    # [0]="3", [1]="G3", [2]="10000101J01DEC2308DEC23", [3]="5",
    # [4]="CGH09050905-0300", [5]="SDU10101010-0300", [6]="73X", ... [9]="1009" ...
    cod_cliente  = splitted[1]
    chunk2       = splitted[2]  # Ex.: '10000101J01DEC2308DEC23'
    freq_str     = splitted[3]  # '5', '1234567', etc.
    origem_info  = splitted[4] if len(splitted) > 4 else ""
    destino_info = splitted[5] if len(splitted) > 5 else ""
    equip        = splitted[6] if len(splitted) > 6 else ""
    casamento    = splitted[9] if len(splitted) > 9 else ""

    # chunk2 => [0:8] => ex. '10000101', [8] => 'J', [9:16] => dataIni, [16:23] => dataFin
    if len(chunk2) < 23:
        return None

    eight_char   = chunk2[0:8]   # '10000101'
    data_inicial_str = chunk2[9:16]  # '01DEC23'
    data_final_str   = chunk2[16:23] # '08DEC23'

    nro_voo    = eight_char[0:4]
    # se quiser dateCount = eight_char[4:6], etapa = eight_char[6:8], etc.

    # Origem e HoraPartida
    if len(origem_info) >= 7:
        origem       = origem_info[0:3]     # ex. 'CGH'
        hora_partida = origem_info[3:7]     # ex. '0905'
    else:
        origem = ""
        hora_partida = ""

    # Destino e HoraChegada
    if len(destino_info) >= 7:
        destino      = destino_info[0:3]    # ex. 'SDU'
        hora_chegada = destino_info[3:7]    # ex. '1010'
    else:
        destino = ""
        hora_chegada = ""

    return {
        "CodCliente":  cod_cliente,
        "Voo":         nro_voo,
        "DataInicial": data_inicial_str,
        "DataFinal":   data_final_str,
        "Frequencia":  freq_str,
        "Origem":      origem,
        "HoraPartida": hora_partida,
        "Destino":     destino,
        "HoraChegada": hora_chegada,
        "Equip":       equip,
        "Casamento":   casamento
    }

###############################################################################
# 2) Expandir datas com base em DataInicial, DataFinal e Frequência.
#    Frequência = string com dígitos 1..7 (1=seg,...,7=dom)
#    Gera data no formato dd/mm/yyyy, hora no formato HH:MM
###############################################################################
def expand_with_frequency(row: dict):
    data_inicial_str = row.get("DataInicial","")
    data_final_str   = row.get("DataFinal","")
    freq_str         = row.get("Frequencia","")
    if not data_inicial_str or not data_final_str:
        return []

    # converter data (ex. '01DEC23' => '%d%b%y')
    try:
        dt_ini = datetime.strptime(data_inicial_str, "%d%b%y")
        dt_fim = datetime.strptime(data_final_str, "%d%b%y")
    except:
        return []

    # set de dias da semana
    freq_set = set()
    for c in freq_str:
        if c.isdigit():
            freq_set.add(int(c))  # 1=seg,...,7=dom

    expanded = []
    d = dt_ini
    while d <= dt_fim:
        dow = d.weekday() + 1  # 1=seg,...,7=dom
        if dow in freq_set:
            newrow = dict(row)
            # data dd/mm/yyyy
            data_fmt = d.strftime("%d/%m/%Y")  # ex. "01/12/2023"
            newrow["DataPartida"] = data_fmt
            newrow["DataChegada"] = data_fmt  # presumindo que chega no mesmo dia
            # hora partida => "HH:MM"
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

###############################################################################
# 3) Carregar arquivos de suporte (iata_airlines.csv, airport.csv) se existirem
###############################################################################
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

###############################################################################
# 4) Lê o SSIM, faz parse, expande datas, depois casa 2 voos (saida+chegada)
###############################################################################
def gerar_csv_from_ssim(ssim_path, df_airlines, df_airport, output_csv="malha_consolidada.csv"):
    with open(ssim_path,"r",encoding="latin-1") as f:
        lines = f.readlines()

    base_rows = []
    for line in lines:
        parsed = parse_ssim_line(line.rstrip('\n'))
        if parsed:
            base_rows.append(parsed)
    if len(base_rows) == 0:
        st.error("Nenhuma linha do tipo 3 reconhecida no SSIM.")
        return

    # Expansão datas
    expanded = []
    for row in base_rows:
        multi = expand_with_frequency(row)
        expanded.extend(multi)

    if len(expanded) == 0:
        st.error("Nenhuma data foi gerada após expandir pela frequência.")
        return

    df_voos = pd.DataFrame(expanded)
    # map cia
    map_iata_to_name = dict(zip(df_airlines["IATA Designator"], df_airlines["Airline Name"]))
    map_iata_to_icao = dict(zip(df_airlines["IATA Designator"], df_airlines["ICAO code"]))

    # map equip
    equip_map = {
        "73X":"B738",
        "73G":"B738",
        "77W":"B777",
        # ...
    }

    # criar col datetime p/ saida
    df_voos["dt_partida"] = None
    for idx, row2 in df_voos.iterrows():
        try:
            parted_str = row2["DataPartida"] + " " + row2["HoraPartida"]  # ex "01/12/2023 09:05"
            dtp = datetime.strptime(parted_str, "%d/%m/%Y %H:%M")
            df_voos.at[idx,"dt_partida"] = dtp
        except:
            df_voos.at[idx,"dt_partida"] = None

    # agrupar
    grouped = df_voos.groupby(["Casamento","DataPartida"])
    registros = []
    for (cas_key, dataKey), group in grouped:
        gsorted = group.sort_values("dt_partida", na_position="first").reset_index(drop=True)
        reg = {
            "Base": None,
            "Cód. Cliente": None,
            "Nome": None,
            "Data": dataKey,  # ex "01/12/2023"
            "Mod": None,
            "Tipo": None,
            "Voo": None,
            "Hora Chegada": None,
            "Hora Saída": None,
            "ICAO": None,
            "AERONAVE": None
        }

        parted_dt = None
        rowcount = 0
        for _, r3 in gsorted.iterrows():
            rowcount += 1
            if rowcount == 1:
                # Voo de saída
                reg["Base"] = r3["Origem"]
                reg["Cód. Cliente"] = r3["CodCliente"]
                reg["Nome"] = map_iata_to_name.get(r3["CodCliente"], r3["CodCliente"])
                reg["ICAO"] = map_iata_to_icao.get(r3["CodCliente"], r3["CodCliente"])
                reg["Voo"] = r3["Voo"]
                # Tipo e Aeronave
                eq_ = r3["Equip"]
                reg["Tipo"] = equip_map.get(eq_, eq_)
                reg["AERONAVE"] = reg["Tipo"]
                reg["Hora Saída"] = r3["HoraPartida"]
                parted_dt = r3["dt_partida"]
            elif rowcount == 2:
                # Voo de chegada
                reg["Hora Chegada"] = r3["HoraChegada"]
                chg_dt = r3["dt_partida"]
                if parted_dt and chg_dt:
                    diff_h = (chg_dt - parted_dt).total_seconds()/3600
                    if diff_h > 4:
                        reg["Mod"] = "PNT"
                    else:
                        reg["Mod"] = "TST"
                else:
                    reg["Mod"] = "TST"

        registros.append(reg)

    df_final = pd.DataFrame(registros)
    df_final = df_final[[
        "Base","Cód. Cliente","Nome","Data","Mod","Tipo","Voo",
        "Hora Chegada","Hora Saída","ICAO","AERONAVE"
    ]]
    df_final.to_csv(output_csv, index=False, encoding="utf-8")
    st.success(f"Arquivo CSV gerado: {output_csv} ({len(df_final)} linhas).")

###############################################################################
# STREAMLIT
###############################################################################
def main():
    st.title("Conversor SSIM - Expansão por Datas e Frequência, e Casamento (2 Voos)")
    st.markdown("Aplicativo minimalista, o resto das explicações estarão no README.")

    df_airlines, df_airport = load_support_files()

    ssim_file = st.file_uploader("Carregue o arquivo SSIM:", type=["ssim","txt"])
    if ssim_file:
        with open("uploaded.ssim","wb") as f:
            f.write(ssim_file.getbuffer())
        
        st.write(f"Arquivo: {ssim_file.name}, tamanho: {ssim_file.size} bytes")

        if st.button("Processar"):
            outcsv = "malha_consolidada.csv"
            gerar_csv_from_ssim("uploaded.ssim", df_airlines, df_airport, outcsv)

            try:
                with open(outcsv,"rb") as fx:
                    st.download_button("Baixar CSV", fx, file_name=outcsv, mime="text/csv")
            except Exception as e:
                st.error(f"Erro download: {e}")

if __name__ == "__main__":
    main()
