import json, re, requests, traceback
from myid import OPENROUTER_API_KEY

headers ={
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    #"HTTP-Referer": "<YOUR_SITE_URL>", # Optional. Site URL for rankings on openrouter.ai.
    #"X-Title": "<YOUR_SITE_NAME>", # Optional. Site title for rankings on openrouter.ai.
}

def openrouterai_models(filter_words=[], desired_items=[]):
    """
    available items in 2026.1.30
    ['id', 'canonical_slug', 'hugging_face_id', 'name', 'created', 'description',
     'context_length', 'architecture', 'pricing', 'top_provider', 'per_request_limits',
     'supported_parameters', 'default_parameters', 'expiration_date']
    """
    if isinstance(filter_words, str):
        filter_words = [filter_words,]
    if isinstance(desired_items, str):
        desired_items = [desired_items,]
    try:
        res= requests.get(
            url="https://openrouter.ai/api/v1/models",
            headers=headers,
            timeout=(10, 120))
        d = json.loads(res.text)
        if d.get('data'):
            ret = {}
            KEYS = ['name', 'context_length',] 
            for i in desired_items:
                if not i in KEYS:
                    KEYS.append(i)
            regptn = filter_words and '|'.join([re.escape(x) for x in filter_words]) 
            for r in d['data']:
                if not r.get('id'): continue
                if regptn and not re.search(regptn, r['id']): continue
                ret[r['id']] = dict([(k, r[k]) for k in r if k in KEYS])
        else:
            ret = d

    except:
        traceback.print_exc()
        ret = {}

    return ret

def openrouterai_invoke(model, content, messages, **kw):
    request = {}
    request['model'] = model
    request['messages'] = list(messages)
    request['messages'].append({"role": "user", "content": content})
    if kw.get('temperature'):
        request['temperature'] = kw['temperature']
    if kw.get('top_p'):
        request['top_p'] = kw['top_p']

    data = json.dumps(request)

    retry_max = 3
    while retry_max > 0:
        try:
            res= requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                data=data,
                timeout=(10, 120))
            if res.status_code in (400, 401, 404):
                print(f"{res.status_code} in openrouterai_invoke")
                res.raise_for_status()
                break

            if res.status_code != 200:
                print(f"{res.status_code} in openrouterai_invoke")
                retry_max -= 1
                time.sleep(20.0)
                continue

            d = json.loads(res.text)
            if not d.get("choices"):
                retry_max -= 1
                print(f"no candidates on response in openrouterai_invoke", d)
                time.sleep(20.0)
                continue

            ret = {"content" : d["choices"][0]["message"]["content"]}
            if d.get('usage'):
                ret['prompt_eval_count'] = d['usage']['prompt_tokens']
                ret['eval_count'] = d['usage']['completion_tokens']

            if d.get('model'):
                ret['model'] = d['model']

            return ret

        except:
            traceback.print_exc()
            time.sleep(20.0)
            continue

    return {}
