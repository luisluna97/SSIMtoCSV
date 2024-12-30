import streamlit as st
import pandas as pd
from datetime import datetime

def parse_ssim_line(line: str):
    """
    Faz parsing de uma linha SSIM do tipo '3' (ignorando possíveis espaços iniciais)
    e retorna um dicionário com os campos extraídos ou None se não reconhece.

    Exemplo típico de linha:
    
    3 G3 10000101J01DEC2308DEC23    5   CGH09050905-0300  SDU10101010-0300  73X  G3 G3 1009 Y186VVG373X 00000003

    'split()' pode produzir algo assim (separado por espaços):
    splitted[0] = "3"
    splitted[1] = "G3"
    splitted[2] = "10000101J01DEC2308DEC23"
    splitted[3] = "5"
    splitted[4] = "CGH09050905-0300"
    splitted[5] = "SDU10101010-0300"
    splitted[6] = "73X"
    splitted[7] = "G3"
    splitted[8] = "G3"
    splitted[9] = "1009"         <-- campo de casamento
    splitted[10]= "Y186VVG373X"  <-- não usado
    splitted[11]= "00000003"     <-- contagem de linha ou algo assim

    Ajuste se seu SSIM real gerar mais ou menos splits.
    """
    # Remover espaços à esquerda
    line_stripped = line.lstrip()
    if not line_stripped.startswith('3'):
        # Se depois de tirar espaços, não inicia com '3', não é uma linha de voo tipo 3
        return None

    splitted = line_stripped.split()
    if len(splitted) < 3:
        return None
    
    # splitted[0] deve ser "3", splitted[1] = "G3", splitted[2] = "10000101J01DEC2308DEC23", etc...
    # Caso algumas linhas venham "3G3" junto, será preciso ainda mais lógica, mas vamos supor
    # que splitted[0] == "3" e splitted[1] == "G3"

    if splitted[0] != '3':
        return None
    
    # Exemplo de extrações
    cod_cliente   = splitted[1]   # "G3"
    if len(splitted) < 3: 
        return None

    chunk2        = splitted[2]   # "10000101J01DEC2308DEC23"
    # A 'freq' se quisesse, splitted[3], e etc...
    freq          = splitted[3] if len(splitted) >= 4 else ""
    origem_info   = splitted[4] if len(splitted) >= 5 else ""
    destino_info  = splitted[5] if len(splitted) >= 6 else ""
    equip         = splitted[6] if len(splitted) >= 7 else ""
    # splitted[7], splitted[8] podem ser cia repetida
    casamento_voo = splitted[9] if len(splitted) >= 10 else ""  # "1009"
    # splitted[10] e splitted[11] podem ser ignorados

    # chunk2 => "eight_char_field + status + dataPartida + dataChegada"
    # Ex: "10000101J01DEC2308DEC23"
    #  0..8 => "10000101"
    #  8 => 'J'
    #  9..16 => "01DEC23"
    #  16..23 => "08DEC23"
    if len(chunk2) < 23:
        return None

    eight_char  = chunk2[0:8]    # "10000101"
    status_char = chunk2[8]      # 'J'
    data_part   = chunk2[9:16]   # '01DEC23'
    data_cheg   = chunk2[16:23]  # '08DEC23'

    # eight_char => ex: "10000101"
    nro_voo      = eight_char[0:4]
    date_counter = eight_char[4:6]
    etapa        = eight_char[6:8]

    # Origem e HoraPartida
    if len(origem_info) >= 7:
        aeroporto_o = origem_info[0:3]
        hora_partida= origem_info[3:7]
    else:
        aeroporto_o = ""
        hora_partida= ""

    # Destino e HoraChegada
    if len(destino_info) >= 7:
        aeroporto_d = destino_info[0:3]
        hora_chegada= destino_info[3:7]
    else:
        aeroporto_d = ""
        hora_chegada= ""

    return {
        "CodCliente": cod_cliente,
        "NumVoo": nro_voo,
        "DateCounter": date_counter,
        "Etapa": etapa,
        "StatusChar": status_char,
        "DataPartida": data_part,
        "DataChegada": data_cheg,
        "Origem": aeroporto_o,
        "HoraPartida": hora_partida,
        "Destino": aeroporto_d,
        "HoraChegada": hora_chegada,
        "Equip": equip,
        "Casamento": casamento_voo
    }

@st.cache_data
def load_support_files():
    """
    Lê iata_airlines.csv e airport.csv, se existirem, para mapear:
      - CIA IATA -> Nome, ICAO
      - (Opcional) IATA Aeroporto -> Nome Aeroporto etc.
    """
    try:
        df_airlines = pd.read_csv("iata_airlines.csv")
    except:
        df_airlines = pd.DataFrame(columns=["IATA Designator","Airline Name","ICAO code"])

    try:
        df_airport = pd.read_csv("airport.csv")
    except:
        df_airport = pd.DataFrame(columns=["IATA","Airport","ICAO"])

    return df_airlines, df_airport

