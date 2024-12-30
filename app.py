import pandas as pd
import re
from datetime import datetime
import streamlit as st

@st.cache_data
def load_support_files():
    """
    Carrega os arquivos de suporte 'iata_airlines.csv' e 'airport.csv' 
    que devem estar presentes no mesmo repositório.
    """
    try:
        df_airlines = pd.read_csv('iata_airlines.csv')
        df_airport = pd.read_csv('airport.csv')
        return df_airlines, df_airport
    except FileNotFoundError as e:
        st.error(f"Erro ao carregar arquivos de suporte: {e}")
        return None, None

def parse_ssim_line(line):
    """
    Parseia uma única linha SSIM do tipo '3' e extrai as informações relevantes.
    """
    if not line.startswith('3 '):
        return None  # Ignorar linhas que não começam com '3 '
    
    # Padrão regex para extrair campos fixos da linha
    pattern = r'^3\s+(\w{2})\s+(\d{8})(\w)\s+(\d{2}[A-Z]{3}\d{2})(\d{2}[A-Z]{3}\d{2})\s+(\d+)\s+(\w{3})(\d{4})([+-]\d{4})\s+(\w{3})(\d{4})([+-]\d{4})\s+(\w+)\s+(\w{2})\s+(\w{2})\s+(\d+)\s+(\d+)$'
    match = re.match(pattern, line)
    if not match:
        return None  # Se a linha não corresponder ao padrão, retornar None
    
    (
        cod_cliente, eight_char_field, status,
        data_partida, data_chegada, frequencia,
        origem, hora_partida, tz_origem,
        destino, hora_chegada, tz_destino,
        equipamento, campo1, campo2,
        campo_casamento, campo_final
    ) = match.groups()
    
    # Extraindo informações do eight_char_field
    numero_voo = eight_char_field[:4]
    date_counter = eight_char_field[4:6]
    etapa = eight_char_field[6:8]
    
    # Identificador que casa dois voos
    casamento_voo = campo_casamento
    
    return {
        'Cód. Cliente': cod_cliente,
        'Voo': numero_voo,
        'Date_Counter': date_counter,
        'Etapa': etapa,
        'Status': status,
        'Data_Partida': data_partida,
        'Data_Chegada': data_chegada,
        'Frequencia': frequencia,
        'Origem': origem,
        'Hora_Partida': hora_partida,
        'Timezone_Origem': tz_origem,
        'Destino': destino,
        'Hora_Chegada': hora_chegada,
        'Timezone_Destino': tz_destino,
        'Equipamento': equipamento,
        'Casamento_Voo': casamento_voo
    }

