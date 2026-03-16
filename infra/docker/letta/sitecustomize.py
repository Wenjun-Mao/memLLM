from __future__ import annotations

try:
    import nltk
except Exception:
    nltk = None
else:
    _real_download = nltk.download

    def _memllm_safe_download(info_or_id=None, *args, **kwargs):
        if info_or_id == 'punkt_tab':
            try:
                nltk.data.find('tokenizers/punkt_tab')
                return True
            except LookupError:
                pass
        return _real_download(info_or_id, *args, **kwargs)

    nltk.download = _memllm_safe_download
