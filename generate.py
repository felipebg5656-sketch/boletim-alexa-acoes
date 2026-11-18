#!/usr/bin/env python3
"""Gera um Flash Briefing JSON da Alexa e página HTML com dados públicos.

Requer BRAPI_API_KEY no ambiente para consulta real. Não publica dados inventados.
Python 3.11+, apenas biblioteca padrão.
"""
from __future__ import annotations

import datetime as dt
import email.utils
import html
import json
import logging
import os
from pathlib import Path
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")
ROOT = Path(__file__).resolve().parent
OUT = ROOT / "site"

# Tickers de referência. Edite aqui se possuir outra classe (ex.: SAPR11, etc.).
ASSETS = [
    {"ticker": "ITUB4", "name": "Itaú", "class": "PN"},
    {"ticker": "BBDC4", "name": "Bradesco", "class": "PN"},
    {"ticker": "ABCB4", "name": "Banco ABC Brasil", "class": "PN"},
    {"ticker": "CPFE3", "name": "CPFL Energia", "class": "ON"},
    {"ticker": "AXIA3", "name": "AXIA Energia", "class": "ON"},
    {"ticker": "ISAE4", "name": "ISA Energia", "class": "PN"},
    {"ticker": "PSSA3", "name": "Porto Seguro", "class": "ON"},
    {"ticker": "BBSE3", "name": "BB Seguridade", "class": "ON"},
    {"ticker": "CXSE3", "name": "Caixa Seguridade", "class": "ON"},
    {"ticker": "SAPR4", "name": "Sanepar", "class": "PN"},
]

MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
WEEKDAYS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
KEYWORDS = ("dividend", "jcp", "provento", "balan", "resultado", "lucro", "receita", "ebitda", "aç", "acao", "ações", "aquisi", "regula", "aneel", "preju", "trimestre", "capital", "fato relevante", "energia", "banco", "seguro", "saneamento")


def clean(value: str, maximum: int = 185) -> str:
    value = html.unescape(re.sub(r"<[^>]*>", " ", value or ""))
    value = re.sub(r"\s+", " ", value).strip()
    return value[:maximum].rstrip(" ,.;-")


def request(url: str, headers: dict | None = None, retries: int = 2) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "BoletimAlexa/1.0 (uso pessoal)", "Accept": "application/json, application/rss+xml, */*", **(headers or {})})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=15) as res:
                return res.read(1_500_000)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            if attempt >= retries or (isinstance(exc, urllib.error.HTTPError) and exc.code in (400, 401, 403, 404)):
                raise
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError("Falha inesperada na requisição")


def iso_date(s: str | None) -> dt.date | None:
    if not s:
        return None
    try:
        return dt.date.fromisoformat(s[:10])
    except ValueError:
        return None


def price_br(value: float) -> str:
    return "R$ " + f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def money_speech(value: float) -> str:
    centavos_total = round(value * 100)
    reais, centavos = divmod(centavos_total, 100)
    return f"{reais} reais e {centavos:02d} centavos"


def percent_br(value: float) -> str:
    return f"{abs(value):.2f}".replace(".", ",") + "%"


def when_portuguese(day: dt.date) -> str:
    return f"{day.day} de {MONTHS[day.month-1]} de {day.year}"


def fetch_quote(ticker: str, token: str) -> dict | None:
    params = urllib.parse.urlencode({"symbols": ticker})
    data = json.loads(request(f"https://brapi.dev/api/v2/stocks/quote?{params}", {"Authorization": "Bearer " + token}))
    result = (data.get("results") or [None])[0]
    if not isinstance(result, dict):
        return None
    raw = result.get("data") or {}
    try:
        price = float(raw["regularMarketPrice"])
        change = float(raw["regularMarketChangePercent"])
    except (KeyError, ValueError, TypeError):
        return None
    return {"price": price, "change": change, "date": iso_date(raw.get("regularMarketTime")), "symbol": result.get("symbol", ticker)}


