# Conversor SSIM para Malha de Aeroportos

Este repositório contém um aplicativo **Streamlit** que lê arquivos SSIM, expande datas conforme a Frequência e converte para uma **visão de chegadas** por aeroporto (duplicando cada voo em Chegada/Partida e mostrando apenas as chegadas finais).

## Inspiração

- **[Schiphol-Hub/ssim](https://github.com/Schiphol-Hub/ssim)**  
  Utilizamos princípios de parse robusto de linhas do tipo `3`, com slices em posições fixas e fallback em `split()`, conforme o SSIM oficial.
  
## Como Funciona

1. **Parse Robusto**: Cada linha do SSIM (tipo 3) é extraída com base em posições fixas (se >=200 chars) ou fallback com `split()`.  
2. **Expansão**: De `DataIni` até `DataFim`, filtrando dias da semana pela Frequência (1=Seg, ..., 7=Dom).  
3. **Duplicação C/P**: Cada voo expandido gera 2 linhas:  
   - `CP="P"` (Partida) no aeroporto de origem.  
   - `CP="C"` (Chegada) no aeroporto de destino.  
4. **Conexão**: Para cada chegada que tenha `NextVoo=XXX`, buscamos a partida do voo XXX no mesmo aeroporto e data, calculando tempo de solo.  
5. **Exibindo**: Mostramos somente as chegadas (CP="C"), agrupadas por mês.

## Passos para Executar

1. **Clonar o Repositório**:
   ```bash
   git clone https://github.com/luisluna97/SSIMtoCSV.git
   cd seu-repo
2. ** Acessar Link**:
3. https://ssimtocsv.streamlit.app/
