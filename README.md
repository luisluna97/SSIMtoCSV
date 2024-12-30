# SSIM Malha - Expansão por Datas e Casamento

Este repositório contém um aplicativo **Streamlit** que lê um arquivo **SSIM** (linhas do tipo `3`), expande as datas de acordo com o período (Data Inicial e Data Final) e a Frequência (quais dias da semana o voo opera). Em seguida, realiza o **casamento** de 2 voos (saída e chegada) na visão do aeroporto.

## Como funciona

1. **Parse** das linhas do tipo `3`: A cada linha, extrai:
   - Datas de Início e Fim (Ex.: `01DEC23` a `08DEC23`)
   - Frequência (Ex.: `5`, `1234567`, etc.)
   - Horários de Origem e Destino
   - Campo de “Casamento” (para unir dois voos em uma única linha final).

2. **Expansão de Datas**: Para cada dia entre a Data Inicial e a Data Final, verifica se o dia da semana está na frequência e gera uma linha real. As datas são formatadas em `dd/mm/yyyy` e as horas em `HH:MM`.

3. **Casamento (Saída + Chegada)**: Agrupa as linhas pelo campo de “Casamento” e pela data, obtendo duas linhas (primeira = saída, segunda = chegada) que se transformam em uma linha final no CSV. Também calcula o tempo de solo (se >4h = `PNT`, senão `TST`).

4. **Resultado**: Gera um arquivo CSV chamado `malha_consolidada.csv`, com as colunas:

