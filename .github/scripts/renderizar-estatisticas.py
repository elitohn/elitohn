from pathlib import Path
import re
import sys
from xml.etree import ElementTree
from xml.sax.saxutils import escape


SVG = "{http://www.w3.org/2000/svg}svg"
METRICAS = {
    "stars": "Estrelas recebidas",
    "commits": "Commits (último ano)",
    "prs": "Pull requests",
    "issues": "Issues criadas",
    "contribs": "Repos. com contribuição (último ano)",
}
TEMAS = {
    "light": ("#fbfaff", "#ddd6fe", "#6d28d9", "#334155", "#0e7490", "#ecfeff"),
    "dark": ("#15152a", "#393456", "#c4b5fd", "#cbd5e1", "#67e8f9", "#1a2940"),
}


def ler_svg(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 131_072:
        raise ValueError(f"Arquivo de origem inválido: {path.name}")
    svg = path.read_text(encoding="utf-8")
    if "<!DOCTYPE" in svg or "<!ENTITY" in svg:
        raise ValueError(f"Declaração XML inesperada: {path.name}")
    root = ElementTree.fromstring(svg)
    if root.tag != SVG:
        raise ValueError(f"A origem não é um SVG: {path.name}")
    return root


def ler_atividade(root):
    valores = {
        e.get("data-testid"): "".join(e.itertext()).strip()
        for e in root.findall(".//*[@data-testid]")
    }
    contagens = {campo: valores.get(campo, "") for campo in METRICAS}
    rank = valores.get("level-rank-icon", "")
    if not all(re.fullmatch(r"[0-9]+(?:[.,][0-9]+)*[kKmMbB]?", v) for v in contagens.values()):
        raise ValueError("O card de atividade não contém todas as contagens")
    if not re.fullmatch(r"[A-Z]{1,3}[+-]?", rank):
        raise ValueError("O card de atividade não contém um rank válido")
    return contagens, rank


def ler_linguagens(root):
    nomes = root.findall(".//*[@data-testid='lang-name']")
    segmentos = root.findall(".//*[@data-testid='lang-progress']")
    if not nomes or len(nomes) != len(segmentos) or len(nomes) > 6:
        raise ValueError("O card de linguagens não contém a lista esperada")
    linguagens = []
    for nome, segmento in zip(nomes, segmentos):
        dados = "".join(nome.itertext()).strip()
        match = re.fullmatch(r"(.+?)\s+(\d{1,3}(?:[.,]\d{1,2})?)%", dados)
        cor = segmento.get("fill", "")
        if not match or not re.fullmatch(r"#[0-9a-fA-F]{6}", cor):
            raise ValueError("Linguagem ou percentual inválido")
        rotulo, percentual = match.groups()
        valor = float(percentual.replace(",", "."))
        if not 0 <= valor <= 100:
            raise ValueError("Percentual fora do intervalo esperado")
        linguagens.append((rotulo, valor, cor))
    if sum(valor for _, valor, _ in linguagens) <= 0:
        raise ValueError("A distribuição de linguagens está vazia")
    return linguagens


def card(titulo, descricao, icone, tema, elementos, definicoes=""):
    fundo, borda, destaque, _, icone_cor, _ = tema
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="370" height="186" viewBox="0 0 370 186">
  <title>{escape(titulo)}</title>
  <desc>{escape(descricao)}</desc>
{definicoes}  <rect x="4.5" y="4.5" width="361" height="177" rx="10" fill="{fundo}" stroke="{borda}"/>
  <path d="{icone}" fill="none" stroke="{icone_cor}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>
  <g font-family="Arial, Helvetica, sans-serif">
    <text x="49" y="34" font-size="20" font-weight="700" fill="{destaque}">{escape(titulo)}</text>
{elementos}
  </g>
</svg>
'''


def atividade_svg(contagens, rank, tema):
    _, borda, destaque, texto, icone_cor, selo = tema
    linhas = [
        f'    <rect x="282" y="18" width="65" height="22" rx="11" fill="{selo}"/>',
        f'    <text x="314.5" y="33" text-anchor="middle" font-size="12" font-weight="700" fill="{icone_cor}">Rank {rank}</text>',
        f'    <path d="M22 49H347" stroke="{borda}"/>',
    ]
    for i, (campo, rotulo) in enumerate(METRICAS.items()):
        y = 69 + i * 23
        linhas.append(f'    <text x="22" y="{y}" font-size="14" fill="{texto}">{rotulo}</text>')
        linhas.append(
            f'    <text x="347" y="{y}" text-anchor="end" font-size="15" font-weight="700" fill="{destaque}">{contagens[campo]}</text>'
        )
    resumo = ". ".join(f"{rotulo}: {contagens[campo]}" for campo, rotulo in METRICAS.items())
    return card("Estatísticas do GitHub", f"{resumo}. Rank {rank}.", "M23 20v16h17m-14-5 4-5 4 2 5-7", tema, "\n".join(linhas))


def linguagens_svg(linguagens, tema):
    _, borda, _, texto, _, _ = tema
    total = sum(valor for _, valor, _ in linguagens)
    barras = []
    legenda = []
    resumo = []
    x_barra = 22.0
    for i, (nome, valor, cor) in enumerate(linguagens):
        largura = 325 * valor / total
        barras.append(f'      <rect x="{x_barra:.3f}" y="54" width="{largura:.3f}" height="10" fill="{cor}"/>')
        x_barra += largura
        x, y = 22 + (i % 2) * 173, 97 + (i // 2) * 28
        rotulo = nome if len(nome) <= 13 else f"{nome[:12]}…"
        percentual = f"{valor:.2f}%".replace(".", ",")
        legenda.extend([
            f'    <circle cx="{x + 5}" cy="{y - 4}" r="4.5" fill="{cor}" stroke="{borda}" stroke-width=".5"/>',
            f'    <text x="{x + 17}" y="{y}" font-size="14" fill="{texto}">{escape(rotulo)}</text>',
            f'    <text x="{x + 152}" y="{y}" text-anchor="end" font-size="14" font-weight="700" fill="{texto}">{percentual}</text>',
        ])
        resumo.append(f"{nome} {percentual}")
    elementos = "\n".join(['    <g clip-path="url(#barra)">', *barras, "    </g>", *legenda])
    definicoes = '  <defs><clipPath id="barra"><rect x="22" y="54" width="325" height="10" rx="5"/></clipPath></defs>\n'
    return card("Linguagens mais usadas", ", ".join(resumo), "M28 23l-5 5 5 5m9-10 5 5-5 5m-3-14-4 18", tema, elementos, definicoes)


def main(origem, destino):
    contagens, rank = ler_atividade(ler_svg(origem / "atividade.svg"))
    linguagens = ler_linguagens(ler_svg(origem / "linguagens.svg"))
    destino.mkdir(parents=True, exist_ok=True)
    for nome, tema in TEMAS.items():
        (destino / f"atividade-{nome}.svg").write_text(atividade_svg(contagens, rank, tema), encoding="utf-8")
        (destino / f"linguagens-{nome}.svg").write_text(linguagens_svg(linguagens, tema), encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
