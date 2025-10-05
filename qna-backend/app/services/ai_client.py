# app/services/ai_client.py
import os
import time
import inspect
from dotenv import load_dotenv

load_dotenv()

GEMINI_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
if not GEMINI_KEY:
    print("[ai_client] WARNING: GEMINI_API_KEY not set; AI calls will fail until set.")

_has_new_genai = False
_has_old_genai = False
_client = None
_old_genai = None


try:
    from google import genai  # type: ignore
    try:
        _client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else genai.Client()
    except Exception:
        _client = genai.Client()
    _has_new_genai = True
    print("[ai_client] Detected new google-genai SDK (genai.Client).")
except Exception:
    _has_new_genai = False

if not _has_new_genai:
    try:
        import google.generativeai as genai  # type: ignore
        genai.configure(api_key=GEMINI_KEY)
        _old_genai = genai
        _has_old_genai = True
        print("[ai_client] Detected older google.generativeai SDK.")
    except Exception:
        _has_old_genai = False

if not _has_new_genai and not _has_old_genai:
    raise ImportError("No Google GenAI SDK found. Install `google-genai` or `google-generativeai`.")

def _extract_text(resp) -> str:
    try:
        output = getattr(resp, "output", None)
        if output and len(output) > 0:
            c = getattr(output[0], "content", None)
            if c and len(c) > 0:
                part = c[0]
                text = getattr(part, "text", None) or (part.get("text") if isinstance(part, dict) else None)
                if text:
                    return text.strip()
    except Exception:
        pass

    try:
        candidates = getattr(resp, "candidates", None)
        if candidates and len(candidates) > 0:
            c0 = candidates[0]
            cont = getattr(c0, "content", None)
            if cont and len(cont) > 0:
                part = cont[0]
                text = getattr(part, "text", None) or (part.get("text") if isinstance(part, dict) else None)
                if text:
                    return text.strip()
    except Exception:
        pass


    try:
        t = getattr(resp, "text", None)
        if t:
            return t.strip()
    except Exception:
        pass

    return str(resp)

def _call_with_signature(func, payload_variants: dict):

    sig = None
    try:
        sig = inspect.signature(func)
    except Exception:
        sig = None

    tried = []
    for name, kwargs in payload_variants.items():

        if sig:
            accepted = []
            for k in kwargs.keys():
                if k in sig.parameters:
                    accepted.append(k)

            accepts_varkw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
            if not accepted and not accepts_varkw:

                tried.append((name, "skipped - signature doesn't accept keys"))
                continue

            if accepts_varkw:
                call_kwargs = kwargs
            else:
                call_kwargs = {k: v for k, v in kwargs.items() if k in sig.parameters}
        else:

            call_kwargs = kwargs

        tried.append((name, f"trying with keys={list(call_kwargs.keys())}"))
        try:
            resp = func(**call_kwargs)
            return resp, tried
        except TypeError as te:
            tried.append((name, f"TypeError: {te}"))

        except Exception as e:
            tried.append((name, f"Exception: {e}"))
            raise

    raise TypeError(f"All payload variants failed. Attempts: {tried}")

