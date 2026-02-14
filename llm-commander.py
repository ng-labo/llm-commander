#!/usr/bin/env python3
"""
Simple terminal console base using prompt_toolkit.
- Left pane: streaming log / history (scrollable)
- Right top: status / info
- Right bottom: multiline input (Enter = submit, Shift+Enter = newline)
- Simple history and tab-completion for commands
"""


#####################
# application global setting
#####################

import os.path, json, sys, time, re


global_settings = {}
global_settings["coding-model"] = "openai/gpt-5.1-codex-mini"
#global_settings["general-model"] = "gpt-oss:120b"
global_settings["general-model"] = "openai/gpt-4o-mini"

coding_prompt = {}
coding_prompt["python2"] = """Python 2.7のレガシー環境向けコード生成器、Python 3の構文・標準ライブラリは使用禁止。"""
coding_prompt["java8"] = """Java8専用のレガシー環境向けコード生成器、Java9以降の機能(var, module system, Stream API拡張,Optional新メソッド,HttpClient,Records,Switch式)は使用禁止、標準ライブラリはjava.util,java.io,java.nioのみ。"""


LOG_FILE = 'llm-commander-log.json'


class UserHistory:
    def __init__(self):
        self.user_log = []

        if os.path.exists(LOG_FILE):
            with open(LOG_FILE) as f:
                self.user_log = json.load(f)

    def user_log(self):
        return self.user_log

    def answer(self, i):
        return self.user_log[i].get('answer') and self.user_log[i]['answer'] or ''

    def save(self):
        with open(LOG_FILE, 'w') as f:
            json.dump(self.user_log, f)

    def append(self, query, text, model):
        self.user_log.append({"query": query, "answer": text, "model": model})
        self.save()

    def get_query_all(self):
        return [x['query'] for x in self.user_log if x.get('query')]


user_history = UserHistory()


#####################
# ollama
#####################
from utils import perform, ollamalist

#####################
#  clipboard
#####################
from utils import cbcopy


#####################
#  terminal
#####################
import asyncio
from prompt_toolkit.application import Application
from prompt_toolkit.document import Document
from prompt_toolkit.layout import Layout, HSplit, VSplit, Window
from prompt_toolkit.widgets import TextArea, Label, Frame
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from prompt_toolkit.completion import Completer, Completion

from prompt_toolkit.layout.controls import FormattedTextControl

class InternalCache:
    # input-area
    history = []
    index = 0
    last_model = None

    # list-area
    list_area_Y = 0

    # log-area
    log_area_Y = 0

    # popup status
    popup_active = False

    model = global_settings["coding-model"]

    code_language = "python"

    def __init__(self):
        pass

    def set_model(self, m):
        self.model = m 

    def set_lang(self, l):
        self.code_language = l

_C = InternalCache()

# --- UI widgets ---
# for output
log_area = TextArea(
    text="",
    scrollbar=True,
    focusable=False,
    wrap_lines=True,
    read_only=True,
)

# for small information
def ready_status():
    return f"{_C.code_language}, {_C.model} ...Ready"
    
status = Label(text=ready_status(), dont_extend_height=True)

# for user input
input_area = TextArea(
    height=6,
    prompt="> ",
    multiline=True,
    wrap_lines=True,
    dont_extend_height=False,
)

# --- Simple completer (plug-in) ---
class SimpleCompleter(Completer):
    def __init__(self, words):
        self.words = words

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor.lower()
        for w in self.words:
            if w.startswith(text) and text:
                yield Completion(w, start_position=-len(text))

# Attach a simple completer (for single-word completions)
completer = SimpleCompleter(["run", "stop", "status", "clear", "help", "exit", "tail", "stream"])
input_area.completer = completer

# for user log titles
list_area = TextArea(text="\n".join(user_history.get_query_all()), read_only=True, )


#
# Layout
frames = {}
frames['log_area'] = Frame(log_area, title="Output") #, width=80)
frames['status'] = Frame(status, title="Status")
frames['input_area'] = Frame(input_area, title="Input (Enter=newline, Control+J=send)")
frames['list_area'] = Frame(list_area, title="List")
root_container = VSplit(
    [ HSplit([frames['status'], frames['input_area'], frames['list_area']], width=80),
      frames['log_area'], ],
    #  Frame(log_area, title="Log / Output", width=80),
    #  HSplit([Frame(status, title="Status"), Frame(input_area, title="Input (Enter=newline, Control+J=send)")], padding=1),
    #],
    padding=1,
)

root_container_2 = VSplit(
    [ HSplit([frames['status'], frames['input_area']], width=80), frames['log_area'], ],
    padding=1,
)

from prompt_toolkit.application.current import get_app
def get_frame_height(frame_widget):
    app = get_app()
    return app.renderer._last_size


# --- Key bindings ---
kb = KeyBindings()

