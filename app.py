import streamlit as st
import pandas as pd
from datetime import datetime

##############################################################################
# 1. Função de Parsing: Lê a linha do tipo 3, faz split() e extrai campos.
##############################################################################
def parse_ssim_line(line: str):
    """
    Exemplo de linha:
      3 G3 10000101J01DEC2308DEC23    5   CGH09050905-0300  SDU10101010-0300  73X  G3 G3 1009 Y186VVG373X 00000003

    splitted[0] = '3'
    splitted[1] = 'G3'
    splitted[2] = '10000101J01DEC2308DEC23'
      => 0..8 => eight_char_field
         8 => status char (J)
         9..16 => dataPartida (01DEC23)
         16..23 => dataChegada(08DEC23)
    splitted[3] = '5' (frequência, se quiser usar)
    splitted[4] = 'CGH09050905-0300' (origem + horas)
    splitted[5] = 'SDU10101010-0300' (destino + horas)
    splitted[6] = '73X' (equip)
    splitted[7] = 'G3'
    splitted[8] = 'G3'
    splitted[9] = '1009' (casamento)
    splitted[10]= 'Y186VVG373X'
    splitted[11]= '00000003'
    """

    line_stripped = line.lstrip()  # remove espaços no início
    splitted = line_stripped.split()
    if len(splitted) < 3:
        return None
    if splitted[0] != '3':
        return None

    cod_cliente = splitted[1]          # ex.: 'G3'
    chunk2      = splitted[2]          # ex.: '10000101J01DEC2308DEC23'
    freq        = splitted[3] if len(splitted) > 3 else ""      # '5'
    origem_info = splitted[4] if len(splitted) > 4 else ""      # 'CGH09050905-0300'
    destino_info= splitted[5] if len(splitted) > 5 else ""      # 'SDU10101010-0300'
    equip       = splitted[6] if len(splitted) > 6 else ""      # '73X'
    casamento   = splitted[9] if len(splitted) > 9 else ""      # '1009'

    # chunk2 => "eight_char + status + data_part + data_cheg"
    # Ex.: "10000101J01DEC2308DEC23" => 24 chars
    #   0..8 => '10000101' => (4 chars voo, 2 date_counter, 2 etapa)
    #   8 => 'J'
    #   9..16 => '01DEC23'
    #   16..23 => '08DEC23'
    if len(chunk2) < 23:
        return None

    eight_char  = chunk2[0:8]    # "10000101"
    status_char = chunk2[8]      # 'J'
    data_part   = chunk2[9:16]   # '01DEC23'
    data_cheg   = chunk2[16:23]  # '08DEC23'

    nro_voo     = eight_char[0:4]   # "1000"
    date_count  = eight_char[4:6]   # "01"
    etapa       = eight_char[6:8]   # "01"

    # Origem e HoraPartida => ex.: 'CGH09050905-0300'
    if len(origem_info) >= 7:
        origem       = origem_info[0:3]    # 'CGH'
        hora_partida = origem_info[3:7]    # '0905'
    else:
        origem       = ""
        hora_partida = ""

    # Destino e HoraChegada => ex.: 'SDU10101010-0300'
    if len(destino_info) >= 7:
        destino      = destino_info[0:3]   # 'SDU'
        hora_chegada = destino_info[3:7]   # '1010'
    else:
        destino      = ""
        hora_chegada = ""

    return {
        "CodCliente": cod_cliente,
        "NumVoo": nro_voo,
        "DateCounter": date_count,
        "Etapa": etapa,
        "DataPartida": data_part,
        "DataChegada": data_cheg,
        "Frequencia": freq,
        "Origem": origem,
        "HoraPartida": hora_partida,
        "Destino": destino,
        "HoraChegada": hora_chegada,
        "Equip": equip,
        "Casamento": casamento
    }

