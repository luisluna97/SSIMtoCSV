import streamlit as st
import pandas as pd
from datetime import datetime

###############################################################################
# 1) PARSER BÁSICO DE UMA LINHA "3 G3 10000101J01DEC2308DEC23 ..."
###############################################################################
def parse_ssim_line(line: str):
    """
    Faz o split por espaços e pega os campos na ordem conhecida.
    Exemplo de linha:

    3 G3 10000101J01DEC2308DEC23    5   CGH09050905-0300  SDU10101010-0300  73X  G3 G3 1009 Y186VVG373X 00000003

    Vamos supor que, ao fazer split, teremos algo como:
    splitted[0] = "3"
    splitted[1] = "G3"
    splitted[2] = "10000101J01DEC2308DEC23"
    splitted[3] = "5"
    splitted[4] = "CGH09050905-0300"
    splitted[5] = "SDU10101010-0300"
    splitted[6] = "73X"
    splitted[7] = "G3"
    splitted[8] = "G3"
    splitted[9] = "1009"
    splitted[10] = "Y186VVG373X"
    splitted[11] = "00000003"

    Ajuste caso seu layout real seja um pouco diferente.
    """
    splitted = line.split()
    if len(splitted) < 9:
        return None
    if splitted[0] != "3":
        return None

    # Exemplo de parse
    cod_cliente = splitted[1]  # "G3"
    chunk2      = splitted[2]  # "10000101J01DEC2308DEC23"
    freq        = splitted[3]  # "5" (pode ignorar se não precisar)
    origem_info = splitted[4]  # "CGH09050905-0300"
    destino_info= splitted[5]  # "SDU10101010-0300"
    equip       = splitted[6]  # "73X"
    # splitted[7] e splitted[8] podem ser repetições de "G3" ou algo que vc não precise
    # splitted[9] = "1009" -> suposto "casamento" ou voo de conexão
    # splitted[10]= "Y186VVG373X" -> supostamente ignorado
    # splitted[11]= "00000003" -> contagem de linha?

    # Se não houver splitted[9], retorne None
    if len(splitted) < 10:
        return None
    casamento_voo = splitted[9]  # "1009"

    # Vamos parsear splitted[2] => "eight_char_field" + "J" + data_partida + data_chegada
    # Exemplo: "10000101J01DEC2308DEC23"
    #   0..8 => "10000101"
    #   8 => 'J' (status)
    #   9..16 => '01DEC23'
    #   16..23 => '08DEC23'
    # total = 24 chars
    c2 = chunk2
    if len(c2) < 23:
        return None
    
    eight_field   = c2[0:8]   # "10000101"
    status_char   = c2[8]     # "J"
    data_partida  = c2[9:16]  # "01DEC23"
    data_chegada  = c2[16:23] # "08DEC23"

    # eight_field => ex: "10000101"
    #   0..4 => "1000" => nro voo
    #   4..6 => "01" => date_counter
    #   6..8 => "01" => etapa
    nro_voo      = eight_field[0:4]
    date_counter = eight_field[4:6]
    etapa        = eight_field[6:8]

    # Agora extrair "Origem" e "HoraPartida" de splitted[4], ex: "CGH09050905-0300" 
    # Fica a seu critério como fatiar. Exemplo:
    if len(origem_info) >= 7:
        origem = origem_info[0:3]     # "CGH"
        hora_partida = origem_info[3:7]  # "0905"  
        # timezone? parted? 
    else:
        origem = ""
        hora_partida = ""

    # Idem "Destino" e "HoraChegada"
    if len(destino_info) >= 7:
        destino = destino_info[0:3]    
        hora_chegada = destino_info[3:7] 
    else:
        destino = ""
        hora_chegada = ""

    # Montar o dicionário final
    return {
        "CodCliente": cod_cliente,
        "NumVoo": nro_voo,
        "DateCounter": date_counter,
        "Etapa": etapa,
        "StatusChar": status_char,
        "DataPartida": data_partida,
        "DataChegada": data_chegada,
        "Origem": origem,
        "HoraPartida": hora_partida,
        "Destino": destino,
        "HoraChegada": hora_chegada,
        "Equip": equip,
        "Casamento": casamento_voo
    }

###############################################################################
# 2) Lê iata_airlines.csv e airport.csv para mapear nomes e etc.
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
        df_airport = pd.DataFrame(columns=["IATA","ICAO","Airport","City","Country"])
    return df_airlines, df_airport

