import streamlit as st

def parse_record_fixed(line: str, debug=False):
    """
    Tenta extrair cada campo por offsets fixos. 
    AJUSTE se estiver 'um char pro lado'.

    Exemplo de offsets (você deve alinhar com seu SSIM real):
      line[0]      = '3'
      line[2:4]    = cia (2 chars) -> "G3"
      line[5:13]   = eight_char ("10020101"?)
      line[13]     = status? (desprezamos)
      line[14:21]  = dataIni (7 chars, ex. "03FEB25")
      line[21:28]  = dataFim (7 chars, ex. "28FEB25")
      line[28:35]  = freq (7 chars)
      line[36:51]  = origem+hora (15 chars)
      line[52:67]  = destino+hora(15 chars)
      line[67:70]  = equip (3 chars) 
      line[70]     = espaço?
      line[140:144]= nextVoo (4 chars) 

    Se 'Equip' sai apenas '7' em vez de '7M8', 
      -> Tente line[68:71] ou line[67:70+1]
    Se 'NextVoo' sai '136' em vez de '2136',
      -> Tente line[139:143] etc.
    """

    if len(line) < 200:
        if debug:
            st.write(f"Len <200 => {len(line)}; ignorado =>", repr(line))
        return None
    if line[0] != '3':
        if debug:
            st.write("Primeiro char != '3'; ignorado =>", repr(line[:50]))
        return None

    try:
        # Ajuste de offsets
        cia        = line[2:4].strip()     
        eight_char = line[5:13].strip()    # "10020101"
        data_ini   = line[14:21].strip()   # "03FEB25"
        data_fim   = line[21:28].strip()   # "28FEB25"
        freq       = line[28:35].strip()   # "1234567"

        # 15 chars p/ Origem+Hora
        orig_blk   = line[36:51].strip()  
        # 15 chars p/ Destino+Hora
        dest_blk   = line[52:67].strip()  

        # EXEMPLO: 3 chars p/ equip
        equip      = line[67:70].strip()  
        # 4 chars p/ nextVoo
        next_voo   = line[140:144].strip()

        num_voo = eight_char[:4]  # ex "1002"

        def parse_apt(block:str):
            """
            Se block ex "CGH0900-0300", pegamos apt=[:3], hora=[3:7].
            """
            if len(block)>=7:
                apt = block[:3]
                hhmm= block[3:7]
                return apt, hhmm
            return "", ""

        orig, hp = parse_apt(orig_blk)
        dst , hc = parse_apt(dest_blk)

        record = {
          "cia": cia,
          "num_voo": num_voo,
          "data_ini": data_ini,
          "data_fim": data_fim,
          "freq": freq,
          "origem": orig,
          "hora_part": hp,
          "destino": dst,
          "hora_cheg": hc,
          "equip": equip,
          "next_voo": next_voo
        }
        if debug:
            st.write("DEBUG =>", record)
        return record
    except Exception as e:
        if debug:
            st.write("parse error =>", e, repr(line[:60]))
        return None

def main():
    st.title("Debug Offset - Primeiras 20 linhas")

    debug_mode = st.checkbox("Ativar debug?", value=False)

    ssim_file = st.file_uploader("SSIM (200 chars)", type=["ssim","txt"])
    if ssim_file:
        lines = ssim_file.read().decode("latin-1").splitlines()
        st.write(f"Total lines: {len(lines)}")

        limit=20
        rows=[]
        for i, line in enumerate(lines[:limit]):
            rec = parse_record_fixed(line, debug=debug_mode)
            if rec:
                rec["LineNum"] = i
                rows.append(rec)
            else:
                rows.append({
                    "LineNum": i,
                    "ParseFail?": True,
                    "RawLineSample": line[:60]
                })

        st.write(f"### Primeiras {limit} linhas (parse results)")
        st.dataframe(rows)

        st.write("**Ajuste** as slices no parse_record_fixed() até 'equip' e 'next_voo' fiquem corretos (ex '7M8' e '2136').") 

if __name__=="__main__":
    main()
