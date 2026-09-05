"""fcv.progress — dashboard de progreso para corridas FCV (solo presentacion).

Render en el PROCESO PRINCIPAL: los workers no lo tocan. El bucle as_completed sabe
a que metodo/familia pertenece cada celda terminada, asi que podemos pintar una barra
de color por metodo + por familia + un TOTAL sin tocar el codigo paralelo.

Cadena de fallback (que la corrida NUNCA se rompa por algo cosmetico):
  1) rich + consola jupyter/tty -> dashboard con panel + barras de color por fila
  2) rich ausente / sin consola -> barras tqdm por metodo (con color) + TOTAL
  3) nada disponible            -> barra unica tqdm / impresion esporadica

Uso:
    from fcv.progress import live_dashboard
    with live_dashboard(tasks, jobs) as dash:
        for fut in as_completed(futs):
            ...
            dash.advance(method, family)
"""
import time
from collections import OrderedDict
from contextlib import contextmanager

# orden de despliegue canonico; pares vainilla/memetico comparten gama de color
_METHOD_ORDER = ["floor", "ils", "ga", "mga", "bpso", "mbpso", "bde", "mbde"]
_FAMILY_ORDER = ["knapsack", "scp", "scp_orlib", "uflp"]

# color por metodo (nombres rich). vainilla = tono base, memetico = tono brillante.
_METHOD_RICH = {
    "floor": "green",
    "ils":   "cyan",
    "ga":    "blue",        "mga":   "bright_blue",
    "bpso":  "magenta",     "mbpso": "bright_magenta",
    "bde":   "dark_orange", "mbde":  "yellow",
}
# equivalentes hex para tqdm (no soporta los bright_* por nombre)
_METHOD_HEX = {
    "floor": "#2ca02c",
    "ils":   "#17becf",
    "ga":    "#1f77b4",   "mga":   "#5fa8ff",
    "bpso":  "#c724b1",   "mbpso": "#ff5fff",
    "bde":   "#ff8c00",   "mbde":  "#e8c100",
}
_FAMILY_RICH = "grey70"
_FAMILY_HEX = "#9aa0a6"


def _tally(tasks):
    """Cuenta celdas por metodo y por familia desde la lista REAL de tasks.

    task = (spec, decoder, method, n_seeds); spec = (family, tag, n, idx).
    Devuelve dos OrderedDict ordenados por el orden canonico, dejando claves
    desconocidas al final en orden de aparicion. Solo aparecen las presentes.
    """
    methods, families = OrderedDict(), OrderedDict()
    for spec, _dec, method, _ns in tasks:
        family = spec[0]
        methods[method] = methods.get(method, 0) + 1
        families[family] = families.get(family, 0) + 1

    def _ordered(counts, canonical):
        keys = ([k for k in canonical if k in counts] +
                [k for k in counts if k not in canonical])
        return OrderedDict((k, counts[k]) for k in keys)

    return _ordered(methods, _METHOD_ORDER), _ordered(families, _FAMILY_ORDER)


def _fmt_eta(sec):
    if sec is None or sec != sec or sec == float("inf"):
        return "--:--"
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _fmt_rate(r):
    return f"{r:.1f}/s" if r >= 1 else f"{r * 60:.0f}/m"


