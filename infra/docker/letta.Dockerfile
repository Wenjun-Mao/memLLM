FROM letta/letta:latest

COPY infra/docker/letta/sitecustomize.py /opt/memllm-overrides/sitecustomize.py

ENV PYTHONPATH=/opt/memllm-overrides
