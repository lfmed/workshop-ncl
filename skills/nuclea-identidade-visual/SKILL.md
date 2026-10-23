---
name: nuclea-identidade-visual
description: Código de cores e identidade visual da Núclea (ex-CIP) - HEX oficiais (preto, branco, verde-água, lilás, amarelo-lima), tons de texto, tons derivados acessíveis, regras de contraste WCAG, uso em apps/dashboards/gráficos/slides e tokens CSS prontos. Use sempre que for criar ou estilizar qualquer artefato visual para a Núclea - app Databricks, dashboard AI/BI, gráfico, apresentação, HTML, e-mail ou documento.
---

# Identidade visual Núclea: código de cores

**Fonte:** os valores foram extraídos dos vetores do *Código de Ética e Conduta Núclea (2022)*, um PDF institucional da própria empresa. É o material público mais fiel encontrado.

**Limites:**
- **Não existe brandbook público.** Para peças oficiais, peça o manual de marca à Núclea.
- O logo oficial (`LOGO_NUCLEA.svg`, no site) é **monocromático**: preto, ou branco sobre fundo escuro.

## Paleta oficial

| Token | HEX | RGB | Papel | Onde aparece |
|---|---|---|---|---|
| `--nuclea-preto` | `#000000` | 0, 0, 0 | **Base**: fundos de destaque, logo, texto | Painéis de capa e seções; logo |
| `--nuclea-branco` | `#FFFFFF` | 255, 255, 255 | **Base**: fundo principal, logo invertido | Fundo das páginas |
| `--nuclea-verde-agua` | `#67FFCC` | 103, 255, 204 | **Destaque 1**: blocos, faixas, ilustrações | Painéis e formas geométricas |
| `--nuclea-lilas` | `#CC99FE` | 204, 153, 254 | **Destaque 2**: títulos e subtítulos sobre preto | Títulos em negrito |
| `--nuclea-lima` | `#DBED1F` | 219, 237, 31 | **Destaque 3**: traço sob títulos, setas | Pincelada sob títulos; chevron `>` |
| `--nuclea-lima-vivo` | `#D4EE00` | 212, 238, 0 | Variação do lima | Grafismos pontuais |
| `--nuclea-azul-noite` | `#0E2233` | 14, 34, 51 | Texto escuro alternativo | Corpo de texto |
| `--nuclea-grafite` | `#464646` | 70, 70, 70 | Texto corrido sobre branco | Corpo de texto (cor mais usada) |

Na área do documento, as cores se dividem assim:
- branco 64%
- lilás 12%
- preto 8%
- verde-água 8%
- lima 8%

A estética é **preto + branco dominantes, com destaques neon pontuais**.

Exemplos de aplicação: [fundo preto](referencias/exemplo_pagina_fundo_preto.png) e [verde-água](referencias/exemplo_pagina_verde_agua.png).

## Regras de contraste (WCAG 2.x, calculadas)

Os três destaques são **cores claras e luminosas**. Eles funcionam como texto **só sobre fundo escuro**, e como fundo **só com texto preto**.

| Combinação | Contraste | Uso |
|---|---|---|
| Lilás sobre preto | 9,6:1 | ✅ títulos e texto |
| Verde-água sobre preto | 16,8:1 | ✅ texto, números de destaque |
| Lima sobre preto | 16,2:1 | ✅ texto, ícones, sublinhado |
| Preto sobre verde-água, lima ou lilás | 16,8 / 16,2 / 9,6:1 | ✅ texto sobre bloco colorido |
| Branco, lilás, verde-água ou lima sobre azul-noite | 16,2 / 7,4 / 12,9 / 12,5:1 | ✅ alternativa ao preto puro |
| Grafite ou azul-noite sobre branco | 9,4 / 16,2:1 | ✅ texto corrido |
| **Lilás sobre branco** | 2,2:1 | ❌ nunca como texto |
| **Verde-água ou lima sobre branco** | 1,25 / 1,3:1 | ❌ nunca como texto nem como linha fina; só como bloco de fundo |

