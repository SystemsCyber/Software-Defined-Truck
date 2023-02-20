# import numpy as np
# import matplotlib.pyplot as plt
# import matplotlib.animation as animation
# from mpl_toolkits.axes_grid1 import make_axes_locatable
# import time

# data = np.load('data.npy')
# data = 20*np.log10(abs(data))

# fig = plt.figure(figsize = (7, 7))
# ax = fig.add_subplot(111)

# #initialise subfigure (dimensions and parameters)
# im = ax.imshow(np.zeros((256, 128)), cmap = 'viridis', vmin = 0, vmax = 90, interpolation = 'none', aspect = 'auto')

# #get rid of spines and fix range of axes, rotate x-axis labels
# ax.spines['left'].set_visible(False)
# ax.spines['right'].set_visible(False)
# ax.spines['top'].set_visible(False)
# ax.spines['bottom'].set_visible(False)
# ax.xaxis.set_ticks_position('bottom')
# ax.yaxis.set_ticks_position('left')
# ax.xaxis.set_ticks(np.arange(0, 128, 5))
# ax.yaxis.set_ticks(np.arange(0, 256, 10))
# for tick in ax.get_xticklabels():
#     tick.set_rotation(90)

# #use a divider to fix the size of the colorbar
# divider = make_axes_locatable(ax)
# #colorbar on the right of ax. Colorbar width in % of ax and space between them is defined by pad in inches
# cax = divider.append_axes('right', size = '5%', pad = 0.07) 
# cb = fig.colorbar(im, cax = cax)
# #remove colorbar frame/spines
# cb.outline.set_visible(False)

# #don't stop after each subfigure change
# plt.show(block = False)

# #loop through array
# start = time.time()
# for i in range(data[0, 0, 2, :].size):
#     time.sleep(0.005)
#     im.set_array(data[:, :, 0, i])  
#     fig.canvas.draw()
# stop = time.time()
# print(stop-start)

# from rich.layout import Layout
# from rich.live import Live
# from rich.ansi import AnsiDecoder
# from rich.console import Group
# from rich.jupyter import JupyterMixin
# from rich.panel import Panel
# from rich.text import Text

# from time import sleep
# import plotext as plt

# def make_plot(width, height, phase = 0, title = ""):
#     plt.clf()
#     l, frames = 1000, 30
#     x = range(1, l + 1)
#     y = plt.sin(periods = 2, length = l, phase = 2 * phase  / frames)
#     plt.scatter(x, y, marker = "fhd")
#     plt.plotsize(width, height)
#     plt.xaxes(1, 0)
#     plt.yaxes(1, 0)
#     plt.title(title)
#     plt.theme('dark')
#     plt.ylim(-1, 1)
#     #plt.cls()
#     return plt.build()

# class plotextMixin(JupyterMixin):
#     def __init__(self, phase = 0, title = ""):
#         self.decoder = AnsiDecoder()
#         self.phase = phase
#         self.title = title

#     def __rich_console__(self, console, options):
#         self.width = options.max_width or console.width
#         self.height = options.height or console.height
#         canvas = make_plot(self.width, self.height, self.phase, self.title)
#         self.rich_canvas = Group(*self.decoder.decode(canvas))
#         yield self.rich_canvas

# def make_layout():
#     layout = Layout(name="root")
#     layout.split(
#         Layout(name="header", size=1),
#         Layout(name="main", ratio=1),
#     )
#     layout["main"].split_column(
#         Layout(name="static", ratio = 1),
#         Layout(name="dynamic"),
#     )
#     return layout

# layout = make_layout()

# header = layout['header']
# title = plt.colorize("Pl✺ text ", "cyan+", "bold") + "integration with " + plt.colorize("rich_", style = "dim")
# header.update(Text(title, justify = "left"))

# static = layout["static"]
# phase = 0
# mixin_static = Panel(plotextMixin(title = "Static Plot"))
# static.update(mixin_static)

# dynamic = layout["dynamic"]

# with Live(layout, refresh_per_second=0.0001) as live:
#     while True:
#         phase += 1
#         mixin_dynamic = Panel(plotextMixin(phase, "Dynamic Plot")) 
#         dynamic.update(mixin_dynamic)
#         #sleep(0.001)
#         live.refresh()

# from __future__ import annotations

# import asyncio

# try:
#     import httpx
# except ImportError:
#     raise ImportError("Please install httpx with 'pip install httpx' ")

# from rich.markdown import Markdown

# from textual.app import App, ComposeResult
# from textual.containers import Content
# from textual.widgets import Static, Input
# import plotext as plt; plt.clf()
# from random import randrange
# from rich.ansi import AnsiDecoder
# from rich.console import Group


# class DictionaryApp(App):
#     """Searches ab dictionary API as-you-type."""

#     CSS_PATH = "dictionary.css"

#     def compose(self) -> ComposeResult:
#         yield Content(Static(id="results", markup=True), id="results-container")

#     def on_mount(self) -> None:
#         """Called when app starts."""
#         # Give the input focus, so we can start typing straight away
#         # self.query_one(Input).focus()
#         asyncio.create_task(self.run_plot())

#     async def run_plot(self) -> None:
#         l = 300
#         actual = [randrange(0, 4) for i in range(l)]
#         predicted = [randrange(0,4) for i in range(l)]
#         labels = ['Autumn', 'Spring', 'Summer', 'Winter']

#         plt.cmatrix(actual, predicted, labels)
#         plt.plot_size(100, 100)
#         self.query_one("#results", Static).update(
#             Group(*AnsiDecoder().decode(plt.build())))

    # async def on_input_changed(self, message: Input.Changed) -> None:
    #     """A coroutine to handle a text changed message."""
    #     if message.value:
    #         # Look up the word in the background
    #         asyncio.create_task(self.lookup_word(message.value))
    #     else:
    #         # Clear the results
    #         self.query_one("#results", Static).update()

    # async def lookup_word(self, word: str) -> None:
    #     """Looks up a word."""
    #     url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
    #     async with httpx.AsyncClient() as client:
    #         results = (await client.get(url)).json()

    #     if word == self.query_one(Input).value:
    #         markdown = self.make_word_markdown(results)
    #         self.query_one("#results", Static).update(Markdown(markdown))

    # def make_word_markdown(self, results: object) -> str:
    #     """Convert the results in to markdown."""
    #     lines = []
    #     if isinstance(results, dict):
    #         lines.append(f"# {results['title']}")
    #         lines.append(results["message"])
    #     elif isinstance(results, list):
    #         for result in results:
    #             lines.append(f"# {result['word']}")
    #             lines.append("")
    #             for meaning in result.get("meanings", []):
    #                 lines.append(f"_{meaning['partOfSpeech']}_")
    #                 lines.append("")
    #                 for definition in meaning.get("definitions", []):
    #                     lines.append(f" - {definition['definition']}")
    #                 lines.append("---")

        # return "\n".join(lines)


if __name__ == "__main__":
    app = DictionaryApp()
    app.run()
