#!/usr/bin/env python3
"""
Análise diária de Follow-up Biomedical
Compara CSV de hoje com ontem e gera relatório de alterações de datas.
"""

import csv
import sys
import os
from datetime import datetime, timedelta
from collections import defaultdict

HISTORICO_DIR = os.path.join(os.path.dirname(__file__), "historico")

DATE_COLS = ["Entrega (Fat.) solicitada", "Prev. Prontidão", "Prev. Chegada Embarque", "Prev. Chegada PO", "Necessidade"]
KEY_COLS  = ["Nome da ordem de compra", "Código do produto"]
FASE_COL  = "Fase"

FASES_ATIVAS = {"Em trânsito", "Pedido Enviado", "Pedido no Sistema", "Disponível"}


def parse_date(s):
    s = s.strip()
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def fmt_date(d):
    return d.strftime("%d/%m/%Y") if d else "—"


def load_csv(path):
    rows = {}
    for enc in ("latin-1", "utf-8-sig", "cp1252"):
        try:
            with open(path, encoding=enc) as f:
                reader = csv.DictReader(f, delimiter=";")
                for row in reader:
                    key = tuple(row.get(c, "").strip() for c in KEY_COLS)
                    rows[key] = row
            if rows:
                return rows
        except (UnicodeDecodeError, KeyError):
            rows = {}
    return rows


def delta_days(old_d, new_d):
    if old_d and new_d:
        return (new_d - old_d).days
    return None


