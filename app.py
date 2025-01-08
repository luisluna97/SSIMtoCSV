import streamlit as st

def parse_record_fixed(line: str):
    """
    Exemplo de offsets fixos (200 chars):
    - line[0]  = '3'
    - line[2:4]= CIA (2 chars)
    - line[5:13]= 8-chars (ex "10020801")
    - line[13] = status char (opcional)
    - line[14:21]= dataIni (7 chars, ex "03FEB25")
    - line[21:28]= dataFim (7 chars, ex "28FEB25")
    - line[28:35]= freq (7 chars)
    - line[36:51]= origem+hora (15 chars)
    - line[52:67]= destino+hora (15 chars)
    - line[70:73]= equip (3 chars)
    - line[141:145]= nextVoo (4 chars)
    Ajuste se não bater exatamente com seu SSIM real.
    """

    # Se tiver <200, descarta
    if len(line)<200: 
        return None
    if line[0] != '3':
        return None

    try:
        cia        = line[2:4].strip()     # ex "G3"
        eight_char = line[5:13].strip()    # ex "10020801"
        # status_char= line[13]           # se precisar
        data_ini   = line[14:21].strip()   # "03FEB25"
        data_fim   = line[21:28].strip()   # "28FEB25"
        freq       = line[28:35].strip()   # "1234567"

        orig_blk   = line[36:51].strip()   # 15 chars
        dest_blk   = line[52:67].strip()   # 15 chars

        # pos 68..69 => possiveis espaços? 
        equip      = line[70:73].strip()   # 3 chars
        # se next voo for 141..145
        next_voo   = line[141:145].strip()

        num_voo = eight_char[:4]  # ex "1002"

        def parse_apt(block:str):
            # ex "CGH09000900-0300"
            # assumindo apt=[:3], hora= [3:7]
            if len(block)>=7:
                apt = block[:3]
                hr4= block[3:7]
                return apt, hr4
            return "", ""

        orig, hp = parse_apt(orig_blk)
        dst , hc = parse_apt(dest_blk)

        return {
          "Cia": cia,
          "NumVoo": num_voo,
          "DataIni": data_ini,
          "DataFim": data_fim,
          "Freq": freq,
          "Origem": orig,
          "HoraPartida": hp,
          "Destino": dst,
          "HoraChegada": hc,
          "Equip": equip,
          "NextVoo": next_voo
        }
    except:
        return None

def main():
    st.title("Debug 200-chars SSIM (Primeiras 20 linhas)")

    ssim_file = st.file_uploader("Selecione SSIM (200 chars/linha):", type=["ssim","txt"])
    if ssim_file:
        lines = ssim_file.read().decode("latin-1").splitlines()
        st.write(f"Total lines: {len(lines)}")

        # limit to 20 lines
        debug_limit = 20
        lines_to_debug = lines[:debug_limit]
        debug_rows = []
        for i, line in enumerate(lines_to_debug):
            parsed = parse_record_fixed(line)
            if parsed:
                debug_rows.append({
                    "LineNum": i,
                    **parsed
                })
            else:
                debug_rows.append({
                    "LineNum": i,
                    "ParseError": True,
                    "RawLineSample": line[:50]+"..." if len(line)>50 else line
                })

        st.write(f"### Primeiras {debug_limit} linhas (parse result)")
        st.dataframe(debug_rows)

        st.write("Se 'ParseError' estiver em branco, a parse foi ok. Verifique se 'Equip' e 'NextVoo' etc. sairam certos.")

if __name__=="__main__":
    main()
