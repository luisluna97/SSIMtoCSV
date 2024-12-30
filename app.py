import streamlit as st

def debug_inspect_ssim_line(line: str, index: int):
    """
    Exibe (no Streamlit) como a linha se apresenta após remover espaços à esquerda,
    e como fica o split.
    Retorna True se splitted[0] == '3' (provavelmente tipo 3), senão False.
    """
    line_original = line.rstrip('\n')   # remover quebra de linha no final
    line_stripped = line_original.lstrip()  # remove espaços no início

    splitted = line_stripped.split()

    st.write(f"**Linha {index} Original**: {repr(line_original)}")
    st.write(f"**Linha {index} Stripped**: {repr(line_stripped)}")
    st.write(f"**Linha {index} splitted** (len={len(splitted)}): {splitted}")
    st.write("---")

    if len(splitted) > 0 and splitted[0] == "3":
        return True
    return False

def main():
    st.title("Debug: Inspecionando Linhas do Tipo 3 em SSIM")

    st.markdown("""
    Este app vai **exibir** como cada linha do seu arquivo SSIM aparece
    após remover espaços iniciais (`lstrip()`) e fazer `split()`.

    Assim identificamos se as linhas de voo realmente começam com `'3'`
    e em quais campos fica cada pedaço de informação.
    """)

    ssim_file = st.file_uploader("Selecione o arquivo SSIM (sem hifens, com espaços reais):", type=["ssim","txt"])
    if ssim_file is not None:
        # salvar local
        with open("uploaded.ssim","wb") as f:
            f.write(ssim_file.getbuffer())

        st.write(f"**Arquivo Carregado**: {ssim_file.name}")
        st.write(f"**Tamanho**: {ssim_file.size} bytes")

        if st.button("Exibir Debug das Linhas"):
            with open("uploaded.ssim","r", encoding="latin-1") as f:
                lines = f.readlines()

            total_lines = len(lines)
            st.write(f"Total de linhas no arquivo: {total_lines}")

            max_lines_to_show = 300  # limite de quantas linhas exibir p/ não poluir
            recognized_count = 0
            shown_count = 0

            for i, line in enumerate(lines):
                is_type3 = debug_inspect_ssim_line(line, i)
                shown_count += 1
                if is_type3:
                    recognized_count += 1
                if shown_count >= max_lines_to_show:
                    st.write("**Limite de linhas exibidas** (300). Parando por aqui...")
                    break

            st.write(f"Exibidas {shown_count} linhas (máximo {max_lines_to_show}).")
            st.write(f"Linhas reconhecidas como tipo '3': {recognized_count}")

if __name__ == "__main__":
    main()