def analyze(today_path, yesterday_path=None):
    today_rows = load_csv(today_path)
    ontem_rows = load_csv(yesterday_path) if yesterday_path else {}

    today_str  = os.path.basename(today_path).replace("followup_", "").replace(".csv", "")

    changes_delay  = []  # data adiada
    changes_accel  = []  # data antecipada
    new_orders     = []  # ordens novas
    closed_orders  = []  # ordens que saíram
    fase_changes   = []  # mudança de fase

    # --- Comparação com ontem ---
    if ontem_rows:
        all_keys = set(today_rows) | set(ontem_rows)
        for key in all_keys:
            oc, cod = key
            if key not in ontem_rows:
                new_orders.append(today_rows[key])
                continue
            if key not in today_rows:
                closed_orders.append(ontem_rows[key])
                continue

            t = today_rows[key]
            o = ontem_rows[key]

            # Fase
            if t.get(FASE_COL, "").strip() != o.get(FASE_COL, "").strip():
                fase_changes.append({
                    "OC": oc, "Produto": t.get("Nome do produto", "").strip(),
                    "De": o.get(FASE_COL, ""), "Para": t.get(FASE_COL, "")
                })

            # Datas
            for col in DATE_COLS:
                d_old = parse_date(o.get(col, ""))
                d_new = parse_date(t.get(col, ""))
                if d_old == d_new:
                    continue
                delta = delta_days(d_old, d_new)
                entry = {
                    "OC": oc, "Fornecedor": t.get("Fornecedor", "").strip(),
                    "Produto": t.get("Nome do produto", "").strip()[:55],
                    "Família": t.get("Família de produtos", "").strip(),
                    "Campo": col, "Anterior": fmt_date(d_old), "Nova": fmt_date(d_new),
                    "Delta": delta
                }
                if delta and delta > 0:
                    changes_delay.append(entry)
                elif delta and delta < 0:
                    changes_accel.append(entry)

        changes_delay.sort(key=lambda x: x["Delta"] or 0, reverse=True)
        changes_accel.sort(key=lambda x: x["Delta"] or 0)

    # --- Análise de situação atual (independente de comparação) ---
    today_date = datetime.today().date()

    overdue     = []
    arriving_7d = []
    no_shipment = []
    in_transit  = []

    for key, row in today_rows.items():
        fase = row.get(FASE_COL, "").strip()
        necessidade = parse_date(row.get("Necessidade", ""))
        chegada_po  = parse_date(row.get("Prev. Chegada PO", ""))
        embarque    = row.get("Embarque", "").strip()
        nome_prod   = row.get("Nome do produto", "").strip()[:55]
        oc          = row.get("Nome da ordem de compra", "").strip()
        fornecedor  = row.get("Fornecedor", "").strip()
        familia     = row.get("Família de produtos", "").strip()
        qtde        = row.get("QTDE", "").strip()

        base = {"OC": oc, "Fornecedor": fornecedor, "Produto": nome_prod,
                "Família": familia, "QTDE": qtde, "Fase": fase}

        # Chegando em até 7 dias
        if chegada_po and 0 <= (chegada_po - today_date).days <= 7:
            arriving_7d.append({**base, "Chegada PO": fmt_date(chegada_po),
                                 "Dias": (chegada_po - today_date).days})

        # Necessidade vencida sem chegada confirmada
        if necessidade and necessidade < today_date and fase in FASES_ATIVAS:
            atraso = (today_date - necessidade).days
            overdue.append({**base, "Necessidade": fmt_date(necessidade),
                            "Chegada PO": fmt_date(chegada_po), "Atraso (dias)": atraso})

        # Sem embarque definido e já enviado
        if fase == "Pedido Enviado" and not embarque:
            no_shipment.append({**base, "Necessidade": fmt_date(necessidade)})

        if fase == "Em trânsito":
            in_transit.append({**base, "Chegada PO": fmt_date(chegada_po)})

    overdue.sort(key=lambda x: x["Atraso (dias)"], reverse=True)
    arriving_7d.sort(key=lambda x: x["Dias"])

    # --- Monta relatório em texto ---
    sep = "=" * 72
    lines = [
        sep,
        f"  FOLLOW-UP BIOMEDICAL — RELATÓRIO DIÁRIO",
        f"  Gerado em: {today_str}  |  Total de registros: {len(today_rows)}",
        sep,
    ]

    # Bloco de comparação
    if ontem_rows:
        lines += ["", f"{'─'*72}", "  ALTERAÇÕES EM RELAÇÃO A ONTEM", f"{'─'*72}"]

        if changes_delay:
            lines += [f"\n⚠️  ATRASOS ({len(changes_delay)} itens):"]
            for c in changes_delay:
                lines.append(f"  [{c['OC']}] {c['Produto']}")
                lines.append(f"    {c['Campo']}: {c['Anterior']} → {c['Nova']}  (+{c['Delta']} dias)")
        else:
            lines.append("\n✅  Sem novos atrasos.")

        if changes_accel:
            lines += [f"\n🚀  ANTECIPAÇÕES ({len(changes_accel)} itens):"]
            for c in changes_accel:
                lines.append(f"  [{c['OC']}] {c['Produto']}")
                lines.append(f"    {c['Campo']}: {c['Anterior']} → {c['Nova']}  ({c['Delta']} dias)")

        if fase_changes:
            lines += [f"\n🔄  MUDANÇAS DE FASE ({len(fase_changes)} itens):"]
            for f in fase_changes:
                lines.append(f"  [{f['OC']}] {f['Produto']}: {f['De']} → {f['Para']}")

        if new_orders:
            lines += [f"\n🆕  NOVAS ORDENS ({len(new_orders)}):"]
            for r in new_orders:
                lines.append(f"  [{r.get('Nome da ordem de compra','')}] {r.get('Nome do produto','')[:55]}")

        if closed_orders:
            lines += [f"\n✔️  ORDENS ENCERRADAS/REMOVIDAS ({len(closed_orders)}):"]
            for r in closed_orders:
                lines.append(f"  [{r.get('Nome da ordem de compra','')}] {r.get('Nome do produto','')[:55]}")
    else:
        lines.append("\n  (Primeira execução — sem relatório anterior para comparação)")

    # Bloco de situação atual
    lines += ["", f"{'─'*72}", "  SITUAÇÃO ATUAL", f"{'─'*72}"]

    lines += [f"\n📦  EM TRÂNSITO: {len(in_transit)} linhas"]

    if arriving_7d:
        lines += [f"\n📬  CHEGANDO EM ATÉ 7 DIAS ({len(arriving_7d)}):"]
        for r in arriving_7d:
            label = "HOJE" if r["Dias"] == 0 else f"em {r['Dias']}d"
            lines.append(f"  [{r['OC']}] {r['Produto']} — {r['Chegada PO']} ({label})")

    if overdue:
        lines += [f"\n🔴  NECESSIDADE VENCIDA — SEM CHEGADA ({len(overdue)}):"]
        for r in overdue[:15]:  # top 15
            lines.append(f"  [{r['OC']}] {r['Produto']}")
            lines.append(f"    Necessidade: {r['Necessidade']} | Chegada PO: {r['Chegada PO']} | Atraso: {r['Atraso (dias)']} dias")
        if len(overdue) > 15:
            lines.append(f"  ... e mais {len(overdue)-15} itens")

    if no_shipment:
        lines += [f"\n⚡  PEDIDO ENVIADO SEM EMBARQUE DEFINIDO ({len(no_shipment)}):"]
        for r in no_shipment[:10]:
            lines.append(f"  [{r['OC']}] {r['Produto']} — Necessidade: {r['Necessidade']}")
        if len(no_shipment) > 10:
            lines.append(f"  ... e mais {len(no_shipment)-10} itens")

    # Resumo por fornecedor
    forn_count = defaultdict(int)
    forn_qtde  = defaultdict(int)
    for row in today_rows.values():
        f = row.get("Fornecedor", "").strip()
        try:
            q = int(float(row.get("QTDE", "0").replace(",", ".")))
        except:
            q = 0
        forn_count[f] += 1
        forn_qtde[f]  += q

    lines += [f"\n{'─'*72}", "  RESUMO POR FORNECEDOR", f"{'─'*72}"]
    for forn in sorted(forn_count, key=lambda x: forn_count[x], reverse=True):
        lines.append(f"  {forn:<45} {forn_count[forn]:>4} linhas   {forn_qtde[forn]:>10,} unid.")

    lines += ["", sep, ""]
    return "\n".join(lines)


