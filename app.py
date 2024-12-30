import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

##############################################################################
# 1) Função para converter Frequência (ex.: '12356') em um set de dias da semana
#    onde 1=Segunda, 2=Terça, ..., 7=Domingo, por exemplo.
##############################################################################
def parse_frequency_bits(freq_str: str):
    """
    Recebe algo tipo '5', ou '1234567', ou '1357' etc.
    Retorna um set de int representando dias da semana. Ex. {5} ou {1,2,3,4,5,6,7}.
    Precisamos padronizar: 1=Seg, 2=Ter, 3=Qua, 4=Qui, 5=Sex, 6=Sab, 7=Dom.
    Ajuste se seu SSIM usar outro mapeamento (ex. 1=Dom).
    """
    freq_str = freq_str.strip()
    dias = set()
    for ch in freq_str:
        if ch.isdigit():
            d = int(ch)
            if 1 <= d <= 7:
                dias.add(d)
    return dias

##############################################################################
# 2) Parser de uma linha do tipo 3, usando split() e expandindo datas
##############################################################################
def parse_ssim_line_and_expand(line: str):
    """
    Exemplo de linha:
    3 G3 10000101J01DEC2308DEC23    5   CGH09050905-0300  SDU10101010-0300  73X  G3 G3 1009 Y186VVG373X 00000003

    splitted[0] = '3'
    splitted[1] = 'G3'
    splitted[2] = '10000101J01DEC2308DEC23'
       => 0..8 => '10000101' -> NumVoo(0..4), date_counter(4..6), etapa(6..8)
       => [8] = 'J' (status)
       => [9..16] -> DataInicio ex '01DEC23'
       => [16..23] -> DataFim ex '08DEC23'
    splitted[3] = '5' (Frequência)
    splitted[4] = 'CGH09050905-0300' (Origem+Hora)
    splitted[5] = 'SDU10101010-0300' (Destino+Hora)
    splitted[6] = '73X' (Equip)
    splitted[9] = '1009' (Casamento)
    etc.

    Precisamos expandir para cada data do intervalo [DataInicio..DataFim]
    SOMENTE nos dias da semana que a Frequência indica.
    """
    line_stripped = line.lstrip()
    splitted = line_stripped.split()
    if len(splitted) < 4:
        return []  # nada

    if splitted[0] != '3':
        return []  # não é tipo 3

    # Extrações
    cod_cliente = splitted[1]                # ex: 'G3'
    chunk2      = splitted[2]                # "10000101J01DEC2308DEC23"
    freq_str    = splitted[3]                # ex: '5'
    origem_info = splitted[4] if len(splitted) > 4 else ""
    destino_info= splitted[5] if len(splitted) > 5 else ""
    equip       = splitted[6] if len(splitted) > 6 else ""
    casamento   = splitted[9] if len(splitted) > 9 else ""

    if len(chunk2) < 23:
        return []  # incompleto

    # eight_char => [0..8]
    eight_char  = chunk2[0:8]   # "10000101"
    status_char = chunk2[8]     # 'J'
    data_ini    = chunk2[9:16]  # '01DEC23'
    data_fim    = chunk2[16:23] # '08DEC23'

    # Exemplo: '10000101' => 0..4 => '1000' -> nro voo
    nro_voo      = eight_char[0:4]
    date_counter = eight_char[4:6]
    etapa        = eight_char[6:8]

    # Origem e HoraPartida
    if len(origem_info) >= 7:
        origem = origem_info[0:3]
        hora_partida = origem_info[3:7]
    else:
        origem = ""
        hora_partida = ""

    # Destino e HoraChegada
    if len(destino_info) >= 7:
        destino = destino_info[0:3]
        hora_chegada = destino_info[3:7]
    else:
        destino = ""
        hora_chegada = ""

    # Frequência -> set de dias
    freq_days = parse_frequency_bits(freq_str)  # ex. {5} => Sexta, etc.

    # Converter data_ini e data_fim p/ datetime
    # ddMMMYY => ex: '01DEC23'
    def parse_date(ddmmyy: str):
        try:
            return datetime.strptime(ddmmyy, "%d%b%y")
        except:
            return None
    
    dt_ini = parse_date(data_ini)
    dt_fim = parse_date(data_fim)
    if (not dt_ini) or (not dt_fim):
        return []  # datas inválidas

    # Expandir dia a dia
    expanded_rows = []
    current_dt = dt_ini
    while current_dt <= dt_fim:
        # Ver qual dia da semana (1=Seg,...,7=Dom). Python: Monday=0, Sunday=6
        # Precisamos mapear Monday=0 => "1" (Seg), Tuesday=1 => "2", etc.
        # Ou seja: day_of_week = current_dt.weekday() => 0..6
        # Se 0 => seg => "1", 1 => ter => "2", ... 6 => dom => "7"
        python_day = current_dt.weekday()  # 0=Seg ... 6=Dom
        ssim_day = python_day + 1          # 1..7
        if ssim_day in freq_days:
            # Essa data está dentro da freq
            expanded_rows.append({
                "CodCliente": cod_cliente,
                "NumVoo": nro_voo,
                "DateCounter": date_counter,
                "Etapa": etapa,
                "Data": current_dt.strftime("%d%b%y").upper(),  # ex: '01DEC23'
                "HoraSaida": hora_partida,
                "HoraChegada": hora_chegada,
                "Origem": origem,
                "Destino": destino,
                "Equip": equip,
                "Casamento": casamento
            })
        # proximo dia
        current_dt += timedelta(days=1)

    return expanded_rows


