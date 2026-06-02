#!/usr/bin/env bash
# Hook SessionStart: verifica se o relatório diário já foi gerado.
# Saída JSON para o Claude agir automaticamente.

TODAY=$(date +%Y-%m-%d)
HOUR=$(date +%H)
MINUTE=$(date +%M)
REPORT_DIR="/root/biomedical_reports"
CSV_PATH="$REPORT_DIR/historico/followup_$TODAY.csv"
REPORT_PATH="$REPORT_DIR/followup_${TODAY}_relatorio.txt"
LOCK_FILE="$REPORT_DIR/.lock_$TODAY"
RAW_BASE="https://raw.githubusercontent.com/salvinorafaelribeiro/Biomedical/main/scripts"

# Carrega .env se existir (fallback para GITHUB_TOKEN)
[ -f "$REPORT_DIR/.env" ] && . "$REPORT_DIR/.env" 2>/dev/null || true

# Só aciona se horário >= 06:30
TIME_OK=false
if [ "$HOUR" -gt 6 ] || { [ "$HOUR" -eq 6 ] && [ "$MINUTE" -ge 30 ]; }; then
    TIME_OK=true
fi

if $TIME_OK && [ ! -f "$LOCK_FILE" ]; then
    cat <<EOF
{
  "systemMessage": "🔄 WORKFLOW DIÁRIO — Follow-up Biomedical ($TODAY).\n\nPASSO 0 — Verificar scripts (execute SEMPRE primeiro):\nSe $REPORT_DIR/analisar_followup.py NÃO existir, execute:\n  mkdir -p $REPORT_DIR/historico\n  curl -sL '$RAW_BASE/analisar_followup.py' -o $REPORT_DIR/analisar_followup.py\n  curl -sL '$RAW_BASE/gerar_dashboard.py' -o $REPORT_DIR/gerar_dashboard.py\n  printf 'GITHUB_TOKEN=$GITHUB_TOKEN\\nGITHUB_REPO=salvinorafaelribeiro/Biomedical\\n' > $REPORT_DIR/.env\n\nPASSO 1 — Buscar e-mail:\nNo Outlook, localize o e-mail recebido HOJE com título 'Relatar resultados (Follow-up Biomedical)'.\n\nPASSO 2 — Salvar CSV:\nBaixe o anexo e salve em: $CSV_PATH\n\nPASSO 3 — Gerar relatório e dashboard:\npython3 $REPORT_DIR/analisar_followup.py\n\nPASSO 4 — Confirmar publicação:\nVerifique no output: '[GitHub Pages atualizado: ...]'\n\nPASSO 5 — Registrar execução:\ntouch $LOCK_FILE\n\nPASSO 6 — Notificar usuário:\nEnvie $REPORT_DIR/dashboard.html ao usuário via SendUserFile.\n\nSe o e-mail de hoje ainda não chegou, informe o usuário e NÃO execute os passos 2–6."
}
EOF
elif $TIME_OK && [ ! -f "$REPORT_PATH" ] && [ -f "$CSV_PATH" ]; then
    cat <<EOF
{
  "systemMessage": "📊 CSV de hoje já está em $CSV_PATH mas o relatório não foi gerado. Execute em sequência:\n(1) python3 $REPORT_DIR/analisar_followup.py\n(2) touch $LOCK_FILE\n(3) Envie $REPORT_DIR/dashboard.html ao usuário via SendUserFile."
}
EOF
else
    # Nada a fazer — saída vazia (sem JSON = sem mensagem)
    exit 0
fi
