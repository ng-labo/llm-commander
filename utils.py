#!/usr/bin/env python3

#####################
# ollama
#####################
import requests
import traceback
import json, time, sys
from openrouterai import openrouterai_invoke

default_model = 'gpt-oss:120b'

from myid import OLLAMA_APIKEY

THINKING_MODELS = ('gpt-oss:20b', 'gpt-oss:120b', 'deepseek-v3.1:671b',)

chat_system_prompt = '日本語で流暢に答えてください。リラックスした雰囲気の話し方をしてください。'

def url_base(target, model):
    return 'https://ollama.com/api/'


def ollama_api_invoke(body, api_path, model=default_model, target=None):
    headers = {"Content-Type": "application/json"}
    headers['Authorization'] = OLLAMA_APIKEY
    url_head = url_base(target, model)

    while True:
        response = requests.post(url_head + api_path, headers=headers, json=body)
        # 400は、リクエストが間違えてる
        if response.status_code in (400, 404):
            response.raise_for_status()
            break

        if response.status_code != 200:
            time.sleep(10.0)
            print("try again", response.status_code, model, url_head)
            continue

        response.raise_for_status()
        break

    return json.loads(response.text)


def ollama_health(model):
    if not model in OLLAMA_MODELS:
        return 501

    headers = {"Content-Type": "application/json"}
    url_head = url_base('localhost', model)
    headers['Authorization'] = OLLAMA_APIKEY

    body = {
        "model": model,
        "stream": False,
        "prompt": 'Say yes, to check your health'
    }
    response = requests.post(url_head + 'generate', headers=headers, json=body)
    return response.status_code


def ollama_web_search(query):

    headers = {"Content-Type": "application/json"}
    headers['Authorization'] = OLLAMA_APIKEY
    body = {
        "query": query,
    }
    response = requests.post('https://ollama.com/api/web_search', headers=headers, json=body)
    if response.status_code != 200:
        return {"result": f"failed ({response.status_code})"}

    return json.loads(response.text)


def simple(content, model=default_model, **kw):
    options = {}
    if kw.get("temperature"):
        options["temperature"] = kw["temperature"]
    if kw.get("top_p"):
        options["top_p"] = kw["top_p"]

    body = {
        "model": model,
        "stream": False,
        "prompt": content,
    }
    if options:
        body["options"] = options

    return ollama_api_invoke(body, 'generate', model, target)


def chat(messages, model=default_model, **kw):
    target = None

    options = {}
    if kw.get("temperature"):
        options["temperature"] = kw["temperature"]
    if kw.get("top_p"):
        options["top_p"] = kw["top_p"]

    body = {
        "model": model,
        "stream": False,
        "messages": messages,
    }
    if options:
        body["options"] = options

    if model in THINKING_MODELS and kw.get("think"):
        body["think"] = kw.get("think")

    return ollama_api_invoke(body, 'chat', model, target)


OLLAMA_MODELS = []


def ollamalist():
    ret = {}

    if OLLAMA_MODELS:
        ret['ollama.com'] = tuple(OLLAMA_MODELS)
        return ret

    headers = {"Content-Type": "application/json"}
    headers['Authorization'] = OLLAMA_APIKEY
    res = requests.get('https://ollama.com/api/tags', headers=headers)
    if res.status_code == 200:
        models = res.json()
        if isinstance(models, dict) and models.get('models'):
            for model in models['models']:
                OLLAMA_MODELS.append(model['model'])
        ret['ollama.com'] = tuple(OLLAMA_MODELS)

    return ret


def make_available_models():
    ret = []
    [ ret.extend(x) for x in ollamalist().values() ]
    return tuple(ret)


# 使えるモデル一覧
enable_models = make_available_models()


def init_messages(system="日本語の自然な表現を優先して、できるだけ流暢に回答してください。"):
    return [{"role": "system", "content": system}]


def perform(args):
    res = {}
    st = time.time()

    try:
        model = 'model' in args and args['model'] or default_model
        system = 'system' in args and args['system'] or chat_system_prompt
        content = args['content']
        messages = init_messages(system)
        if 'history' in args and type(args['history'])==list:
            for r, c in args['history']:
                messages.append({"role": r, "content": c})

        kw = {}
        if args.get("temperature"):
            kw['temperature'] =  args["temperature"]
        if args.get("top_p"):
            kw['top_p'] =  args["top_p"]

        if model in ('openai/gpt-5.1-codex-mini', 'openai/gpt-4o-mini'):
            pass
            
        elif model not in enable_models:
            cands = [ m for m in enable_models if model.startswith(m) ]
            model = cands and cands[0] or default_model
            if model == default_model: print("fall back to", model)

        if model in ('openai/gpt-5.1-codex-mini', 'openai/gpt-4o-mini'):
            res = openrouterai_invoke(model, content, messages, **kw)

        elif system:
            # chat
            messages.append({"role": "user", "content": content})
            r = chat(messages, model, **kw)
            res['model'] = r['model']
            res['content'] = r['message']['content']
            if r['message'].get('thinking'):
                res['thinking'] = r['message']['thinking']

        else:
            # generate
            r = simple(content, model)
            res['model'] = r['model']
            res['content'] = r['response']

    except Exception as exception:
        traceback.print_exc()
        res['exception'] = str(type(exception))

    res['elapsed'] = time.time() - st
    return res

#####################
#  clipboard
#####################

import subprocess
def cbcopy(s):
    if isinstance(s, list):
        s = "\n".join(s)

    if isinstance(s, str):
        p = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE, text=True)
        p.communicate(s)