###############################################################################
# 3) Faz a consolidação (visão de aeroporto) usando 'Casamento' para juntar 2 voos
###############################################################################
def gerar_csv_from_ssim(ssim_path: str, df_airlines: pd.DataFrame, df_airport: pd.DataFrame, output_csv="malha_consolidada.csv"):
    # Ler e parsear
    with open(ssim_path, "r", encoding="latin-1") as f:
        lines = f.readlines()

    parsed_rows = []
    for line in lines:
        rowp = parse_ssim_line(line.strip())
        if rowp:
            parsed_rows.append(rowp)
    if len(parsed_rows) == 0:
        st.error("Nenhuma linha SSIM do tipo 3 foi reconhecida.")
        return
    
    df_voos = pd.DataFrame(parsed_rows)

    # Mapeamento cia -> Nome e ICAO
    map_iata_to_name = dict(zip(df_airlines["IATA Designator"], df_airlines["Airline Name"]))
    map_iata_to_icao = dict(zip(df_airlines["IATA Designator"], df_airlines["ICAO code"]))

    # Mapeamento equip -> Tipo
    equip_map = {
        '73X': 'B738',
        '73G': 'B738',
        '77W': 'B777',
        'A320': 'A320',
        # ...
    }

    # Agrupar pelo 'Casamento'
    grouped = df_voos.groupby("Casamento")

    registros = []
    for cas_key, group in grouped:
        # Ordenar por dataPartida p/ 1o reg ser saida, 2o ser chegada
        # (Exemplo: "01DEC23" < "08DEC23" etc.)
        # Para ordenar com datetime, é melhor converter. 
        group = group.copy()
        def dtparse(row):
            try:
                return datetime.strptime(row["DataPartida"]+row["HoraPartida"], "%d%b%y%H%M")
            except:
                return None
        group["dt_saida"] = group.apply(dtparse, axis=1)
        group = group.sort_values(by="dt_saida", na_position="first")

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

        saida_dt = None
        chegada_dt = None
        rowcount = 0
        for idx, row in group.iterrows():
            rowcount += 1
            if rowcount == 1:
                # Saída
                reg["Base"] = row["Origem"]   # "REC" ou "CGH" etc.
                reg["Cód. Cliente"] = row["CodCliente"]
                reg["Nome"] = map_iata_to_name.get(row["CodCliente"], row["CodCliente"])
                reg["ICAO"] = map_iata_to_icao.get(row["CodCliente"], row["CodCliente"])
                reg["Voo"] = row["NumVoo"]
                reg["Data"] = row["DataPartida"]
                # Tipo e Aeronave
                eq = row["Equip"]
                reg["Tipo"] = equip_map.get(eq, eq)
                reg["AERONAVE"] = reg["Tipo"]
                # Hora de Saída
                reg["Hora Saída"] = row["HoraPartida"]
                # Guardar dt
                saida_dt = row["dt_saida"]
            elif rowcount == 2:
                # Chegada
                reg["Hora Chegada"] = row["HoraChegada"]
                chegada_dt = row["dt_saida"]  # esse "dt_saida" do 2o item é a data/hora do 2o reg
                # Calcular tempo de solo => 'Mod'
                if saida_dt and chegada_dt:
                    diff_h = (chegada_dt - saida_dt).total_seconds() / 3600
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
    st.success(f"Arquivo CSV gerado: {output_csv}")

###############################################################################
# STREAMLIT MAIN
###############################################################################
def main():
    st.title("Conversor SSIM para CSV - Visão de Aeroporto (2 voos por linha)")

    st.markdown("""
    Este aplicativo converte as linhas do tipo 3 de um arquivo SSIM
    em um CSV onde cada linha representa o casamento de 2 voos (chegada + saída)
    na perspectiva do aeroporto-base.
    """)

    # Carrega arquivos de suporte
    df_airlines, df_airport = load_support_files()

    # Upload do arquivo SSIM
    file_ssim = st.file_uploader("Selecione o arquivo SSIM:", type=['ssim','txt'])
    if file_ssim is not None:
        ssim_filename = "uploaded_ssim.ssim"
        with open(ssim_filename, "wb") as f:
            f.write(file_ssim.getbuffer())
        
        st.write(f"Arquivo Carregado: {file_ssim.name}")
        st.write(f"Tamanho: {file_ssim.size/1024:.2f} KB")

        if st.button("Gerar CSV"):
            outcsv = "malha_consolidada.csv"
            gerar_csv_from_ssim(
                ssim_path=ssim_filename,
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
                st.error(f"Erro ao gerar link de download: {e}")


if __name__ == "__main__":
    main()
