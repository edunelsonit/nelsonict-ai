"""One local model; exclusive generation without blocking administration."""
import threading
import time
from pathlib import Path
from .config import settings

class ModelRuntime:
    def __init__(self):
        self.gate = threading.Lock()
        self.model = None
        self.config = None
        self.error = None
        self.loading = False
        self.active = {}

    def path(self, filename):
        if Path(filename).name != filename or not filename.lower().endswith(".gguf"):
            raise ValueError("Choose a GGUF filename from the model directory.")
        root = settings.models_dir.resolve()
        path = (root / filename).resolve()
        if path.parent != root or not path.is_file():
            raise ValueError("Model file is missing or outside the model directory.")
        return path

    def load(self, config):
        if not self.gate.acquire(blocking=False):
            raise RuntimeError("Model is busy. Stop generation before changing it.")
        self.loading = True
        self.error = None
        try:
            path = self.path(config["filename"])
            with path.open("rb") as handle:
                if handle.read(4) != b"GGUF":
                    raise ValueError("File does not have a valid GGUF header.")
            from llama_cpp import Llama
            if self.model:
                self.model.close()
                self.model = None
                self.config = None
            self.model = Llama(model_path=str(path), n_ctx=config["context"],
                               n_threads=config["threads"], n_gpu_layers=config["gpu_layers"],
                               chat_format=config.get("chat_format") or None, verbose=False)
            self.config = config
        except Exception as exc:
            self.error = str(exc)[:400]
            raise
        finally:
            self.loading = False
            self.gate.release()

    def unload(self):
        if not self.gate.acquire(blocking=False):
            raise RuntimeError("Model is busy. Stop generation first.")
        try:
            if self.model:
                self.model.close()
            self.model = None
            self.config = None
        finally:
            self.gate.release()

    def reserve(self, conversation_id, user_id):
        if not self.gate.acquire(blocking=False):
            raise RuntimeError("Another response or model operation is running. Try again shortly.")
        if not self.model:
            self.gate.release()
            raise RuntimeError("No model is loaded. Ask an administrator to load a GGUF model.")
        event = threading.Event()
        self.active[conversation_id] = (user_id, event)
        return event

    def release(self, conversation_id):
        self.active.pop(conversation_id, None)
        self.gate.release()

    def cancel(self, conversation_id, user_id):
        item = self.active.get(conversation_id)
        if item and item[0] == user_id:
            item[1].set()
            return True
        return False

    def fit(self, instructions, question, history, sources):
        budget = self.config["context"] - self.config["max_tokens"] - 384
        def tokens(text):
            return len(self.model.tokenize(text.encode("utf-8")))
        system = instructions
        selected = []
        used = tokens(system) + tokens(question) + 32
        if used >= budget:
            raise ValueError("Message or assistant instructions exceed the model context. Shorten them.")
        for source in sources:
            passage = f"\n[{source['id']}] {source['name']} page {source['page']}\n{source['text']}\n"
            cost = tokens(passage) + 16
            if used + cost < budget:
                system += passage
                used += cost
                selected.append(source)
        kept = []
        for message in reversed(history):
            cost = tokens(message["content"]) + 32
            if used + cost >= budget:
                break
            kept.insert(0, {"role": message["role"], "content": message["content"]})
            used += cost
        return [{"role": "system", "content": system}, *kept,
                {"role": "user", "content": question}], selected

    def stream(self, messages, stop):
        from llama_cpp import StoppingCriteriaList
        started = time.monotonic()
        events = self.model.create_chat_completion(
            messages=messages, stream=True, max_tokens=self.config["max_tokens"],
            temperature=self.config["temperature"],
            stopping_criteria=StoppingCriteriaList([lambda *_: stop.is_set() or time.monotonic() - started > 300]))
        for item in events:
            if stop.is_set():
                break
            text = item["choices"][0].get("delta", {}).get("content")
            if text:
                yield text
        if time.monotonic() - started > 300:
            raise TimeoutError("Generation time limit reached; partial answer saved.")

    def status(self):
        return {"loaded": self.model is not None, "config": self.config, "error": self.error,
                "loading": self.loading, "busy": self.gate.locked()}


runtime = ModelRuntime()