def fetch_dividends(ticker: str, share_class: str) -> list[dict]:
    url = f"https://dadosb3.com/empresas/{ticker}/dividendos"
    data = json.loads(request(url, {"Accept": "application/json"}, retries=1))
    result = []
    for item in data.get("proventos", []):
        classe = str(item.get("tipo_acao") or "").upper().strip()
        # Não misturar proventos de ON e PN. Para UNIT, revisar tratamento manualmente.
        if share_class == "PN" and not classe.startswith("PN"):
            continue
        if share_class == "ON" and not classe.startswith("ON"):
            continue
        aprovado = iso_date(item.get("data_aprovacao"))
        pagamento = iso_date(item.get("data_pagamento"))
        data_com = iso_date(item.get("data_com"))
        try:
            valor = float(item.get("valor"))
        except (TypeError, ValueError):
            continue
        if valor <= 0:
            continue
        result.append({"ticker": ticker, "type": clean(item.get("tipo") or "Provento", 16), "value": valor, "approved": aprovado, "payment": pagamento, "data_com": data_com, "source": url})
    return result


def fetch_news(asset: dict, today: dt.date) -> list[dict]:
    # A consulta é por empresa/ticker. Nunca presumir que título equivale a fato confirmado.
    q = f'("{asset["ticker"]}" OR "{asset["name"]}") (ações OR dividendos OR resultados OR bolsa) when:2d'
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": q, "hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"})
    root = ET.fromstring(request(url, {"Accept": "application/rss+xml"}, retries=1))
    results = []
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=42)
    for item in root.findall("./channel/item")[:12]:
        title = clean(item.findtext("title") or "")
        link = clean(item.findtext("link") or "", 400)
        if not link.startswith(("https://", "http://")):
            continue
        try:
            published = email.utils.parsedate_to_datetime(item.findtext("pubDate") or "")
            if published.tzinfo is None:
                published = published.replace(tzinfo=dt.timezone.utc)
        except (ValueError, TypeError):
            continue
        if not title or published < cutoff:
            continue
        normalized = unicodedata.normalize("NFKD", title).casefold()
        score = sum(1 for k in KEYWORDS if k in normalized)
        if score < 1:
            continue
        results.append({"ticker": asset["ticker"], "company": asset["name"], "title": title, "url": link, "published": published, "score": score})
    return results[:3]


def choose_events(events: list[dict], today: dt.date) -> list[dict]:
    selected = []
    seen = set()
    for e in events:
        approved = e["approved"]
        payment = e["payment"]
        # Eventos anunciados na última semana ou pagamento nos próximos 14 dias.
        is_recent = bool(approved and dt.timedelta(0) <= (today - approved) <= dt.timedelta(days=7))
        is_upcoming = bool(payment and dt.timedelta(0) <= (payment - today) <= dt.timedelta(days=14))
        if not (is_recent or is_upcoming):
            continue
        signature = (e["ticker"], e["type"], e["value"], e["data_com"], payment)
        if signature in seen:
            continue
        seen.add(signature)
        selected.append(e)
    selected.sort(key=lambda x: (x["approved"] or dt.date.min, x["payment"] or dt.date.min), reverse=True)
    return selected[:3]


def choose_news(news: list[dict]) -> list[dict]:
    sorted_news = sorted(news, key=lambda x: (x["score"], x["published"]), reverse=True)
    seen_titles = set()
    chosen = []
    for item in sorted_news:
        key = unicodedata.normalize("NFKD", item["title"]).casefold()
        if key in seen_titles:
            continue
        seen_titles.add(key)
        if len(chosen) >= 4:
            break
        chosen.append(item)
    return chosen


