import pandas as pd
from datetime import datetime, timedelta

def parse_ssim_line(line: str):
    """
    Exemplo de linha (split por espaços):
      splitted[0] = '3'
      splitted[1] = 'G3'
      splitted[2] = '10000101J01DEC2308DEC23'
      splitted[3] = '5'  (frequência, ex. '5' ou '1234567')
      splitted[4] = 'CGH09050905-0300'
      splitted[5] = 'SDU10101010-0300'
      splitted[6] = '73X'
      splitted[9] = '1009' (campo de casamento)
    """
    line_stripped = line.lstrip()
    splitted = line_stripped.split()
    if len(splitted) < 4:
        return None
    if splitted[0] != '3':
        return None

    cod_cliente  = splitted[1]
    chunk2       = splitted[2]  # "10000101J01DEC2308DEC23"
    freq_str     = splitted[3]  # "5", "1234567", etc.
    origem_info  = splitted[4] if len(splitted) > 4 else ""
    destino_info = splitted[5] if len(splitted) > 5 else ""
    equip        = splitted[6] if len(splitted) > 6 else ""
    casamento    = splitted[9] if len(splitted) > 9 else ""

    # chunk2 => [0:8]eight_char, [8]status, [9:16]dataIni, [16:23]dataFin
    if len(chunk2) < 23:
        return None
    eight_char   = chunk2[0:8]
    data_inicial_str = chunk2[9:16]   # p.ex. "01DEC23"
    data_final_str   = chunk2[16:23]  # p.ex. "08DEC23"

    nro_voo    = eight_char[0:4]
    # date_count= eight_char[4:6]  # se precisar
    # etapa     = eight_char[6:8]  # se precisar

    # Horas e Aeroportos
    if len(origem_info) >= 7:
        origem       = origem_info[0:3]     # p.ex. 'CGH'
        hora_partida = origem_info[3:7]     # p.ex. '0905'
    else:
        origem = ""
        hora_partida = ""
    if len(destino_info) >= 7:
        destino      = destino_info[0:3]
        hora_chegada = destino_info[3:7]
    else:
        destino = ""
        hora_chegada = ""

    return {
        "CodCliente": cod_cliente,
        "Voo": nro_voo,
        "DataInicial": data_inicial_str,   # ex. "01DEC23"
        "DataFinal":   data_final_str,     # ex. "08DEC23"
        "Frequencia":  freq_str,           # ex. '5' ou '1234567'
        "Origem":      origem,
        "HoraPartida": hora_partida,       # ex. "0905"
        "Destino":     destino,
        "HoraChegada": hora_chegada,
        "Equip":       equip,
        "Casamento":   casamento
    }

def expand_with_frequency(row: dict):
    """
    Recebe um dicionário com DataInicial, DataFinal, Frequencia, etc.
    Gera várias linhas, uma para cada dia do intervalo [DataInicial, DataFinal],
    cujo dia da semana está na Frequencia.
    Retorna uma lista de dicts, cada qual com DataPartida/ DataChegada = dd/mm/yyyy e
    HoraPartida/HoraChegada = HH:MM
    """
    data_inicial_str = row.get("DataInicial","")
    data_final_str   = row.get("DataFinal","")
    freq_str         = row.get("Frequencia","")
    if not data_inicial_str or not data_final_str:
        return []

    # converter p/ datetime (padrão 'DDMMMYY' => '%d%b%y')
    # ex.: '01DEC23'
    try:
        dt_ini = datetime.strptime(data_inicial_str, "%d%b%y")
        dt_fim = datetime.strptime(data_final_str, "%d%b%y")
    except:
        return []

    # Montar set de dias da semana. ex. '5' => {5}, '1234567' => {1,2,3,4,5,6,7}
    freq_set = set()
    for c in freq_str:
        if c.isdigit():
            freq_set.add(int(c))  # 1=seg ... 7=dom (conforme a convenção usual SSIM)

    expanded = []
    # loop data
    d = dt_ini
    while d <= dt_fim:
        # d.weekday() => 0=mon,...,6=sun => +1 => 1=mon,...,7=sun
        dow = d.weekday() + 1
        if dow in freq_set:
            # Clonar row e trocar DataPartida/ DataChegada por d
            newrow = dict(row)
            # Formatar data => dd/mm/yyyy
            data_fmt = d.strftime("%d/%m/%Y")  # ex. "01/12/2023"
            newrow["DataPartida"] = data_fmt
            newrow["DataChegada"] = data_fmt  # Presume que o voo chega no mesmo dia
            # Formatar HoraPartida => "HH:MM"
            # se "HoraPartida" era "0905", transformamos em "09:05"
            hp = row.get("HoraPartida","")
            if len(hp) == 4:  # '0905'
                hp_formatted = hp[0:2] + ":" + hp[2:4]  # "09:05"
            else:
                hp_formatted = hp  # se vier vazio ou outro formato
            newrow["HoraPartida"] = hp_formatted

            hc = row.get("HoraChegada","")
            if len(hc) == 4:  # ex. "1010" => "10:10"
                hc_formatted = hc[0:2] + ":" + hc[2:4]
            else:
                hc_formatted = hc
            newrow["HoraChegada"] = hc_formatted

            expanded.append(newrow)
        d += timedelta(days=1)

    return expanded

def exemplo_de_fluxo():
    """
    Exemplo completo de fluxo:
    - Ler linhas SSIM de um arquivo
    - parsear
    - expandir
    - *depois* agrupar ou casar (ex.: groupby 'Casamento' + data)
    """
    # 1) ler arquivo
    with open("exemplo.ssim","r",encoding="latin-1") as f:
        lines = f.readlines()

    base_rows = []
    for line in lines:
        parsed = parse_ssim_line(line.rstrip('\n'))
        if parsed:
            base_rows.append(parsed)
    # 2) expand freq
    expanded = []
    for row in base_rows:
        multi = expand_with_frequency(row)
        expanded.extend(multi)

    # Agora expanded tem 1 dict p/ cada dia em que opera
    df = pd.DataFrame(expanded)
    # exibe df
    print("Malha expandida:")
    print(df.head(20))

    # 3) Fazer casamento
    # -> Precisaremos de algo como: agrupar por (Casamento, DataPartida) ou "DataChegada" etc.
    #   e supor que no df final, a 1a linha do group => 'saida', a 2a => 'chegada'.
    #   se quiser a "visão do aeroporto" com 2 voos, etc.
    #   Exemplo simplificado:
    grouped = df.groupby(["Casamento","DataPartida"])
    final_regs = []
    for (cas_key, data_part), group in grouped:
        group_sorted = group.sort_values("HoraPartida")  # se a do 1 = saida e do 2 = chegada
        # etc...
        # Exemplo, se group_sorted.iloc[0] = saida, group_sorted.iloc[1] = chegada
        # e calculamos tempo de solo
        # ...
        # final_regs.append(...)
    # ...
    # df_final = pd.DataFrame(final_regs)
    # df_final.to_csv("malha_final.csv",index=False)

if __name__ == "__main__":
    print("Este snippet não cria app.py. Integre as funções no seu código e chame-as.")