**Tons derivados para fundo branco.** Use quando precisar da cor do destaque em texto, link, linha de gráfico ou ícone sobre branco. **Não são oficiais;** sinalize se a peça for institucional.

| Token | HEX | Contraste sobre branco |
|---|---|---|
| `--nuclea-lilas-escuro` | `#6B2FC0` | 7,5:1 |
| `--nuclea-verde-escuro` | `#00795A` | 5,4:1 |
| `--nuclea-lima-escuro` | `#5E6600` | 6,2:1 |

Para validar uma combinação nova: [referencias/contraste_wcag.py](referencias/contraste_wcag.py).

## Como aplicar

### Apps (Flask/Jinja2) e HTML
Importe [referencias/nuclea_tokens.css](referencias/nuclea_tokens.css) e siga este padrão:
- **Cabeçalho e navegação:** fundo `--nuclea-preto` com logo branco. A aba ativa leva sublinhado `--nuclea-lima` e o hover `--nuclea-verde-agua`.
- **Conteúdo:** fundo `--nuclea-branco`, texto `--nuclea-grafite` ou `--nuclea-azul-noite`, títulos em preto.
- **Botão primário:** fundo `--nuclea-verde-agua` com texto **preto**. **Botão secundário:** borda preta. **Link:** `--nuclea-lilas-escuro`.
- **Cards de KPI de destaque:** fundo preto, número em verde-água ou lima, rótulo em lilás.
- **Status** (a marca não define; use os derivados mais o vermelho):

| Status | Cor |
|---|---|
| OK | `#00795A` |
| Atenção | `#5E6600`, ou fundo lima com texto preto |
| Crítico | `#C62828` |

Não invente uma 4ª cor neon.

### Dashboards AI/BI e gráficos
- **Ordem da paleta categórica sobre fundo escuro:** `#67FFCC`, `#CC99FE`, `#DBED1F`, `#FFFFFF`.
- **Ordem da paleta categórica sobre fundo claro:** `#00795A`, `#6B2FC0`, `#5E6600`, `#464646`.
- Com mais de 4 séries, agrupe em "Outros" em vez de inventar cores.
- **Escala sequencial:**
  - Fundo claro: de branco a `#00795A`.
  - Fundo escuro: de `#0E2233` a `#67FFCC`.
- **Destaque de 1 série:** só ela colorida (verde-água no escuro, verde-escuro no claro) e o resto em cinza `#BDBDBD`.
- **Divergente** (pior / melhor que o mercado): de `#6B2FC0` (lilás-escuro) a cinza a `#00795A` (verde-escuro). Evite vermelho e verde puros.

### Slides e documentos
Siga o padrão do material institucional:
- Página dividida entre um painel **preto** ou **verde-água** e um painel branco.
- Títulos em **lilás** sobre preto, com uma **pincelada lima** embaixo.
- Uma seta ou chevron lima como grafismo.
- Corpo de texto em grafite.
- Logo "Nuclea" em traço fino no canto superior direito, em preto ou branco.

**Tipografia:** não há fonte oficial pública confirmada. O documento usa Calibri. Em web, use `Calibri, Carlito, "Segoe UI", sans-serif`.

## Não fazer
- Texto em verde-água, lima ou lilás sobre fundo branco.
- Aplicar os três destaques juntos e com o mesmo peso em uma tela. Escolha 1 dominante e no máximo 1 de apoio.
- Colorir o logo com os destaques. Ele é sempre preto ou branco.
- Usar gradientes entre os destaques, sombras coloridas ou versões "pastel" lavadas.
- Apresentar os tons derivados como oficiais da Núclea.

## Para reextrair de um material novo
Se a Núclea enviar um PDF ou deck atualizado:
```bash
python -I referencias/extrair_cores_pdf.py <arquivo.pdf>
```
O script lista as cores de forma por área e as cores e fontes de texto.