###############################################################################
# Carrega os arquivos de suporte (iata_airlines.csv, airport.csv)
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
# Agrupa 2 voos (chegada + saída) para formar 1 linha no CSV final
###############################################################################
def gerar_csv_from_ssim(ssim_path: str, df_airlines: pd.DataFrame, df_airport: pd.DataFrame, output_csv="malha_consolidada.csv"):
    # Ler arquivo
    with open(ssim_path,"r",encoding="latin-1") as f:
        lines = f.readlines()

    # parsear
    lista_voos = []
    for line in lines:
        parsed = parse_ssim_line(line.rstrip('\n'))
        if parsed:
            lista_voos.append(parsed)
    if len(lista_voos) == 0:
        st.error("Nenhuma linha do tipo '3' reconhecida no arquivo SSIM.")
        return

    df_voos = pd.DataFrame(lista_voos)

    # Mapeamento cia
    map_iata_to_nome = dict(zip(df_airlines["IATA Designator"], df_airlines["Airline Name"]))
    map_iata_to_icao = dict(zip(df_airlines["IATA Designator"], df_airlines["ICAO code"]))

    # Mapeamento equip -> Tipo
    equip_map = {
        "73X":"B738",
        "73G":"B738",
        "77W":"B777",
        "A320":"A320",
        # ...
    }

    # Preparar datetime p/ Partida
    df_voos["dt_partida"] = None
    for idx, row in df_voos.iterrows():
        try:
            parted_str = row["DataPartida"] + row["HoraPartida"]  # ex '01DEC230905'
            dtp = datetime.strptime(parted_str, "%d%b%y%H%M")
            df_voos.at[idx,"dt_partida"] = dtp
        except:
            df_voos.at[idx,"dt_partida"] = None

    # Agrupar pelo "Casamento"
    grouped = df_voos.groupby("Casamento")
    registros = []

    for cas, group in grouped:
        # Ordenar, assumindo q 1o é saída, 2o é chegada
        group_sorted = group.sort_values("dt_partida", na_position="first").reset_index(drop=True)

        reg = {
            "Base": None,
            "Cód. Cliente": None,
            "Nome": None,
            "Data": None,
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
        for _, r2 in group_sorted.iterrows():
            rowcount += 1
            if rowcount == 1:
                # Saída
                reg["Base"] = r2["Origem"]
                reg["Cód. Cliente"] = r2["CodCliente"]
                reg["Nome"] = map_iata_to_nome.get(r2["CodCliente"], r2["CodCliente"])
                reg["ICAO"] = map_iata_to_icao.get(r2["CodCliente"], r2["CodCliente"])
                reg["Voo"] = r2["NumVoo"]
                reg["Data"] = r2["DataPartida"]
                eq = r2["Equip"]
                reg["Tipo"] = equip_map.get(eq, eq)
                reg["AERONAVE"] = reg["Tipo"]
                reg["Hora Saída"] = r2["HoraPartida"]
                parted_dt = r2["dt_partida"]
            elif rowcount == 2:
                # Chegada
                reg["Hora Chegada"] = r2["HoraChegada"]
                chg_dt = r2["dt_partida"]
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
    st.success(f"Gerado {output_csv} com {len(df_final)} linhas.")
    
###############################################################################
# STREAMLIT APP
###############################################################################
def main():
    st.title("Conversor SSIM → CSV (2 voos por linha, via 'Casamento')")
    st.markdown("""
    Sobe um arquivo SSIM. Vamos parsear as linhas do tipo 3 (ex: 
    `"3 G3 10000101J01DEC2308DEC23    5   CGH09050905-0300  SDU10101010-0300  73X  G3 G3 1009 Y186VVG373X 00000003"`)
    e agrupar 2 voos (chegada+saída) na "visão do aeroporto".
    """)

    # Carregar suportes
    df_airlines, df_airport = load_support_files()

    ssim_file = st.file_uploader("Selecione o arquivo SSIM:", type=["ssim","txt"])
    if ssim_file is not None:
        with open("uploaded.ssim","wb") as f:
            f.write(ssim_file.getbuffer())
        
        st.write(f"**Arquivo**: {ssim_file.name}, Tamanho: {ssim_file.size} bytes")

        if st.button("Gerar CSV"):
            outcsv = "malha_consolidada.csv"
            gerar_csv_from_ssim(
                ssim_path="uploaded.ssim",
                df_airlines=df_airlines,
                df_airport=df_airport,
                output_csv=outcsv
            )
            # Oferecer download
            try:
                with open(outcsv,"rb") as fx:
                    st.download_button(
                        label="Baixar CSV",
                        data=fx,
                        file_name=outcsv,
                        mime="text/csv"
                    )
            except Exception as e:
                st.error(f"Erro no download: {e}")


if __name__ == "__main__":
    main()