# ポップアップウィンドウのコンテンツ
def create_popup_content():
    popup_text = FormattedTextControl(text="ポップアップメッセージ\n\n[Enter]で閉じる")
    return Window(content=popup_text, width=30, height=5)

# メイン画面のコンテンツ
def create_main_content():
    main_text = FormattedTextControl(text="メイン画面\n\n[s]キーでポップアップ表示\n[q]キーで終了")
    return Window(content=main_text)

@kb.add('c-y')
def show_popup(event):
    _C.popup_active = True

    # ポップアップ表示用のレイアウトを作成
    popup_window = create_popup_content()
    #main_window = create_main_content()
    
    # ポップアップを中央に配置するためのコンテナ
    overlay = HSplit([
        Window(height=5),  # 上部のスペース
        VSplit([
            Window(width=10),  # 左側のスペース
            popup_window,
            Window(width=10),  # 右側のスペース
        ]),
        Window(height=5),  # 下部のスペース
    ])
    
    # 新しいルートコンテナを設定
    event.app.layout.container = overlay
    event.app.layout.focus(popup_window)


background_stream_alive = True
@kb.add("c-q")
def _(event):
    """Ctrl-Q to exit cleanly."""
    global background_stream_alive
    background_stream_alive = False
    time.sleep(0.1)
    event.app.exit()


@kb.add("c-l")
def _(event):
    """Ctrl-L clear log."""
    log_area.text = ""
    status.text = " Cleared log "


#@kb.add("enter")
@kb.add("c-j")
def _(event):
    if _C.popup_active:
        # 元のメイン画面に戻す
        main_window = create_main_content()
        event.app.layout.container = root_container
        appacahe.popup_active = False
        #event.app.layout.focus(main_window)
        return

    buf = input_area.text.strip()
    if not buf:
        # nothing to send
        return
    asyncio.ensure_future(handle_input(buf))


@kb.add("c-c")
def _(event):
    """Ctrl-C to copy text to clip-buffer."""
    cbcopy(log_area.text)


@kb.add("c-s")
def _(event):
    """Ctrl-S to save question-answer into file."""
    if event.app.layout.has_focus(frames['input_area']):
        if input_area.text and log_area.text:
            user_history.append(input_area.text, log_area.text, _C.last_model)


@kb.add("up")
def _(event):
    """Browse history with Up/Down when input is focused."""
    if event.app.layout.has_focus(frames['log_area']):
        # log_area focused
        #nlpos = [i for i, t in enumerate(log_area.text) if t == '\n']
        #print(nlpos, get_frame_height(frames['log_area']))
        _C.log_area_Y = _C.log_area_Y > 0 and _C.log_area_Y - 1 or 0
        log_lines = log_area.text.split('\n')
        log_area.buffer.cursor_position = sum([len(x)+1 for x in log_lines[0:_C.log_area_Y]])

    elif event.app.layout.has_focus(frames['list_area']):
        # up cursor like position in line oriented
        _C.list_area_Y = _C.list_area_Y > 0 and _C.list_area_Y - 1 or 0
        queries_list = user_history.get_query_all()
        list_area.buffer.cursor_position = sum([len(x)+1 for x in queries_list[0:_C.list_area_Y]])
        # apply for log_area 
        log_area.text = user_history.answer(_C.list_area_Y)

    else:
        if not _C.history:
            return
        _C.index = max(0, _C.index - 1)
        input_area.buffer.document = Document(_C.history[_C.index], len(_C.history[_C.index]))


@kb.add("down")
def _(event):
    if event.app.layout.has_focus(frames['log_area']):
        log_lines = log_area.text.split('\n')
        _C.log_area_Y = _C.log_area_Y < len(log_lines) - 1 and _C.log_area_Y + 1 or len(log_lines) - 1
        log_area.buffer.cursor_position = sum([len(x)+1 for x in log_lines[0:_C.log_area_Y]])

    elif event.app.layout.has_focus(frames['list_area']):
        # down cursor like position in line oriented
        queries_list = user_history.get_query_all()
        _C.list_area_Y = _C.list_area_Y < len(queries_list) - 1 and _C.list_area_Y + 1 or len(queries_list) - 1
        list_area.buffer.cursor_position = sum([len(x) + 1 for x in queries_list[0:_C.list_area_Y]])
        # apply for log_area 
        log_area.text = user_history.answer(_C.list_area_Y)

    else:
        if not _C.history:
            return
        _C.index = min(len(_C.history) - 1, _C.index + 1)
        input_area.buffer.document = Document(_C.history[_C.index], len(_C.history[_C.index]))

@kb.add('tab')
def _(event):
    if event.app.layout.has_focus(frames['log_area']):
        event.app.layout.focus(input_area)
        #log_area.buffer.cursor_position = len(log_area.text)
        log_area.text = ""

    elif event.app.layout.has_focus(frames['input_area']):
        event.app.layout.focus(list_area)
        # list cursor position
        queries_list = user_history.get_query_all()
        list_area.buffer.cursor_position = sum([len(x)+1 for x in queries_list[0:_C.list_area_Y]])
        # and set log_area text
        log_area.text = user_history.answer(_C.list_area_Y)

    else:
        event.app.layout.focus(log_area)

