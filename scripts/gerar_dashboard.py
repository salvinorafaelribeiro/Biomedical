#!/usr/bin/env python3
"""
Gera dashboard HTML do Follow-up Biomedical.
Chamado automaticamente após analisar_followup.py.
"""

import csv
import json as _json
import os
import sys
from datetime import datetime, date, timedelta
from collections import defaultdict

HISTORICO_DIR = os.path.join(os.path.dirname(__file__), "historico")
DASHBOARD_PATH = os.path.join(os.path.dirname(__file__), "dashboard.html")


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
    return d.strftime("%d/%m/%Y") if d else ""


def load_csv(path):
    rows = []
    for enc in ("latin-1", "utf-8-sig", "cp1252"):
        try:
            with open(path, encoding=enc) as f:
                reader = csv.DictReader(f, delimiter=";")
                rows = list(reader)
            if rows:
                return rows
        except (UnicodeDecodeError, KeyError):
            rows = []
    return rows


def build_dashboard(today_path, yesterday_path=None):
    today_rows = load_csv(today_path)
    ontem_rows = {(r.get("Nome da ordem de compra", "").strip(),
                   r.get("Código do produto", "").strip()): r
                  for r in load_csv(yesterday_path)} if yesterday_path else {}

    today_date = date.today()
    today_str  = os.path.basename(today_path).replace("followup_", "").replace(".csv", "")
    try:
        today_display = datetime.strptime(today_str, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        today_display = today_str

    total       = len(today_rows)
    em_transito = sum(1 for r in today_rows if r.get("Fase", "").strip() == "Em trânsito")

    arriving, overdue, fat_overdue, no_ship, delays, accels = [], [], [], [], [], []
    _fases_ativas = {"Em trânsito", "Pedido Enviado", "Pedido no Sistema", "Disponível"}

    for row in today_rows:
        oc       = row.get("Nome da ordem de compra", "").strip()
        cod      = row.get("Código do produto", "").strip()
        fase     = row.get("Fase", "").strip()
        prod     = row.get("Nome do produto", "").strip()[:60]
        forn     = row.get("Fornecedor", "").strip()
        familia  = row.get("Família de produtos", "").strip()
        nec      = parse_date(row.get("Necessidade", ""))
        chegada  = parse_date(row.get("Prev. Chegada PO", ""))
        fat_date = parse_date(row.get("Entrega (Fat.) solicitada", ""))
        embarque = row.get("Embarque", "").strip()

        if chegada and 0 <= (chegada - today_date).days <= 7:
            arriving.append({"OC": oc, "Produto": prod, "Fornecedor": forn,
                             "Chegada": fmt_date(chegada),
                             "Dias": (chegada - today_date).days, "Fase": fase,
                             "Familia": familia})

        if nec and nec < today_date and fase in _fases_ativas:
            overdue.append({"OC": oc, "Produto": prod, "Fornecedor": forn,
                            "Necessidade": fmt_date(nec), "ChegadaPO": fmt_date(chegada),
                            "Atraso": (today_date - nec).days, "Familia": familia, "Fase": fase})

        if fat_date and fat_date < today_date and fase in _fases_ativas:
            fat_overdue.append({"OC": oc, "Produto": prod, "Fornecedor": forn,
                                "FatSolicitada": fmt_date(fat_date),
                                "ChegadaPO": fmt_date(chegada),
                                "Necessidade": fmt_date(nec),
                                "Atraso": (today_date - fat_date).days,
                                "Familia": familia, "Fase": fase})

        if fase == "Pedido Enviado" and not embarque:
            no_ship.append({"OC": oc, "Produto": prod, "Fornecedor": forn,
                            "Necessidade": fmt_date(nec), "Familia": familia})

        key = (oc, cod)
        if key in ontem_rows:
            for col in ["Prev. Chegada PO", "Prev. Chegada Embarque", "Entrega (Fat.) solicitada"]:
                d_old = parse_date(ontem_rows[key].get(col, ""))
                d_new = parse_date(row.get(col, ""))
                if d_old and d_new and d_old != d_new:
                    delta = (d_new - d_old).days
                    entry = {"OC": oc, "Produto": prod, "Fornecedor": forn,
                             "Campo": col.replace("Prev. ", ""), "Familia": familia,
                             "Anterior": fmt_date(d_old), "Nova": fmt_date(d_new), "Delta": delta}
                    (delays if delta > 0 else accels).append(entry)

    overdue.sort(key=lambda x: x["Atraso"], reverse=True)
    fat_overdue.sort(key=lambda x: x["Atraso"], reverse=True)
    arriving.sort(key=lambda x: x["Dias"])
    delays.sort(key=lambda x: x["Delta"], reverse=True)

    forn_stats = defaultdict(lambda: {"linhas": 0, "qtde": 0})
    for row in today_rows:
        f = row.get("Fornecedor", "").strip()
        try:
            q = int(float(row.get("QTDE", "0").replace(",", ".")))
        except Exception:
            q = 0
        forn_stats[f]["linhas"] += 1
        forn_stats[f]["qtde"]   += q
    forn_list = sorted(forn_stats.items(), key=lambda x: x[1]["linhas"], reverse=True)

    all_fases    = sorted(set(r.get("Fase", "").strip() for r in today_rows if r.get("Fase", "").strip()))
    all_familias = sorted(set(r.get("Família de produtos", "").strip() for r in today_rows
                              if r.get("Família de produtos", "").strip()))

    data_payload = {
        "arriving":    arriving,
        "overdue":     overdue,
        "fat_overdue": fat_overdue,
        "no_ship":     no_ship,
        "delays":      delays,
        "accels":      accels,
        "forn":        [{"name": k, "linhas": v["linhas"], "qtde": v["qtde"]} for k, v in forn_list],
        "fases":       all_fases,
        "familias":    all_familias,
        "fornecedores":[k for k, _ in forn_list],
        "meta": {
            "total":        total,
            "em_transito":  em_transito,
            "today_str":    today_str,
            "today_display":today_display,
            "has_yesterday":bool(ontem_rows),
        }
    }
    data_json = _json.dumps(data_payload, ensure_ascii=False)

    def kpi(icon, label, kid, sub, color):
        return (f'<div class="kpi-card {color}">'
                f'<div class="kpi-icon">{icon}</div>'
                f'<div class="kpi-label">{label}</div>'
                f'<div class="kpi-value" id="kpi-{kid}">—</div>'
                f'<div class="kpi-sub">{sub}</div></div>')

    vs = "vs ontem" if ontem_rows else "1ª execução"
    kpis_html = (
        kpi("🚢", "Em Trânsito",        "transito", "embarques ativos",   "blue")  +
        kpi("📬", "Chegando ≤ 7 dias",  "arriving", "ordens previstas",   "green") +
        kpi("🔴", "Necessidade Vencida","overdue",  "necessidade passou", "red")   +
        kpi("💰", "Fat. Vencido",        "fat",      "entrega solicitada", "amber") +
        kpi("⚡", "Sem Embarque",        "noship",   "pedido enviado",     "amber") +
        kpi("⏰", "Atrasos Hoje",        "delays",   vs,                   "red")   +
        kpi("🚀", "Antecipações",        "accels",   vs,                   "green")
    )

    # ── CSS ───────────────────────────────────────────────────────────────────
    CSS = """
:root{
  --bg:#F0F4F8;--surface:#fff;--border:#E2E8F0;
  --txt:#0F172A;--txt2:#64748B;--txt3:#94A3B8;
  --navy:#0B1E3E;--navy2:#1A3660;
  --blue:#2563EB;--blue-l:#EFF6FF;
  --green:#059669;--green-l:#ECFDF5;
  --red:#DC2626;--red-l:#FEF2F2;
  --amber:#D97706;--amber-l:#FFFBEB;
  --r:10px;
  --s1:0 1px 3px rgba(0,0,0,.06),0 1px 2px rgba(0,0,0,.04);
  --s2:0 4px 12px rgba(0,0,0,.08),0 2px 4px rgba(0,0,0,.04);
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Inter',system-ui,sans-serif;background:var(--bg);color:var(--txt);font-size:13.5px;line-height:1.5}

/* Stale banner */
#stale-banner{display:none;background:linear-gradient(135deg,#F59E0B,#B45309);color:#fff;
  text-align:center;padding:11px 20px;font-weight:600;font-size:13px}

/* Header */
header{background:linear-gradient(135deg,var(--navy) 0%,var(--navy2) 100%);
  position:sticky;top:0;z-index:100;box-shadow:0 2px 12px rgba(0,0,0,.25)}
.hdr{display:flex;align-items:center;padding:16px 32px;gap:16px}
.hdr-icon{width:42px;height:42px;background:rgba(255,255,255,.1);border-radius:10px;
  display:flex;align-items:center;justify-content:center;font-size:20px;flex-shrink:0}
.hdr-title{font-size:17px;font-weight:700;color:#fff;letter-spacing:-.3px}
.hdr-sub{font-size:11.5px;color:rgba(255,255,255,.45);margin-top:1px}
.hdr-meta{margin-left:auto;text-align:right}
.hdr-date{font-size:13px;font-weight:600;color:rgba(255,255,255,.9)}
.hdr-count{font-size:11px;color:rgba(255,255,255,.45);margin-top:2px}
nav{background:rgba(0,0,0,.15);border-top:1px solid rgba(255,255,255,.06);
  padding:0 28px;display:flex;gap:2px;overflow-x:auto}
nav a{color:rgba(255,255,255,.55);text-decoration:none;font-size:12px;font-weight:500;
  padding:9px 14px;border-bottom:2px solid transparent;white-space:nowrap;
  transition:color .15s,border-color .15s}
nav a:hover{color:#fff;border-bottom-color:rgba(255,255,255,.4)}

/* Main */
main{max-width:1380px;margin:0 auto;padding:24px 32px}

/* KPI grid */
.kpi-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:14px;margin-bottom:20px}
@media(max-width:1200px){.kpi-grid{grid-template-columns:repeat(4,1fr)}}
@media(max-width:700px){.kpi-grid{grid-template-columns:repeat(2,1fr)}}
.kpi-card{background:var(--surface);border-radius:var(--r);padding:18px 18px 14px;
  box-shadow:var(--s1);border-top:3px solid transparent;position:relative;overflow:hidden;
  transition:transform .15s,box-shadow .15s;cursor:default}
.kpi-card:hover{transform:translateY(-2px);box-shadow:var(--s2)}
.kpi-card.blue{border-top-color:var(--blue)}.kpi-card.green{border-top-color:var(--green)}
.kpi-card.red{border-top-color:var(--red)}.kpi-card.amber{border-top-color:var(--amber)}
.kpi-icon{position:absolute;top:12px;right:14px;font-size:28px;opacity:.12;
  transform:rotate(-10deg) scale(1.5);pointer-events:none}
.kpi-label{font-size:10.5px;font-weight:600;text-transform:uppercase;letter-spacing:.7px;
  color:var(--txt2);margin-bottom:8px}
.kpi-value{font-size:36px;font-weight:800;line-height:1;letter-spacing:-1.5px}
.kpi-card.blue .kpi-value{color:var(--blue)}.kpi-card.green .kpi-value{color:var(--green)}
.kpi-card.red .kpi-value{color:var(--red)}.kpi-card.amber .kpi-value{color:var(--amber)}
.kpi-sub{font-size:11px;color:var(--txt3);margin-top:5px}

/* Filter bar */
.filter-bar{background:var(--surface);border-radius:var(--r);box-shadow:var(--s1);
  padding:16px 20px;margin-bottom:20px}
.fb-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.fb-row+.fb-row{margin-top:10px}
.fb-search{position:relative;flex:1;min-width:200px}
.fb-search input{width:100%;padding:8px 12px 8px 36px;border:1.5px solid var(--border);
  border-radius:8px;font-size:13px;font-family:inherit;outline:none;
  transition:border-color .15s;background:#FAFAFA;color:var(--txt)}
.fb-search input:focus{border-color:var(--blue);background:#fff}
.fb-search::before{content:'🔍';position:absolute;left:10px;top:50%;
  transform:translateY(-50%);font-size:13px;pointer-events:none;opacity:.45}
.fb-label{font-size:12px;font-weight:500;color:var(--txt2);white-space:nowrap;flex-shrink:0}
.fb-atraso{display:flex;align-items:center;gap:8px}
.fb-atraso label{font-size:12px;color:var(--txt2);white-space:nowrap}
#f-atraso{width:110px;accent-color:var(--blue);cursor:pointer}
#atraso-lbl{font-weight:700;color:var(--blue);min-width:30px}
.fase-pills{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.fase-pill{padding:5px 14px;border-radius:20px;border:1.5px solid var(--border);
  background:transparent;font-size:12px;font-family:inherit;color:var(--txt2);
  cursor:pointer;transition:all .15s;white-space:nowrap}
.fase-pill:hover{border-color:var(--blue);color:var(--blue)}
.fase-pill.active{background:var(--blue);border-color:var(--blue);color:#fff}
.btn-clear{padding:7px 14px;border-radius:8px;border:1.5px solid var(--border);
  background:transparent;font-size:12px;font-family:inherit;color:var(--txt3);
  cursor:pointer;transition:all .15s;white-space:nowrap;flex-shrink:0}
.btn-clear:hover,.btn-clear.hot{border-color:var(--red);color:var(--red);background:var(--red-l)}
#filter-status{margin-top:10px;display:none;align-items:center;gap:6px;flex-wrap:wrap;
  font-size:12px;color:var(--txt2)}
.af-tag{background:var(--blue-l);color:var(--blue);padding:2px 10px;
  border-radius:12px;font-weight:500;font-size:11.5px}

/* Preset buttons */
.preset-pills{display:flex;gap:6px;flex-wrap:wrap}
.preset-btn{padding:5px 14px;border-radius:20px;border:1.5px solid var(--border);
  background:transparent;font-size:12px;font-family:inherit;color:var(--txt2);
  cursor:pointer;transition:all .15s;white-space:nowrap}
.preset-btn:hover{border-color:var(--blue);color:var(--blue);background:var(--blue-l)}
.preset-btn.active[data-preset="critico"]{background:var(--red-l);color:var(--red);border-color:var(--red)}
.preset-btn.active[data-preset="atencao"]{background:var(--amber-l);color:var(--amber);border-color:var(--amber)}
.preset-btn.active[data-preset="transito"]{background:var(--blue-l);color:var(--blue);border-color:var(--blue)}
.preset-btn.active[data-preset="enviado"]{background:var(--amber-l);color:var(--amber);border-color:var(--amber)}

/* Multi-select */
.ms-wrap{position:relative}
.ms-btn{display:flex;align-items:center;gap:8px;padding:8px 12px;border:1.5px solid var(--border);
  border-radius:8px;font-size:12.5px;font-family:inherit;color:var(--txt);background:#FAFAFA;
  cursor:pointer;transition:all .15s;white-space:nowrap;min-width:150px}
.ms-btn:hover,.ms-btn.active{border-color:var(--blue);color:var(--blue)}
.ms-btn.active{background:var(--blue-l)}
.ms-arrow{font-size:10px;color:var(--txt3);margin-left:auto}
.ms-dd{position:absolute;top:calc(100% + 4px);left:0;min-width:230px;
  background:var(--surface);border:1.5px solid var(--border);border-radius:10px;
  box-shadow:var(--s2);z-index:200;padding:6px 0;display:none;max-height:300px;overflow-y:auto}
.ms-si{padding:8px 12px;border-bottom:1px solid var(--border);position:sticky;top:0;background:#fff}
.ms-si input{width:100%;padding:6px 10px;border:1.5px solid var(--border);border-radius:6px;
  font-size:12px;font-family:inherit;outline:none;background:#FAFAFA}
.ms-si input:focus{border-color:var(--blue)}
.ms-opt{display:flex;align-items:center;gap:9px;padding:8px 14px;cursor:pointer;font-size:13px}
.ms-opt:hover{background:#F8FAFC}
.ms-opt input{accent-color:var(--blue);cursor:pointer;flex-shrink:0;width:15px;height:15px}
.ms-div{height:1px;background:var(--border);margin:4px 0}

/* Sections */
.section{background:var(--surface);border-radius:var(--r);box-shadow:var(--s1);margin-bottom:20px;overflow:hidden}
.sec-hdr{display:flex;align-items:center;gap:10px;padding:14px 20px;border-bottom:1px solid var(--border)}
.sec-icon{font-size:16px}
.sec-title{font-size:14px;font-weight:600}
.sec-badge{margin-left:auto;font-size:11px;font-weight:600;padding:3px 11px;border-radius:20px}
.sec-badge.blue{background:var(--blue-l);color:var(--blue)}
.sec-badge.green{background:var(--green-l);color:var(--green)}
.sec-badge.red{background:var(--red-l);color:var(--red)}
.sec-badge.amber{background:var(--amber-l);color:var(--amber)}
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px}
.grid-2 .section{margin-bottom:0}
@media(max-width:860px){.grid-2{grid-template-columns:1fr}}

/* Tables */
.table-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse}
thead th{background:#F8FAFC;padding:10px 16px;text-align:left;font-size:11px;
  font-weight:600;text-transform:uppercase;letter-spacing:.5px;color:var(--txt2);
  border-bottom:1px solid var(--border);white-space:nowrap;position:sticky;top:0;z-index:1}
thead th.sortable{cursor:pointer;user-select:none}
thead th.sortable:hover{background:#EEF2F7;color:var(--txt)}
thead th.sort-asc,thead th.sort-desc{color:var(--blue);background:#EEF6FF}
.sort-icon{font-size:10px;margin-left:4px;opacity:.5}
thead th.sort-asc .sort-icon,thead th.sort-desc .sort-icon{opacity:1;color:var(--blue)}
tbody td{padding:10px 16px;border-bottom:1px solid #F8FAFC;vertical-align:middle}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover td{background:#F8FAFC}
td.mono{font-family:'SFMono-Regular',Consolas,monospace;font-size:12px;color:var(--txt2)}
td.bold{font-weight:600}
td.dim{color:var(--txt2);font-size:12.5px}

/* Badges */
.badge{display:inline-flex;align-items:center;padding:3px 10px;border-radius:20px;
  font-size:11px;font-weight:600;white-space:nowrap}
.badge-blue{background:var(--blue-l);color:var(--blue)}
.badge-green{background:var(--green-l);color:var(--green)}
.badge-red{background:var(--red-l);color:var(--red)}
.badge-amber{background:var(--amber-l);color:var(--amber)}
.badge-solid-green{background:var(--green);color:#fff}
.badge-solid-red{background:var(--red);color:#fff}
.badge-solid-blue{background:var(--blue);color:#fff}

/* Phase pills */
.phase{display:inline-flex;align-items:center;gap:5px;padding:3px 10px;
  border-radius:20px;font-size:11px;font-weight:500}
.phase::before{content:'';width:6px;height:6px;border-radius:50%;background:currentColor;opacity:.7}
.phase-transito{background:#EFF6FF;color:#2563EB}
.phase-enviado{background:#FFFBEB;color:#D97706}
.phase-sistema{background:#F5F3FF;color:#7C3AED}
.phase-disponivel{background:#ECFDF5;color:#059669}

/* Empty state */
.empty-state{padding:40px 20px;text-align:center}
.empty-icon{font-size:30px;margin-bottom:8px;opacity:.4}
.empty-text{font-size:13px;font-style:italic;color:var(--txt3)}

/* Truncate note */
.truncate-note{padding:10px 20px;font-size:12px;color:var(--txt3);
  border-top:1px solid var(--border);background:#FAFAFA}

/* Forn chart */
.forn-row{display:flex;align-items:center;padding:12px 20px;
  border-bottom:1px solid #F8FAFC;gap:16px}
.forn-row:last-child{border-bottom:none}
.forn-row:hover{background:#F8FAFC}
.forn-name{width:220px;flex-shrink:0;font-size:13px;font-weight:500;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.forn-bars{flex:1;display:flex;flex-direction:column;gap:5px}
.bar-row{display:flex;align-items:center;gap:10px}
.bar-lbl{font-size:10px;color:var(--txt3);width:38px;text-align:right;flex-shrink:0}
.bar-track{flex:1;height:6px;background:var(--border);border-radius:3px;overflow:hidden}
.bar-fill{height:100%;border-radius:3px;transition:width .8s cubic-bezier(.16,1,.3,1)}
.bar-fill.blue{background:var(--blue)}.bar-fill.green{background:var(--green)}
.bar-val{font-size:12px;font-weight:600;width:80px;text-align:right;flex-shrink:0}
.bar-val.blue{color:var(--blue)}.bar-val.green{color:var(--green)}

/* Footer */
footer{text-align:center;padding:22px;font-size:11.5px;color:var(--txt3);
  border-top:1px solid var(--border);margin-top:8px}

/* Animations */
@keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
.kpi-card,.section,.filter-bar{animation:fadeUp .35s ease both}
.kpi-card:nth-child(1){animation-delay:.04s}.kpi-card:nth-child(2){animation-delay:.08s}
.kpi-card:nth-child(3){animation-delay:.12s}.kpi-card:nth-child(4){animation-delay:.16s}
.kpi-card:nth-child(5){animation-delay:.20s}.kpi-card:nth-child(6){animation-delay:.24s}
.kpi-card:nth-child(7){animation-delay:.28s}
"""

    # ── JavaScript ────────────────────────────────────────────────────────────
    JS = r"""
const DATA = __DATA_JSON__;

// ── State ─────────────────────────────────────────────────────────────────
const S = {search:'', forns:new Set(), familias:new Set(), fase:'',
           atraso:0, atraso_max:9999, preset:''};
const SORT = {};

// ── Helpers ───────────────────────────────────────────────────────────────
const esc = s => String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

function badge(t,cls){return `<span class="badge badge-${cls}">${esc(t)}</span>`}

function phaseBadge(f){
  const m={'Em trânsito':'transito','Pedido Enviado':'enviado',
           'Pedido no Sistema':'sistema','Disponível':'disponivel'};
  const c=m[f]||'';
  return c?`<span class="phase phase-${c}">${esc(f)}</span>`:esc(f);
}

function arrivingBadge(d){
  return d===0?badge('HOJE','solid-green'):d<=3?badge(`em ${d}d`,'solid-blue'):badge(`em ${d}d`,'blue');
}

function overdueBadge(d){
  return d>60?badge(d+'d','solid-red'):d>30?badge(d+'d','red'):badge(d+'d','amber');
}

function empty(msg,icon='📭'){
  return `<div class="empty-state"><div class="empty-icon">${icon}</div><div class="empty-text">${msg}</div></div>`;
}

function parseDD(s){
  const m=String(s||'').match(/(\d{2})\/(\d{2})\/(\d{4})/);
  return m?new Date(+m[3],+m[2]-1,+m[1]):null;
}

function set(id,v){const e=document.getElementById(id);if(e)e.textContent=v;}

// ── Column sorting ────────────────────────────────────────────────────────
function setSort(sid, field){
  const cur=SORT[sid];
  SORT[sid]=cur&&cur.field===field?{field,dir:-cur.dir}:{field,dir:1};
  applyFilters();
}

function applySorted(rows, sid){
  const s=SORT[sid]; if(!s) return rows;
  return [...rows].sort((a,b)=>{
    let av=a[s.field]??'', bv=b[s.field]??'';
    if(typeof av==='number'&&typeof bv==='number') return (av-bv)*s.dir;
    const da=parseDD(av),db=parseDD(bv);
    if(da&&db) return (da-db)*s.dir;
    return String(av).localeCompare(String(bv),'pt-BR')*s.dir;
  });
}

// ── Table builder ─────────────────────────────────────────────────────────
function tbl(headers, rows, rowFn, opts={}){
  if(!rows.length) return empty(opts.empty||'Nenhum registro.',opts.icon||'📭');
  const sid=opts.sid, s=sid&&SORT[sid];
  const ths=headers.map((h,i)=>{
    const f=opts.fields&&opts.fields[i];
    if(!f||!sid) return `<th>${h}</th>`;
    const active=s&&s.field===f;
    const cls=active?(s.dir===1?' sort-asc':' sort-desc'):'';
    const icon=active?(s.dir===1?'↑':'↓'):'↕';
    return `<th class="sortable${cls}" onclick="setSort('${sid}','${f}')">${h}<span class="sort-icon">${icon}</span></th>`;
  }).join('');
  const data=opts.max?rows.slice(0,opts.max):rows;
  const trs=data.map(r=>`<tr>${rowFn(r)}</tr>`).join('');
  let html=`<div class="table-wrap"><table><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table></div>`;
  if(opts.max&&rows.length>opts.max)
    html+=`<div class="truncate-note">+${rows.length-opts.max} itens adicionais</div>`;
  return html;
}

function td(v,cls){return cls?`<td class="${cls}">${v}</td>`:`<td>${v}</td>`}

// ── Filter logic ──────────────────────────────────────────────────────────
const mt    = r => { if(!S.search) return true; const q=S.search.toLowerCase();
                     return (r.OC||'').toLowerCase().includes(q)||(r.Produto||'').toLowerCase().includes(q)||(r.Fornecedor||'').toLowerCase().includes(q); };
const mf    = r => !S.forns.size    || S.forns.has(r.Fornecedor);
const mfam  = r => !S.familias.size || S.familias.has(r.Familia);
const mz    = r => !S.fase          || r.Fase===S.fase;
const mAtr  = r => r.Atraso>=S.atraso && r.Atraso<=S.atraso_max;

// ── Main filter + render ──────────────────────────────────────────────────
function applyFilters(){
  const arriving    = applySorted(DATA.arriving.filter(r=>mt(r)&&mf(r)&&mz(r)),                   'arriving');
  const overdue     = applySorted(DATA.overdue.filter(r=>mt(r)&&mf(r)&&mz(r)&&mfam(r)&&mAtr(r)), 'overdue');
  const fat         = applySorted(DATA.fat_overdue.filter(r=>mt(r)&&mf(r)&&mz(r)&&mfam(r)&&mAtr(r)),'fat');
  const no_ship     = applySorted(DATA.no_ship.filter(r=>mt(r)&&mf(r)&&mfam(r)),                  'noship');
  const delays      = applySorted(DATA.delays.filter(r=>mt(r)&&mf(r)),                            'delays');
  const accels      = applySorted(DATA.accels.filter(r=>mt(r)&&mf(r)),                            'accels');
  const forn        = DATA.forn.filter(r=>!S.search||r.name.toLowerCase().includes(S.search.toLowerCase()));

  renderArriving(arriving); renderOverdue(overdue); renderFat(fat);
  renderNoShip(no_ship); renderDelays(delays); renderAccels(accels); renderForn(forn);

  document.getElementById('kpi-transito').textContent = DATA.meta.em_transito;
  document.getElementById('kpi-arriving').textContent = arriving.length;
  document.getElementById('kpi-overdue').textContent  = overdue.length;
  document.getElementById('kpi-fat').textContent      = fat.length;
  document.getElementById('kpi-noship').textContent   = no_ship.length;
  document.getElementById('kpi-delays').textContent   = delays.length;
  document.getElementById('kpi-accels').textContent   = accels.length;

  set('cnt-arriving',  arriving.length+' ordens');
  set('cnt-overdue',   overdue.length+' itens');
  set('cnt-fat',       fat.length+' itens');
  set('cnt-noship',    no_ship.length+' itens');
  set('cnt-delays',    delays.length+' hoje');
  set('cnt-accels',    accels.length+' hoje');
  set('cnt-forn',      forn.length+' fornecedores');

  updateStatus();
}

// ── Section renderers ─────────────────────────────────────────────────────
function renderArriving(rows){
  document.getElementById('tbl-arriving').innerHTML=tbl(
    ['Ordem de Compra','Produto','Fornecedor','Chegada PO','Fase','Status'],rows,
    r=>td(esc(r.OC),'mono')+td(esc(r.Produto))+td(esc(r.Fornecedor),'dim')+
       td(r.Chegada||'—','bold')+td(phaseBadge(r.Fase))+td(arrivingBadge(r.Dias)),
    {empty:'Nenhum embarque previsto para os próximos 7 dias.',icon:'📦',
     sid:'arriving',fields:['OC','Produto','Fornecedor','Chegada','Fase','Dias']});
}

function renderOverdue(rows){
  document.getElementById('tbl-overdue').innerHTML=tbl(
    ['Ordem de Compra','Produto','Fornecedor','Família','Necessidade','Chegada PO','Atraso'],rows,
    r=>td(esc(r.OC),'mono')+td(esc(r.Produto))+td(esc(r.Fornecedor),'dim')+td(esc(r.Familia),'dim')+
       td(r.Necessidade||'—')+td(r.ChegadaPO||'—')+td(overdueBadge(r.Atraso),'bold'),
    {empty:'Nenhum item com necessidade vencida.',icon:'✅',
     sid:'overdue',fields:['OC','Produto','Fornecedor','Familia','Necessidade','ChegadaPO','Atraso']});
}

function renderFat(rows){
  document.getElementById('tbl-fat').innerHTML=tbl(
    ['Ordem de Compra','Produto','Fornecedor','Família','Fat. Solicitada','Chegada PO','Necessidade','Atraso','Fase'],rows,
    r=>td(esc(r.OC),'mono')+td(esc(r.Produto))+td(esc(r.Fornecedor),'dim')+td(esc(r.Familia),'dim')+
       td(r.FatSolicitada||'—','bold')+td(r.ChegadaPO||'—')+td(r.Necessidade||'—')+
       td(overdueBadge(r.Atraso),'bold')+td(phaseBadge(r.Fase)),
    {empty:'Nenhum item com faturamento vencido.',icon:'✅',
     sid:'fat',fields:['OC','Produto','Fornecedor','Familia','FatSolicitada','ChegadaPO','Necessidade','Atraso','Fase']});
}

function renderNoShip(rows){
  document.getElementById('tbl-noship').innerHTML=tbl(
    ['Ordem de Compra','Produto','Fornecedor','Família','Necessidade'],rows,
    r=>td(esc(r.OC),'mono')+td(esc(r.Produto))+td(esc(r.Fornecedor),'dim')+
       td(esc(r.Familia),'dim')+td(r.Necessidade||'—'),
    {empty:'Todos os pedidos enviados possuem embarque definido.',icon:'✅',
     sid:'noship',fields:['OC','Produto','Fornecedor','Familia','Necessidade']});
}

function renderDelays(rows){
  const nc=!DATA.meta.has_yesterday;
  document.getElementById('tbl-delays').innerHTML=tbl(
    ['Ordem de Compra','Produto','Fornecedor','Campo','Anterior','Nova Data','Impacto'],rows,
    r=>td(esc(r.OC),'mono')+td(esc(r.Produto))+td(esc(r.Fornecedor),'dim')+td(esc(r.Campo),'dim')+
       td(r.Anterior,'dim')+td(r.Nova,'bold')+td(badge('+'+r.Delta+'d','solid-red')),
    {empty:nc?'Primeira execução — sem comparativo.':'Nenhum atraso registrado hoje.',
     icon:nc?'ℹ️':'✅',max:15,
     sid:'delays',fields:['OC','Produto','Fornecedor','Campo','Anterior','Nova','Delta']});
}

function renderAccels(rows){
  const nc=!DATA.meta.has_yesterday;
  document.getElementById('tbl-accels').innerHTML=tbl(
    ['Ordem de Compra','Produto','Fornecedor','Campo','Anterior','Nova Data','Ganho'],rows,
    r=>td(esc(r.OC),'mono')+td(esc(r.Produto))+td(esc(r.Fornecedor),'dim')+td(esc(r.Campo),'dim')+
       td(r.Anterior,'dim')+td(r.Nova,'bold')+td(badge(r.Delta+'d','solid-green')),
    {empty:nc?'Primeira execução — sem comparativo.':'Nenhuma antecipação registrada hoje.',
     icon:nc?'ℹ️':'✅',max:10,
     sid:'accels',fields:['OC','Produto','Fornecedor','Campo','Anterior','Nova','Delta']});
}

function renderForn(forn){
  if(!forn.length){document.getElementById('forn-chart').innerHTML=empty('Nenhum fornecedor.','🏭');return;}
  const maxL=Math.max(...forn.map(r=>r.linhas));
  const maxQ=Math.max(...forn.map(r=>r.qtde),1);
  document.getElementById('forn-chart').innerHTML=forn.map(r=>{
    const pL=Math.round(r.linhas/maxL*100), pQ=Math.round(r.qtde/maxQ*100);
    const qf=r.qtde.toLocaleString('pt-BR');
    return `<div class="forn-row">
      <div class="forn-name" title="${esc(r.name)}">${esc(r.name)}</div>
      <div class="forn-bars">
        <div class="bar-row"><span class="bar-lbl">Linhas</span>
          <div class="bar-track"><div class="bar-fill blue" style="width:${pL}%"></div></div>
          <span class="bar-val blue">${r.linhas}</span></div>
        <div class="bar-row"><span class="bar-lbl">Unid.</span>
          <div class="bar-track"><div class="bar-fill green" style="width:${pQ}%"></div></div>
          <span class="bar-val green">${qf}</span></div>
      </div></div>`;
  }).join('');
}

// ── Multi-select ──────────────────────────────────────────────────────────
function buildMS(wid, skey, placeholder, options){
  const wrap=document.getElementById(wid);
  wrap.innerHTML=`
    <button class="ms-btn" id="${wid}-btn" type="button" onclick="toggleMSDD('${wid}')">
      <span class="ms-lbl">${placeholder}</span><span class="ms-arrow">▾</span>
    </button>
    <div class="ms-dd" id="${wid}-dd">
      <div class="ms-si"><input type="text" placeholder="Buscar…" oninput="filterMSOpts('${wid}',this.value)"></div>
      <label class="ms-opt"><input type="checkbox" id="${wid}-all" checked
        onchange="msToggleAll('${wid}','${skey}','${placeholder}')"> Todos</label>
      <div class="ms-div"></div>
      <div id="${wid}-list">${options.map(o=>`<label class="ms-opt">
        <input type="checkbox" value="${esc(o)}" onchange="msToggleOpt('${wid}','${skey}','${placeholder}',this)">
        ${esc(o)}</label>`).join('')}</div>
    </div>`;
}

function toggleMSDD(wid){
  const dd=document.getElementById(wid+'-dd');
  const open=dd.style.display==='block';
  document.querySelectorAll('.ms-dd').forEach(d=>d.style.display='none');
  if(!open) dd.style.display='block';
}

function filterMSOpts(wid, q){
  q=q.toLowerCase();
  document.querySelectorAll(`#${wid}-list .ms-opt`).forEach(l=>{
    l.style.display=l.textContent.trim().toLowerCase().includes(q)?'':'none';
  });
}

function msToggleAll(wid, skey, ph){
  S[skey].clear();
  document.querySelectorAll(`#${wid}-list input`).forEach(c=>c.checked=false);
  document.getElementById(wid+'-all').checked=true;
  msBtnUpdate(wid,skey,ph); applyFilters();
}

function msToggleOpt(wid, skey, ph, cb){
  cb.checked?S[skey].add(cb.value):S[skey].delete(cb.value);
  const total=document.querySelectorAll(`#${wid}-list input`).length;
  const allCb=document.getElementById(wid+'-all');
  allCb.checked=S[skey].size===0;
  allCb.indeterminate=S[skey].size>0&&S[skey].size<total;
  msBtnUpdate(wid,skey,ph); applyFilters();
}

function msBtnUpdate(wid, skey, ph){
  const btn=document.getElementById(wid+'-btn');
  btn.querySelector('.ms-lbl').textContent=S[skey].size===0?ph:`${S[skey].size} selecionado${S[skey].size>1?'s':''}`;
  btn.classList.toggle('active',S[skey].size>0);
}

function msReset(wid, skey, ph){
  S[skey]=new Set();
  document.querySelectorAll(`#${wid}-dd input[type=checkbox]`).forEach(c=>{c.checked=false;c.indeterminate=false;});
  const allCb=document.getElementById(wid+'-all');
  if(allCb) allCb.checked=true;
  msBtnUpdate(wid,skey,ph);
}

// ── Presets ───────────────────────────────────────────────────────────────
function applyPreset(name){
  clearFilters(true);
  S.preset=name;
  if(name==='critico'){S.atraso=61;document.getElementById('f-atraso').value=61;document.getElementById('atraso-lbl').textContent='61d';}
  if(name==='atencao'){S.atraso=15;S.atraso_max=60;document.getElementById('f-atraso').value=15;document.getElementById('atraso-lbl').textContent='15d';}
  if(name==='transito') S.fase='Em trânsito';
  if(name==='enviado')  S.fase='Pedido Enviado';
  applyFilters();
}

// ── Status bar ────────────────────────────────────────────────────────────
function updateStatus(){
  const tags=[
    S.search&&`"${S.search}"`,
    S.forns.size&&`${S.forns.size} fornecedor(es)`,
    S.familias.size&&`${S.familias.size} família(s)`,
    S.fase&&S.fase,
    S.atraso>0&&(S.atraso_max<9999?`Atraso ${S.atraso}–${S.atraso_max}d`:`Atraso ≥${S.atraso}d`),
    (!S.atraso&&S.atraso_max<9999)&&`Atraso ≤${S.atraso_max}d`,
  ].filter(Boolean);
  const bar=document.getElementById('filter-status');
  const btn=document.getElementById('btn-clear');
  bar.style.display=tags.length?'flex':'none';
  if(tags.length) bar.innerHTML='<span>Filtros:</span>'+tags.map(t=>`<span class="af-tag">${esc(String(t))}</span>`).join('');
  btn.classList.toggle('hot',tags.length>0);
  document.querySelectorAll('.fase-pill').forEach(p=>p.classList.toggle('active',p.dataset.fase===S.fase));
  document.querySelectorAll('.preset-btn').forEach(b=>b.classList.toggle('active',b.dataset.preset===S.preset));
}

// ── Clear ─────────────────────────────────────────────────────────────────
function clearFilters(silent){
  S.search='';S.fase='';S.atraso=0;S.atraso_max=9999;S.preset='';
  document.getElementById('f-search').value='';
  document.getElementById('f-atraso').value='0';
  document.getElementById('atraso-lbl').textContent='0d';
  msReset('forn-wrap','forns','Fornecedores');
  msReset('familia-wrap','familias','Famílias');
  if(!silent) applyFilters();
}

// ── Init ──────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded',function(){
  buildMS('forn-wrap',   'forns',    'Fornecedores', DATA.fornecedores);
  buildMS('familia-wrap','familias', 'Famílias',     DATA.familias);

  document.addEventListener('click',e=>{
    if(!e.target.closest('.ms-wrap')) document.querySelectorAll('.ms-dd').forEach(d=>d.style.display='none');
  });

  // Fase pills
  const pp=document.getElementById('fase-pills');
  [['','Todas'],...DATA.fases.map(f=>[f,f])].forEach(([v,l])=>{
    const b=document.createElement('button');
    b.className='fase-pill'+(v===''?' active':'');b.dataset.fase=v;b.textContent=l;b.type='button';
    b.onclick=()=>{S.fase=S.fase===v&&v!==''?'':v;S.preset='';applyFilters();};
    pp.appendChild(b);
  });

  let t;
  document.getElementById('f-search').addEventListener('input',function(){
    clearTimeout(t);t=setTimeout(()=>{S.search=this.value.trim();S.preset='';applyFilters();},220);
  });

  document.getElementById('f-atraso').addEventListener('input',function(){
    S.atraso=+this.value;S.atraso_max=9999;S.preset='';
    document.getElementById('atraso-lbl').textContent=S.atraso+'d';
    applyFilters();
  });

  // Stale banner
  const fd=new Date('__TODAY_STR__');fd.setHours(0,0,0,0);
  const nd=new Date();nd.setHours(0,0,0,0);
  const diff=Math.round((nd-fd)/86400000);
  if(diff>0){
    const b=document.getElementById('stale-banner');b.style.display='block';
    b.textContent=`⚠️ Dashboard desatualizado — dados de __TODAY_DISPLAY__ (${diff} dia(s) atrás). Acesse a URL original para ver os dados de hoje.`;
  }

  document.querySelectorAll('nav a').forEach(a=>a.addEventListener('click',function(e){
    const el=document.getElementById(this.getAttribute('href').slice(1));
    if(el){e.preventDefault();el.scrollIntoView({behavior:'smooth',block:'start'});}
  }));

  applyFilters();
});
"""
    JS = JS.replace("__DATA_JSON__", data_json).replace("__TODAY_STR__", today_str).replace("__TODAY_DISPLAY__", today_display)

    # ── Full HTML ─────────────────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Follow-up Biomedical — {today_display}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>

<div id="stale-banner"></div>

<header>
  <div class="hdr">
    <div class="hdr-icon">📋</div>
    <div>
      <div class="hdr-title">Follow-up Biomedical</div>
      <div class="hdr-sub">Importações · Análise Diária</div>
    </div>
    <div class="hdr-meta">
      <div class="hdr-date">📅 {today_display}</div>
      <div class="hdr-count">{total} ordens ativas</div>
    </div>
  </div>
  <nav>
    <a href="#chegando">📦 Chegando</a>
    <a href="#movimentacoes">📊 Movimentações</a>
    <a href="#vencidos">🔴 Vencidos</a>
    <a href="#fat-vencido">💰 Fat. Vencido</a>
    <a href="#sem-embarque">⚡ Sem Embarque</a>
    <a href="#fornecedores">🏭 Fornecedores</a>
  </nav>
</header>

<main>

  <div class="kpi-grid">{kpis_html}</div>

  <div class="filter-bar">
    <div class="fb-row">
      <span class="fb-label">Atalhos:</span>
      <div class="preset-pills">
        <button class="preset-btn" data-preset="critico"  type="button" onclick="applyPreset('critico')"  title="Atraso maior que 60 dias">🔴 Crítico (&gt;60d)</button>
        <button class="preset-btn" data-preset="atencao"  type="button" onclick="applyPreset('atencao')"  title="Atraso entre 15 e 60 dias">🟠 Atenção (15–60d)</button>
        <button class="preset-btn" data-preset="transito" type="button" onclick="applyPreset('transito')" title="Somente Em trânsito">🚢 Em Trânsito</button>
        <button class="preset-btn" data-preset="enviado"  type="button" onclick="applyPreset('enviado')"  title="Pedido Enviado sem embarque">⚡ Enviado s/ Embarque</button>
      </div>
      <button id="btn-clear" class="btn-clear" type="button" onclick="clearFilters()">✕ Limpar</button>
    </div>
    <div class="fb-row">
      <div class="fb-search">
        <input type="text" id="f-search" placeholder="Buscar OC, produto ou fornecedor…" autocomplete="off">
      </div>
      <div class="ms-wrap" id="forn-wrap"></div>
      <div class="ms-wrap" id="familia-wrap"></div>
      <div class="fb-atraso">
        <label>Atraso mín: <span id="atraso-lbl">0d</span></label>
        <input type="range" id="f-atraso" min="0" max="120" step="5" value="0">
      </div>
    </div>
    <div class="fb-row">
      <span class="fb-label">Fase:</span>
      <div class="fase-pills" id="fase-pills"></div>
    </div>
    <div id="filter-status"></div>
  </div>

  <div id="chegando" class="section">
    <div class="sec-hdr">
      <span class="sec-icon">📦</span>
      <span class="sec-title">Chegando em até 7 dias</span>
      <span class="sec-badge green" id="cnt-arriving">—</span>
    </div>
    <div id="tbl-arriving"></div>
  </div>

  <div id="movimentacoes" class="grid-2">
    <div class="section">
      <div class="sec-hdr">
        <span class="sec-icon">⏰</span>
        <span class="sec-title">Atrasos de Data</span>
        <span class="sec-badge red" id="cnt-delays">—</span>
      </div>
      <div id="tbl-delays"></div>
    </div>
    <div class="section">
      <div class="sec-hdr">
        <span class="sec-icon">🚀</span>
        <span class="sec-title">Antecipações</span>
        <span class="sec-badge green" id="cnt-accels">—</span>
      </div>
      <div id="tbl-accels"></div>
    </div>
  </div>

  <div id="vencidos" class="section">
    <div class="sec-hdr">
      <span class="sec-icon">🔴</span>
      <span class="sec-title">Necessidade Vencida</span>
      <span class="sec-badge red" id="cnt-overdue">—</span>
    </div>
    <div id="tbl-overdue"></div>
  </div>

  <div id="fat-vencido" class="section">
    <div class="sec-hdr">
      <span class="sec-icon">💰</span>
      <span class="sec-title">Faturamento Vencido — Entrega Solicitada vs Hoje</span>
      <span class="sec-badge amber" id="cnt-fat">—</span>
    </div>
    <div id="tbl-fat"></div>
  </div>

  <div id="sem-embarque" class="section">
    <div class="sec-hdr">
      <span class="sec-icon">⚡</span>
      <span class="sec-title">Pedido Enviado sem Embarque</span>
      <span class="sec-badge amber" id="cnt-noship">—</span>
    </div>
    <div id="tbl-noship"></div>
  </div>

  <div id="fornecedores" class="section">
    <div class="sec-hdr">
      <span class="sec-icon">🏭</span>
      <span class="sec-title">Resumo por Fornecedor</span>
      <span class="sec-badge blue" id="cnt-forn">—</span>
    </div>
    <div id="forn-chart"></div>
  </div>

</main>

<footer>Follow-up Biomedical &mdash; dados de {today_display} &mdash; gerado automaticamente</footer>

<script>{JS}</script>
</body>
</html>"""

    with open(DASHBOARD_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[Dashboard gerado: {DASHBOARD_PATH}]")
    return DASHBOARD_PATH


def find_yesterday(today_path):
    s = os.path.basename(today_path).replace("followup_", "").replace(".csv", "")
    try:
        d = datetime.strptime(s, "%Y-%m-%d").date() - timedelta(days=1)
        p = os.path.join(HISTORICO_DIR, f"followup_{d}.csv")
        return p if os.path.exists(p) else None
    except ValueError:
        return None


if __name__ == "__main__":
    if len(sys.argv) < 2:
        csvs = sorted(f for f in os.listdir(HISTORICO_DIR)
                      if f.startswith("followup_") and f.endswith(".csv"))
        if not csvs:
            print("Nenhum CSV encontrado.")
            sys.exit(1)
        today_path = os.path.join(HISTORICO_DIR, csvs[-1])
    else:
        today_path = sys.argv[1]

    yesterday_path = find_yesterday(today_path) if len(sys.argv) < 3 else sys.argv[2]
    build_dashboard(today_path, yesterday_path)