# --- 1) dashboard rich --------------------------------------------------------
class _RichDashboard:
    def __init__(self, method_tot, family_tot, jobs, console):
        from rich.live import Live
        self.method_tot, self.family_tot, self.jobs = method_tot, family_tot, jobs
        self.console = console
        self.method_done = {k: 0 for k in method_tot}
        self.family_done = {k: 0 for k in family_tot}
        self.total = sum(method_tot.values())
        self.done = 0
        self.t0 = time.time()
        self._live = Live(self._render(), console=console,
                          refresh_per_second=4, transient=False)

    def __enter__(self):
        self._live.__enter__()
        return self

    def __exit__(self, *exc):
        self._live.update(self._render(), refresh=True)
        self._live.__exit__(*exc)
        self._summary()
        return False

    def advance(self, method, family):
        self.done += 1
        if method in self.method_done:
            self.method_done[method] += 1
        if family in self.family_done:
            self.family_done[family] += 1
        self._live.update(self._render(), refresh=False)

    def _bar_width(self):
        # ancho de barra ADAPTATIVO: el resto de columnas (label/pct/done/rate/eta) +
        # padding + bordes ocupan ~46 cols en el peor caso (eta H:MM:SS). Reservamos
        # eso y un margen para que el eta NUNCA se salga del recuadro aunque la consola
        # sea angosta. Clamp [10, 24] para que se vea bien en anchos tipicos.
        avail = getattr(self.console, "width", 80) or 80
        return max(10, min(22, avail - 48))

    def _bar(self, done, total, style, width):
        from rich.progress_bar import ProgressBar
        return ProgressBar(total=max(total, 1), completed=done, width=width,
                           complete_style=style, finished_style=style)

    def _row(self, table, label, done, total, color, bar_w, show_rate=True,
             bar_color=None):
        # bar_color separado de color: la barra NUNCA va en negrita (en varias fuentes
        # de terminal el glifo en bold se dibuja mas ancho por celda y empujaria el eta
        # fuera del recuadro). La etiqueta si puede ir en negrita para destacar el TOTAL.
        el = time.time() - self.t0
        rate = done / el if el > 0 else 0.0
        eta = (total - done) / rate if rate > 0 else None
        pct = f"{100 * done / total:>3.0f}%" if total else "  0%"
        table.add_row(
            f"[{color}]{label}[/]",
            self._bar(done, total, bar_color or color, bar_w),
            pct,
            f"{done}/{total}",
            _fmt_rate(rate) if show_rate else "",
            _fmt_eta(eta) if show_rate else "",
        )

    def _render(self):
        from rich.table import Table
        from rich.panel import Panel
        from rich import box
        bw = self._bar_width()
        t = Table.grid(padding=(0, 2))
        t.add_column(justify="left", min_width=9, no_wrap=True)   # label
        t.add_column(no_wrap=True)                                # bar
        t.add_column(justify="right", no_wrap=True)               # pct
        t.add_column(justify="right", no_wrap=True)               # done/total
        t.add_column(justify="right", no_wrap=True)               # rate
        t.add_column(justify="right", no_wrap=True)               # eta
        t.add_row("[dim]POR MÉTODO[/]", "", "", "[dim]done[/]",
                  "[dim]rate[/]", "[dim]eta[/]")
        for m, tot in self.method_tot.items():
            self._row(t, m, self.method_done[m], tot, _METHOD_RICH.get(m, "white"), bw)
        if self.family_tot:
            t.add_row("", "", "", "", "", "")
            t.add_row("[dim]POR FAMILIA[/]", "", "", "", "", "")
            for f, tot in self.family_tot.items():
                self._row(t, f, self.family_done[f], tot, _FAMILY_RICH, bw,
                          show_rate=False)
        t.add_row("[dim]" + "─" * 9 + "[/]", "", "", "", "", "")
        self._row(t, "TOTAL", self.done, self.total, "bold white", bw,
                  bar_color="white")
        title = f"[bold]FCV[/] · Floor-Ceiling Validation · {self.jobs} workers"
        return Panel(t, title=title, border_style="cyan", box=box.ROUNDED,
                     expand=False)

    def _summary(self):
        el = time.time() - self.t0
        rate = self.done / el if el > 0 else 0.0
        self.console.print(
            f"[green]✓[/] {self.done}/{self.total} celdas en "
            f"{_fmt_eta(el)} ({_fmt_rate(rate)})")


# --- 2) fallback: barras tqdm por metodo --------------------------------------
class _TqdmDashboard:
    _BAR = ("{desc:<9}{percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt}")
    _BAR_T = ("{desc:<9}{percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} "
              "[{rate_fmt} {remaining}]")

    def __init__(self, method_tot, family_tot, jobs, tqdm):
        total = sum(method_tot.values())
        pos = 0
        self.total_bar = tqdm(total=total, desc="TOTAL", position=pos,
                              colour="#ffffff", bar_format=self._BAR_T)
        pos += 1
        self.method_bars = {}
        for m, tot in method_tot.items():
            self.method_bars[m] = tqdm(total=tot, desc=m, position=pos,
                                       colour=_METHOD_HEX.get(m, "white"),
                                       bar_format=self._BAR)
            pos += 1
        self.family_bars = {}
        for f, tot in family_tot.items():
            self.family_bars[f] = tqdm(total=tot, desc=f, position=pos,
                                       colour=_FAMILY_HEX, bar_format=self._BAR)
            pos += 1

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        for b in list(self.method_bars.values()) + list(self.family_bars.values()):
            b.close()
        self.total_bar.close()
        return False

    def advance(self, method, family):
        self.total_bar.update(1)
        if method in self.method_bars:
            self.method_bars[method].update(1)
        if family in self.family_bars:
            self.family_bars[family].update(1)


# --- 3) fallback minimo: barra unica / impresion ------------------------------
class _PlainDashboard:
    def __init__(self, total):
        self.total, self.done, self._bar = total, 0, None
        try:
            from tqdm.auto import tqdm
            self._bar = tqdm(total=total, desc="FCV", unit="celda")
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if self._bar is not None:
            self._bar.close()
        return False

    def advance(self, method, family):
        self.done += 1
        if self._bar is not None:
            self._bar.update(1)
        elif self.done % 25 == 0 or self.done == self.total:
            print(f"  {self.done}/{self.total}", flush=True)


def _make_dashboard(method_tot, family_tot, jobs):
    try:
        from rich.console import Console
        console = Console()
        if console.is_terminal or console.is_jupyter:
            return _RichDashboard(method_tot, family_tot, jobs, console)
    except Exception:
        pass
    try:
        from tqdm.auto import tqdm
        return _TqdmDashboard(method_tot, family_tot, jobs, tqdm)
    except Exception:
        pass
    return _PlainDashboard(sum(method_tot.values()))


@contextmanager
def live_dashboard(tasks, jobs):
    """Context manager que elige el mejor dashboard disponible.

    `tasks` es la lista real de tasks; de ahi se derivan los totales por metodo y
    familia. Cede un objeto con `.advance(method, family)`.
    """
    method_tot, family_tot = _tally(tasks)
    dash = _make_dashboard(method_tot, family_tot, jobs)
    with dash:
        yield dash