def compose(assets: list[dict], quotes: dict, events: list[dict], news: list[dict], today: dt.date, errors: list[str]) -> str:
    parts = [f"Boletim da bolsa de {when_portuguese(today)}."]
    if quotes:
        parts.append("Confira as últimas cotações disponíveis das suas dez empresas. Os preços podem ter atraso e não representam negociação em tempo real.")
        for asset in assets:
            ticker, name = asset["ticker"], asset["name"]
            q = quotes.get(ticker)
            if not q:
                parts.append(f"{name}, {ticker}: cotação indisponível.")
                continue
            signal = "alta" if q["change"] > 0 else "queda" if q["change"] < 0 else "estabilidade"
            date_note = f"Referência: {when_portuguese(q['date'])}. " if q.get("date") and q["date"] != today else ""
            parts.append(f"{name}, {ticker}: {date_note}{money_speech(q['price'])}, {signal} de {percent_br(q['change']).replace('%', ' por cento')}.")
    else:
        parts.append("Não foi possível atualizar as cotações hoje. Não vou informar preços sem confirmação.")

    top_news = choose_news(news)
    if top_news:
        parts.append("Destaques da imprensa financeira:")
        for article in top_news:
            title = article["title"]
            parts.append(f"{article['company']}: manchete publicada: {title}.")
    elif any("notícia" in e for e in errors):
        parts.append("A consulta às manchetes não ficou disponível nesta atualização.")
    else:
        parts.append("Não foram selecionadas manchetes recentes com os filtros definidos.")

    selected = choose_events(events, today)
    if selected:
        parts.append("Dividendos e juros sobre capital próprio em destaque. Valores brutos por ação:")
        for event in selected:
            name = next(a["name"] for a in assets if a["ticker"] == event["ticker"])
            try:
                pmt = f" Pagamento previsto para {when_portuguese(event['payment'])}." if event["payment"] else " Data de pagamento não informada."
                date_com = f" Data com {when_portuguese(event['data_com'])}." if event["data_com"] else ""
                parts.append(f"{name}: {event['type']}, {price_br(event['value'])} por ação.{date_com}{pmt}")
            except Exception as exc:
                logging.warning("Falha ao formatar provento %s: %s", event, exc)
        parts.append("A existência de um pagamento não confirma que você tenha direito a recebê-lo. Isso depende da posição na data com.")
    elif any("provento" in e for e in errors):
        parts.append("A consulta de dividendos ficou parcialmente indisponível; confirme datas e valores nos comunicados oficiais.")
    else:
        parts.append("Sem novos eventos de proventos selecionados nos últimos sete dias nem pagamentos identificados para os próximos quatorze dias.")
    parts.append("Este boletim é informativo e não constitui recomendação de investimento.")
    text = " ".join(parts)
    if len(text) >= 4400:
        # A especificação da Amazon trunca em 4.500 caracteres.
        text = text[:4330].rsplit(".", 1)[0] + "."
    return text