@kb.add("c-n")
def _(event):
    _C.set_model(_C.model == global_settings["coding-model"] and global_settings["general-model"] or global_settings["coding-model"])
    status.text = ready_status()

@kb.add("c-t")
def _(event):
    if event.app.layout.has_focus(frames['input_area']):
        m = re.search(r'%\d%', input_area.text)
        if m: 
            N = re.match(r'%(\d)%', m.group(0)).group(1)
            with open(N) as f:
                new_text = f.read().strip()
            input_area.text = re.sub(m.group(0) ,new_text, input_area.text)

@kb.add("c-p")
def _(event):
    frames['input_area'].height = None
    input_area.height = None
    event.app.layout.container = root_container_2
    event.app.layout.focus(input_area)
    get_app().invalidate()


@kb.add("c-o")
def _(event):
    input_area.height = 6
    frames['input_area'].height = 6
    event.app.layout.container = root_container
    get_app().invalidate()

# --- Helpers ---
def append_log(text: str):
    # Keep cursor at bottom after appending
    if log_area.text:
        log_area.text = log_area.text + "\n" + text
    else:
        log_area.text = text
    # move scrollbar to bottom by setting cursor
    log_area.buffer.cursor_position = len(log_area.text)


async def handle_input(text: str):
    global background_stream_alive
    """
    Example handler: recognize a few commands, or simulate streaming output.
    Replace/extend this to call actual local logic / external processes.
    """
    status.text = " Processing... "
    # built-in commands
    if text == "help":
        append_log("Commands: help, clear, exit")
        append_log("ctrl+c: copy log buffer into clipboard")
        append_log("ctrl+m: change model")
        append_log("ctrl+t: replace text in input-area")
        append_log("ctrl+s: save query-answer")
        append_log(">language change coding language")

    elif text == "clear":
        log_area.text = ""
        input_area.text = ""

    elif text == "exit":
        background_stream_alive = False
        append_log("Bye.")
        await asyncio.sleep(0.1)
        app.exit()

    elif text.startswith("stream"):
        # simulate streaming output asynchronously (n lines)
        parts = text.split()
        n = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 10
        for i in range(1, n + 1):
            append_log(f"[stream] line {i}")
            await asyncio.sleep(0.15)  # simulate delay
        append_log("[stream] done")

    elif text.startswith("list"):
        models = ollamalist()['ollama.com']
        append_log(f"{models}")
        input_area.text = ""

    elif text.startswith('>'):
        new_language = text[1:]
        _C.set_lang(new_language)
        input_area.text = ""

    elif text.startswith("@"):
        if not OLLAMA_MODELS:
            ollamalist()
        args = text.split()
        model = None
        for m in OLLAMA_MODELS:
            if m.startswith(args[0][1:]):
                model = m
                break
        content = text[len(args[0])+1:].strip()
        #append_log(f"Q:{content}")
        params = {'content': content}
        if model:
            params['model'] = model
        result = await asyncio.to_thread(perform, params)
        append_log(f"{result['model']}: {result['content']}")

    else:
        content = text.strip()
        params = {'content': content}
        params['model'] = _C.model
        if _C.model == global_settings['general-model']:
            # 普通の質問
            pass
        else:
            # コード生成呼び出し
            if _C.code_language in coding_prompt:
                param['system'] = coding_prompt[_C.code_language] + "\n回答となるコードのみを出力してください。"
            else:
                params['system'] = f'{_C.code_language} コード生成器として、回答となるコードのみを出力してください。'
        result = await asyncio.to_thread(perform, params)
        #append_log(result['content'])
        log_area.text = result['content']
        _C.last_model = _C.model

    status.text = ready_status()

# --- Build application ---
style = Style.from_dict({
    "status": "#ffffff bg:#444444",
})

layout = Layout(root_container, focused_element=input_area)

app = Application(layout=layout, key_bindings=kb, full_screen=True, style=style)

# --- Optional: background task that injects periodic messages (simulates external streams) ---
import threading
def background_task():
    global background_stream_alive
    i = 0
    #append_log(f"[bg] in background_task {background_stream_alive}")
    while background_stream_alive:
        for _ in range(100):
            time.sleep(0.1)
            if not background_stream_alive:
                break
        if not background_stream_alive:
            break
        i += 1
        #append_log(f"[bg] heartbeat {i}")

    print("byebye")


# --- Runner ---
def main():
    # schedule background task
    bt = threading.Thread(target=background_task, args=(), kwargs={})
    bt.start()
    try:
        app.run()
    except Exception as e:
        print("Exited:", e)
    bt.join()


if __name__ == "__main__":
    if len(sys.argv) == 2:
        global_settings["language"] = sys.argv[1]
    main()