def gerar_csv_from_ssim(ssim_file_path, output_csv_path, df_airlines, df_airport):
    """
    Lê um arquivo SSIM e gera um CSV na visão de aeroporto, 
    onde cada linha representa 2 voos (chegada + saída).
    """
    # Ler o arquivo SSIM
    with open(ssim_file_path, 'r') as f:
        lines = f.readlines()

    # Parsear as linhas do tipo '3'
    voos = [parse_ssim_line(line.strip()) for line in lines]
    voos = [v for v in voos if v is not None]
    
    if not voos:
        st.error("Nenhuma linha do tipo '3' encontrada no arquivo SSIM.")
        return

    # Converter lista de dicionários em DataFrame
    df_voos = pd.DataFrame(voos)
    
    # Criar dicionários de mapeamento a partir de iata_airlines.csv
    cod_cliente_to_nome = pd.Series(df_airlines['Airline Name'].values, index=df_airlines['IATA Designator']).to_dict()
    cod_cliente_to_icao = pd.Series(df_airlines['ICAO code'].values, index=df_airlines['IATA Designator']).to_dict()

    # Mapeamento de Equipamento → Tipo
    equipamento_to_tipo = {
        '77W': 'B777',
        '73G': 'B738',
        'A320': 'A320',
        'A321': 'A321',
        # Adicione conforme necessário
    }
    
    # Agrupar os voos pelo campo que casa dois voos (Casamento_Voo)
    grouped = df_voos.groupby('Casamento_Voo')
    
    # Lista de registros consolidados
    registros = []
    
    for casamento, grupo in grouped:
        # Ordenar registros por Data_Partida, assumindo que o 1º é saída e o 2º é chegada
        grupo = grupo.sort_values(by='Data_Partida')
        
        registro = {
            'Base': None,
            'Cód. Cliente': None,
            'Nome': None,
            'Data': None,
            'Mod': None,
            'Tipo': None,
            'Voo': None,
            'Hora Chegada': None,
            'Hora Saída': None,
            'ICAO': None,
            'AERONAVE': None
        }
        
        # Variáveis para hora de partida/chegada como datetime
        partida_datetime = None
        chegada_datetime = None
        
        for idx, row in grupo.iterrows():
            # Converter data e hora de partida
            try:
                partida_datetime = datetime.strptime(row['Data_Partida'] + row['Hora_Partida'], "%d%b%y%H%M")
            except:
                partida_datetime = None
            
            # Converter data e hora de chegada
            try:
                chegada_datetime = datetime.strptime(row['Data_Chegada'] + row['Hora_Chegada'], "%d%b%y%H%M")
            except:
                chegada_datetime = None
            
            if registro['Voo'] is None:
                # Primeiro registro (Saída)
                registro['Base'] = row['Origem']  # Aeroporto base → Origem
                registro['Cód. Cliente'] = row['Cód. Cliente']
                registro['Nome'] = cod_cliente_to_nome.get(row['Cód. Cliente'], row['Cód. Cliente'])
                registro['ICAO'] = cod_cliente_to_icao.get(row['Cód. Cliente'], row['Cód. Cliente'])
                registro['Voo'] = row['Voo']
                registro['Data'] = row['Data_Partida']
                # Tipo e Aeronave
                tipo_aeronave = equipamento_to_tipo.get(row['Equipamento'], row['Equipamento'])
                registro['Tipo'] = tipo_aeronave
                registro['AERONAVE'] = tipo_aeronave
                # Hora de Saída
                registro['Hora Saída'] = row['Hora_Partida']
            else:
                # Segundo registro (Chegada)
                registro['Hora Chegada'] = row['Hora_Chegada']
                # Calcular tempo de solo
                if partida_datetime and chegada_datetime:
                    diff_horas = (chegada_datetime - partida_datetime).total_seconds() / 3600
                    if diff_horas > 4:
                        registro['Mod'] = 'PNT'
                    else:
                        registro['Mod'] = 'TST'
                else:
                    # Se não for possível calcular, default para TST
                    registro['Mod'] = 'TST'
        
        # Adicionar o registro consolidado
        registros.append(registro)
    
    # DataFrame final
    df_final = pd.DataFrame(registros)
    # Reordenar colunas
    df_final = df_final[[
        'Base', 'Cód. Cliente', 'Nome', 'Data', 'Mod', 
        'Tipo', 'Voo', 'Hora Chegada', 'Hora Saída', 'ICAO', 'AERONAVE'
    ]]
    
    # Exportar para CSV
    df_final.to_csv(output_csv_path, index=False)
    st.success(f"Arquivo CSV gerado com sucesso: {output_csv_path}")

def main():
    st.title("Conversor SSIM para CSV (Visão de Aeroporto)")
    st.markdown("""
    Este aplicativo converte um arquivo SSIM para um arquivo CSV, onde cada linha 
    representa dois voos (chegada + saída) consolidados na visão de aeroporto.
    """)
    
    # Carregar arquivos de suporte
    df_airlines, df_airport = load_support_files()
    if df_airlines is None or df_airport is None:
        st.stop()

    # Upload do arquivo SSIM
    ssim_file = st.file_uploader("Selecione o arquivo SSIM:", type=['ssim', 'txt'])
    if ssim_file is not None:
        with open("arquivo_ssim.ssim", "wb") as f:
            f.write(ssim_file.getbuffer())
        
        st.write(f"**Arquivo Carregado:** {ssim_file.name}")
        st.write(f"**Tamanho do Arquivo:** {ssim_file.size/1024:.2f} KB")
        
        if st.button("Gerar CSV"):
            try:
                output_csv = "malha_consolidada.csv"
                gerar_csv_from_ssim(
                    ssim_file_path="arquivo_ssim.ssim",
                    output_csv_path=output_csv,
                    df_airlines=df_airlines,
                    df_airport=df_airport
                )
                
                with open(output_csv, 'rb') as f:
                    st.download_button(
                        label="Baixar CSV Consolidado",
                        data=f,
                        file_name=output_csv,
                        mime='text/csv'
                    )
            except Exception as e:
                st.error(f"Ocorreu um erro: {e}")

if __name__ == "__main__":
    main()