def make_html(today: dt.date, quotes: dict, events: list[dict], news: list[dict], errors: list[str], narration: str) -> str:
    rows = []
    for a in ASSETS:
        q = quotes.get(a["ticker"])
        p = price_br(q["price"]) if q else "indisponível"
        ch = ("+" if q["change"] > 0 else "−" if q["change"] < 0 else "") + percent_br(q["change"]) if q else "—"
        css = "up" if q and q["change"] > 0 else "down" if q and q["change"] < 0 else ""
        day = q["date"].strftime("%d/%m/%Y") if q and q.get("date") else "—"
        rows.append(f'<tr><td><b>{html.escape(a["name"])}</b><small>{html.escape(a["ticker"])}</small></td><td>{html.escape(p)}</td><td class="{css}">{html.escape(ch)}</td><td>{day}</td></tr>')
    selected = choose_events(events, today)
    event_html = "".join('<li><b>{}</b>: {} — {} por ação, data-com {}, pagamento {}. <a rel="noopener" href="{}">Fonte</a></li>'.format(
        html.escape(e["ticker"]), html.escape(e["type"]), html.escape(price_br(e["value"])),
        e["data_com"].strftime("%d/%m/%Y") if e["data_com"] else "não informada",
        e["payment"].strftime("%d/%m/%Y") if e["payment"] else "não informado",
        html.escape(e["source"], quote=True)) for e in selected) or "<li>Nenhum evento selecionado para a janela de acompanhamento.</li>"
    news_html = "".join(f'<li><b>{html.escape(n["company"])}</b>: <a rel="noopener noreferrer" href="{html.escape(n["url"], quote=True)}">{html.escape(n["title"])}</a></li>' for n in choose_news(news)) or "<li>Nenhuma manchete selecionada.</li>"
    err_html = '<p class="warning">Consultas não concluídas: ' + html.escape(", ".join(sorted(set(errors)))) + '</p>' if errors else ""
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>Boletim de Ações</title><style>
:root{{color-scheme:dark;font-family:system-ui,Arial,sans-serif}}body{{margin:0;background:#0d1321;color:#e9eef8}}main{{max-width:900px;margin:0 auto;padding:24px 16px 60px}}.subtitle{{color:#94a3b8}}.card{{background:#172136;padding:19px;border:1px solid #273449;border-radius:16px;margin:18px 0}}h1{{font-size:clamp(27px,5vw,39px);margin-bottom:6px}}h2{{font-size:20px}}table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{padding:13px 8px;border-bottom:1px solid #2e3a4d;text-align:left}}small{{display:block;color:#8fa0b9;margin-top:3px}}.up{{color:#65dbac}}.down{{color:#ff9494}}a{{color:#91caff}}li{{margin:12px 0;line-height:1.55}}p{{line-height:1.7}}.warning{{color:#ffcc8a}}.muted{{color:#9badc6;font-size:12px}}</style></head><body><main>
<h1>Boletim da Bolsa</h1><p class="subtitle">Atualização preparada em {html.escape(when_portuguese(today))} • Brasil</p>
<div class="card"><h2>Suas 10 empresas</h2><table><thead><tr><th>Empresa</th><th>Cotação</th><th>Dia</th><th>Referência</th></tr></thead><tbody>{''.join(rows)}</tbody></table><p class="muted">Cotações informativas, com possível atraso de 30 minutos. Fonte: brapi.dev. Os preços e respectivas datas são exibidos conforme disponibilidade.</p></div>
<div class="card"><h2>Manchetes financeiras</h2><ul>{news_html}</ul><p class="muted">Fonte: Google Notícias (RSS). As manchetes são de veículos externos e não constituem análise de seu conteúdo.</p></div>
<div class="card"><h2>Proventos e JCP</h2><ul>{event_html}</ul><p class="muted">Valores brutos por ação; crédito efetivo depende da posição na data-com. Fonte: dadosb3.com — valide os avisos do RI.</p></div>
<div class="card"><h2>Texto que a Alexa vai ler</h2><p>{html.escape(narration)}</p></div>
{err_html}<p class="muted">Atualização automática prevista para 20h (horário de Brasília), antes da rotina das 21h. Em fins de semana e feriados, poderá constar a cotação do último pregão.</p>
</main></body></html>'''


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    token = os.getenv("BRAPI_API_KEY", "").strip()
    if not token:
        logging.error("BRAPI_API_KEY ausente. Configure como GitHub Actions Secret; nada foi publicado.")
        return 2
    now = dt.datetime.now(TZ)
    today = now.date()
    quotes, events, news, errors = {}, [], [], []
    for idx, a in enumerate(ASSETS, 1):
        t = a["ticker"]
        logging.info("[%s/%s] Consultando %s", idx, len(ASSETS), t)
        try:
            q = fetch_quote(t, token)
            if q:
                quotes[t] = q
            else:
                errors.append(f"cotação {t}")
        except Exception as exc:
            errors.append(f"cotação {t}")
            logging.warning("cotação %s: %s", t, exc)
        try:
            events.extend(fetch_dividends(t, a["class"]))
        except Exception as exc:
            errors.append(f"proventos {t}")
            logging.warning("proventos %s: %s", t, exc)
        try:
            news.extend(fetch_news(a, today))
        except Exception as exc:
            errors.append(f"notícias {t}")
            logging.warning("notícias %s: %s", t, exc)
    if len(quotes) < len(ASSETS):
        logging.error("Apenas %d/10 cotações retornaram. Publicação cancelada.", len(quotes))
        return 3
    narration = compose(ASSETS, quotes, events, news, today, errors)
    # UID estável por edição diária, updateDate varia em cada atualização.
    entry = [{"uid": "urn:boletim-bolsa:" + today.isoformat(),
              "updateDate": now.astimezone(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
              "titleText": "Boletim das suas ações — " + today.strftime("%d/%m/%Y"),
              "mainText": narration,
              "redirectionUrl": os.getenv("PUBLIC_URL") or "https://felipebg5656-sketch.github.io/boletim-alexa-acoes/"}]
    OUT.mkdir(exist_ok=True)
    (OUT / "briefing.json").write_text(json.dumps(entry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "index.html").write_text(make_html(today, quotes, events, news, errors, narration), encoding="utf-8")
    print(f"Gerado: {OUT/'briefing.json'}, {len(narration)} caracteres, {len(quotes)} cotações, {len(choose_news(news))} notícias, {len(choose_events(events, today))} proventos")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