def gerar_csv_from_ssim(ssim_path, df_airlines, df_airport, output_csv="malha_consolidada.csv"):
    # Ler linhas do SSIM
    try:
        with open(ssim_path,"r",encoding="latin-1") as f:
            lines = f.readlines()
    except Exception as e:
        st.error(f"Erro ao ler {ssim_path}: {e}")
        return

    # Parsear
    lista_voos = []
    for line in lines:
        parsed = parse_ssim_line(line.rstrip('\n'))
        if parsed:
            lista_voos.append(parsed)
    if len(lista_voos) == 0:
        st.error("Nenhuma linha do tipo '3' reconhecida no arquivo SSIM.")
        return

    df_voos = pd.DataFrame(lista_voos)

    # Mapeamentos de cia e equip
    map_iata_to_nome = dict(zip(df_airlines["IATA Designator"], df_airlines["Airline Name"]))
    map_iata_to_icao = dict(zip(df_airlines["IATA Designator"], df_airlines["ICAO code"]))

    equip_map = {
        "73X":"B738",
        "73G":"B738",
        "77W":"B777",
        "A320":"A320",
        # ...
    }

    # Agrupar e consolidar 2 voos
    df_voos["dt_part"] = None
    for idx, row in df_voos.iterrows():
        try:
            parted_str = row["DataPartida"] + row["HoraPartida"]  # ex: '01DEC230905'
            dtp = datetime.strptime(parted_str, "%d%b%y%H%M")
            df_voos.at[idx,"dt_part"] = dtp
        except:
            df_voos.at[idx,"dt_part"] = None

    grouped = df_voos.groupby("Casamento")

    registros = []
    for cas_key, grupo in grouped:
        # Sort p/ a 1a ser a saída, 2a ser a chegada
        grupo_sorted = grupo.sort_values("dt_part", na_position="first").reset_index(drop=True)

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
        rowcount = 0
        for _, r2 in grupo_sorted.iterrows():
            rowcount += 1
            if rowcount == 1:
                # Saída
                reg["Base"] = r2["Origem"]  # ex.: 'REC'
                reg["Cód. Cliente"] = r2["CodCliente"]
                reg["Nome"] = map_iata_to_nome.get(r2["CodCliente"], r2["CodCliente"])
                reg["ICAO"] = map_iata_to_icao.get(r2["CodCliente"], r2["CodCliente"])
                reg["Voo"] = r2["NumVoo"]
                reg["Data"] = r2["DataPartida"]

                eq_ = r2["Equip"]
                reg["Tipo"] = equip_map.get(eq_, eq_)
                reg["AERONAVE"] = reg["Tipo"]

                reg["Hora Saída"] = r2["HoraPartida"]
                saida_dt = r2["dt_part"]
            elif rowcount == 2:
                # Chegada
                reg["Hora Chegada"] = r2["HoraChegada"]
                chegada_dt = r2["dt_part"]
                if saida_dt and chegada_dt:
                    diff_h = (chegada_dt - saida_dt).total_seconds()/3600
                    if diff_h > 4:
                        reg["Mod"] = "PNT"
                    else:
                        reg["Mod"] = "TST"
                else:
                    reg["Mod"] = "TST"

        registros.append(reg)

    df_final = pd.DataFrame(registros)
    df_final = df_final[[
        "Base","Cód. Cliente","Nome","Data","Mod",
        "Tipo","Voo","Hora Chegada","Hora Saída","ICAO","AERONAVE"
    ]]

    df_final.to_csv(output_csv, index=False, encoding="utf-8")
    st.success(f"Gerado {output_csv} com {len(df_final)} linhas.")

def main():
    st.title("Conversor SSIM → CSV (Casamento 2 voos) [Flex]")

    st.markdown("""
    Esse aplicativo lê um arquivo SSIM e extrai linhas do tipo 3, mesmo que haja
    variação de espaços, usando `split()` de forma flexível.
    Depois, agrupa 2 voos (chegada + saída) na visão do aeroporto.
    """)

    df_airl, df_airp = load_support_files()

    file_ssim = st.file_uploader("Carregue o SSIM:", type=['ssim','txt'])
    if file_ssim is not None:
        with open("uploaded.ssim","wb") as f:
            f.write(file_ssim.getbuffer())

        st.write(f"Arquivo carregado: {file_ssim.name}, size: {file_ssim.size} bytes")

        if st.button("Gerar CSV"):
            outcsv = "malha_consolidada.csv"
            gerar_csv_from_ssim(
                ssim_path="uploaded.ssim",
                df_airlines=df_airl,
                df_airport=df_airp,
                output_csv=outcsv
            )
            # Baixar
            try:
                with open(outcsv,"rb") as fx:
                    st.download_button("Baixar CSV", fx, file_name=outcsv, mime="text/csv")
            except:
                st.error("Não foi gerado o CSV ou erro no link de download")

if __name__ == "__main__":
    main()
