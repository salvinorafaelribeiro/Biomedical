# Follow-up Biomedical — Dashboard Diário

Dashboard HTML gerado automaticamente a partir do relatório diário de Follow-up de importações da Biomedical.

## O que é

Workflow automatizado que:
1. Busca o e-mail **"Relatar resultados (Follow-up Biomedical)"** no Outlook a cada dia
2. Baixa o CSV anexado (exportado do Salesforce)
3. Compara com o dia anterior e identifica atrasos, antecipações e mudanças de fase
4. Gera um dashboard HTML e publica aqui via GitHub Pages

## Acesso ao dashboard

🔗 **https://salvinorafaelribeiro.github.io/Biomedical/**

> O dashboard é atualizado automaticamente todos os dias úteis.  
> Se os dados estiverem desatualizados, um aviso laranja aparece no topo da página.

## O que o dashboard mostra

| Seção | Descrição |
|---|---|
| Cards de resumo | Em trânsito, chegando ≤7 dias, necessidade vencida, sem embarque |
| Chegando em até 7 dias | Ordens com previsão de chegada iminente |
| Atrasos do dia | Datas que atrasaram vs. ontem |
| Antecipações do dia | Datas que foram antecipadas vs. ontem |
| Necessidade vencida | Top 20 ordens com necessidade já ultrapassada |
| Pedido enviado sem embarque | Ordens aguardando definição de embarque |
| Resumo por fornecedor | Linhas e unidades por fornecedor |

## Estrutura dos arquivos

```
biomedical_reports/
├── analisar_followup.py     # Script principal de análise
├── gerar_dashboard.py       # Gerador do HTML
├── followup_diario.sh       # Orquestrador do workflow
├── check_session_start.sh   # Hook de inicialização do Claude Code
└── historico/
    └── followup_YYYY-MM-DD.csv   # CSVs diários (Salesforce)
```

## Tecnologia

- **Python 3** — análise e geração do dashboard
- **Claude Code** — agente de automação (busca e-mail, processa CSV, publica)
- **Microsoft 365 MCP** — acesso ao Outlook
- **GitHub Pages** — hospedagem do dashboard