###############################################################################
# Carrega iata_airlines.csv e airport.csv
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
# Agrupa (casamento) 2 voos => 1 linha
###############################################################################
def gerar_csv_from_ssim(ssim_path, df_airlines, df_airport, output_csv="malha_consolidada.csv"):
    # Ler linhas
    with open(ssim_path, "r", encoding="latin-1") as f:
        lines = f.readlines()

    # parse e expand
    all_expanded = []
    for line in lines:
        list_expanded = parse_ssim_line_and_expand(line)
        if list_expanded:
            all_expanded.extend(list_expanded)
    if len(all_expanded) == 0:
        st.error("Nenhuma linha de voo foi expandida (freq/datas).")
        return

    df_voos = pd.DataFrame(all_expanded)

    # Mapeamentos de cia
    map_iata_to_name = dict(zip(df_airlines["IATA Designator"], df_airlines["Airline Name"]))
    map_iata_to_icao = dict(zip(df_airlines["IATA Designator"], df_airlines["ICAO code"]))

    # Mapeamento equip -> Tipo
    equip_map = {
        "73X":"B738",
        "73G":"B738",
        "77W":"B777",
        "A320":"A320",
        # ...
    }

    # Converter Data+HoraSaida em datetime
    def parse_dt(row):
        dt_str = row["Data"] + row["HoraSaida"]
        try:
            return datetime.strptime(dt_str, "%d%b%y%H%M")
        except:
            return None
    df_voos["dt_partida"] = df_voos.apply(parse_dt, axis=1)

    # Agrupar por "Casamento"
    grouped = df_voos.groupby("Casamento")

    registros = []
    for cas, group in grouped:
        # ordenar p/ 1º => saída, 2º => chegada
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
        rowcount = 0
        saida_dt = None
        for _, r2 in group_sorted.iterrows():
            rowcount += 1
            if rowcount == 1:
                # saída
                reg["Base"] = r2["Origem"]
                reg["Cód. Cliente"] = r2["CodCliente"]
                reg["Nome"] = map_iata_to_name.get(r2["CodCliente"], r2["CodCliente"])
                reg["ICAO"] = map_iata_to_icao.get(r2["CodCliente"], r2["CodCliente"])
                reg["Voo"] = r2["NumVoo"]
                reg["Data"] = r2["Data"]  # Ex: '01DEC23'
                eq_ = r2["Equip"]
                reg["Tipo"] = equip_map.get(eq_, eq_)
                reg["AERONAVE"] = reg["Tipo"]
                reg["Hora Saída"] = r2["HoraSaida"]
                saida_dt = r2["dt_partida"]
            elif rowcount == 2:
                # chegada
                reg["Hora Chegada"] = r2["HoraChegada"]
                chg_dt = r2["dt_partida"]
                if saida_dt and chg_dt:
                    diff_h = (chg_dt - saida_dt).total_seconds()/3600
                    if diff_h > 4:
                        reg["Mod"] = "PNT"
                    else:
                        reg["Mod"] = "TST"
                else:
                    reg["Mod"] = "TST"
        registros.append(reg)

    df_final = pd.DataFrame(registros)
    # reordenar colunas
    df_final = df_final[[
        "Base","Cód. Cliente","Nome","Data","Mod","Tipo","Voo",
        "Hora Chegada","Hora Saída","ICAO","AERONAVE"
    ]]

    df_final.to_csv(output_csv, index=False, encoding="utf-8")
    st.success(f"Arquivo CSV gerado: {output_csv} ({len(df_final)} linhas)")

###############################################################################
# STREAMLIT
###############################################################################
def main():
    st.title("SSIM → CSV (com Expansão de Datas + Frequência e Casamento de 2 voos)")
    st.markdown("""
    Este aplicativo:
    1) Lê as linhas do tipo 3 do SSIM.
    2) Extrai data inicial e final (ex: 01DEC23, 08DEC23) e a Freq (ex: '5', '1234567').
    3) Expande todas as datas desse intervalo, mas **somente** nos dias da semana indicados pela Freq.
    4) Agrupa (casamento) para gerar 2 voos por linha (visão do aeroporto).
    """)

    df_airlines, df_airport = load_support_files()

    ssim_file = st.file_uploader("Carregue o SSIM:", type=["ssim","txt"])
    if ssim_file is not None:
        with open("my_ssim.ssim","wb") as f:
            f.write(ssim_file.getbuffer())
        st.write(f"**Arquivo**: {ssim_file.name}, tamanho {ssim_file.size} bytes")

        if st.button("Gerar CSV"):
            outcsv = "malha_consolidada.csv"
            gerar_csv_from_ssim("my_ssim.ssim", df_airlines, df_airport, outcsv)
            # Download
            try:
                with open(outcsv,"rb") as fx:
                    st.download_button("Baixar CSV", fx, file_name=outcsv, mime="text/csv")
            except Exception as e:
                st.error(f"Erro no download: {e}")


if __name__ == "__main__":
    main()