def generate_dashboard(today_path, yesterday_path=None):
    try:
        import importlib.util, pathlib
        spec = importlib.util.spec_from_file_location(
            "gerar_dashboard",
            pathlib.Path(__file__).parent / "gerar_dashboard.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.build_dashboard(today_path, yesterday_path)
    except Exception as e:
        print(f"[Dashboard não gerado: {e}]")


def publish_to_github(dashboard_path):
    import base64, urllib.request, urllib.error, json as _json

    env_path = os.path.join(os.path.dirname(__file__), ".env")
    token, repo = "", ""
    if os.path.exists(env_path):
        for line in open(env_path):
            k, _, v = line.strip().partition("=")
            if k == "GITHUB_TOKEN": token = v
            if k == "GITHUB_REPO":  repo  = v

    token = token or os.environ.get("GITHUB_TOKEN", "")
    repo  = repo  or os.environ.get("GITHUB_REPO",  "")

    if not token or not repo:
        print("[GitHub Pages: token ou repo não configurados — pulando publicação]")
        return

    with open(dashboard_path, "rb") as f:
        content = base64.b64encode(f.read()).decode()

    api = f"https://api.github.com/repos/{repo}/contents/index.html"
    headers = {"Authorization": f"token {token}", "Content-Type": "application/json"}

    # Busca SHA atual (necessário para update)
    sha = ""
    try:
        req = urllib.request.Request(f"{api}?ref=gh-pages", headers=headers)
        with urllib.request.urlopen(req) as r:
            sha = _json.load(r).get("sha", "")
    except urllib.error.HTTPError:
        pass

    today_str = os.path.basename(dashboard_path).replace("dashboard_", "").replace(".html", "") or \
                datetime.today().strftime("%Y-%m-%d")
    payload = {"message": f"Dashboard {today_str}", "content": content, "branch": "gh-pages"}
    if sha:
        payload["sha"] = sha

    data = _json.dumps(payload).encode()
    req = urllib.request.Request(api, data=data, headers=headers, method="PUT")
    try:
        with urllib.request.urlopen(req) as r:
            result = _json.load(r)
            commit = result.get("commit", {}).get("sha", "")[:12]
            print(f"[GitHub Pages atualizado: https://{repo.split('/')[0]}.github.io/{repo.split('/')[1]}/ | commit {commit}]")
    except urllib.error.HTTPError as e:
        print(f"[GitHub Pages erro {e.code}: {e.read().decode()[:200]}]")


def find_yesterday_csv(today_path):
    today_str = os.path.basename(today_path).replace("followup_", "").replace(".csv", "")
    try:
        today_date = datetime.strptime(today_str, "%Y-%m-%d").date()
    except ValueError:
        return None
    yesterday = today_date - timedelta(days=1)
    path = os.path.join(HISTORICO_DIR, f"followup_{yesterday}.csv")
    return path if os.path.exists(path) else None


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # Detecta o CSV mais recente no histórico
        csvs = sorted(
            [f for f in os.listdir(HISTORICO_DIR) if f.startswith("followup_") and f.endswith(".csv")]
        )
        if not csvs:
            print("Nenhum CSV encontrado em", HISTORICO_DIR)
            sys.exit(1)
        today_path = os.path.join(HISTORICO_DIR, csvs[-1])
    else:
        today_path = sys.argv[1]

    yesterday_path = find_yesterday_csv(today_path) if len(sys.argv) < 3 else sys.argv[2]

    report = analyze(today_path, yesterday_path)
    print(report)

    # Salva relatório em arquivo
    out_name = os.path.basename(today_path).replace(".csv", "_relatorio.txt")
    out_path = os.path.join(os.path.dirname(today_path), "..", out_name)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"[Relatório salvo em: {os.path.abspath(out_path)}]")

    # Gera dashboard HTML
    generate_dashboard(today_path, yesterday_path)

    # Publica no GitHub Pages
    dashboard_path = os.path.join(os.path.dirname(__file__), "dashboard.html")
    if os.path.exists(dashboard_path):
        publish_to_github(dashboard_path)