def ask_gemini_sync(question: str,
                    model: str = DEFAULT_MODEL,
                    max_output_tokens: int = 512,
                    temperature: float = 0.2,
                    retries: int = 2,
                    backoff: float = 1.0) -> str:
 
    if not question or not question.strip():
        return ""

    last_err = None
    for attempt in range(retries + 1):
        try:

            if _has_new_genai and _client is not None:
                try:
                    chat_api = getattr(_client, "chat", None)
                    if chat_api is not None and hasattr(chat_api, "completions") and hasattr(chat_api.completions, "create"):
                        print("[ai_client] Using client.chat.completions.create(...)")
                        resp = chat_api.completions.create(
                            model=model,
                            messages=[
                                {"role": "system", "content": "You are a concise helpful assistant."},
                                {"role": "user", "content": question}
                            ],
                            temperature=temperature,
                            max_output_tokens=max_output_tokens
                        )
                        return _extract_text(resp)

                    models_obj = getattr(_client, "models", None)
                    if models_obj is None:
                        raise RuntimeError("genai.Client has no .models attribute")

       
                    candidate_names = ["generate_content", "generate", "create", "call", "generate_text"]
                    func = None
                    func_name = None
                    for n in candidate_names:
                        if hasattr(models_obj, n):
                            f = getattr(models_obj, n)
                            if callable(f):
                                func = f
                                func_name = f"models.{n}"
                                break

                    if func is None:
                        for n in ["generate_text", "generate"]:
                            if hasattr(_client, n) and callable(getattr(_client, n)):
                                func = getattr(_client, n)
                                func_name = n
                                break

                    if func is None:
                        raise RuntimeError("No suitable generate function found on genai client.models or client")

                    print(f"[ai_client] Using detected function: {func_name}")

                    messages_variant = [{"role": "system", "content": "You are a concise helpful assistant."},
                                         {"role": "user",   "content": question}]
                    payload_variants = {
                        "messages": {"messages": messages_variant, "model": model},
                        "contents": {"contents": [question], "model": model},
                        "input":    {"input": question, "model": model},
                        "prompt":   {"prompt": question, "model": model},
                    }


                    token_param_names = ["max_output_tokens", "max_tokens", "max_tokens_to_sample"]
                    temp_param_names = ["temperature", "temp"]

        
                    try:
                        resp, trace = _call_with_signature(func, payload_variants)
                        print("[ai_client] Call succeeded with trace:", trace)
                        return _extract_text(resp)
                    except TypeError as te:
             
                        print("[ai_client] base payload shapes failed, trying with token/temp variations:", te)
                        augmented_variants = {}
                        for name, base in payload_variants.items():
                            for tk in token_param_names + temp_param_names:
                                v = dict(base)
                            
                                if tk in token_param_names:
                                    v[tk] = max_output_tokens
                                else:
                                    v[tk] = temperature
                                augmented_variants[f"{name}+{tk}"] = v
                
                        resp, trace = _call_with_signature(func, augmented_variants)
                        print("[ai_client] Augmented call succeeded with trace:", trace)
                        return _extract_text(resp)

                except Exception as e:
                    print(f"[ai_client] New SDK attempt failed on try {attempt}: {e}")
                    raise


            if _has_old_genai and _old_genai is not None:
                try:
                    print("[ai_client] Using older google.generativeai path")
                    if hasattr(_old_genai, "ChatCompletion") and hasattr(_old_genai.ChatCompletion, "create"):
                        resp = _old_genai.ChatCompletion.create(
                            model=model,
                            messages=[
                                {"role": "system", "content": "You are a concise helpful assistant."},
                                {"role": "user", "content": question}
                            ],
                            temperature=temperature,
                            max_output_tokens=max_output_tokens
                        )
                        return _extract_text(resp)
                    if hasattr(_old_genai, "generate_text"):
                        resp = _old_genai.generate_text(model=model, prompt=question, max_output_tokens=max_output_tokens)
                        return _extract_text(resp)
                    raise RuntimeError("No compatible function on older SDK")
                except Exception as e:
                    print(f"[ai_client] Older SDK attempt failed: {e}")
                    raise

            raise RuntimeError("No compatible Google GenAI SDK available")

        except Exception as e:
            last_err = e
            if attempt < retries:
                sleep = backoff * (2 ** attempt)
                print(f"[ai_client] Attempt {attempt+1} failed: {e}; retrying after {sleep}s...")
                time.sleep(sleep)
                continue
            else:
                raise RuntimeError(f"Gemini/GenAI request failed after {retries+1} attempts: {e}") from e

    raise RuntimeError("Unreachable: ask_gemini_sync failed unexpectedly")
